import pytest

from backend.checks import llm_checks
from backend.db import init_db


@pytest.fixture
def tmp_db(tmp_path, monkeypatch):
    path = tmp_path / "test.sqlite"
    monkeypatch.setenv("DB_PATH", str(path))
    # Never load the team's real data files into a test database.
    monkeypatch.setenv("REQUIREMENTS_PATH", str(tmp_path / "no-requirements.yaml"))
    monkeypatch.setenv("PRECOMPUTED_PATH", str(tmp_path / "no-precomputed.json"))
    monkeypatch.setenv("PRECOMPUTED_DECISIONS_PATH", str(tmp_path / "no-decisions.json"))
    monkeypatch.setenv("LIVE_DECISIONS_EPHEMERAL", "0")
    monkeypatch.setattr(llm_checks, "HINTS_PATH", tmp_path / "no-check-hints.yaml")
    init_db(path)
    return path
