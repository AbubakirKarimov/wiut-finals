"""required_document and key_info checks, search keywords and quote translation.

Both checks first select candidate pages deterministically by keywords (Uzbek Latin and
Cyrillic, Russian, English). Keywords come from data/check_hints.yaml when a human wrote
them for the requirement, otherwise the LLM proposes them once (cached in llm_cache).
Then the LLM answers yes/no for each candidate page and MUST return a verbatim quote; the
quote is verified against the page text in code and the answer is rejected if it is not
found.
"""

import os
from pathlib import Path

import yaml
from pydantic import BaseModel, Field

from backend.checks.evidence import (excerpt, keyword_hits, opening_quote, partial_hits,
                                     verify_quote)
from backend.checks.types import CheckOutcome
from backend.llm.provider import LLMError, LLMProvider, LLMTransientError
from backend.models import Page, Requirement

HINTS_PATH = Path(__file__).resolve().parents[2] / "data" / "check_hints.yaml"
TIMEOUT_REASON = "LLM timeout / rate limit"
CHARS_PER_TOKEN = 2.5  # a real run measured ~2.6 characters per token on Uzbek/Russian text


class KeywordSet(BaseModel):
    uz_latn: list[str] = Field(default_factory=list, max_length=8)
    uz_cyrl: list[str] = Field(default_factory=list, max_length=8)
    ru: list[str] = Field(default_factory=list, max_length=8)
    en: list[str] = Field(default_factory=list, max_length=8)


class PresenceAnswer(BaseModel):
    present: bool
    quote: str = Field(description="Passage copied character for character from the excerpts")
    explanation: str = Field(default="", description="One short English sentence")


class TranslationAnswer(BaseModel):
    translation_en: str


KEYWORDS_PROMPT = """A tool searches a bank's public website (menu items, section titles, \
page text, PDF file names) for evidence of one legal requirement.

Requirement (English, machine translation): {text_en}
Requirement (original): {text_original}

List short search keywords (1-3 words each, lowercase, word stems are fine) that such a \
website would use for this topic, in Uzbek Latin, Uzbek Cyrillic, Russian and English. \
At most 6 per language. No generic words like "bank" or "service"."""

PRESENCE_PROMPT = """You check one page of a bank's public website for one legal \
requirement of Uzbek banking law. Use ONLY the excerpts below; they are verbatim parts of \
the page in its original language (Uzbek or Russian).

Requirement (English, machine translation): {text_en}
Requirement (original): {text_original}
Question: {question}

Page URL: {url}
Page title: {title}
<excerpts>
{excerpts}
</excerpts>

Answer "present": true only if the excerpts clearly show it. In "quote" copy ONE passage \
of 20-300 characters EXACTLY as written in the excerpts: same letters, same punctuation, \
same language; do not translate, shorten words or fix spelling. If present is false, quote \
the passage most closely related to the requirement, or "" if nothing is related."""

QUESTIONS = {
    "required_document": "Is the required document or section published on this page "
                         "(as text, a section, or a link/file named after it)?",
    "key_info": "Does this page state the required information?",
}

TRANSLATE_PROMPT = """Translate this quote from a bank website (Uzbek or Russian) into \
English. Keep numbers and names. Quote:
{quote}"""


def _env_int(name: str, default: int) -> int:
    return int(os.getenv(name) or default)


def _hint_entry(req: Requirement, path: Path | None = None) -> dict:
    path = path or HINTS_PATH
    if not path.exists():
        return {}
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return (data.get("requirements") or {}).get(req.id) or {}


def hint_sections(req: Requirement, path: Path | None = None) -> list[str]:
    """Site sections where evidence for the requirement is expected (data/check_hints.yaml)."""
    return [s for s in (_hint_entry(req, path).get("sections") or []) if s]


def hint_keywords(req: Requirement, path: Path | None = None) -> list[str] | None:
    entry = _hint_entry(req, path)
    if not entry:
        return None
    kws = entry.get("keywords") or {}
    flat = [k for v in kws.values() for k in (v or [])] if isinstance(kws, dict) else list(kws)
    return [k for k in flat if k] or None


def get_keywords(req: Requirement, llm: LLMProvider | None) -> tuple[list[str] | None, str]:
    """(keywords, source). source is 'hints', 'llm', or an explanation when none."""
    kws = hint_keywords(req)
    if kws:
        return kws, "hints"
    if llm is None:
        return None, "no keywords: LLM not configured and no data/check_hints.yaml entry"
    try:
        ans = llm.complete_json(KEYWORDS_PROMPT.format(text_en=req.text_en or "no data",
                                                       text_original=req.text_original),
                                KeywordSet)
    except LLMTransientError as e:
        return None, f"{TIMEOUT_REASON} while choosing keywords: {str(e)[:120]}"
    except LLMError as e:
        return None, f"no keywords: LLM error ({str(e)[:120]})"
    flat = [k for v in ans.values() for k in v if k and len(k.strip()) >= 3]
    return (flat or None), "llm"


