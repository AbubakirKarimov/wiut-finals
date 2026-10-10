import httpx

from backend import db
from backend.crawl.crawler import CrawlConfig, Crawler, pdf_text
from backend.crawl.fetch import FetchConfig, Fetcher

UA = "ComplianceRadar/0.1"
UZ = " ".join(["Bank xizmatlari va kredit uchun bilan omonat haqida ma'lumot"] * 20)
RU = " ".join(["Банковские услуги, вклады и кредиты для физических лиц"] * 20)


def make_pdf(text: str) -> bytes:
    """Smallest valid one-page PDF with a text layer (Helvetica, ASCII text)."""
    stream = f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode()
    objs = [b"<< /Type /Catalog /Pages 2 0 R >>",
            b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R "
            b"/Resources << /Font << /F1 5 0 R >> >> >>",
            b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream",
            b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"]
    out, offsets = bytearray(b"%PDF-1.4\n"), []
    for i, o in enumerate(objs, 1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % i + o + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1)
    out += b"".join(b"%010d 00000 n \n" % off for off in offsets)
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objs) + 1, xref)
    return bytes(out)


SITE = {
    "/robots.txt": (200, "text/plain", "User-agent: *\nDisallow: /private/\n"),
    "/uz/": (200, "text/html", f"<html><title>Bosh</title><body><p>{UZ}</p>"
             '<a href="/ru/">Рус</a><a href="/uz/tariflar">Tariflar</a>'
             '<a href="/uz/news">Yangiliklar</a><a href="/private/x">x</a>'
             '<a href="/uz/missing">x</a><a href="/uz/search/?q=kredit">s</a>'
             '<a href="/uz/old">old</a><a href="/files/tarif.pdf">PDF</a>'
             '<a href="https://other.uz/">ext</a><a href="/logo.png">logo</a></body></html>'),
    "/ru/": (200, "text/html", f"<html><body><p>{RU}</p><a href='/ru/deep'>d</a></body></html>"),
    "/uz/tariflar": (200, "text/html", f"<html><body><p>{UZ}</p>"
                     "<a href='/uz/tariflar/level3'>deeper</a></body></html>"),
    "/uz/old": (301, "text/html", ""),
    "/uz/news": (200, "text/html", f"<html><body><p>{UZ}</p></body></html>"),
    "/ru/deep": (200, "text/html", f"<html><body><p>{RU}</p></body></html>"),
    "/uz/tariflar/level3": (200, "text/html", "<p>depth 2</p><a href='/uz/level4'>d</a>"),
    "/uz/level4": (200, "text/html", "<p>too deep</p>"),
    "/files/tarif.pdf": (200, "application/pdf", make_pdf("Tariff list 2026")),
}


def site_handler(requests_seen):
    def handler(req):
        requests_seen.append(req.url.path)
        status, ctype, body = SITE.get(req.url.path, (404, "text/html", "not found"))
        if status == 301:
            return httpx.Response(301, headers={"location": "/uz/news"})
        content = body if isinstance(body, bytes) else body.encode()
        return httpx.Response(status, headers={"content-type": ctype}, content=content)
    return handler


def crawler(handler, **kw) -> Crawler:
    fcfg = FetchConfig(user_agent=UA, min_delay_seconds=0, min_text_chars=100,
                       browser_fallback=kw.pop("browser", True))
    cfg = CrawlConfig(fetch=fcfg, **kw)
    return Crawler(cfg, fetcher=Fetcher(fcfg, transport=httpx.MockTransport(handler)))


def test_pdf_text_extracts_text_layer():
    assert pdf_text(make_pdf("Hello tariff"), 5) == "Hello tariff"


def test_crawl_depth_robots_languages_pdf():
    seen: list[str] = []
    res = crawler(site_handler(seen), max_depth=2, max_pages=15).crawl("b", "https://bank.uz/uz/")
    urls = {u.split("bank.uz")[1] for u in res.urls_read}
    assert res.status == "ok"
    assert {"/uz/", "/ru/", "/uz/tariflar", "/uz/news", "/files/tarif.pdf", "/ru/deep"} <= urls
    assert "/uz/tariflar/level3" in urls and "/uz/level4" not in seen  # depth 3 > max_depth
    assert "/private/x" not in seen                   # robots.txt respected
    assert not any("other.uz" in u for u in res.urls_read) and "/logo.png" not in seen
    assert res.has_language_switcher is True and "ru" in res.language_links
    langs = {u.split("bank.uz")[1]: p.language for u, p in zip(res.urls_read, res.pages)}
    assert langs["/uz/"] == "uz_latn" and langs["/ru/"] == "ru"
    pdf = next(p for p in res.pages if p.source_type == "pdf")
    assert pdf.text == "Tariff list 2026" and pdf.readable
    assert "/uz/search/" not in seen
    assert len(res.urls_read) == len(set(res.urls_read))  # /uz/old -> /uz/news not doubled
    assert res.fetch_errors == []                     # a 404 link is skipped, not an error
    assert any("missing" in s for s in res.skipped)


def test_page_limit_and_language_links_first():
    res = crawler(site_handler([]), max_pages=2).crawl("b", "https://bank.uz/uz/")
    assert [u.split("bank.uz")[1] for u in res.urls_read] == ["/uz/", "/ru/"]


def test_time_budget_stops_crawl():
    res = crawler(site_handler([]), time_budget_seconds=0).crawl("b", "https://bank.uz/uz/")
    assert len(res.pages) == 1 and res.budget_exhausted


def test_js_shell_without_browser_is_needs_browser():
    def handler(req):
        if req.url.path == "/robots.txt":
            return httpx.Response(404)
        return httpx.Response(200, html="<div id=root></div>")

    res = crawler(handler, browser=False).crawl("b", "https://spa.uz/")
    assert res.status == "needs_browser"
    assert res.reason.startswith("page needs JavaScript rendering; not available on this "
                                 "hosted demo")
    assert res.pages == []


