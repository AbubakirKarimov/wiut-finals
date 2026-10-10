"""lex.uz documents: polite fetching of raw pages and offline parsing into clauses.

Parsing never touches the network: it reads saved pages from data/raw/lex/ and writes
data/regulations/<source_id>.json. Fetching is a separate function (`fetch_doc`).

CLI:
    python -m backend.ingest.lex --source cbu_reg_3030 [--source law_state_language] [--fetch]
"""

import argparse
import json
import os
import re
import sys
import time
import urllib.robotparser
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import httpx
import yaml
from bs4 import BeautifulSoup, NavigableString
from dotenv import load_dotenv

load_dotenv()

ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = ROOT / "data" / "raw" / "lex"
OUT_DIR = ROOT / "data" / "regulations"
SOURCES_PATH = ROOT / "data" / "sources.yaml"
LEX_BASE = "https://lex.uz"

# Editorial / metadata blocks that never become clause text.
DROP_CLASSES = {"COMMENT", "CHANGES_ORIGINS", "INDEXES_ON_REF", "EXPLANATION",
                "COMMENT_FOR_WARNING", "PUBLICATION_ORIGIN"}
# Document header/footer blocks: kept as metadata only.
META_CLASSES = {"ACT_FORM", "ACCEPTING_BODY", "ACT_TITLE", "DEPARTMENTAL", "SIGNATURE",
                "ACT_ESSENTIAL_ELEMENTS", "ACT_ESSENTIAL_ELEMENTS_NUM", "NEW_EDITION",
                "ACT_TITLE_APPL", "APPL_BANNER_LANDSCAPE_TITLE"}

APOS = "ʻ'‘’`"
CLAUSE_RE = re.compile(r"^(\d+)(?:\^(\d+))?\s*\.(?=\s|$)")
ARTICLE_RE = re.compile(r"^(?:(\d+)\s*-\s*(?:модда|modda)|Статья\s+(\d+))", re.I)
CHAPTER_RE = re.compile(r"^\d+\s*-\s*(?:боб|bob)\b", re.I)
PARAGRAPH_RE = re.compile(r"^\d+\s*-\s*(?:§|параграф|paragraf)", re.I)
ANNEX_RE = re.compile(r"(\d+[^\W\d_]?)\s*-\s*(?:илова|ilova)", re.I)
REPEAL_RE = re.compile(
    rf"кучини\s+йўқотган|kuchini\s+yo[{APOS}]?qotgan|утратил[аио]?\s+силу", re.I)
NOTE_CLAUSE_RE = re.compile(
    r"^\(\s*(?P<nums>\d+(?:\^\d+)?(?:\s*(?:ва|va|,|—|–)\s*\d+(?:\^\d+)?)*)\s*-\s*"
    r"(?P<kind>банд|band|модда|modda)(?P<rest>.*)", re.I | re.S)
NOTE_CLAUSE_RU_RE = re.compile(r"^\(\s*(?P<kind>пункт|статья)\s+(?P<nums>\d+)(?P<rest>.*)",
                               re.I | re.S)
NOTE_PREAMBLE_RE = re.compile(r"^\(\s*(?:муқаддима|muqaddima|преамбула)", re.I)
AMENDING_ACT_RES = [
    re.compile(rf"(?:рўйхат\s+рақами|ro[{APOS}]yxat\s+raqami)\s+(\d+(?:-\d+)?)", re.I),
    re.compile(rf"\b(ЎРҚ-\d+|O[{APOS}]RQ-\d+|ЗРУ-\d+|УП-\d+|ПП-\d+|\d+-[IVX]+)\b"),
]
ADDED_RE = re.compile(rf"киритилган|тўлдирилган|kiritilgan|to[{APOS}]ldirilgan|дополнен", re.I)
AMENDED_RE = re.compile(r"таҳририда|tahririda|в редакции", re.I)
CYR_TO_LAT = str.maketrans({"а": "a", "б": "b", "в": "v", "г": "g", "д": "d"})

WRAPPER_SECTION = {"regulation": "resolution", "law": "enactment"}
MAIN_SECTION = {"regulation": "main", "law": "art"}


class AlignmentError(ValueError):
    """Cyrillic and Latin pages do not pair block-by-block."""


class FetchError(RuntimeError):
    """lex.uz did not return the document (blocked, missing, or unexpected page)."""


# ---------------------------------------------------------------- blocks

@dataclass
class Block:
    cls: str
    block_id: str | None
    text: str
    has_table: bool


