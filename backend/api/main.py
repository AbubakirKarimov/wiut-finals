"""HTTP API for ComplianceRadar.

Run with a single worker (jobs, the rate limiter and the SQLite file live in one process):
    uvicorn backend.api.main:app --workers 1 --proxy-headers --forwarded-allow-ips="*"
"""

import os
import threading
import uuid
from contextlib import asynccontextmanager
from typing import Literal

from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from backend import db, metrics, precomputed, team_decisions
from backend.api.cors import cors_origins
from backend.api.ratelimit import limiter_from_env, rate_limit_dependency
from backend.api.urlcheck import allow_private, validate_public_url
from backend.checks.llm_checks import hint_title
from backend.crawl.banks import load_banks
from backend.crawl.crawler import CrawlConfig, Crawler
from backend.models import Decision, Job, Requirement
from backend.pipeline import check_site, sync_requirements_yaml

MT_LABEL = "machine translation"


@asynccontextmanager
async def lifespan(_: FastAPI):
    db.init_db()
    sync_requirements_yaml()
    # Hosted demo: an empty database starts with the committed pre-computed results.
    precomputed.load_if_empty()
    team_decisions.load()  # the team's decisions on those findings (idempotent)
    with db.connect() as conn:
        # Jobs cannot survive a restart (they run in this process).
        conn.execute("UPDATE jobs SET status = 'error', error = 'server restarted' "
                     "WHERE status IN ('queued', 'running')")
        conn.execute("UPDATE runs SET status = 'error', error = 'server restarted' "
                     "WHERE status = 'running'")
    yield


app = FastAPI(title="ComplianceRadar", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins(),
    allow_credentials=False,  # no cookies or auth headers cross-origin
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)

check_limiter = limiter_from_env()
_check_slots = threading.BoundedSemaphore(int(os.getenv("MAX_CONCURRENT_CHECKS") or 2))


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


# --- helpers ---

def _bank_names() -> dict[str, str]:
    return {b.id: b.name for b in load_banks()}


def _finding_rows(conn, where: str = "", args: tuple = ()) -> list[dict]:
    rows = conn.execute(
        "SELECT f.*, r.text_en AS req_text_en, r.text_original AS req_text_original, "
        "r.source_url AS req_source_url, r.source_clause_id AS req_clause_id, "
        "r.check_type AS req_check_type, "
        "ru.source AS run_source, ru.started_at AS run_started_at, "
        "ru.finished_at AS run_finished_at, ru.crawl_status AS run_crawl_status, "
        "ru.start_url AS run_start_url "
        "FROM findings f LEFT JOIN requirements r ON r.id = f.requirement_id "
        "LEFT JOIN runs ru ON ru.id = f.run_id " + where +
        " ORDER BY ru.finished_at DESC, f.bank_id, f.requirement_id", args).fetchall()
    decisions: dict[str, dict] = {}
    for d in conn.execute("SELECT * FROM decisions ORDER BY decided_at, id"):
        decisions[d["finding_id"]] = _decision_dict(d)
    names = _bank_names()
    langs: dict[tuple[str, str], str] = {}
    for b in {r["bank_id"] for r in rows}:
        for p in conn.execute("SELECT url, language FROM pages WHERE bank_id = ?", (b,)):
            langs[(b, p["url"])] = p["language"]
    titles: dict[str, str | None] = {}
    out = []
    for r in rows:
        f = db._finding(r)  # parses urls_read
        if f.requirement_id not in titles:
            titles[f.requirement_id] = hint_title(Requirement(
                id=f.requirement_id, text_original="", source_doc="", source_clause_id="",
                source_url="", check_type="uz_version"))
        out.append({
            **f.model_dump(mode="json"),
            "bank_name": names.get(f.bank_id, f.bank_id),
            # Language as stored for the URL now (the page store keeps one row per URL).
            "pages_detail": [{"url": u, "language": langs.get((f.bank_id, u), "no data")}
                             for u in f.urls_read],
            "requirement": {"text_en": r["req_text_en"], "text_en_label": MT_LABEL,
                            "short_title": titles[f.requirement_id],
                            "text_original": r["req_text_original"],
                            "source_url": r["req_source_url"],
                            "clause_id": r["req_clause_id"],
                            "check_type": r["req_check_type"]},
            "evidence_quote_en_label": MT_LABEL,
            "run": {"id": f.run_id, "source": r["run_source"],
                    "started_at": r["run_started_at"], "finished_at": r["run_finished_at"],
                    "crawl_status": r["run_crawl_status"], "start_url": r["run_start_url"]},
            "decision": decisions.get(f.id),
        })
    return out


def _decision_dict(row) -> dict:
    d = dict(row)
    ephemeral = os.getenv("LIVE_DECISIONS_EPHEMERAL", "").strip() in ("1", "true", "yes")
    d["storage_note"] = ("live session, may reset on restart"
                         if d.get("source", "live") == "live" and ephemeral else None)
    return d


# --- banks ---

@app.get("/banks")
def banks() -> list[dict]:
    with db.connect() as conn:
        latest = {}
        for r in db.list_runs(conn):
            if r.source != "consistency":
                latest.setdefault(r.bank_id, r)
        counts: dict[tuple[str, str], int] = {}
        for r in conn.execute("SELECT run_id, status, COUNT(*) AS n FROM findings "
                              "GROUP BY run_id, status"):
            counts[(r["run_id"], r["status"])] = r["n"]
    out = []
    for b in load_banks():
        run = latest.get(b.id)
        out.append({**b.model_dump(), "latest_run": run.model_dump(mode="json") if run else None,
                    "findings": {s: counts.get((run.id, s), 0) if run else 0
                                 for s in ("ok", "possible_gap", "not_checkable")}})
    return out


