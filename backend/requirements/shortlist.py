"""Shortlist requirement candidates from parsed regulations for human approval.

Steps:
1. Deterministic keyword pre-filter over all non-repealed, non-form clauses.
2. LLM classification (English prompt): is the clause checkable from the bank's public
   website alone; if yes, proposed check_type, one-sentence English requirement (machine
   translation) and an evidence hint.
3. Write data/requirements_review.md and data/requirements_candidates.json. Every candidate
   has approved=false; approval is done by a human with `python -m backend.requirements.approve`.

CLI:
    python -m backend.requirements.shortlist               # pre-filter + LLM
    python -m backend.requirements.shortlist --prefilter-only
"""

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from backend import db
from backend.llm.provider import (LLMConfigError, LLMError, LLMProvider,
                                  LLMResponseError, cost_of, provider_from_env)

ROOT = Path(__file__).resolve().parents[2]
REGULATIONS_DIR = ROOT / "data" / "regulations"
CANDIDATES_PATH = ROOT / "data" / "requirements_candidates.json"
REVIEW_PATH = ROOT / "data" / "requirements_review.md"
MT_LABEL = "machine translation"

# Keyword stems per topic: (Uzbek Cyrillic, Uzbek Latin). Matched as lowercase substrings
# after apostrophe normalization; Cyrillic against text_original, Latin against the parallel
# Latin text.
KEYWORDS: dict[str, tuple[list[str], list[str]]] = {
    "website": (["веб-сайт", "вебсайт", "сайт", "интернет", "мобил илова", "мобиль илова"],
                ["veb-sayt", "vebsayt", "sayt", "internet", "mobil ilova"]),
    "state_language": (["давлат тил", "ўзбек тил"], ["davlat til", "o'zbek til"]),
    "disclosure": (["ошкор", "ахборот бер", "маълумот бер", "жойлаштир"],
                   ["oshkor", "axborot ber", "ma'lumot ber", "joylashtir"]),
    "publication": (["эълон", "чоп эт", "нашр"], ["e'lon", "chop et", "nashr"]),
    "collateral": (["гаров"], ["garov"]),
    "credit_cost": (["тўлиқ қиймат", "калькулятор", "ҳисоблаб чиқ"],
                    ["to'liq qiymat", "kalkulyator", "hisoblab chiq"]),
    "complaints": (["мурожаат", "шикоят"], ["murojaat", "shikoyat"]),
    "tariffs_fees": (["тариф", "комиссия", "фоиз ставка", "ҳақ ундир"],
                     ["tarif", "komissiya", "foiz stavka", "haq undir"]),
    "terms_offer": (["реклама", "оферта", "асосий шарт"], ["reklama", "oferta", "asosiy shart"]),
}

# A clause passes the pre-filter only with a core topic; "complaints" and "terms_offer" are
# recorded but count only together with a core topic.
CORE_TOPICS = {"website", "state_language", "disclosure", "publication", "collateral",
               "credit_cost", "tariffs_fees"}
SECONDARY_TOPICS = set(KEYWORDS) - CORE_TOPICS

# Always reviewed, whatever the pre-filter or the LLM says.
ALWAYS_INCLUDE = [
    "cbu_reg_3030:main:13", "cbu_reg_3030:main:14", "cbu_reg_3030:main:17",
    "cbu_reg_3030:main:18^1",
    # State Language Law: texts of signs, announcements, price lists and other visual and
    # oral information are in the state language.
    "law_state_language:art:20",
]

CHECK_TYPES = {
    "uz_version": "the bank's key public pages (loans, deposits, tariffs, terms) must exist in "
                  "Uzbek (state language); checked from page languages and language links",
    "required_document": "a specific document or section must be published on the website",
    "key_info": "specific information must be stated on a relevant public page",
}

PROMPT_TEMPLATE = """You review one clause of an Uzbek legal act for a Central Bank \
consumer-protection monitoring tool. The tool can ONLY read the bank's public website \
(HTML pages and PDF files reachable without login). It cannot see branches, contracts \
signed with clients, internal procedures, personal cabinets behind login, or mobile apps.

Decide whether compliance with this clause can be checked from the bank's PUBLIC website alone.
If yes, pick one check_type:
{check_types}

Rules:
- requirement_en: ONE English sentence stating what the bank must do, faithful to the clause \
(it is a machine translation; do not add obligations that are not in the text).
- evidence_hint: if checkable, what exact evidence a human should look for on the website \
(page, section, document or statement). Otherwise null.
- not_checkable_reason: if not checkable, one sentence why. Otherwise null.
- confidence: your confidence in the checkable decision, from 0 to 1.

Source: {source_id}
Clause id: {clause_id}
Context: {context}
Clause text (Uzbek, Cyrillic, verbatim):
\"\"\"
{text}
\"\"\"
"""


