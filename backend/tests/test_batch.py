from backend import db
from backend.batch import markdown_table, summarize, text_table
from backend.models import Finding, Run, utcnow


def test_summary_rows_from_stored_runs(tmp_db, monkeypatch):
    monkeypatch.setenv("LLM_BASE_URL", "https://api.example/v1")
    monkeypatch.setenv("LLM_MODEL", "m")
    monkeypatch.setenv("LLM_API_KEY", "k")
    monkeypatch.setenv("LLM_PRICE_INPUT_PER_MTOK", "1.0")
    monkeypatch.setenv("LLM_PRICE_OUTPUT_PER_MTOK", "2.0")
    with db.connect(tmp_db) as conn:
        db.upsert_run(conn, Run(id="r1", bank_id="a", start_url="https://a.uz/", source="batch",
                                status="done", crawl_status="ok", pages_read=15,
                                finished_at=utcnow()))
        db.upsert_run(conn, Run(id="r2", bank_id="b", start_url="https://b.uz/", source="batch",
                                status="done", crawl_status="js_shell_failed",
                                crawl_reason="needs browser", finished_at=utcnow()))
        db.upsert_finding(conn, Finding(id="f1", bank_id="a", requirement_id="x",
                                        status="possible_gap", run_id="r1"))
        db.upsert_finding(conn, Finding(id="f2", bank_id="b", requirement_id="x",
                                        status="not_checkable", run_id="r2"))
        token = db.current_run_id.set("r1")
        db.log_llm_call(conn, provider="openai-compatible:api.example", model="m",
                        input_tokens=1000, output_tokens=500, duration_ms=1, ok=True,
                        cache_hit=False)
        db.log_llm_call(conn, provider="openai-compatible:api.example", model="m",
                        input_tokens=None, output_tokens=None, duration_ms=1, ok=True,
                        cache_hit=True)
        db.current_run_id.reset(token)
        rows = summarize(conn, ["r1", "r2"])
    a, b = rows
    assert a["possible_gap"] == 1 and a["tokens"] == 1500 and a["cache_hits"] == 1
    assert a["cost_usd"] == round(1000 / 1e6 * 1.0 + 500 / 1e6 * 2.0, 6)
    assert b["crawl"] == "skipped: js_shell_failed" and b["reason"] == "needs browser"
    assert "TOTAL" in text_table(rows) and "needs browser" in markdown_table(rows)
