import json

import pytest

from backend import db
from backend.checks import llm_checks
from backend.checks.evidence import excerpt, opening_quote, verify_quote
from backend.checks.runner import run_checks
from backend.crawl.crawler import CrawlResult
from backend.llm.provider import LLMProvider, RateLimits, RawCompletion
from backend.models import Page, Requirement

UZ_TARIFF = ("Jismoniy shaxslar uchun tariflar. Bank xizmatlari uchun komissiya miqdori: "
             "plastik karta ochish uchun 15 000 so'm. Kredit bo'yicha yillik foiz stavkasi "
             "24 foiz. Omonatlar va depozitlar haqida ma'lumot.")
RU_HOME = ("Главная страница банка. Вклады, кредиты и банковские карты для физических лиц. "
           "Контакты и отделения банка в Ташкенте.")


def page(url, text, lang="uz_latn", title="", source_type="html"):
    return Page(bank_id="b", url=url, language=lang, text=text, title=title,
                source_type=source_type)


def req(check_type, rid="req:x"):
    return Requirement(id=rid, text_original="Банк тарифларни веб-сайтда эълон қилади.",
                       text_en="The bank publishes its tariffs on its website.",
                       source_doc="cbu_reg_3030", source_clause_id="cbu_reg_3030:main:13",
                       source_url="https://lex.uz/ru/docs/3804290#1", check_type=check_type,
                       approved=True)


def crawl(pages, errors=(), status="ok", switcher=True):
    return CrawlResult(bank_id="b", start_url="https://b.uz/", status=status, pages=list(pages),
                       fetch_errors=list(errors), has_language_switcher=switcher,
                       reason="needs browser: home page empty" if status != "ok" else "")


def many(n, lang="uz_latn", text=UZ_TARIFF):
    return [page(f"https://b.uz/p{i}", text, lang) for i in range(n)]


class ScriptedLLM(LLMProvider):
    """Test double: answers by schema; records prompts. Goes through the real
    cache/validation/logging code of LLMProvider."""
    name, model = "scripted", "test-model"

    def __init__(self, db_path, presence=None, keywords=None):
        super().__init__(db_path, RateLimits(min_interval_seconds=0))
        self.presence = presence or {"present": True, "quote": "", "explanation": ""}
        self.keywords = keywords or {"uz_latn": ["tarif", "komissiya"], "uz_cyrl": ["тариф"],
                                     "ru": ["тариф"], "en": ["tariff"]}
        self.prompts: list[str] = []

    def _complete(self, prompt, schema):
        self.prompts.append(prompt)
        props = schema.get("properties", {})
        if "translation_en" in props:
            body = {"translation_en": "EN: " + prompt.rsplit("Quote:\n", 1)[1][:40]}
        elif "present" in props:
            body = self.presence
        else:
            body = self.keywords
        return RawCompletion(text=json.dumps(body, ensure_ascii=False), input_tokens=100,
                             output_tokens=20)


# --- evidence helpers ---

def test_verify_quote_whitespace_only_normalization():
    text = "Kredit  bo'yicha\nyillik foiz stavkasi 24 foiz."
    assert verify_quote("Kredit bo'yicha yillik foiz stavkasi", text)
    assert not verify_quote("Kredit boʻyicha yillik foiz stavkasi", text)  # other apostrophe
    assert not verify_quote("kredit bo'yicha yillik foiz stavkasi", text)  # case differs
    assert not verify_quote("foiz", text)                                  # too short
    assert not verify_quote(None, text)


def test_excerpt_is_verbatim():
    text = UZ_TARIFF * 3
    parts = excerpt(text, [10, 50, 400], 300)
    assert all(p in text for p in parts) and sum(map(len, parts)) <= 300
    q = opening_quote(text, 60)
    assert text.startswith(q) and len(q) <= 60


# --- uz_version (deterministic) ---

def test_uz_version_ok(tmp_db):
    pages = many(4) + many(2, "ru", RU_HOME)
    [f] = run_checks("r", crawl(pages), [req("uz_version")], None)
    assert f.status == "ok" and f.evidence_quote and "language switcher found" in f.reason
    assert f.decided_by == "code"
    assert f.evidence_quote_en is None  # no LLM -> no translation, never invented


def test_uz_version_gap_when_no_uzbek_pages(tmp_db):
    [f] = run_checks("r", crawl(many(6, "ru", RU_HOME), switcher=False), [req("uz_version")], None)
    assert f.status == "possible_gap"
    assert f.pages_read == 6 and len(f.urls_read) == 6
    assert verify_quote(f.evidence_quote, RU_HOME) and f.evidence_url == "https://b.uz/p0"


