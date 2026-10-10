"""LLM layer tests: no network. A fake provider and httpx.MockTransport stand in for APIs."""

import json

import httpx
import pytest
from pydantic import BaseModel

from backend import db
from backend.llm import provider as llm


class Answer(BaseModel):
    present: bool
    quote: str


NO_RETRY = llm.RateLimits(max_retries=0, min_interval_seconds=0)


class FakeProvider(llm.LLMProvider):
    """Returns scripted raw replies (or raises scripted errors) in order."""

    def __init__(self, replies, *, name="fake", model="fake-model", db_path=None,
                 limits=NO_RETRY):
        super().__init__(db_path, limits)
        self.replies = list(replies)
        self.name, self.model = name, model
        self.calls = 0
        self.slept = []
        self._sleep = self.slept.append

    def _complete(self, prompt, schema):
        self.calls += 1
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return llm.RawCompletion(text=reply, input_tokens=11, output_tokens=7)


def calls(path):
    with db.connect(path) as conn:
        return [dict(r) for r in conn.execute("SELECT * FROM llm_calls ORDER BY id")]


def test_valid_json_is_validated_cached_and_logged(tmp_db):
    p = FakeProvider(['{"present": true, "quote": "Ўзбек тилида"}'], db_path=tmp_db)
    assert p.complete_json("prompt", Answer) == {"present": True, "quote": "Ўзбек тилида"}
    # Second identical request is served from the cache: no new provider call.
    assert p.complete_json("prompt", Answer) == {"present": True, "quote": "Ўзбек тилида"}
    assert p.calls == 1
    rows = calls(tmp_db)
    assert [(r["ok"], r["cache_hit"]) for r in rows] == [(1, 0), (1, 1)]
    assert rows[0]["input_tokens"] == 11 and rows[0]["output_tokens"] == 7
    assert rows[1]["input_tokens"] is None


def test_cache_key_depends_on_prompt_model_and_schema(tmp_db):
    p = FakeProvider(['{"present": true, "quote": "a"}', '{"present": false, "quote": ""}'],
                     db_path=tmp_db)
    p.complete_json("prompt A", Answer)
    p.complete_json("prompt B", Answer)
    assert p.calls == 2


def test_one_retry_on_invalid_json_then_success(tmp_db):
    p = FakeProvider(["not json", '```json\n{"present": false, "quote": ""}\n```'],
                     db_path=tmp_db)
    assert p.complete_json("prompt", Answer) == {"present": False, "quote": ""}
    assert p.calls == 2
    assert [r["ok"] for r in calls(tmp_db)] == [0, 1]


def test_invalid_json_twice_raises_clear_error(tmp_db):
    p = FakeProvider(['{"present": "maybe"}', "still not json"], db_path=tmp_db)
    with pytest.raises(llm.LLMResponseError, match="invalid JSON for Answer twice"):
        p.complete_json("prompt", Answer)
    assert p.calls == 2
    with db.connect(tmp_db) as conn:
        assert conn.execute("SELECT COUNT(*) FROM llm_cache").fetchone()[0] == 0


def test_fallback_on_transient_error_only(tmp_db):
    first = FakeProvider([llm.LLMTransientError("HTTP 429")], name="first", db_path=tmp_db)
    second = FakeProvider(['{"present": true, "quote": "x"}'], name="second", db_path=tmp_db)
    fb = llm.FallbackProvider([first, second])
    assert fb.complete_json("prompt", Answer)["quote"] == "x"
    assert [r["provider"] for r in calls(tmp_db)] == ["first", "second"]

    bad = FakeProvider([llm.LLMError("HTTP 401")], name="bad", db_path=tmp_db)
    unused = FakeProvider(['{"present": true, "quote": "x"}'], name="unused", db_path=tmp_db)
    with pytest.raises(llm.LLMError, match="401"):
        llm.FallbackProvider([bad, unused]).complete_json("other prompt", Answer)
    assert unused.calls == 0


def test_all_providers_transient_raises(tmp_db):
    a = FakeProvider([llm.LLMTransientError("HTTP 503")], name="a", db_path=tmp_db)
    b = FakeProvider([llm.LLMTransientError("timeout")], name="b", db_path=tmp_db)
    with pytest.raises(llm.LLMTransientError, match="all providers failed"):
        llm.FallbackProvider([a, b]).complete_json("prompt", Answer)


