import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from backend.api.ratelimit import RateLimiter, limiter_from_env, rate_limit_dependency


class FakeClock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


def test_limiter_blocks_then_recovers():
    clock = FakeClock()
    limiter = RateLimiter(max_requests=2, window_seconds=60, clock=clock)
    assert limiter.allow("1.1.1.1")
    assert limiter.allow("1.1.1.1")
    assert not limiter.allow("1.1.1.1")
    assert limiter.allow("2.2.2.2")  # limits are per IP
    clock.now = 60.0
    assert limiter.allow("1.1.1.1")


def test_limiter_reads_config(monkeypatch):
    monkeypatch.setenv("CHECK_RATE_LIMIT_PER_MINUTE", "7")
    assert limiter_from_env().max_requests == 7
    monkeypatch.delenv("CHECK_RATE_LIMIT_PER_MINUTE")
    with pytest.raises(RuntimeError):
        limiter_from_env()


def test_dependency_returns_429():
    app = FastAPI()
    limit = rate_limit_dependency(RateLimiter(max_requests=1))

    @app.post("/check", dependencies=[Depends(limit)])
    def check():
        return {"ok": True}

    client = TestClient(app)
    assert client.post("/check").status_code == 200
    resp = client.post("/check")
    assert resp.status_code == 429
    assert "Rate limit exceeded" in resp.json()["detail"]
