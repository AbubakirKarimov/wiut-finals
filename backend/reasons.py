"""Split a finding's stored reason into a short human sentence and technical details.

Display only: the stored `reason` is unchanged (and stays in the audit log). The short text
is one or two plain sentences; the details keep everything technical (keyword lists from
data/check_hints.yaml, "re-checked <date> (...)" notes, stem counts, page lists).
"""

import re

RECHECK = re.compile(r"^re-checked (\d{4}-\d{2}-\d{2}) \((.*?)\):\s*")

# (pattern on the reason, short text). Short texts may use groups of the match.
_PATTERNS: list[tuple[re.Pattern, str]] = [(re.compile(p, re.I | re.S), t) for p, t in [
    (r"page needs JavaScript rendering",
     "The page needs JavaScript rendering, which is not available on this hosted demo."),
    (r"homepage text too short \((\d+) chars\)",
     "The homepage had too little text ({0} characters), likely dynamic content or a block, "
     "so no gap is reported."),
    (r"relevant section not reached: only the section index",
     "Only the deposits overview page was read, no deposit product page; manual review "
     "needed."),
    (r"relevant section not reached \(read (\d+) pages\)",
     "The relevant section of the site was not reached ({0} pages read)."),
    (r"^only (\d+) page\(s\) read",
     "Too few pages were read ({0}) to report a possible gap."),
    (r"^site had (\d+) fetch error",
     "Some pages failed to load, so no possible gap is reported."),
    (r"LLM timeout / rate limit",
     "The LLM quota was exhausted or the call timed out; try again later."),
    (r"LLM did not confirm the requirement",
     "LLM did not confirm it; manual review needed."),
    (r"repeats our own instructions|quote was not found verbatim|answer rejected",
     "The LLM's answer was rejected because its quote is not on the page; manual review "
     "needed."),
    (r"evidence quote not found verbatim",
     "The quote could not be verified on the page; manual review needed."),
    (r"links the law, not the Agency",
     "The page links the law, not the Deposit Guarantee Agency; manual review needed."),
    (r"appears in the text of .* but not as a link",
     "The words are on the page, but not as a link the crawler could read; manual review "
     "needed."),
    (r"inner page|which is not a homepage page",
     "Found on an inner page, not on the homepage; manual review needed."),
    (r"text is not in the visible page text|does not name the topic",
     "A matching link was found, but its text cannot be quoted; manual review needed."),
    (r"no link data",
     "No link data was stored for these pages; the site needs to be crawled again."),
    (r"LLM not configured",
     "The LLM is not configured on this server, so this check could not run."),
    (r"bot protection|blocked",
     "The site blocked the crawler; protection was not bypassed."),
    (r"robots",
     "The site's robots.txt does not allow the crawler."),
    (r"unreachable|timed out|connection",
     "The site could not be reached."),
    (r"needs browser|stayed nearly empty",
     "The site needs a browser to show its content."),
    (r"^Code: link \"([^\"]*)\"",
     "Found by code: the link \"{0}\" is on the page."),
    (r"^Code: call-centre number (.+?) found",
     "Found by code: call-centre number {0} on the homepage."),
    (r"^Uzbek version present \((\d+) Uzbek pages of (\d+); completeness not assessed\)",
     "Uzbek version present ({0} Uzbek pages of {1}; completeness not assessed)."),
    (r"^LLM: present, quote verified",
     "Confirmed with LLM assistance; the quote was verified on the page by code."),
    (r"no Uzbek-language page found",
     "No Uzbek-language page was found among the pages read."),
]]


def split_reason(status: str, reason: str | None, pages_read: int | None = None
                 ) -> tuple[str, str | None]:
    """(reason_short, reason_details). Details are None when there is nothing more."""
    if not reason:
        return "No reason recorded.", None
    notes, body = [], reason
    m = RECHECK.match(body)
    if m:
        notes.append(f"Re-checked on {m.group(1)} ({m.group(2)}).")
        body = body[m.end():]
    if status == "possible_gap":
        n = pages_read if pages_read is not None else "no data"
        short = f"No evidence found on {n} pages read."
    else:
        short = None
        for pattern, text in _PATTERNS:
            hit = pattern.search(body)
            if hit:
                short = text.format(*hit.groups())
                break
        if short is None:  # unknown wording: first sentence, the rest goes to details
            first = re.split(r"(?<=[.!?])\s", body, maxsplit=1)[0]
            short = first if len(first) <= 200 else first[:197].rsplit(" ", 1)[0] + "..."
        caveat = re.search(r"[^.]*\bis not verified\.", body)
        if status == "ok" and caveat:  # what the code did NOT check stays visible
            short += " " + caveat.group().strip()
    details = " ".join(notes + ([body] if body.strip() and body.strip() != short else []))
    return short, (details or None)
