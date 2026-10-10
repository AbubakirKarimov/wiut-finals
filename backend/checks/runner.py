"""Run all approved requirements against the pages of one crawl and build Findings.

Order per finding: check -> verify the quote verbatim against the page text -> gate
possible_gap (enough pages, no fetch errors) -> machine-translate the verified quote.
"""

import os

from backend.checks.evidence import verify_quote
from backend.checks.llm_checks import check_presence, translate
from backend.checks.types import CheckOutcome
from backend.checks.uz_version import check_uz_version
from backend.crawl.crawler import CrawlResult
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


def finalize(out: CheckOutcome, crawl: CrawlResult) -> CheckOutcome:
    """Enforce the evidence and gating rules on a raw outcome."""
    if out.status in ("ok", "possible_gap"):
        if out.page is None or not verify_quote(out.quote, out.page.text):
            return CheckOutcome("not_checkable", page=out.page, llm_used=out.llm_used,
                                reason="evidence quote not found verbatim in the page text; "
                                       f"original outcome {out.status}: {out.reason}")
    if out.status == "possible_gap":
        n, need = len(crawl.pages), min_pages_for_gap()
        if n < need:
            return CheckOutcome("not_checkable", page=out.page, quote=out.quote,
                                llm_used=out.llm_used,
                                reason=f"only {n} page(s) read (at least {need} needed to "
                                       f"report a possible gap): {out.reason}")
        if crawl.fetch_errors:
            return CheckOutcome("not_checkable", page=out.page, quote=out.quote,
                                llm_used=out.llm_used,
                                reason=f"site had {len(crawl.fetch_errors)} fetch error(s), "
                                       f"e.g. {crawl.fetch_errors[0]}: {out.reason}")
    return out


def run_checks(run_id: str, crawl: CrawlResult, requirements: list[Requirement],
               llm: LLMProvider | None) -> list[Finding]:
    findings = []
    for req in requirements:
        if not req.approved:
            continue
        out = finalize(run_one(req, crawl, llm), crawl)
        quote_ok = out.page is not None and verify_quote(out.quote, out.page.text)
        quote = out.quote if quote_ok else None
        findings.append(Finding(
            id=f"{run_id}:{req.id}", bank_id=crawl.bank_id, requirement_id=req.id,
            status=out.status, run_id=run_id, reason=out.reason or None,
            evidence_url=out.page.url if out.page else None,
            evidence_quote=quote,
            # Translation only after the original quote has been verified.
            evidence_quote_en=translate(quote, llm) if quote else None,
            pages_read=len(crawl.pages), urls_read=crawl.urls_read))
    return findings
