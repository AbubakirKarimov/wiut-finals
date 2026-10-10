from pathlib import Path

import yaml

SOURCES = Path(__file__).resolve().parents[2] / "data" / "sources.yaml"
FIELDS = {"id", "title_original", "title_en", "lex_uz_doc_id", "url",
          "expected_regulation_number", "status", "language"}
LANGS = {"uz_cyrl", "uz_latn", "ru"}


def test_sources_registry_shape():
    entries = yaml.safe_load(SOURCES.read_text(encoding="utf-8"))["sources"]
    assert entries
    ids = [e["id"] for e in entries]
    assert len(ids) == len(set(ids))
    for e in entries:
        assert FIELDS <= e.keys(), e["id"]
        assert e["status"] in {"verified", "unverified"}
        assert e.get("role") in {"regulation", "law", "amendment", "reference"}, e["id"]
        assert e["language"] in LANGS, e["id"]
        if e["status"] == "verified":
            # A verified source must point at a concrete lex.uz document.
            assert e["lex_uz_doc_id"] and e["url"], e["id"]
        if e["role"] == "amendment":
            assert e.get("amends") in ids, e["id"]
        for p in e.get("parallel", []):
            assert p["language"] in LANGS | {"en"} and p["lex_uz_doc_id"], e["id"]
