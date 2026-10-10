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
             text="Bank 1994 yilda tashkil etilgan. " * 60)
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
    dep = Page(bank_id="b", url="https://x.uz/uz/omonatlar/jamgarma", language="uz_latn",
               source_type="html", text="Omonat foiz stavkasi. " * 20)
    pages = [Page(**{**p.model_dump(), "links": []}) for p in filler("https://x.uz", 5)] + [dep]
    out, _, _ = check("40^4", pages)
    assert out.status == "not_checkable" and "no link data" in out.reason


def test_40_4_no_deposit_page_read_is_not_checkable():
    out, _, _ = check("40^4", home("mkbank_uz_home"))
    assert out.status == "not_checkable" and "relevant section not reached" in out.reason


def test_40_4_deposit_page_without_link_or_statement_is_code_gap():
    dep = Page(bank_id="b", url="https://x.uz/uz/omonatlar/jamgarma", language="uz_latn",
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
             text="Yo'l xaritasi " * 120, links=[("https://x.uz/roadmap", "Yo'l xaritasi")])
    out, _, _ = check("14", [p, *filler("https://x.uz", 6)])
    assert out.status == "possible_gap"


# --- the runner marks all of these as decided by code ---

def test_runner_marks_rule_findings_as_code():
    fs = run_checks("r", CrawlResult(bank_id="b", start_url="https://mkbank.uz/uz/",
                                     pages=home("mkbank_uz_home"), has_language_switcher=True),
                    [req(c) for c in ("14", "17", "18^1", "49", "51")], None)
    assert {f.decided_by for f in fs} == {"code"}
    assert all(f.status == "ok" for f in fs), [(f.requirement_id, f.reason) for f in fs]


# --- short homepage: no possible_gap from a thin homepage ---

def thin_home(chars: int, links=()) -> Page:
    text = ("Bosh sahifa " * 200)[:chars - 1] + "."
    return Page(bank_id="b", url="https://x.uz/", language="uz_latn", source_type="html",
                text=text, links=list(links) or [("https://x.uz/news", "Yangiliklar")])


@pytest.mark.parametrize("clause", ["14", "17", "49", "51"])
def test_short_homepage_never_gives_a_gap(clause):
    out, _, _ = check(clause, [thin_home(900), *filler("https://x.uz", 6)])
    assert out.status == "not_checkable"
    assert out.reason.startswith("homepage text too short (900 chars), likely dynamic content "
                                 "or blocked")


def test_short_homepage_any_page_rule_18_1():
    loans = filler("https://x.uz", 1, "uz/kreditlar")
    out, _, _ = check("18^1", [thin_home(900), *loans, *filler("https://x.uz", 6)])
    assert out.status == "not_checkable" and "homepage text too short" in out.reason


def test_long_enough_homepage_still_gives_a_gap():
    out, _, _ = check("14", [thin_home(1600), *filler("https://x.uz", 6)])
    assert out.status == "possible_gap"


def test_short_homepage_keeps_verified_evidence():
    """Evidence actually found on a thin homepage is still ok (only absence is suspect)."""
    home = thin_home(900, [("https://x.uz/sitemap", "Sayt xaritasi")])
    home.text = "Sayt xaritasi " + home.text
    out, _, _ = check("14", [home, *filler("https://x.uz", 6)])
    assert out.status == "ok"


def test_short_homepage_does_not_affect_section_rule_40_4():
    dep = Page(bank_id="b", url="https://x.uz/uz/omonatlar/jamgarma", language="uz_latn",
               source_type="html", text="Omonat foiz stavkasi 20 foiz. " * 20,
               links=[("https://x.uz/uz/omonat/1", "Jamg'arma omonati")])
    out, _, _ = check("40^4", [thin_home(300), *filler("https://x.uz", 5), dep])
    assert out.status == "possible_gap"


def test_threshold_comes_from_check_hints(tmp_path, monkeypatch):
    h = tmp_path / "hints.yaml"
    h.write_text(REAL_HINTS.read_text(encoding="utf-8").replace(
        "homepage_min_chars: 1500", "homepage_min_chars: 500"), encoding="utf-8")
    monkeypatch.setattr(llm_checks, "HINTS_PATH", h)
    out, _, _ = check("14", [thin_home(900), *filler("https://x.uz", 6)])
    assert out.status == "possible_gap"


# --- regression: a stored page without link metadata hid MKBANK's guarantee link ---

def test_guarantee_link_extracted_from_mkbank_markup():
    dep = fixture_page("mkbank_ru_deposit_guarantee")
    assert ("https://fgd.uz/ru", "Ваши вклады гарантированы") in dep.links
    out, _, _ = check("40^4", [*filler("https://mkbank.uz", 5), dep])
    assert out.status == "ok" and "Ваши вклады гарантированы" in out.quote
    assert "fgd.uz" in out.reason