def _norm_lines(text: str) -> str:
    lines = (re.sub(r"[ \t ​‎‏﻿]+", " ", ln).strip()
             for ln in text.split("\n"))
    return "\n".join(ln for ln in lines if ln)


def _table_text(table) -> str:
    rows = []
    for tr in table.find_all("tr"):
        cells = [_norm_lines(td.get_text(" ")).replace("\n", " ")
                 for td in tr.find_all(["td", "th"])]
        cells = [c for c in cells if c]
        if cells:
            rows.append(" | ".join(cells))
    return "\n".join(rows)


def read_blocks(html: str) -> list[Block]:
    soup = BeautifulSoup(html, "lxml")
    cont = soup.find(id="divCont")
    if cont is None:
        raise ValueError("Not a lex.uz document page: div#divCont not found")
    for toolbar in cont.select(".lx_elem2"):
        toolbar.decompose()
    for sup in cont.find_all("sup"):
        sup.replace_with("^" + sup.get_text(strip=True))
    blocks = []
    for el in cont.find_all(recursive=False):
        classes = el.get("class") or []
        inner = el.find("div", id=True)
        has_table = el.find("table") is not None
        for table in el.find_all("table"):
            if table.parent is not None:  # skip tables inside an already replaced table
                table.replace_with(NavigableString("\n" + _table_text(table) + "\n"))
        blocks.append(Block(
            cls=classes[0] if classes else "",
            block_id=inner.get("id") if inner else None,
            text=_norm_lines(el.get_text("")),
            has_table=has_table,
        ))
    return blocks


def latin_block_id(cyr_id: str) -> str:
    """lex.uz Latin pages use the Cyrillic id with '-' before its number."""
    return re.sub(r"(\d+)", r"-\1", cyr_id, count=1)


def align_latin(cyr: list[Block], lat: list[Block]) -> dict[str, str]:
    if len(cyr) != len(lat):
        raise AlignmentError(f"block count differs: Cyrillic {len(cyr)}, Latin {len(lat)}")
    mapping = {}
    for i, (c, l) in enumerate(zip(cyr, lat)):
        if c.cls != l.cls:
            raise AlignmentError(f"block {i}: class {c.cls!r} vs {l.cls!r}")
        if (c.block_id is None) != (l.block_id is None) or (
                c.block_id and l.block_id != latin_block_id(c.block_id)):
            raise AlignmentError(f"block {i}: id {c.block_id!r} vs {l.block_id!r}")
        if c.block_id:
            mapping[c.block_id] = l.text
    return mapping


# ---------------------------------------------------------------- notes

def parse_note(block: Block) -> dict:
    text = block.text
    act = None
    for rx in AMENDING_ACT_RES:
        m = rx.search(text)
        if m:
            act = m.group(1)
            break
    if REPEAL_RE.search(text):
        change = "repealed"
    elif ADDED_RE.search(text):
        change = "added"
    elif AMENDED_RE.search(text):
        change = "amended"
    else:
        change = "other"
    return {"block_id": block.block_id, "text": text, "amending_act": act, "change": change}


def note_target(text: str) -> tuple[list[tuple[str, str]], bool] | None:
    """Return ([(first, last) clause number ranges], whole_clause) for a clause/article note.

    "35^3 ва 35^4-бандлар" -> [("35^3", "35^3"), ("35^4", "35^4")];
    "36^1 — 36^4-бандлар" -> [("36^1", "36^4")]. Notes about a chapter, paragraph or
    annex return None.
    """
    if NOTE_PREAMBLE_RE.match(text):
        return ([("preamble", "preamble")], True)
    m = NOTE_CLAUSE_RE.match(text) or NOTE_CLAUSE_RU_RE.match(text)
    if not m:
        return None
    ranges = []
    for part in re.split(r"\s*(?:ва|va|,)\s*", m.group("nums")):
        ends = re.findall(r"\d+(?:\^\d+)?", part)
        ranges.append((ends[0], ends[-1]))
    rest = m.group("rest")
    # "1-банднинг учинчи хатбошиси" / "2-банд «в» кичик бандининг" refer to a part only.
    whole = bool(re.match(r"^(?:лар|lar)?\s+(?![«“\"])", rest)) and not re.match(
        r"^(?:нинг|ning|ини|ini)", rest)
    return (ranges, whole)


# ---------------------------------------------------------------- parsing

@dataclass
class _Section:
    key: str
    annex: str | None
    kind: str  # "text" | "form"
    blocks: list[Block] = field(default_factory=list)


