"""Which bank websites work on the hosted demo (no browser fallback).

A site is a hosted example only when its home page, fetched over plain HTTP the way the
crawler does with BROWSER_FALLBACK=0, is classified `ok` and has at least
`homepage_min_chars` characters of visible text (data/check_hints.yaml). The measurements
are written by scripts/probe_hosted_examples.py to data/hosted_examples.json; the Check
screen offers only these sites as examples.
"""

import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HOSTED_EXAMPLES = ROOT / "data" / "hosted_examples.json"


def measure(banks, fetcher, threshold: int, min_text_chars: int) -> list[dict]:
    from backend.crawl.text import classify, visible_text
    rows = []
    for b in banks:
        if not b.website_url:
            continue
        r = fetcher.get(b.website_url)
        html = r.text if not r.error and r.is_html else ""
        chars = len(visible_text(html)) if html else 0
        cls = "error" if r.error else classify(r.status, html, chars, min_text_chars)
        rows.append({"bank_id": b.id, "url": b.website_url, "http_status": r.status,
                     "text_chars": chars, "classification": cls, "error": r.error or None,
                     "works_on_hosted": cls == "ok" and chars >= threshold})
    return rows


def write(rows: list[dict], threshold: int, path: Path = HOSTED_EXAMPLES) -> None:
    path.write_text(json.dumps({
        "measured_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "homepage_min_chars": threshold, "browser_fallback": False, "banks": rows,
    }, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def load(path: Path = HOSTED_EXAMPLES) -> dict[str, dict]:
    """bank_id -> measurement; empty when the file is missing (no data: no examples)."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return {r["bank_id"]: {**r, "measured_at": data.get("measured_at")}
            for r in data.get("banks", [])}