def test_stored_page_without_link_metadata_is_fetched_again(tmp_db):
    """Rows stored before link metadata existed have links "{}"; the crawler must not reuse
    them (it did, and the 40^4 link check saw a deposit page with no links)."""
    import httpx
    from backend import db
    from backend.crawl.crawler import CrawlConfig, Crawler
    from backend.crawl.fetch import FetchConfig, Fetcher
    from backend.crawl.store import DbPageStore

    raw = (FIX / "mkbank_ru_deposit_guarantee.html").read_text(encoding="utf-8")
    home = ("<html><body><p>" + "Bank xizmatlari va omonatlar haqida. " * 40 + "</p>"
            "<a href='/ru/private/deposit/'>Вклады</a></body></html>")
    fetched = []

    def handler(req):
        if req.url.path == "/robots.txt":
            return httpx.Response(404)
        fetched.append(req.url.path)
        body = raw if req.url.path == "/ru/private/deposit/" else home
        return httpx.Response(200, headers={"content-type": "text/html"}, content=body.encode())

    stale = fixture_page("mkbank_ru_deposit_guarantee", bank="mkbank")
    with db.connect(tmp_db) as conn:   # the old row: text present, link metadata missing
        db.upsert_page(conn, stale.model_copy(update={"links": []}))
    f = FetchConfig(user_agent="ComplianceRadar/0.1", min_delay_seconds=0, min_text_chars=100)
    c = Crawler(CrawlConfig(fetch=f, max_pages=5), store=DbPageStore(tmp_db),
                fetcher=Fetcher(f, transport=httpx.MockTransport(handler)))
    res = c.crawl("mkbank", "https://mkbank.uz/ru/")
    assert "/ru/private/deposit/" in fetched                    # not reused from the store
    dep = next(p for p in res.pages if p.url.endswith("/ru/private/deposit/"))
    assert ("https://fgd.uz/ru", "Ваши вклады гарантированы") in dep.links
    with db.connect(tmp_db) as conn:                             # and the store is repaired
        _, meta = db.get_cached_page(conn, "mkbank", dep.url,
                                     __import__("datetime").datetime(2000, 1, 1))
    assert ["https://fgd.uz/ru", "Ваши вклады гарантированы"] in meta["links"]


# --- 40^4 (approved 2026-10-11): phrase fallback, law-only link, product page required ---

def dep_page(url, text, links=()):
    return Page(bank_id="b", url=url, language="ru", source_type="html", text=text,
                links=list(links) or [("https://x.uz/ru/kredity", "Кредиты")])


def run_40_4(*deposit_pages):
    out, _, _ = check("40^4", [*filler("https://x.uz", 5), *deposit_pages])
    return out


def test_40_4_scattered_words_are_not_the_statement():
    """Anor Bank's case: "Гарантированная надежность ..." near "вклад" is not the phrase."""
    p = dep_page("https://x.uz/ru/vklady/onlajn",
                 "Вклад Онлайн. Гарантированная надежность и сохранность средств. " * 10)
    out = run_40_4(p)
    assert out.status == "possible_gap"


def test_40_4_adjacent_phrase_without_link_is_not_checkable():
    p = dep_page("https://x.uz/ru/vklady/onlajn", "Вклад Онлайн. Ваши вклады гарантированы. " * 10)
    out = run_40_4(p)
    assert out.status == "not_checkable" and "not as a link" in out.reason


def test_40_4_link_only_to_the_law_is_not_checkable():
    law = ("https://lex.uz/ru/docs/7389439", "О гарантиях защиты вкладов в банках")
    p = dep_page("https://x.uz/ru/vklady/onlajn",
                 "Вклад Онлайн. Закон О гарантиях защиты вкладов в банках. " * 10, [law])
    out = run_40_4(p)
    assert out.status == "not_checkable"
    assert "links the law, not the Agency" in out.reason and "lex.uz" in out.reason


def test_40_4_agency_link_wins_over_law_link():
    """MKBANK's page links both the Agency (fgd.uz) and the law (lex.uz)."""
    dep = fixture_page("mkbank_ru_deposit_guarantee")
    out = run_40_4(dep)
    assert out.status == "ok" and "fgd.uz" in out.reason


def test_40_4_only_the_section_index_read_is_not_checkable():
    idx = dep_page("https://x.uz/ru/vklady", "Все вклады банка: Онлайн, Срочный. " * 10)
    out = run_40_4(idx)
    assert out.status == "not_checkable"
    assert out.reason.startswith("relevant section not reached: only the section index")
    assert "https://x.uz/ru/vklady (index)" in out.reason


def test_40_4_gap_lists_every_deposit_page_read():
    idx = dep_page("https://x.uz/ru/vklady", "Все вклады банка. " * 20)
    prod = dep_page("https://x.uz/ru/vklad-srochnyj", "Вклад Срочный: ставка 20% годовых. " * 10)
    out = run_40_4(idx, prod)
    assert out.status == "possible_gap" and out.page.url == prod.url
    assert "https://x.uz/ru/vklady (index); https://x.uz/ru/vklad-srochnyj (product)" in out.reason


