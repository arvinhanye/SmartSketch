"""Backend test defaults and function-scoped setup.

C13: the served entry ``app.main:app`` refuses to import without AUTH_JWT_SECRET (IAM-23),
and several test modules import ``app.main`` at collection time. Provide a test-only key
unless the environment already sets one; tests that need it missing remove it themselves.
"""

import os

import pytest

from tests.backend.helpers.sqlite import migrated_database, sqlite_url

os.environ.setdefault("AUTH_JWT_SECRET", "backend-tests-only-signing-key-not-a-real-secret")


@pytest.fixture
def db_url(tmp_path):
    """An independently migrated SQLite file for each test invocation."""
    return migrated_database(sqlite_url(tmp_path / "state.sqlite3"))


@pytest.fixture
def url(db_url):
    """Historical fixture name used by the model/retrieval tests."""
    return db_url


@pytest.fixture
def app_factory(monkeypatch):
    """Create a fresh app after applying explicit, test-local environment values.

    Callers retain their TestClient context and app.state overrides. Nothing is
    cached: two calls create two applications even within one test.
    """
    def make_app(**environment: str):
        from app.main import create_app

        for name, value in environment.items():
            monkeypatch.setenv(name, value)
        return create_app()

    return make_app
