import csv

import httpx
import pytest
from fastapi.testclient import TestClient

from backend import db, metrics, pipeline
from backend.api import main
from backend.api.urlcheck import validate_public_url
from backend.crawl.crawler import CrawlConfig, Crawler
from backend.crawl.fetch import FetchConfig, Fetcher
from backend.models import Requirement

RU = " ".join(["Банковские услуги, вклады и кредиты для физических лиц"] * 20)


def ru_site(req):
    if req.url.path == "/robots.txt":
        return httpx.Response(404)
    links = "".join(f'<a href="/ru/p{i}">p{i}</a>' for i in range(8))
    return httpx.Response(200, html=f"<html><body><p>{RU}</p>{links}</body></html>")


@pytest.fixture
def client(tmp_db, monkeypatch):
    monkeypatch.setenv("CHECK_ALLOW_PRIVATE_URLS", "1")
    for k in ("LLM_BASE_URL", "LLM_API_KEY", "LLM_MODEL"):
        monkeypatch.setenv(k, "")

    def fake_crawler(cfg, progress=None):
        f = FetchConfig(user_agent="ComplianceRadar/0.1", min_delay_seconds=0,
                        min_text_chars=100)
        return Crawler(CrawlConfig(fetch=f, max_pages=6), progress=progress,
                       fetcher=Fetcher(f, transport=httpx.MockTransport(ru_site)))

    monkeypatch.setattr(main, "Crawler", fake_crawler)
    # Isolate from the team's real data/requirements.yaml (loaded at API startup).
    monkeypatch.setattr(pipeline, "REQUIREMENTS_YAML", tmp_db.parent / "no-requirements.yaml")
    main.check_limiter._hits.clear()
    with db.connect(tmp_db) as conn:
        db.upsert_requirement(conn, Requirement(
            id="req:law:20", text_original="Давлат тилида", text_en="State language",
            source_doc="law_state_language", source_clause_id="law_state_language:art:20",
            source_url="https://lex.uz/docs/x#20", check_type="uz_version", approved=True))
    with TestClient(main.app) as c:
        yield c


def test_check_job_to_findings_to_decision(client):
    r = client.post("/check", json={"url": "https://ru-only.example/ru/"})
    assert r.status_code == 202
    job = client.get(f"/jobs/{r.json()['job_id']}").json()
    assert job["status"] == "done" and job["run"]["pages_read"] == 6
    [f] = job["findings"]
    assert f["status"] == "possible_gap" and f["evidence_quote"]
    assert f["requirement"]["source_url"] == "https://lex.uz/docs/x#20"
    assert f["evidence_quote_en_label"] == "machine translation"
    assert f["run"]["finished_at"] and f["pages_read"] == 6

    listed = client.get("/findings", params={"status": "possible_gap"}).json()
    assert [x["id"] for x in listed] == [f["id"]]
    assert client.get("/findings", params={"status": "ok"}).json() == []

    d = client.post("/decisions", json={"finding_id": f["id"], "analyst": "A. Analyst",
                                        "verdict": "confirmed", "comment": "checked"})
    assert d.status_code == 201
    log = client.get("/decisions").json()
    assert log[0]["finding_id"] == f["id"] and log[0]["verdict"] == "confirmed"
    assert client.get("/findings").json()[0]["decision"]["verdict"] == "confirmed"

    m = client.get("/metrics").json()
    assert m["checks_completed"] == 1 and m["latency_seconds"]["p50"] != "no data"
    dp = m["precision_possible_gap_from_decisions"]
    assert dp["decided"] == 1 and dp["confirmed"] == 1
    assert dp["value"] == "too few decisions to be meaningful"
    assert m["llm"]["api_calls"] == 0


def test_decision_validation(client):
    assert client.post("/decisions", json={"finding_id": "nope", "analyst": "a",
                                           "verdict": "confirmed"}).status_code == 404
    assert client.post("/decisions", json={"finding_id": "x", "analyst": "a",
                                           "verdict": "violation"}).status_code == 422


