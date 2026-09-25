"""D10：来源块持久化（ADR-012 修订 1 决定 9；ADR-018；specs/teacher-review-publish.md V2、PUB-28～30；
specs/task-processing.md §8.4 `parsing` 行、§8.6）。"""

from __future__ import annotations

import shutil
import sqlite3
from pathlib import Path

import pytest

from app.repositories import chunks as store
from app.repositories import tasks
from app.repositories.chunks import (
    ChunkDeleteRefused,
    ChunkImmutableError,
    ChunkScopeError,
    ChunkWriteResult,
    StoredChunk,
)
from app.repositories.sqlite import connect, migrate
from app.services.chunk_identity import (
    ChunkIdentityError,
    assign_chunk_identities,
    derive_chunk_id,
    revision_id_for,
    text_sha256,
)
from app.services.chunking import SemanticChunk, chunk_blocks, chunking_version
from app.services.file_storage import StoredFile
from app.services.parsers.models import ParsedBlock, RevisionKey, SourceLocator

MIGRATIONS = Path(__file__).resolve().parents[2] / "src" / "backend" / "migrations"
HASH_A = "sha256:" + "a" * 64
HASH_B = "sha256:" + "b" * 64
PV_1 = "txt/1+" + chunking_version(40, 10)
PV_2 = "txt/2+" + chunking_version(40, 10)
COURSE = "course-a"
OTHER = "course-b"


def _url(path: Path) -> str:
    return f"sqlite:///{path.as_posix()}"


def _chunk_migration() -> Path:
    # D-10：合并前可能改号，按文件名后缀定位，不写死版本号。
    (path,) = MIGRATIONS.glob("*_chunks.sql")
    return path


def _copy_migrations(target: Path, *, include_chunks: bool) -> Path:
    """只复制本任务需要的迁移：块迁移之前的全部，以及（可选）块迁移本身；之后的迁移不参与。"""
    last = _chunk_migration().name[:3]
    target.mkdir(parents=True, exist_ok=True)
    for path in sorted(MIGRATIONS.glob("*.sql")):
        version = path.name[:3]
        if version < last or (include_chunks and version == last):
            shutil.copyfile(path, target / path.name)
    return target


_counter = iter(range(10**6))


def _stored_file(tmp_path: Path, content_hash: str = HASH_A) -> StoredFile:
    n = next(_counter)
    storage_name = f"{n:032x}.txt"
    path = tmp_path / storage_name
    path.write_text("course notes", encoding="utf-8")
    return StoredFile(
        storage_name=storage_name,
        path=path,
        original_filename="notes.txt",
        format="txt",
        size_bytes=12,
        content_hash=content_hash,
    )


@pytest.fixture
def db_url(tmp_path: Path) -> str:
    url = _url(tmp_path / "state.sqlite3")
    directory = _copy_migrations(tmp_path / "migrations", include_chunks=True)
    assert _chunk_migration().name[:3] in migrate(url, directory)
    return url


@pytest.fixture
def new_material(db_url, tmp_path):
    """Create a material with its first task; return ``(material_id, task_id)``."""

    def _make(course_id: str = COURSE) -> tuple[str, str]:
        result = tasks.create_material_task(
            db_url,
            course_id=course_id,
            stored_file=_stored_file(tmp_path),
            idempotency_key=f"key-{next(_counter)}",
        )
        return result.material.id, result.task.id

    return _make


def _sql(url: str, statement: str, *params: object) -> list[tuple]:
    with connect(url) as database:
        return database.execute(statement, params).fetchall()


def _extra_task(url: str, course_id: str, material_id: str) -> str:
    task_id = f"task{next(_counter):028x}"
    _sql(
        url,
        "INSERT INTO processing_tasks (id, course_id, document_id, idempotency_key) VALUES (?, ?, ?, ?)",
        task_id,
        course_id,
        material_id,
        f"extra-{task_id}",
    )
    return task_id


