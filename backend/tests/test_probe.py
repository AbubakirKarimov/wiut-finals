import httpx
import pytest

from backend.crawl import fetch as F
from backend.crawl import probe as P
from backend.crawl import text as T
from backend.crawl.banks import Bank

UA = "ComplianceRadar/0.1"
LONG_UZ = "<html><head><title>Bosh sahifa</title></head><body><p>" + \
    " ".join(["Bank xizmatlari va kredit uchun bilan omonat haqida"] * 30) + "</p>" \
    '<a href="/ru/">Рус</a><a href="/oz/">Ўзб</a></body></html>'
LONG_RU = "<html><body>" + " ".join(["Банковские услуги и вклады для физических лиц"] * 30) \
    + "</body></html>"


def test_visible_text_drops_scripts_and_styles():
    html = "<html><head><title>T</title><style>.a{}</style></head>" \
           "<body><script>var x=1</script><p>Salom  dunyo</p></body></html>"
    assert T.visible_text(html) == "Salom dunyo"
    assert T.page_title(html) == "T"


@pytest.mark.parametrize("text,lang", [
    ("Банк хизматлари бўйича қўшимча маълумот ҳақида", "uz_cyrl"),
    ("Банковские услуги для физических лиц и вклады с выгодой", "ru"),
    ("Bank xizmatlari va kredit olish uchun ariza", "uz_latn"),
    ("Read the news about our bank and your cards", "other"),
    ("12345 !!!", None),
])
def test_detect_language(text, lang):
    assert T.detect_language(text) == lang


def test_classify():
    assert T.classify(None, "", 0, 500) == "unreachable"
    for s in (403, 429, 503):
        assert T.classify(s, "", 0, 500) == "blocked"
    assert T.classify(200, "<div id=root></div>", 10, 500) == "js_shell"
    assert T.classify(200, "<title>Just a moment...</title>", 10, 500) == "blocked"
    # A real page that merely loads reCAPTCHA is not blocked.
    assert T.classify(200, "<script src=recaptcha></script>", 5000, 500) == "ok"
    assert T.classify(404, "", 0, 500) == "other"


def test_language_links():
    html = ('<link rel="alternate" hreflang="ru" href="https://bank.uz/ru/">'
            '<a href="/oz/">Ўзб</a><a href="https://other.uz/en/">EN</a>'
            '<a href="/uz/kredit">Kreditlar haqida batafsil malumot</a>'
            '<a href="?lang=en">EN</a>')
    found = T.language_links(html, "https://www.bank.uz/uz/")
    assert found == {"ru": "https://bank.uz/ru/", "uz_cyrl": "https://www.bank.uz/oz/",
                     "en": "https://www.bank.uz/uz/?lang=en"}


def test_robots_disallows():
    rules = "User-agent: ComplianceRadar\nDisallow: /\n\nUser-agent: *\nAllow: /\n"
    assert F.robots_disallows(rules, UA, "https://x.uz/")
    assert not F.robots_disallows("User-agent: *\nDisallow: /admin\n", UA, "https://x.uz/uz/")


def _prober(handler) -> P.Prober:
    cfg = F.FetchConfig(user_agent=UA, min_delay_seconds=0, min_text_chars=100)
    return P.Prober(cfg, transport=httpx.MockTransport(handler))


def _bank(url="https://bank.uz/uz/"):
    return Bank(id="b", name="B", website_url=url, role="fined_group")


