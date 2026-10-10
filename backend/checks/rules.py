"""Deterministic checks (no LLM): links and phone numbers found in the crawled pages.

Which rule a requirement uses, and all of its keywords, come from data/check_hints.yaml
(`rule:` and its parameters); nothing requirement-specific is hardcoded here.

Rules
- link:  a link whose anchor text or URL path matches `link_keywords` (word stems, Latin and
         Cyrillic, any word order) or whose host is in `link_domains`, on the pages named by
         `where` (homepage | section | any).
- phone: a call-centre number in the homepage text: +998 numbers, or a short number of
         4 digits starting with 1 near one of `phone_context` words.

Outcomes
- ok:            found on a `where` page and the anchor text (or number) is quoted verbatim
                 from that page's visible text.
- not_checkable: found only outside `where` (e.g. on an inner page for a homepage rule), or
                 found but nothing quotable, or no link data stored for the pages.
- possible_gap:  nothing found on the `where` pages that were read (code-level evidence of
                 absence; the runner still requires the relevant section to have been read).
"""

import re
from urllib.parse import urlsplit

from backend.checks.evidence import _Tokens, keyword_stems, min_quote_chars, normalize_ws
from backend.checks.types import CheckOutcome
from backend.crawl.sections import is_homepage, page_in_section
from backend.models import Page

PHONE_998 = re.compile(r"(?<![\d+])\+?\s?998[\s\-()]*\d{2}[\s\-()]*\d{3}[\s\-]*\d{2}[\s\-]*\d{2}"
                       r"(?!\d)")
SHORT_NUMBER = re.compile(r"(?<![\d.,:/\-])1\d{3}(?![\d.,:/]\d|\d)")


def _quote_around(text: str, needle: str) -> str | None:
    """A verbatim passage of the (whitespace-normalized) page text containing `needle`,
    widened by whole words to at least min_quote_chars characters."""
    t, n = normalize_ws(text), normalize_ws(needle)
    if not n:
        return None
    i = t.find(n)
    if i < 0:
        return None
    s, e = i, i + len(n)
    while e - s < min_quote_chars() + 8 and (s > 0 or e < len(t)):
        ns = t.rfind(" ", 0, max(0, s - 1))
        s = 0 if ns < 0 else ns + 1
        ne = t.find(" ", e + 1)
        e = len(t) if ne < 0 else ne
    return t[s:e].strip()


def _link_match(url: str, anchor: str, stems: list[list[str]], domains: list[str]
                ) -> str | None:
    """'anchor' if the link text names the topic (or the link goes to a listed domain),
    'url' if only its address does, None otherwise."""
    host = urlsplit(url).netloc.lower()
    if any(host == d or host.endswith("." + d) for d in domains):
        return "anchor"
    if any(_Tokens(anchor).find(s) is not None for s in stems):
        return "anchor"
    path = _Tokens(urlsplit(url).path.replace("/", " ").replace("-", " ").replace("_", " "))
    return "url" if any(path.find(s) is not None for s in stems) else None


def _where_pages(pages: list[Page], where: str, sections: list[str]) -> list[Page]:
    home = pages[0].url if pages else None
    if where == "homepage":
        return [p for p in pages if is_homepage(p.url, home)]
    if where == "section":
        return [p for p in pages if page_in_section(p.url, p.title, sections, home)]
    return list(pages)


def _no_evidence(pages: list[Page], checked: list[Page], what: str) -> CheckOutcome:
    return CheckOutcome(
        "possible_gap", page=checked[0], absence=True,
        reason=f"No evidence found on {len(pages)} pages read. Code checked {what} on "
               f"{len(checked)} page(s) ({', '.join(p.url for p in checked[:3])}"
               f"{', ...' if len(checked) > 3 else ''}): nothing matched.")


