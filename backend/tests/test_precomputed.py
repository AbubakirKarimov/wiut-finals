import json

from fastapi.testclient import TestClient

from backend import db, precomputed
from backend.models import Finding, Page, Requirement, Run, utcnow


def seed(conn):
    db.upsert_requirement(conn, Requirement(
        id="req:a", text_original="t", text_en="e", source_doc="d", source_clause_id="c",
        source_url="https://lex.uz/x", check_type="key_info", approved=True))
    db.upsert_run(conn, Run(id="r1", bank_id="mkbank", start_url="https://mkbank.uz/uz/",
                            source="batch", status="done", crawl_status="ok", pages_read=15,
                            finished_at=utcnow()))
    db.upsert_finding(conn, Finding(
        id="r1:req:a", bank_id="mkbank", requirement_id="req:a", status="possible_gap",
        run_id="r1", evidence_url="https://mkbank.uz/uz/", evidence_quote="Bank xizmatlari",
        evidence_quote_en="Bank services", pages_read=15, urls_read=["https://mkbank.uz/uz/"]))
    db.upsert_page(conn, Page(bank_id="mkbank", url="https://mkbank.uz/uz/",
                                 language="uz_latn", text="SECRET FULL PAGE TEXT",
                                 source_type="html", run_id="r1"))
    token = db.current_run_id.set("r1")
    db.log_llm_call(conn, provider="openai-compatible:api.example", model="m1",
                    input_tokens=10, output_tokens=5, duration_ms=1, ok=True, cache_hit=False)
    db.current_run_id.reset(token)


def test_export_has_no_page_text_and_loads_into_empty_db(tmp_db, tmp_path):
    out = tmp_path / "findings.json"
    with db.connect(tmp_db) as conn:
        seed(conn)
    data = precomputed.export(out, db_path=tmp_db)
    raw = out.read_text(encoding="utf-8")
    assert "SECRET FULL PAGE TEXT" not in raw
    [run] = data["runs"]
    [f] = run["findings"]
    assert f["model"] == "openai-compatible:api.example/m1" and f["urls_read"]
    assert {"bank_id", "finished_at", "models"} <= run.keys()

    fresh = tmp_path / "fresh.sqlite"
    db.init_db(fresh)
    assert precomputed.load_if_empty(out, db_path=fresh) == 1
    assert precomputed.load_if_empty(out, db_path=fresh) == 0   # not empty any more
    with db.connect(fresh) as conn:
        [g] = db.list_findings(conn)
        assert db.get_run(conn, "r1").source == "precomputed"
        assert db.list_pages(conn, "mkbank") == []
    assert g.evidence_quote == "Bank xizmatlari" and g.status == "possible_gap"


def test_api_startup_loads_precomputed(tmp_db, tmp_path, monkeypatch):
    out = tmp_path / "findings.json"
    with db.connect(tmp_db) as conn:
        seed(conn)
    precomputed.export(out, db_path=tmp_db)
    fresh = tmp_path / "api.sqlite"
    monkeypatch.setenv("DB_PATH", str(fresh))
    monkeypatch.setenv("PRECOMPUTED_PATH", str(out))
    from backend.api.main import app
    with TestClient(app) as client:
        rows = client.get("/findings").json()
    assert len(rows) == 1 and rows[0]["run"]["source"] == "precomputed"
    assert rows[0]["run"]["finished_at"] and rows[0]["evidence_quote_en"] == "Bank services"
    json.loads(out.read_text(encoding="utf-8"))
