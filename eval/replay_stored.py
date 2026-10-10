"""Replay the current checks on the pages stored for each bank's latest batch run.

No network and no LLM API calls: LLM-path requirements are run with a provider that only
answers from the llm_cache and otherwise raises (the finding is then not_checkable, with
decided_by = llm_assisted because the LLM would have been asked). Nothing is written to the
database or to data/precomputed/. Prints a table and writes eval/replay_stored.json.

Caveat (audit B4): the page store keeps one row per URL, so a page's text may come from a
later re-fetch than the batch run itself.

Usage: .venv/bin/python eval/replay_stored.py
"""

import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend import db  # noqa: E402
from backend.checks.runner import finalize, run_one  # noqa: E402
from backend.crawl.crawler import CrawlResult  # noqa: E402
from backend.llm.provider import LLMProvider, LLMTransientError, RateLimits  # noqa: E402
from backend.models import Page  # noqa: E402


class CacheOnlyLLM(LLMProvider):
    """Answers only from llm_cache (same keys as the configured provider); never calls an API."""

    def __init__(self, inner):
        super().__init__(inner.db_path, RateLimits(min_interval_seconds=0))
        self.name, self.model = inner.name, inner.model
        self.calls = 0

    def _complete(self, prompt, schema):
        self.calls += 1
        raise LLMTransientError("replay: not in llm_cache (no API call made)")


def stored_pages(conn, bank_id: str, urls: list[str]) -> list[Page]:
    out = []
    for u in urls:
        r = conn.execute("SELECT * FROM pages WHERE bank_id = ? AND url = ?", (bank_id, u)).fetchone()
        if r is None:
            continue
        d = dict(r)
        meta = json.loads(d.pop("links") or "{}")
        d.pop("request_url", None)
        out.append(Page(**{**d, "readable": bool(d["readable"])},
                        links=[tuple(x) for x in meta.get("links") or []]))
    return out


def main() -> int:
    from backend.pipeline import llm_from_env
    inner = llm_from_env()
    llm = CacheOnlyLLM(inner) if inner else None
    rows, counts = [], Counter()
    with db.connect() as conn:
        reqs = {r.id: r for r in db.list_requirements(conn, approved_only=True)}
        runs = conn.execute(
            "SELECT * FROM runs r1 WHERE source = 'batch' AND status = 'done' AND finished_at = "
            "(SELECT MAX(finished_at) FROM runs r2 WHERE r2.bank_id = r1.bank_id AND "
            "r2.source = 'batch' AND r2.status = 'done') ORDER BY bank_id").fetchall()
        for run in runs:
            f0 = conn.execute("SELECT urls_read FROM findings WHERE run_id = ? LIMIT 1",
                              (run["id"],)).fetchone()
            urls = json.loads(f0["urls_read"]) if f0 else []
            pages = stored_pages(conn, run["bank_id"], urls)
            crawl = CrawlResult(bank_id=run["bank_id"], start_url=run["start_url"],
                                status=run["crawl_status"] or "ok", pages=pages,
                                reason=run["crawl_reason"] or "",
                                fetch_errors=json.loads(run["fetch_errors"] or "[]"),
                                has_language_switcher=bool(run["has_language_switcher"]))
            for rid, req in sorted(reqs.items()):
                old = conn.execute("SELECT status FROM findings WHERE run_id = ? AND "
                                   "requirement_id = ?", (run["id"], rid)).fetchone()
                out = finalize(run_one(req, crawl, llm), crawl, req)
                by = "llm_assisted" if out.llm_used else "code"
                counts[by] += 1
                rows.append({"bank_id": run["bank_id"], "requirement_id": rid,
                             "old_status": old["status"] if old else None,
                             "new_status": out.status, "decided_by": by,
                             "evidence_url": out.page.url if out.page else None,
                             "quote": out.quote, "reason": out.reason[:300],
                             "pages_found": len(pages), "pages_listed": len(urls)})
    n = sum(counts.values())
    by_status = Counter(r["new_status"] for r in rows)
    summary = {"findings": n, "decided_by": dict(counts), "by_status": dict(by_status),
               "banks": len({r["bank_id"] for r in rows}),
               "share_code": round(counts["code"] / n, 3) if n else None,
               "llm_api_calls_attempted": llm.calls if llm else 0,
               "note": "LLM-path checks not in llm_cache become not_checkable in this replay"}
    from datetime import datetime, timezone
    generated = datetime.now(timezone.utc).isoformat(timespec="seconds")
    (ROOT / "eval" / "replay_stored.json").write_text(
        json.dumps({"generated_at": generated, "summary": summary, "rows": rows},
                   ensure_ascii=False, indent=1) + "\n",
        encoding="utf-8")
    for r in rows:
        print(f"{r['bank_id']:<16} {r['requirement_id'].split(':', 2)[2]:<12} "
              f"{str(r['old_status']):<14} -> {r['new_status']:<14} {r['decided_by']:<13} "
              f"{r['reason'][:110]}")
    print(json.dumps(summary))
    return 0


if __name__ == "__main__":
    sys.exit(main())
