"""Compare the primary and fallback LLM on the same clauses (for the deck).

    python -m backend.requirements.compare [--n 10] [--seed 3030]

Runs every configured provider (LLM_*, LLM_FALLBACK_n_*) separately on the same clauses and
writes eval/model_comparison.md + .json: valid-JSON rate, check_type agreement, latency,
tokens, and examples of disagreement. It never changes which model is primary.
"""

import argparse
import json
import random
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path

from backend import db
from backend.llm.provider import (FallbackProvider, LLMConfigError, LLMError, LLMProvider,
                                  LLMResponseError, LLMTransientError, provider_from_env)
from backend.requirements.shortlist import (ALWAYS_INCLUDE, ROOT, ClauseAssessment,
                                            build_prompt, load_clauses, prefilter)

OUT_MD = ROOT / "eval" / "model_comparison.md"
OUT_JSON = ROOT / "eval" / "model_comparison.json"


def pick_clauses(n: int, seed: int) -> list[dict]:
    passed = prefilter(load_clauses())
    fixed = [c for c in passed if c["clause_id"] in ALWAYS_INCLUDE][:n]
    rest = [c for c in passed if c["clause_id"] not in ALWAYS_INCLUDE]
    return fixed + random.Random(seed).sample(rest, max(0, min(n - len(fixed), len(rest))))


def _original_call(p: LLMProvider, clause: dict, db_path=None) -> dict | None:
    """The first successful non-cached call for this prompt (also when now served from cache)."""
    key = db.llm_cache_key(p.name, p.model, build_prompt(clause),
                           ClauseAssessment.model_json_schema())
    with db.connect(db_path) as conn:
        row = conn.execute(
            "SELECT input_tokens, output_tokens, duration_ms FROM llm_calls WHERE cache_key = ? "
            "AND provider = ? AND model = ? AND ok = 1 AND cache_hit = 0 ORDER BY id LIMIT 1",
            (key, p.name, p.model)).fetchone()
    return dict(row) if row else None


def run_provider(p: LLMProvider, clauses: list[dict], db_path=None) -> list[dict]:
    out = []
    for c in clauses:
        result, error = None, None
        try:
            result = p.complete_json(build_prompt(c), ClauseAssessment)
        except LLMResponseError as exc:
            error = f"invalid JSON: {exc}"
        except LLMTransientError as exc:
            error = f"transient: {exc}"
        out.append({"clause_id": c["clause_id"], "result": result, "error": error,
                    "call": _original_call(p, c, db_path) if result else None})
    return out


def summarize(p: LLMProvider, rows: list[dict]) -> dict:
    calls = [r["call"] for r in rows if r["call"]]
    lat = [c["duration_ms"] for c in calls]
    tin = [c["input_tokens"] for c in calls if c["input_tokens"] is not None]
    tout = [c["output_tokens"] for c in calls if c["output_tokens"] is not None]
    return {"provider": p.name, "model": p.model, "clauses": len(rows),
            "valid_json": sum(1 for r in rows if r["result"]),
            "invalid_json": sum(1 for r in rows if r["error"] and r["error"].startswith("invalid")),
            "transient_failures": sum(1 for r in rows if r["error"]
                                      and r["error"].startswith("transient")),
            "latency_ms_mean": round(statistics.mean(lat)) if lat else "no data",
            "latency_ms_median": round(statistics.median(lat)) if lat else "no data",
            "input_tokens_total": sum(tin) if tin else "no data",
            "output_tokens_total": sum(tout) if tout else "no data"}


def compare(providers: list[LLMProvider], clauses: list[dict], db_path=None) -> dict:
    runs = {p.name + " / " + p.model: run_provider(p, clauses, db_path) for p in providers}
    summary = [summarize(p, rows) for p, rows in zip(providers, runs.values())]
    report = {"generated_at": datetime.now(timezone.utc).isoformat(),
              "clauses": [c["clause_id"] for c in clauses], "providers": summary,
              "runs": runs, "agreement": None, "disagreements": []}
    if len(providers) >= 2:
        a, b = list(runs.values())[:2]
        both = [(x, y) for x, y in zip(a, b) if x["result"] and y["result"]]
        same = [x for x, y in both if x["result"]["check_type"] == y["result"]["check_type"]]
        report["agreement"] = {"both_valid": len(both), "same_check_type": len(same)}
        text = {c["clause_id"]: c["text_original"] for c in clauses}
        report["disagreements"] = [
            {"clause_id": x["clause_id"], "text_original": text[x["clause_id"]],
             "primary": x["result"], "fallback": y["result"]}
            for x, y in both if x["result"]["check_type"] != y["result"]["check_type"]]
    return report


def write_report(report: dict, md_path: Path = OUT_MD, json_path: Path = OUT_JSON) -> None:
    md_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=1) + "\n",
                         encoding="utf-8")
    cols = ["provider", "model", "clauses", "valid_json", "invalid_json", "transient_failures",
            "latency_ms_mean", "latency_ms_median", "input_tokens_total", "output_tokens_total"]
    out = ["# LLM model comparison", "",
           f"Generated {report['generated_at']} by `python -m backend.requirements.compare` on "
           f"{len(report['clauses'])} clauses: {', '.join(report['clauses'])}.",
           "Latency and tokens come from each prompt's original (non-cached) API call.", "",
           "| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    out += ["| " + " | ".join(str(s[c]) for c in cols) + " |" for s in report["providers"]]
    if report["agreement"] is None:
        out += ["", "Only one provider is configured (no LLM_FALLBACK_1_*): no agreement data."]
    else:
        ag = report["agreement"]
        out += ["", f"check_type agreement: {ag['same_check_type']} of {ag['both_valid']} "
                    "clauses where both models returned valid JSON.", "",
                "## Disagreements (up to 3)", ""]
        for d in report["disagreements"][:3]:
            out += [f"### {d['clause_id']}",
                    f"- primary: {d['primary']['check_type']} — {d['primary']['requirement_en']}",
                    f"- fallback: {d['fallback']['check_type']} — {d['fallback']['requirement_en']}",
                    "", "> " + d["text_original"].replace("\n", "\n> "), ""]
        if not report["disagreements"]:
            out.append("none")
    md_path.write_text("\n".join(out) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Compare primary and fallback LLM.")
    ap.add_argument("--n", type=int, default=10)
    ap.add_argument("--seed", type=int, default=3030)
    args = ap.parse_args(argv)
    db.init_db()
    try:
        p = provider_from_env()
    except LLMConfigError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    providers = p.providers if isinstance(p, FallbackProvider) else [p]
    try:
        report = compare(providers, pick_clauses(args.n, args.seed))
    except LLMError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    write_report(report)
    for s in report["providers"]:
        print(s)
    print("agreement:", report["agreement"] or "only one provider configured")
    print(f"wrote {OUT_MD.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
