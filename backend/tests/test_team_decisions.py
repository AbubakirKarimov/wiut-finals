import json
from datetime import datetime, timezone

from fastapi.testclient import TestClient

from backend import db, metrics, team_decisions
from backend.models import Decision, Finding, Run


def seed(conn, n_gaps=6, source="batch"):
    now = datetime(2026, 10, 10, 12, tzinfo=timezone.utc)
    db.upsert_run(conn, Run(id="r1", bank_id="b", start_url="https://b.uz/", status="done",
                            source=source, started_at=now, finished_at=now))
    for i in range(n_gaps):
        db.upsert_finding(conn, Finding(id=f"r1:q{i}", bank_id="b", requirement_id=f"q{i}",
                                        status="possible_gap", run_id="r1", decided_by="code"))


def test_export_then_load_into_a_fresh_db(tmp_db, tmp_path):
    with db.connect(tmp_db) as conn:
        seed(conn)
        for i in range(6):
            db.add_decision(conn, Decision(
                finding_id=f"r1:q{i}", analyst="T. Analyst",
                verdict="confirmed" if i < 4 else "rejected", comment=f"c{i}",
                decided_at=datetime(2026, 10, 11, 9, i, tzinfo=timezone.utc)))
    out = tmp_path / "decisions.json"
    data = team_decisions.export(out, db_path=tmp_db)
    assert data["n"] == 6 and data["authors"] == ["T. Analyst"]
    assert data["reviewed_on"].startswith("2026-10-11")
    assert json.loads(out.read_text())["decisions"][0]["comment"] == "c0"

    fresh = tmp_path / "fresh.sqlite"
    db.init_db(fresh)
    with db.connect(fresh) as conn:
        seed(conn, source="precomputed")
    assert team_decisions.load(out, db_path=fresh)["loaded"] == 6
    assert team_decisions.load(out, db_path=fresh)["skipped_existing"] == 6   # idempotent
    with db.connect(fresh) as conn:
        assert {r["source"] for r in conn.execute("SELECT source FROM decisions")} == {"team"}
        review = metrics.team_review(conn)
    assert review["label"] == "4 of 6 confirmed (reviewed by team on 2026-10-11)"


def test_team_review_not_enough_data_and_live_decisions_ignored(tmp_db):
    with db.connect(tmp_db) as conn:
        seed(conn)
        for i in range(4):
            db.add_decision(conn, Decision(finding_id=f"r1:q{i}", analyst="a",
                                           verdict="confirmed", source="team"))
        db.add_decision(conn, Decision(finding_id="r1:q5", analyst="a", verdict="confirmed"))
        r = metrics.team_review(conn)
    assert r["n"] == 4 and r["label"] == "not enough data"


def test_missing_file_and_unknown_findings(tmp_db, tmp_path):
    assert team_decisions.load(tmp_path / "none.json", db_path=tmp_db)["file"] is False
    f = tmp_path / "d.json"
    f.write_text(json.dumps({"decisions": [{"finding_id": "nope", "analyst": "a",
                                            "verdict": "confirmed",
                                            "decided_at": "2026-10-11T00:00:00+00:00"}]}))
    assert team_decisions.load(f, db_path=tmp_db)["skipped_no_finding"] == 1


def test_live_decision_labelled_when_storage_is_ephemeral(tmp_db, monkeypatch):
    from backend.api import main
    with db.connect(tmp_db) as conn:
        seed(conn)
    monkeypatch.setenv("LIVE_DECISIONS_EPHEMERAL", "1")
    with TestClient(main.app) as c:
        d = c.post("/decisions", json={"finding_id": "r1:q0", "analyst": "A",
                                       "verdict": "confirmed"}).json()
        assert d["source"] == "live"
        assert d["storage_note"] == "live session, may reset on restart"
        assert c.get("/decisions").json()[0]["storage_note"] == d["storage_note"]
    monkeypatch.setenv("LIVE_DECISIONS_EPHEMERAL", "0")
    with TestClient(main.app) as c:
        assert c.get("/decisions").json()[0]["storage_note"] is None
