import httpx

from backend import db
from backend.crawl.crawler import CrawlConfig, Crawler
from backend.crawl.fetch import FetchConfig, Fetcher
from backend.models import Requirement
from backend.pipeline import bank_id_for, check_site, sync_requirements_yaml

RU = " ".join(["Банковские услуги, вклады и кредиты для физических лиц"] * 20)


def ru_site(req):
    if req.url.path == "/robots.txt":
        return httpx.Response(404)
    links = "".join(f'<a href="/ru/p{i}">p{i}</a>' for i in range(8))
    return httpx.Response(200, html=f"<html><body><p>{RU}</p>{links}</body></html>")


def make_crawler():
    f = FetchConfig(user_agent="ComplianceRadar/0.1", min_delay_seconds=0, min_text_chars=100)
    return Crawler(CrawlConfig(fetch=f, max_pages=6),
                   fetcher=Fetcher(f, transport=httpx.MockTransport(ru_site)))


def test_check_site_end_to_end(tmp_db):
    with db.connect(tmp_db) as conn:
        db.upsert_requirement(conn, Requirement(
            id="req:law:20", text_original="Давлат тилида", text_en="State language",
            source_doc="law_state_language", source_clause_id="law_state_language:art:20",
            source_url="https://lex.uz/x", check_type="uz_version", approved=True))
    run = check_site("https://ru-only.uz/ru/", crawler=make_crawler(), llm=None,
                     db_path=tmp_db)
    assert run.status == "done" and run.crawl_status == "ok" and run.pages_read == 6
    assert run.bank_id == "site_ru_only_uz"
    with db.connect(tmp_db) as conn:
        [f] = db.list_findings(conn, run_id=run.id)
        assert len(db.list_pages(conn, run.bank_id, run_id=run.id)) == 6
        stored = db.get_run(conn, run.id)
    assert f.status == "possible_gap" and f.pages_read == 6 and f.evidence_quote
    assert stored.finished_at is not None


def test_bank_id_for_known_bank():
    assert bank_id_for("https://mkbank.uz/ru/some/page") == "mkbank"


def test_sync_requirements_yaml(tmp_db, tmp_path):
    y = tmp_path / "r.yaml"
    y.write_text("requirements:\n- id: req:a\n  text_original: t\n  text_en: e\n"
                 "  source_doc: d\n  source_clause_id: c\n  source_url: https://lex.uz/x\n"
                 "  check_type: key_info\n  approved: true\n  text_en_label: machine translation\n"
                 "- id: req:b\n  text_original: t\n  source_doc: d\n  source_clause_id: c\n"
                 "  source_url: https://lex.uz/x\n  check_type: key_info\n  approved: false\n",
                 encoding="utf-8")
    assert sync_requirements_yaml(y, db_path=tmp_db) == 1
    with db.connect(tmp_db) as conn:
        assert [r.id for r in db.list_requirements(conn, approved_only=True)] == ["req:a"]
