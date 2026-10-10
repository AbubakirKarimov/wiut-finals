"""Evidence helpers: verbatim quote verification, keyword matching and page excerpts.

A quote is accepted only if it appears verbatim in the page text after whitespace
normalization (case, letters and punctuation must match). This runs BEFORE any translation.
"""

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


def _fold(text: str) -> str:
    """Lowercase and unify apostrophe variants (for keyword matching only, never quotes)."""
    return re.sub(r"[ʻʼ’‘`´]", "'", text.lower())


def keyword_hits(page: Page, keywords: list[str]) -> tuple[int, list[int]]:
    """Score a page for keywords: title/URL hits weigh 3, text hits 1 per distinct keyword.
    Returns (score, character offsets of text hits)."""
    text, head = _fold(page.text), _fold(page.title + " " + page.url)
    score, offsets = 0, []
    for kw in {_fold(k).strip() for k in keywords if k and k.strip()}:
        if kw in head:
            score += 3
        i = text.find(kw)
        if i >= 0:
            score += 1
            offsets.append(i)
    return score, sorted(offsets)


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