class ClauseAssessment(BaseModel):
    checkable_from_public_website: bool
    check_type: Literal["uz_version", "required_document", "key_info"] | None = None
    requirement_en: str = Field(min_length=10)
    evidence_hint: str | None = None
    not_checkable_reason: str | None = None
    confidence: float = Field(ge=0.0, le=1.0)

    @model_validator(mode="after")
    def _consistent(self):
        if self.checkable_from_public_website:
            if not self.check_type or not self.evidence_hint:
                raise ValueError("checkable clauses need check_type and evidence_hint")
        elif not self.not_checkable_reason:
            raise ValueError("non-checkable clauses need not_checkable_reason")
        return self


def normalize(text: str) -> str:
    return re.sub(r"[ʻʼ’‘`']", "'", text.lower())


def load_clauses(regulations_dir: Path = REGULATIONS_DIR) -> list[dict]:
    """All non-repealed, non-form clauses of every parsed source."""
    out = []
    for path in sorted(regulations_dir.glob("*.json")):
        doc = json.loads(path.read_text(encoding="utf-8"))
        for c in doc["clauses"]:
            if c["kind"] == "text" and not c["repealed"]:
                out.append({**c, "source_id": doc["source_id"]})
    return out


def keyword_hits(clause: dict) -> dict[str, list[str]]:
    cyr = normalize(clause["text_original"])
    lat = normalize(clause.get("text_parallel_latn") or "")
    hits: dict[str, list[str]] = {}
    for topic, (cyr_words, lat_words) in KEYWORDS.items():
        found = [w for w in cyr_words if w in cyr] + [w for w in lat_words if w in lat]
        if found:
            hits[topic] = found
    return hits


def passes_topics(topics) -> bool:
    """Secondary topics only count together with a core topic."""
    return any(t in CORE_TOPICS for t in topics)


def prefilter(clauses: list[dict]) -> list[dict]:
    """Clauses matching a core topic, plus ALWAYS_INCLUDE; adds `prefilter` info."""
    selected = []
    for c in clauses:
        hits = keyword_hits(c)
        forced = c["clause_id"] in ALWAYS_INCLUDE
        if passes_topics(hits) or forced:
            selected.append({**c, "prefilter": {"topics": sorted(hits), "keywords": hits,
                                                "always_include": forced}})
    return selected


def build_prompt(clause: dict) -> str:
    context = " / ".join(x for x in (clause.get("chapter"), clause.get("paragraph"),
                                     f"annex {clause['annex']}" if clause.get("annex") else None)
                         if x) or "none"
    types = "\n".join(f"- {k}: {v}" for k, v in CHECK_TYPES.items())
    return PROMPT_TEMPLATE.format(check_types=types, source_id=clause["source_id"],
                                  clause_id=clause["clause_id"], context=context,
                                  text=clause["text_original"])


def _candidate(c: dict, result: dict | None, error: str | None) -> dict:
    checkable = bool(result and result["checkable_from_public_website"])
    return {
        "clause_id": c["clause_id"],
        "source_id": c["source_id"],
        "url": c["url"],
        "chapter": c.get("chapter"),
        "paragraph": c.get("paragraph"),
        "text_original": c["text_original"],
        "text_en": result["requirement_en"] if result else None,
        "text_en_label": MT_LABEL,
        "checkable": checkable,
        "check_type": result["check_type"] if result else None,
        "evidence_hint": result["evidence_hint"] if result else None,
        "not_checkable_reason": result["not_checkable_reason"] if result else None,
        "llm_confidence": result["confidence"] if result else None,
        "llm_error": error,
        "prefilter": c["prefilter"],
        "shortlisted": checkable or c["prefilter"]["always_include"],
        "approved": False,
    }


def assess(clauses: list[dict], provider: LLMProvider, on_result=None) -> list[dict]:
    """Classify each clause. Invalid JSON (after the provider's retry) is recorded per clause;
    transient/config errors abort the run (finished clauses stay in the cache)."""
    candidates = []
    for c in clauses:
        try:
            result, error = provider.complete_json(build_prompt(c), ClauseAssessment), None
        except LLMResponseError as exc:
            result, error = None, str(exc)
        cand = _candidate(c, result, error)
        candidates.append(cand)
        if on_result:
            on_result(c, cand, provider)
    return candidates


