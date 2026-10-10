import json
from pathlib import Path

import pytest

from backend.reasons import split_reason

PRE = Path(__file__).resolve().parents[2] / "data" / "precomputed" / "findings.json"


@pytest.mark.parametrize("status,reason,short", [
    ("not_checkable", "Code found related passages on 2 candidate page(s) but the LLM did not "
     "confirm the requirement there; a possible gap needs code-level evidence of absence, so "
     "this is left for review. Quote: x (keywords from hints: a, b)",
     "LLM did not confirm it; manual review needed."),
    ("not_checkable", "re-checked 2026-10-10 (0 page(s) re-fetched for missing link data): "
     "relevant section not reached (read 4 pages): no section page",
     "The relevant section of the site was not reached (4 pages read)."),
    ("not_checkable", "LLM timeout / rate limit: openai-compatible:api.groq.com: HTTP 429",
     "The LLM quota was exhausted or the call timed out; try again later."),
    ("not_checkable", "page needs JavaScript rendering; not available on this hosted demo (...)",
     "The page needs JavaScript rendering, which is not available on this hosted demo."),
    ("ok", "Code: link \"Kalkulyatorlar\" (https://x.uz/c/) found on https://x.uz/ (any page); "
     "anchor text quoted from the page. Presence only: whether the calculator shows the full "
     "cost of the loan (all interest and fees) is not verified.",
     "Found by code: the link \"Kalkulyatorlar\" is on the page. Presence only: whether the "
     "calculator shows the full cost of the loan (all interest and fees) is not verified."),
])
def test_short_reasons(status, reason, short):
    s, details = split_reason(status, reason)
    assert s == short
    assert details and "re-checked" not in s and "keywords from hints" not in s


def test_gap_short_is_the_pages_read_sentence_and_details_keep_the_technical_text():
    s, d = split_reason("possible_gap", "re-checked 2026-10-10 (0 page(s) re-fetched for "
                        "missing link data): No evidence found on 15 pages read. No page "
                        "matched the keywords (keywords from hints: garovdan ozod qilish)", 15)
    assert s == "No evidence found on 15 pages read."
    assert d.startswith("Re-checked on 2026-10-10 (0 page(s) re-fetched for missing link data).")
    assert "keywords from hints: garovdan ozod qilish" in d


def test_every_stored_finding_gets_a_short_human_reason():
    for run in json.loads(PRE.read_text(encoding="utf-8"))["runs"]:
        for f in run["findings"]:
            s, _ = split_reason(f["status"], f["reason"], f["pages_read"])
            assert 0 < len(s) <= 260, s
            for tech in ("keywords from hints", "re-checked", "stem(s)", "Code checked"):
                assert tech not in s, (f["requirement_id"], s)
