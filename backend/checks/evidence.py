"""Evidence helpers: verbatim quote verification, keyword matching and page excerpts.

A quote is accepted only if it appears verbatim in the page text after whitespace
normalization (case, letters and punctuation must match). This runs BEFORE any translation.
"""

import bisect
import os
import re

from backend.models import Page


def normalize_ws(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def min_quote_chars() -> int:
    return int(os.getenv("CHECK_MIN_QUOTE_CHARS") or 12)


def verify_quote(quote: str | None, page_text: str) -> bool:
    q = normalize_ws(quote or "")
    return len(q) >= min_quote_chars() and q in normalize_ws(page_text)


# Uzbek/Russian Cyrillic -> Latin, so a keyword in one script matches a page in the other.
_CYR = dict(zip("абвгдезийклмнопрстуфхчшщъыьэўқғҳ",
                ["a", "b", "v", "g", "d", "e", "z", "i", "y", "k", "l", "m", "n", "o", "p",
                 "r", "s", "t", "u", "f", "x", "ch", "sh", "sh", "", "i", "", "e", "o", "q",
                 "g", "h"]))
_CYR.update({"ё": "yo", "ж": "j", "ц": "ts", "ю": "yu", "я": "ya"})
_APOS = "'ʻʼ’‘`´"
# A word: letters/digits, with apostrophes inside it (o'zgartirish, ғ ўзгартириш).
_WORD = re.compile(r"[^\W_]+(?:[" + _APOS + r"][^\W_]+)*")
STEM_CHARS = 5       # a keyword word matches any page word that starts with its first 5 letters
KEYWORD_WINDOW = 8   # all words of a multi-word keyword must occur within this many words


def fold_word(word: str) -> str:
    """Matching form of one word (keyword matching only, never quotes): lowercase, Cyrillic
    transliterated to Latin, apostrophes removed."""
    w = "".join(_CYR.get(c, c) for c in word.lower())
    return re.sub("[" + _APOS + "]", "", w)


def _fold(text: str) -> str:
    """Lowercase, transliterated, apostrophes and punctuation removed."""
    return " ".join(fold_word(m.group()) for m in _WORD.finditer(text or ""))


def keyword_stems(keyword: str) -> list[str]:
    """Stems of a keyword's words (words shorter than 3 letters, e.g. "va", are dropped)."""
    words = [fold_word(m.group()) for m in _WORD.finditer(keyword or "")]
    return [w[:STEM_CHARS] for w in words if len(w) >= 3]


class _Tokens:
    """Words of a text with their character offsets, indexed by prefix for stem lookups."""

    def __init__(self, text: str):
        found = [(fold_word(m.group()), m.start()) for m in _WORD.finditer(text or "")]
        self.words = [w for w, _ in found]
        self.offsets = [o for _, o in found]
        self._index: dict[int, dict[str, list[int]]] = {}

    def positions(self, stem: str) -> list[int]:
        n = len(stem)
        if n not in self._index:
            idx: dict[str, list[int]] = {}
            for i, w in enumerate(self.words):
                if len(w) >= n:
                    idx.setdefault(w[:n], []).append(i)
            self._index[n] = idx
        return self._index[n].get(stem, [])

    def find(self, stems: list[str]) -> int | None:
        """Word index where all stems occur within KEYWORD_WINDOW words (any order)."""
        if not stems:
            return None
        lists = sorted((self.positions(s) for s in stems), key=len)
        if not lists[0]:
            return None
        for p in lists[0]:
            near = [p]
            for other in lists[1:]:
                i = bisect.bisect_left(other, p - KEYWORD_WINDOW)
                if i < len(other) and other[i] <= p + KEYWORD_WINDOW:
                    near.append(other[i])
                else:
                    break
            else:
                return min(near)
        return None


def partial_hits(page: Page, keywords: list[str]) -> tuple[int, int | None]:
    """How many distinct keyword stems occur anywhere on the page, and the character offset
    of the first one (None if none). Used only to pick the closest page for context."""
    text = _Tokens(page.text)
    stems = {s for kw in keywords for s in keyword_stems(kw)}
    found = [text.offsets[ps[0]] for s in stems if (ps := text.positions(s))]
    return len(found), (min(found) if found else None)


def keyword_hits(page: Page, keywords: list[str]) -> tuple[int, list[int]]:
    """Score a page for keywords: title/URL hits weigh 3, text hits 1 per distinct keyword.
    A keyword matches by word stems (see keyword_stems), across Latin/Cyrillic script and
    apostrophe variants, with its words in any order within a short window.
    Returns (score, character offsets of text hits)."""
    text, head = _Tokens(page.text), _Tokens(page.title + " " + page.url)
    score, offsets, done = 0, [], set()
    for kw in keywords:
        stems = keyword_stems(kw)
        if not stems or tuple(stems) in done:
            continue
        done.add(tuple(stems))
        if head.find(stems) is not None:
            score += 3
        i = text.find(stems)
        if i is not None:
            score += 1
            offsets.append(text.offsets[i])
    return score, sorted(set(offsets))


def excerpt(text: str, offsets: list[int], max_chars: int, before: int = 300,
            after: int = 700) -> list[str]:
    """Verbatim windows of `text` around offsets (merged), within max_chars in total.
    Without offsets: the opening of the page."""
    if not offsets:
        return [text[:max_chars]] if text else []
    spans: list[list[int]] = []
    for o in offsets:
        s, e = max(0, o - before), min(len(text), o + after)
        if spans and s <= spans[-1][1]:
            spans[-1][1] = max(spans[-1][1], e)
        else:
            spans.append([s, e])
    out, used = [], 0
    for s, e in spans:
        if used >= max_chars:
            break
        e = min(e, s + max_chars - used)
        out.append(text[s:e])
        used += e - s
    return out


def opening_quote(text: str, max_chars: int = 200) -> str:
    """A verbatim quote from the start of the page, cut at a word boundary."""
    t = normalize_ws(text)
    if len(t) <= max_chars:
        return t
    cut = t[:max_chars]
    return cut[:cut.rfind(" ")] if " " in cut else cut
