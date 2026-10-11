"""Polite fetching: robots.txt (RFC 9309), per-host throttle, honest User-Agent, manual
redirects (each hop is throttled and robots-checked), size caps and a plain Playwright
renderer for JavaScript-only pages. Nothing here bypasses bot protection."""

import os
import time
from dataclasses import dataclass, field
from typing import Callable
from urllib.parse import urljoin, urlsplit
from urllib.robotparser import RobotFileParser

import httpx
from dotenv import load_dotenv

load_dotenv()

MAX_REDIRECTS = 5
ROBOTS_UNREADABLE = "robots.txt could not be read"


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    return default if raw is None or raw.strip() == "" else raw.strip() not in {"0", "false"}


@dataclass
class FetchConfig:
    user_agent: str = "ComplianceRadar/0.1"
    timeout_seconds: float = 15.0
    min_delay_seconds: float = 1.0
    min_text_chars: int = 500          # below this a 200 HTML page counts as js_shell
    browser_fallback: bool = True      # BROWSER_FALLBACK=0 disables Playwright
    browser_timeout_seconds: float = 45.0
    # Hosted demo without a browser: "jina" renders JavaScript-only pages through Jina
    # Reader (backend/crawl/jina.py); "" = off.
    render_fallback: str = ""
    max_bytes: int = 10 * 1024 * 1024  # per response (PDFs included)

    @classmethod
    def from_env(cls) -> "FetchConfig":
        d = cls()
        return cls(
            user_agent=os.getenv("CRAWLER_USER_AGENT") or d.user_agent,
            timeout_seconds=float(os.getenv("PROBE_TIMEOUT_SECONDS") or d.timeout_seconds),
            min_delay_seconds=float(os.getenv("CRAWLER_MIN_DELAY_SECONDS")
                                    or d.min_delay_seconds),
            min_text_chars=int(os.getenv("PROBE_MIN_TEXT_CHARS") or d.min_text_chars),
            browser_fallback=_env_bool("BROWSER_FALLBACK", d.browser_fallback),
            browser_timeout_seconds=float(os.getenv("BROWSER_TIMEOUT_SECONDS")
                                          or d.browser_timeout_seconds),
            render_fallback=(os.getenv("RENDER_FALLBACK") or "").strip().lower(),
            max_bytes=int(float(os.getenv("CRAWLER_MAX_FILE_MB") or 10) * 1024 * 1024),
        )


class DomainThrottle:
    """At most one request per delay per host (delay may be raised by robots Crawl-delay)."""

    def __init__(self, min_delay: float):
        self.min_delay = min_delay
        self._last: dict[str, float] = {}
        self._delay: dict[str, float] = {}

    def set_delay(self, host: str, delay: float) -> None:
        self._delay[host] = max(self.min_delay, delay)

    def wait(self, url: str) -> None:
        host = urlsplit(url).hostname or ""
        delay = self._delay.get(host, self.min_delay)
        gap = time.monotonic() - self._last.get(host, float("-inf"))
        if gap < delay:
            time.sleep(delay - gap)
        self._last[host] = time.monotonic()


def robots_disallows(robots_txt: str, user_agent: str, url: str) -> bool:
    rp = RobotFileParser()
    rp.parse(robots_txt.splitlines())
    return not rp.can_fetch(user_agent, url)


@dataclass
class FetchResult:
    url: str
    final_url: str = ""
    status: int | None = None
    content_type: str = ""
    body: bytes = b""
    error: str | None = None          # network/TLS/timeout error, or "robots"
    robots_blocked: bool = False
    truncated: bool = False
    notes: list[str] = field(default_factory=list)

    @property
    def text(self) -> str:
        return self.body.decode(_charset(self.content_type), errors="replace")

    @property
    def is_pdf(self) -> bool:
        return "pdf" in self.content_type.lower() or self.final_url.lower().endswith(".pdf")

    @property
    def is_html(self) -> bool:
        ct = self.content_type.lower()
        return "html" in ct or (not ct and not self.is_pdf)


def _charset(content_type: str) -> str:
    for part in content_type.split(";"):
        k, _, v = part.strip().partition("=")
        if k.lower() == "charset" and v:
            return v.strip('"')
    return "utf-8"


