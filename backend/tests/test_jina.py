"""RENDER_FALLBACK=jina: JavaScript-only pages rendered through Jina Reader (mocked here)."""

import httpx

from backend.crawl.crawler import CrawlConfig, Crawler
from backend.crawl.fetch import FetchConfig, Fetcher
from backend.crawl.jina import JinaReader, markdown_to_html
from backend.crawl.text import links, visible_text

SHELL = "<html><body><div id='root'></div><script src='/app.js'></script></body></html>"
BODY = ("Bank xizmatlari, omonatlar va kreditlar haqida batafsil ma'lumot. " * 12)
HOME_MD = f"""Title: Bank
URL Source: https://spa-bank.example/uz/

Markdown Content:
*   [Omonatlar](https://spa-bank.example/uz/deposits)
*   [![Image 1: logo](https://spa-bank.example/logo.png) Kreditlar](https://spa-bank.example/uz/credits)

{BODY}
"""
PAGE_MD = f"Title: Omonatlar\nURL Source: {{u}}\n\nMarkdown Content:\n**Omonatlar**\n\n{BODY}\n"


def _site(req):
    if req.url.path == "/robots.txt":
        return httpx.Response(404)
    return httpx.Response(200, html=SHELL)


def _crawl(jina_handler):
    seen = []

    def handler(req):
        seen.append(req)
        return jina_handler(req)

    f = FetchConfig(user_agent="ComplianceRadar/0.1", min_delay_seconds=0,
                    browser_fallback=False, render_fallback="jina")
    fetcher = Fetcher(f, transport=httpx.MockTransport(_site))
    crawler = Crawler(CrawlConfig(fetch=f, max_pages=3), fetcher=fetcher,
                      browser_factory=lambda: JinaReader(
                          f, fetcher.throttle, transport=httpx.MockTransport(handler),
                          min_delay=0))
    return crawler.crawl("spa_bank", "https://spa-bank.example/uz/"), seen


def test_markdown_keeps_text_and_links_without_images():
    html, source, warnings = markdown_to_html(HOME_MD)
    assert source == "https://spa-bank.example/uz/" and warnings == []
    assert ("https://spa-bank.example/uz/deposits", "Omonatlar") in links(html, source)
    assert "logo.png" not in html and "Image 1" not in visible_text(html)
    assert "omonatlar va kreditlar" in visible_text(html)


def test_success_renders_pages_with_link_data_and_sends_only_the_public_url():
    def jina(req):
        target = str(req.url)[len("https://r.jina.ai/"):]
        md = HOME_MD if target.endswith("/uz/") else PAGE_MD.format(u=target)
        return httpx.Response(200, text=md)

    res, seen = _crawl(jina)
    assert res.status == "ok" and res.method == "jina"
    assert len(res.pages) == 3
    assert all(p.links is not None for p in res.pages)
    assert res.pages[0].links  # link data preserved from the Markdown
    assert any("Jina Reader" in n for n in res.notes)
    for req in seen:
        assert str(req.url).startswith("https://r.jina.ai/https://spa-bank.example/")
        assert "authorization" not in req.headers and "cookie" not in req.headers
        assert req.method == "GET" and not req.content


def test_timeout_keeps_the_page_not_checkable():
    def jina(req):
        raise httpx.ReadTimeout("timed out", request=req)

    res, _ = _crawl(jina)
    assert res.status == "js_shell_failed" and res.pages == []
    assert any("jina: ReadTimeout" in n for n in res.notes)


def test_too_short_text_keeps_the_page_not_checkable():
    def jina(req):
        return httpx.Response(200, text="Title: x\nURL Source: https://spa-bank.example/uz/\n\n"
                                        "Markdown Content:\nYou need to enable JavaScript.\n")

    res, _ = _crawl(jina)
    assert res.status == "js_shell_failed" and res.pages == []
    assert any("little text" in n for n in res.notes)


def test_target_error_reported_by_jina_is_not_used():
    def jina(req):
        return httpx.Response(200, text="Title: x\nURL Source: https://spa-bank.example/uz/\n"
                                        "Warning: Target URL returned error 403: Forbidden\n\n"
                                        f"Markdown Content:\n{BODY}\n")

    res, _ = _crawl(jina)
    assert res.status == "js_shell_failed"


def test_off_by_default():
    assert FetchConfig().render_fallback == ""
    f = FetchConfig(min_delay_seconds=0, browser_fallback=False)
    crawler = Crawler(CrawlConfig(fetch=f),
                      fetcher=Fetcher(f, transport=httpx.MockTransport(_site)))
    res = crawler.crawl("spa_bank", "https://spa-bank.example/uz/")
    assert res.status == "needs_browser"
