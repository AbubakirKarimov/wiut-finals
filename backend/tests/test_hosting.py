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


REAL_PRECOMPUTED = __import__("pathlib").Path(__file__).resolve().parents[2] / "data" / "precomputed"


@pytest.fixture
def hosted_demo(tmp_path, monkeypatch):
    """The hosted configuration: /tmp-like DB, committed pre-computed data, no LLM key."""
    from backend.api import main
    monkeypatch.setenv("DB_PATH", str(tmp_path / "demo.sqlite"))
    monkeypatch.setenv("REQUIREMENTS_PATH", str(REAL_PRECOMPUTED.parents[0] / "requirements.yaml"))
    monkeypatch.setenv("PRECOMPUTED_PATH", str(REAL_PRECOMPUTED / "findings.json"))
    decisions = tmp_path / "decisions.json"
    monkeypatch.setenv("PRECOMPUTED_DECISIONS_PATH", str(decisions))
    monkeypatch.setenv("RESET_DB_ON_START", "1")
    monkeypatch.setenv("LIVE_DECISIONS_EPHEMERAL", "1")
    for k in ("LLM_BASE_URL", "LLM_API_KEY", "LLM_MODEL"):
        monkeypatch.setenv(k, "")
    return main, decisions


def test_starts_without_llm_key_and_shows_precomputed_findings(hosted_demo):
    import json
    main, decisions = hosted_demo
    expected = sum(len(r["findings"]) for r in
                   json.loads((REAL_PRECOMPUTED / "findings.json").read_text())["runs"])
    with TestClient(main.app) as c:
        fs = c.get("/findings").json()
        assert len(fs) == expected > 0
        assert {f["run"]["source"] for f in fs} == {"precomputed"}
        assert c.get("/metrics").status_code == 200


def test_every_start_rebuilds_state_from_the_files(hosted_demo):
    import json
    main, decisions = hosted_demo
    with TestClient(main.app) as c:
        gap = next(f for f in c.get("/findings").json() if f["status"] == "possible_gap")
    decisions.write_text(json.dumps({"decisions": [{
        "finding_id": gap["id"], "analyst": "Team", "verdict": "confirmed",
        "decided_at": "2026-10-11T08:00:00+00:00"}]}), encoding="utf-8")
    with TestClient(main.app) as c:            # restart 1: team decision loaded
        c.post("/decisions", json={"finding_id": gap["id"], "analyst": "Live",
                                   "verdict": "rejected"})
        log = c.get("/decisions").json()
        assert {(d["analyst"], d["source"]) for d in log} == {("Team", "team"), ("Live", "live")}
        live = next(d for d in log if d["source"] == "live")
        assert live["storage_note"] == "live session, may reset on restart"
    with TestClient(main.app) as c:            # restart 2: live decision gone, team kept
        assert [(d["analyst"], d["source"]) for d in c.get("/decisions").json()] == \
            [("Team", "team")]