def test_gap_downgraded_with_few_pages_or_fetch_errors(tmp_db):
    [f] = run_checks("r", crawl(many(4, "ru", RU_HOME)), [req("uz_version")], None)
    assert f.status == "not_checkable" and "only 4 page(s) read" in f.reason
    [f] = run_checks("r", crawl(many(6, "ru", RU_HOME), errors=["https://b.uz/x: HTTP 503"]),
                     [req("uz_version")], None)
    assert f.status == "not_checkable" and "fetch error" in f.reason


def test_uz_version_min_share(tmp_db, monkeypatch):
    pages = many(1) + many(5, "ru", RU_HOME)
    monkeypatch.setenv("UZ_VERSION_MIN_SHARE", "0.5")
    [f] = run_checks("r", crawl(pages), [req("uz_version")], None)
    assert f.status == "possible_gap" and "UZ_VERSION_MIN_SHARE" in f.reason


def test_crawl_failure_is_not_checkable(tmp_db):
    [f] = run_checks("r", crawl([], status="needs_browser"), [req("uz_version")], None)
    assert f.status == "not_checkable" and "needs browser" in f.reason


# --- required_document / key_info (LLM) ---

def test_key_info_ok_with_verified_quote_then_translation(tmp_db):
    quote = "Kredit bo'yicha yillik foiz stavkasi 24 foiz."
    llm = ScriptedLLM(tmp_db, presence={"present": True, "quote": quote, "explanation": "ok"})
    pages = [page("https://b.uz/tariflar", UZ_TARIFF, title="Tariflar")] + many(5, "ru", RU_HOME)
    [f] = run_checks("r", crawl(pages), [req("key_info")], llm)
    assert f.status == "ok" and f.evidence_quote == quote
    assert f.evidence_url == "https://b.uz/tariflar"
    assert f.decided_by == "llm_assisted"
    with db.connect(tmp_db) as conn:
        db.upsert_finding(conn, f)
        assert db.get_finding(conn, f.id).decided_by == "llm_assisted"
    assert f.evidence_quote_en.startswith("EN: ")
    # The translation prompt comes after the presence prompt (verification first).
    kinds = ["translate" if "Translate" in p else "presence" if "<excerpts>" in p else "kw"
             for p in llm.prompts]
    assert kinds == ["kw", "presence", "translate"]


def test_key_info_rejects_quote_not_in_page(tmp_db):
    llm = ScriptedLLM(tmp_db, presence={"present": True, "explanation": "",
                                        "quote": "Kredit foiz stavkasi 18 foiz (invented)."})
    pages = [page("https://b.uz/tariflar", UZ_TARIFF)] + many(5, "ru", RU_HOME)
    [f] = run_checks("r", crawl(pages), [req("key_info")], llm)
    assert f.status == "not_checkable" and "not found verbatim" in f.reason
    assert f.evidence_quote is None and f.evidence_quote_en is None


def test_required_document_gap_when_llm_says_absent(tmp_db):
    closest = "Bank xizmatlari uchun komissiya miqdori"
    llm = ScriptedLLM(tmp_db, presence={"present": False, "quote": closest, "explanation": "no"})
    pages = [page("https://b.uz/tariflar", UZ_TARIFF)] + many(5, "ru", RU_HOME)
    [f] = run_checks("r", crawl(pages), [req("required_document")], llm)
    assert f.status == "possible_gap" and f.evidence_quote == closest
    assert f.pages_read == 6 and f.urls_read[0] == "https://b.uz/tariflar"


def test_required_document_gap_without_keyword_match(tmp_db):
    llm = ScriptedLLM(tmp_db, keywords={"uz_latn": ["ommaviy oferta"], "uz_cyrl": [],
                                        "ru": ["публичная оферта"], "en": []})
    [f] = run_checks("r", crawl(many(6, "ru", RU_HOME)), [req("required_document")], llm)
    assert f.status == "possible_gap" and "No page matched" in f.reason
    assert f.reason.startswith("No evidence found on 6 pages read.")
    assert f.evidence_quote is None  # an absence is not quoted (audit B6)


def test_llm_not_configured_is_not_checkable(tmp_db):
    [f] = run_checks("r", crawl(many(6)), [req("key_info")], None)
    assert f.status == "not_checkable" and "LLM not configured" in f.reason


def test_hints_file_overrides_llm_keywords(tmp_db, tmp_path, monkeypatch):
    hints = tmp_path / "hints.yaml"
    hints.write_text("requirements:\n  req:x:\n    keywords:\n      uz_latn: [tariflar]\n",
                     encoding="utf-8")
    monkeypatch.setattr(llm_checks, "HINTS_PATH", hints)
    kws, source = llm_checks.get_keywords(req("key_info"), None)
    assert kws == ["tariflar"] and source == "hints"


