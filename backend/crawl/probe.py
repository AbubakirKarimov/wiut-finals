"""Probe each bank home page once before the real crawl.

For every bank with a website_url: fetch robots.txt and the home page with httpx (honest
User-Agent, 1 request/second per domain, 15 s timeout) and classify the result as
ok | js_shell | js_shell_failed | blocked | unreachable | other. js_shell pages are rendered
in a plain Playwright Chromium (no stealth, no proxies): network idle up to
BROWSER_TIMEOUT_SECONDS, one retry; still empty -> js_shell_failed. Then the Uzbek and
Russian versions are looked up (switcher links, else /uz/ and /ru/) and their language is
recorded per page. Protection is never bypassed: a block or a challenge is recorded and the
site is left alone.

Usage: python -m backend.crawl.probe   (or scripts/probe_banks.py)
Writes data/probe_report.md: a table only, no page contents.
"""

import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

from backend.crawl.banks import BANKS_YAML, Bank, load_banks
from backend.crawl.fetch import Browser, FetchConfig, Fetcher
from backend.crawl.text import (challenge_marker, classify, detect_language, language_links,
                                page_title, visible_text)

REPORT_PATH = Path(__file__).resolve().parents[2] / "data" / "probe_report.md"
CLASSES = ("ok", "js_shell", "js_shell_failed", "blocked", "unreachable", "other")
SWITCH_LANGS = ("uz", "uz_cyrl", "ru")


@dataclass
class LangPage:
    key: str          # uz | uz_cyrl | ru (what the link points to)
    url: str
    found_by: str     # link | guess
    status: int | None = None
    language: str | None = None
    text_length: int | None = None
    note: str = ""


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
    lang_pages: list[LangPage] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    html: str = field(default="", repr=False)  # in memory only, never written to the report


class Prober:
    def __init__(self, cfg: FetchConfig, transport=None):
        self.cfg = cfg
        self.fetcher = Fetcher(cfg, transport=transport)
        self.throttle = self.fetcher.throttle

    def close(self) -> None:
        self.fetcher.close()

    def probe(self, bank: Bank) -> ProbeResult:
        res = ProbeResult(bank_id=bank.id, url=bank.website_url)
        self.fetcher.notes = res.notes
        allowed = self.fetcher.allowed(bank.website_url)
        if allowed is None:
            res.classification = "unreachable"
            return res
        res.robots_disallows_home = not allowed
        if not allowed:
            res.notes.append("home page disallowed by robots.txt: not fetched")
            return res
        r = self.fetcher.get(bank.website_url)
        res.http_status, res.final_url = r.status, r.final_url
        if r.robots_blocked:
            res.notes.append(f"redirect target: {r.error}: {r.final_url}")
            return res
        if r.error:
            res.classification = "unreachable"
            res.notes.append(r.error)
            return res
        html = r.text
        text = visible_text(html)
        res.html, res.title, res.text_length = html, page_title(html), len(text)
        res.language = detect_language(text)
        res.classification = classify(r.status, html, len(text), self.cfg.min_text_chars)
        if res.classification == "blocked" and (m := challenge_marker(html)):
            res.notes.append(f"challenge marker: {m!r}")
        return res

    def probe_languages(self, res: ProbeResult, browser: Browser | None) -> None:
        """Find the uz / uz_cyrl / ru versions and record each page's detected language."""
        if res.classification != "ok" or not res.html:
            return
        found = language_links(res.html, res.final_url)
        targets = [(k, found[k], "link") for k in SWITCH_LANGS if k in found]
        origin = "{0.scheme}://{0.netloc}".format(urlsplit(res.final_url))
        for k in ("uz", "ru"):
            if k not in found:
                targets.append((k, f"{origin}/{k}/", "guess"))
        for key, url, how in targets:
            lp = LangPage(key=key, url=url, found_by=how)
            res.lang_pages.append(lp)
            if url.rstrip("/") == res.final_url.rstrip("/"):
                lp.status, lp.language, lp.text_length = (res.http_status, res.language,
                                                          res.text_length)
                lp.note = "same as home page"
                continue
            if res.method == "browser" and browser:
                if self.fetcher.allowed(url) is not True:
                    lp.note = "robots.txt disallows or unreadable"
                    continue
                rr = browser.render(url, text_len=lambda h: len(visible_text(h)))
                lp.status, html = rr.status, rr.html
                if not rr.ok:
                    lp.note = "browser: " + "; ".join(rr.notes)
            else:
                r = self.fetcher.get(url)
                if r.error:
                    lp.note = r.error
                    continue
                lp.status, html = r.status, r.text if r.is_html else ""
            text = visible_text(html) if html else ""
            lp.text_length, lp.language = len(text), detect_language(text)


