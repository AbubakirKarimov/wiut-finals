"""uz_version: deterministic, no LLM. Does the site have an Uzbek (state language) version?

Counts Uzbek (Latin or Cyrillic) vs Russian HTML pages among the pages read and records
whether a language switcher was found. Rules:
- no Uzbek or Russian page read                -> not_checkable
- no Uzbek page at all, Russian pages present  -> possible_gap (quote: a Russian page)
- UZ_VERSION_MIN_SHARE set and the Uzbek share is below it -> possible_gap
- otherwise                                    -> ok (quote: an Uzbek page); the
  explanation says "N Uzbek pages of M; completeness not assessed" (audit B8)
The runner downgrades possible_gap to not_checkable when too few pages were read.
"""

import os

from backend.checks.evidence import opening_quote
from backend.checks.types import CheckOutcome
from backend.models import Page, Requirement

UZ = {"uz_latn", "uz_cyrl"}


def check_uz_version(req: Requirement, pages: list[Page],
                     has_language_switcher: bool | None) -> CheckOutcome:
    html = [p for p in pages if p.source_type == "html" and p.readable]
    uz = [p for p in html if p.language in UZ]
    ru = [p for p in html if p.language == "ru"]
    switcher = {True: "language switcher found", False: "no language switcher found",
                None: "language switcher: no data"}[has_language_switcher]
    if not uz and not ru:
        return CheckOutcome("not_checkable",
                            reason=f"no Uzbek or Russian pages among {len(html)} HTML pages read")
    share = len(uz) / (len(uz) + len(ru))
    stats = (f"{len(uz)} Uzbek and {len(ru)} Russian pages of {len(html)} HTML pages read "
             f"(Uzbek share {share:.0%}); {switcher}")
    if not uz:
        return CheckOutcome("possible_gap", page=ru[0], quote=opening_quote(ru[0].text),
                            reason=f"no Uzbek-language page found: {stats}")
    raw_min = os.getenv("UZ_VERSION_MIN_SHARE", "").strip()
    if raw_min and ru and share < float(raw_min):
        return CheckOutcome("possible_gap", page=ru[0], quote=opening_quote(ru[0].text),
                            reason=f"Uzbek share below UZ_VERSION_MIN_SHARE={raw_min}: {stats}")
    # An Uzbek version exists; whether every key page has an Uzbek counterpart is not checked.
    return CheckOutcome("ok", page=uz[0], quote=opening_quote(uz[0].text),
                        reason=f"Uzbek version present ({len(uz)} Uzbek pages of {len(html)}; "
                               f"completeness not assessed): {stats}")
