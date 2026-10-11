"""Measure which bank home pages are readable without a browser (hosted demo examples).

Usage: .venv/bin/python scripts/probe_hosted_examples.py
One plain HTTP request per bank (robots.txt, 1 request/second per domain, project
User-Agent), no browser, no LLM. Writes data/hosted_examples.json and prints a table.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend import hosted_examples  # noqa: E402
from backend.checks.llm_checks import homepage_min_chars  # noqa: E402
from backend.crawl.banks import load_banks  # noqa: E402
from backend.crawl.fetch import FetchConfig, Fetcher  # noqa: E402


def main() -> None:
    cfg = FetchConfig.from_env()
    cfg.browser_fallback = False
    threshold = homepage_min_chars()
    fetcher = Fetcher(cfg)
    try:
        rows = hosted_examples.measure(load_banks(), fetcher, threshold, cfg.min_text_chars)
    finally:
        fetcher.close()
    hosted_examples.write(rows, threshold)
    print(f"| bank | url | homepage text (chars) | works on hosted (>= {threshold}) |")
    print("|---|---|---|---|")
    for r in rows:
        note = f" ({r['classification']})" if r["classification"] != "ok" else ""
        print(f"| {r['bank_id']} | {r['url']} | {r['text_chars']}{note} | "
              f"{'yes' if r['works_on_hosted'] else 'no'} |")


if __name__ == "__main__":
    main()
