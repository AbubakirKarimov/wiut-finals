"""Crawl and check every bank with a website_url in data/banks.yaml (stored as batch runs).

    .venv/bin/python scripts/crawl_all.py [bank_id ...]

Results are stored in SQLite and shown in the UI as "pre-computed on <finish time>".
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend import db  # noqa: E402
from backend.crawl.banks import crawlable_banks  # noqa: E402
from backend.pipeline import check_site, sync_requirements_yaml  # noqa: E402


def main(only: list[str]) -> int:
    db.init_db()
    sync_requirements_yaml()
    banks = [b for b in crawlable_banks() if not only or b.id in only]
    if not banks:
        print("no banks with a website_url match", file=sys.stderr)
        return 2
    for b in banks:
        print(f"{b.id}: {b.website_url}", file=sys.stderr)
        try:
            run = check_site(b.website_url, bank_id=b.id, source="batch",
                             progress=lambda m: print(f"  {m}", file=sys.stderr))
        except Exception as e:  # keep going with the next bank; the run row has the error
            print(f"  error: {type(e).__name__}: {e}", file=sys.stderr)
            continue
        with db.connect() as conn:
            findings = db.list_findings(conn, run_id=run.id)
        counts = {s: sum(f.status == s for f in findings)
                  for s in ("ok", "possible_gap", "not_checkable")}
        print(f"  crawl={run.crawl_status} pages={run.pages_read} "
              f"errors={len(run.fetch_errors)} findings={counts}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