def _set_stage(url: str, task_id: str, stage: str) -> None:
    if stage == "failed":
        _sql(
            url,
            "UPDATE processing_tasks SET stage = 'failed', error_code = 'PARSE_FAILED', "
            "error_message = '解析失败' WHERE id = ?",
            task_id,
        )
    elif stage == "cancelled":
        _sql(url, "UPDATE processing_tasks SET stage = 'cancelled', cancel_requested = 1 WHERE id = ?", task_id)
    else:
        _sql(url, "UPDATE processing_tasks SET stage = ? WHERE id = ?", stage, task_id)


def _blocks(texts: list[str], title: str = "第1章 栈") -> list[ParsedBlock]:
    return [
        ParsedBlock(ordinal=i, text=text, locator=SourceLocator(section_titles=(title,), paragraph=i + 1))
        for i, text in enumerate(texts)
    ]


TEXTS = [
    "栈是一种后进先出的线性结构。",
    "入栈与出栈都只在栈顶进行，时间复杂度为常数。",
    "队列与栈不同，它先进先出。",
    "递归调用依赖调用栈保存返回地址。",
]


def _chunks(texts: list[str] = TEXTS) -> tuple[SemanticChunk, ...]:
    result = chunk_blocks(_blocks(texts), target_chars=40, overlap_chars=10)
    assert len(result) >= 2, "测试数据须切出多个块"
    return result


def _key(material_id: str, content_hash: str = HASH_A, parser_version: str = PV_1) -> RevisionKey:
    return RevisionKey(document_id=material_id, content_hash=content_hash, parser_version=parser_version)


def _persist(url: str, course_id: str, task_id: str, key: RevisionKey, chunks=None):
    return store.persist_revision_chunks(
        url, course_id=course_id, task_id=task_id, key=key, chunks=_chunks() if chunks is None else chunks
    )


def _no_committed(database: sqlite3.Connection, course_id: str) -> frozenset[str]:
    return frozenset()


def _count(url: str, table: str) -> int:
    return _sql(url, f"SELECT count(*) FROM {table}")[0][0]


# --- migration ---------------------------------------------------------------------------


def _schema(url: str) -> list[tuple]:
    return _sql(
        url,
        "SELECT type, name, tbl_name, sql FROM sqlite_master "
        "WHERE name NOT LIKE 'sqlite_%' ORDER BY type, name",
    )


def test_migration_applies_on_top_of_existing_data_and_keeps_a_backup(tmp_path):
    url = _url(tmp_path / "state.sqlite3")
    migrate(url, _copy_migrations(tmp_path / "before", include_chunks=False))
    before = tasks.create_material_task(
        url, course_id=COURSE, stored_file=_stored_file(tmp_path), idempotency_key="old"
    )

    version = _chunk_migration().name[:3]
    assert migrate(url, _copy_migrations(tmp_path / "all", include_chunks=True)) == [version]

    assert next((tmp_path / "backups").glob(f"*-before-{version}.sqlite"))
    tables = {row[0] for row in _sql(url, "SELECT name FROM sqlite_master WHERE type = 'table'")}
    assert {"material_revisions", "task_revisions", "chunks"} <= tables
    assert tasks.get_task(url, before.task.id, course_id=COURSE) is not None


def test_documented_rollback_restores_previous_schema_and_the_migration_can_be_reapplied(tmp_path):
    url = _url(tmp_path / "state.sqlite3")
    migrate(url, _copy_migrations(tmp_path / "before", include_chunks=False))
    previous = _schema(url)
    migrate(url, _copy_migrations(tmp_path / "all", include_chunks=True))

    prefix = "-- ROLLBACK: "
    steps = [
        line[len(prefix):]
        for line in _chunk_migration().read_text(encoding="utf-8").splitlines()
        if line.startswith(prefix)
    ]
    assert steps, "迁移文件须以 '-- ROLLBACK: ' 行写明手工回滚步骤"
    with connect(url) as database:
        database.execute("BEGIN IMMEDIATE")
        for step in steps:
            database.execute(step)
        database.execute("COMMIT")

    assert _schema(url) == previous
    assert migrate(url, tmp_path / "all") == [_chunk_migration().name[:3]]


# --- schema invariants -------------------------------------------------------------------