def test_blocked_and_unreachable():
    def blocked(req):
        if req.url.path == "/robots.txt":
            return httpx.Response(404)
        return httpx.Response(403, html="<title>Just a moment...</title>")

    res = crawler(blocked).crawl("b", "https://cf.uz/")
    assert res.status == "blocked" and res.fetch_errors

    def down(req):
        raise httpx.ConnectTimeout("timeout", request=req)

    res = crawler(down).crawl("b", "https://down.uz/")
    assert res.status == "unreachable"


def test_server_errors_count_as_fetch_errors():
    def handler(req):
        if req.url.path == "/robots.txt":
            return httpx.Response(404)
        if req.url.path == "/":
            return httpx.Response(200, html=f"<p>{UZ}</p><a href='/broken'>b</a>")
        return httpx.Response(502)

    res = crawler(handler).crawl("b", "https://x.uz/")
    assert any("/broken: HTTP 502" in e for e in res.fetch_errors)


def test_pages_stored_in_sqlite(tmp_db):
    res = crawler(site_handler([])).crawl("b", "https://bank.uz/uz/", run_id="r1")
    with db.connect(tmp_db) as conn:
        for p in res.pages:
            db.upsert_page(conn, p)
    with db.connect(tmp_db) as conn:
        stored = db.list_pages(conn, "b", run_id="r1")
    assert len(stored) == len(res.pages)
    assert {p.language for p in stored} >= {"uz_latn", "ru"}


def test_section_pages_fetched_first_within_page_cap():
    """Deposit, loan and document links come before generic pages; sections take turns."""
    generic = "".join(f'<a href="/uz/news/{i}">Yangilik {i}</a>' for i in range(10))
    home = (f"<html><body><p>{UZ}</p><a href=\"/uz/\">Oʻz</a><a href=\"/ru/\">Рус</a>{generic}"
            '<a href="/uz/kredit/avto">Avtokredit</a><a href="/uz/kredit/ipoteka">Ipoteka</a>'
            '<a href="/uz/contacts">Aloqa</a>'
            '<a href="/uz/private/deposit/">Omonatlar</a>'
            '<a href="/uz/about/documents/">Hujjatlar</a></body></html>')

    def handler(req):
        if req.url.path == "/robots.txt":
            return httpx.Response(404)
        body = home if req.url.path == "/uz/" else f"<html><body><p>{UZ}</p></body></html>"
        return httpx.Response(200, headers={"content-type": "text/html"}, content=body.encode())

    res = crawler(handler, max_pages=6).crawl("b", "https://bank.uz/uz/")
    paths = [u.split("bank.uz")[1] for u in res.urls_read]
    # home, /ru/ (language version first), then one page per core section, then the 2nd loan page
    assert paths[0] == "/uz/" and paths[1] == "/ru/"
    assert set(paths[2:5]) == {"/uz/kredit/avto", "/uz/private/deposit/", "/uz/about/documents/"}
    assert paths[5] == "/uz/kredit/ipoteka"
    assert not any("/news/" in p for p in paths)


class FakeBrowser:
    def __init__(self, html, calls):
        self.html, self.calls = html, calls

    def __enter__(self):
        return self

    def __exit__(self, *a):
        pass

    def render(self, url, timeout_seconds=None, text_len=None):
        from backend.crawl.fetch import RenderResult
        self.calls.append(url)
        return RenderResult(ok=self.html is not None, html=self.html or "", status=200,
                            final_url=url, attempts=1)


def short_home_site(req):
    if req.url.path == "/robots.txt":
        return httpx.Response(404)
    body = f"<html><body><p>{UZ}</p><a href='/uz/omonat'>Omonat</a></body></html>"
    return httpx.Response(200, headers={"content-type": "text/html"}, content=body.encode())


def short_home_crawler(html, calls, browser=True, min_chars=5000):
    fcfg = FetchConfig(user_agent=UA, min_delay_seconds=0, min_text_chars=100,
                       browser_fallback=browser)
    return Crawler(CrawlConfig(fetch=fcfg, max_pages=3, homepage_min_chars=min_chars),
                   fetcher=Fetcher(fcfg, transport=httpx.MockTransport(short_home_site)),
                   browser_factory=lambda: FakeBrowser(html, calls))


def test_short_home_page_is_rendered_once_in_a_browser():
    calls = []
    rich = ("<html><body><p>" + UZ * 4 + "</p><a href='/uz/murojaat'>Murojaat yuborish</a>"
            "</body></html>")
    res = short_home_crawler(rich, calls).crawl("b", "https://bank.uz/uz/")
    assert calls == ["https://bank.uz/uz/"]                       # once, the home page only
    assert len(res.pages[0].text) > len(UZ) * 3
    assert ("https://bank.uz/uz/murojaat", "Murojaat yuborish") in res.pages[0].links
    assert any("re-rendered in a browser" in n for n in res.notes)


def test_short_home_page_kept_when_browser_gives_nothing_more():
    calls = []
    res = short_home_crawler(None, calls).crawl("b", "https://bank.uz/uz/")
    assert calls == ["https://bank.uz/uz/"] and res.pages[0].text.startswith("Bank xizmatlari")
    assert any("no usable page" in n for n in res.notes)


def test_short_home_page_not_rendered_when_fallback_off_or_long_enough():
    calls = []
    short_home_crawler("<p>x</p>", calls, browser=False).crawl("b", "https://bank.uz/uz/")
    short_home_crawler("<p>x</p>", calls, min_chars=100).crawl("b", "https://bank.uz/uz/")
    assert calls == []
