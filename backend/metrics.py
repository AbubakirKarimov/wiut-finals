"""Metrics computed only from stored data: runs, findings, decisions, llm_calls and the
team's labels (data/labels/labels.csv). Missing inputs are reported as "no data" / "not set",
never estimated."""

import csv
import json
import math
import os
import sqlite3
from datetime import datetime
from pathlib import Path

from backend.llm.provider import cost_of

LABELS_PATH = Path(__file__).resolve().parents[1] / "data" / "labels" / "labels.csv"
NO_DATA = "no data"
TOO_FEW = "too few decisions to be meaningful"


def percentile(values: list[float], q: float) -> float | None:
    """Nearest-rank percentile; None for an empty list."""
    if not values:
        return None
    s = sorted(values)
    k = max(0, min(len(s) - 1, math.ceil(q / 100 * len(s)) - 1))
    return s[k]


def _latest_findings(conn: sqlite3.Connection) -> dict[tuple[str, str], str]:
    """(bank_id, requirement_id) -> status of the most recent finding."""
    rows = conn.execute("SELECT bank_id, requirement_id, status FROM findings "
                        "ORDER BY created_at")
    return {(r["bank_id"], r["requirement_id"]): r["status"] for r in rows}


def label_precision(conn: sqlite3.Connection, path: Path = LABELS_PATH) -> dict:
    if not path.exists():
        return {"value": NO_DATA, "detail": f"{path.name} not found; the team has not "
                                            "labelled any (bank, requirement) pairs yet"}
    with path.open(encoding="utf-8") as fh:
        labels = [r for r in csv.DictReader(fh) if (r.get("expected") or "").strip()]
    predicted = _latest_findings(conn)
    pairs = [(predicted.get((r["bank_id"], r["requirement_id"])), r["expected"].strip())
             for r in labels]
    pairs = [(p, e) for p, e in pairs if p is not None]
    flagged = [(p, e) for p, e in pairs if p == "possible_gap"]
    if not flagged:
        return {"value": NO_DATA, "labelled_pairs": len(labels), "matched": len(pairs),
                "detail": "no labelled pair has a possible_gap finding"}
    tp = sum(e == "possible_gap" for _, e in flagged)
    value = round(tp / len(flagged), 3)
    return {"value": value, "true_positives": tp,
            "predicted_gaps": len(flagged), "labelled_pairs": len(labels),
            "matched": len(pairs),
            "label": f"precision {value:.0%} on {len(flagged)} labelled possible gaps"}


def min_decisions() -> int:
    return int(os.getenv("METRICS_MIN_DECISIONS") or 10)


def decision_precision(conn: sqlite3.Connection) -> dict:
    """Precision of possible_gap from analyst decisions: Confirm = correct, Reject = false
    positive (latest decision per finding). Below METRICS_MIN_DECISIONS the value is not
    reported as a percentage."""
    rows = conn.execute(
        "SELECT d.finding_id, d.verdict FROM decisions d JOIN findings f ON f.id = d.finding_id "
        "WHERE f.status = 'possible_gap' ORDER BY d.decided_at, d.id")
    latest = {r["finding_id"]: r["verdict"] for r in rows}
    n = len(latest)
    confirmed = sum(v == "confirmed" for v in latest.values())
    out = {"decided": n, "confirmed": confirmed, "rejected": n - confirmed,
           "min_decisions": min_decisions()}
    if n == 0:
        return {**out, "value": NO_DATA, "label": "no decided possible gaps yet"}
    if n < min_decisions():
        return {**out, "value": TOO_FEW,
                "label": f"{n} decided finding(s): {TOO_FEW} (need {min_decisions()})"}
    value = round(confirmed / n, 3)
    return {**out, "value": value, "label": f"precision {value:.0%} on {n} decided findings"}


