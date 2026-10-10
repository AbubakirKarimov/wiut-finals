"""Shortlist and approval tests: real parsed clauses, fake LLM provider, temp output paths."""

import json

import pytest
import yaml

from backend import db
from backend.llm import provider as llm
from backend.requirements import approve as approve_mod
from backend.requirements import shortlist as sl
from backend.tests.test_llm import FakeProvider

CHECKABLE = json.dumps({
    "checkable_from_public_website": True, "check_type": "required_document",
    "requirement_en": "The bank must have its own official website.",
    "evidence_hint": "An official website of the bank exists and is reachable.",
    "not_checkable_reason": None, "confidence": 0.9})
NOT_CHECKABLE = json.dumps({
    "checkable_from_public_website": False, "check_type": None,
    "requirement_en": "Texts of signs and announcements must be in the state language.",
    "evidence_hint": None,
    "not_checkable_reason": "Concerns physical signs, not the website.", "confidence": 0.6})


@pytest.fixture(scope="module")
def clauses():
    return {c["clause_id"]: c for c in sl.load_clauses()}


def test_eligible_clauses_exclude_forms_and_repealed(clauses):
    assert len(clauses) == 175
    assert not any(c["clause_id"].endswith(":form") for c in clauses.values())


def test_prefilter_keeps_always_include_and_matches_both_scripts(clauses):
    passed = {c["clause_id"]: c for c in sl.prefilter(list(clauses.values()))}
    assert set(sl.ALWAYS_INCLUDE) <= passed.keys()
    c13 = passed["cbu_reg_3030:main:13"]["prefilter"]
    assert "website" in c13["topics"] and c13["always_include"]
    assert "веб-сайт" in c13["keywords"]["website"] and "veb-sayt" in c13["keywords"]["website"]
    assert "state_language" in passed["law_state_language:art:20"]["prefilter"]["topics"]
    # Art. 15 (writing one's own name) has none of the topic keywords.
    assert "law_state_language:art:15" not in passed


def test_normalize_apostrophes():
    assert sl.normalize("Oʻzbek TILI") == sl.normalize("O‘zbek tili") == "o'zbek tili"


def test_prompt_is_english_and_quotes_clause_verbatim(clauses):
    c = sl.prefilter([clauses["cbu_reg_3030:main:13"]])[0]
    prompt = sl.build_prompt(c)
    assert "checked from the bank's PUBLIC website alone" in prompt
    assert c["text_original"] in prompt
    assert "2-§. Банкнинг расмий веб-сайтида" in prompt


def test_assessment_schema_consistency():
    with pytest.raises(ValueError):
        sl.ClauseAssessment.model_validate(
            {**json.loads(CHECKABLE), "check_type": None})
    with pytest.raises(ValueError):
        sl.ClauseAssessment.model_validate(
            {**json.loads(NOT_CHECKABLE), "not_checkable_reason": None})


@pytest.fixture
def assessed(tmp_db, clauses):
    items = sl.prefilter([clauses["cbu_reg_3030:main:13"],
                          clauses["law_state_language:art:20"],
                          clauses["law_state_language:art:16"]])
    fake = FakeProvider([CHECKABLE, NOT_CHECKABLE, NOT_CHECKABLE], db_path=tmp_db)
    return sl.assess(items, fake), fake


def test_assess_builds_candidates(assessed):
    candidates, fake = assessed
    by_id = {c["clause_id"]: c for c in candidates}
    c13 = by_id["cbu_reg_3030:main:13"]
    assert c13["checkable"] and c13["check_type"] == "required_document"
    assert c13["text_en_label"] == "machine translation"
    assert c13["url"] == "https://lex.uz/ru/docs/3804290#3804958"
    # Not checkable, but always included for human review.
    art20 = by_id["law_state_language:art:20"]
    assert not art20["checkable"] and art20["shortlisted"]
    assert not by_id["law_state_language:art:16"]["shortlisted"]
    assert all(c["approved"] is False for c in candidates)
    assert fake.calls == 3


def test_rerun_uses_cache(tmp_db, clauses):
    items = sl.prefilter([clauses["cbu_reg_3030:main:13"]])
    first = FakeProvider([CHECKABLE], db_path=tmp_db)
    sl.assess(items, first)
    again = FakeProvider([], db_path=tmp_db)  # would fail if it were called
    assert sl.assess(items, again)[0]["check_type"] == "required_document"
    assert again.calls == 0


def test_write_outputs(tmp_path, assessed):
    candidates, _ = assessed
    cpath, rpath = tmp_path / "c.json", tmp_path / "r.md"
    sl.write_outputs(candidates, {"eligible clauses": 3}, "fake, model fake-model",
                     candidates_path=cpath, review_path=rpath)
    data = json.loads(cpath.read_text(encoding="utf-8"))
    assert len(data["candidates"]) == 3
    md = rpath.read_text(encoding="utf-8")
    assert "### cbu_reg_3030:main:13" in md and "Requirement (English, machine translation)" in md
    assert "https://lex.uz/ru/docs/3804290#3804958" in md
    assert "13. Банк ўзининг расмий веб-сайтига эга бўлиши шарт." in md
    assert "| law_state_language:art:16 |" in md  # listed as not checkable


def test_main_without_key_fails_clearly(monkeypatch, tmp_db, capsys):
    for k in ("LLM_BASE_URL", "LLM_API_KEY", "LLM_MODEL", "LLM_FALLBACK_1_BASE_URL",
              "LLM_FALLBACK_1_API_KEY", "LLM_FALLBACK_1_MODEL"):
        monkeypatch.setenv(k, "")
    assert sl.main([]) == 2
    assert "LLM_BASE_URL, LLM_API_KEY, LLM_MODEL not set in .env" in capsys.readouterr().err


def test_approve_flow(tmp_path, tmp_db, assessed):
    candidates, _ = assessed
    cpath, ypath = tmp_path / "c.json", tmp_path / "requirements.yaml"
    sl.write_outputs(candidates, {}, "fake", candidates_path=cpath,
                     review_path=tmp_path / "r.md")
    done = approve_mod.approve(["cbu_reg_3030:main:13"], candidates_path=cpath,
                               yaml_path=ypath, db_path=tmp_db)
    assert [r.id for r in done] == ["req:cbu_reg_3030:main:13"]
    with db.connect(tmp_db) as conn:
        [req] = db.list_requirements(conn, approved_only=True)
    assert req.check_type == "required_document" and req.text_en.startswith("The bank must")
    rows = yaml.safe_load(ypath.read_text(encoding="utf-8"))["requirements"]
    assert rows[0]["source_clause_id"] == "cbu_reg_3030:main:13"
    assert rows[0]["text_en_label"] == "machine translation"

    with pytest.raises(ValueError, match="no proposed check_type"):
        approve_mod.approve(["law_state_language:art:20"], candidates_path=cpath,
                            yaml_path=ypath, db_path=tmp_db)
    approve_mod.approve(["law_state_language:art:20"], "uz_version", candidates_path=cpath,
                        yaml_path=ypath, db_path=tmp_db)
    assert len(yaml.safe_load(ypath.read_text(encoding="utf-8"))["requirements"]) == 2
    with pytest.raises(ValueError, match="not in"):
        approve_mod.approve(["nope:1"], candidates_path=cpath, yaml_path=ypath,
                            db_path=tmp_db)