def test_40_4_homepage_is_not_a_deposit_page():
    """Anor Bank: the homepage title "... kreditlar va omonatlar" made it a deposit page."""
    home = Page(bank_id="b", url="https://x.uz/uz/", language="uz_latn", source_type="html",
                title="Raqamli bank: kreditlar va omonatlar", text="Bosh sahifa. " * 200,
                links=[("https://x.uz/uz/kredit", "Kredit")])
    idx = dep_page("https://x.uz/uz/deposit/", "Omonatlar ro'yxati. " * 20)
    out, _, _ = check("40^4", [home, *filler("https://x.uz", 5), idx])
    assert out.status == "not_checkable" and "only the section index" in out.reason
    assert "https://x.uz/uz/ " not in out.reason


def test_40_4_styled_text_that_is_not_a_link():
    """Garant Bank: "Подробнее: Агентство по гарантированию вкладов." is red and underlined
    (<span><u>) but has no <a href>; it must not count as the link."""
    raw = ("<html><body><a href='/ru/kredity'>Кредиты</a><p>Вклад «Orzu sari». "
           + "Ставка 18 процентов годовых. " * 30 + "Подробнее: <span style='color:#c0392b'>"
           "<u>Агентство по гарантированию вкладов.</u></span></p></body></html>")
    url = "https://x.uz/ru/vklad-orzu-sari"
    p = Page(bank_id="b", url=url, language="ru", source_type="html", text=visible_text(raw),
             links=links(raw, url))
    assert not any("fgd" in u for u, _ in p.links)
    out = run_40_4(p)
    assert out.status == "not_checkable" and "not as a link" in out.reason


# --- strict section gate for 18^1, 28^1, 37^5 (decision 2026-10-11) ---

def loans_titled_home(extra_links=()):
    return Page(bank_id="b", url="https://x.uz/uz/", language="uz_latn", source_type="html",
                title="Bank: loans and deposits / kreditlar va omonatlar",
                text="Bosh sahifa yangiliklari va xizmatlar. " * 60,
                links=[("https://x.uz/uz/news", "Yangiliklar"), *extra_links])


def news(n=6):
    return [Page(bank_id="b", url=f"https://x.uz/uz/news/{i}", language="uz_latn",
                 source_type="html", text="Yangiliklar va e'lonlar. " * 20,
                 links=[("https://x.uz/uz/news", "Yangiliklar")]) for i in range(n)]


@pytest.mark.parametrize("clause", ["18^1", "28^1", "37^5"])
def test_homepage_titled_loans_does_not_reach_the_loan_section(clause):
    out, _, _ = check(clause, [loans_titled_home(), *news()])
    assert out.status == "not_checkable"
    assert out.reason.startswith("relevant section not reached (read 7 pages)")


@pytest.mark.parametrize("clause", ["18^1", "37^5"])
def test_real_loans_page_allows_a_gap(clause):
    loans = Page(bank_id="b", url="https://x.uz/uz/kreditlar/avtokredit", language="uz_latn",
                 source_type="html", text="Avtokredit: yillik foiz stavkasi 24 foiz. " * 20,
                 links=[("https://x.uz/uz/kreditlar", "Kreditlar")])
    out, _, _ = check(clause, [loans_titled_home(), *news(), loans])
    assert out.status == "possible_gap" and not out.llm_used


def test_page_reached_by_a_section_menu_link_counts():
    """URL without a section stem, but the homepage menu links to it as "Kreditlar"."""
    page = Page(bank_id="b", url="https://x.uz/uz/p/123", language="uz_latn",
                source_type="html", text="Shartlar va foizlar. " * 30)
    home = loans_titled_home([("https://x.uz/uz/p/123", "Kreditlar")])
    out, _, _ = check("18^1", [home, *news(), page])
    assert out.status == "possible_gap"


def test_title_alone_does_not_make_a_section_page():
    page = Page(bank_id="b", url="https://x.uz/uz/p/9", language="uz_latn", source_type="html",
                title="Kreditlar", text="Shartlar va foizlar. " * 30)
    out, _, _ = check("18^1", [loans_titled_home(), *news(), page])
    assert out.status == "not_checkable" and "relevant section not reached" in out.reason


def test_section_stems_come_from_check_hints(tmp_path, monkeypatch):
    from backend.crawl.sections import section_stems
    assert "lending" in section_stems()["loan"]          # only in data/check_hints.yaml
    h = tmp_path / "hints.yaml"
    h.write_text("requirements: {}\n", encoding="utf-8")
    monkeypatch.setattr(llm_checks, "HINTS_PATH", h)
    assert "lending" not in section_stems()["loan"]      # code fallback without the block
