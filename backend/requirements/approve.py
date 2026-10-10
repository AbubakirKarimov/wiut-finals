"""Approve requirement candidates after reading data/requirements_review.md (run by a human).

    python -m backend.requirements.approve <clause_id> [<clause_id> ...] [--check-type TYPE]

Marks the candidates approved in data/requirements_candidates.json, stores them as approved
Requirements in SQLite and rewrites data/requirements.yaml with all approved requirements.
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml

from backend import db
from backend.models import Requirement
from backend.requirements.shortlist import CANDIDATES_PATH, MT_LABEL, ROOT

REQUIREMENTS_YAML = ROOT / "data" / "requirements.yaml"
CHECK_TYPES = ("uz_version", "required_document", "key_info")


def requirement_from(c: dict) -> Requirement:
    return Requirement(id=f"req:{c['clause_id']}", text_original=c["text_original"],
                       text_en=c["text_en"], source_doc=c["source_id"],
                       source_clause_id=c["clause_id"], source_url=c["url"],
                       check_type=c["check_type"], approved=True)


def approve(clause_ids: list[str], check_type: str | None = None, *,
            candidates_path: Path = CANDIDATES_PATH, yaml_path: Path = REQUIREMENTS_YAML,
            db_path: Path | str | None = None) -> list[Requirement]:
    data = json.loads(candidates_path.read_text(encoding="utf-8"))
    by_id = {c["clause_id"]: c for c in data["candidates"]}
    unknown = [cid for cid in clause_ids if cid not in by_id]
    if unknown:
        raise ValueError(f"not in {candidates_path.name}: {', '.join(unknown)}")
    no_type = [cid for cid in clause_ids if not (check_type or by_id[cid]["check_type"])]
    if no_type:
        raise ValueError(f"no proposed check_type for {', '.join(no_type)}; "
                         f"pass --check-type {{{','.join(CHECK_TYPES)}}}")

    now = datetime.now(timezone.utc).isoformat()
    for cid in clause_ids:
        c = by_id[cid]
        if check_type:
            c["check_type"] = check_type
        c["approved"] = True
        c["approved_at"] = now
    candidates_path.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n",
                               encoding="utf-8")

    approved = [requirement_from(c) for c in data["candidates"] if c["approved"]]
    db.init_db(db_path)
    with db.connect(db_path) as conn:
        for req in approved:
            db.upsert_requirement(conn, req)
    rows = [{**r.model_dump(), "text_en_label": MT_LABEL} for r in approved]
    yaml_path.write_text(yaml.safe_dump({"requirements": rows}, allow_unicode=True,
                                        sort_keys=False, width=100), encoding="utf-8")
    return [r for r in approved if r.source_clause_id in clause_ids]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Approve requirement candidates.")
    ap.add_argument("clause_ids", nargs="+")
    ap.add_argument("--check-type", choices=CHECK_TYPES,
                    help="override (or supply) the check type for all given clauses")
    args = ap.parse_args(argv)
    try:
        done = approve(args.clause_ids, args.check_type)
    except (FileNotFoundError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    for r in done:
        print(f"approved {r.source_clause_id} as {r.check_type}")
    print(f"wrote {REQUIREMENTS_YAML.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
