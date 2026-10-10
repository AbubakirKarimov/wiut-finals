"""SQLite storage: requirements, pages, findings, decisions, jobs, LLM call log and cache."""

import hashlib
import json
import os
import sqlite3
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime
from pathlib import Path
from typing import Iterator

from dotenv import load_dotenv

from backend.models import Decision, Finding, Job, Page, Requirement, Run, utcnow

load_dotenv()

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB_PATH = ROOT / "data" / "compliance.sqlite"

SCHEMA = """
CREATE TABLE IF NOT EXISTS requirements (
    id TEXT PRIMARY KEY,
    text_original TEXT NOT NULL,
    text_en TEXT,
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
    evidence_quote_en TEXT,
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
    cache_hit INTEGER NOT NULL DEFAULT 0,
    cache_key TEXT,
    error TEXT,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS runs (
    id TEXT PRIMARY KEY,
    bank_id TEXT NOT NULL,
    start_url TEXT NOT NULL,
    source TEXT NOT NULL,
    status TEXT NOT NULL,
    crawl_status TEXT,
    crawl_reason TEXT,
    pages_read INTEGER NOT NULL DEFAULT 0,
    fetch_errors TEXT NOT NULL DEFAULT '[]',
    has_language_switcher INTEGER,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    error TEXT
);
CREATE INDEX IF NOT EXISTS idx_runs_bank ON runs(bank_id);
CREATE TABLE IF NOT EXISTS consistency (
    id TEXT PRIMARY KEY,
    bank_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    run_ids TEXT NOT NULL,
    n_requirements INTEGER NOT NULL,
    status_agreement REAL,
    quote_agreement REAL,
    per_requirement TEXT NOT NULL,
    models TEXT NOT NULL DEFAULT '[]'
);
CREATE TABLE IF NOT EXISTS llm_cache (
    key TEXT PRIMARY KEY,
    provider TEXT NOT NULL,
    model TEXT NOT NULL,
    response_json TEXT NOT NULL,
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
        # Migrations for databases created by earlier versions of the schema.
        for table, column, decl in MIGRATIONS:
            cols = {r["name"] for r in conn.execute(f"PRAGMA table_info({table})")}
            if column not in cols:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {decl}")


MIGRATIONS = [
    ("llm_calls", "cache_key", "TEXT"),
    ("llm_calls", "run_id", "TEXT"),
    ("pages", "title", "TEXT NOT NULL DEFAULT ''"),
    ("pages", "run_id", "TEXT"),
    ("pages", "request_url", "TEXT"),
    ("pages", "links", "TEXT NOT NULL DEFAULT '{}'"),
    ("findings", "run_id", "TEXT"),
    ("findings", "pages_read", "INTEGER"),
    ("findings", "urls_read", "TEXT NOT NULL DEFAULT '[]'"),
    ("findings", "reason", "TEXT"),
    ("findings", "context_quote", "TEXT"),
    ("findings", "decided_by", "TEXT"),
    ("jobs", "progress", "TEXT NOT NULL DEFAULT ''"),
]

# Run id of the check currently executing in this thread/context; stamped on llm_calls so
# tokens and cost can be attributed per check.
current_run_id: ContextVar[str | None] = ContextVar("current_run_id", default=None)


def _ts(value: datetime) -> str:
    return value.isoformat()


# --- requirements ---

def upsert_requirement(conn: sqlite3.Connection, req: Requirement) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO requirements VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (req.id, req.text_original, req.text_en, req.source_doc, req.source_clause_id,
         req.source_url, req.check_type, int(req.approved)),
    )


def list_requirements(conn: sqlite3.Connection, approved_only: bool = False) -> list[Requirement]:
    sql = "SELECT * FROM requirements" + (" WHERE approved = 1" if approved_only else "")
    return [Requirement(**{**dict(r), "approved": bool(r["approved"])}) for r in conn.execute(sql)]


# --- pages (crawl cache) ---

def _insert(conn: sqlite3.Connection, table: str, row: dict) -> None:
    cols = ", ".join(row)
    marks = ", ".join("?" for _ in row)
    conn.execute(f"INSERT OR REPLACE INTO {table} ({cols}) VALUES ({marks})",
                 tuple(row.values()))


def upsert_page(conn: sqlite3.Connection, page: Page, links: dict | None = None,
                request_url: str | None = None) -> None:
    """links: crawl metadata kept so a later run can reuse the page without fetching it
    ({"links": [[url, anchor], ...], "lang": {...}, "method": "httpx"})."""
    _insert(conn, "pages", {
        "bank_id": page.bank_id, "url": page.url, "language": page.language,
        "text": page.text, "source_type": page.source_type,
        "fetched_at": _ts(page.fetched_at), "readable": int(page.readable),
        "title": page.title, "run_id": page.run_id, "request_url": request_url,
        "links": json.dumps(links or {}, ensure_ascii=False)})


def get_cached_page(conn: sqlite3.Connection, bank_id: str, url: str,
                    fetched_after: datetime) -> tuple[Page, dict] | None:
    """A stored page for this URL (requested or final) fetched after the given time."""
    row = conn.execute(
        "SELECT * FROM pages WHERE bank_id = ? AND (url = ? OR request_url = ?) "
        "AND fetched_at >= ? ORDER BY fetched_at DESC LIMIT 1",
        (bank_id, url, url, _ts(fetched_after))).fetchone()
    if row is None:
        return None
    d = dict(row)
    links = json.loads(d.pop("links") or "{}")
    d.pop("request_url", None)
    return Page(**{**d, "readable": bool(d["readable"])},
                links=[tuple(x) for x in links.get("links") or []]), links


def list_pages(conn: sqlite3.Connection, bank_id: str, run_id: str | None = None) -> list[Page]:
    if run_id:
        rows = conn.execute("SELECT * FROM pages WHERE bank_id = ? AND run_id = ? ORDER BY url",
                            (bank_id, run_id))
    else:
        rows = conn.execute("SELECT * FROM pages WHERE bank_id = ? ORDER BY url", (bank_id,))
    return [_page(r) for r in rows]


def _page(row: sqlite3.Row) -> Page:
    d = dict(row)
    meta = json.loads(d.pop("links", None) or "{}")
    d.pop("request_url", None)
    return Page(**{**d, "readable": bool(d["readable"])},
                links=[tuple(x) for x in meta.get("links") or []])


# --- findings ---

def upsert_finding(conn: sqlite3.Connection, finding: Finding) -> None:
    _insert(conn, "findings", {
        "id": finding.id, "bank_id": finding.bank_id,
        "requirement_id": finding.requirement_id, "status": finding.status,
        "evidence_url": finding.evidence_url, "evidence_quote": finding.evidence_quote,
        "evidence_quote_en": finding.evidence_quote_en, "confidence": finding.confidence,
        "created_at": _ts(finding.created_at), "run_id": finding.run_id,
        "pages_read": finding.pages_read,
        "urls_read": json.dumps(finding.urls_read, ensure_ascii=False),
        "reason": finding.reason, "context_quote": finding.context_quote,
        "decided_by": finding.decided_by})


def _finding(row: sqlite3.Row) -> Finding:
    d = dict(row)
    d["urls_read"] = json.loads(d.get("urls_read") or "[]")
    return Finding(**d)


def get_finding(conn: sqlite3.Connection, finding_id: str) -> Finding | None:
    row = conn.execute("SELECT * FROM findings WHERE id = ?", (finding_id,)).fetchone()
    return _finding(row) if row else None


def list_findings(conn: sqlite3.Connection, bank_id: str | None = None,
                  run_id: str | None = None) -> list[Finding]:
    where, args = [], []
    if bank_id is not None:
        where.append("bank_id = ?")
        args.append(bank_id)
    if run_id is not None:
        where.append("run_id = ?")
        args.append(run_id)
    sql = "SELECT * FROM findings" + (" WHERE " + " AND ".join(where) if where else "")
    return [_finding(r) for r in conn.execute(sql + " ORDER BY created_at", args)]


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
    _insert(conn, "jobs", {
        "id": job.id, "url": job.url, "status": job.status, "result_ref": job.result_ref,
        "error": job.error, "created_at": _ts(job.created_at), "progress": job.progress})


# --- runs ---

def upsert_run(conn: sqlite3.Connection, run: Run) -> None:
    _insert(conn, "runs", {
        "id": run.id, "bank_id": run.bank_id, "start_url": run.start_url,
        "source": run.source, "status": run.status, "crawl_status": run.crawl_status,
        "crawl_reason": run.crawl_reason, "pages_read": run.pages_read,
        "fetch_errors": json.dumps(run.fetch_errors, ensure_ascii=False),
        "has_language_switcher": (None if run.has_language_switcher is None
                                  else int(run.has_language_switcher)),
        "started_at": _ts(run.started_at),
        "finished_at": _ts(run.finished_at) if run.finished_at else None,
        "error": run.error})


def _run(row: sqlite3.Row) -> Run:
    d = dict(row)
    d["fetch_errors"] = json.loads(d["fetch_errors"] or "[]")
    if d["has_language_switcher"] is not None:
        d["has_language_switcher"] = bool(d["has_language_switcher"])
    return Run(**d)


def get_run(conn: sqlite3.Connection, run_id: str) -> Run | None:
    row = conn.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
    return _run(row) if row else None


def list_runs(conn: sqlite3.Connection, bank_id: str | None = None) -> list[Run]:
    if bank_id is None:
        rows = conn.execute("SELECT * FROM runs ORDER BY started_at DESC")
    else:
        rows = conn.execute("SELECT * FROM runs WHERE bank_id = ? ORDER BY started_at DESC",
                            (bank_id,))
    return [_run(r) for r in rows]


def get_job(conn: sqlite3.Connection, job_id: str) -> Job | None:
    row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
    return Job(**dict(row)) if row else None


# --- LLM call log and response cache ---

def llm_cache_key(provider: str, model: str, prompt: str, schema: dict,
                  namespace: str = "") -> str:
    """namespace="" keeps the normal shared cache; another namespace (e.g. a consistency
    re-run) gets its own entries, so its answers come from fresh API calls."""
    parts = [provider, model, prompt, schema] + ([namespace] if namespace else [])
    payload = json.dumps(parts, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def llm_cache_get(conn: sqlite3.Connection, key: str) -> dict | None:
    row = conn.execute("SELECT response_json FROM llm_cache WHERE key = ?", (key,)).fetchone()
    return json.loads(row["response_json"]) if row else None


def llm_cache_put(conn: sqlite3.Connection, key: str, provider: str, model: str,
                  response: dict) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO llm_cache VALUES (?, ?, ?, ?, ?)",
        (key, provider, model, json.dumps(response, ensure_ascii=False), _ts(utcnow())),
    )


def log_llm_call(conn: sqlite3.Connection, *, provider: str, model: str,
                 input_tokens: int | None, output_tokens: int | None, duration_ms: float,
                 ok: bool, cache_hit: bool, error: str | None = None,
                 cache_key: str | None = None) -> None:
    conn.execute(
        "INSERT INTO llm_calls (provider, model, input_tokens, output_tokens, duration_ms, "
        "ok, cache_hit, cache_key, error, created_at, run_id) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (provider, model, input_tokens, output_tokens, duration_ms, int(ok), int(cache_hit),
         cache_key, error, _ts(utcnow()), current_run_id.get()),
    )
