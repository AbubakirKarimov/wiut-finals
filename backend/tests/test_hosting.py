"""Hosting: the API serves the built frontend from the same origin (Docker image / Render)."""

import importlib

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def hosted(tmp_db, tmp_path, monkeypatch):
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text('<!doctype html><div id="root"></div>', encoding="utf-8")
    (dist / "assets" / "app.js").write_text("console.log(1)", encoding="utf-8")
    (dist / "favicon.svg").write_text("<svg/>", encoding="utf-8")
    (tmp_path / "secret.txt").write_text("nope", encoding="utf-8")
    monkeypatch.setenv("FRONTEND_DIST", str(dist))
    from backend.api import main
    main = importlib.reload(main)
    with TestClient(main.app) as c:
        yield c
    monkeypatch.delenv("FRONTEND_DIST")
    importlib.reload(main)


def test_frontend_served_with_spa_fallback(hosted):
    r = hosted.get("/")
    assert r.status_code == 200 and '<div id="root">' in r.text
    assert hosted.get("/assets/app.js").text == "console.log(1)"
    assert hosted.get("/favicon.svg").text == "<svg/>"
    assert '<div id="root">' in hosted.get("/findings-page/anything").text  # SPA fallback


def test_api_routes_win_over_the_frontend(hosted):
    assert hosted.get("/health").json() == {"status": "ok"}
    assert isinstance(hosted.get("/findings").json(), list)
    assert hosted.get("/jobs/missing").status_code == 404


def test_no_files_outside_dist(hosted):
    r = hosted.get("/../secret.txt")
    assert "nope" not in r.text
    r = hosted.get("/%2e%2e/secret.txt")
    assert "nope" not in r.text