def _split_sections(blocks: list[Block], role: str) -> list[_Section]:
    wrapper = WRAPPER_SECTION.get(role, "act")
    main = MAIN_SECTION.get(role, "main")
    sections = [_Section(wrapper, None, "text")]
    signed = False
    for b in blocks:
        cur = sections[-1]
        if b.cls == "APPL_BANNER_LANDSCAPE_TITLE":
            m = ANNEX_RE.search(b.text)
            if m:
                label = m.group(1).lower().translate(CYR_TO_LAT)
                sections.append(_Section(f"annex{label}", label, "text"))
            else:
                sections.append(_Section(main, None, "text"))
        elif b.cls == "ACT_FORM" and signed and cur.key == wrapper:
            sections.append(_Section(main, None, "text"))
        elif b.cls == "SIGNATURE":
            signed = True
        sections[-1].blocks.append(b)
    for s in sections:
        if s.annex is None:
            continue
        numbered = any(b.cls == "ACT_TEXT" and CLAUSE_RE.match(b.text) for b in s.blocks)
        if any(b.has_table for b in s.blocks) or not numbered:
            s.kind = "form"
    return sections


def _clause_key(number: str) -> tuple[int, int]:
    base, _, sup = number.partition("^")
    return int(base), int(sup or 0)


def parse_document(html: str, *, source_id: str, doc_id: str, role: str, language: str,
                   latin_html: str | None = None, latin_doc_id: str | None = None,
                   fetched_at: str | None = None) -> dict:
    blocks = read_blocks(html)
    latin = align_latin(blocks, read_blocks(latin_html)) if latin_html is not None else None
    url = f"{LEX_BASE}/ru/docs/{doc_id}"

    title = next((b.text for b in blocks if b.cls == "ACT_TITLE"), None)
    clauses: list[dict] = []
    annexes: list[dict] = []
    unattached: list[dict] = []
    warnings: list[str] = []
    ids: set[str] = set()

    def new_clause(section: _Section, number: str, chapter, paragraph, first_id) -> dict:
        clause_id = f"{source_id}:{section.key}:{number}"
        if clause_id in ids:
            raise ValueError(f"duplicate clause_id {clause_id}")
        ids.add(clause_id)
        c = {"clause_id": clause_id, "number": number, "section": section.key,
             "chapter": chapter, "paragraph": paragraph, "annex": section.annex,
             "kind": section.kind, "block_ids": [], "text_original": "",
             "url": f"{url}#{first_id}" if first_id else url,
             "amendment_notes": [], "repealed": False}
        if latin is not None:
            c["text_parallel_latn"] = ""
        clauses.append(c)
        return c

    def add_block(c: dict, b: Block) -> None:
        if not b.text:
            return
        c["block_ids"].append(b.block_id)
        c["text_original"] = (c["text_original"] + "\n" + b.text).strip("\n")
        if latin is not None:
            c["text_parallel_latn"] = (c["text_parallel_latn"] + "\n" +
                                       latin.get(b.block_id, "")).strip("\n")

    for section in _split_sections(blocks, role):
        chapter = paragraph = None
        current: dict | None = None
        by_number: dict[str, dict] = {}
        last_key: tuple[int, int] | None = None
        list_next: int | None = None  # next expected item number of an in-clause list
        article_mode = False
        text_counter = 0

        if section.annex is not None:
            title_parts = [b.text for b in section.blocks
                           if b.cls in ("ACT_TITLE_APPL", "ACT_FORM") and b.text]
            first = next((b.block_id for b in section.blocks if b.block_id), None)
            annexes.append({"annex": section.annex, "section": section.key,
                            "title": " ".join(title_parts), "kind": section.kind,
                            "block_id": first})

        if section.kind == "form":
            first = next((b.block_id for b in section.blocks if b.block_id), None)
            form = new_clause(section, "form", None, None, first)
            for b in section.blocks:
                if b.cls == "CHANGES_ORIGINS":
                    form["amendment_notes"].append(parse_note(b))
                elif b.cls not in DROP_CLASSES:
                    add_block(form, b)
            continue

        for b in section.blocks:
            if b.cls == "CHANGES_ORIGINS":
                note = parse_note(b)
                target = note_target(b.text)
                attached = False
                if target is not None:
                    ranges, whole = target
                    nums = []
                    for first, last in ranges:
                        if first == last or first == "preamble":
                            nums.append(first)
                            continue
                        lo, hi = _clause_key(first), _clause_key(last)
                        nums += [n for n in by_number
                                 if n[0].isdigit() and lo <= _clause_key(n) <= hi]
                    for num in nums:
                        c = by_number.get(num)
                        if c is None and whole and note["change"] == "repealed":
                            c = new_clause(section, num, chapter, paragraph, b.block_id)
                            c["block_ids"].append(b.block_id)
                            by_number[num] = c
                        if c is None:
                            continue
                        c["amendment_notes"].append(note)
                        if whole and note["change"] == "repealed":
                            c["repealed"] = True
                        attached = True
                if not attached:
                    unattached.append({**note, "section": section.key, "chapter": chapter,
                                       "paragraph": paragraph})
                continue
            if b.cls in DROP_CLASSES or b.cls in META_CLASSES or not b.text:
                continue
            if b.cls == "TEXT_HEADER_DEFAULT":
                if PARAGRAPH_RE.match(b.text):
                    paragraph = b.text
                else:
                    chapter, paragraph = b.text, None
                current = None
                list_next = None
                continue
            if b.cls == "CLAUSE_DEFAULT":
                m = ARTICLE_RE.match(b.text)
                if m:
                    number = m.group(1) or m.group(2)
                    current = new_clause(section, number, chapter, paragraph, b.block_id)
                    by_number[number] = current
                    add_block(current, b)
                    article_mode = True
                    continue
            m = CLAUSE_RE.match(b.text) if b.cls == "ACT_TEXT" and not article_mode else None
            if m:
                number = m.group(1) + (f"^{m.group(2)}" if m.group(2) else "")
                key = _clause_key(number)
                # A "1." inside an open clause starts a numbered list within that clause;
                # "2.", "3." ... continue it until a number breaks the sequence.
                if current is not None and last_key is not None and (
                        key == (1, 0) or (list_next is not None and key == (list_next, 0))):
                    list_next = key[0] + 1
                    add_block(current, b)
                    continue
                if last_key is None or key > last_key:
                    current = new_clause(section, number, chapter, paragraph, b.block_id)
                    by_number[number] = current
                    last_key = key
                    list_next = None
                    add_block(current, b)
                    continue
                warnings.append(f"{section.key}: block {b.block_id} starts with {number}. "
                                f"after {last_key}; kept as continuation")
            if current is None:
                number = "preamble" if "preamble" not in by_number else f"text{text_counter}"
                text_counter += 1
                current = new_clause(section, number, chapter, paragraph, b.block_id)
                by_number[number] = current
            add_block(current, b)

    for c in clauses:
        if not c["repealed"] and len(c["text_original"]) < 200 and REPEAL_RE.search(
                c["text_original"]):
            c["repealed"] = True

    fetched = fetched_at
    return {
        "source_id": source_id,
        "doc_id": doc_id,
        "url": url,
        "language": language,
        "title": title,
        "fetched_at": fetched,
        "source_snapshot_date": fetched[:10] if fetched else None,
        "parallel": ({"doc_id": latin_doc_id, "language": "uz_latn",
                      "url": f"{LEX_BASE}/ru/docs/{latin_doc_id}"} if latin_doc_id else None),
        "annexes": annexes,
        "unattached_notes": unattached,
        "warnings": warnings,
        "clauses": clauses,
    }


