"""Probe each bank home page once before the real crawl.

For every bank with a website_url: fetch robots.txt and the home page with httpx (honest
User-Agent, 1 request/second per domain, 15 s timeout) and classify the result as
ok | js_shell | blocked | unreachable | other. js_shell pages get one retry in a plain
Playwright Chromium (no stealth, no proxies). Protection is never bypassed: a block or a
challenge is recorded and the site is left alone.

Usage: python -m backend.crawl.probe   (or scripts/probe_banks.py)
Writes data/probe_report.md: a table only, no page contents.
"""

import os
import re
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlsplit
from urllib.robotparser import RobotFileParser

import httpx
from bs4 import BeautifulSoup
from dotenv import load_dotenv

from backend.crawl.banks import BANKS_YAML, Bank, load_banks

load_dotenv()

REPORT_PATH = Path(__file__).resolve().parents[2] / "data" / "probe_report.md"
CLASSES = ("ok", "js_shell", "blocked", "unreachable", "other")
BLOCK_STATUSES = {403, 429, 503}
CHALLENGE_MARKERS = ("just a moment", "cf-chl", "captcha", "access denied",
                     "attention required", "checking your browser", "ddos-guard")
MAX_REDIRECTS = 5


@dataclass
class ProbeConfig:
    user_agent: str = "ComplianceRadar/0.1"
    timeout_seconds: float = 15.0
    min_delay_seconds: float = 1.0
    min_text_chars: int = 500  # below this a 200 page counts as js_shell

    @classmethod
    def from_env(cls) -> "ProbeConfig":
        d = cls()
        return cls(
            user_agent=os.getenv("CRAWLER_USER_AGENT") or d.user_agent,
            timeout_seconds=float(os.getenv("PROBE_TIMEOUT_SECONDS") or d.timeout_seconds),
            min_delay_seconds=float(os.getenv("CRAWLER_MIN_DELAY_SECONDS")
                                    or d.min_delay_seconds),
            min_text_chars=int(os.getenv("PROBE_MIN_TEXT_CHARS") or d.min_text_chars),
        )


@dataclass
class ProbeResult:
    bank_id: str
    url: str
    classification: str = "other"
    http_status: int | None = None
    final_url: str = ""
    title: str = ""
    text_length: int | None = None
    language: str | None = None
    robots_disallows_home: bool | None = None  # None = robots.txt could not be read
    method: str = "httpx"
    notes: list[str] = field(default_factory=list)


# ---------- pure helpers (unit-tested) ----------

def visible_text(html: str) -> str:
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "noscript", "template", "svg", "head"]):
        tag.decompose()
    return re.sub(r"\s+", " ", soup.get_text(" ")).strip()


def page_title(html: str) -> str:
    soup = BeautifulSoup(html, "lxml")
    return re.sub(r"\s+", " ", soup.title.get_text()).strip() if soup.title else ""


UZ_CYRL_LETTERS = set("ўқғҳЎҚҒҲ")
RU_ONLY_LETTERS = set("ыщЫЩ")
UZ_LATN_WORDS = {"va", "uchun", "bilan", "yoki", "bo'yicha", "boʻyicha", "haqida", "mumkin",
                 "sizning", "kredit", "to'lov", "toʻlov", "hisob", "omonat", "bank", "barcha",
                 "xizmatlar", "kartasi", "orqali", "bo'lim", "yangiliklar", "biz"}
EN_WORDS = {"the", "and", "for", "of", "to", "your", "with", "our", "about", "news"}


def detect_language(text: str) -> str | None:
    """Dominant script/language of a page: uz_latn | uz_cyrl | ru | other; None if no text."""
    cyr = sum(1 for c in text if "Ѐ" <= c <= "ӿ")
    lat = sum(1 for c in text if c.isascii() and c.isalpha())
    if cyr + lat == 0:
        return None
    if cyr >= lat:
        uz = sum(1 for c in text if c in UZ_CYRL_LETTERS)
        ru = sum(1 for c in text if c in RU_ONLY_LETTERS)
        return "uz_cyrl" if uz > ru else "ru"
    words = re.findall(r"[a-zʻ'’]+", text.lower())
    uz = sum(1 for w in words if w.replace("’", "'") in UZ_LATN_WORDS)
    en = sum(1 for w in words if w in EN_WORDS)
    return "uz_latn" if uz > en else "other"


def challenge_marker(html: str) -> str | None:
    low = html.lower()
    return next((m for m in CHALLENGE_MARKERS if m in low), None)