def test_llm_calls_logged_with_run_id(tmp_db):
    llm = ScriptedLLM(tmp_db)
    token = db.current_run_id.set("run-42")
    try:
        llm_checks.get_keywords(req("key_info", "req:y"), llm)
    finally:
        db.current_run_id.reset(token)
    with db.connect(tmp_db) as conn:
        row = conn.execute("SELECT run_id, input_tokens FROM llm_calls").fetchone()
    assert row["run_id"] == "run-42" and row["input_tokens"] == 100


def test_only_approved_requirements_run(tmp_db):
    r = req("uz_version")
    r.approved = False
    assert run_checks("r", crawl(many(6)), [r], None) == []


@pytest.mark.parametrize("status", ["blocked", "unreachable", "js_shell_failed"])
def test_every_crawl_failure_never_yields_gap(tmp_db, status):
    [f] = run_checks("r", crawl([], status=status), [req("required_document")], None)
    assert f.status == "not_checkable"


# --- pacing: timeouts, context size, progress ---

class SlowLLM(ScriptedLLM):
    """Every presence call is rate limited longer than the check timeout allows."""

    def _complete(self, prompt, schema):
        if "present" in schema.get("properties", {}):
            from backend.llm.provider import LLMTransientError
            raise LLMTransientError("scripted: HTTP 429", retry_after=500)
        return super()._complete(prompt, schema)


def test_llm_timeout_is_not_checkable_never_gap(tmp_db, monkeypatch):
    monkeypatch.setenv("CHECK_TIMEOUT_SECONDS", "5")
    llm = SlowLLM(tmp_db)
    llm.limits.max_wait_seconds = 1000
    pages = [page("https://b.uz/tariflar", UZ_TARIFF)] + many(5, "ru", RU_HOME)
    [f] = run_checks("r", crawl(pages), [req("required_document")], llm)
    assert f.status == "not_checkable"
    assert f.reason.startswith("LLM timeout / rate limit")


def test_run_budget_exhausted_marks_remaining_checks(tmp_db, monkeypatch):
    monkeypatch.setenv("CHECK_RUN_BUDGET_SECONDS", "0")
    fs = run_checks("r", crawl(many(6)), [req("uz_version", "req:a"), req("key_info", "req:b")],
                    ScriptedLLM(tmp_db))
    assert [f.status for f in fs] == ["not_checkable", "not_checkable"]
    assert all("run time cap" in f.reason for f in fs)


def test_context_sent_to_llm_is_bounded(tmp_db, monkeypatch):
    monkeypatch.setenv("CHECK_MAX_CONTEXT_TOKENS", "1000")
    quote = "Kredit bo'yicha yillik foiz stavkasi 24 foiz."
    llm = ScriptedLLM(tmp_db, presence={"present": True, "quote": quote, "explanation": ""})
    huge = ("Boshqa ma'lumot. " * 3000) + UZ_TARIFF + (" Yana matn." * 3000)
    pages = [page("https://b.uz/tariflar", huge)] + many(5, "ru", RU_HOME)
    [f] = run_checks("r", crawl(pages), [req("key_info")], llm)
    assert f.status == "ok"
    sent = next(p for p in llm.prompts if "<excerpts>" in p)
    excerpt_text = sent.split("<excerpts>")[1].split("</excerpts>")[0]
    assert len(excerpt_text) <= 1000 * llm_checks.CHARS_PER_TOKEN + 50
    assert len(huge) > 10 * len(excerpt_text)


def test_progress_lines_per_check(tmp_db):
    lines = []
    quote = "Kredit bo'yicha yillik foiz stavkasi 24 foiz."
    llm = ScriptedLLM(tmp_db, presence={"present": True, "quote": quote, "explanation": ""})
    pages = [page("https://b.uz/tariflar", UZ_TARIFF)] + many(5, "ru", RU_HOME)
    run_checks("r", crawl(pages), [req("uz_version", "req:a"), req("key_info", "req:b")], llm,
               progress=lines.append)
    assert lines[0] == "check 1/2 cbu_reg_3030:main:13: uz_version"
    assert any(l.startswith("check 2/2 cbu_reg_3030:main:13: calling LLM test-model (attempt 1")
               for l in lines)
    assert any("input / " in l and "output tokens" in l for l in lines)
    assert lines[-1] == "check 2/2 cbu_reg_3030:main:13: ok"
