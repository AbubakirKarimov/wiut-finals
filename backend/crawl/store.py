"""Page store for resumable crawls: pages are written to SQLite as soon as they are fetched,
and a later run reuses pages fetched within CRAWLER_CACHE_MAX_AGE_HOURS instead of
requesting them again (0 disables reuse)."""

import os
from datetime import timedelta

from backend import db
from backend.models import Page, utcnow


class DbPageStore:
    def __init__(self, db_path=None, max_age_hours: float | None = None):
        self.db_path = db_path
        if max_age_hours is None:
            max_age_hours = float(os.getenv("CRAWLER_CACHE_MAX_AGE_HOURS") or 24)
        self.max_age_hours = max_age_hours

    def get(self, bank_id: str, url: str) -> tuple[Page, dict] | None:
        if self.max_age_hours <= 0:
            return None
        with db.connect(self.db_path) as conn:
            return db.get_cached_page(conn, bank_id, url,
                                      utcnow() - timedelta(hours=self.max_age_hours))

    def put(self, page: Page, links: dict, request_url: str | None = None) -> None:
        with db.connect(self.db_path) as conn:
            db.upsert_page(conn, page, links=links, request_url=request_url)
