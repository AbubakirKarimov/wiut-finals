import httpx
import pytest

from backend.crawl import probe as P
from backend.crawl.banks import Bank

UA = "ComplianceRadar/0.1"
LONG_UZ = "<html><head><title>Bosh sahifa</title></head><body><p>" + \
    " ".join(["Bank xizmatlari va kredit uchun bilan omonat haqida"] * 30) + "</p></body></html>"


def test_visible_text_drops_scripts_and_styles():
    html = "<html><head><title>T</title><style>.a{}</style></head>" \
           "<body><script>var x=1</script><p>Salom  dunyo</p></body></html>"
    assert P.visible_text(html) == "Salom dunyo"
    assert P.page_title(html) == "T"


@pytest.mark.parametrize("text,lang", [
    ("Банк хизматлари бўйича қўшимча маълумот ҳақида", "uz_cyrl"),
    ("Банковские услуги для физических лиц и вклады с выгодой", "ru"),
    ("Bank xizmatlari va kredit olish uchun ariza", "uz_latn"),
    ("Read the news about our bank and your cards", "other"),
    ("12345 !!!", None),
])
def test_detect_language(text, lang):
    assert P.detect_language(text) == lang


def test_classify():
    assert P.classify(None, "", 0, 500) == "unreachable"
    for s in (403, 429, 503):
        assert P.classify(s, "", 0, 500) == "blocked"
    assert P.classify(200, "<div id=root></div>", 10, 500) == "js_shell"
    assert P.classify(200, "<title>Just a moment...</title>", 10, 500) == "blocked"
    # A real page that merely loads reCAPTCHA is not blocked.
    assert P.classify(200, "<script src=recaptcha></script>", 5000, 500) == "ok"
    assert P.classify(404, "", 0, 500) == "other"


def test_robots_disallows():
    rules = "User-agent: ComplianceRadar\nDisallow: /\n\nUser-agent: *\nAllow: /\n"
    assert P.robots_disallows(rules, UA, "https://x.uz/")
    assert not P.robots_disallows("User-agent: *\nDisallow: /admin\n", UA, "https://x.uz/uz/")


def _prober(handler) -> P.Prober:
    pr = P.Prober(P.ProbeConfig(user_agent=UA, min_delay_seconds=0, min_text_chars=100))
    pr.client = httpx.Client(transport=httpx.MockTransport(handler),
                             headers={"User-Agent": UA}, follow_redirects=False)
    return pr


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
        return httpx.Response(200, html=LONG_UZ)

    r = _prober(handler).probe(_bank())
    assert r.classification == "ok" and r.http_status == 200
    assert r.final_url == "https://bank.uz/uz/home"
    assert r.language == "uz_latn" and r.title == "Bosh sahifa"
    assert r.robots_disallows_home is False
    assert all(ua == UA for _, ua in seen)


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


def test_throttle_spaces_requests(monkeypatch):
    sleeps = []
    monkeypatch.setattr(P.time, "sleep", lambda s: sleeps.append(s))
    t = P.DomainThrottle(1.0)
    t.wait("https://a.uz/1")
    t.wait("https://b.uz/1")   # other host: no wait
    t.wait("https://a.uz/2")   # same host: must wait
    assert len(sleeps) == 1 and 0 < sleeps[0] <= 1.0


def test_report_has_no_page_text(tmp_path):
    res = P.ProbeResult(bank_id="b", url="https://bank.uz/", classification="ok",
                        http_status=200, text_length=1234, language="ru", title="Home")
    out = P.render_report([res], [], P.ProbeConfig())
    assert "| b | ok | 200 | 1234 | ru |" in out
    assert "| ok | 1 |" in out and "| blocked | 0 |" in out
