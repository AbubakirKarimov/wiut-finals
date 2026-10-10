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
# "code": the status was decided by deterministic code alone; "llm_assisted": an LLM answer
# influenced the status (its quote still verified by code). Translation does not count.
DecidedBy = Literal["code", "llm_assisted"]
JobStatus = Literal["queued", "running", "done", "error"]


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Requirement(BaseModel):
    id: str
    text_original: str  # clause wording in the source language (ru/uz)
    text_en: str | None = None
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
    title: str = ""
    run_id: str | None = None


class Finding(BaseModel):
    id: str
    bank_id: str
    requirement_id: str
    status: FindingStatus
    evidence_url: str | None = None
    # Verbatim quote in the page's original language; verified against page text.
    evidence_quote: str | None = None
    # Machine translation of evidence_quote; never used for verification.
    evidence_quote_en: str | None = None
    # "No evidence found" findings: a verbatim passage of the closest page (evidence_url),
    # verified like a quote but shown as context only. evidence_quote is then empty.
    context_quote: str | None = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    created_at: datetime = Field(default_factory=utcnow)
    run_id: str | None = None
    # How much of the site was read before deciding (stored for every finding).
    pages_read: int | None = None
    urls_read: list[str] = Field(default_factory=list)
    # Why the status was chosen (e.g. "needs browser", "quote not found verbatim").
    reason: str | None = None
    # None only for findings stored before this field existed ("not recorded").
    decided_by: DecidedBy | None = None


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
    result_ref: str | None = None  # run id once the crawl has started
    error: str | None = None
    created_at: datetime = Field(default_factory=utcnow)
    progress: str = ""


RunStatus = Literal["running", "done", "error"]


class Run(BaseModel):
    """One crawl + check of one site (from POST /check or scripts/crawl_all.py)."""
    id: str
    bank_id: str
    start_url: str
    # job = POST /check; batch = scripts/crawl_all.py; precomputed = loaded from
    # data/precomputed/findings.json; consistency = repeat run for the consistency metric
    source: Literal["job", "batch", "precomputed", "consistency"] = "job"
    status: RunStatus = "running"
    crawl_status: str | None = None  # ok | blocked | unreachable | needs_browser | ...
    crawl_reason: str | None = None
    pages_read: int = 0
    fetch_errors: list[str] = Field(default_factory=list)
    has_language_switcher: bool | None = None
    started_at: datetime = Field(default_factory=utcnow)
    finished_at: datetime | None = None
    error: str | None = None
