"""One site check end to end: crawl -> store pages -> run approved checks -> store findings.

Used by POST /check (source="job") and scripts/crawl_all.py (source="batch").
"""

import os
import re
import uuid
from pathlib import Path
from typing import Callable
from urllib.parse import urlsplit

import yaml

from backend import db
from backend.checks.runner import run_checks
from backend.crawl.banks import BANKS_YAML, load_banks
from backend.crawl.crawler import CrawlConfig, Crawler
from backend.crawl.store import DbPageStore
from backend.crawl.text import same_site
from backend.llm.provider import LLMConfigError, LLMProvider, provider_from_env
from backend.models import Requirement, Run, utcnow

REQUIREMENTS_YAML = Path(__file__).resolve().parents[1] / "data" / "requirements.yaml"


def bank_id_for(url: str, banks_path: Path = BANKS_YAML) -> str:
    """The banks.yaml id whose website is on the same site, else 'site_<host>'."""
    for b in load_banks(banks_path):
        if b.website_url and same_site(b.website_url, url):
            return b.id
    host = (urlsplit(url).hostname or "unknown").removeprefix("www.")
    return "site_" + re.sub(r"[^a-z0-9]+", "_", host.lower()).strip("_")


def sync_requirements_yaml(path: Path | None = None, db_path=None) -> int:
    """Load human-approved requirements from data/requirements.yaml into SQLite."""
    path = path or Path(os.getenv("REQUIREMENTS_PATH") or REQUIREMENTS_YAML)
    if not path.exists():
        return 0
    rows = (yaml.safe_load(path.read_text(encoding="utf-8")) or {}).get("requirements") or []
    n = 0
    with db.connect(db_path) as conn:
        for r in rows:
            req = Requirement(**{k: v for k, v in r.items() if k in Requirement.model_fields})
            if req.approved:
                db.upsert_requirement(conn, req)
                n += 1
    return n


def llm_from_env(db_path=None) -> LLMProvider | None:
    try:
        return provider_from_env(db_path=db_path)
    except LLMConfigError:
        return None


def check_site(url: str, *, bank_id: str | None = None, source: str = "job",
               crawl_cfg: CrawlConfig | None = None, crawler: Crawler | None = None,
               llm: LLMProvider | None | str = "env", db_path=None,
               progress: Callable[[str], None] | None = None,
               on_run: Callable[[str], None] | None = None,
               on_crawl: Callable[[object], None] | None = None) -> Run:
    progress = progress or (lambda m: None)
    run = Run(id=uuid.uuid4().hex[:12], bank_id=bank_id or bank_id_for(url), start_url=url,
              source=source)
    with db.connect(db_path) as conn:
        db.upsert_run(conn, run)
    if on_run:
        on_run(run.id)
    token = db.current_run_id.set(run.id)
    crawler = crawler or Crawler(crawl_cfg or CrawlConfig.from_env(), progress=progress)
    if crawler.store is None:
        # Pages are written as they are fetched and reused by later runs (resumable).
        crawler.store = DbPageStore(db_path)

    def save_finding(f) -> None:
        with db.connect(db_path) as conn:
            db.upsert_finding(conn, f)

    try:
        crawl = crawler.crawl(run.bank_id, url, run_id=run.id)
        if on_crawl:
            on_crawl(crawl)
        run.crawl_status, run.crawl_reason = crawl.status, crawl.reason or None
        run.pages_read, run.fetch_errors = len(crawl.pages), crawl.fetch_errors
        run.has_language_switcher = crawl.has_language_switcher
        with db.connect(db_path) as conn:
            db.upsert_run(conn, run)
            requirements = db.list_requirements(conn, approved_only=True)
        progress(f"crawl {crawl.status}: {len(crawl.pages)} page(s) "
                 f"({crawl.reused_pages} from the store), {len(crawl.fetch_errors)} fetch error(s)")
        if llm == "env":
            llm = llm_from_env(db_path)
        progress(f"running {len(requirements)} approved check(s)"
                 + ("" if llm else " (LLM not configured)"))
        run_checks(run.id, crawl, requirements, llm, progress=progress,
                   on_finding=save_finding)
        run.status = "done"
    except Exception as e:  # recorded on the run and the job; never swallowed silently
        run.status, run.error = "error", f"{type(e).__name__}: {str(e)[:300]}"
        raise
    finally:
        run.finished_at = utcnow()
        with db.connect(db_path) as conn:
            db.upsert_run(conn, run)
        db.current_run_id.reset(token)
        crawler.close()
    return run
