import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from backend import db
from backend.api.main import app
from backend.models import Decision, Finding, Job, Page, Requirement


def test_health(tmp_db):
    with TestClient(app) as client:
        resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_finding_status_rejects_violation():
    with pytest.raises(ValidationError):
        Finding(id="f1", bank_id="b", requirement_id="r", status="violation")


def test_confidence_bounds():
    with pytest.raises(ValidationError):
        Finding(id="f1", bank_id="b", requirement_id="r", status="ok", confidence=1.5)


def test_db_roundtrip(tmp_db):
    req = Requirement(id="r1", text_original="Банк обязан...", text_en="The bank must...",
                      source_doc="d", source_clause_id="c1",
                      source_url="https://lex.uz/x", check_type="key_info")
    page = Page(bank_id="b1", url="https://bank.uz/", language="ru", text="hello",
                source_type="html")
    finding = Finding(id="f1", bank_id="b1", requirement_id="r1", status="possible_gap",
                      evidence_url=page.url, evidence_quote="hello",
                      evidence_quote_en="hello (mt)", confidence=0.7)
    with db.connect(tmp_db) as conn:
        db.upsert_requirement(conn, req)
        db.upsert_page(conn, page)
        db.upsert_finding(conn, finding)
        db.add_decision(conn, Decision(finding_id="f1", analyst="a", verdict="confirmed"))
        db.upsert_job(conn, Job(id="j1", url="https://bank.uz/"))

    with db.connect(tmp_db) as conn:
        assert db.list_requirements(conn) == [req]
        assert db.list_requirements(conn, approved_only=True) == []
        assert db.list_pages(conn, "b1")[0].text == "hello"
        assert db.get_finding(conn, "f1").status == "possible_gap"
        assert db.get_finding(conn, "f1").evidence_quote_en == "hello (mt)"
        assert db.list_decisions(conn)[0].verdict == "confirmed"
        assert db.get_job(conn, "j1").status == "queued"


def test_llm_cache_and_log(tmp_db):
    key = db.llm_cache_key("p", "m", "prompt", {"type": "object"})
    assert key == db.llm_cache_key("p", "m", "prompt", {"type": "object"})
    assert key != db.llm_cache_key("p", "m2", "prompt", {"type": "object"})
    with db.connect(tmp_db) as conn:
        assert db.llm_cache_get(conn, key) is None
        db.llm_cache_put(conn, key, "p", "m", {"present": True, "quote": "Ўзбек"})
        db.log_llm_call(conn, provider="p", model="m", input_tokens=None, output_tokens=None,
                        duration_ms=0.4, ok=True, cache_hit=True)
    with db.connect(tmp_db) as conn:
        assert db.llm_cache_get(conn, key) == {"present": True, "quote": "Ўзбек"}
        row = conn.execute("SELECT cache_hit FROM llm_calls").fetchone()
        assert row["cache_hit"] == 1
