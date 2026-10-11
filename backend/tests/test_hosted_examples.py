"""Hosted-demo examples (data/hosted_examples.json) and the JS-only job fields."""

import json

import httpx

from backend import hosted_examples
from backend.crawl.banks import Bank
from backend.crawl.fetch import FetchConfig, Fetcher

LONG = "<html><body><p>" + "Bank xizmatlari haqida batafsil ma'lumot. " * 60 + "</p></body></html>"
SHORT = "<html><body><p>" + "Bank. " * 120 + "</p></body></html>"
SHELL = "<html><body><div id=root></div><script src=app.js></script></body></html>"


def _fetcher():
    pages = {"/": LONG, "/short": SHORT, "/shell": SHELL}

    def handler(req: httpx.Request) -> httpx.Response:
        if req.url.path == "/robots.txt":
            return httpx.Response(404)
        return httpx.Response(200, text=pages[req.url.path],
                              headers={"content-type": "text/html; charset=utf-8"})
    return Fetcher(FetchConfig(min_delay_seconds=0, browser_fallback=False),
                   transport=httpx.MockTransport(handler))


def test_measure_uses_threshold_and_classification(tmp_path):
    banks = [Bank(id=i, name=i, website_url=u, role="partner") for i, u in [
        ("long", "https://a.example/"), ("short", "https://b.example/short"),
        ("shell", "https://c.example/shell"), ("empty", "")]]
    rows = hosted_examples.measure(banks, _fetcher(), threshold=1500, min_text_chars=500)
    by = {r["bank_id"]: r for r in rows}
    assert set(by) == {"long", "short", "shell"}  # no URL -> not measured
    assert by["long"]["works_on_hosted"] and by["long"]["text_chars"] >= 1500
    assert by["short"]["classification"] == "ok" and not by["short"]["works_on_hosted"]
    assert by["shell"]["classification"] == "js_shell" and not by["shell"]["works_on_hosted"]
    path = tmp_path / "h.json"
    hosted_examples.write(rows, 1500, path)
    loaded = hosted_examples.load(path)
    assert loaded["long"]["works_on_hosted"] and loaded["long"]["measured_at"]
    assert json.loads(path.read_text())["homepage_min_chars"] == 1500


def test_missing_file_means_no_examples(tmp_path):
    assert hosted_examples.load(tmp_path / "missing.json") == {}


def test_committed_examples_exclude_js_only_sites():
    data = hosted_examples.load()
    assert data, "data/hosted_examples.json is missing"
    for r in data.values():
        if r["classification"] != "ok":
            assert not r["works_on_hosted"]


def test_job_reports_precomputed_results_for_the_same_bank(tmp_db):
    """The JS-only message links to the Findings tab only when stored (pre-computed) results
    exist for the job's bank; the crawl reason names no env var."""
    from datetime import datetime, timezone

    from fastapi.testclient import TestClient

    from backend import db
    from backend.api import main
    from backend.models import Finding, Job, Requirement, Run

    when = datetime(2026, 10, 10, tzinfo=timezone.utc)
    with db.connect() as conn:
        db.upsert_requirement(conn, Requirement(
            id="req:x", text_original="x", text_en="x", source_doc="law_state_language",
            source_clause_id="law_state_language:art:20", source_url="https://lex.uz/x",
            check_type="uz_version", approved=True))
        for bank, src in [("js_bank", "precomputed"), ("js_bank", "job"), ("new_bank", "job")]:
            rid = f"{src}-{bank}"
            db.upsert_run(conn, Run(id=rid, bank_id=bank, start_url=f"https://{bank}.example/",
                                    source=src, status="done", crawl_status="needs_browser",
                                    crawl_reason="page needs JavaScript rendering",
                                    started_at=when, finished_at=when))
            if src == "precomputed":
                db.upsert_finding(conn, Finding(
                    id=f"{rid}:req:x", bank_id=bank, requirement_id="req:x", status="ok",
                    run_id=rid, evidence_url="https://js_bank.example/", evidence_quote="q",
                    reason="r", pages_read=1, urls_read=[], created_at=when))
            db.upsert_job(conn, Job(id=f"job-{bank}-{src}", url=f"https://{bank}.example/",
                                    status="done", result_ref=rid))
    with TestClient(main.app) as c:
        assert c.get("/jobs/job-js_bank-job").json()["precomputed_findings"] == 1
        assert c.get("/jobs/job-new_bank-job").json()["precomputed_findings"] == 0


def test_js_only_crawl_reason_names_no_env_var():
    import inspect
    import re

    from backend.crawl import crawler
    src = inspect.getsource(crawler.Crawler.crawl)
    block = src[src.index('res.status = "needs_browser"'):][:400]
    assert not re.search(r"[A-Z]{3,}_[A-Z_]{3,}", block)
