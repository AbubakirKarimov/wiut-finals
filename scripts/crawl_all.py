"""Crawl and check every bank with a website_url in data/banks.yaml (stored as batch runs).

    .venv/bin/python scripts/crawl_all.py [bank_id ...]
    .venv/bin/python scripts/crawl_all.py --summary    # table of the latest stored runs only

Respects robots.txt, 1 request/second per host and the LLM pacing settings in .env; prints
progress for every page and check. Banks whose site cannot be read (blocked, unreachable,
js_shell_failed, ...) are recorded with the reason and their checks are not_checkable.
At the end a summary table is printed and written to data/precomputed/batch_summary.md.
Results are stored in SQLite and shown in the UI as "pre-computed on <finish time>".
"""

import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend import db  # noqa: E402
from backend.batch import markdown_table, summarize, text_table  # noqa: E402
from backend.crawl.banks import crawlable_banks, load_banks  # noqa: E402
from backend.pipeline import check_site, llm_from_env, sync_requirements_yaml  # noqa: E402

SUMMARY_PATH = ROOT / "data" / "precomputed" / "batch_summary.md"


def latest_batch_runs() -> list[str]:
    with db.connect() as conn:
        latest: dict[str, str] = {}
        for r in db.list_runs(conn):  # newest first
            if r.source == "batch" and r.status == "done":
                latest.setdefault(r.bank_id, r.id)
    order = [b.id for b in load_banks()]
    return [latest[b] for b in order if b in latest]


def main(only: list[str]) -> int:
    db.init_db()
    sync_requirements_yaml()
    without_url = [b.id for b in load_banks() if not b.website_url]
    if only == ["--summary"]:  # rebuild the table from the latest stored batch runs
        report(latest_batch_runs(), without_url)
        return 0
    banks = [b for b in crawlable_banks() if not only or b.id in only]
    not_selected = [b.id for b in crawlable_banks() if b not in banks]
    if not banks:
        print("no banks with a website_url match", file=sys.stderr)
        return 2
    run_ids = []
    for i, b in enumerate(banks, 1):
        print(f"[{i}/{len(banks)}] {b.id}: {b.website_url}", file=sys.stderr)
        try:
            run = check_site(b.website_url, bank_id=b.id, source="batch",
                             progress=lambda m: print(f"  {m}", file=sys.stderr),
                             on_run=run_ids.append)
        except Exception as e:  # keep going with the next bank; the run row has the error
            print(f"  error: {type(e).__name__}: {e}", file=sys.stderr)
            continue
        print(f"  done: crawl={run.crawl_status} pages={run.pages_read}", file=sys.stderr)
    report(run_ids, without_url, not_selected)
    return 0


def report(run_ids: list[str], without_url: list[str], not_selected: list[str] = ()) -> None:
    with db.connect() as conn:
        rows = summarize(conn, run_ids)
    llm = llm_from_env()
    model = f"{llm.name} / {llm.model}" if llm else "LLM not configured"
    print("\n" + text_table(rows))
    print(f"\nmodel: {model}; cost from token logs x LLM_PRICE_* in .env "
          f"(\"not set\" when no price is configured)")
    if without_url:
        print(f"not run (no website_url in data/banks.yaml): {', '.join(without_url)}")
    SUMMARY_PATH.parent.mkdir(parents=True, exist_ok=True)
    SUMMARY_PATH.write_text(
        f"# Batch run summary\n\n- Finished: "
        f"{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}\n- Model: {model}\n"
        f"- Cost: token logs x LLM_PRICE_* from .env\n"
        f"- Not run (no website_url): {', '.join(without_url) or 'none'}\n"
        f"- Not selected for this run (have a website_url): {', '.join(not_selected) or 'none'}\n"
        f"- Columns: by code / LLM-assisted = who decided each finding's status; $/check = "
        f"cost / requirement checks\n\n"
        + markdown_table(rows) + "\n", encoding="utf-8")
    print(f"summary: {SUMMARY_PATH.relative_to(ROOT)}")


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