def consistency(conn: sqlite3.Connection) -> dict:
    """Latest consistency measurement per bank (python -m backend.consistency)."""
    rows = [dict(r) for r in conn.execute("SELECT * FROM consistency ORDER BY created_at")]
    latest = {}
    for r in rows:
        latest[r["bank_id"]] = r
    measured = [r for r in latest.values() if r["status_agreement"] is not None]
    if not measured:
        if latest:
            return {"value": NO_DATA, "detail": "repeat runs were rate limited: no requirement "
                                                "was answered in every run; run it again later"}
        return {"value": NO_DATA, "detail": "run python -m backend.consistency <bank_id>"}
    not_measured = sum(json.loads(r["per_requirement"]).get("_not_measured", 0)
                       for r in measured)
    n_req = sum(r["n_requirements"] for r in measured)
    agree = sum(r["status_agreement"] * r["n_requirements"] for r in measured) / n_req
    quote = sum((r["quote_agreement"] or 0) * r["n_requirements"] for r in measured) / n_req
    return {"value": round(agree, 3), "quote_agreement": round(quote, 3),
            "requirements": n_req, "not_measured": not_measured, "banks": len(measured),
            "runs_per_bank": sorted({len(json.loads(r["run_ids"])) for r in measured}),
            "models": sorted({m for r in measured for m in json.loads(r["models"])}),
            "measured_at": max(r["created_at"] for r in measured),
            "per_bank": [{"bank_id": r["bank_id"], "status_agreement": r["status_agreement"],
                          "quote_agreement": r["quote_agreement"],
                          "requirements": r["n_requirements"], "created_at": r["created_at"],
                          "per_requirement": json.loads(r["per_requirement"])}
                         for r in measured]}


LATEST_RUNS = ("SELECT id FROM runs r1 WHERE r1.status = 'done' AND r1.source != 'consistency' "
               "AND r1.finished_at = (SELECT MAX(r2.finished_at) FROM runs r2 WHERE "
               "r2.bank_id = r1.bank_id AND r2.status = 'done' AND r2.source != 'consistency')")


def decided_by(conn: sqlite3.Connection) -> dict:
    """Who decided the status of the findings currently shown (each bank's latest run):
    deterministic code or LLM-assisted. Findings stored before decided_by existed count as
    "not recorded" and are left out of the percentages."""
    counts = {"code": 0, "llm_assisted": 0, "not_recorded": 0}
    for r in conn.execute(f"SELECT decided_by, COUNT(*) AS n FROM findings WHERE run_id IN "
                          f"({LATEST_RUNS}) GROUP BY decided_by"):
        counts[r["decided_by"] or "not_recorded"] += r["n"]
    recorded = counts["code"] + counts["llm_assisted"]
    out = {**counts, "recorded": recorded}
    if not recorded:
        return {**out, "share_code": NO_DATA, "share_llm_assisted": NO_DATA}
    return {**out, "share_code": round(counts["code"] / recorded, 3),
            "share_llm_assisted": round(counts["llm_assisted"] / recorded, 3)}