def problems_of(cand: dict) -> list[str]:
    out = []
    if cand["llm_error"]:
        out.append(f"LLM error: {cand['llm_error']}")
    if cand["text_en"] is not None and not cand["text_en"].strip():
        out.append("empty text_en")
    if cand["checkable"] and cand["check_type"] not in CHECK_TYPES:
        out.append(f"bad check_type {cand['check_type']!r}")
    return out


def _max_call_id() -> int:
    with db.connect() as conn:
        return conn.execute("SELECT COALESCE(MAX(id), 0) FROM llm_calls").fetchone()[0]


def _rows_since(last_id: int) -> list[dict]:
    with db.connect() as conn:
        return [dict(r) for r in conn.execute(
            "SELECT provider, model, ok, cache_hit, input_tokens, output_tokens, duration_ms, "
            "error FROM llm_calls WHERE id > ? ORDER BY id", (last_id,))]


def dry_run(clauses: list[dict], provider: LLMProvider) -> list[str]:
    """Run a few clauses and print raw replies and per-call numbers. Writes no output files."""
    all_problems = []
    for c in clauses:
        last = _max_call_id()
        cand = assess([c], provider)[0]
        raw = provider.last_raw.text if provider.last_raw else "(served from cache)"
        print(f"=== {c['clause_id']}  ({c['url']})")
        print(f"raw LLM output: {raw}")
        for r in _rows_since(last):
            print(f"  call: {r['provider']} ok={r['ok']} cache_hit={r['cache_hit']} "
                  f"in={r['input_tokens']} out={r['output_tokens']} "
                  f"latency_ms={r['duration_ms']:.0f}" + (f" error={r['error']}" if r['error']
                                                          else ""))
        probs = problems_of(cand)
        print(f"  problems: {probs or 'none'}\n")
        all_problems += [f"{c['clause_id']}: {p}" for p in probs]
    return all_problems


def _conf(c: dict) -> str:
    return "no data" if c["llm_confidence"] is None else f"{c['llm_confidence']:.2f}"


def _md_block(c: dict) -> str:
    lines = [f"### {c['clause_id']}",
             f"- lex.uz: {c['url']}",
             f"- Proposed check_type: {c['check_type'] or 'none (not checkable)'}",
             f"- Checkable from public website (LLM): {'yes' if c['checkable'] else 'no'}",
             f"- LLM confidence (self-reported): {_conf(c)}",
             f"- Pre-filter topics: {', '.join(c['prefilter']['topics']) or 'none'}"
             + (" (always included)" if c["prefilter"]["always_include"] else ""),
             f"- Requirement (English, {MT_LABEL}): {c['text_en'] or 'no data'}"]
    if c["evidence_hint"]:
        lines.append(f"- Evidence to look for: {c['evidence_hint']}")
    if c["not_checkable_reason"]:
        lines.append(f"- Not checkable because: {c['not_checkable_reason']}")
    if c["llm_error"]:
        lines.append(f"- LLM error: {c['llm_error']}")
    lines += ["", "Original text (Uzbek Cyrillic):", "", "> " + c["text_original"].replace(
        "\n", "\n> "), ""]
    return "\n".join(lines)


def rank_key(c: dict):
    """Most promising first: checkable, higher self-reported confidence, then clause id."""
    return (not c["checkable"], -(c["llm_confidence"] or 0.0), c["clause_id"])