def browser_retry(results: list[ProbeResult], prober: Prober, browser: Browser) -> None:
    """Render js_shell pages: network idle up to the browser timeout, one retry."""
    for res in results:
        if res.classification != "js_shell":
            continue
        res.method = "browser"
        res.notes.append(f"httpx: js_shell ({res.text_length} chars)")
        url = res.final_url or res.url
        rr = browser.render(url, text_len=lambda h: len(visible_text(h)))
        res.notes.extend(f"browser {n}" for n in rr.notes)
        if prober.fetcher.allowed(rr.final_url or url) is not True:
            res.notes.append(f"browser landed on disallowed URL: {rr.final_url}")
            res.classification = "other"
            continue
        text = visible_text(rr.html) if rr.html else ""
        res.html, res.final_url = rr.html, rr.final_url or url
        res.http_status = rr.status
        res.title, res.text_length = page_title(rr.html), len(text)
        res.language = detect_language(text)
        if rr.html and (m := challenge_marker(rr.html)) and not rr.ok:
            res.classification = "blocked"
            res.notes.append(f"browser: challenge marker {m!r}; stopped for this site")
        elif rr.ok:
            res.classification = classify(rr.status, rr.html, len(text),
                                          prober.cfg.min_text_chars)
        else:
            res.classification = "js_shell_failed"


# ---------- report ----------

def _cell(v) -> str:
    if v is None or v == "":
        return "no data"
    if isinstance(v, bool):
        return "yes" if v else "no"
    return str(v).replace("|", "\\|")


def _lang_cell(r: ProbeResult) -> str:
    parts = []
    for lp in r.lang_pages:
        what = (f"{lp.language or 'no data'} ({lp.text_length} chars)"
                if lp.text_length is not None else (lp.note or "no data"))
        parts.append(f"{lp.key} [{lp.found_by}] {urlsplit(lp.url).path or '/'} → "
                     f"{_cell(lp.status)} {what}")
    return _cell("; ".join(parts))


def render_report(results: list[ProbeResult], skipped: list[Bank], cfg: FetchConfig) -> str:
    counts = {c: sum(r.classification == c for r in results) for c in CLASSES}
    lines = [
        "# Bank website probe",
        "",
        f"- Run at: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
        f"- User-Agent: `{cfg.user_agent}`",
        f"- Min visible text for `ok`: {cfg.min_text_chars} characters; httpx timeout "
        f"{cfg.timeout_seconds:g} s; {cfg.min_delay_seconds:g} s between requests per domain",
        f"- Browser fallback: {'on' if cfg.browser_fallback else 'off'}; network idle up to "
        f"{cfg.browser_timeout_seconds:g} s, one retry",
        "- Page contents are not stored; this table only.",
        "",
        "| bank | class | status | text length | language | robots disallows home "
        "| method | final URL | title | language versions | notes |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for r in results:
        lines.append("| " + " | ".join(_cell(v) for v in (
            r.bank_id, r.classification, r.http_status, r.text_length, r.language,
            r.robots_disallows_home, r.method, r.final_url, r.title[:80])) + " | "
            + _lang_cell(r) + " | " + _cell("; ".join(r.notes)) + " |")
    lines += ["", "## Summary", "", "| class | banks |", "|---|---|"]
    lines += [f"| {c} | {n} |" for c, n in counts.items()]
    lines += [f"| skipped (no website_url) | {len(skipped)} |", ""]
    if skipped:
        lines += ["Skipped: " + ", ".join(b.id for b in skipped), ""]
    return "\n".join(lines)


def print_table(results: list[ProbeResult], skipped: list[Bank]) -> None:
    head = ("bank", "class", "status", "text_len", "language", "uz/ru versions")
    rows = [(r.bank_id, r.classification, _cell(r.http_status), _cell(r.text_length),
             _cell(r.language),
             ", ".join(f"{lp.key}:{lp.language or '-'}" for lp in r.lang_pages) or "-")
            for r in results]
    widths = [max(len(str(x)) for x in col) for col in zip(head, *rows)]
    for row in (head, *rows):
        print("  ".join(str(x).ljust(w) for x, w in zip(row, widths)))
    print()
    for c in CLASSES:
        print(f"{c:16} {sum(r.classification == c for r in results)}")
    print(f"{'skipped':16} {len(skipped)} (no website_url)")


def run(banks_path: Path = BANKS_YAML, report_path: Path = REPORT_PATH) -> list[ProbeResult]:
    cfg = FetchConfig.from_env()
    banks = load_banks(banks_path)
    targets = [b for b in banks if b.crawlable]
    skipped = [b for b in banks if not b.crawlable]
    prober = Prober(cfg)
    results: list[ProbeResult] = []
    try:
        for b in targets:
            print(f"probing {b.id} ...", file=sys.stderr)
            results.append(prober.probe(b))
        need_browser = cfg.browser_fallback and any(
            r.classification == "js_shell" for r in results)
        if need_browser:
            with Browser(cfg, prober.throttle) as browser:
                browser_retry(results, prober, browser)
                for r in results:
                    print(f"languages {r.bank_id} ...", file=sys.stderr)
                    prober.probe_languages(r, browser)
        else:
            for r in results:
                print(f"languages {r.bank_id} ...", file=sys.stderr)
                prober.probe_languages(r, None)
    finally:
        prober.close()
    print_table(results, skipped)
    report_path.write_text(render_report(results, skipped, cfg), encoding="utf-8")
    print(f"\nreport: {report_path}")
    return results


if __name__ == "__main__":
    run()
