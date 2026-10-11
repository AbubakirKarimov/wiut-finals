"""Optional rendering fallback through Jina Reader (https://r.jina.ai/<url>) for the hosted
demo, where no local browser runs. Enabled only with RENDER_FALLBACK=jina.

What is sent: the public page URL in the request path, our project User-Agent and the
format headers below. No API key, no cookies, no user data. What comes back: the page
rendered by Jina as Markdown with its links, which is turned into minimal HTML so the
crawler's usual text/link extraction, language detection and quote verification apply to
exactly the text Jina returned. Used only for pages that answered HTTP 200 with almost no
text (JavaScript shells): never for pages that blocked us (that would bypass a block).
"""

import html as htmllib
import re
import time

import httpx

from backend.crawl.fetch import DomainThrottle, FetchConfig, RenderResult

JINA_BASE = "https://r.jina.ai/"
_HEADER = re.compile(r"^(Title|URL Source|Published Time|Warning|Markdown Content):\s?(.*)$")
_IMAGE = re.compile(r"!\[[^\]]*\]\([^)]*\)")
_LINK = re.compile(r"\[([^\]]*)\]\((\S+?)(?:\s+\"[^\"]*\")?\)")
_MARK = re.compile(r"^\s*(?:[*+-]|\d+\.|#{1,6}|>)\s+")


def markdown_to_html(md: str) -> tuple[str, str | None, list[str]]:
    """(html, source url, warnings) from a Jina Reader Markdown response."""
    title, source, warnings, body = "", None, [], []
    in_body = False
    for line in md.splitlines():
        h = None if in_body else _HEADER.match(line)
        if h:
            key, val = h.groups()
            if key == "Title":
                title = val
            elif key == "URL Source":
                source = val.strip() or None
            elif key == "Warning":
                warnings.append(val)
            elif key == "Markdown Content":
                in_body = True
            continue
        if not in_body:
            continue
        line = _MARK.sub("", _IMAGE.sub("", line)).replace("**", "").replace("__", "")
        if set(line.strip()) <= set("-=*_|: "):  # rules, table separators, blank lines
            continue
        parts, last = [], 0
        for m in _LINK.finditer(line):
            parts.append(htmllib.escape(line[last:m.start()]))
            parts.append(f'<a href="{htmllib.escape(m.group(2), quote=True)}">'
                         f"{htmllib.escape(m.group(1))}</a>")
            last = m.end()
        parts.append(htmllib.escape(line[last:]))
        body.append(f"<p>{''.join(parts).strip()}</p>")
    doc = (f"<html><head><title>{htmllib.escape(title)}</title></head><body>"
           f"{''.join(body)}</body></html>")
    return doc, source, warnings


class JinaReader:
    """Same interface as fetch.Browser: a context manager with render(url, timeout, text_len)."""

    method = "jina"

    def __init__(self, cfg: FetchConfig, throttle: DomainThrottle,
                 transport: httpx.BaseTransport | None = None, min_delay: float = 3.0,
                 timeout_seconds: float = 20.0, locale: str = "uz-UZ"):
        self.cfg, self.throttle = cfg, throttle
        self.locale = locale
        self.min_delay, self.timeout = min_delay, timeout_seconds
        self._transport = transport
        self._client: httpx.Client | None = None
        self._last = float("-inf")

    def __enter__(self) -> "JinaReader":
        # A fresh client: no shared cookies or auth, only the headers listed here.
        self._client = httpx.Client(
            transport=self._transport, timeout=self.timeout, follow_redirects=False,
            headers={"User-Agent": self.cfg.user_agent, "Accept": "text/plain",
                     "X-No-Cache": "true", "X-Timeout": str(max(1, int(self.timeout) - 5)),
                     # Without a locale Jina's browser may get the English version (seen on
                     # universalbank.uz); the regulations concern the Uzbek-language site.
                     "X-Locale": self.locale})
        return self

    def __exit__(self, *exc) -> None:
        if self._client:
            self._client.close()

    def render(self, url: str, timeout_seconds: float | None = None,
               text_len=lambda html: 0) -> RenderResult:
        out = RenderResult(ok=False, final_url=url, attempts=1)
        # 1 request/s to the bank (Jina fetches it) and a slower pace to Jina itself.
        self.throttle.wait(url)
        gap = time.monotonic() - self._last
        if gap < self.min_delay:
            time.sleep(self.min_delay - gap)
        self._last = time.monotonic()
        timeout = min(self.timeout, timeout_seconds or self.timeout)
        try:
            r = self._client.get(JINA_BASE + url, timeout=timeout)
        except httpx.HTTPError as e:
            out.notes.append(f"jina: {type(e).__name__}")
            return out
        out.status = r.status_code
        if r.status_code != 200:
            out.notes.append(f"jina: HTTP {r.status_code}")
            return out
        html, source, warnings = markdown_to_html(r.text)
        out.notes += [f"jina warning: {w[:120]}" for w in warnings]
        if any(re.search(r"returned error|blocked|captcha|403|429", w, re.I) for w in warnings):
            out.notes.append("jina: the target page reported an error; not used")
            return out
        out.html, out.final_url = html, source or url
        if text_len(html) >= self.cfg.min_text_chars:
            out.ok = True
        else:
            out.notes.append("jina: page still has little text")
        return out