def llm_usage(conn: sqlite3.Connection) -> dict:
    """LLM calls, tokens and estimated cost per run and per requirement check, from llm_calls
    (API calls only; cache hits are free) and the prices in .env. Median latency of API calls.
    """
    runs = [r["id"] for r in conn.execute("SELECT id FROM runs WHERE status = 'done'")]
    if not runs:
        return {"runs": 0, "calls_per_run": NO_DATA, "tokens_per_run": NO_DATA,
                "cost_usd_per_run": NO_DATA, "cost_usd_per_check": NO_DATA,
                "median_call_latency_ms": NO_DATA, "price_source": "LLM_*PRICE_*_PER_MTOK"}
    marks = ",".join("?" for _ in runs)
    calls = [dict(r) for r in conn.execute(
        f"SELECT provider, model, input_tokens, output_tokens, cache_hit, duration_ms, ok "
        f"FROM llm_calls WHERE run_id IN ({marks})", runs)]
    checks = conn.execute(f"SELECT COUNT(*) AS n FROM findings WHERE run_id IN ({marks})",
                          runs).fetchone()["n"]
    api = [c for c in calls if not c["cache_hit"]]
    tokens = sum((c["input_tokens"] or 0) + (c["output_tokens"] or 0) for c in api)
    cost = cost_of(calls) if calls else 0.0
    lat = percentile([c["duration_ms"] for c in api if c["ok"]], 50)
    n = len(runs)
    return {
        "runs": n, "checks": checks, "api_calls": len(api),
        "cache_hits": len(calls) - len(api),
        "calls_per_run": round(len(api) / n, 2),
        "tokens_per_run": round(tokens / n, 1),
        "cost_usd_per_run": round(cost / n, 6) if isinstance(cost, float) else cost,
        "cost_usd_per_check": (round(cost / checks, 6) if isinstance(cost, float) and checks
                               else (cost if not isinstance(cost, float) else NO_DATA)),
        "median_call_latency_ms": round(lat) if lat is not None else NO_DATA,
        "price_source": "LLM_*PRICE_*_PER_MTOK in .env (list price; missing -> not set)",
    }


def _seconds(start: str, end: str) -> float:
    return (datetime.fromisoformat(end) - datetime.fromisoformat(start)).total_seconds()


def compute(conn: sqlite3.Connection, labels_path: Path = LABELS_PATH) -> dict:
    runs = [dict(r) for r in conn.execute(
        "SELECT id, started_at, finished_at FROM runs WHERE status = 'done' "
        "AND finished_at IS NOT NULL")]
    durations = [_seconds(r["started_at"], r["finished_at"]) for r in runs]
    p50, p95 = percentile(durations, 50), percentile(durations, 95)

    calls = [dict(r) for r in conn.execute(
        "SELECT provider, model, input_tokens, output_tokens, cache_hit, run_id, ok "
        "FROM llm_calls WHERE run_id IS NOT NULL")]
    run_ids = {r["id"] for r in runs}
    per_run = [c for c in calls if c["run_id"] in run_ids]
    api_calls = [c for c in per_run if not c["cache_hit"]]
    tokens_known = [c for c in api_calls
                    if c["input_tokens"] is not None or c["output_tokens"] is not None]
    total_tokens = sum((c["input_tokens"] or 0) + (c["output_tokens"] or 0)
                       for c in tokens_known)
    cost = cost_of(per_run) if per_run else 0.0
    n = len(runs)
    if not n:
        avg_tokens = avg_cost = NO_DATA
    else:
        avg_tokens = round(total_tokens / n, 1)
        avg_cost = round(cost / n, 6) if isinstance(cost, float) else cost

    status_counts = {s: 0 for s in ("ok", "possible_gap", "not_checkable")}
    for r in conn.execute("SELECT status, COUNT(*) AS n FROM findings GROUP BY status"):
        status_counts[r["status"]] = r["n"]

    return {
        "checks_completed": n,
        "latency_seconds": {"p50": round(p50, 1) if p50 is not None else NO_DATA,
                            "p95": round(p95, 1) if p95 is not None else NO_DATA,
                            "runs": n},
        "llm": {"api_calls": len(api_calls),
                "cache_hits": sum(1 for c in per_run if c["cache_hit"]),
                "failed_calls": sum(1 for c in api_calls if not c["ok"]),
                "avg_tokens_per_check": avg_tokens,
                "avg_cost_usd_per_check": avg_cost,
                "total_cost_usd": cost if per_run else (0.0 if n else NO_DATA)},
        "precision_possible_gap_vs_labels": label_precision(conn, labels_path),
        "precision_possible_gap_from_decisions": decision_precision(conn),
        "consistency": consistency(conn),
        "findings_by_status": status_counts,
        "decided_by": decided_by(conn),
        "llm_usage": llm_usage(conn),
    }
