"""Tests for the lex.uz parser on small fixtures cut from real saved pages (no network)."""

import json
from pathlib import Path

import httpx
import pytest

from backend.ingest import lex

FIX = Path(__file__).resolve().parent / "fixtures"
REGULATIONS = Path(__file__).resolve().parents[2] / "data" / "regulations"
FETCHED = "2026-10-10T12:00:00+00:00"


def _read(name: str) -> str:
    return (FIX / name).read_text(encoding="utf-8")


def parse(name: str, *, source_id: str, role: str, doc_id: str, latin: bool = True) -> dict:
    return lex.parse_document(
        _read(f"{name}_cyrl.html" if latin else f"{name}.html"),
        source_id=source_id, doc_id=doc_id, role=role,
        language="uz_cyrl" if latin else "ru",
        latin_html=_read(f"{name}_latn.html") if latin else None,
        latin_doc_id=f"-{doc_id}" if latin else None, fetched_at=FETCHED)


@pytest.fixture(scope="module")
def body():
    return parse("reg3030_body", source_id="cbu_reg_3030", role="regulation", doc_id="3804290")


@pytest.fixture(scope="module")
def annex():
    return parse("reg3030_annex", source_id="cbu_reg_3030", role="regulation", doc_id="3804290")


@pytest.fixture(scope="module")
def law():
    return parse("law", source_id="law_state_language", role="law", doc_id="121051")


def by_id(doc: dict) -> dict:
    return {c["clause_id"]: c for c in doc["clauses"]}


def test_output_schema(body):
    assert body["source_snapshot_date"] == "2026-10-10"
    assert body["fetched_at"] == FETCHED
    assert body["parallel"]["doc_id"] == "-3804290"
    keys = {"clause_id", "number", "chapter", "paragraph", "annex", "block_ids",
            "text_original", "text_parallel_latn", "url", "amendment_notes", "repealed", "kind"}
    for c in body["clauses"]:
        assert keys <= c.keys()
        assert c["url"].startswith("https://lex.uz/ru/docs/3804290#")


def test_wrapper_and_body_clause_1_have_distinct_ids(body):
    ids = by_id(body)
    assert "cbu_reg_3030:resolution:1" in ids
    assert "cbu_reg_3030:main:1" in ids
    assert ids["cbu_reg_3030:resolution:1"]["text_original"].startswith("1. Банк хизматлари")
    assert ids["cbu_reg_3030:main:1"]["text_original"].startswith("1. Мазкур Низомда")


def test_superscript_clause(body):
    c = by_id(body)["cbu_reg_3030:main:6^1"]
    assert c["number"] == "6^1"
    assert c["text_original"].startswith("6^1. Истеъмолчи банк хизматларини")
    # The fixture keeps the clause's first two paragraphs (separate blocks on the page).
    assert c["block_ids"] == ["4427441", "4427448"]
    assert c["text_original"].split("\n")[1] == (
        "Банк истеъмолчини ушбу ҳуқуққа эга эканлиги тўғрисида хабардор қилиши лозим.")
    assert c["url"] == "https://lex.uz/ru/docs/3804290#4427441"


def test_sub_clause_attached_to_parent(body):
    c = by_id(body)["cbu_reg_3030:main:9"]
    lines = c["text_original"].split("\n")
    assert lines[0].startswith("9. Банк томонидан кредит")
    assert lines[1].startswith("а) кредит бўйича")
    assert len(c["block_ids"]) == 2
    assert c["text_parallel_latn"].split("\n")[1].startswith("a) kredit boʻyicha")


def test_chapter_and_paragraph_context(body):
    c = by_id(body)["cbu_reg_3030:main:13"]
    assert c["chapter"].startswith("2-боб.")
    assert c["paragraph"] == "2-§. Банкнинг расмий веб-сайтида ахборот бериш хусусиятлари"
    assert c["text_original"] == "13. Банк ўзининг расмий веб-сайтига эга бўлиши шарт."