# ---- OpenAI-compatible provider over a mock transport

def _chat_reply(content, usage=True):
    body = {"choices": [{"message": {"content": content}}]}
    if usage:
        body["usage"] = {"prompt_tokens": 120, "completion_tokens": 30}
    return httpx.Response(200, json=body)


def test_openai_compatible_request_and_usage(tmp_db):
    seen = {}

    def handler(request):
        seen["url"] = str(request.url)
        seen["auth"] = request.headers["authorization"]
        seen["body"] = json.loads(request.content)
        return _chat_reply('{"present": true, "quote": "q"}')

    p = llm.OpenAICompatibleProvider("https://example.test/v1/", "secret-key", "m-1",
                                     db_path=tmp_db, transport=httpx.MockTransport(handler),
                                     limits=NO_RETRY)
    assert p.complete_json("Is X present?", Answer) == {"present": True, "quote": "q"}
    assert seen["url"] == "https://example.test/v1/chat/completions"
    assert seen["auth"] == "Bearer secret-key"
    assert seen["body"]["model"] == "m-1"
    assert seen["body"]["response_format"] == {"type": "json_object"}
    assert "Is X present?" in seen["body"]["messages"][1]["content"]
    [row] = calls(tmp_db)
    assert (row["provider"], row["model"]) == ("openai-compatible:example.test", "m-1")
    assert (row["input_tokens"], row["output_tokens"]) == (120, 30)
    assert "secret-key" not in repr(p)


@pytest.mark.parametrize("status,error", [(429, llm.LLMTransientError),
                                          (503, llm.LLMTransientError),
                                          (401, llm.LLMError)])
def test_openai_compatible_status_mapping(tmp_db, status, error):
    p = llm.OpenAICompatibleProvider(
        "https://example.test/v1", "k", "m", db_path=tmp_db, limits=NO_RETRY,
        transport=httpx.MockTransport(lambda r: httpx.Response(status, text="err")))
    with pytest.raises(error) as exc:
        p.complete_json("prompt", Answer)
    assert (status == 401) != isinstance(exc.value, llm.LLMTransientError)
    row = calls(tmp_db)[0]
    assert row["ok"] == 0 and str(status) in row["error"] and "k" not in row["error"].split()


def test_openai_compatible_timeout_is_transient(tmp_db):
    def handler(request):
        raise httpx.ReadTimeout("slow", request=request)

    p = llm.OpenAICompatibleProvider("https://example.test/v1", "k", "m", db_path=tmp_db,
                                     transport=httpx.MockTransport(handler), limits=NO_RETRY)
    with pytest.raises(llm.LLMTransientError, match="timeout"):
        p.complete_json("prompt", Answer)


def test_error_log_never_contains_key_or_prompt(tmp_db):
    p = llm.OpenAICompatibleProvider(
        "https://example.test/v1", "sk-very-secret", "m", db_path=tmp_db, limits=NO_RETRY,
        transport=httpx.MockTransport(lambda r: _chat_reply("garbage")))
    with pytest.raises(llm.LLMResponseError):
        p.complete_json("CONFIDENTIAL PROMPT TEXT", Answer)
    dump = json.dumps(calls(tmp_db))
    assert "sk-very-secret" not in dump and "CONFIDENTIAL PROMPT TEXT" not in dump


# ---- rate limits: Retry-After, exponential backoff, pacing

def test_backoff_uses_retry_after_then_exponential(tmp_db):
    limits = llm.RateLimits(max_retries=3, backoff_seconds=2, max_wait_seconds=60,
                            min_interval_seconds=0)
    p = FakeProvider([llm.LLMTransientError("HTTP 429", retry_after=7),
                      llm.LLMTransientError("HTTP 503"),
                      llm.LLMTransientError("timeout"),
                      '{"present": true, "quote": "x"}'], db_path=tmp_db, limits=limits)
    assert p.complete_json("prompt", Answer)["quote"] == "x"
    assert p.slept == [7, 4, 8]  # Retry-After, then 2*2**1, 2*2**2
    assert [r["ok"] for r in calls(tmp_db)] == [0, 0, 0, 1]
    assert len({r["cache_key"] for r in calls(tmp_db)}) == 1


