"""Data contract shared by ingest, crawl, checks and API."""

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field

CheckType = Literal["uz_version", "required_document", "key_info"]
Language = Literal["uz_latn", "uz_cyrl", "ru", "other"]
SourceType = Literal["html", "pdf"]
# A finding is never a "violation": only a possible gap for an analyst to review.
FindingStatus = Literal["ok", "possible_gap", "not_checkable"]
Verdict = Literal["confirmed", "rejected"]
JobStatus = Literal["queued", "running", "done", "error"]


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Requirement(BaseModel):
    id: str
    text: str
    source_doc: str
    source_clause_id: str
    source_url: str
    check_type: CheckType
    approved: bool = False


class Page(BaseModel):
    bank_id: str
    url: str
    language: Language
    text: str
    source_type: SourceType
    fetched_at: datetime = Field(default_factory=utcnow)
    readable: bool = True


class Finding(BaseModel):
    id: str
    bank_id: str
    requirement_id: str
    status: FindingStatus
    evidence_url: str | None = None
    evidence_quote: str | None = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    created_at: datetime = Field(default_factory=utcnow)


class Decision(BaseModel):
    finding_id: str
    analyst: str
    verdict: Verdict
    comment: str = ""
    decided_at: datetime = Field(default_factory=utcnow)


class Job(BaseModel):
    id: str
    url: str
    status: JobStatus = "queued"
    result_ref: str | None = None
    error: str | None = None
    created_at: datetime = Field(default_factory=utcnow)