def test_check_rejects_bad_urls(client, monkeypatch):
    monkeypatch.setenv("CHECK_ALLOW_PRIVATE_URLS", "0")
    for url in ("http://example.com/", "https://127.0.0.1/", "https://localhost/",
                "https://user:pw@example.com/", "ftp://example.com/x"):
        r = client.post("/check", json={"url": url})
        assert r.status_code == 422, url
    assert client.get("/jobs/missing").status_code == 404


def test_check_rate_limit_429(client, monkeypatch):
    monkeypatch.setattr(main.check_limiter, "max_requests", 1)
    assert client.post("/check", json={"url": "https://a.example/"}).status_code == 202
    r = client.post("/check", json={"url": "https://a.example/"})
    assert r.status_code == 429 and "Rate limit" in r.json()["detail"]


def test_metrics_no_data(tmp_db):
    with db.connect(tmp_db) as conn:
        m = metrics.compute(conn, labels_path=tmp_db.parent / "missing.csv")
    assert m["latency_seconds"]["p50"] == "no data"
    assert m["llm"]["avg_cost_usd_per_check"] == "no data"
    assert m["precision_possible_gap_vs_labels"]["value"] == "no data"


def test_label_precision(client, tmp_path):
    client.post("/check", json={"url": "https://ru-only.example/ru/"})
    labels = tmp_path / "labels.csv"
    with labels.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["bank_id", "requirement_id", "expected"])
        w.writerow(["site_ru_only_example", "req:law:20", "ok"])
    with db.connect() as conn:
        p = metrics.label_precision(conn, labels)
    assert p["value"] == 0.0 and p["predicted_gaps"] == 1


def test_percentile():
    assert metrics.percentile([], 50) is None
    assert metrics.percentile([3, 1, 2], 50) == 2
    assert metrics.percentile(list(range(1, 101)), 95) == 95


def test_validate_public_url_accepts_public_host(monkeypatch):
    monkeypatch.setenv("CHECK_ALLOW_PRIVATE_URLS", "0")
    monkeypatch.setattr("socket.getaddrinfo",
                        lambda *a, **k: [(2, 1, 6, "", ("93.184.216.34", 443))])
    assert validate_public_url("https://example.com/") == "https://example.com/"
    monkeypatch.setattr("socket.getaddrinfo",
                        lambda *a, **k: [(2, 1, 6, "", ("10.0.0.5", 443))])
    with pytest.raises(ValueError, match="non-public"):
        validate_public_url("https://internal.example/")


def test_decision_precision_threshold(tmp_db, monkeypatch):
    from backend.models import Decision, Finding
    with db.connect(tmp_db) as conn:
        for i in range(13):
            db.upsert_finding(conn, Finding(id=f"f{i}", bank_id="b", requirement_id="r",
                                            status="possible_gap"))
        db.upsert_finding(conn, Finding(id="ok1", bank_id="b", requirement_id="r", status="ok"))
        for i in range(13):
            db.add_decision(conn, Decision(finding_id=f"f{i}", analyst="a",
                                           verdict="confirmed" if i < 8 else "rejected"))
        # Latest decision wins; decisions on non-gap findings are ignored.
        db.add_decision(conn, Decision(finding_id="f0", analyst="a", verdict="rejected"))
        db.add_decision(conn, Decision(finding_id="ok1", analyst="a", verdict="confirmed"))
        p = metrics.decision_precision(conn)
        assert p["decided"] == 13 and p["confirmed"] == 7
        assert p["value"] == round(7 / 13, 3)
        assert p["label"] == "precision 54% on 13 decided findings"
        monkeypatch.setenv("METRICS_MIN_DECISIONS", "20")
        p = metrics.decision_precision(conn)
        assert p["value"] == "too few decisions to be meaningful" and p["decided"] == 13