def test_schema_refuses_updates_to_chunks_and_revisions(db_url, new_material):
    material_id, task_id = new_material()
    _persist(db_url, COURSE, task_id, _key(material_id))
    for statement in (
        "UPDATE chunks SET text = 'x'",
        "UPDATE chunks SET text_sha256 = text_sha256",
        "UPDATE material_revisions SET parser_version = parser_version",
    ):
        with pytest.raises(sqlite3.IntegrityError, match="immutable"):
            _sql(db_url, statement)


def test_schema_rejects_rows_that_break_identity_or_course_scope(db_url, new_material):
    material_id, task_id = new_material()
    other_material, other_task = new_material(OTHER)
    revision, _ = _persist(db_url, COURSE, task_id, _key(material_id))
    rid = revision.revision_id
    good = (rid, COURSE, material_id, "t", text_sha256("t"), "[]", '[{"block_ordinal":0}]')
    insert = (
        "INSERT INTO chunks (chunk_id, revision_id, course_id, material_id, ordinal, text, "
        "text_sha256, section_titles, sources) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)"
    )
    # 块 ID 必须等于 revision_id-ordinal（十进制、无前导零）
    with pytest.raises(sqlite3.IntegrityError):
        _sql(db_url, insert, f"{rid}-07", good[0], good[1], good[2], 7, *good[3:])
    # 块的课程必须与修订一致
    with pytest.raises(sqlite3.IntegrityError):
        _sql(db_url, insert, f"{rid}-99", rid, OTHER, material_id, 99, *good[3:])
    # 至少一个出处
    with pytest.raises(sqlite3.IntegrityError):
        _sql(db_url, insert, f"{rid}-98", rid, COURSE, material_id, 98, "t", text_sha256("t"), "[]", "[]")
    # 任务-修订关联只能指向同课程、同资料的任务
    with pytest.raises(sqlite3.IntegrityError, match="task"):
        _sql(
            db_url,
            "INSERT INTO task_revisions (task_id, revision_id, course_id, material_id) VALUES (?, ?, ?, ?)",
            other_task,
            rid,
            COURSE,
            material_id,
        )


def test_deleting_a_material_with_revisions_is_refused(db_url, new_material):
    material_id, task_id = new_material()
    _persist(db_url, COURSE, task_id, _key(material_id))
    _sql(db_url, "DELETE FROM task_revisions")
    with pytest.raises(sqlite3.IntegrityError):
        _sql(db_url, "DELETE FROM processing_tasks")
        _sql(db_url, "DELETE FROM materials WHERE id = ?", material_id)
    with pytest.raises(sqlite3.IntegrityError):
        _sql(db_url, "DELETE FROM material_revisions")
    assert _count(db_url, "chunks") == len(_chunks())


# --- revisions ---------------------------------------------------------------------------


def test_record_revision_derives_id_and_is_idempotent(db_url, new_material):
    material_id, task_id = new_material()
    key = _key(material_id)
    with connect(db_url) as database:
        database.execute("BEGIN IMMEDIATE")
        first = store.record_revision(database, course_id=COURSE, task_id=task_id, key=key)
        second = store.record_revision(database, course_id=COURSE, task_id=task_id, key=key)
        database.execute("COMMIT")

    assert first == second
    assert first.revision_id == revision_id_for(key)
    assert (first.course_id, first.material_id, first.content_hash, first.parser_version) == (
        COURSE,
        material_id,
        HASH_A,
        PV_1,
    )
    assert _count(db_url, "material_revisions") == 1
    assert [r.revision_id for r in store.list_task_revisions(db_url, course_id=COURSE, task_id=task_id)] == [
        first.revision_id
    ]
    assert store.get_revision(db_url, course_id=COURSE, revision_id=first.revision_id) == first
    assert store.get_revision(db_url, course_id=OTHER, revision_id=first.revision_id) is None


def test_record_revision_rejects_task_outside_course_or_other_document(db_url, new_material):
    material_id, task_id = new_material()
    other_material, _ = new_material()
    foreign_material, foreign_task = new_material(OTHER)
    cases = [
        (OTHER, task_id, _key(material_id)),  # 任务不在该课程
        (COURSE, task_id, _key(other_material)),  # 任务处理的不是这份资料
        (COURSE, foreign_task, _key(foreign_material)),  # 外课程的任务与资料
        (COURSE, "missing-task", _key(material_id)),
    ]
    for course_id, task, key in cases:
        with connect(db_url) as database:
            database.execute("BEGIN IMMEDIATE")
            with pytest.raises(ChunkScopeError):
                store.record_revision(database, course_id=course_id, task_id=task, key=key)
            database.execute("ROLLBACK")
    assert _count(db_url, "material_revisions") == 0
    assert _count(db_url, "task_revisions") == 0


