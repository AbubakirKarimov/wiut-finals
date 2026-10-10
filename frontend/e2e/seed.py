"""E2E TEST SETUP ONLY: fresh SQLite database with one approved requirement.

The requirement is the real clause law_state_language:art:20 read from
data/regulations/law_state_language.json; it is approved here only inside the throwaway
test database (the real approval is done by a human with backend.requirements.approve).
"""

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from backend import db  # noqa: E402
from backend.models import Requirement  # noqa: E402

path = Path(os.environ["DB_PATH"])
path.parent.mkdir(parents=True, exist_ok=True)
for suffix in ("", "-wal", "-shm", "-journal"):
    Path(str(path) + suffix).unlink(missing_ok=True)
db.init_db(path)
law = json.loads((ROOT / "data/regulations/law_state_language.json").read_text(encoding="utf-8"))
clause = next(c for c in law["clauses"] if c["clause_id"] == "law_state_language:art:20")
with db.connect(path) as conn:
    db.upsert_requirement(conn, Requirement(
        id="req:law_state_language:art:20", text_original=clause["text_original"],
        text_en="Signs, announcements, price lists and other visual information are issued "
                "in the state language (test seed text).",
        source_doc="law_state_language", source_clause_id=clause["clause_id"],
        source_url=clause["url"], check_type="uz_version", approved=True))
print(f"seeded {path}")