# ---------------------------------------------------------------- sources & IO

def load_sources(path: Path = SOURCES_PATH) -> dict[str, dict]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return {e["id"]: e for e in data["sources"]}


def _fetched_at(raw_path: Path) -> str:
    meta = raw_path.with_suffix(".meta.json")
    if meta.exists():
        return json.loads(meta.read_text(encoding="utf-8"))["fetched_at"]
    # Pages saved before meta files existed: the file was written right after the fetch.
    return datetime.fromtimestamp(raw_path.stat().st_mtime, timezone.utc).isoformat()


def parse_source(source: dict, raw_dir: Path = RAW_DIR) -> dict:
    doc_id = source["lex_uz_doc_id"]
    raw = raw_dir / f"{doc_id}.html"
    if not raw.exists():
        raise FileNotFoundError(f"{raw} missing; run with --fetch or save the page manually")
    latin = next((p for p in source.get("parallel", []) if p["language"] == "uz_latn"), None)
    latin_html = None
    if latin:
        latin_path = raw_dir / f"{latin['lex_uz_doc_id']}.html"
        if not latin_path.exists():
            raise FileNotFoundError(f"{latin_path} missing")
        latin_html = latin_path.read_text(encoding="utf-8")
    return parse_document(
        raw.read_text(encoding="utf-8"), source_id=source["id"], doc_id=doc_id,
        role=source.get("role", "reference"), language=source["language"],
        latin_html=latin_html, latin_doc_id=latin["lex_uz_doc_id"] if latin else None,
        fetched_at=_fetched_at(raw))


