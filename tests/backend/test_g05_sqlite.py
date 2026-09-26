"""G05 SQLite pieces without Neo4j: the sweeper's expired-attempt and course listings.

The full sweep runs against a real Neo4j in ``tests/integration/test_g05.py``.
"""

from __future__ import annotations

import uuid

import pytest

from app.repositories import versions
from app.repositories.accounts import insert_account
from app.repositories.courses import create_course
from app.repositories.sqlite import connect, migrate

VALID_HASH = "$argon2id$v=19$m=65536,t=3,p=4$c2FsdA$aGFzaA"


@pytest.fixture
def env(tmp_path):
    url = f"sqlite:///{(tmp_path / 's.sqlite3').as_posix()}"
    migrate(url)
    teacher = insert_account(url, account_id=uuid.uuid4().hex, username="teacher1", password_hash=VALID_HASH,
                             role="teacher")
    a = create_course(url, name="A", description=None, creator_id=teacher.id).id
    b = create_course(url, name="B", description=None, creator_id=teacher.id).id
    return url, a, b


def expire(url, version_id):
    with connect(url) as db:
        db.execute("UPDATE graph_versions SET expires_at = unixepoch() - 1 WHERE version_id = ?", (version_id,))


def test_expired_attempts_are_listed_per_course_and_only_while_active(env):
    url, a, b = env
    live = versions.begin_attempt(url, a, kind="publish", created_by=None, lease_seconds=60)
    assert versions.list_expired_attempts(url, a) == []
    expire(url, live.version_id)
    other = versions.begin_attempt(url, b, kind="publish", created_by=None, lease_seconds=60)
    expire(url, other.version_id)
    assert [r.version_id for r in versions.list_expired_attempts(url, a)] == [live.version_id]
    assert versions.fail_attempt(url, live.version_id, "LEASE_EXPIRED")
    assert versions.list_expired_attempts(url, a) == []
    assert not versions.heartbeat(url, other.version_id, lease_seconds=60)  # 过期后不能复活
    assert [r.version_id for r in versions.list_expired_attempts(url, b)] == [other.version_id]


def test_course_ids_cover_every_course(env):
    url, a, b = env
    assert versions.list_course_ids(url) == sorted([a, b])
