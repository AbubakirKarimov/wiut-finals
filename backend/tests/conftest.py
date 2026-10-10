import pytest

from backend.db import init_db


@pytest.fixture
def tmp_db(tmp_path, monkeypatch):
    path = tmp_path / "test.sqlite"
    monkeypatch.setenv("DB_PATH", str(path))
    init_db(path)
    return path