def write_outputs(candidates: list[dict], stats: dict, model_info: str, *,
                  candidates_path: Path = CANDIDATES_PATH,
                  review_path: Path = REVIEW_PATH) -> None:
    generated = datetime.now(timezone.utc).isoformat()
    candidates_path.write_text(json.dumps(
        {"generated_at": generated, "llm": model_info, "stats": stats,
         "candidates": candidates}, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    short = sorted((c for c in candidates if c["shortlisted"]), key=rank_key)
    rest = sorted((c for c in candidates if not c["shortlisted"]), key=lambda c: c["clause_id"])
    out = ["# Requirement candidates for review",
           "",
           f"Generated {generated} by `python -m backend.requirements.shortlist` ({model_info}).",
           "All candidates have approved=false. Approve after reading with:",
           "`python -m backend.requirements.approve <clause_id> ...`",
           "",
           "| Step | Count |", "|---|---|"]
    out += [f"| {k} | {v} |" for k, v in stats.items()]
    out += ["", f"## Shortlist ({len(short)})", ""] + [_md_block(c) for c in short]
    out += [f"## Pre-filtered but judged not checkable ({len(rest)})", "",
            "| clause_id | reason (LLM) | confidence |", "|---|---|---|"]
    out += [f"| {c['clause_id']} | {c['not_checkable_reason'] or c['llm_error']} | {_conf(c)} |"
            for c in rest]
    review_path.write_text("\n".join(out) + "\n", encoding="utf-8")


def run_stats(rows: list[dict]) -> dict:
    api = [r for r in rows if not r["cache_hit"]]
    tokens_in = [r["input_tokens"] for r in api if r["input_tokens"] is not None]
    tokens_out = [r["output_tokens"] for r in api if r["output_tokens"] is not None]
    return {"llm_api_calls": len(api), "llm_failed_calls": sum(1 for r in api if not r["ok"]),
            "llm_cache_hits": sum(1 for r in rows if r["cache_hit"]),
            "input_tokens": sum(tokens_in) if tokens_in else "no data",
            "output_tokens": sum(tokens_out) if tokens_out else "no data",
            "api_time_s": round(sum(r["duration_ms"] for r in api) / 1000, 1),
            "cost_usd": cost_of(rows)}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--prefilter-only", action="store_true",
                    help="run the deterministic pre-filter only; no LLM, no output files")
    ap.add_argument("--only", nargs="+", metavar="CLAUSE_ID",
                    help="restrict the LLM step to these clauses (pre-filter not required)")
    ap.add_argument("--dry-run", action="store_true",
                    help="print raw LLM outputs and per-call numbers; write no output files")
    args = ap.parse_args(argv)

    clauses = load_clauses()
    passed = prefilter(clauses)
    by_topic = {t: sum(1 for c in passed if t in c["prefilter"]["topics"]) for t in KEYWORDS}
    forced_only = [c["clause_id"] for c in passed
                   if c["prefilter"]["always_include"] and not passes_topics(
                       c["prefilter"]["topics"])]
    missing = sorted(set(ALWAYS_INCLUDE) - {c["clause_id"] for c in clauses})
    print(f"eligible clauses (non-repealed, non-form): {len(clauses)}")
    print(f"pass keyword pre-filter: {len(passed) - len(forced_only)}"
          f" (+{len(forced_only)} always-include without a core topic: {forced_only})")
    print("hits per topic among passing clauses: "
          + ", ".join(f"{k}={v}" for k, v in by_topic.items()))
    if missing:
        print(f"error: always-include clauses not found: {missing}", file=sys.stderr)
        return 2
    if args.prefilter_only:
        return 0

    selected = passed
    if args.only:
        by_id = {c["clause_id"]: c for c in clauses}
        unknown = [cid for cid in args.only if cid not in by_id]
        if unknown:
            print(f"error: unknown or ineligible clause ids: {unknown}", file=sys.stderr)
            return 2
        info = {c["clause_id"]: c for c in prefilter(clauses)}
        selected = [info.get(cid) or {**by_id[cid], "prefilter": {
            "topics": sorted(keyword_hits(by_id[cid])), "keywords": keyword_hits(by_id[cid]),
            "always_include": False}} for cid in args.only]

    db.init_db()
    try:
        provider = provider_from_env()
    except LLMConfigError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    last_id = _max_call_id()
    if args.dry_run:
        try:
            problems = dry_run(selected, provider)
        except LLMError as exc:
            print(f"error: LLM step failed: {exc}", file=sys.stderr)
            return 1
        for k, v in run_stats(_rows_since(last_id)).items():
            print(f"run: {k}: {v}")
        print("problems: " + ("; ".join(problems) if problems else "none"))
        return 1 if problems else 0

    progress = lambda c, cand, p: print(  # noqa: E731
        f"  {c['clause_id']}: {'checkable ' + cand['check_type'] if cand['checkable'] else 'not checkable'}"
        + (f" (error: {cand['llm_error']})" if cand["llm_error"] else ""), flush=True)
    try:
        candidates = assess(selected, provider, on_result=progress)
    except LLMError as exc:
        print(f"error: LLM step failed: {exc}. Finished clauses are cached; re-run to resume.",
              file=sys.stderr)
        return 1
    stats = {"eligible clauses": len(clauses), "passed pre-filter": len(passed),
             "sent to LLM": len(selected),
             "LLM errors (invalid JSON after retry)": sum(1 for c in candidates if c["llm_error"]),
             "judged checkable by LLM": sum(c["checkable"] for c in candidates),
             "shortlisted (checkable + always-include)": sum(c["shortlisted"]
                                                             for c in candidates)}
    stats.update({f"run: {k}": v for k, v in run_stats(_rows_since(last_id)).items()})
    write_outputs(candidates, stats, f"{provider.name}, model {provider.model}")
    for k, v in stats.items():
        print(f"{k}: {v}")
    print(f"wrote {REVIEW_PATH.relative_to(ROOT)} and {CANDIDATES_PATH.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
