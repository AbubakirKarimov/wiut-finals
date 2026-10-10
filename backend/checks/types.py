from dataclasses import dataclass

from backend.models import Page


@dataclass
class CheckOutcome:
    """Result of one check before gating, quote verification and translation."""
    status: str                 # ok | possible_gap | not_checkable
    reason: str = ""
    page: Page | None = None    # page the quote comes from
    quote: str | None = None    # must appear verbatim in page.text (verified by the runner)
    llm_used: bool = False