def test_notes_and_comments_dropped_but_notes_recorded(body):
    texts = "\n".join(c["text_original"] for c in body["clauses"])
    assert "Олдинги таҳрирга қаранг" not in texts
    assert "ОКОЗ" not in texts                       # INDEXES_ON_REF
    assert "Аудио" not in texts and "Прослушать" not in texts  # toolbar
    assert "рўйхат рақами 3030-6" not in texts       # CHANGES_ORIGINS is not clause text
    c = by_id(body)["cbu_reg_3030:main:40^1"]
    assert [n["amending_act"] for n in c["amendment_notes"]] == ["3030-6"]
    assert c["amendment_notes"][0]["change"] == "added"


def test_section_level_repeal_note_does_not_repeal_previous_clause(body):
    # The "3-параграф ... ўз кучини йўқотган" note follows clause 40^1 on the page.
    assert by_id(body)["cbu_reg_3030:main:40^1"]["repealed"] is False
    [note] = [n for n in body["unattached_notes"] if n["change"] == "repealed"]
    assert note["amending_act"] == "3030-5"
    assert note["text"].startswith("(3-параграф")


def test_annex_resets_numbering_and_form_kind(annex):
    ids = by_id(annex)
    assert "cbu_reg_3030:main:60" in ids
    c = ids["cbu_reg_3030:annex1:1"]
    assert c["annex"] == "1" and c["kind"] == "text"
    assert c["text_original"].startswith("1. Мазкур Тартибда")
    form = ids["cbu_reg_3030:annex3b:form"]
    assert form["kind"] == "form" and form["annex"] == "3b"
    assert " | " in form["text_original"]            # table flattened into rows of cells
    assert {a["annex"]: a["kind"] for a in annex["annexes"]} == {"1": "text", "3b": "form"}


def test_latin_alignment(body, law):
    for doc in (body, law):
        for c in doc["clauses"]:
            assert c["text_parallel_latn"]
            assert c["text_original"].count("\n") == c["text_parallel_latn"].count("\n")
    assert by_id(body)["cbu_reg_3030:main:13"]["text_parallel_latn"] == (
        "13. Bank oʻzining rasmiy veb-saytiga ega boʻlishi shart.")
    assert lex.latin_block_id("onLBC121105") == "onLBC-121105"
    assert lex.latin_block_id("edi5009738") == "edi-5009738"


def test_latin_misalignment_raises():
    cyr = _read("reg3030_body_cyrl.html")
    lat = _read("reg3030_body_latn.html").replace('id="-4427441"', 'id="-1"')
    with pytest.raises(lex.AlignmentError):
        lex.parse_document(cyr, source_id="x", doc_id="3804290", role="regulation",
                           language="uz_cyrl", latin_html=lat)


def test_law_articles(law):
    ids = by_id(law)
    assert "law_state_language:enactment:preamble" in ids
    a1 = ids["law_state_language:art:1"]
    assert a1["text_original"] == "1-модда.\nЎзбекистон Республикасининг давлат тили ўзбек тилидир."
    assert a1["text_parallel_latn"].startswith("1-modda.")
    a3 = ids["law_state_language:art:3"]
    assert a3["amendment_notes"][0]["amending_act"] == "ЎРҚ-683"
    assert "LexUZ шарҳи" not in a1["text_original"]


def test_repealed_clause_kept():
    doc = parse("pp3620_ru", source_id="pp_3620", role="reference", doc_id="3593543",
                latin=False)
    ids = by_id(doc)
    for n in ("1", "2"):
        c = ids[f"pp_3620:act:{n}"]
        assert c["repealed"] is True and c["text_original"] == ""
        assert c["amendment_notes"][0]["amending_act"] == "УП-152"
    assert ids["pp_3620:act:3"]["repealed"] is False


