import httpx

from backend import db, metrics
from backend.consistency import compare, pair_agreement, run_consistency
from backend.crawl.crawler import CrawlConfig, Crawler
from backend.crawl.fetch import FetchConfig, Fetcher
from backend.models import Finding, Requirement
from backend.tests.test_checks import ScriptedLLM

UZ = ("Jismoniy shaxslar uchun tariflar. Bank xizmatlari uchun komissiya miqdori: plastik "
      "karta ochish uchun 15 000 so'm. Kredit bo'yicha yillik foiz stavkasi 24 foiz. ")
QUOTE = "Kredit bo'yicha yillik foiz stavkasi 24 foiz."


def site(req):
    if req.url.path == "/robots.txt":
        return httpx.Response(404)
    links = "".join(f'<a href="/uz/p{i}">p{i}</a>' for i in range(8))
    return httpx.Response(200, html=f"<html><title>Tariflar</title><body><p>{UZ * 8}</p>"
                                    f"{links}</body></html>")


def test_pair_agreement():
    assert pair_agreement(["ok", "ok"]) == 1.0
    assert pair_agreement(["ok", "possible_gap"]) == 0.0
    assert pair_agreement(["ok", "ok", "possible_gap"]) == 1 / 3


def test_compare_counts_status_and_quote_agreement():
    a = [Finding(id="1", bank_id="b", requirement_id="r1", status="ok", evidence_quote="q"),
         Finding(id="2", bank_id="b", requirement_id="r2", status="ok", evidence_quote="q")]
    b = [Finding(id="3", bank_id="b", requirement_id="r1", status="ok", evidence_quote="q2"),
         Finding(id="4", bank_id="b", requirement_id="r2", status="possible_gap")]
    r = compare([a, b])
    assert r["status_agreement"] == 0.5 and r["quote_agreement"] == 0.0
    assert r["per_requirement"]["r2"]["statuses"] == ["ok", "possible_gap"]


def test_second_run_replays_pages_and_bypasses_cache(tmp_db, tmp_path, monkeypatch):
    monkeypatch.setenv("REQUIREMENTS_PATH", str(tmp_path / "none.yaml"))  # not the team's file
    banks = tmp_path / "banks.yaml"
    banks.write_text('banks:\n  - id: b\n    name: "B"\n    website_url: "https://b.example/uz/"'
                     '\n    role: partner\n    notes: ""\n', encoding="utf-8")
    with db.connect(tmp_db) as conn:
        db.upsert_requirement(conn, Requirement(
            id="req:k", text_original="t", text_en="Rates are published.", source_doc="d",
            source_clause_id="c:1", source_url="https://lex.uz/x", check_type="key_info",
            approved=True))
    requests = []

    def counting(req):
        requests.append(req.url.path)
        return site(req)

    f = FetchConfig(user_agent="ComplianceRadar/0.1", min_delay_seconds=0, min_text_chars=100)
    crawler = Crawler(CrawlConfig(fetch=f, max_pages=6),
                      fetcher=Fetcher(f, transport=httpx.MockTransport(counting)))
    llms = []

    def factory():
        llm = ScriptedLLM(tmp_db, presence={"present": True, "quote": QUOTE, "explanation": ""})
        llms.append(llm)
        return llm

    r = run_consistency("b", 2, db_path=tmp_db, progress=lambda m: None, llm_factory=factory,
                        first_crawler=crawler, banks_path=banks)
    n_requests = len(requests)
    assert r["status_agreement"] == 1.0 and r["n_requirements"] == 1
    # Run 2 fetched nothing (replay) but called the LLM again (fresh cache namespace).
    assert len(requests) == n_requests
    assert llms[-1].prompts, "second run must not be served from the shared cache"
    with db.connect(tmp_db) as conn:
        m = metrics.consistency(conn)
    assert m["value"] == 1.0 and m["requirements"] == 1 and m["banks"] == 1


def test_consistency_metric_no_data(tmp_db):
    with db.connect(tmp_db) as conn:
        assert metrics.consistency(conn)["value"] == "no data"