# --- checks / jobs ---

class CheckRequest(BaseModel):
    url: str = Field(min_length=8, max_length=2000)


def _set_job(job_id: str, **fields) -> None:
    with db.connect() as conn:
        job = db.get_job(conn, job_id)
        if job is None:
            return
        db.upsert_job(conn, job.model_copy(update=fields))


class JobCancelled(Exception):
    pass


_cancel_requests: set[str] = set()


def run_job(job_id: str, url: str) -> None:
    def progress(message: str) -> None:
        # Progress events are frequent (every page, every check): a cancel request stops
        # the job at the next one.
        if job_id in _cancel_requests:
            raise JobCancelled()
        _set_job(job_id, progress=message)

    with _check_slots:
        if job_id in _cancel_requests:
            _set_job(job_id, status="cancelled", progress="cancelled by user")
            return
        _set_job(job_id, status="running", progress="starting")
        try:
            crawler = Crawler(CrawlConfig.from_env(), progress=progress)
            if not allow_private():
                crawler.fetcher.url_guard = validate_public_url
            run = check_site(url, crawler=crawler, progress=progress,
                             on_run=lambda rid: _set_job(job_id, result_ref=rid))
            _set_job(job_id, status="done", result_ref=run.id, progress="done")
        except JobCancelled:
            _set_job(job_id, status="cancelled", progress="cancelled by user")
        except Exception as e:
            _set_job(job_id, status="error", error=f"{type(e).__name__}: {str(e)[:300]}",
                     progress="failed")


@app.post("/check", status_code=202,
          dependencies=[Depends(rate_limit_dependency(check_limiter))])
def check(body: CheckRequest, background: BackgroundTasks) -> dict:
    try:
        url = validate_public_url(body.url)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from None
    job = Job(id=uuid.uuid4().hex[:12], url=url, progress="queued")
    with db.connect() as conn:
        db.upsert_job(conn, job)
    background.add_task(run_job, job.id, url)
    return {"job_id": job.id, "status": job.status}


@app.post("/jobs/{job_id}/cancel")
def cancel_job(job_id: str) -> dict:
    with db.connect() as conn:
        job = db.get_job(conn, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found.")
    if job.status in ("queued", "running"):
        _cancel_requests.add(job_id)
    return {"job_id": job_id, "status": job.status,
            "cancel_requested": job.status in ("queued", "running")}


@app.get("/jobs/{job_id}")
def get_job(job_id: str) -> dict:
    with db.connect() as conn:
        job = db.get_job(conn, job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="Job not found.")
        run = db.get_run(conn, job.result_ref) if job.result_ref else None
        findings = _finding_rows(conn, "WHERE f.run_id = ?", (run.id,)) if run else []
        approved = len(db.list_requirements(conn, approved_only=True))
    return {**job.model_dump(mode="json"),
            "run": run.model_dump(mode="json") if run else None,
            "approved_requirements": approved,
            "findings": findings}


# --- findings ---

@app.get("/findings")
def findings(bank_id: str | None = None, run_id: str | None = None,
             status: Literal["ok", "possible_gap", "not_checkable"] | None = None,
             latest: bool = Query(True, description="only each bank's latest finished run"),
             ) -> list[dict]:
    where, args = [], []
    if bank_id:
        where.append("f.bank_id = ?")
        args.append(bank_id)
    if run_id:
        where.append("f.run_id = ?")
        args.append(run_id)
    elif latest:
        # Consistency repeat runs are measurements, not the bank's current result.
        where.append("f.run_id IN (SELECT id FROM runs r1 WHERE r1.status = 'done' AND "
                     "r1.source != 'consistency' AND "
                     "r1.finished_at = (SELECT MAX(r2.finished_at) FROM runs r2 "
                     "WHERE r2.bank_id = r1.bank_id AND r2.status = 'done' "
                     "AND r2.source != 'consistency'))")
    if status:
        where.append("f.status = ?")
        args.append(status)
    with db.connect() as conn:
        return _finding_rows(conn, ("WHERE " + " AND ".join(where)) if where else "",
                             tuple(args))


# --- decisions ---

class DecisionRequest(BaseModel):
    finding_id: str
    analyst: str = Field(min_length=1, max_length=100)
    verdict: Literal["confirmed", "rejected"]
    comment: str = Field(default="", max_length=2000)


@app.post("/decisions", status_code=201)
def add_decision(body: DecisionRequest) -> dict:
    analyst = body.analyst.strip()
    if not analyst:
        raise HTTPException(status_code=422, detail="Analyst name is required.")
    with db.connect() as conn:
        if db.get_finding(conn, body.finding_id) is None:
            raise HTTPException(status_code=404, detail="Finding not found.")
        d = Decision(finding_id=body.finding_id, analyst=analyst, verdict=body.verdict,
                     comment=body.comment.strip())
        db.add_decision(conn, d)
    return _decision_dict(d.model_dump(mode="json"))


@app.get("/decisions")
def decisions() -> list[dict]:
    names = _bank_names()
    with db.connect() as conn:
        rows = conn.execute(
            "SELECT d.*, f.bank_id, f.requirement_id, f.status AS finding_status, "
            "f.decided_by, "
            "r.text_en AS req_text_en FROM decisions d "
            "LEFT JOIN findings f ON f.id = d.finding_id "
            "LEFT JOIN requirements r ON r.id = f.requirement_id "
            "ORDER BY d.decided_at DESC, d.id DESC").fetchall()
    return [{**_decision_dict(r), "bank_name": names.get(r["bank_id"], r["bank_id"])}
            for r in rows]


# --- metrics ---

@app.get("/metrics")
def get_metrics() -> dict:
    with db.connect() as conn:
        return metrics.compute(conn)
