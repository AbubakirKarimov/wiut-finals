import importlib

import pytest
from fastapi.testclient import TestClient

from backend.api.cors import DEFAULT_ORIGINS, parse_origins


def test_defaults_when_unset_or_empty():
    assert parse_origins(None) == DEFAULT_ORIGINS
    assert parse_origins(" , ") == DEFAULT_ORIGINS
    assert "http://127.0.0.1:5174" in DEFAULT_ORIGINS


def test_env_list_replaces_defaults():
    assert parse_origins("https://wiut-finals.vercel.app/, http://localhost:5173") == [
        "https://wiut-finals.vercel.app", "http://localhost:5173"]


@pytest.mark.parametrize("raw", ["*", "https://*.vercel.app", "wiut.vercel.app",
                                 "https://wiut.vercel.app/app"])
def test_invalid_origins_rejected(raw):
    with pytest.raises(ValueError):
        parse_origins(raw)


def preflight(client, origin):
    return client.options("/check", headers={
        "Origin": origin, "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "content-type"})


def app_with_cors(monkeypatch, value: str):
    """Rebuild the real app with CORS_ORIGINS set (the app reads it at import)."""
    from backend.api import main
    monkeypatch.setenv("CORS_ORIGINS", value)
    return importlib.reload(main).app


@pytest.fixture(autouse=True)
def restore_main():
    yield
    from backend.api import main
    importlib.reload(main)  # back to the environment's configuration


def test_preflight_allows_default_origins_only(tmp_db, monkeypatch):
    with TestClient(app_with_cors(monkeypatch, "")) as client:
        for origin in DEFAULT_ORIGINS:
            r = preflight(client, origin)
            assert r.status_code == 200, origin
            assert r.headers["access-control-allow-origin"] == origin
            assert "POST" in r.headers["access-control-allow-methods"]
            assert "access-control-allow-credentials" not in r.headers
        r = preflight(client, "https://evil.example")
        assert r.status_code == 400
        assert "access-control-allow-origin" not in r.headers


def test_preflight_production_origin(tmp_db, monkeypatch):
    prod = "https://wiut-finals.vercel.app"
    with TestClient(app_with_cors(monkeypatch, prod)) as client:
        r = preflight(client, prod)
        assert r.status_code == 200 and r.headers["access-control-allow-origin"] == prod
        assert preflight(client, "http://localhost:5173").status_code == 400
        # Simple (non-preflight) requests from the allowed origin get the header too.
        r = client.get("/health", headers={"Origin": prod})
        assert r.headers["access-control-allow-origin"] == prod


def test_wildcard_env_fails_at_startup(monkeypatch):
    with pytest.raises(ValueError, match="not allowed"):
        app_with_cors(monkeypatch, "*")