def test_record_revision_requires_composite_parser_version(db_url, new_material):
    material_id, task_id = new_material()
    with connect(db_url) as database:
        database.execute("BEGIN IMMEDIATE")
        with pytest.raises(ChunkIdentityError, match="parser_version"):
            store.record_revision(database, course_id=COURSE, task_id=task_id, key=_key(material_id, parser_version="txt/1"))
        database.execute("ROLLBACK")


def test_connection_level_writes_require_the_callers_transaction(db_url, new_material):
    material_id, task_id = new_material()
    key = _key(material_id)
    with connect(db_url) as database:
        with pytest.raises(RuntimeError, match="transaction"):
            store.record_revision(database, course_id=COURSE, task_id=task_id, key=key)
        with pytest.raises(RuntimeError, match="transaction"):
            store.put_chunks(database, course_id=COURSE, revision_id=revision_id_for(key), chunks=_chunks())
    assert _count(db_url, "material_revisions") == 0


# --- chunks ------------------------------------------------------------------------------


def test_persist_round_trips_text_and_sources_with_d09_identities(db_url, new_material):
    material_id, task_id = new_material()
    key = _key(material_id)
    semantic = _chunks()
    revision, written = _persist(db_url, COURSE, task_id, key, semantic)

    identities = assign_chunk_identities(COURSE, key, semantic)
    assert written == ChunkWriteResult(inserted=tuple(i.chunk_id for i in identities), existing=())
    stored = store.list_chunks(db_url, course_id=COURSE, revision_id=revision.revision_id)
    assert [c.chunk_id for c in stored] == [i.chunk_id for i in identities]
    for chunk, identity, original in zip(stored, identities, semantic):
        assert isinstance(chunk, StoredChunk)
        assert (chunk.course_id, chunk.material_id, chunk.revision_id) == (COURSE, material_id, revision.revision_id)
        assert chunk.ordinal == original.ordinal
        assert chunk.text == original.text
        assert chunk.text_sha256 == identity.text_sha256
        assert chunk.section_titles == original.section_titles
        assert chunk.sources == original.sources


def test_stored_chunk_repr_does_not_contain_text(db_url, new_material):
    material_id, task_id = new_material()
    revision, _ = _persist(db_url, COURSE, task_id, _key(material_id))
    chunk = store.list_chunks(db_url, course_id=COURSE, revision_id=revision.revision_id)[0]
    assert chunk.text not in repr(chunk)


def test_pub30_retry_with_same_content_writes_nothing_new(db_url, new_material):
    material_id, task_id = new_material()
    key = _key(material_id)
    _, first = _persist(db_url, COURSE, task_id, key)
    before = _sql(db_url, "SELECT * FROM chunks ORDER BY chunk_id")

    # 同一任务重跑，以及另一任务处理同资料同内容同解析器
    again_task = _extra_task(db_url, COURSE, material_id)
    _, retry = _persist(db_url, COURSE, task_id, key)
    _, other = _persist(db_url, COURSE, again_task, key)

    assert retry == other == ChunkWriteResult(inserted=(), existing=first.inserted)
    assert _sql(db_url, "SELECT * FROM chunks ORDER BY chunk_id") == before
    assert _count(db_url, "material_revisions") == 1
    assert _count(db_url, "task_revisions") == 2


def test_pub30_different_text_under_existing_id_is_rejected_atomically(db_url, new_material):
    material_id, task_id = new_material()
    key = _key(material_id)
    original = _chunks()
    _persist(db_url, COURSE, task_id, key, original[:2])
    before = _sql(db_url, "SELECT * FROM chunks ORDER BY chunk_id")

    tampered = list(original)
    tampered[1] = SemanticChunk(
        ordinal=1, text=original[1].text + "（改）", section_titles=original[1].section_titles, sources=original[1].sources
    )
    with pytest.raises(ChunkImmutableError, match=derive_chunk_id(revision_id_for(key), 1)):
        _persist(db_url, COURSE, task_id, key, tuple(tampered))

    # 同批中排在后面的新块也未写入，已有块原文不变
    assert _sql(db_url, "SELECT * FROM chunks ORDER BY chunk_id") == before