def test_probe_ok_follows_redirect_and_sends_user_agent():
    seen = []

    def handler(req):
        seen.append((req.url.path, req.headers["user-agent"]))
        if req.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nAllow: /\n")
        if req.url.path == "/uz/":
            return httpx.Response(301, headers={"location": "/uz/home"})
        if req.url.path == "/ru/":
            return httpx.Response(200, html=LONG_RU)
        if req.url.path == "/oz/":
            return httpx.Response(404)
        return httpx.Response(200, html=LONG_UZ)

    pr = _prober(handler)
    r = pr.probe(_bank())
    assert r.classification == "ok" and r.http_status == 200
    assert r.final_url == "https://bank.uz/uz/home"
    assert r.language == "uz_latn" and r.title == "Bosh sahifa"
    assert r.robots_disallows_home is False
    assert all(ua == UA for _, ua in seen)
    pr.probe_languages(r, None)
    by_key = {lp.key: lp for lp in r.lang_pages}
    assert by_key["ru"].found_by == "link" and by_key["ru"].language == "ru"
    assert by_key["uz_cyrl"].status == 404
    assert by_key["uz"].found_by == "guess"  # no uz link on the page -> /uz/ tried


def test_probe_respects_robots_disallow():
    paths = []

    def handler(req):
        paths.append(req.url.path)
        return httpx.Response(200, text="User-agent: *\nDisallow: /\n")

    r = _prober(handler).probe(_bank())
    assert r.robots_disallows_home is True and r.classification == "other"
    assert paths == ["/robots.txt"]  # home page never requested


def test_probe_blocked_challenge_and_unreachable():
    def blocked(req):
        if req.url.path == "/robots.txt":
            return httpx.Response(404)
        return httpx.Response(403, html="<title>Attention Required! | Cloudflare</title>")

    r = _prober(blocked).probe(_bank())
    assert r.classification == "blocked" and r.http_status == 403

    def down(req):
        raise httpx.ConnectError("dns", request=req)

    assert _prober(down).probe(_bank()).classification == "unreachable"


class FakeBrowser:
    def __init__(self, result):
        self.result = result

    def render(self, url, timeout_seconds=None, text_len=None):
        return self.result


def test_browser_retry_marks_js_shell_failed():
    def handler(req):
        if req.url.path == "/robots.txt":
            return httpx.Response(404)
        return httpx.Response(200, html="<div id=root></div>")

    pr = _prober(handler)
    r = pr.probe(_bank())
    assert r.classification == "js_shell"
    P.browser_retry([r], pr, FakeBrowser(F.RenderResult(
        ok=False, html="<div id=root></div>", status=200, final_url=r.final_url, attempts=2,
        notes=["attempt 1: network idle not reached", "attempt 2: network idle not reached"])))
    assert r.classification == "js_shell_failed" and r.method == "browser"

    r2 = pr.probe(_bank())
    P.browser_retry([r2], pr, FakeBrowser(F.RenderResult(
        ok=True, html=LONG_UZ, status=200, final_url=r2.final_url, attempts=1)))
    assert r2.classification == "ok" and r2.language == "uz_latn"


def test_throttle_spaces_requests(monkeypatch):
    sleeps = []
    monkeypatch.setattr(F.time, "sleep", lambda s: sleeps.append(s))
    t = F.DomainThrottle(1.0)
    t.wait("https://a.uz/1")
    t.wait("https://b.uz/1")   # other host: no wait
    t.wait("https://a.uz/2")   # same host: must wait
    assert len(sleeps) == 1 and 0 < sleeps[0] <= 1.0


def test_crawl_delay_raises_throttle():
    def handler(req):
        return httpx.Response(200, text="User-agent: *\nCrawl-delay: 3\nAllow: /\n")

    f = F.Fetcher(F.FetchConfig(user_agent=UA, min_delay_seconds=0),
                  transport=httpx.MockTransport(handler))
    f.robots_for("https://slow.uz/")
    assert f.throttle._delay["slow.uz"] == 3.0


def test_report_has_no_page_text():
    res = P.ProbeResult(bank_id="b", url="https://bank.uz/", classification="ok",
                        http_status=200, text_length=1234, language="ru", title="Home",
                        html="<p>SECRET PAGE BODY</p>")
    out = P.render_report([res], [], F.FetchConfig())
    assert "| b | ok | 200 | 1234 | ru |" in out
    assert "| ok | 1 |" in out and "| js_shell_failed | 0 |" in out
    assert "SECRET" not in out
