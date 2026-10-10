"""Analyst decisions made by the team, shipped with the pre-computed findings.

The hosted demo has no persistent database: at startup it loads data/precomputed/
findings.json and, if present, data/precomputed/decisions.json (this module). Decisions
from the file are stored with source="team"; decisions made on the running site are
source="live" and may be lost on restart (labelled in the UI when LIVE_DECISIONS_EPHEMERAL=1).

    .venv/bin/python -m backend.team_decisions export   # local DB -> decisions.json
    .venv/bin/python -m backend.team_decisions load     # decisions.json -> DB (idempotent)

Only decisions on findings of the runs in findings.json (each bank's latest batch run) are
exported, so that every exported decision refers to a finding the hosted site has.
"""

import argparse
import json
import os
import sys
from pathlib import Path

from backend import db
from backend.models import Decision, utcnow

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PATH = ROOT / "data" / "precomputed" / "decisions.json"


def decisions_path() -> Path:
    return Path(os.getenv("PRECOMPUTED_DECISIONS_PATH") or DEFAULT_PATH)


def _latest_batch_runs(conn) -> set[str]:
    latest: dict[str, str] = {}
    for r in db.list_runs(conn):  # newest first
        if r.source in ("batch", "precomputed") and r.status == "done":
            latest.setdefault(r.bank_id, r.id)
    return set(latest.values())


def export(path: Path | None = None, db_path=None) -> dict:
    path = path or decisions_path()
    with db.connect(db_path) as conn:
        runs = _latest_batch_runs(conn)
        rows = [dict(r) for r in conn.execute(
            "SELECT d.finding_id, d.analyst, d.verdict, d.comment, d.decided_at, f.run_id "
            "FROM decisions d JOIN findings f ON f.id = d.finding_id ORDER BY d.decided_at, d.id")]
    rows = [{k: v for k, v in r.items() if k != "run_id"} for r in rows if r["run_id"] in runs]
    data = {"format": 1, "exported_at": utcnow().isoformat(),
            "reviewed_on": max((r["decided_at"] for r in rows), default=None),
            "n": len(rows),
            "authors": sorted({r["analyst"] for r in rows}),
            "decisions": rows}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return data


def load(path: Path | None = None, db_path=None) -> dict:
    """Insert the file's decisions as source="team" (skips ones already stored and ones whose
    finding is not in the database). Returns counts."""
    path = path or decisions_path()
    if not path.exists():
        return {"loaded": 0, "skipped_existing": 0, "skipped_no_finding": 0, "file": False}
    data = json.loads(path.read_text(encoding="utf-8"))
    out = {"loaded": 0, "skipped_existing": 0, "skipped_no_finding": 0, "file": True}
    with db.connect(db_path) as conn:
        for d in data.get("decisions", []):
            dec = Decision(**{k: d[k] for k in ("finding_id", "analyst", "verdict", "decided_at")},
                           comment=d.get("comment") or "", source="team")
            if db.get_finding(conn, dec.finding_id) is None:
                out["skipped_no_finding"] += 1
                continue
            same = conn.execute(
                "SELECT 1 FROM decisions WHERE finding_id = ? AND analyst = ? AND decided_at = ?",
                (dec.finding_id, dec.analyst, db._ts(dec.decided_at))).fetchone()
            if same:
                out["skipped_existing"] += 1
                continue
            db.add_decision(conn, dec)
            out["loaded"] += 1
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Export or load the team's analyst decisions.")
    ap.add_argument("action", choices=["export", "load"])
    args = ap.parse_args(argv)
    db.init_db()
    if args.action == "export":
        data = export()
        print(f"exported {data['n']} decision(s) by {', '.join(data['authors']) or 'nobody'} "
              f"to {decisions_path()}")
    else:
        print(load())
    return 0


if __name__ == "__main__":
    sys.exit(main())
