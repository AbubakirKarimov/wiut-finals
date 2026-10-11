"""Bank registry loader: data/banks.yaml -> validated Bank entries."""

from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

import yaml
from pydantic import BaseModel, field_validator

BANKS_YAML = Path(__file__).resolve().parents[2] / "data" / "banks.yaml"

BankRole = Literal["partner", "fined_group", "other"]


class Bank(BaseModel):
    id: str
    name: str
    website_url: str = ""  # empty = not filled in yet; the crawler skips the bank
    role: BankRole
    notes: str = ""

    @field_validator("id")
    @classmethod
    def _slug(cls, v: str) -> str:
        if not v or not all(c.islower() or c.isdigit() or c == "_" for c in v):
            raise ValueError(f"bank id must be a lowercase slug: {v!r}")
        return v

    @field_validator("website_url")
    @classmethod
    def _https(cls, v: str | None) -> str:
        v = (v or "").strip()
        if not v:
            return ""
        parts = urlsplit(v)
        if parts.scheme != "https" or not parts.hostname or "." not in parts.hostname:
            raise ValueError(f"website_url must be a valid https URL: {v!r}")
        return v

    @property
    def crawlable(self) -> bool:
        return bool(self.website_url)


def load_banks(path: Path = BANKS_YAML) -> list[Bank]:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    banks = [Bank.model_validate(e) for e in data.get("banks") or []]
    seen: set[str] = set()
    for b in banks:
        if b.id in seen:
            raise ValueError(f"duplicate bank id: {b.id}")
        seen.add(b.id)
    return banks


def crawlable_banks(path: Path = BANKS_YAML) -> list[Bank]:
    """Banks with a website_url; entries with an empty URL are skipped."""
    return [b for b in load_banks(path) if b.crawlable]
