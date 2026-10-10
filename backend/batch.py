"""Summary of batch runs (scripts/crawl_all.py): one row per bank, figures from SQLite only."""

import json
from datetime import datetime

from backend.llm.provider import cost_of

STATUSES = ("ok", "possible_gap", "not_checkable")


def summarize(conn, run_ids: list[str]) -> list[dict]:
    rows = []
    for rid in run_ids:
        run = conn.execute("SELECT * FROM runs WHERE id = ?", (rid,)).fetchone()
        if run is None:
            continue
        counts = {s: 0 for s in STATUSES}
        for r in conn.execute("SELECT status, COUNT(*) AS n FROM findings WHERE run_id = ? "
                              "GROUP BY status", (rid,)):
            counts[r["status"]] = r["n"]
        by = {"code": 0, "llm_assisted": 0, "not_recorded": 0}
        for r in conn.execute("SELECT decided_by, COUNT(*) AS n FROM findings WHERE run_id = ? "
                              "GROUP BY decided_by", (rid,)):
            by[r["decided_by"] or "not_recorded"] += r["n"]
        calls = [dict(r) for r in conn.execute(
            "SELECT provider, model, input_tokens, output_tokens, cache_hit, ok FROM llm_calls "
            "WHERE run_id = ?", (rid,))]
        api = [c for c in calls if not c["cache_hit"]]
        tokens = sum((c["input_tokens"] or 0) + (c["output_tokens"] or 0) for c in api)
        duration = None
        if run["finished_at"]:
            duration = (datetime.fromisoformat(run["finished_at"])
                        - datetime.fromisoformat(run["started_at"])).total_seconds()
        skipped = run["crawl_status"] not in (None, "ok")
        rows.append({
            "bank_id": run["bank_id"], "run_id": rid, "status": run["status"],
            "crawl": (f"skipped: {run['crawl_status']}" if skipped else run["crawl_status"])
            or "no data",
            "reason": run["crawl_reason"] or run["error"] or "",
            "pages": run["pages_read"], "errors": len(json.loads(run["fetch_errors"] or "[]")),
            **counts, "by_code": by["code"], "by_llm": by["llm_assisted"],
            "checks": sum(counts.values()),
            "duration_s": duration, "tokens": tokens, "api_calls": len(api),
            "cache_hits": len(calls) - len(api),
            "rate_limited": sum(1 for c in api if not c["ok"]),
            "cost_usd": cost_of(calls) if calls else 0.0,
        })
    return rows


def _fmt(v) -> str:
    if v is None:
        return "no data"
    if isinstance(v, float):
        return f"{v:.4f}" if v < 1 else f"{v:.0f}"
    return str(v)


def _cell(row: dict, key: str) -> str:
    if key == "cost_per_check":
        c, n = row["cost_usd"], row["checks"]
        return f"{c / n:.6f}" if isinstance(c, (int, float)) and n else _fmt(c if n else None)
    v = row[key]
    if key == "duration_s" and isinstance(v, (int, float)):
        return f"{v:.1f}"
    if key == "cost_usd" and isinstance(v, (int, float)):
        return f"{v:.4f}"
    return _fmt(v)


COLUMNS = [("bank_id", "bank"), ("crawl", "crawl"), ("pages", "pages"), ("errors", "errors"),
           ("ok", "ok"), ("possible_gap", "gap"), ("not_checkable", "n/c"),
           ("by_code", "by code"), ("by_llm", "LLM-assisted"),
           ("duration_s", "secs"), ("api_calls", "calls"), ("cache_hits", "cached"),
           ("rate_limited", "429/err"), ("tokens", "tokens"), ("cost_usd", "cost $"),
           ("cost_per_check", "$/check")]


def totals(rows: list[dict]) -> dict:
    t = {"bank_id": "TOTAL", "crawl": f"{sum(r['crawl'] == 'ok' for r in rows)} ok"}
    for k in ("pages", "errors", "ok", "possible_gap", "not_checkable", "api_calls",
              "cache_hits", "rate_limited", "tokens", "by_code", "by_llm", "checks"):
        t[k] = sum(r[k] for r in rows)
    durs = [r["duration_s"] for r in rows if r["duration_s"] is not None]
    t["duration_s"] = sum(durs) if durs else None
    costs = [r["cost_usd"] for r in rows]
    t["cost_usd"] = (next((c for c in costs if isinstance(c, str)), None)
                     or sum(costs))
    return t


def text_table(rows: list[dict]) -> str:
    data = [[_cell(r, k) for k, _ in COLUMNS] for r in rows + [totals(rows)]]
    head = [h for _, h in COLUMNS]
    widths = [max(len(x) for x in col) for col in zip(head, *data)]
    lines = ["  ".join(h.ljust(w) for h, w in zip(head, widths))]
    lines += ["  ".join(x.ljust(w) for x, w in zip(row, widths)) for row in data]
    return "\n".join(lines)


def markdown_table(rows: list[dict]) -> str:
    out = ["| " + " | ".join(h for _, h in COLUMNS) + " |",
           "|" + "---|" * len(COLUMNS)]
    for r in rows + [totals(rows)]:
        out.append("| " + " | ".join(_cell(r, k) for k, _ in COLUMNS) + " |")
    reasons = [f"- {r['bank_id']}: {r['reason']}" for r in rows if r["reason"]]
    if reasons:
        out += ["", "Crawl notes:", *reasons]
    return "\n".join(out)
