"""Metrics computed only from stored data: runs, findings, decisions, llm_calls and the
team's labels (data/labels/labels.csv). Missing inputs are reported as "no data" / "not set",
never estimated."""

import csv
import math
import sqlite3
from datetime import datetime
from pathlib import Path

from backend.llm.provider import cost_of

LABELS_PATH = Path(__file__).resolve().parents[1] / "data" / "labels" / "labels.csv"
NO_DATA = "no data"


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
    return {"value": round(tp / len(flagged), 3), "true_positives": tp,
            "predicted_gaps": len(flagged), "labelled_pairs": len(labels),
            "matched": len(pairs)}


def analyst_confirmation(conn: sqlite3.Connection) -> dict:
    """Share of possible_gap findings confirmed by analysts (latest decision per finding)."""
    rows = conn.execute(
        "SELECT d.finding_id, d.verdict FROM decisions d JOIN findings f ON f.id = d.finding_id "
        "WHERE f.status = 'possible_gap' ORDER BY d.decided_at, d.id")
    latest = {r["finding_id"]: r["verdict"] for r in rows}
    if not latest:
        return {"value": NO_DATA, "decided": 0}
    confirmed = sum(v == "confirmed" for v in latest.values())
    return {"value": round(confirmed / len(latest), 3), "confirmed": confirmed,
            "decided": len(latest)}


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
        "analyst_confirmation_rate": analyst_confirmation(conn),
        "findings_by_status": status_counts,
    }