class Fetcher:
    def __init__(self, cfg: FetchConfig, transport: httpx.BaseTransport | None = None):
        self.cfg = cfg
        self.throttle = DomainThrottle(cfg.min_delay_seconds)
        self.client = httpx.Client(headers={"User-Agent": cfg.user_agent},
                                   timeout=cfg.timeout_seconds, follow_redirects=False,
                                   transport=transport)
        # host -> robots.txt text ("" = no restrictions), or None if it could not be read
        self._robots: dict[str, str | None] = {}
        self.notes: list[str] = []
        # Optional check run on every URL before it is requested (raises ValueError).
        self.url_guard: Callable[[str], object] | None = None

    def close(self) -> None:
        self.client.close()

    def _raw_get(self, url: str) -> httpx.Response:
        self.throttle.wait(url)
        return self.client.get(url)

    def robots_for(self, url: str) -> str | None:
        p = urlsplit(url)
        host = p.hostname or ""
        if host in self._robots:
            return self._robots[host]
        robots_url = f"{p.scheme}://{p.netloc}/robots.txt"
        text: str | None
        try:
            r = self._raw_get(robots_url)
            hops = 0
            while r.is_redirect and hops < MAX_REDIRECTS:
                nxt = urljoin(str(r.url), r.headers["location"])
                if urlsplit(nxt).hostname != host:
                    break
                r = self._raw_get(nxt)
                hops += 1
            if r.status_code == 200:
                text = r.text
            elif 400 <= r.status_code < 500:
                # RFC 9309: robots.txt unavailable (4xx) -> no restrictions.
                text = ""
                self.notes.append(f"robots.txt {r.status_code} on {host}")
            else:
                # RFC 9309: unreachable (5xx) -> assume full disallow.
                text = "User-agent: *\nDisallow: /"
                self.notes.append(f"robots.txt {r.status_code} on {host}: treated as disallow")
        except httpx.HTTPError as e:
            text = None
            self.notes.append(f"robots.txt error on {host}: {type(e).__name__}")
        if text:
            rp = RobotFileParser()
            rp.parse(text.splitlines())
            delay = rp.crawl_delay(self.cfg.user_agent)
            if delay:
                self.throttle.set_delay(host, float(delay))
        self._robots[host] = text
        return text

    def allowed(self, url: str) -> bool | None:
        """True/False per robots.txt; None if robots.txt could not be read (do not fetch)."""
        robots = self.robots_for(url)
        if robots is None:
            return None
        return not robots_disallows(robots, self.cfg.user_agent, url)

    def get(self, url: str) -> FetchResult:
        res = FetchResult(url=url)
        current = url
        try:
            for _ in range(MAX_REDIRECTS + 1):
                if self.url_guard:
                    try:
                        self.url_guard(current)
                    except ValueError as e:
                        res.error, res.final_url = f"URL not allowed: {e}", current
                        return res
                ok = self.allowed(current)
                if not ok:
                    res.robots_blocked = True
                    res.final_url = current
                    res.error = "robots.txt disallows" if ok is False else ROBOTS_UNREADABLE
                    return res
                self.throttle.wait(current)
                with self.client.stream("GET", current) as r:
                    if r.is_redirect:
                        current = urljoin(str(r.url), r.headers["location"])
                        continue
                    res.status, res.final_url = r.status_code, str(r.url)
                    res.content_type = r.headers.get("content-type", "")
                    chunks, size = [], 0
                    for chunk in r.iter_bytes():
                        size += len(chunk)
                        if size > self.cfg.max_bytes:
                            res.truncated = True
                            break
                        chunks.append(chunk)
                    res.body = b"".join(chunks)
                    return res
            res.error = "too many redirects"
        except httpx.HTTPError as e:
            res.error = f"{type(e).__name__}: {str(e)[:120]}"
        res.final_url = res.final_url or current
        return res


@dataclass
class RenderResult:
    ok: bool
    html: str = ""
    status: int | None = None
    final_url: str = ""
    attempts: int = 0
    notes: list[str] = field(default_factory=list)


class Browser:
    method = "browser"
    """Plain headless Chromium (no stealth, no proxies, honest User-Agent).

    render(): navigate, wait for network idle up to the timeout, retry once if the page
    still has too little text. Use as a context manager."""

    def __init__(self, cfg: FetchConfig, throttle: DomainThrottle):
        self.cfg = cfg
        self.throttle = throttle
        self._pw = self._browser = None

    def __enter__(self) -> "Browser":
        from playwright.sync_api import sync_playwright
        self._pw = sync_playwright().start()
        self._browser = self._pw.chromium.launch()
        return self

    def __exit__(self, *exc) -> None:
        if self._browser:
            self._browser.close()
        if self._pw:
            self._pw.stop()

    def render(self, url: str, timeout_seconds: float | None = None,
               text_len=lambda html: 0) -> RenderResult:
        from playwright.sync_api import Error as PWError
        timeout_ms = (timeout_seconds or self.cfg.browser_timeout_seconds) * 1000
        out = RenderResult(ok=False, final_url=url)
        for attempt in (1, 2):
            out.attempts = attempt
            ctx = self._browser.new_context(user_agent=self.cfg.user_agent)
            page = ctx.new_page()
            try:
                self.throttle.wait(url)
                resp = page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
                try:
                    page.wait_for_load_state("networkidle", timeout=timeout_ms)
                except PWError:
                    out.notes.append(f"attempt {attempt}: network idle not reached")
                out.html, out.final_url = page.content(), page.url
                out.status = resp.status if resp else None
            except PWError as e:
                out.notes.append(f"attempt {attempt}: {str(e).splitlines()[0][:120]}")
                ctx.close()
                continue
            ctx.close()
            if text_len(out.html) >= self.cfg.min_text_chars:
                out.ok = True
                return out
            out.notes.append(f"attempt {attempt}: page still has little text")
        return out