def test_pub30_same_text_with_different_locator_is_rejected(db_url, new_material):
    material_id, task_id = new_material()
    key = _key(material_id)
    original = _chunks()
    _persist(db_url, COURSE, task_id, key, original)

    first = original[0]
    moved = tuple(
        type(source)(
            block_ordinal=source.block_ordinal,
            start=source.start,
            end=source.end,
            locator=SourceLocator(section_titles=source.locator.section_titles, paragraph=(source.locator.paragraph or 0) + 5),
        )
        for source in first.sources
    )
    changed = (SemanticChunk(ordinal=0, text=first.text, section_titles=first.section_titles, sources=moved),)
    with pytest.raises(ChunkImmutableError):
        _persist(db_url, COURSE, task_id, key, changed)


def test_pub29_parser_upgrade_creates_a_new_revision_and_leaves_old_chunks(db_url, new_material):
    material_id, task_id = new_material()
    old_revision, old = _persist(db_url, COURSE, task_id, _key(material_id, parser_version=PV_1))
    snapshot = store.list_chunks(db_url, course_id=COURSE, revision_id=old_revision.revision_id)

    new_task = _extra_task(db_url, COURSE, material_id)
    new_revision, new = _persist(db_url, COURSE, new_task, _key(material_id, parser_version=PV_2))

    assert new_revision.revision_id != old_revision.revision_id
    assert set(new.inserted).isdisjoint(old.inserted)
    assert store.list_chunks(db_url, course_id=COURSE, revision_id=old_revision.revision_id) == snapshot
    assert {r.revision_id for r in store.list_material_revisions(db_url, course_id=COURSE, material_id=material_id)} == {
        old_revision.revision_id,
        new_revision.revision_id,
    }


def test_pub28_new_content_creates_a_new_revision_and_keeps_old_text(db_url, new_material):
    material_id, task_id = new_material()
    old_revision, _ = _persist(db_url, COURSE, task_id, _key(material_id, content_hash=HASH_A))
    snapshot = store.list_chunks(db_url, course_id=COURSE, revision_id=old_revision.revision_id)

    new_task = _extra_task(db_url, COURSE, material_id)
    new_texts = ["全新内容：" + text for text in TEXTS]
    new_revision, _ = _persist(db_url, COURSE, new_task, _key(material_id, content_hash=HASH_B), _chunks(new_texts))

    assert new_revision.revision_id != old_revision.revision_id
    assert store.list_chunks(db_url, course_id=COURSE, revision_id=old_revision.revision_id) == snapshot
    fresh = store.list_chunks(db_url, course_id=COURSE, revision_id=new_revision.revision_id)
    assert fresh and {c.chunk_id for c in fresh}.isdisjoint(c.chunk_id for c in snapshot)


def test_put_chunks_requires_a_revision_recorded_in_the_same_course(db_url, new_material):
    material_id, task_id = new_material()
    foreign_material, foreign_task = new_material(OTHER)
    foreign_revision, _ = _persist(db_url, OTHER, foreign_task, _key(foreign_material))
    unknown = revision_id_for(_key(material_id))
    for revision_id in (unknown, foreign_revision.revision_id):
        with connect(db_url) as database:
            database.execute("BEGIN IMMEDIATE")
            with pytest.raises(ChunkScopeError):
                store.put_chunks(database, course_id=COURSE, revision_id=revision_id, chunks=_chunks())
            database.execute("ROLLBACK")
    assert _sql(db_url, "SELECT count(*) FROM chunks WHERE course_id = ?", COURSE)[0][0] == 0


