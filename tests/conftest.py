from __future__ import annotations

import pytest

from db.database import init_db, reset_caches


@pytest.fixture()
def fresh_db(tmp_path, monkeypatch):
    """Initialize a fresh SQLite DB at a tmp path for the duration of one test."""
    db_file = tmp_path / "test.db"
    monkeypatch.setenv("DATABASE_PATH", str(db_file))
    reset_caches()
    init_db()
    yield db_file
    reset_caches()
