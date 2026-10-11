"""Measure the Jina Reader fallback (RENDER_FALLBACK=jina, BROWSER_FALLBACK=0) on the
JavaScript-only / short-homepage banks and compare with the stored laptop results
(data/precomputed/findings.json, made with a local browser and the LLM).

Hosted-demo crawl settings: 15 pages, 60 s per run (CRAWLER_TIME_BUDGET_SECONDS default).
No LLM: the run uses llm=None, so the two LLM-path checks end not_checkable ("LLM not
configured"). A throwaway SQLite database is used; nothing is written to data/.

Usage: .venv/bin/python eval/jina_fallback.py  (writes eval/jina_fallback.json)
"""

import json
import os
import sys
import tempfile
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ["DB_PATH"] = str(Path(tempfile.mkdtemp()) / "jina.sqlite")
# Hosted-demo settings, set before .env is read (dotenv never overrides them).
os.environ.update(BROWSER_FALLBACK="0", RENDER_FALLBACK="jina",
                  CRAWLER_MAX_PAGES_PER_BANK="15", CRAWLER_TIME_BUDGET_SECONDS="60")

from backend import db  # noqa: E402
from backend.crawl.banks import load_banks  # noqa: E402
from backend.crawl.crawler import CrawlConfig, Crawler  # noqa: E402
from backend.pipeline import check_site, sync_requirements_yaml  # noqa: E402

BANKS = ["agrobank", "hayot_bank", "universal_bank", "asakabank"]


def main() -> None:
    db.init_db()
    sync_requirements_yaml(ROOT / "data/requirements.yaml")
    stored = {r["bank_id"]: r for r in
              json.loads((ROOT / "data/precomputed/findings.json").read_text())["runs"]}
    urls = {b.id: b.website_url for b in load_banks()}
    out = []
    for bank in BANKS:
        t = time.time()
        crawler = Crawler(CrawlConfig.from_env())
        run = check_site(urls[bank], bank_id=bank, crawler=crawler, llm=None, source="job")
        secs = time.time() - t
        with db.connect() as conn:
            fs = db.list_findings(conn, run_id=run.id)
            methods = Counter(json.loads(r["links"] or "{}").get("method", "?") for r in
                              conn.execute("SELECT links FROM pages WHERE bank_id = ?", (bank,)))
        new = {f.requirement_id: f for f in fs}
        old = {f["requirement_id"]: f for f in stored.get(bank, {}).get("findings", [])}
        diffs = [{"requirement_id": rid,
                  "stored": old[rid]["status"] if rid in old else "no data",
                  "jina": new[rid].status if rid in new else "no data",
                  "jina_reason": new[rid].reason[:220] if rid in new else "",
                  "stored_reason": (old[rid]["reason"] or "")[:220] if rid in old else ""}
                 for rid in sorted(set(new) | set(old))
                 if (old.get(rid) or {}).get("status") != getattr(new.get(rid), "status", None)]
        s = stored.get(bank, {})
        row = {"bank": bank, "url": urls[bank], "secs": round(secs, 1),
               "crawl_status": run.crawl_status, "crawl_reason": run.crawl_reason,
               "pages": run.pages_read, "page_methods": dict(methods),
               "jina": dict(Counter(f.status for f in fs)),
               "stored_pages": s.get("pages_read"),
               "stored_secs": None,
               "stored": dict(Counter(f["status"] for f in s.get("findings", []))),
               "diffs": diffs}
        if s.get("started_at") and s.get("finished_at"):
            from datetime import datetime
            row["stored_secs"] = round((datetime.fromisoformat(s["finished_at"])
                                        - datetime.fromisoformat(s["started_at"])).total_seconds(), 1)
        print(json.dumps({k: v for k, v in row.items() if k != "diffs"}), flush=True)
        out.append(row)
    (ROOT / "eval/jina_fallback.json").write_text(json.dumps(out, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
