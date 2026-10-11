"""Findings by status on the Audit screen: each bank's latest run, not all stored runs."""

from datetime import datetime, timedelta, timezone

from backend import db, metrics
from backend.models import Finding, Requirement, Run


def test_findings_by_status_latest_counts_only_the_latest_run_per_bank(tmp_db):
    t0 = datetime(2026, 10, 10, tzinfo=timezone.utc)
    with db.connect() as conn:
        db.upsert_requirement(conn, Requirement(
            id="req:x", text_original="x", text_en="x", source_doc="law_state_language",
            source_clause_id="law_state_language:art:20", source_url="https://lex.uz/x",
            check_type="uz_version", approved=True))
        for rid, bank, when, status in [("old", "a", t0, "possible_gap"),
                                        ("new", "a", t0 + timedelta(hours=1), "ok"),
                                        ("b1", "b", t0, "not_checkable")]:
            db.upsert_run(conn, Run(id=rid, bank_id=bank, start_url=f"https://{bank}.example/",
                                    source="batch", status="done", started_at=when,
                                    finished_at=when))
            db.upsert_finding(conn, Finding(
                id=f"{rid}:req:x", bank_id=bank, requirement_id="req:x", status=status,
                run_id=rid, reason="r", pages_read=1, urls_read=[], created_at=when))
        m = metrics.compute(conn)
    assert m["findings_by_status"] == {"ok": 1, "possible_gap": 1, "not_checkable": 1}
    assert m["findings_by_status_latest"] == {"ok": 1, "possible_gap": 0, "not_checkable": 1,
                                              "banks": 2, "findings": 2}
