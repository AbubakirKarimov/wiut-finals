"""Consumer-facing site sections, recognised by stems in a URL path, link text or page title.

Used by the crawler (fetch these sections first) and by the checks (a possible_gap for a
section-bound requirement needs at least one page of that section read).
"""

import re
from urllib.parse import urlsplit

from backend.checks.evidence import _fold

# Stems are matched against folded text (lowercase, Cyrillic transliterated to Latin,
# apostrophes and punctuation removed), so one Latin stem covers both scripts.
# The authoritative list is `settings.section_stems` in data/check_hints.yaml; this copy is
# only the fallback when that block is missing (e.g. tests with their own hints file).
SECTION_STEMS: dict[str, tuple[str, ...]] = {
    "deposit": ("omonat", "vklad", "depozit", "deposit"),
    "loan": ("kredit", "credit", "loan", "ipotek", "mikroqarz", "mikrozaym", "avtokredit"),
    "document": ("hujjat", "dokument", "document", "oferta", "shartnoma", "dogovor", "pdf",
                 "qoidalar", "pravila"),
    "tariff": ("tarif", "komissiya", "komiss"),
    "restructuring": ("restruktur", "restructur", "qayta"),
    "complaint": ("murojaat", "obrashen", "jalob", "shikoyat", "complaint", "appeal",
                  "reception", "feedback"),
    "contacts": ("contact", "kontakt", "aloqa", "svyaz"),
}
# Sections that hold most checked requirements; fetched before complaint/contacts pages.
CORE_SECTIONS = ("deposit", "loan", "document", "tariff", "restructuring")
OTHER_STEMS = ("karta", "foiz", "stavk", "consumer", "istemolchi", "about",
               "biz haqimizda", "o banke")
HOMEPAGE_PATHS = {"", "uz", "ru", "oz", "en", "uz-latn", "uz-cyrl", "main", "home"}


def section_stems() -> dict[str, tuple[str, ...]]:
    from backend.checks.llm_checks import hint_setting  # data/check_hints.yaml
    stems = hint_setting("section_stems", None)
    if not stems:
        return SECTION_STEMS
    return {k: tuple(str(x) for x in (v or [])) for k, v in stems.items()}


def _hay(*texts: str) -> str:
    return " ".join(_fold(t.replace("/", " ").replace("-", " ").replace("_", " "))
                    for t in texts)


def sections_of(*texts: str) -> list[str]:
    hay = _hay(*texts)
    return [s for s, stems in section_stems().items() if any(st in hay for st in stems)]


def _norm(url: str) -> str:
    p = urlsplit(url)
    return p.netloc.lower().removeprefix("www.") + "/" + p.path.strip("/")


def page_reached_section(page, sections: list[str], pages: list, home_url: str | None) -> bool:
    """Strict section membership (section_match: strict): the page's URL path matches the
    section stems, or a page that was read links to it with link text naming the section
    (menu). The homepage never counts for a content section, and titles are not used."""
    if is_homepage(page.url, home_url):
        return "homepage" in sections
    wanted = set(sections) - {"homepage"}
    if wanted & set(sections_of(urlsplit(page.url).path)):
        return True
    target = _norm(page.url)
    for other in pages:
        for u, anchor in getattr(other, "links", None) or []:
            if _norm(u) == target and wanted & set(sections_of(anchor)):
                return True
    return False


def link_rank(url: str, anchor: str) -> tuple[int, str | None]:
    """(tier, section) for crawl order: 0 core section, 1 complaint/contacts, 2 other
    consumer page, 3 anything else. Section is the first matching one (None if none)."""
    secs = sections_of(urlsplit(url).path, anchor)
    core = [s for s in secs if s in CORE_SECTIONS]
    if core:
        return 0, core[0]
    if secs:
        return 1, secs[0]
    hay = _fold(urlsplit(url).path.replace("/", " ") + " " + anchor)
    return (2 if any(s in hay for s in OTHER_STEMS) else 3), None


def is_homepage(url: str, home_url: str | None = None) -> bool:
    """Site root, a language root (/uz/, /ru/, ...) or the crawl's own start page."""
    def norm(u: str) -> str:
        p = urlsplit(u)
        return p.netloc.lower() + "/" + p.path.strip("/")
    if home_url and norm(url) == norm(home_url):
        return True
    parts = [x for x in urlsplit(url).path.lower().split("/") if x]
    return len(parts) <= 1 and (not parts or parts[0] in HOMEPAGE_PATHS
                                or re.fullmatch(r"index\.\w+", parts[0]) is not None)


def page_in_section(url: str, title: str, sections: list[str],
                    home_url: str | None = None) -> bool:
    """Does a page belong to one of `sections` (SECTION_STEMS names or "homepage")?"""
    if "homepage" in sections and is_homepage(url, home_url):
        return True
    return bool(set(sections_of(urlsplit(url).path, title)) & set(sections))