def test_repeal_wording_cyrillic_and_latin():
    assert lex.REPEAL_RE.search("13-банд ўз кучини йўқотган")
    assert lex.REPEAL_RE.search("13-band oʻz kuchini yoʻqotgan")
    assert lex.REPEAL_RE.search("пункт 1 утратил силу")
    assert not lex.REPEAL_RE.search("40^1-банд ... асосан киритилган")


def test_note_target_ranges_and_parts():
    assert lex.note_target("(36^1 — 36^4-бандлар Ўзбекистон ...)") == ([("36^1", "36^4")], True)
    assert lex.note_target("(35^3 ва 35^4-бандлар Ўзбекистон ...)") == (
        [("35^3", "35^3"), ("35^4", "35^4")], True)
    assert lex.note_target("(1-банднинг учинчи хатбошиси Ўзбекистон ...)") == (
        [("1", "1")], False)
    assert lex.note_target("(2-банд «в» кичик бандининг биринчи хатбошиси ...)")[1] is False
    assert lex.note_target("(3-параграф Ўзбекистон ...)") is None


def test_duplicate_clause_id_raises():
    html = _read("pp3620_ru.html").replace("3. Установить", "1. Установить")
    with pytest.raises(ValueError, match="duplicate clause_id"):
        lex.parse_document(html, source_id="pp_3620", doc_id="3593543", role="reference",
                           language="ru")


def test_committed_outputs_have_unique_clause_ids():
    files = sorted(REGULATIONS.glob("*.json"))
    assert files, "data/regulations/*.json missing"
    seen: dict[str, str] = {}
    for f in files:
        for c in json.loads(f.read_text(encoding="utf-8"))["clauses"]:
            assert c["clause_id"] not in seen, f"{c['clause_id']} in {f.name} and {seen[c['clause_id']]}"
            seen[c["clause_id"]] = f.name


# ---- fetching (network layer, exercised through an httpx test transport)

def _client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler), base_url=lex.LEX_BASE)


def test_fetch_doc_saves_page_and_meta(tmp_path, monkeypatch):
    monkeypatch.setenv("CRAWLER_MIN_DELAY_SECONDS", "0")
    page = _read("pp3620_ru.html")
    seen = []

    def handler(req):
        seen.append(req.url.path)
        if req.url.path == "/robots.txt":
            return httpx.Response(404)
        return httpx.Response(200, text=page)

    path = lex.fetch_doc("3593543", raw_dir=tmp_path, client=_client(handler),
                         polite=lex._Polite())
    assert seen == ["/robots.txt", "/ru/docs/3593543"]
    assert path.read_text(encoding="utf-8") == page
    meta = json.loads(path.with_suffix(".meta.json").read_text())
    assert meta["doc_id"] == "3593543" and meta["status"] == 200


@pytest.mark.parametrize("status,text", [(403, "Forbidden"), (200, "<html>captcha</html>")])
def test_fetch_doc_stops_on_block(tmp_path, monkeypatch, status, text):
    monkeypatch.setenv("CRAWLER_MIN_DELAY_SECONDS", "0")

    def handler(req):
        if req.url.path == "/robots.txt":
            return httpx.Response(404)
        return httpx.Response(status, text=text)

    with pytest.raises(lex.FetchError):
        lex.fetch_doc("1", raw_dir=tmp_path, client=_client(handler), polite=lex._Polite())
    assert not list(tmp_path.iterdir())


def test_fetch_doc_respects_robots_disallow(tmp_path, monkeypatch):
    monkeypatch.setenv("CRAWLER_MIN_DELAY_SECONDS", "0")

    def handler(req):
        if req.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nDisallow: /ru/docs/\n")
        raise AssertionError("document must not be requested")

    with pytest.raises(lex.FetchError, match="robots.txt disallows"):
        lex.fetch_doc("1", raw_dir=tmp_path, client=_client(handler), polite=lex._Polite())
