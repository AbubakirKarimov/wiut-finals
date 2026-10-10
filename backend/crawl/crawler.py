"""Polite same-site crawler: robots.txt, 1 request/second per host, depth limit, page limit,
wall-clock budget. HTML -> visible text, PDF -> pdfplumber text (a scan without a text layer
is stored as readable=false; nothing is guessed). Language detected per page.

JavaScript-only sites: rendered with plain Playwright when BROWSER_FALLBACK=1; otherwise the
crawl stops with crawl_status "needs_browser" and checks report not_checkable.
"""

import heapq
import io
import os
import re
import time
from dataclasses import dataclass, field
from typing import Callable
from urllib.parse import urlsplit, urlunsplit

from backend.crawl.fetch import (ROBOTS_UNREADABLE, Browser, FetchConfig, Fetcher,
                                 FetchResult)
from backend.crawl.sections import link_rank
from backend.crawl.text import (classify, detect_language, language_links, links, page_title,
                                same_site, visible_text)
from backend.models import Page

SKIP_EXT = re.compile(r"\.(jpe?g|png|gif|svg|webp|ico|css|js|zip|rar|7z|mp4|mp3|avi|mov|"
                      r"docx?|xlsx?|pptx?|apk|exe|dmg|woff2?|ttf|xml|json)$", re.I)
# Site search, login and print views add no new content.
SKIP_PATH = re.compile(r"/(search|poisk|qidiruv|login|auth|signin|print)(/|$)|[?&](q|search|query)=",
                       re.I)
# Fetch failures that make a site unreliable to judge (not ordinary 404 links).
ERROR_STATUSES = {403, 429} | set(range(500, 600))


@dataclass
class CrawlConfig:
    max_pages: int = 15
    max_depth: int = 2
    time_budget_seconds: float = 60.0
    max_pdf_pages: int = 30
    fetch: FetchConfig = field(default_factory=FetchConfig)

    @classmethod
    def from_env(cls) -> "CrawlConfig":
        d = cls()
        return cls(
            max_pages=int(os.getenv("CRAWLER_MAX_PAGES_PER_BANK") or d.max_pages),
            max_depth=int(os.getenv("CRAWLER_MAX_DEPTH") or d.max_depth),
            time_budget_seconds=float(os.getenv("CRAWLER_TIME_BUDGET_SECONDS")
                                      or d.time_budget_seconds),
            max_pdf_pages=int(os.getenv("CRAWLER_MAX_PDF_PAGES") or d.max_pdf_pages),
            fetch=FetchConfig.from_env())


@dataclass
class CrawlResult:
    bank_id: str
    start_url: str
    # ok | blocked | unreachable | robots_disallowed | needs_browser | js_shell_failed | other
    status: str = "ok"
    reason: str = ""
    pages: list[Page] = field(default_factory=list)
    fetch_errors: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)   # 404s, robots-disallowed links
    has_language_switcher: bool | None = None
    language_links: dict[str, str] = field(default_factory=dict)
    method: str = "httpx"
    budget_exhausted: bool = False
    reused_pages: int = 0          # taken from the page store instead of fetched
    notes: list[str] = field(default_factory=list)

    @property
    def urls_read(self) -> list[str]:
        return [p.url for p in self.pages]

    @property
    def unique_pages(self) -> int:
        """Pages read, counting each normalized URL once (gates possible_gap)."""
        return len({normalize_url(p.url) for p in self.pages})


def normalize_url(url: str) -> str:
    p = urlsplit(url)
    path = p.path or "/"
    return urlunsplit((p.scheme, p.netloc.lower(), path, p.query, ""))


class LinkRanker:
    """Crawl order within the page cap: deposit/loan/document/tariff/restructuring pages
    first, then complaint and contacts pages, then other consumer pages, then the rest.
    Within a tier, sections take turns (the 1st deposit link, the 1st loan link, ..., then
    the 2nd of each), so one section with many links cannot use up the cap."""

    def __init__(self):
        self.per_section: dict[str | None, int] = {}

    def __call__(self, url: str, anchor: str) -> tuple[int, int]:
        tier, section = link_rank(url, anchor)
        turn = self.per_section.get(section, 0) if section else 0
        if section:
            self.per_section[section] = turn + 1
        return tier, turn