def classify(status: int | None, html: str, text_len: int, min_text_chars: int) -> str:
    """Markers only count on an error status or a near-empty page: a normal home page
    may legitimately load a reCAPTCHA script."""
    if status is None:
        return "unreachable"
    if status in BLOCK_STATUSES:
        return "blocked"
    if status == 200:
        if text_len < min_text_chars:
            return "blocked" if challenge_marker(html) else "js_shell"
        return "ok"
    return "other"


def robots_disallows(robots_txt: str, user_agent: str, url: str) -> bool:
    rp = RobotFileParser()
    rp.parse(robots_txt.splitlines())
    return not rp.can_fetch(user_agent, url)


# ---------- network ----------

class DomainThrottle:
    """At most one request per min_delay seconds per host."""

    def __init__(self, min_delay: float):
        self.min_delay = min_delay
        self._last: dict[str, float] = {}

    def wait(self, url: str) -> None:
        host = urlsplit(url).hostname or ""
        gap = time.monotonic() - self._last.get(host, float("-inf"))
        if gap < self.min_delay:
            time.sleep(self.min_delay - gap)
        self._last[host] = time.monotonic()


class Prober:
    def __init__(self, cfg: ProbeConfig):
        self.cfg = cfg
        self.throttle = DomainThrottle(cfg.min_delay_seconds)
        self.client = httpx.Client(headers={"User-Agent": cfg.user_agent},
                                   timeout=cfg.timeout_seconds, follow_redirects=False)
        # host -> robots.txt text ("" = no restrictions), or None if it could not be read
        self._robots: dict[str, str | None] = {}

    def close(self) -> None:
        self.client.close()

    def _get(self, url: str) -> httpx.Response:
        self.throttle.wait(url)
        return self.client.get(url)

    def robots_for(self, url: str, notes: list[str]) -> str | None:
        p = urlsplit(url)
        host = p.hostname or ""
        if host in self._robots:
            return self._robots[host]
        robots_url = f"{p.scheme}://{p.netloc}/robots.txt"
        text: str | None
        try:
            r = self._get(robots_url)
            hops = 0
            while r.is_redirect and hops < MAX_REDIRECTS:
                nxt = urljoin(str(r.url), r.headers["location"])
                if urlsplit(nxt).hostname != host:
                    break
                r = self._get(nxt)
                hops += 1
            if r.status_code == 200:
                text = r.text
            elif 400 <= r.status_code < 500:
                # RFC 9309: robots.txt unavailable (4xx) -> no restrictions.
                text = ""
                notes.append(f"robots.txt {r.status_code} on {host}")
            else:
                # RFC 9309: unreachable (5xx) -> assume full disallow.
                text = "User-agent: *\nDisallow: /"
                notes.append(f"robots.txt {r.status_code} on {host}: treated as disallow")
        except httpx.HTTPError as e:
            text = None
            notes.append(f"robots.txt error on {host}: {type(e).__name__}")
        self._robots[host] = text
        return text

    def allowed(self, url: str, res: ProbeResult) -> bool:
        robots = self.robots_for(url, res.notes)
        if robots is None:
            # Could not read robots.txt at all: be conservative and do not fetch.
            return False
        return not robots_disallows(robots, self.cfg.user_agent, url)

    def probe(self, bank: Bank) -> ProbeResult:
        res = ProbeResult(bank_id=bank.id, url=bank.website_url)
        url = bank.website_url
        robots = self.robots_for(url, res.notes)
        if robots is None:
            res.classification = "unreachable"
            return res
        res.robots_disallows_home = robots_disallows(robots, self.cfg.user_agent, url)
        if res.robots_disallows_home:
            res.notes.append("home page disallowed by robots.txt: not fetched")
            return res
        try:
            r = self._get(url)
            hops = 0
            while r.is_redirect and hops < MAX_REDIRECTS:
                nxt = urljoin(str(r.url), r.headers["location"])
                if not self.allowed(nxt, res):
                    res.notes.append(f"redirect target disallowed or robots unknown: {nxt}")
                    res.http_status, res.final_url = r.status_code, str(r.url)
                    return res
                r = self._get(nxt)
                hops += 1
        except httpx.HTTPError as e:
            res.classification = "unreachable"
            res.notes.append(f"{type(e).__name__}: {str(e)[:120]}")
            return res
        html = r.text
        text = visible_text(html)
        res.http_status, res.final_url = r.status_code, str(r.url)
        res.title, res.text_length = page_title(html), len(text)
        res.language = detect_language(text)
        res.classification = classify(r.status_code, html, len(text), self.cfg.min_text_chars)
        if res.classification == "blocked" and (m := challenge_marker(html)):
            res.notes.append(f"challenge marker: {m!r}")
        return res


