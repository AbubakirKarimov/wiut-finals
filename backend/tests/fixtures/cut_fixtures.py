"""Rebuild the small lex.uz test fixtures by cutting blocks out of saved real pages.

Needs the full pages in data/raw/lex/ (not committed). Run:
    python -m backend.tests.fixtures.cut_fixtures
Blocks are copied verbatim; toolbars are kept only on a few blocks and long tables are cut
to their first rows to keep each fixture small.
"""

import copy
import re
from pathlib import Path

from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[3]
RAW = ROOT / "data" / "raw" / "lex"
OUT = Path(__file__).resolve().parent
KEEP_TOOLBAR = 3
TABLE_ROWS = 1


def _children(doc_id: str):
    html = (RAW / f"{doc_id}.html").read_text(encoding="utf-8")
    return BeautifulSoup(html, "lxml").find(id="divCont").find_all(recursive=False)


def _text(el) -> str:
    c = copy.copy(el)
    for t in c.select(".lx_elem2"):
        t.decompose()
    return re.sub(r"\s+", " ", c.get_text(" ", strip=True))


def _write(name: str, kids, indices: list[int]) -> None:
    parts = []
    for n, i in enumerate(sorted(set(indices))):
        el = copy.copy(kids[i])
        if n >= KEEP_TOOLBAR:
            for t in el.select(".lx_elem2"):
                t.decompose()
        for table in el.find_all("table"):
            for tr in table.find_all("tr")[TABLE_ROWS:]:
                tr.decompose()
        parts.append(str(el))
    html = ('<!DOCTYPE html><html lang="ru-UZ"><head><meta charset="utf-8"></head><body>'
            '<div id="divCont">' + "\n".join(parts) + "</div></body></html>\n")
    (OUT / name).write_text(html, encoding="utf-8")
    print(f"{name}: {len(parts)} blocks, {len(html.encode('utf-8'))} bytes")


def _find(kids, pred, start=0) -> int:
    return next(i for i in range(start, len(kids)) if pred(kids[i]))


WRAPPER_KEEP = {"INDEXES_ON_REF", "ACT_FORM", "ACT_TITLE", "DEPARTMENTAL", "ACT_TEXT",
                "SIGNATURE", "APPL_BANNER_LANDSCAPE_TITLE", "ACT_TITLE_APPL", "NEW_EDITION",
                "EXPLANATION", "CLAUSE_DEFAULT", "COMMENT", "CHANGES_ORIGINS"}


def _cls(k) -> str:
    return (k.get("class") or [""])[0]


def _header(kids, stop: int) -> list[int]:
    """Wrapper blocks up to `stop`, without blocks the tests do not need."""
    idx = [i for i in range(stop) if _cls(kids[i]) in WRAPPER_KEEP]
    first_index = next(i for i in idx if _cls(kids[i]) == "INDEXES_ON_REF")
    return [i for i in idx if _cls(kids[i]) != "INDEXES_ON_REF" or i == first_index]


def reg3030() -> None:
    kids = _children("3804290")
    lat = _children("-3804290")
    nizom = _find(kids, lambda k: _cls(k) == "ACT_FORM" and _text(k) == "НИЗОМ")
    idx = _header(kids, nizom + 1)                             # resolution + Regulation start
    ch1 = _find(kids, lambda k: _text(k).startswith("1-боб."))
    idx += [ch1, ch1 + 1]                                      # chapter 1 + clause 1
    s61 = _find(kids, lambda k: 'id="4427441"' in str(k))      # clause 6^1 and its note
    idx += [s61, s61 + 1]
    c9 = _find(kids, lambda k: _text(k).startswith("9. Банк томонидан кредит"))
    idx += [c9, c9 + 1]                                        # clause 9 + sub-clause а)
    ch2 = _find(kids, lambda k: _text(k).startswith("2-боб."))
    p2 = _find(kids, lambda k: _text(k).startswith("2-§. Банкнинг расмий веб-сайтида"))
    idx += [ch2, p2, p2 + 1]                                   # chapter 2, §2, clause 13
    c401 = _find(kids, lambda k: 'id="5290580"' in str(k))
    idx += list(range(c401, c401 + 4))                         # 40^1, its note, §3 repeal note
    _write("reg3030_body_cyrl.html", kids, idx)
    _write("reg3030_body_latn.html", lat, idx)

    a1 = _find(kids, lambda k: _cls(k) == "APPL_BANNER_LANDSCAPE_TITLE"
               and "1-ИЛОВА" in _text(k))
    a1c1 = _find(kids, lambda k: _cls(k) == "ACT_TEXT" and _text(k).startswith("1."), a1)
    c60 = _find(kids, lambda k: _cls(k) == "ACT_TEXT" and _text(k).startswith("60."))
    reg_banner = _find(kids, lambda k: _cls(k) == "APPL_BANNER_LANDSCAPE_TITLE")
    idx = [reg_banner, nizom, c60]                             # Regulation start + clause 60
    idx += [a1, a1 + 2, a1 + 3, a1c1]                          # annex 1 banner/title + clause 1
    a3b = _find(kids, lambda k: _cls(k) == "APPL_BANNER_LANDSCAPE_TITLE"
                and "3б-ИЛОВА" in _text(k))
    a4 = _find(kids, lambda k: _cls(k) == "APPL_BANNER_LANDSCAPE_TITLE"
               and "4-ИЛОВА" in _text(k))
    idx += [i for i in range(a3b, a4) if _text(kids[i]) or kids[i].find("table")]
    _write("reg3030_annex_cyrl.html", kids, idx)               # + form annex 3б (table)
    _write("reg3030_annex_latn.html", lat, idx)


def law() -> None:
    kids = _children("121051")
    end = _find(kids, lambda k: _text(k).startswith("3-модда."))
    idx = _header(kids, end + 6)                               # enactment + arts 1-2 + art 3 part
    _write("law_cyrl.html", kids, idx)
    _write("law_latn.html", _children("-121051"), idx)


def pp3620_ru() -> None:
    kids = _children("3593543")
    start = _find(kids, lambda k: _text(k).startswith("В целях устранения"))
    _write("pp3620_ru.html", kids, list(range(start, start + 6)))


if __name__ == "__main__":
    reg3030()
    law()
    pp3620_ru()