def check_link(pages: list[Page], rule: dict, sections: list[str]) -> CheckOutcome:
    readable = [p for p in pages if p.readable]
    where = rule.get("where", "any")
    named_stems = [(k, keyword_stems(k)) for k in rule.get("link_keywords") or []]
    named_stems = [(k, st) for k, st in named_stems if st]
    stems = [st for _, st in named_stems]
    domains = [d.lower() for d in rule.get("link_domains") or []]
    if not stems and not domains:
        return CheckOutcome("not_checkable", reason="rule 'link' has no link_keywords or "
                                                    "link_domains in data/check_hints.yaml")
    targets = _where_pages(readable, where, sections)
    if not targets:
        return CheckOutcome("not_checkable", reason=f"relevant section not reached (read "
                                                    f"{len(readable)} pages): no {where} page")
    if not any(p.links for p in readable):
        return CheckOutcome("not_checkable", reason="no link data stored for the pages read; "
                                                    "re-crawl the site")
    found_elsewhere, unquotable, by_url = None, None, None
    target_urls = {p.url for p in targets}
    for p in sorted(readable, key=lambda p: p.url not in target_urls):
        kinds = [(u, a, _link_match(u, a, stems, domains)) for u, a in p.links]
        # Shortest anchors first: navigation items, not long teaser texts.
        named = sorted(((u, a) for u, a, k in kinds if k == "anchor"),
                       key=lambda x: (len(x[1]) == 0, len(x[1])))
        if p.url not in target_urls:
            if named and found_elsewhere is None:
                found_elsewhere = (p, named[0][1])
            continue
        by_url = by_url or next(((p, u, a) for u, a, k in kinds if k == "url"), None)
        for u, anchor in named:
            quote = _quote_around(p.text, anchor) if anchor else None
            if quote:
                note = f" {rule['ok_note']}" if rule.get("ok_note") else ""
                return CheckOutcome("ok", page=p, quote=quote,
                                    reason=f"Code: link \"{anchor}\" ({u}) found on {p.url} "
                                           f"({where} page); anchor text quoted from the page."
                                           + note)
        if named:
            unquotable = unquotable or (p, named[0][0])
    if unquotable:
        p, u = unquotable
        return CheckOutcome("not_checkable", page=p,
                            reason=f"Code: a matching link ({u}) is on {p.url} but its text is "
                                   "not in the visible page text (icon or image link?); "
                                   "check manually.")
    if found_elsewhere:
        p, a = found_elsewhere
        return CheckOutcome("not_checkable", page=p,
                            reason=f"Code: matching link \"{a}\" found on {p.url}, which is "
                                   f"not a {where} page; the requirement names the {where}, so "
                                   "check it manually.")
    if by_url:
        p, u, a = by_url
        return CheckOutcome("not_checkable", page=p,
                            reason=f"Code: a link on {p.url} goes to {u}, whose address matches, "
                                   f"but its text \"{a or 'no text'}\" does not name the topic; "
                                   "check manually.")
    for p in targets:  # the words are on the page, but not as a link the crawler could read
        words = _Tokens(p.text)
        hit = next((k for k, st in named_stems if words.find(st) is not None), None)
        if hit:
            return CheckOutcome("not_checkable", page=p,
                                reason=f"Code: \"{hit}\" appears in the text of {p.url} but "
                                       "not as a link the crawler could read (a button or "
                                       "script?); check manually.")
    what = ("links matching " + ", ".join(rule.get("link_keywords") or [])
            + (f" or linking to {', '.join(domains)}" if domains else ""))
    return _no_evidence(readable, targets, what)


def check_phone(pages: list[Page], rule: dict, sections: list[str]) -> CheckOutcome:
    readable = [p for p in pages if p.readable]
    targets = _where_pages(readable, rule.get("where", "homepage"), sections)
    if not targets:
        return CheckOutcome("not_checkable", reason=f"relevant section not reached (read "
                                                    f"{len(readable)} pages): no homepage")
    context = [s for s in (keyword_stems(k) for k in rule.get("phone_context") or []) if s]

    def number_in(p: Page) -> str | None:
        t = normalize_ws(p.text)
        m = PHONE_998.search(t)
        if m:
            return m.group().strip()
        for m in SHORT_NUMBER.finditer(t):
            near = _Tokens(t[max(0, m.start() - 60):m.end() + 60])
            if any(near.find(s) is not None for s in context):
                return m.group()
        return None

    for p in targets:
        number = number_in(p)
        quote = _quote_around(p.text, number) if number else None
        if quote:
            return CheckOutcome("ok", page=p, quote=quote,
                                reason=f"Code: call-centre number {number} found in the text "
                                       f"of the homepage {p.url}.")
    target_urls = {p.url for p in targets}
    for p in readable:  # audit B2: found only on an inner page -> not ok, not a gap
        number = None if p.url in target_urls else number_in(p)
        if number:
            return CheckOutcome("not_checkable", page=p, quote=_quote_around(p.text, number),
                                reason=f"Code: number {number} found on {p.url}, an inner page, "
                                       "but not in the homepage text read; the requirement "
                                       "names the homepage, so check it manually.")
    return _no_evidence(readable, targets, "for +998 numbers and short 1xxx numbers near "
                                           + ", ".join(rule.get("phone_context") or []))


RULES = {"link": check_link, "phone": check_phone}


def run_rule(rule: dict, pages: list[Page], sections: list[str]) -> CheckOutcome:
    fn = RULES.get(rule.get("kind", ""))
    if fn is None:
        return CheckOutcome("not_checkable", reason=f"unknown rule {rule.get('kind')!r} in "
                                                    "data/check_hints.yaml")
    return fn(pages, rule, sections)