def browser_retry(results: list[ProbeResult], prober: Prober) -> None:
    """One plain headless Chromium visit per js_shell page. No stealth, no proxies."""
    todo = [r for r in results if r.classification == "js_shell"]
    if not todo:
        return
    from playwright.sync_api import Error as PWError
    from playwright.sync_api import sync_playwright

    cfg = prober.cfg
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        try:
            for res in todo:
                ctx = browser.new_context(user_agent=cfg.user_agent)
                page = ctx.new_page()
                url = res.final_url or res.url
                res.method = "browser"
                res.notes.append(f"httpx: js_shell ({res.text_length} chars)")
                try:
                    prober.throttle.wait(url)
                    resp = page.goto(url, wait_until="load",
                                     timeout=cfg.timeout_seconds * 1000)
                    try:
                        page.wait_for_load_state("networkidle",
                                                 timeout=cfg.timeout_seconds * 1000)
                    except PWError:
                        res.notes.append("browser: networkidle not reached")
                    html = page.content()
                except PWError as e:
                    res.notes.append(f"browser error: {str(e).splitlines()[0][:120]}")
                    ctx.close()
                    continue
                final_url = page.url
                ctx.close()
                if not prober.allowed(final_url, res):
                    res.notes.append(f"browser landed on disallowed URL: {final_url}")
                    continue
                text = visible_text(html)
                status = resp.status if resp else None
                res.http_status, res.final_url = status, final_url
                res.title, res.text_length = page_title(html), len(text)
                res.language = detect_language(text)
                res.classification = classify(status, html, len(text), cfg.min_text_chars)
                if challenge_marker(html) and res.classification != "ok":
                    res.classification = "blocked"
                    res.notes.append(f"browser: challenge marker {challenge_marker(html)!r}; "
                                     "stopped for this site")
        finally:
            browser.close()


# ---------- report ----------

def _cell(v) -> str:
    if v is None or v == "":
        return "no data"
    if isinstance(v, bool):
        return "yes" if v else "no"
    return str(v).replace("|", "\\|")


def render_report(results: list[ProbeResult], skipped: list[Bank], cfg: ProbeConfig) -> str:
    counts = {c: sum(r.classification == c for r in results) for c in CLASSES}
    lines = [
        "# Bank website probe",
        "",
        f"- Run at: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
        f"- User-Agent: `{cfg.user_agent}`",
        f"- Min visible text for `ok`: {cfg.min_text_chars} characters; "
        f"timeout {cfg.timeout_seconds:g} s; "
        f"{cfg.min_delay_seconds:g} s between requests per domain",
        "- Page contents are not stored; this table only.",
        "",
        "| bank | class | status | text length | language | robots disallows home "
        "| method | final URL | title | notes |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for r in results:
        lines.append("| " + " | ".join(_cell(v) for v in (
            r.bank_id, r.classification, r.http_status, r.text_length, r.language,
            r.robots_disallows_home, r.method, r.final_url, r.title[:80],
            "; ".join(r.notes))) + " |")
    lines += ["", "## Summary", "", "| class | banks |", "|---|---|"]
    lines += [f"| {c} | {n} |" for c, n in counts.items()]
    lines += [f"| skipped (no website_url) | {len(skipped)} |", ""]
    if skipped:
        lines += ["Skipped: " + ", ".join(b.id for b in skipped), ""]
    return "\n".join(lines)


def print_table(results: list[ProbeResult], skipped: list[Bank]) -> None:
    head = ("bank", "class", "status", "text_len", "language")
    rows = [(r.bank_id, r.classification, _cell(r.http_status), _cell(r.text_length),
             _cell(r.language)) for r in results]
    widths = [max(len(str(x)) for x in col) for col in zip(head, *rows)]
    for row in (head, *rows):
        print("  ".join(str(x).ljust(w) for x, w in zip(row, widths)))
    print()
    for c in CLASSES:
        print(f"{c:12} {sum(r.classification == c for r in results)}")
    print(f"{'skipped':12} {len(skipped)} (no website_url)")


def run(banks_path: Path = BANKS_YAML, report_path: Path = REPORT_PATH) -> list[ProbeResult]:
    cfg = ProbeConfig.from_env()
    banks = load_banks(banks_path)
    targets = [b for b in banks if b.crawlable]
    skipped = [b for b in banks if not b.crawlable]
    prober = Prober(cfg)
    results: list[ProbeResult] = []
    try:
        for b in targets:
            print(f"probing {b.id} ...", file=sys.stderr)
            results.append(prober.probe(b))
        browser_retry(results, prober)
    finally:
        prober.close()
    print_table(results, skipped)
    report_path.write_text(render_report(results, skipped, cfg), encoding="utf-8")
    print(f"\nreport: {report_path}")
    return results


if __name__ == "__main__":
    run()
