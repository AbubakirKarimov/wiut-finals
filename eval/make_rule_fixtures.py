"""Build the small HTML fixtures used by backend/tests/test_rules.py from stored crawl records.

The page store keeps visible text and (URL, anchor) link pairs, not raw HTML. Each fixture is
rebuilt as a minimal HTML page: the stored links as <a> elements in a <nav>, and excerpts of
the stored visible text (start, end, and passages around the checked words) in <p>. They are
excerpts, not full pages. Run once; the output is committed so tests need no network.

Usage: .venv/bin/python eval/make_rule_fixtures.py
"""

import html
import json
import re
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "backend" / "tests" / "fixtures" / "bank_pages"
PICK = re.compile(r"murojaat|обращени|kalkul|калькул|sayt xarit|карта сайта|haqida|о банке|"
                  r"kafolat|гарант|fgd\.uz|998|\b1\d{3}\b|telefon|телефон", re.I)
PAGES = [  # (fixture name, database, bank_id, url)
    ("mkbank_uz_home", "data/compliance.sqlite", "mkbank", "https://mkbank.uz/uz/"),
    ("anor_uz_home", "data/compliance.sqlite", "anor_bank", "https://www.anorbank.uz/uz/"),
    ("universal_home", "data/compliance.sqlite", "universal_bank", "https://universalbank.uz/"),
    ("garant_ru_home", "data/compliance.sqlite", "garant_bank", "https://garantbank.uz/ru"),
    ("agrobank_deposit_baraka", "data/raw/audit/audit.sqlite", "agrobank",
     "https://agrobank.uz/uz/person/deposits/baraka"),
    ("mkbank_uz_deposit", "data/compliance.sqlite", "mkbank", "https://mkbank.uz/uz/private/deposit/"),
    ("garant_ru_vklady", "data/raw/audit/audit.sqlite", "garant_bank", "https://garantbank.uz/ru/vklady"),
]


def excerpt(text: str) -> list[str]:
    parts = [text[:800]]
    for m in PICK.finditer(text):
        parts.append(text[max(0, m.start() - 150):m.end() + 150])
    parts.append(text[-600:])
    out, seen = [], set()
    for p in parts:  # drop repeats, keep order
        if p not in seen:
            seen.add(p)
            out.append(p)
    return out[:25]


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for name, dbp, bank, url in PAGES:
        c = sqlite3.connect(ROOT / dbp)
        row = c.execute("SELECT title, text, links FROM pages WHERE bank_id = ? AND url = ?",
                        (bank, url)).fetchone()
        title, text, links = row
        links = json.loads(links or "{}").get("links", [])
        keep = [(u, a) for u, a in links if PICK.search(u + " " + a)] + links[:25]
        seen, anchors = set(), []
        for u, a in keep:
            if (u, a) not in seen:
                seen.add((u, a))
                anchors.append(f'<a href="{html.escape(u)}">{html.escape(a)}</a>')
        paras = "\n".join(f"<p>{html.escape(p)}</p>" for p in excerpt(text))
        doc = (f"<!-- {url} | rebuilt by eval/make_rule_fixtures.py from stored crawl records "
               f"(links + visible-text excerpts), not the full page -->\n"
               f"<html><head><title>{html.escape(title or '')}</title></head><body>\n"
               f"<nav>{' '.join(anchors)}</nav>\n<main>\n{paras}\n</main></body></html>\n")
        (OUT / f"{name}.html").write_text(doc, encoding="utf-8")
        print(name, len(doc))


if __name__ == "__main__":
    main()
