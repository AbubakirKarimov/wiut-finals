"""Pre-computed results for the hosted demo.

    python -m backend.precomputed export     # latest batch run per bank -> findings.json
    python -m backend.precomputed load       # load into an empty database (also at startup)

The file holds no scraped page text: per run the bank, start URL, timestamps, crawl status,
pages read and the models used; per finding the requirement id, status, reason, verified
quote, its machine translation, evidence URL and the list of URLs read. The API loads it
into an empty database at startup; the UI labels these rows "pre-computed on <date>".
"""

import argparse
import json
import os
import sys
from pathlib import Path

from backend import db
from backend.models import Finding, Run, utcnow

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PATH = ROOT / "data" / "precomputed" / "findings.json"
NO_LLM = "deterministic (no LLM)"


def precomputed_path() -> Path:
    return Path(os.getenv("PRECOMPUTED_PATH") or DEFAULT_PATH)


def _models(conn, run_id: str) -> list[str]:
    return sorted({f"{r['provider']}/{r['model']}" for r in conn.execute(
        "SELECT DISTINCT provider, model FROM llm_calls WHERE run_id = ? AND ok = 1",
        (run_id,))})


def export(path: Path | None = None, db_path=None) -> dict:
    path = path or precomputed_path()
    with db.connect(db_path) as conn:
        latest: dict[str, Run] = {}
        for r in db.list_runs(conn):  # newest first
            if r.source == "batch" and r.status == "done":
                latest.setdefault(r.bank_id, r)
        check_types = {r["id"]: r["check_type"]
                       for r in conn.execute("SELECT id, check_type FROM requirements")}
        runs = []
        for bank_id in sorted(latest):
            run = latest[bank_id]
            models = _models(conn, run.id)
            findings = []
            for f in db.list_findings(conn, run_id=run.id):
                llm_check = check_types.get(f.requirement_id) != "uz_version"
                findings.append({
                    "requirement_id": f.requirement_id, "status": f.status,
                    "reason": f.reason, "evidence_url": f.evidence_url,
                    "evidence_quote": f.evidence_quote,
                    "evidence_quote_en": f.evidence_quote_en,
                    "context_quote": f.context_quote,
                    "decided_by": f.decided_by,
                    "pages_read": f.pages_read, "urls_read": f.urls_read,
                    "created_at": f.created_at.isoformat(),
                    "model": (", ".join(models) or "no API call (cached)") if llm_check
                    else NO_LLM,
                })
            runs.append({
                "run_id": run.id, "bank_id": run.bank_id, "start_url": run.start_url,
                "started_at": run.started_at.isoformat(),
                "finished_at": run.finished_at.isoformat() if run.finished_at else None,
                "crawl_status": run.crawl_status, "crawl_reason": run.crawl_reason,
                "pages_read": run.pages_read, "fetch_error_count": len(run.fetch_errors),
                "has_language_switcher": run.has_language_switcher, "models": models,
                "findings": findings,
            })
    data = {"format": 1, "exported_at": utcnow().isoformat(),
            "note": "No page text. Quotes are verified verbatim against the page text at "
                    "check time; evidence_quote_en is a machine translation.",
            "runs": runs}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return data


def load_if_empty(path: Path | None = None, db_path=None) -> int:
    """Insert the file's runs and findings when the database has no findings yet."""
    path = path or precomputed_path()
    if not path.exists():
        return 0
    with db.connect(db_path) as conn:
        if conn.execute("SELECT COUNT(*) AS n FROM findings").fetchone()["n"]:
            return 0
        data = json.loads(path.read_text(encoding="utf-8"))
        n = 0
        for r in data.get("runs", []):
            run = Run(id=r["run_id"], bank_id=r["bank_id"], start_url=r["start_url"],
                      source="precomputed", status="done", crawl_status=r["crawl_status"],
                      crawl_reason=r["crawl_reason"], pages_read=r["pages_read"],
                      fetch_errors=[f"{r['fetch_error_count']} fetch error(s) at check time"]
                      if r.get("fetch_error_count") else [],
                      has_language_switcher=r["has_language_switcher"],
                      started_at=r["started_at"], finished_at=r["finished_at"])
            db.upsert_run(conn, run)
            for f in r["findings"]:
                db.upsert_finding(conn, Finding(
                    id=f"{run.id}:{f['requirement_id']}", bank_id=run.bank_id,
                    requirement_id=f["requirement_id"], status=f["status"], run_id=run.id,
                    reason=f["reason"], evidence_url=f["evidence_url"],
                    evidence_quote=f["evidence_quote"],
                    evidence_quote_en=f["evidence_quote_en"],
                    context_quote=f.get("context_quote"), decided_by=f.get("decided_by"),
                    pages_read=f["pages_read"],
                    urls_read=f["urls_read"], created_at=f["created_at"]))
                n += 1
    return n


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Export or load pre-computed findings.")
    ap.add_argument("action", choices=["export", "load"])
    args = ap.parse_args(argv)
    db.init_db()
    if args.action == "export":
        data = export()
        n = sum(len(r["findings"]) for r in data["runs"])
        print(f"exported {len(data['runs'])} run(s), {n} finding(s) to "
              f"{precomputed_path().relative_to(ROOT)}")
    else:
        print(f"loaded {load_if_empty()} finding(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
