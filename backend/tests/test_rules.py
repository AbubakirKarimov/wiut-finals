"""Deterministic checks (backend/checks/rules.py) on HTML rebuilt from stored crawl records
(backend/tests/fixtures/bank_pages/, made by eval/make_rule_fixtures.py). No network, no LLM:
every check here must decide with decided_by = "code"."""

import re
from pathlib import Path

import pytest

from backend.checks import llm_checks
from backend.checks.runner import finalize, run_checks, run_one
from backend.crawl.crawler import CrawlResult
from backend.crawl.text import detect_language, links, page_title, visible_text
from backend.models import Page, Requirement

FIX = Path(__file__).parent / "fixtures" / "bank_pages"
REAL_HINTS = Path(llm_checks.__file__).resolve().parents[2] / "data" / "check_hints.yaml"


@pytest.fixture(autouse=True)
def real_hints(monkeypatch, tmp_db):
    monkeypatch.setattr(llm_checks, "HINTS_PATH", REAL_HINTS)


def fixture_page(name: str, bank: str = "b") -> Page:
    raw = (FIX / f"{name}.html").read_text(encoding="utf-8")
    url = re.match(r"<!-- (\S+)", raw).group(1)
    text = visible_text(raw)
    return Page(bank_id=bank, url=url, text=text, source_type="html", title=page_title(raw),
                language=detect_language(text) or "other", links=links(raw, url))


def filler(base: str, n: int, path: str = "news") -> list[Page]:
    return [Page(bank_id="b", url=f"{base}/{path}/{i}", language="uz_latn", source_type="html",
                 text="Yangiliklar va e'lonlar. " * 20,
                 links=[(f"{base}/{path}/{i + 1}", "Keyingi yangilik")]) for i in range(n)]


def req(clause: str) -> Requirement:
    return Requirement(id=f"req:cbu_reg_3030:main:{clause}", text_original="t", text_en="t",
                       source_doc="cbu_reg_3030", source_clause_id=f"cbu_reg_3030:main:{clause}",
                       source_url="https://lex.uz/ru/docs/3804290", check_type="key_info",
                       approved=True)


def check(clause: str, pages: list[Page]):
    c = CrawlResult(bank_id="b", start_url=pages[0].url, pages=pages, has_language_switcher=True)
    r = req(clause)
    return finalize(run_one(r, c, None), c, r), r, c


def home(name, extra=()):
    h = fixture_page(name)
    base = "{0.scheme}://{0.netloc}".format(__import__("urllib.parse").parse.urlsplit(h.url))
    return [h, *extra, *filler(base, 6)]


# --- main:49 complaints link on the homepage ---

def test_49_positive_link_on_homepage():
    out, _, _ = check("49", home("mkbank_uz_home"))
    assert out.status == "ok" and not out.llm_used
    assert out.page.url == "https://mkbank.uz/uz/" and "murojaat" in out.quote.lower()


def test_49_text_without_link_is_not_a_gap():
    out, _, _ = check("49", home("universal_home"))
    assert out.status == "not_checkable" and "not as a link" in out.reason


# --- main:51 call-centre number on the homepage ---

def test_51_positive_plus998_number():
    out, _, _ = check("51", home("anor_uz_home"))
    assert out.status == "ok" and "+998" in out.quote and not out.llm_used


def test_51_negative_no_number_is_code_gap():
    out, _, _ = check("51", home("universal_home"))
    assert out.status == "possible_gap" and out.absence and out.quote is None
    assert out.reason.startswith("No evidence found on 7 pages read.")


def test_51_year_is_not_a_short_number():
    p = Page(bank_id="b", url="https://x.uz/", language="uz_latn", source_type="html",
             text="Bank 1994 yilda tashkil etilgan. " * 20)
    out, _, _ = check("51", [p, *filler("https://x.uz", 6)])
    assert out.status == "possible_gap"


# --- main:40^4 deposit guarantee link on a deposit page ---

