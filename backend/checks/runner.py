"""Run all approved requirements against the pages of one crawl and build Findings.

Order per finding: check -> verify the quote verbatim against the page text -> gate
possible_gap (enough pages, no fetch errors) -> machine-translate the verified quote.
"""

import os
import time
from typing import Callable

from backend.checks.evidence import verify_quote
from backend.checks.llm_checks import TIMEOUT_REASON, check_presence, hint_sections, translate
from backend.checks.types import CheckOutcome
from backend.checks.uz_version import check_uz_version
from backend.crawl.crawler import CrawlResult
from backend.crawl.sections import page_in_section
from backend.llm.provider import LLMProvider
from backend.models import Finding, Requirement


def min_pages_for_gap() -> int:
    return int(os.getenv("CHECK_MIN_PAGES_FOR_GAP") or 5)


def run_one(req: Requirement, crawl: CrawlResult, llm: LLMProvider | None) -> CheckOutcome:
    if crawl.status != "ok":
        return CheckOutcome("not_checkable", reason=crawl.reason or f"crawl: {crawl.status}")
    if req.check_type == "uz_version":
        return check_uz_version(req, crawl.pages, crawl.has_language_switcher)
    if req.check_type in ("required_document", "key_info"):
        return check_presence(req, crawl.pages, llm)
    return CheckOutcome("not_checkable", reason=f"unknown check type {req.check_type}")


def finalize(out: CheckOutcome, crawl: CrawlResult, req: Requirement | None = None
             ) -> CheckOutcome:
    """Enforce the evidence and gating rules on a raw outcome."""
    if out.status == "possible_gap" and out.absence and out.page is not None:
        # "No evidence found": nothing to quote; a context passage must still be verbatim.
        if out.context and not verify_quote(out.context, out.page.text):
            out = CheckOutcome(out.status, reason=out.reason, page=out.page,
                               llm_used=out.llm_used, absence=True)
    elif out.status in ("ok", "possible_gap"):
        if out.page is None or not verify_quote(out.quote, out.page.text):
            return CheckOutcome("not_checkable", page=out.page, llm_used=out.llm_used,
                                reason="evidence quote not found verbatim in the page text; "
                                       f"original outcome {out.status}: {out.reason}")
    if out.status == "possible_gap":
        n, need = crawl.unique_pages, min_pages_for_gap()
        if n < need:
            return CheckOutcome("not_checkable", page=out.page, quote=out.quote,
                                llm_used=out.llm_used, context=out.context,
                                reason=f"only {n} page(s) read (at least {need} needed to "
                                       f"report a possible gap): {out.reason}")
        if crawl.fetch_errors:
            return CheckOutcome("not_checkable", page=out.page, quote=out.quote,
                                llm_used=out.llm_used, context=out.context,
                                reason=f"site had {len(crawl.fetch_errors)} fetch error(s), "
                                       f"e.g. {crawl.fetch_errors[0]}: {out.reason}")
        # A gap needs at least one page of the section where the evidence would be.
        sections = hint_sections(req) if req is not None else []
        home = crawl.pages[0].url if crawl.pages else None
        if sections and not any(p.readable and page_in_section(p.url, p.title, sections, home)
                                for p in crawl.pages):
            return CheckOutcome("not_checkable", page=out.page, quote=out.quote,
                                llm_used=out.llm_used, context=out.context,
                                reason=f"relevant section not reached (read {n} pages); no page "
                                       f"of section {' / '.join(sections)} was read: "
                                       f"{out.reason}")
    return out


def run_checks(run_id: str, crawl: CrawlResult, requirements: list[Requirement],
               llm: LLMProvider | None, progress: Callable[[str], None] | None = None,
               on_finding: Callable[[Finding], None] | None = None) -> list[Finding]:
    """Each check gets CHECK_TIMEOUT_SECONDS; all checks together CHECK_RUN_BUDGET_SECONDS.
    A check that runs out of time is not_checkable ("LLM timeout / rate limit")."""
    progress = progress or (lambda m: None)
    approved = [r for r in requirements if r.approved]
    check_timeout = float(os.getenv("CHECK_TIMEOUT_SECONDS") or 90)
    run_deadline = time.monotonic() + float(os.getenv("CHECK_RUN_BUDGET_SECONDS") or 900)
    findings = []
    for i, req in enumerate(approved, 1):
        prefix = f"check {i}/{len(approved)} {req.source_clause_id}"
        progress(f"{prefix}: {req.check_type}")
        if llm is not None:
            llm.deadline = min(time.monotonic() + check_timeout, run_deadline)
            llm.on_event = lambda m, p=prefix: progress(f"{p}: {m}")
        if time.monotonic() >= run_deadline:
            out = CheckOutcome("not_checkable",
                               reason=f"{TIMEOUT_REASON}: run time cap reached before this check")
        else:
            out = finalize(run_one(req, crawl, llm), crawl, req)
        quote_ok = out.page is not None and verify_quote(out.quote, out.page.text)
        quote = out.quote if quote_ok and not out.absence else None
        context_ok = out.page is not None and verify_quote(out.context, out.page.text)
        f = Finding(
            id=f"{run_id}:{req.id}", bank_id=crawl.bank_id, requirement_id=req.id,
            status=out.status, run_id=run_id, reason=out.reason or None,
            evidence_url=out.page.url if out.page else None,
            evidence_quote=quote,
            # Translation only after the original quote has been verified.
            evidence_quote_en=translate(quote, llm) if quote else None,
            context_quote=out.context if context_ok else None,
            decided_by="llm_assisted" if out.llm_used else "code",
            pages_read=crawl.unique_pages, urls_read=crawl.urls_read)
        findings.append(f)
        if on_finding:
            on_finding(f)
        progress(f"{prefix}: {f.status}")
    if llm is not None:
        llm.deadline, llm.on_event = None, None
    return findings