def test_backoff_gives_up_and_fallback_takes_over(tmp_db):
    limits = llm.RateLimits(max_retries=1, backoff_seconds=1, min_interval_seconds=0)
    first = FakeProvider([llm.LLMTransientError("HTTP 429")] * 2, name="first",
                         db_path=tmp_db, limits=limits)
    second = FakeProvider(['{"present": true, "quote": "y"}'], name="second", db_path=tmp_db)
    assert llm.FallbackProvider([first, second]).complete_json("p", Answer)["quote"] == "y"
    assert first.calls == 2 and first.slept == [1]


def test_long_retry_after_is_not_waited_out(tmp_db):
    limits = llm.RateLimits(max_retries=3, max_wait_seconds=60, min_interval_seconds=0)
    p = FakeProvider([llm.LLMTransientError("HTTP 429", retry_after=600)], db_path=tmp_db,
                     limits=limits)
    with pytest.raises(llm.LLMTransientError):
        p.complete_json("prompt", Answer)
    assert p.slept == [] and p.calls == 1


def test_min_interval_between_api_calls_but_not_cache_hits(tmp_db):
    limits = llm.RateLimits(max_retries=0, min_interval_seconds=5)
    p = FakeProvider(['{"present": true, "quote": "a"}', '{"present": true, "quote": "b"}'],
                     db_path=tmp_db, limits=limits)
    p.complete_json("one", Answer)
    p.complete_json("one", Answer)  # cache hit: no pacing
    p.complete_json("two", Answer)
    assert len(p.slept) == 1 and 0 < p.slept[0] <= 5


def test_parse_retry_after():
    assert llm.parse_retry_after("12") == 12.0
    assert llm.parse_retry_after(None) is None
    assert llm.parse_retry_after("garbage") is None
    assert llm.parse_retry_after("Wed, 21 Oct 2015 07:28:00 GMT") == 0.0  # in the past


def test_http_429_retry_after_header_is_read(tmp_db):
    replies = iter([httpx.Response(429, headers={"Retry-After": "3"}, text="slow down"),
                    _chat_reply('{"present": true, "quote": "q"}')])
    p = llm.OpenAICompatibleProvider(
        "https://example.test/v1", "k", "m", db_path=tmp_db,
        limits=llm.RateLimits(max_retries=2, min_interval_seconds=0),
        transport=httpx.MockTransport(lambda r: next(replies)))
    slept = []
    p._sleep = slept.append
    assert p.complete_json("prompt", Answer)["quote"] == "q"
    assert slept == [3.0]


# ---- configuration from env

def _clear_llm_env(monkeypatch):
    for k in ("BASE_URL", "API_KEY", "MODEL"):
        monkeypatch.setenv(f"LLM_{k}", "")
        for n in (1, 2):
            monkeypatch.setenv(f"LLM_FALLBACK_{n}_{k}", "")


def test_missing_key_gives_clear_config_error(monkeypatch, tmp_db):
    _clear_llm_env(monkeypatch)
    monkeypatch.setenv("LLM_BASE_URL", "https://example.test/v1")
    monkeypatch.setenv("LLM_MODEL", "m")
    with pytest.raises(llm.LLMConfigError, match="LLM_API_KEY not set in .env"):
        llm.provider_from_env(db_path=tmp_db)


def test_env_builds_fallback_chain(monkeypatch, tmp_db):
    _clear_llm_env(monkeypatch)
    for prefix, host in (("LLM_", "a.test"), ("LLM_FALLBACK_1_", "b.test")):
        monkeypatch.setenv(f"{prefix}BASE_URL", f"https://{host}/v1")
        monkeypatch.setenv(f"{prefix}API_KEY", "k")
        monkeypatch.setenv(f"{prefix}MODEL", "m")
    p = llm.provider_from_env(db_path=tmp_db)
    assert isinstance(p, llm.FallbackProvider)
    assert [x.name for x in p.providers] == ["openai-compatible:a.test",
                                             "openai-compatible:b.test"]
    monkeypatch.setenv("LLM_FALLBACK_2_BASE_URL", "https://c.test/v1")
    with pytest.raises(llm.LLMConfigError, match="LLM_FALLBACK_2_API_KEY"):
        llm.provider_from_env(db_path=tmp_db)