def test_40_4_positive_link_to_agency():
    dep = fixture_page("agrobank_deposit_baraka")
    out, _, _ = check("40^4", [*filler("https://agrobank.uz", 5), dep])
    assert out.status == "ok" and "Omonatlaringiz kafolatlangan" in out.quote
    assert out.page.url.endswith("/deposits/baraka")


def test_40_4_statement_without_link_is_not_a_gap():
    dep = fixture_page("mkbank_uz_deposit")
    out, _, _ = check("40^4", [*filler("https://mkbank.uz", 5), dep])
    assert out.status == "not_checkable" and "not as a link" in out.reason


def test_no_link_data_at_all_is_not_checkable():
    dep = Page(bank_id="b", url="https://x.uz/uz/omonatlar", language="uz_latn",
               source_type="html", text="Omonat foiz stavkasi. " * 20)
    pages = [Page(**{**p.model_dump(), "links": []}) for p in filler("https://x.uz", 5)] + [dep]
    out, _, _ = check("40^4", pages)
    assert out.status == "not_checkable" and "no link data" in out.reason


def test_40_4_no_deposit_page_read_is_not_checkable():
    out, _, _ = check("40^4", home("mkbank_uz_home"))
    assert out.status == "not_checkable" and "relevant section not reached" in out.reason


def test_40_4_deposit_page_without_link_or_statement_is_code_gap():
    dep = Page(bank_id="b", url="https://x.uz/uz/omonatlar", language="uz_latn",
               source_type="html", text="Omonat foiz stavkasi 20 foiz. " * 20,
               links=[("https://x.uz/uz/omonat/1", "Jamg'arma omonati")])
    out, _, _ = check("40^4", [*filler("https://x.uz", 5), dep])
    assert out.status == "possible_gap" and out.page.url == dep.url


# --- main:17 one-click link to bank information ---

def test_17_positive_about_link():
    out, _, _ = check("17", home("garant_ru_home"))
    assert out.status == "ok" and "О банке" in out.quote


def test_17_negative_homepage_without_about_link():
    out, _, _ = check("17", home("universal_home"))
    assert out.status == "possible_gap" and not out.llm_used


# --- main:18^1 loan calculator ---

def test_18_1_positive_calculator_link_with_caveat():
    out, _, _ = check("18^1", home("garant_ru_home"))
    assert out.status == "ok" and "калькулятор" in out.quote.lower()
    assert "not verified" in out.reason


def test_18_1_negative_no_calculator_with_loan_section_read():
    loans = filler("https://www.anorbank.uz", 1, "uz/kreditlar")
    out, _, _ = check("18^1", home("anor_uz_home", loans))
    assert out.status == "possible_gap"


def test_18_1_no_loan_page_read_is_not_checkable():
    out, _, _ = check("18^1", home("universal_home"))
    assert out.status == "not_checkable" and "relevant section not reached" in out.reason


# --- main:14 site structure (site map) ---

def test_14_positive_sitemap_link():
    out, _, _ = check("14", home("mkbank_uz_home"))
    assert out.status == "ok" and "Sayt xaritasi" in out.quote


def test_14_negative_and_road_map_is_not_a_site_map():
    out, _, _ = check("14", home("anor_uz_home"))
    assert out.status == "possible_gap"
    p = Page(bank_id="b", url="https://x.uz/", language="uz_latn", source_type="html",
             text="Yo'l xaritasi " * 30, links=[("https://x.uz/roadmap", "Yo'l xaritasi")])
    out, _, _ = check("14", [p, *filler("https://x.uz", 6)])
    assert out.status == "possible_gap"


# --- the runner marks all of these as decided by code ---

def test_runner_marks_rule_findings_as_code():
    fs = run_checks("r", CrawlResult(bank_id="b", start_url="https://mkbank.uz/uz/",
                                     pages=home("mkbank_uz_home"), has_language_switcher=True),
                    [req(c) for c in ("14", "17", "18^1", "49", "51")], None)
    assert {f.decided_by for f in fs} == {"code"}
    assert all(f.status == "ok" for f in fs), [(f.requirement_id, f.reason) for f in fs]
