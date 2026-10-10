"""Re-run ONE requirement for a bank on the pages of its latest batch run (no full crawl).

    .venv/bin/python scripts/recheck.py <requirement_id> <bank_id> [<bank_id> ...]

Pages of that run are taken from the page store. An HTML page stored without link metadata
(rows written before links were kept) is fetched again first, politely (robots.txt, 1
request/second, project User-Agent), and stored with its links. The finding of that run is
replaced and its reason starts with "re-checked <date>". Then re-export findings.json with
python -m backend.precomputed export.
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend import db  # noqa: E402
from backend.checks.runner import run_checks  # noqa: E402
from backend.crawl.crawler import CrawlConfig, CrawlResult, Crawler  # noqa: E402
from backend.crawl.store import DbPageStore  # noqa: E402
from backend.models import Page, utcnow  # noqa: E402
from backend.pipeline import llm_from_env  # noqa: E402


def pages_of_run(conn, bank_id: str, urls: list[str]) -> list[tuple[Page, dict]]:
    out = []
    for u in urls:
        r = conn.execute("SELECT * FROM pages WHERE bank_id = ? AND url = ?", (bank_id, u)).fetchone()
        if r is None:
            continue
        d = dict(r)
        meta = json.loads(d.pop("links") or "{}")
        d.pop("request_url", None)
        out.append((Page(**{**d, "readable": bool(d["readable"])},
                         links=[tuple(x) for x in meta.get("links") or []]), meta))
    return out


def main(req_id: str, banks: list[str]) -> int:
    db.init_db()
    crawler = Crawler(CrawlConfig.from_env(), store=DbPageStore())
    llm = llm_from_env()
    with db.connect() as conn:
        req = next((r for r in db.list_requirements(conn, approved_only=True) if r.id == req_id), None)
    if req is None:
        print(f"unknown or unapproved requirement {req_id}", file=sys.stderr)
        return 2
    for bank in banks:
        with db.connect() as conn:
            run = next((r for r in db.list_runs(conn) if r.bank_id == bank and r.source == "batch"
                        and r.status == "done"), None)
            if run is None:
                print(f"{bank}: no batch run", file=sys.stderr)
                continue
            old = db.get_finding(conn, f"{run.id}:{req_id}")
            stored = pages_of_run(conn, bank, old.urls_read if old else [])
        pages, refetched = [], []
        for page, meta in stored:
            if page.source_type == "html" and "links" not in meta:
                r = crawler.fetcher.get(page.url)
                res = CrawlResult(bank_id=bank, start_url=page.url)
                new, _ = crawler._store(res, r, run.id) if r.status == 200 and not r.error \
                    else (None, None)
                if new is not None:
                    page = new
                    refetched.append(page.url)
            pages.append(page)
        crawl = CrawlResult(bank_id=bank, start_url=run.start_url, pages=pages,
                            has_language_switcher=run.has_language_switcher)
        [f] = run_checks(run.id, crawl, [req], llm)
        f.reason = f"re-checked {utcnow():%Y-%m-%d} ({len(refetched)} page(s) re-fetched for " \
                   f"missing link data): {f.reason}"
        with db.connect() as conn:
            db.upsert_finding(conn, f)
        print(f"{bank}: {old.status if old else 'none'} -> {f.status} | {f.evidence_url} | "
              f"{f.reason[:220]}")
    crawler.close()
    return 0


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(__doc__, file=sys.stderr)
        sys.exit(2)
    sys.exit(main(sys.argv[1], sys.argv[2:]))