def write_output(doc: dict, out_dir: Path = OUT_DIR) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{doc['source_id']}.json"
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return path


# ---------------------------------------------------------------- fetching (network)

class _Polite:
    """Per-process robots.txt cache and >= min-delay spacing between lex.uz requests."""

    def __init__(self):
        self.robots: urllib.robotparser.RobotFileParser | None = None
        self.robots_missing = False
        self.last_request = 0.0

    def wait(self, min_delay: float) -> None:
        delta = time.monotonic() - self.last_request
        if delta < min_delay:
            time.sleep(min_delay - delta)
        self.last_request = time.monotonic()


_polite = _Polite()


def user_agent() -> str:
    return os.getenv("CRAWLER_USER_AGENT") or "ComplianceRadar/0.1 (WIUT hackathon)"


def fetch_doc(doc_id: str, *, raw_dir: Path = RAW_DIR, client: httpx.Client | None = None,
              polite: _Polite = _polite) -> Path:
    """Fetch one lex.uz document page once. Never retries or bypasses protection."""
    min_delay = float(os.getenv("CRAWLER_MIN_DELAY_SECONDS") or 1.0)
    own = client is None
    client = client or httpx.Client(headers={"User-Agent": user_agent()}, timeout=30,
                                    follow_redirects=True)
    try:
        url = f"{LEX_BASE}/ru/docs/{doc_id}"
        if polite.robots is None and not polite.robots_missing:
            polite.wait(min_delay)
            r = client.get(f"{LEX_BASE}/robots.txt")
            if r.status_code == 404:
                polite.robots_missing = True  # no robots.txt: no restrictions
            elif r.status_code == 200:
                rp = urllib.robotparser.RobotFileParser()
                rp.parse(r.text.splitlines())
                polite.robots = rp
            else:
                raise FetchError(f"robots.txt returned HTTP {r.status_code}; not fetching")
        if polite.robots is not None and not polite.robots.can_fetch(user_agent(), url):
            raise FetchError(f"robots.txt disallows {url}")
        polite.wait(min_delay)
        r = client.get(url)
        if r.status_code != 200:
            raise FetchError(f"{url}: HTTP {r.status_code} (possibly blocked); not retrying")
        if 'id="divCont"' not in r.text:
            raise FetchError(f"{url}: page has no document body (possible bot protection)")
        raw_dir.mkdir(parents=True, exist_ok=True)
        path = raw_dir / f"{doc_id}.html"
        path.write_bytes(r.content)
        meta = {"doc_id": doc_id, "url": url, "status": r.status_code,
                "fetched_at": datetime.now(timezone.utc).isoformat()}
        path.with_suffix(".meta.json").write_text(json.dumps(meta), encoding="utf-8")
        return path
    finally:
        if own:
            client.close()


# ---------------------------------------------------------------- CLI

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Parse saved lex.uz pages into clauses.")
    ap.add_argument("--source", action="append", required=True,
                    help="source id from data/sources.yaml (repeatable)")
    ap.add_argument("--fetch", action="store_true",
                    help="download missing raw pages first (network, polite)")
    args = ap.parse_args(argv)
    sources = load_sources()
    for sid in args.source:
        if sid not in sources:
            print(f"error: unknown source {sid!r}", file=sys.stderr)
            return 2
        src = sources[sid]
        if src["status"] != "verified":
            print(f"error: source {sid!r} is not verified", file=sys.stderr)
            return 2
        if args.fetch:
            doc_ids = [src["lex_uz_doc_id"]] + [p["lex_uz_doc_id"] for p in
                                                src.get("parallel", [])
                                                if p["language"] == "uz_latn"]
            for d in doc_ids:
                if not (RAW_DIR / f"{d}.html").exists():
                    print(f"fetching {d} ...")
                    fetch_doc(d)
        doc = parse_source(src)
        path = write_output(doc)
        cl = doc["clauses"]
        print(f"{sid}: {len(cl)} clauses, {sum(c['repealed'] for c in cl)} repealed, "
              f"{sum(a['kind'] == 'form' for a in doc['annexes'])} form annexes, "
              f"{len(doc['unattached_notes'])} unattached notes, "
              f"{len(doc['warnings'])} warnings -> {path.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