LANGUAGE_LINK = (-1, 0)  # language versions of the home page come first


def pdf_text(data: bytes, max_pages: int) -> str:
    import pdfplumber
    parts = []
    with pdfplumber.open(io.BytesIO(data)) as pdf:
        for page in pdf.pages[:max_pages]:
            parts.append(page.extract_text() or "")
    return re.sub(r"\s+", " ", " ".join(parts)).strip()


class Crawler:
    def __init__(self, cfg: CrawlConfig, fetcher: Fetcher | None = None,
                 browser_factory: Callable[[], Browser] | None = None,
                 progress: Callable[[str], None] | None = None, store=None):
        self.cfg = cfg
        self.store = store  # DbPageStore-like: get(bank_id, url) / put(page, links, request_url)
        self.fetcher = fetcher or Fetcher(cfg.fetch)
        self._browser_factory = browser_factory or (
            lambda: Browser(cfg.fetch, self.fetcher.throttle))
        self.progress = progress or (lambda msg: None)

    def crawl(self, bank_id: str, start_url: str, run_id: str | None = None) -> CrawlResult:
        res = CrawlResult(bank_id=bank_id, start_url=start_url)
        self.fetcher.notes = res.notes
        deadline = time.monotonic() + self.cfg.time_budget_seconds
        fcfg = self.cfg.fetch

        cached = self._cached(bank_id, start_url, run_id)
        if cached and cached[1].get("method") == "httpx" and \
                len(cached[0].text) >= fcfg.min_text_chars:
            self.progress("home page from the store (fetched earlier)")
            self._crawl_httpx(res, cached[0], cached[1], deadline, run_id, from_store=True)
            return res
        self.progress("fetching home page")
        home = self.fetcher.get(start_url)
        if home.robots_blocked and home.error == ROBOTS_UNREADABLE:
            res.status, res.reason = "unreachable", f"{home.error} ({'; '.join(res.notes)})"
            res.fetch_errors.append(f"{start_url}: {res.reason}")
            return res
        if home.robots_blocked:
            res.status, res.reason = "robots_disallowed", f"{home.error}: {home.final_url}"
            return res
        if home.error:
            res.status, res.reason = "unreachable", home.error
            res.fetch_errors.append(f"{start_url}: {home.error}")
            return res
        html = home.text if home.is_html else ""
        text = visible_text(html) if html else ""
        cls = classify(home.status, html, len(text), fcfg.min_text_chars)
        if cls == "blocked":
            res.status = "blocked"
            res.reason = f"bot protection or rate limit (HTTP {home.status}); not bypassed"
            res.fetch_errors.append(f"{start_url}: HTTP {home.status}")
            return res
        if cls == "other":
            res.status, res.reason = "other", f"home page returned HTTP {home.status}"
            res.fetch_errors.append(f"{start_url}: HTTP {home.status}")
            return res
        if cls == "js_shell":
            if not fcfg.browser_fallback:
                res.status = "needs_browser"
                res.reason = ("needs browser: the home page has almost no text without "
                              "JavaScript and BROWSER_FALLBACK=0")
                return res
            return self._crawl_with_browser(res, home.final_url, deadline, run_id)

        page, meta = self._store(res, home, run_id)
        if page is None:
            res.status = "other"
            res.reason = f"home page is not a readable HTML page ({home.content_type or 'unknown'})"
            return res
        self._crawl_httpx(res, page, meta, deadline, run_id)
        return res

    def _cached(self, bank_id: str, url: str, run_id: str | None) -> tuple[Page, dict] | None:
        if self.store is None:
            return None
        hit = self.store.get(bank_id, url)
        if hit is None:
            return None
        page, meta = hit
        page = page.model_copy(update={"run_id": run_id})
        self.store.put(page, meta, request_url=url)  # attach the page to this run
        return page, meta

    # --- httpx crawl ---

    def _crawl_httpx(self, res: CrawlResult, home: Page, home_meta: dict, deadline: float,
                     run_id: str | None, from_store: bool = False) -> None:
        root = home.url
        seen = {normalize_url(res.start_url), normalize_url(root)}
        queue: list[tuple[tuple[int, int], int, int, str]] = []  # (rank, depth, order, url)
        order = 0
        rank = LinkRanker()

        def push(url: str, depth: int, prio: tuple[int, int] | None, anchor: str = "") -> None:
            nonlocal order
            key = normalize_url(url)
            if key in seen or not same_site(url, root) or SKIP_EXT.search(urlsplit(url).path) \
                    or SKIP_PATH.search(url):
                return
            seen.add(key)
            order += 1
            heapq.heappush(queue, (prio or rank(url, anchor), depth, order, url))

        def expand(meta: dict, depth: int) -> None:
            if depth >= self.cfg.max_depth:
                return
            for u in (meta.get("lang") or {}).values():
                push(u, depth + 1, LANGUAGE_LINK)
            for u, anchor in meta.get("links") or []:
                push(u, depth + 1, None, anchor)

        if from_store:
            res.pages.append(home)
            res.reused_pages += 1
        res.language_links = dict(home_meta.get("lang") or {})
        res.has_language_switcher = bool(res.language_links)
        expand(home_meta, 0)
        if not res.language_links:
            origin = "{0.scheme}://{0.netloc}".format(urlsplit(root))
            for k in ("uz", "ru"):
                push(f"{origin}/{k}/", 1, LANGUAGE_LINK)

        while queue and len(res.pages) < self.cfg.max_pages:
            if time.monotonic() >= deadline:
                res.budget_exhausted = True
                res.notes.append(f"time budget of {self.cfg.time_budget_seconds:g} s reached")
                break
            _, depth, _, url = heapq.heappop(queue)
            n = len(res.pages) + 1
            cached = self._cached(res.bank_id, url, run_id)
            if cached:
                page, meta = cached
                if normalize_url(page.url) in {normalize_url(p.url) for p in res.pages}:
                    continue
                self.progress(f"page {n}/{self.cfg.max_pages} from the store")
                seen.add(normalize_url(page.url))
                res.pages.append(page)
                res.reused_pages += 1
                expand(meta, depth)
                continue
            self.progress(f"fetching page {n}/{self.cfg.max_pages}")
            r = self.fetcher.get(url)
            if r.robots_blocked:
                res.skipped.append(f"{url}: {r.error}")
                continue
            if r.error:
                res.fetch_errors.append(f"{url}: {r.error}")
                continue
            if r.status in ERROR_STATUSES:
                res.fetch_errors.append(f"{url}: HTTP {r.status}")
                continue
            if r.status != 200:
                res.skipped.append(f"{url}: HTTP {r.status}")
                continue
            if normalize_url(r.final_url) in {normalize_url(p.url) for p in res.pages}:
                continue  # redirected to a page already read
            seen.add(normalize_url(r.final_url))
            page, meta = self._store(res, r, run_id)
            if page and page.source_type == "html":
                expand(meta, depth)
        if res.reused_pages:
            res.notes.append(f"{res.reused_pages} page(s) reused from the store")
        if not res.has_language_switcher:
            # A guessed /uz/ or /ru/ that exists also counts as a language version.
            langs = {p.language for p in res.pages}
            res.has_language_switcher = ({"uz_latn", "uz_cyrl"} & langs) != set() and \
                "ru" in langs and any(urlsplit(p.url).path.strip("/").split("/")[0]
                                      in {"uz", "ru", "oz"} for p in res.pages)

    def _store(self, res: CrawlResult, r: FetchResult, run_id: str | None
               ) -> tuple[Page | None, dict]:
        meta: dict = {"method": "httpx", "links": [], "lang": {}}
        if r.is_pdf:
            if r.truncated:
                res.skipped.append(f"{r.final_url}: PDF larger than the size cap")
                return None, meta
            try:
                text = pdf_text(r.body, self.cfg.max_pdf_pages)
            except Exception as e:  # pdfplumber raises many types on broken files
                res.skipped.append(f"{r.final_url}: unreadable PDF ({type(e).__name__})")
                return None, meta
            page = Page(bank_id=res.bank_id, url=r.final_url, source_type="pdf", text=text,
                        language=detect_language(text) or "other", readable=bool(text),
                        title=r.final_url.rsplit("/", 1)[-1], run_id=run_id)
        elif r.is_html:
            html = r.text
            text = visible_text(html)
            page = Page(bank_id=res.bank_id, url=r.final_url, source_type="html", text=text,
                        language=detect_language(text) or "other", readable=bool(text),
                        title=page_title(html), run_id=run_id)
            meta["links"] = [list(x) for x in links(html, r.final_url)]
            meta["lang"] = language_links(html, r.final_url)
        else:
            res.skipped.append(f"{r.final_url}: content type {r.content_type or 'unknown'}")
            return None, meta
        res.pages.append(page)
        if self.store is not None:
            self.store.put(page, meta, request_url=r.url)
        return page, meta

    # --- browser crawl (JavaScript-only sites) ---

    def _crawl_with_browser(self, res: CrawlResult, root: str, deadline: float,
                            run_id: str | None) -> CrawlResult:
        res.method = "browser"
        tl = lambda h: len(visible_text(h))  # noqa: E731
        with self._browser_factory() as browser:
            self.progress("rendering home page in a browser")
            remaining = max(1.0, deadline - time.monotonic())
            rr = browser.render(root, min(self.cfg.fetch.browser_timeout_seconds, remaining),
                                text_len=tl)
            res.notes.extend(f"browser {n}" for n in rr.notes)
            if not rr.ok:
                res.status = "js_shell_failed"
                res.reason = ("needs browser: the page stayed nearly empty after "
                              f"{rr.attempts} browser attempt(s)")
                return res
            if self.fetcher.allowed(rr.final_url) is not True:
                res.status, res.reason = "robots_disallowed", f"browser landed on {rr.final_url}"
                return res
            self._store_html(res, rr.final_url, rr.html, run_id)
            res.language_links = language_links(rr.html, rr.final_url)
            res.has_language_switcher = bool(res.language_links)
            seen = {normalize_url(rr.final_url)}
            rank = LinkRanker()
            queue = [(LANGUAGE_LINK, u) for u in res.language_links.values()]
            queue += [(rank(u, a), u) for u, a in links(rr.html, rr.final_url)]
            queue.sort(key=lambda x: x[0])  # stable: page order within the same rank
            for _, url in queue:  # depth 1 only in browser mode (slow)
                if len(res.pages) >= self.cfg.max_pages:
                    break
                if time.monotonic() >= deadline:
                    res.budget_exhausted = True
                    res.notes.append(f"time budget of {self.cfg.time_budget_seconds:g} s reached")
                    break
                key = normalize_url(url)
                if key in seen or not same_site(url, rr.final_url) or \
                        SKIP_EXT.search(urlsplit(url).path) or SKIP_PATH.search(url) or \
                        url.lower().endswith(".pdf"):
                    continue
                seen.add(key)
                if self.fetcher.allowed(url) is not True:
                    res.skipped.append(f"{url}: robots.txt")
                    continue
                self.progress(f"rendering page {len(res.pages) + 1}/{self.cfg.max_pages}")
                remaining = deadline - time.monotonic()
                p = browser.render(url, min(self.cfg.fetch.browser_timeout_seconds,
                                            max(1.0, remaining)), text_len=tl)
                if p.ok:
                    self._store_html(res, p.final_url, p.html, run_id)
                else:
                    res.fetch_errors.append(f"{url}: browser render failed")
        return res

    def _store_html(self, res: CrawlResult, url: str, html: str, run_id: str | None) -> None:
        if normalize_url(url) in {normalize_url(p.url) for p in res.pages}:
            # A link that renders to a page already read (e.g. a single-page app's home).
            res.notes.append(f"browser: {url} already read, not counted twice")
            return
        text = visible_text(html)
        page = Page(bank_id=res.bank_id, url=url, source_type="html", text=text,
                    language=detect_language(text) or "other", readable=bool(text),
                    title=page_title(html), run_id=run_id)
        res.pages.append(page)
        if self.store is not None:
            self.store.put(page, {"method": "browser", "links": [list(x) for x in links(html, url)],
                                  "lang": language_links(html, url)}, request_url=url)

    def close(self) -> None:
        self.fetcher.close()
