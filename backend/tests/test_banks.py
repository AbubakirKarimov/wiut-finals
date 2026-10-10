import pytest
from pydantic import ValidationError

from backend.crawl.banks import BANKS_YAML, crawlable_banks, load_banks


def _write(tmp_path, body: str):
    p = tmp_path / "banks.yaml"
    p.write_text("banks:\n" + body, encoding="utf-8")
    return p


def _entry(id_: str, url: str = "", role: str = "fined_group") -> str:
    return f'  - id: {id_}\n    name: "X"\n    website_url: "{url}"\n    role: {role}\n    notes: ""\n'


def test_registry_loads_and_is_consistent():
    banks = load_banks(BANKS_YAML)
    ids = [b.id for b in banks]
    assert len(ids) == len(set(ids))
    assert [b.id for b in banks if b.role == "partner"] == ["mkbank"]
    assert sum(b.role == "fined_group" for b in banks) == 20
    for b in banks:
        assert b.website_url == "" or b.website_url.startswith("https://"), b.id


def test_empty_urls_are_skipped_by_crawler(tmp_path):
    p = _write(tmp_path, _entry("a") + _entry("b", "https://example.uz/"))
    assert [b.id for b in load_banks(p)] == ["a", "b"]
    assert [b.id for b in crawlable_banks(p)] == ["b"]


@pytest.mark.parametrize("url", ["http://example.uz", "example.uz", "https://", "ftp://example.uz",
                                 "https://localhost"])
def test_invalid_urls_rejected(tmp_path, url):
    with pytest.raises(ValidationError):
        load_banks(_write(tmp_path, _entry("a", url)))


def test_duplicate_ids_rejected(tmp_path):
    with pytest.raises(ValueError, match="duplicate bank id"):
        load_banks(_write(tmp_path, _entry("a") + _entry("a")))


def test_unknown_role_rejected(tmp_path):
    with pytest.raises(ValidationError):
        load_banks(_write(tmp_path, _entry("a", role="violator")))