@pytest.mark.parametrize("ordinals", [(1, 2), (0, 2), (0, 0)])
def test_put_chunks_requires_consecutive_ordinals_from_zero(db_url, new_material, ordinals):
    material_id, task_id = new_material()
    base = _chunks()
    broken = tuple(
        SemanticChunk(ordinal=o, text=base[i].text, section_titles=base[i].section_titles, sources=base[i].sources)
        for i, o in enumerate(ordinals)
    )
    with pytest.raises(ChunkIdentityError, match="ordinal"):
        _persist(db_url, COURSE, task_id, _key(material_id), broken)
    assert _count(db_url, "chunks") == 0
    assert _count(db_url, "material_revisions") == 0


# --- lookup and course isolation ---------------------------------------------------------


def test_lookup_by_course_material_revision_and_ids_is_course_scoped(db_url, new_material):
    material_a, task_a = new_material()
    material_b, task_b = new_material()
    foreign_material, foreign_task = new_material(OTHER)
    rev_a, written_a = _persist(db_url, COURSE, task_a, _key(material_a))
    rev_b, written_b = _persist(db_url, COURSE, task_b, _key(material_b))
    rev_f, written_f = _persist(db_url, OTHER, foreign_task, _key(foreign_material))

    by_material = store.list_chunks(db_url, course_id=COURSE, material_id=material_a)
    assert [c.chunk_id for c in by_material] == list(written_a.inserted)
    assert store.list_chunks(db_url, course_id=COURSE, material_id=material_a, revision_id=rev_b.revision_id) == ()
    assert store.list_chunks(db_url, course_id=OTHER, material_id=material_a) == ()
    assert store.list_chunks(db_url, course_id=COURSE, revision_id=rev_f.revision_id) == ()
    with pytest.raises(ValueError):
        store.list_chunks(db_url, course_id=COURSE)

    one = written_b.inserted[1]
    assert store.get_chunk(db_url, course_id=COURSE, chunk_id=one).chunk_id == one
    assert store.get_chunk(db_url, course_id=OTHER, chunk_id=one) is None
    assert store.get_chunk(db_url, course_id=COURSE, chunk_id="not-a-chunk") is None

    wanted = [written_b.inserted[0], written_f.inserted[0], "missing", written_a.inserted[0], written_b.inserted[0]]
    assert [c.chunk_id for c in store.get_chunks(db_url, course_id=COURSE, chunk_ids=wanted)] == [
        written_b.inserted[0],
        written_a.inserted[0],
    ]
    assert store.list_material_revisions(db_url, course_id=OTHER, material_id=material_a) == ()
    assert store.list_task_revisions(db_url, course_id=OTHER, task_id=task_a) == ()


# --- deletion protection (V2 / §8.6) -----------------------------------------------------


def _remaining(url: str, revision_id: str) -> int:
    return _sql(url, "SELECT count(*) FROM chunks WHERE revision_id = ?", revision_id)[0][0]


@pytest.mark.parametrize("terminal", ["failed", "cancelled"])
def test_unprotected_revision_of_failed_or_cancelled_task_is_deleted(db_url, new_material, terminal):
    material_id, task_id = new_material()
    keep_material, keep_task = new_material()
    revision, written = _persist(db_url, COURSE, task_id, _key(material_id))
    kept, _ = _persist(db_url, COURSE, keep_task, _key(keep_material))
    _set_stage(db_url, task_id, terminal)

    result = store.delete_task_chunks(db_url, course_id=COURSE, task_id=task_id, committed_revision_ids=_no_committed)

    assert result.deleted_revisions == (revision.revision_id,)
    assert result.kept_revisions == ()
    assert result.deleted_chunks == len(written.inserted)
    assert _remaining(db_url, revision.revision_id) == 0
    assert store.get_revision(db_url, course_id=COURSE, revision_id=revision.revision_id) is None
    assert _remaining(db_url, kept.revision_id) > 0

    again = store.delete_task_chunks(db_url, course_id=COURSE, task_id=task_id, committed_revision_ids=_no_committed)
    assert (again.deleted_revisions, again.kept_revisions, again.deleted_chunks) == ((), (), 0)