def candidate_pages(pages: list[Page], keywords: list[str], limit: int
                    ) -> list[tuple[Page, list[int]]]:
    scored = []
    for p in pages:
        if not p.readable:
            continue
        score, offs = keyword_hits(p, keywords)
        if score > 0:
            scored.append((score, p, offs))
    scored.sort(key=lambda x: -x[0])
    return [(p, offs) for _, p, offs in scored[:limit]]


def absence_outcome(readable: list[Page], keywords: list[str], kw_note: str) -> CheckOutcome:
    """No page matched the keywords: possible_gap with no evidence quote. The closest page
    (most keyword stems anywhere in its text) and a passage around its first stem are kept
    as context only; without any stem on any page there is no context passage."""
    scored = [(partial_hits(p, keywords), i, p) for i, p in enumerate(readable)]
    (n_stems, off), _, page = max(scored, key=lambda x: (x[0][0], -x[1]))
    context = None
    if off is not None:
        context = opening_quote(excerpt(page.text, [off], 300, before=0, after=300)[0], 300)
    closest = (f"closest page by keyword stems ({n_stems} stem(s)): {page.url}" if n_stems
               else f"no keyword stem on any page; page shown: {page.url}")
    return CheckOutcome("possible_gap", page=page, context=context, absence=True,
                        reason=f"No evidence found on {len(readable)} pages read. No page "
                               f"matched the keywords ({kw_note}); {closest}. Any passage "
                               "shown is context, not evidence.")


def check_presence(req: Requirement, pages: list[Page], llm: LLMProvider | None
                   ) -> CheckOutcome:
    """Shared flow of required_document and key_info."""
    keywords, source = get_keywords(req, llm)
    if not keywords:
        return CheckOutcome("not_checkable", reason=source)
    max_pages = _env_int("CHECK_LLM_MAX_PAGES", 2)
    # Context budget per call: CHECK_MAX_CONTEXT_TOKENS, converted with a conservative
    # CHARS_PER_TOKEN estimate (Cyrillic and Uzbek text tokenize worse than English).
    max_chars = int(_env_int("CHECK_MAX_CONTEXT_TOKENS", 2500) * CHARS_PER_TOKEN)
    window = _env_int("CHECK_EXCERPT_WINDOW_CHARS", 1500)
    cands = candidate_pages(pages, keywords, max_pages)
    kw_note = f"keywords from {source}: {', '.join(keywords[:12])}"
    readable = [p for p in pages if p.readable]
    if not cands:
        if not readable:
            return CheckOutcome("not_checkable", reason="no readable pages")
        return absence_outcome(readable, keywords, kw_note)
    if llm is None:
        return CheckOutcome("not_checkable",
                            reason=f"LLM not configured; {len(cands)} keyword candidate page(s): "
                                   + ", ".join(p.url for p, _ in cands))
    rejected, closest = [], None
    for page, offs in cands:
        parts = excerpt(page.text, offs, max_chars, before=window, after=window)
        prompt = PRESENCE_PROMPT.format(
            text_en=req.text_en or "no data", text_original=req.text_original,
            question=QUESTIONS[req.check_type], url=page.url, title=page.title or "no data",
            excerpts="\n...\n".join(parts))
        try:
            ans = llm.complete_json(prompt, PresenceAnswer)
        except LLMTransientError as e:
            return CheckOutcome("not_checkable", llm_used=True,
                                reason=f"{TIMEOUT_REASON}: {str(e)[:160]}")
        except LLMError as e:
            return CheckOutcome("not_checkable", reason=f"LLM error: {str(e)[:160]}",
                                llm_used=True)
        verified = verify_quote(ans["quote"], page.text)
        if ans["present"] and verified:
            return CheckOutcome("ok", page=page, quote=ans["quote"], llm_used=True,
                                reason=f"LLM: present, quote verified. {ans['explanation']}")
        if ans["present"]:
            rejected.append(page.url)
        elif verified and closest is None:
            closest = (page, ans["quote"], ans["explanation"])
    if rejected:
        return CheckOutcome("not_checkable", llm_used=True,
                            reason="LLM said present but its quote was not found verbatim in "
                                   "the page text (answer rejected): " + ", ".join(rejected))
    if closest:
        page, quote, expl = closest
        return CheckOutcome("possible_gap", page=page, quote=quote, llm_used=True,
                            reason=f"LLM: not present on {len(cands)} candidate page(s); quote "
                                   f"is the closest related passage. {expl} ({kw_note})")
    page, offs = cands[0]
    return CheckOutcome("possible_gap", page=page, llm_used=True,
                        quote=opening_quote(excerpt(page.text, offs[:1], 400, 0, 400)[0]),
                        reason=f"LLM: not present on {len(cands)} candidate page(s); quote is "
                               f"the keyword match on the best candidate ({kw_note})")


def translate(quote: str, llm: LLMProvider | None) -> str | None:
    """Machine translation of an already verified quote; None when unavailable."""
    if llm is None or not quote:
        return None
    try:
        return llm.complete_json(TRANSLATE_PROMPT.format(quote=quote),
                                 TranslationAnswer)["translation_en"] or None
    except LLMError:
        return None  # the finding keeps its verified original quote
