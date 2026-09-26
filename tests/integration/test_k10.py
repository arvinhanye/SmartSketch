"""K10 backup and restore drill: scripts/backup-demo.sh and scripts/restore-demo.sh.

Acceptance (docs/atomic-tasks.json K10; ADR-054):

- one point in time and the publish pointer: the SQLite snapshot and the Neo4j export are taken
  under a write fence (every course write lock held, no live task lease, no unfinished publish or
  rollback attempt) and the backup fails when anything changed either store in between; the
  recorded pointer must name a committed version whose copies verify against its snapshot;
- restore goes to an isolated copy (new SQLite file, empty Neo4j) and verifies references, graph
  and progress (every SQLite table, including progress tables added later) against the manifest;
- the user's databases are never overwritten unless ``--replace-existing`` and ``--confirm
  <backup id>`` are both given, and then only after safety copies of both stores.

Three groups of cases:

- offline refusals: need no Neo4j (the scripts refuse before connecting);
- Bolt path: a disposable Neo4j (``SMARTSKETCH_TEST_NEO4J_URI/USER/PASSWORD``; **the database is
  wiped**);
- neo4j-admin path: two throw-away ``neo4j:5.26-community`` containers (skipped without a Docker
  daemon or the image). Ports ``SMARTSKETCH_K10_DOCKER_PORTS`` (default ``7697,7698``).
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import socket
import sqlite3
import subprocess
import sys
import time
import uuid
from contextlib import closing
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.config import Settings
from app.repositories.accounts import insert_account
from app.repositories.courses import create_course
from app.repositories.graph_migrations import apply_migrations
from app.repositories.graph_read import GraphReader
from app.repositories.neo4j import GraphScope, Neo4jRepository
from app.repositories.sqlite import connect, migrate
from app.services.ai.embeddings import EmbeddingAdapter
from app.services.ai.fake import FakeEmbeddingClient
from app.services.versions.publish import PublishContext, publish

ROOT = Path(__file__).resolve().parents[2]
BACKUP = ROOT / "scripts" / "backup-demo.sh"
RESTORE = ROOT / "scripts" / "restore-demo.sh"

_ENV = ("SMARTSKETCH_TEST_NEO4J_URI", "SMARTSKETCH_TEST_NEO4J_USER", "SMARTSKETCH_TEST_NEO4J_PASSWORD")
live = pytest.mark.skipif(not all(os.environ.get(n) for n in _ENV), reason="isolated Neo4j fixture not configured")

SPACE = "fake/4"
VALID_HASH = "$argon2id$v=19$m=65536,t=3,p=4$c2FsdA$aGFzaA"
REV = "rev_" + "a" * 64
C0, C1 = f"{REV}-0", f"{REV}-1"
UNUSED_BOLT = "bolt://127.0.0.1:1"  # never contacted by the offline cases


def sha(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode()).hexdigest()


def sqlite_url(path: Path) -> str:
    return f"sqlite:///{path.as_posix()}"


def sql(url: str, query: str, *params):
    with connect(url) as db:
        return db.execute(query, params).fetchall()


def dump(path: Path) -> list[str]:
    """Every row of every table, independent of page layout and WAL state."""
    with closing(sqlite3.connect(path)) as db:
        return list(db.iterdump())


def run_script(script: Path, *args: str, sqlite: str | None = None, neo4j_uri: str | None = None,
               extra: dict | None = None, timeout: int = 600) -> subprocess.CompletedProcess:
    env = {**os.environ, "PYTHON": sys.executable}
    env.pop("PYTHONPATH", None)  # the script must set up its own import path
    env.update({"NEO4J_USER": os.environ.get(_ENV[1], "neo4j"), "NEO4J_PASSWORD": os.environ.get(_ENV[2], "x")})
    if sqlite is not None:
        env["SQLITE_URL"] = sqlite
    if neo4j_uri is not None:
        env["NEO4J_URI"] = neo4j_uri
    env.update(extra or {})
    return subprocess.run(["bash", str(script), *args], env=env, capture_output=True, text=True, timeout=timeout,
                          cwd=ROOT)


def backup_dir(result: subprocess.CompletedProcess) -> Path:
    assert result.returncode == 0, result.stderr
    return Path(result.stdout.strip().splitlines()[-1])


def manifest(directory: Path) -> dict:
    return json.loads((directory / "manifest.json").read_text(encoding="utf-8"))


# ---------------------------------------------------------------- seeding


def q(driver, query: str, **params):
    return [dict(r) for r in driver.execute_query(query, parameters_=params, routing_="w", database_="neo4j").records]


def wipe(driver) -> None:
    while q(driver, "MATCH (n) WITH n LIMIT 1000 DETACH DELETE n RETURN count(*) AS c")[0]["c"]:
        pass
    for kind in ("CONSTRAINTS", "INDEXES"):
        for row in q(driver, f"SHOW {kind} YIELD name, type RETURN name, type"):
            if row["type"] != "LOOKUP":
                q(driver, f"DROP {kind[:-1] if kind == 'CONSTRAINTS' else 'INDEX'} `{row['name']}` IF EXISTS")


def embedder():
    return EmbeddingAdapter(Settings(EMBEDDING_MODE="fake", EMBEDDING_MODEL="", EMBEDDING_DIMENSIONS=4,
                                     EMBEDDING_BATCH_SIZE=8), FakeEmbeddingClient())


def seed(tmp_path: Path, driver) -> SimpleNamespace:
    """Two courses: one published twice (pointer on v2, v1 kept), one draft-only; plus progress rows."""
    apply_migrations(driver)
    path = tmp_path / "user" / "smartsketch.sqlite3"
    url = sqlite_url(path)
    migrate(url)
    teacher = insert_account(url, account_id=uuid.uuid4().hex, username="teacher1", password_hash=VALID_HASH,
                             role="teacher")
    course = create_course(url, name="数据结构", description=None, creator_id=teacher.id).id
    other = create_course(url, name="操作系统", description=None, creator_id=teacher.id).id

    sql(url, "INSERT INTO materials (id, course_id, filename, format, size_bytes, content_hash, storage_name) "
        "VALUES ('m1', ?, 'a.txt', 'txt', 10, ?, ?)", course, sha("m1"), uuid.uuid4().hex)
    sql(url, "INSERT INTO material_revisions (revision_id, course_id, material_id, content_hash, parser_version) "
        "VALUES (?, ?, 'm1', ?, 'txt/1+chunk/1')", REV, course, sha("m1"))
    for ordinal in (0, 1):
        sql(url, "INSERT INTO chunks (chunk_id, revision_id, course_id, material_id, ordinal, text, text_sha256, "
            "section_titles, sources) VALUES (?, ?, ?, 'm1', ?, ?, ?, '[]', ?)",
            f"{REV}-{ordinal}", REV, course, ordinal, f"块{ordinal}", sha(f"块{ordinal}"),
            json.dumps([{"block_ordinal": 0, "start": 0, "end": 2, "locator": {"section_titles": [], "paragraph": 1}}]))

    def task(task_id, t6_seq):
        sql(url, "INSERT INTO processing_tasks (id, course_id, document_id, stage, progress, idempotency_key, t6_seq) "
            "VALUES (?, ?, 'm1', 'awaiting_review', 0.95, ?, ?)", task_id, course, task_id, t6_seq)
        sql(url, "INSERT INTO task_revisions (task_id, revision_id, course_id, material_id) VALUES (?, ?, ?, 'm1')",
            task_id, REV, course)
        sql(url, "UPDATE courses SET draft_revision = draft_revision + 1 WHERE id = ?", course)

    def node(kp_id, chunk=C0, course_id=course):
        q(driver, "CREATE (:KnowledgePoint {course_id: $c, version_id: 'draft', kp_id: $k, name: $k, type: 'concept', "
          "definition: '定义', status: 'approved', source: 'ai', confidence: 0.9, locked: false, revision: 1, "
          "contrib_manual: false, contrib_tasks: ['t1']})", c=course_id, k=kp_id)
        q(driver, "MATCH (n:KnowledgePoint {course_id: $c, version_id: 'draft', kp_id: $k}) "
          "MERGE (ch:Chunk {course_id: $c, chunk_id: $chunk}) ON CREATE SET ch.document_id = 'm1' "
          "CREATE (n)-[e:EVIDENCED_BY {chunk_id: $chunk, evidence_start: 0, evidence_end: 2}]->(ch) "
          "SET e.task_id = 't1'", c=course_id, k=kp_id, chunk=chunk)

    def rel(kind, a, b):
        q(driver, f"MATCH (a:KnowledgePoint {{course_id: $c, version_id: 'draft', kp_id: $a}}), "
          f"(b:KnowledgePoint {{course_id: $c, version_id: 'draft', kp_id: $b}}) CREATE (a)-[r:{kind}]->(b) SET r += $p",
          c=course, a=a, b=b,
          p={"course_id": course, "version_id": "draft", "rel_id": f"rel_{kind}_{a}_{b}", "status": "approved",
             "source": "ai", "confidence": 0.8, "contrib_tasks": ["t1"], "contrib_manual": False,
             "source_pairs": [json.dumps(["t1", C1])], "revision": 1})

    task("t1", 1)
    for kp in ("a", "b", "c"):
        node(kp)
    rel("PREREQUISITE", "a", "b")
    rel("RELATED_TO", "b", "c")
    repo = Neo4jRepository(driver)
    ctx = PublishContext(url, repo, embedder(), lambda: SPACE, lease_seconds=15, lock_wait_seconds=0)
    v1 = publish(ctx, course, created_by=teacher.id)
    q(driver, "MATCH (n:KnowledgePoint {course_id: $c, version_id: 'draft', kp_id: 'a'}) SET n.definition = '新定义'",
      c=course)
    sql(url, "UPDATE courses SET draft_revision = draft_revision + 1 WHERE id = ?", course)
    task("t2", 2)
    v2 = publish(ctx, course, created_by=teacher.id)
    q(driver, "CREATE (:KnowledgePoint {course_id: $c, version_id: 'draft', kp_id: 'x', name: 'x', "
      "definition: 'd', status: 'pending'})", c=other)

    # I01's progress tables are not merged yet: the backup copies every table, so a probe table
    # stands in for them (same shape: per-user, per-course, per-knowledge-point rows).
    sql(url, "CREATE TABLE k10_probe_progress (course_id TEXT NOT NULL REFERENCES courses(id), user_id TEXT NOT NULL, "
        "kp_id TEXT NOT NULL, mastered INTEGER NOT NULL, PRIMARY KEY (course_id, user_id, kp_id))")
    for kp, mastered in (("a", 1), ("b", 0)):
        sql(url, "INSERT INTO k10_probe_progress VALUES (?, 'student-1', ?, ?)", course, kp, mastered)
    return SimpleNamespace(path=path, url=url, course=course, other=other, teacher=teacher, v1=v1, v2=v2,
                           repo=repo, ctx=ctx)


def pointer(url: str, course: str):
    return sql(url, "SELECT published_version_id, published_version FROM courses WHERE id = ?", course)[0]


def student_names(driver, course: str, version_id: str) -> set[str]:
    return {p["name"] for p in GraphReader(Neo4jRepository(driver)).nodes(GraphScope(course, version_id), "student")}


def node_count(driver) -> int:
    return q(driver, "MATCH (n) RETURN count(n) AS c")[0]["c"]


# ---------------------------------------------------------------- offline refusals (no Neo4j needed)


def _minimal(tmp_path: Path) -> SimpleNamespace:
    path = tmp_path / "user" / "smartsketch.sqlite3"
    url = sqlite_url(path)
    migrate(url)
    teacher = insert_account(url, account_id=uuid.uuid4().hex, username="teacher1", password_hash=VALID_HASH,
                             role="teacher")
    course = create_course(url, name="数据结构", description=None, creator_id=teacher.id).id
    return SimpleNamespace(path=path, url=url, course=course)


@pytest.mark.parametrize("writer", ["task_lease", "course_lock", "unfinished_attempt", "expired_attempt"])
def test_backup_refuses_while_anything_can_still_write(tmp_path, writer):
    env = _minimal(tmp_path)
    if writer == "task_lease":
        sql(env.url, "INSERT INTO materials (id, course_id, filename, format, size_bytes, content_hash, storage_name) "
            "VALUES ('m1', ?, 'a.txt', 'txt', 10, ?, 'blob')", env.course, sha("m1"))
        sql(env.url, "INSERT INTO processing_tasks (id, course_id, document_id, stage, progress, idempotency_key, "
            "lease_owner, lease_token, lease_expires_at) VALUES ('t1', ?, 'm1', 'parsing', 0.1, 't1', 'w', ?, "
            "unixepoch() + 600)", env.course, "f" * 32)
    elif writer == "course_lock":
        sql(env.url, "INSERT INTO course_locks VALUES (?, 'teacher-edit', ?, unixepoch() + 600)", env.course, "e" * 32)
    else:
        expires = "unixepoch() + 600" if writer == "unfinished_attempt" else "unixepoch() - 1"
        sql(env.url, f"INSERT INTO graph_versions (version_id, course_id, kind, expires_at) "
            f"VALUES (?, ?, 'publish', {expires})", "0" * 26, env.course)
    before = dump(env.path)
    out = tmp_path / "backups"
    result = run_script(BACKUP, "--out", str(out), sqlite=env.url, neo4j_uri=UNUSED_BOLT)
    assert result.returncode == 2, result.stderr
    assert not out.exists() or not any(out.iterdir())  # nothing written, not even a partial directory
    assert dump(env.path) == before  # the foreign lock survives, no k10 lock row is left behind


def test_backup_refuses_an_unmigrated_database(tmp_path):
    path = tmp_path / "empty.sqlite3"
    sqlite3.connect(path).close()
    result = run_script(BACKUP, "--out", str(tmp_path / "b"), sqlite=sqlite_url(path), neo4j_uri=UNUSED_BOLT)
    assert result.returncode == 2
    assert "migrat" in result.stderr


def test_restore_refuses_a_directory_without_a_complete_manifest(tmp_path):
    partial = tmp_path / ".k10-x.partial"
    partial.mkdir()
    (partial / "sqlite.db").write_bytes(b"x")
    result = run_script(RESTORE, "--from", str(partial), "--sqlite-target", str(tmp_path / "r.sqlite3"),
                        "--neo4j-uri", UNUSED_BOLT)
    assert result.returncode == 2
    assert not (tmp_path / "r.sqlite3").exists()


def test_restore_requires_an_explicit_neo4j_target(tmp_path):
    partial = tmp_path / "b"
    partial.mkdir()
    result = run_script(RESTORE, "--from", str(partial), "--sqlite-target", str(tmp_path / "r.sqlite3"),
                        neo4j_uri="bolt://127.0.0.1:7687")
    assert result.returncode == 2  # NEO4J_URI (the user's database) is never used as a default target


# ---------------------------------------------------------------- Bolt path (disposable Neo4j)


@pytest.fixture
def neo():
    neo4j = pytest.importorskip("neo4j")
    driver = neo4j.GraphDatabase.driver(os.environ[_ENV[0]], auth=(os.environ[_ENV[1]], os.environ[_ENV[2]]))
    wipe(driver)
    try:
        yield SimpleNamespace(driver=driver, uri=os.environ[_ENV[0]])
    finally:
        wipe(driver)
        driver.close()


def take_backup(tmp_path, env, neo, *args, extra=None):
    return run_script(BACKUP, "--out", str(tmp_path / "backups"), *args, sqlite=env.url, neo4j_uri=neo.uri,
                      extra=extra)


@live
def test_backup_records_one_point_in_time_and_the_publish_pointer(tmp_path, neo):
    env = seed(tmp_path, neo.driver)
    before = dump(env.path)
    directory = backup_dir(take_backup(tmp_path, env, neo))
    data = manifest(directory)
    assert data["format"] == "smartsketch-k10/1" and data["neo4j_mode"] == "bolt"
    assert directory.name == data["backup_id"]
    inspection = data["inspection"]
    pointers = {p["course_id"]: p for p in inspection["sqlite"]["pointers"]}
    assert (pointers[env.course]["published_version_id"], pointers[env.course]["published_version"]) == (
        env.v2.version_id, 2)
    assert pointers[env.other]["published_version_id"] is None
    consistency = inspection["consistency"]
    assert consistency["pointer_errors"] == [] and consistency["version_errors"] == {}
    assert sorted(consistency["verified_versions"]) == sorted([env.v1.version_id, env.v2.version_id])
    assert inspection["sqlite"]["tables"]["k10_probe_progress"]["rows"] == 2
    # the fence left nothing behind: live database unchanged, snapshot holds no k10 lock row
    assert dump(env.path) == before
    with closing(sqlite3.connect(directory / "sqlite.db")) as copy:
        assert copy.execute("SELECT count(*) FROM course_locks").fetchone() == (0,)
        assert copy.execute("PRAGMA integrity_check").fetchone() == ("ok",)
    for name, digest in data["files"].items():
        assert hashlib.sha256((directory / name).read_bytes()).hexdigest() == digest
        assert (directory / name).stat().st_mode & 0o077 == 0
    assert directory.stat().st_mode & 0o077 == 0
    assert not list((tmp_path / "backups").glob(".*.partial"))


@live
def test_restore_into_an_isolated_copy_verifies_references_graph_and_progress(tmp_path, neo):
    env = seed(tmp_path, neo.driver)
    directory = backup_dir(take_backup(tmp_path, env, neo))
    user_rows = dump(env.path)
    wipe(neo.driver)  # stands in for a fresh, isolated Neo4j instance
    target = tmp_path / "drill" / "restored.sqlite3"
    report = tmp_path / "drill" / "report.json"
    result = run_script(RESTORE, "--from", str(directory), "--sqlite-target", str(target), "--neo4j-uri", neo.uri,
                        "--report", str(report))
    assert result.returncode == 0, result.stderr
    outcome = json.loads(report.read_text(encoding="utf-8"))
    assert outcome["status"] == "verified" and outcome["differences"] == []
    restored = sqlite_url(target)
    assert pointer(restored, env.course) == (env.v2.version_id, 2)
    assert student_names(neo.driver, env.course, env.v2.version_id) == {"a", "b", "c"}
    assert sql(restored, "SELECT kp_id, mastered FROM k10_probe_progress ORDER BY kp_id") == [("a", 1), ("b", 0)]
    assert dump(target) == user_rows  # the copy is the backup, row for row
    assert dump(env.path) == user_rows  # the user's database was not touched


@live
def test_restore_refuses_non_empty_targets_without_touching_them(tmp_path, neo):
    env = seed(tmp_path, neo.driver)
    directory = backup_dir(take_backup(tmp_path, env, neo))
    user_rows = dump(env.path)
    nodes = node_count(neo.driver)

    fresh = tmp_path / "drill" / "restored.sqlite3"
    result = run_script(RESTORE, "--from", str(directory), "--sqlite-target", str(fresh), "--neo4j-uri", neo.uri)
    assert result.returncode == 2 and "not empty" in result.stderr
    assert not fresh.exists()

    wipe(neo.driver)
    q(neo.driver, "CREATE (:Marker {keep: true})")
    result = run_script(RESTORE, "--from", str(directory), "--sqlite-target", str(env.path), "--neo4j-uri", neo.uri)
    assert result.returncode == 2 and "exists" in result.stderr
    assert dump(env.path) == user_rows
    assert node_count(neo.driver) == 1 and nodes > 1


@live
def test_replacing_needs_the_backup_id_and_keeps_safety_copies(tmp_path, neo):
    env = seed(tmp_path, neo.driver)
    directory = backup_dir(take_backup(tmp_path, env, neo))
    backup_id = manifest(directory)["backup_id"]
    # work done after the backup, which the restore will roll back
    sql(env.url, "INSERT INTO k10_probe_progress VALUES (?, 'student-1', 'c', 1)", env.course)
    q(neo.driver, "CREATE (:KnowledgePoint {course_id: $c, version_id: 'draft', kp_id: 'late', name: 'late'})",
      c=env.course)
    after_rows = dump(env.path)
    safety = tmp_path / "safety"
    base = ["--from", str(directory), "--sqlite-target", str(env.path), "--neo4j-uri", neo.uri,
            "--safety-dir", str(safety)]

    for extra in (["--replace-existing"], ["--replace-existing", "--confirm", "k10-wrong"], ["--confirm", backup_id]):
        result = run_script(RESTORE, *base, *extra)
        assert result.returncode == 2, extra
        assert dump(env.path) == after_rows
        assert q(neo.driver, "MATCH (n {kp_id: 'late'}) RETURN count(n) AS c")[0]["c"] == 1

    sql(env.url, "INSERT INTO course_locks VALUES (?, 'teacher-edit', ?, unixepoch() + 600)", env.course, "e" * 32)
    result = run_script(RESTORE, *base, "--replace-existing", "--confirm", backup_id)
    assert result.returncode == 2 and "lock" in result.stderr  # the target is still in use
    sql(env.url, "DELETE FROM course_locks")
    after_rows = dump(env.path)

    result = run_script(RESTORE, *base, "--replace-existing", "--confirm", backup_id)
    assert result.returncode == 0, result.stderr
    assert sql(env.url, "SELECT count(*) FROM k10_probe_progress") == [(2,)]
    assert q(neo.driver, "MATCH (n {kp_id: 'late'}) RETURN count(n) AS c")[0]["c"] == 0
    assert student_names(neo.driver, env.course, env.v2.version_id) == {"a", "b", "c"}
    [saved] = list(safety.iterdir())
    assert dump(saved / "sqlite.db") == after_rows  # the replaced database is kept
    with closing(__import__("gzip").open(saved / "graph.jsonl.gz", "rt", encoding="utf-8")) as graph:
        assert any('"late"' in line for line in graph)


@live
def test_a_publish_during_the_backup_is_rejected_by_the_fence(tmp_path, neo):
    env = seed(tmp_path, neo.driver)
    sql(env.url, "UPDATE courses SET draft_revision = draft_revision + 0 WHERE id = ?", env.course)
    outcome = tmp_path / "publish-outcome.txt"
    probe = tmp_path / "publish_probe.py"
    probe.write_text(
        "import sys\n"
        "from neo4j import GraphDatabase\n"
        "from app.repositories.neo4j import Neo4jRepository\n"
        "from app.services.versions.publish import CourseBusy, PublishContext, publish\n"
        "sys.path.insert(0, sys.argv[5])\n"
        "from test_k10 import embedder\n"
        "driver = GraphDatabase.driver(sys.argv[2], auth=('neo4j', 'x'))\n"
        "ctx = PublishContext(sys.argv[1], Neo4jRepository(driver), embedder(), lambda: 'fake/4', "
        "lease_seconds=15, lock_wait_seconds=0)\n"
        "try:\n"
        "    publish(ctx, sys.argv[3], created_by=None)\n"
        "    result = 'published'\n"
        "except CourseBusy:\n"
        "    result = 'busy'\n"
        "open(sys.argv[4], 'w').write(result)\n",
        encoding="utf-8")
    hook = (f"PYTHONPATH={ROOT / 'src' / 'backend'} {sys.executable} {probe} {env.url} {neo.uri} {env.course} "
            f"{outcome} {Path(__file__).parent}")
    result = take_backup(tmp_path, env, neo, extra={"K10_AFTER_SNAPSHOT_HOOK": hook})
    assert outcome.read_text() == "busy"  # P3 could not take the course write lock: 409 COURSE_BUSY
    # the rejected attempt still left a failed graph_versions row, so this backup is discarded
    assert result.returncode == 1 and "SQLite changed during the backup (tables: graph_versions)" in result.stderr
    assert not any((tmp_path / "backups").iterdir())
    assert pointer(env.url, env.course) == (env.v2.version_id, 2)
    assert sql(env.url, "SELECT state FROM graph_versions WHERE state <> 'committed'") == [("failed",)]
    # nothing was materialized for the rejected attempt; a re-run (nothing writing) succeeds
    directory = backup_dir(take_backup(tmp_path, env, neo))
    consistency = manifest(directory)["inspection"]["consistency"]
    assert consistency["pointer_errors"] == [] and consistency["orphan_versions"] == []


@live
@pytest.mark.parametrize("writer", ["neo4j", "sqlite_progress", "sqlite_course"])
def test_an_unfenced_write_during_the_backup_fails_it(tmp_path, neo, writer):
    env = seed(tmp_path, neo.driver)
    if writer == "neo4j":
        hook = (f"{sys.executable} -c \"from neo4j import GraphDatabase; GraphDatabase.driver('{neo.uri}', "
                f"auth=('neo4j', 'x')).execute_query(\\\"CREATE (:KnowledgePoint {{course_id: '{env.course}', "
                f"version_id: 'draft', kp_id: 'sneaky'}})\\\")\"")
    elif writer == "sqlite_progress":
        hook = (f"{sys.executable} -c \"import sqlite3; c = sqlite3.connect('{env.path}'); "
                f"c.execute(\\\"INSERT INTO k10_probe_progress VALUES ('{env.course}', 's2', 'a', 1)\\\"); c.commit()\"")
    else:
        hook = (f"{sys.executable} -c \"import sqlite3; c = sqlite3.connect('{env.path}'); "
                f"c.execute(\\\"INSERT INTO courses (id, name, teacher_id) SELECT '{'9' * 32}', 'new', teacher_id "
                f"FROM courses LIMIT 1\\\"); c.commit()\"")
    out = tmp_path / "backups"
    result = run_script(BACKUP, "--out", str(out), sqlite=env.url, neo4j_uri=neo.uri,
                        extra={"K10_AFTER_SNAPSHOT_HOOK": hook})
    assert result.returncode == 1, result.stderr
    assert "changed during the backup" in result.stderr
    assert not any(out.iterdir())  # the partial directory is removed
    assert sql(env.url, "SELECT count(*) FROM course_locks") == [(0,)]


@live
def test_a_pointer_without_its_copies_fails_the_backup(tmp_path, neo):
    env = seed(tmp_path, neo.driver)
    q(neo.driver, "MATCH (n {course_id: $c, version_id: $v}) DETACH DELETE n", c=env.course, v=env.v2.version_id)
    out = tmp_path / "backups"
    result = run_script(BACKUP, "--out", str(out), sqlite=env.url, neo4j_uri=neo.uri)
    assert result.returncode == 1
    assert "pointer" in result.stderr
    assert not any(out.iterdir())


@live
def test_leftovers_are_recorded_and_restored_as_they_were(tmp_path, neo):
    env = seed(tmp_path, neo.driver)
    orphan = "Z" * 26
    q(neo.driver, "CREATE (:KnowledgePoint {course_id: $c, version_id: $v, kp_id: 'a', name: 'a'})",
      c=env.course, v=orphan)
    q(neo.driver, "MATCH (n {course_id: $c, version_id: $v}) DETACH DELETE n", c=env.course, v=env.v1.version_id)
    q(neo.driver, "CREATE (:Chunk {course_id: $c, chunk_id: 'rev_gone-0'})", c=env.course)
    directory = backup_dir(take_backup(tmp_path, env, neo))
    consistency = manifest(directory)["inspection"]["consistency"]
    assert consistency["orphan_versions"] == [f"{env.course}/{orphan}"]
    assert list(consistency["version_errors"]) == [env.v1.version_id]
    assert consistency["dangling_chunks"] == [f"{env.course}/rev_gone-0"]
    assert manifest(directory)["warnings"]
    wipe(neo.driver)
    result = run_script(RESTORE, "--from", str(directory), "--sqlite-target", str(tmp_path / "r.sqlite3"),
                        "--neo4j-uri", neo.uri)
    assert result.returncode == 0, result.stderr


@live
def test_a_damaged_backup_is_refused_or_fails_verification(tmp_path, neo):
    env = seed(tmp_path, neo.driver)
    directory = backup_dir(take_backup(tmp_path, env, neo))
    wipe(neo.driver)
    graph = directory / "graph.jsonl.gz"
    import gzip

    lines = gzip.decompress(graph.read_bytes()).decode("utf-8").splitlines()
    tampered = [line.replace('"新定义"', '"篡改"') for line in lines]
    assert tampered != lines
    graph.write_bytes(gzip.compress(("\n".join(tampered) + "\n").encode("utf-8")))
    target = tmp_path / "r.sqlite3"
    result = run_script(RESTORE, "--from", str(directory), "--sqlite-target", str(target), "--neo4j-uri", neo.uri)
    assert result.returncode == 2 and "checksum" in result.stderr
    assert not target.exists() and node_count(neo.driver) == 0

    # the checksum is patched too (a consistent forgery): the content verification still fails
    data = manifest(directory)
    data["files"]["graph.jsonl.gz"] = hashlib.sha256(graph.read_bytes()).hexdigest()
    (directory / "manifest.json").write_text(json.dumps(data), encoding="utf-8")
    report = tmp_path / "report.json"
    result = run_script(RESTORE, "--from", str(directory), "--sqlite-target", str(target), "--neo4j-uri", neo.uri,
                        "--report", str(report))
    assert result.returncode == 1
    differences = json.loads(report.read_text(encoding="utf-8"))["differences"]
    assert any("neo4j" in d for d in differences) and any("version" in d for d in differences)


@live
def test_a_forged_sqlite_copy_fails_the_progress_comparison(tmp_path, neo):
    env = seed(tmp_path, neo.driver)
    directory = backup_dir(take_backup(tmp_path, env, neo))
    wipe(neo.driver)
    copy = directory / "sqlite.db"
    with closing(sqlite3.connect(copy)) as db:
        db.execute("UPDATE k10_probe_progress SET mastered = 1 - mastered WHERE kp_id = 'b'")
        db.commit()
    data = manifest(directory)
    data["files"]["sqlite.db"] = hashlib.sha256(copy.read_bytes()).hexdigest()
    (directory / "manifest.json").write_text(json.dumps(data), encoding="utf-8")
    report = tmp_path / "report.json"
    result = run_script(RESTORE, "--from", str(directory), "--sqlite-target", str(tmp_path / "r.sqlite3"),
                        "--neo4j-uri", neo.uri, "--report", str(report))
    assert result.returncode == 1
    assert json.loads(report.read_text(encoding="utf-8"))["differences"] == ["sqlite table k10_probe_progress differs"]


# ---------------------------------------------------------------- neo4j-admin path (Docker)

IMAGE = "neo4j:5.26-community"


def _docker_ready() -> bool:
    if shutil.which("docker") is None:
        return False
    try:
        info = subprocess.run(["docker", "info"], capture_output=True, timeout=20)
        image = subprocess.run(["docker", "image", "inspect", IMAGE], capture_output=True, timeout=20)
    except (OSError, subprocess.TimeoutExpired):
        return False
    return info.returncode == 0 and image.returncode == 0


docker = pytest.mark.skipif(not _docker_ready(), reason=f"no Docker daemon or image {IMAGE}")


def _port_free(port: int) -> bool:
    with closing(socket.socket()) as s:
        return s.connect_ex(("127.0.0.1", port)) != 0


def _wait_bolt(uri: str, seconds: float = 180) -> None:
    from neo4j import GraphDatabase

    deadline = time.monotonic() + seconds
    while True:
        try:
            with GraphDatabase.driver(uri, auth=("neo4j", "x")) as driver:
                driver.execute_query("RETURN 1", database_="neo4j")
            return
        except Exception:
            if time.monotonic() > deadline:
                raise
            time.sleep(1)


@pytest.fixture(scope="module")
def containers():
    ports = [int(p) for p in os.environ.get("SMARTSKETCH_K10_DOCKER_PORTS", "7697,7698").split(",")]
    if not all(_port_free(p) for p in ports):
        pytest.skip(f"ports {ports} are in use")
    suffix = uuid.uuid4().hex[:8]
    names = [f"k10-src-{suffix}", f"k10-dst-{suffix}"]
    try:
        for name, port in zip(names, ports):
            subprocess.run(["docker", "run", "-d", "--name", name, "-p", f"127.0.0.1:{port}:7687",
                            "-e", "NEO4J_AUTH=none", IMAGE], check=True, capture_output=True, timeout=120)
        uris = [f"bolt://127.0.0.1:{p}" for p in ports]
        for uri in uris:
            _wait_bolt(uri)
        yield SimpleNamespace(src=names[0], dst=names[1], src_uri=uris[0], dst_uri=uris[1])
    finally:
        subprocess.run(["docker", "rm", "-f", "-v", *names], capture_output=True, timeout=120)


@docker
def test_neo4j_admin_dump_and_load_round_trip(tmp_path, containers):
    from neo4j import GraphDatabase

    source = GraphDatabase.driver(containers.src_uri, auth=("neo4j", "x"))
    target = GraphDatabase.driver(containers.dst_uri, auth=("neo4j", "x"))
    try:
        env = seed(tmp_path, source)
        user_rows = dump(env.path)
        result = run_script(BACKUP, "--out", str(tmp_path / "backups"), "--neo4j-container", containers.src,
                            sqlite=env.url, neo4j_uri=containers.src_uri)
        directory = backup_dir(result)
        data = manifest(directory)
        assert data["neo4j_mode"] == "admin" and "neo4j/neo4j.dump" in data["files"]
        assert data["inspection"]["consistency"]["pointer_errors"] == []
        _wait_bolt(containers.src_uri)  # the source came back after the offline dump
        assert student_names(source, env.course, env.v2.version_id) == {"a", "b", "c"}

        restored = tmp_path / "drill" / "restored.sqlite3"
        result = run_script(RESTORE, "--from", str(directory), "--sqlite-target", str(restored),
                            "--neo4j-uri", containers.dst_uri, "--neo4j-container", containers.dst)
        assert result.returncode == 0, result.stderr
        _wait_bolt(containers.dst_uri)
        assert pointer(sqlite_url(restored), env.course) == (env.v2.version_id, 2)
        assert student_names(target, env.course, env.v2.version_id) == {"a", "b", "c"}
        assert dump(env.path) == user_rows

        # the restored container now holds data: a second load is refused without confirmation
        again = run_script(RESTORE, "--from", str(directory), "--sqlite-target", str(tmp_path / "other.sqlite3"),
                           "--neo4j-uri", containers.dst_uri, "--neo4j-container", containers.dst)
        assert again.returncode == 2 and "not empty" in again.stderr
    finally:
        source.close()
        target.close()
