"""Progress events, per-check deadline, fallback after long waits, request options."""

import json
import time

import httpx
import pytest

from backend.llm import provider as llm
from backend.tests.test_llm import Answer, FakeProvider

OK = '{"present": true, "quote": "a"}'


def limits(**kw):
    base = dict(max_retries=3, min_interval_seconds=0, backoff_seconds=1, max_wait_seconds=60)
    base.update(kw)
    return llm.RateLimits(**base)


def test_events_report_attempts_waits_and_tokens(tmp_db):
    p = FakeProvider([llm.LLMTransientError("x: HTTP 429", retry_after=20), OK],
                     db_path=tmp_db, limits=limits())
    events = []
    p.on_event = events.append
    assert p.complete_json("prompt", Answer)["present"] is True
    assert p.slept == [20]
    assert events[0].startswith("calling LLM fake-model (attempt 1")
    assert "rate limited, waiting 20 s" in events
    assert events[2].startswith("calling LLM fake-model (attempt 2")
    assert "11 input / 7 output tokens" in events[3]
    p.complete_json("prompt", Answer)
    assert events[-1] == "LLM answer from cache"


def test_wait_beyond_deadline_raises_timeout(tmp_db):
    p = FakeProvider([llm.LLMTransientError("x: HTTP 429", retry_after=50), OK],
                     db_path=tmp_db, limits=limits())
    p.deadline = time.monotonic() + 10
    with pytest.raises(llm.LLMTimeoutError, match="would exceed the check timeout"):
        p.complete_json("prompt", Answer)
    assert p.slept == []  # never waited silently


def test_expired_deadline_stops_before_calling(tmp_db):
    p = FakeProvider([OK], db_path=tmp_db, limits=limits())
    p.deadline = time.monotonic() - 1
    with pytest.raises(llm.LLMTimeoutError):
        p.complete_json("prompt", Answer)
    assert p.calls == 0


def test_fallback_when_wait_exceeds_threshold(tmp_db):
    primary = FakeProvider([llm.LLMTransientError("p: HTTP 429", retry_after=45)],
                           name="p", model="primary-model", db_path=tmp_db, limits=limits())
    backup = FakeProvider([OK], name="b", model="backup-model", db_path=tmp_db,
                          limits=limits())
    chain = llm.FallbackProvider([primary, backup], fallback_after_seconds=30)
    events = []
    chain.on_event = events.append
    assert chain.complete_json("prompt", Answer)["present"] is True
    assert primary.slept == [] and backup.calls == 1
    assert "switching to fallback model backup-model" in events
    # Primary is cooling down (Retry-After 45 s): the next call goes to the backup first.
    backup.replies.append('{"present": false, "quote": ""}')
    assert chain.complete_json("other prompt", Answer)["present"] is False
    assert primary.calls == 1


def test_short_wait_stays_on_primary(tmp_db):
    primary = FakeProvider([llm.LLMTransientError("p: HTTP 429", retry_after=5), OK],
                           name="p", db_path=tmp_db, limits=limits())
    backup = FakeProvider([], name="b", db_path=tmp_db, limits=limits())
    chain = llm.FallbackProvider([primary, backup], fallback_after_seconds=30)
    assert chain.complete_json("prompt", Answer)["present"] is True
    assert primary.slept == [5] and backup.calls == 0


def test_request_has_max_tokens_and_reasoning_effort(tmp_db):
    bodies = []

    def handler(req):
        bodies.append(json.loads(req.content))
        return httpx.Response(200, json={"choices": [{"message": {"content": OK}}],
                                         "usage": {"prompt_tokens": 5, "completion_tokens": 2}})

    p = llm.OpenAICompatibleProvider("https://api.example/v1", "k", "m", db_path=tmp_db,
                                     transport=httpx.MockTransport(handler), limits=limits(),
                                     max_output_tokens=600, reasoning_effort="low")
    p.complete_json("prompt", Answer)
    assert bodies[0]["max_tokens"] == 600 and bodies[0]["reasoning_effort"] == "low"
    q = llm.OpenAICompatibleProvider("https://api.example/v1", "k", "m", db_path=tmp_db,
                                     transport=httpx.MockTransport(handler), limits=limits())
    q.complete_json("prompt 2", Answer)
    assert "max_tokens" not in bodies[1] and "reasoning_effort" not in bodies[1]


def test_env_options_per_slot(monkeypatch, tmp_db):
    for k, v in {"LLM_BASE_URL": "https://a.example/v1", "LLM_API_KEY": "k", "LLM_MODEL": "m1",
                 "LLM_REASONING_EFFORT": "low", "LLM_MAX_OUTPUT_TOKENS": "700",
                 "LLM_FALLBACK_1_BASE_URL": "https://b.example/v1",
                 "LLM_FALLBACK_1_API_KEY": "k2", "LLM_FALLBACK_1_MODEL": "m2",
                 "LLM_FALLBACK_AFTER_SECONDS": "30", "LLM_MAX_WAIT_SECONDS": "60"}.items():
        monkeypatch.setenv(k, v)
    chain = llm.provider_from_env(db_path=tmp_db)
    a, b = chain.providers
    assert a.reasoning_effort == "low" and b.reasoning_effort is None
    assert a.max_output_tokens == 700 == b.max_output_tokens
    assert a.limits.max_wait_seconds == 30 and b.limits.max_wait_seconds == 60


def test_seed_and_cache_namespace(tmp_db):
    bodies = []

    def handler(req):
        bodies.append(json.loads(req.content))
        return httpx.Response(200, json={"choices": [{"message": {"content": OK}}],
                                         "usage": {"prompt_tokens": 5, "completion_tokens": 2}})

    p = llm.OpenAICompatibleProvider("https://api.example/v1", "k", "m", db_path=tmp_db,
                                     transport=httpx.MockTransport(handler), limits=limits(),
                                     seed=7)
    p.complete_json("prompt", Answer)
    p.complete_json("prompt", Answer)                 # cache hit: no new request
    assert len(bodies) == 1 and bodies[0]["seed"] == 7 and bodies[0]["temperature"] == 0
    p.cache_namespace = "consistency-x"
    p.complete_json("prompt", Answer)                 # other namespace: fresh call
    assert len(bodies) == 2
