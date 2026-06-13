"""Shared test fixtures — isolated in-memory-ish SQLite per test session."""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _temp_db(tmp_path, monkeypatch):
    """Point every test at a throwaway SQLite file and reset cached engine."""
    db_file = tmp_path / "test.db"
    monkeypatch.setenv("YOUTUBE_API_KEY", "test-key")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_file}")

    # Reset cached engine/session so the new DATABASE_URL takes effect.
    import db.session as session_mod

    session_mod._engine = None
    session_mod._SessionLocal = None

    from db.init import init_db

    init_db()
    yield
    session_mod._engine = None
    session_mod._SessionLocal = None