@pytest.mark.parametrize("sharing_stage", ["awaiting_review", "completed", "parsing", "queued"])
def test_revision_shared_with_a_live_or_reviewed_task_is_kept(db_url, new_material, sharing_stage):
    material_id, task_id = new_material()
    key = _key(material_id)
    revision, written = _persist(db_url, COURSE, task_id, key)
    other_task = _extra_task(db_url, COURSE, material_id)
    _persist(db_url, COURSE, other_task, key)
    _set_stage(db_url, other_task, sharing_stage)
    _set_stage(db_url, task_id, "failed")

    result = store.delete_task_chunks(db_url, course_id=COURSE, task_id=task_id, committed_revision_ids=_no_committed)

    assert result.kept_revisions == (revision.revision_id,)
    assert result.deleted_revisions == ()
    assert result.deleted_chunks == 0
    assert _remaining(db_url, revision.revision_id) == len(written.inserted)
    assert len(store.list_task_revisions(db_url, course_id=COURSE, task_id=task_id)) == 1


def test_revision_shared_only_with_other_failed_tasks_is_deleted(db_url, new_material):
    material_id, task_id = new_material()
    key = _key(material_id)
    revision, _ = _persist(db_url, COURSE, task_id, key)
    other_task = _extra_task(db_url, COURSE, material_id)
    _persist(db_url, COURSE, other_task, key)
    _set_stage(db_url, other_task, "cancelled")
    _set_stage(db_url, task_id, "failed")

    result = store.delete_task_chunks(db_url, course_id=COURSE, task_id=task_id, committed_revision_ids=_no_committed)
    assert result.deleted_revisions == (revision.revision_id,)
    assert _remaining(db_url, revision.revision_id) == 0
    # 另一个失败任务的关联仍在，修订行随它的清理一并删除
    assert store.get_revision(db_url, course_id=COURSE, revision_id=revision.revision_id) is not None
    store.delete_task_chunks(db_url, course_id=COURSE, task_id=other_task, committed_revision_ids=_no_committed)
    assert store.get_revision(db_url, course_id=COURSE, revision_id=revision.revision_id) is None


def test_revision_in_a_committed_version_is_kept(db_url, new_material):
    material_id, task_id = new_material()
    revision, written = _persist(db_url, COURSE, task_id, _key(material_id))
    _set_stage(db_url, task_id, "failed")
    seen: list[tuple[str, bool]] = []

    def committed(database: sqlite3.Connection, course_id: str) -> list[str]:
        seen.append((course_id, database.in_transaction))
        return [revision.revision_id]

    result = store.delete_task_chunks(db_url, course_id=COURSE, task_id=task_id, committed_revision_ids=committed)

    assert seen == [(COURSE, True)]
    assert result.kept_revisions == (revision.revision_id,)
    assert _remaining(db_url, revision.revision_id) == len(written.inserted)


def test_committed_predicate_failure_deletes_nothing(db_url, new_material):
    material_id, task_id = new_material()
    revision, written = _persist(db_url, COURSE, task_id, _key(material_id))
    _set_stage(db_url, task_id, "failed")

    def broken(database: sqlite3.Connection, course_id: str) -> list[str]:
        raise RuntimeError("版本表不可读")

    with pytest.raises(RuntimeError, match="版本表不可读"):
        store.delete_task_chunks(db_url, course_id=COURSE, task_id=task_id, committed_revision_ids=broken)
    assert _remaining(db_url, revision.revision_id) == len(written.inserted)


@pytest.mark.parametrize("stage", ["queued", "parsing", "extracting", "awaiting_review", "completed"])
def test_delete_is_refused_unless_the_task_failed_or_was_cancelled(db_url, new_material, stage):
    material_id, task_id = new_material()
    revision, written = _persist(db_url, COURSE, task_id, _key(material_id))
    _set_stage(db_url, task_id, stage)
    with pytest.raises(ChunkDeleteRefused):
        store.delete_task_chunks(db_url, course_id=COURSE, task_id=task_id, committed_revision_ids=_no_committed)
    assert _remaining(db_url, revision.revision_id) == len(written.inserted)


def test_delete_is_course_scoped(db_url, new_material):
    material_id, task_id = new_material()
    revision, written = _persist(db_url, COURSE, task_id, _key(material_id))
    _set_stage(db_url, task_id, "failed")
    with pytest.raises(ChunkScopeError):
        store.delete_task_chunks(db_url, course_id=OTHER, task_id=task_id, committed_revision_ids=_no_committed)
    assert _remaining(db_url, revision.revision_id) == len(written.inserted)
