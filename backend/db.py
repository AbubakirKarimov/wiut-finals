"""SQLite storage for requirements, pages, findings, decisions, jobs and LLM call logs."""

import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Iterator

from dotenv import load_dotenv

from backend.models import Decision, Finding, Job, Page, Requirement

load_dotenv()

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB_PATH = ROOT / "data" / "compliance.sqlite"

SCHEMA = """
CREATE TABLE IF NOT EXISTS requirements (
    id TEXT PRIMARY KEY,
    text TEXT NOT NULL,
    source_doc TEXT NOT NULL,
    source_clause_id TEXT NOT NULL,
    source_url TEXT NOT NULL,
    check_type TEXT NOT NULL,
    approved INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS pages (
    bank_id TEXT NOT NULL,
    url TEXT NOT NULL,
    language TEXT NOT NULL,
    text TEXT NOT NULL,
    source_type TEXT NOT NULL,
    fetched_at TEXT NOT NULL,
    readable INTEGER NOT NULL,
    PRIMARY KEY (bank_id, url)
);
CREATE TABLE IF NOT EXISTS findings (
    id TEXT PRIMARY KEY,
    bank_id TEXT NOT NULL,
    requirement_id TEXT NOT NULL,
    status TEXT NOT NULL,
    evidence_url TEXT,
    evidence_quote TEXT,
    confidence REAL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_findings_bank ON findings(bank_id);
CREATE TABLE IF NOT EXISTS decisions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    finding_id TEXT NOT NULL REFERENCES findings(id),
    analyst TEXT NOT NULL,
    verdict TEXT NOT NULL,
    comment TEXT NOT NULL DEFAULT '',
    decided_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS jobs (
    id TEXT PRIMARY KEY,
    url TEXT NOT NULL,
    status TEXT NOT NULL,
    result_ref TEXT,
    error TEXT,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS llm_calls (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    provider TEXT NOT NULL,
    model TEXT NOT NULL,
    input_tokens INTEGER,
    output_tokens INTEGER,
    duration_ms REAL NOT NULL,
    ok INTEGER NOT NULL,
    error TEXT,
    created_at TEXT NOT NULL
);
"""


def db_path() -> Path:
    return Path(os.getenv("DB_PATH") or DEFAULT_DB_PATH)


@contextmanager
def connect(path: Path | str | None = None) -> Iterator[sqlite3.Connection]:
    conn = sqlite3.connect(str(path or db_path()))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db(path: Path | str | None = None) -> None:
    target = Path(path or db_path())
    target.parent.mkdir(parents=True, exist_ok=True)
    with connect(target) as conn:
        conn.executescript(SCHEMA)


def _ts(value: datetime) -> str:
    return value.isoformat()


# --- requirements ---

def upsert_requirement(conn: sqlite3.Connection, req: Requirement) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO requirements VALUES (?, ?, ?, ?, ?, ?, ?)",
        (req.id, req.text, req.source_doc, req.source_clause_id, req.source_url,
         req.check_type, int(req.approved)),
    )


def list_requirements(conn: sqlite3.Connection, approved_only: bool = False) -> list[Requirement]:
    sql = "SELECT * FROM requirements" + (" WHERE approved = 1" if approved_only else "")
    return [Requirement(**{**dict(r), "approved": bool(r["approved"])}) for r in conn.execute(sql)]


# --- pages (crawl cache) ---

def upsert_page(conn: sqlite3.Connection, page: Page) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO pages VALUES (?, ?, ?, ?, ?, ?, ?)",
        (page.bank_id, page.url, page.language, page.text, page.source_type,
         _ts(page.fetched_at), int(page.readable)),
    )


def list_pages(conn: sqlite3.Connection, bank_id: str) -> list[Page]:
    rows = conn.execute("SELECT * FROM pages WHERE bank_id = ? ORDER BY url", (bank_id,))
    return [Page(**{**dict(r), "readable": bool(r["readable"])}) for r in rows]


# --- findings ---

def upsert_finding(conn: sqlite3.Connection, finding: Finding) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO findings VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (finding.id, finding.bank_id, finding.requirement_id, finding.status,
         finding.evidence_url, finding.evidence_quote, finding.confidence,
         _ts(finding.created_at)),
    )


def get_finding(conn: sqlite3.Connection, finding_id: str) -> Finding | None:
    row = conn.execute("SELECT * FROM findings WHERE id = ?", (finding_id,)).fetchone()
    return Finding(**dict(row)) if row else None


def list_findings(conn: sqlite3.Connection, bank_id: str | None = None) -> list[Finding]:
    if bank_id is None:
        rows = conn.execute("SELECT * FROM findings ORDER BY created_at")
    else:
        rows = conn.execute(
            "SELECT * FROM findings WHERE bank_id = ? ORDER BY created_at", (bank_id,))
    return [Finding(**dict(r)) for r in rows]


# --- decisions ---

def add_decision(conn: sqlite3.Connection, decision: Decision) -> None:
    conn.execute(
        "INSERT INTO decisions (finding_id, analyst, verdict, comment, decided_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (decision.finding_id, decision.analyst, decision.verdict, decision.comment,
         _ts(decision.decided_at)),
    )


def list_decisions(conn: sqlite3.Connection) -> list[Decision]:
    rows = conn.execute(
        "SELECT finding_id, analyst, verdict, comment, decided_at FROM decisions "
        "ORDER BY decided_at DESC")
    return [Decision(**dict(r)) for r in rows]


# --- jobs ---

def upsert_job(conn: sqlite3.Connection, job: Job) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO jobs VALUES (?, ?, ?, ?, ?, ?)",
        (job.id, job.url, job.status, job.result_ref, job.error, _ts(job.created_at)),
    )


def get_job(conn: sqlite3.Connection, job_id: str) -> Job | None:
    row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
    return Job(**dict(row)) if row else None
