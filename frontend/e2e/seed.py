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
from backend.models import Finding, Page, Requirement, Run  # noqa: E402

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
    # Two stored ("pre-computed") findings for the UI tests: an ok finding with a verified
    # quote, and a not_checkable one whose stored passage must NOT be rendered.
    from datetime import datetime, timezone
    when = datetime(2026, 10, 10, 12, tzinfo=timezone.utc)
    seeds = [
        ("e2e_ok_bank", "ok", "Davlat tilida e'lonlar va narxlar ro'yxati joylashtirilgan.",
         "Announcements and price lists are published in the state language.",
         "Uzbek version present (5 Uzbek pages of 6; completeness not assessed): 5 Uzbek and "
         "1 Russian pages of 6 HTML pages read (Uzbek share 83%); language switcher found"),
        ("e2e_nc_bank", "not_checkable", "This stored passage must not be shown in the card.",
         "machine translation of the hidden passage",
         "re-checked 2026-10-10 (0 page(s) re-fetched for missing link data): Code found "
         "related passages on 1 candidate page(s) but the LLM did not confirm the requirement "
         "there; a possible gap needs code-level evidence of absence, so this is left for "
         "review. Quote: the closest related passage. (keywords from hints: e2e, seed)"),
    ]
    for bank, status, quote, quote_en, reason in seeds:
        run = Run(id=f"seed-{bank}", bank_id=bank, start_url=f"https://{bank}.example/",
                  source="precomputed", status="done", crawl_status="ok", pages_read=6,
                  started_at=when, finished_at=when)
        db.upsert_run(conn, run)
        urls = [f"https://{bank}.example/p{i}" for i in range(6)]
        page = Page(bank_id=bank, url=urls[0], language="uz_latn", source_type="html",
                    text=quote + " " + "Bank xizmatlari haqida. " * 20)
        db.upsert_page(conn, page)
        db.upsert_finding(conn, Finding(
            id=f"{run.id}:req:law_state_language:art:20", bank_id=bank,
            requirement_id="req:law_state_language:art:20", status=status, run_id=run.id,
            evidence_url=urls[0], evidence_quote=quote, evidence_quote_en=quote_en,
            reason=reason, pages_read=6, urls_read=urls, created_at=when,
            decided_by="llm_assisted" if status == "not_checkable" else "code"))
print(f"seeded {path}")
