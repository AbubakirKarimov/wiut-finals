"""HTML -> visible text, page language, bot-challenge markers and language-switcher links."""

import re
from urllib.parse import parse_qs, urljoin, urlsplit

from bs4 import BeautifulSoup

BLOCK_STATUSES = {403, 429, 503}
CHALLENGE_MARKERS = ("just a moment", "cf-chl", "captcha", "access denied",
                     "attention required", "checking your browser", "ddos-guard")


def soup_of(html: str) -> BeautifulSoup:
    return BeautifulSoup(html, "lxml")


def visible_text(html: str) -> str:
    soup = soup_of(html)
    for tag in soup(["script", "style", "noscript", "template", "svg", "head"]):
        tag.decompose()
    return normalize_ws(soup.get_text(" "))


def normalize_ws(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def page_title(html: str) -> str:
    soup = soup_of(html)
    return normalize_ws(soup.title.get_text()) if soup.title else ""


UZ_CYRL_LETTERS = set("ўқғҳЎҚҒҲ")
RU_ONLY_LETTERS = set("ыщЫЩ")
UZ_LATN_WORDS = {"va", "uchun", "bilan", "yoki", "bo'yicha", "haqida", "mumkin", "sizning",
                 "kredit", "to'lov", "hisob", "omonat", "bank", "barcha", "xizmatlar",
                 "kartasi", "orqali", "bo'lim", "yangiliklar", "biz", "ham", "bo'lgan"}
EN_WORDS = {"the", "and", "for", "of", "to", "your", "with", "our", "about", "news"}


def detect_language(text: str) -> str | None:
    """Dominant language of a text: uz_latn | uz_cyrl | ru | other; None if no letters.

    Cyrillic: Uzbek-only letters (ў қ ғ ҳ) vs Russian-only letters (ы щ).
    Latin: frequent Uzbek words vs frequent English words.
    """
    cyr = sum(1 for c in text if "Ѐ" <= c <= "ӿ")
    lat = sum(1 for c in text if c.isascii() and c.isalpha())
    if cyr + lat == 0:
        return None
    if cyr >= lat:
        uz = sum(1 for c in text if c in UZ_CYRL_LETTERS)
        ru = sum(1 for c in text if c in RU_ONLY_LETTERS)
        return "uz_cyrl" if uz > ru else "ru"
    words = re.findall(r"[a-zʻ'’`]+", text.lower())
    norm = [re.sub(r"[ʻ’`]", "'", w) for w in words]
    uz = sum(1 for w in norm if w in UZ_LATN_WORDS)
    en = sum(1 for w in norm if w in EN_WORDS)
    return "uz_latn" if uz > en else "other"


def challenge_marker(html: str) -> str | None:
    low = html.lower()
    return next((m for m in CHALLENGE_MARKERS if m in low), None)


def classify(status: int | None, html: str, text_len: int, min_text_chars: int) -> str:
    """ok | js_shell | blocked | unreachable | other.

    Challenge markers only count on an error status or a near-empty page: a normal home
    page may legitimately load a reCAPTCHA script."""
    if status is None:
        return "unreachable"
    if status in BLOCK_STATUSES:
        return "blocked"
    if status == 200:
        if text_len < min_text_chars:
            return "blocked" if challenge_marker(html) else "js_shell"
        return "ok"
    return "other"


# --- language switcher links ---

# Path segment / query value / hreflang -> language key.
LANG_CODES = {
    "uz": "uz", "uz-latn": "uz", "uz_latn": "uz", "oz": "uz_cyrl", "uz-cyrl": "uz_cyrl",
    "uz_cyrl": "uz_cyrl", "kr": "uz_cyrl", "cyrl": "uz_cyrl", "ru": "ru", "ru-ru": "ru",
    "en": "en", "en-us": "en",
}
# Visible anchor text of a switcher -> language key.
LANG_ANCHORS = {
    "uz": "uz", "o'z": "uz", "oʻz": "uz", "o‘z": "uz", "uzb": "uz", "o'zbekcha": "uz",
    "oʻzbekcha": "uz", "o‘zbekcha": "uz", "ўз": "uz_cyrl", "ўзб": "uz_cyrl",
    "ўзбекча": "uz_cyrl", "оз": "uz_cyrl", "ru": "ru", "рус": "ru", "ру": "ru",
    "русский": "ru", "en": "en", "eng": "en", "english": "en",
}


def same_site(a: str, b: str) -> bool:
    ha, hb = urlsplit(a).hostname or "", urlsplit(b).hostname or ""
    strip = lambda h: h[4:] if h.startswith("www.") else h  # noqa: E731
    return strip(ha) == strip(hb)


def _lang_of_url(url: str) -> str | None:
    p = urlsplit(url)
    seg = p.path.strip("/").split("/")[0].lower() if p.path.strip("/") else ""
    if seg in LANG_CODES:
        return LANG_CODES[seg]
    for key in ("lang", "language", "locale", "hl"):
        vals = parse_qs(p.query).get(key)
        if vals and vals[0].lower() in LANG_CODES:
            return LANG_CODES[vals[0].lower()]
    return None


def language_links(html: str, base_url: str) -> dict[str, str]:
    """Links to other language versions of the site: {lang key: absolute URL}.

    Sources: <link hreflang>, <a hreflang>, anchors whose text is a language label, and
    same-site links whose first path segment or ?lang= is a language code (only when the
    anchor text is short, as in a switcher)."""
    soup = soup_of(html)
    found: dict[str, str] = {}

    def add(lang: str | None, href: str | None) -> None:
        if not lang or not href or href.startswith(("javascript:", "mailto:", "tel:")):
            return
        url = urljoin(base_url, href).split("#")[0]
        if url.startswith(("http://", "https://")) and same_site(url, base_url):
            found.setdefault(lang, url)

    for tag in soup.find_all(["link", "a"], hreflang=True):
        add(LANG_CODES.get(tag["hreflang"].lower()), tag.get("href"))
    for a in soup.find_all("a", href=True):
        label = normalize_ws(a.get_text(" ")).lower().strip(" |/")
        if label in LANG_ANCHORS:
            add(LANG_ANCHORS[label], a["href"])
        elif len(label) <= 12:
            add(_lang_of_url(urljoin(base_url, a["href"])), a["href"])
    return found


def links(html: str, base_url: str) -> list[tuple[str, str]]:
    """All http(s) links on the page as (absolute URL without fragment, anchor text)."""
    out = []
    for a in soup_of(html).find_all("a", href=True):
        href = a["href"].strip()
        if href.startswith(("javascript:", "mailto:", "tel:", "#")):
            continue
        url = urljoin(base_url, href).split("#")[0]
        if url.startswith(("http://", "https://")):
            out.append((url, normalize_ws(a.get_text(" "))[:120]))
    return out
