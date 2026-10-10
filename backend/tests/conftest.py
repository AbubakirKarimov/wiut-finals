import pytest

from backend.db import init_db


@pytest.fixture
def tmp_db(tmp_path, monkeypatch):
    path = tmp_path / "test.sqlite"
    monkeypatch.setenv("DB_PATH", str(path))
    # Never load the team's real data files into a test database.
    monkeypatch.setenv("REQUIREMENTS_PATH", str(tmp_path / "no-requirements.yaml"))
    monkeypatch.setenv("PRECOMPUTED_PATH", str(tmp_path / "no-precomputed.json"))
    init_db(path)
    return path
