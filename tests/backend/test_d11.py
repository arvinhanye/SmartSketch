"""D11：解析阶段 worker 编排（specs/task-processing.md §2、§6、§8.2～§8.4、§8.8；ADR-011、ADR-012 修订 1、
ADR-018；specs/teacher-review-publish.md V2）。

被 C09 领取、处于 ``parsing`` 的任务：读已存文件 → 按格式解析 → D08 分块 → D09 块身份 → D10 持久化 →
检查点（带令牌条件的 T4 转 ``extracting``，或取消标志为真时 T8 转 ``cancelled``），块写入与转换同一事务。
失败：``DOCUMENT_UNREADABLE``（corrupted/encrypted/no_text，不重试）、存储不可用主动释放（耗尽 T9
``STORAGE_UNAVAILABLE`` + attempts/stage）、其他 ``INTERNAL_ERROR``；租约丢失立即停写。
对照 TASK-14、LEASE-4、LEASE-7，以及 §8.4 ``parsing`` 行的幂等要求。
"""

from __future__ import annotations

import dataclasses
import hashlib
import io
import json
import secrets
import sqlite3
import time
import zipfile
from pathlib import Path

import pytest

from app.config import load_settings
from app.repositories import chunks as store
from app.repositories import task_leases, tasks
from app.repositories.sqlite import connect, migrate
from app.services.chunk_identity import assign_chunk_identities, revision_parser_version
from app.services.chunking import chunk_blocks, chunking_version
from app.services.file_storage import FileStorage, StoredFile
from app.services.parsers import pdf_headings
from app.services.parsers.models import RevisionKey
from app.services.task_cancel import cancel_task
from app.services.task_state import TaskError, TaskState, TransitionEvent, apply_event, Applied
from app.workers import parse_task
from app.workers.parse_task import LeaseHeartbeat, ParseStatus, report_progress, run_once, run_parse_stage

COURSE = "course-a"
OTHER = "course-b"
LEASE_SECONDS = 60
MAX_ATTEMPTS = 3
SECRET_TEXT = "绝密原文-不得进入错误信息"


class _Crash(BaseException):
    """模拟进程在事务提交前被杀：不被 ``except Exception`` 捕获。"""


# --- 夹具文件 ------------------------------------------------------------------------------------

TXT = (
    "第1章 栈\n"
    "栈是一种后进先出的线性表，只允许在表的一端进行插入和删除操作。\n"
    "\n"
    "入栈操作把元素放到栈顶；出栈操作取走栈顶元素。\n"
    "\n"
    "第2章 队列\n"
    "队列是一种先进先出的线性表，在队尾插入，在队头删除。\n"
).encode("utf-8")

MARKDOWN = (
    "# 线性结构\n\n"
    "## 栈\n\n"
    "栈是一种后进先出的线性表。\n\n"
    "## 队列\n\n"
    "队列是一种先进先出的线性表。\n"
).encode("utf-8")


def _docx(paragraphs: list[str]) -> bytes:
    body = "".join(f"<w:p><w:r><w:t>{text}</w:t></w:r></w:p>" for text in paragraphs)
    document = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        f"<w:body>{body}</w:body></w:document>"
    )
    content_types = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/word/document.xml" ContentType="application/'
        'vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>'
    )
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", content_types)
        archive.writestr("word/document.xml", document)
    return buffer.getvalue()


DOCX = _docx(["栈是一种后进先出的线性表。", "队列是一种先进先出的线性表。"])
# OLE 复合文件 + 加密流名：受密码保护的 Office 文档（D04）。
ENCRYPTED_DOCX = bytes.fromhex("D0CF11E0A1B11AE1") + b"\x00" * 64 + "EncryptionInfo".encode("utf-16-le")


def _pdf(pages: list[list[str]], *, encrypted: bool = False) -> bytes:
    objects: list[bytes] = [b"", b"", b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>"]
    kids: list[int] = []
    for lines in pages:
        content = b"".join(
            b"BT /F1 12 Tf 72 %d Td (%s) Tj ET\n" % (700 - 20 * index, line.encode("latin-1"))
            for index, line in enumerate(lines)
        )
        objects.append(b"<< /Length %d >>\nstream\n%s\nendstream" % (len(content), content))
        content_number = len(objects)
        objects.append(
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            b"/Resources << /Font << /F1 3 0 R >> >> /Contents %d 0 R >>" % content_number
        )
        kids.append(len(objects))
    objects[0] = b"<< /Type /Catalog /Pages 2 0 R >>"
    objects[1] = b"<< /Type /Pages /Kids [%s] /Count %d >>" % (
        b" ".join(b"%d 0 R" % kid for kid in kids),
        len(kids),
    )
    trailer_extra = b""
    if encrypted:
        owner = hashlib.md5(b"owner-secret").digest() * 2
        user = hashlib.sha256(b"not-the-empty-password").digest()
        objects.append(
            b"<< /Filter /Standard /V 1 /R 2 /Length 40 /P -44 /O <%s> /U <%s> >>"
            % (owner.hex().encode(), user.hex().encode())
        )
        file_id = b"0123456789abcdef0123456789abcdef"
        trailer_extra = b"/Encrypt %d 0 R /ID [<%s> <%s>] " % (len(objects), file_id, file_id)
    out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += b"%d 0 obj\n%s\nendobj\n" % (number, body)
    xref_at = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)
    for offset in offsets:
        out += b"%010d 00000 n \n" % offset
    out += b"trailer\n<< /Size %d /Root 1 0 R %s>>\nstartxref\n%d\n%%%%EOF\n" % (
        len(objects) + 1,
        trailer_extra,
        xref_at,
    )
    return bytes(out)


PDF = _pdf([["Stacks are last in first out lists."], ["Queues are first in first out lists."]])

_SUFFIX = {"txt": ".txt", "markdown": ".md", "docx": ".docx", "pdf": ".pdf"}
_NAME = {"txt": "notes.txt", "markdown": "notes.md", "docx": "notes.docx", "pdf": "notes.pdf"}


# --- 数据准备 ------------------------------------------------------------------------------------


def _url(path: Path) -> str:
    return f"sqlite:///{path.as_posix()}"


@pytest.fixture
def db_url(tmp_path: Path) -> str:
    url = _url(tmp_path / "state.sqlite3")
    migrate(url)
    return url


@pytest.fixture
def storage(tmp_path: Path) -> FileStorage:
    return FileStorage(tmp_path / "files", 10 * 1024 * 1024)


def _sql(url: str, statement: str, *params: object) -> list[tuple]:
    with connect(url) as database:
        return database.execute(statement, params).fetchall()


def _add_material(
    db_url: str, storage: FileStorage, data: bytes, fmt: str, *, course: str = COURSE
) -> tuple[str, str]:
    """把字节直接放进存储根目录（绕过 C05 的格式嗅探，以便放入损坏/加密文件），建资料与任务。"""
    storage_name = secrets.token_hex(16) + _SUFFIX[fmt]
    path = storage.path_for(storage_name)
    path.write_bytes(data)
    stored = StoredFile(
        storage_name=storage_name,
        path=path,
        original_filename=_NAME[fmt],
        format=fmt,  # type: ignore[arg-type]
        size_bytes=max(len(data), 1),
        content_hash="sha256:" + hashlib.sha256(data).hexdigest(),
    )
    result = tasks.create_material_task(
        db_url, course_id=course, stored_file=stored, idempotency_key=secrets.token_hex(8)
    )
    return result.material.id, result.task.id


def _claim(db_url: str, owner: str = "worker-a") -> task_leases.Lease:
    lease = task_leases.claim_next(
        db_url, owner=owner, lease_seconds=LEASE_SECONDS, max_attempts=MAX_ATTEMPTS
    )
    assert lease is not None
    return lease


def _run(db_url: str, lease: task_leases.Lease, storage: FileStorage, **kwargs):
    return run_parse_stage(db_url, lease, storage=storage, max_attempts=MAX_ATTEMPTS, **kwargs)


def _row(db_url: str, task_id: str) -> dict[str, object]:
    (row,) = _sql(
        db_url,
        """SELECT stage, progress, cancel_requested, error_code, error_message, error_details,
                  lease_owner, lease_token, lease_expires_at, attempt, not_before
           FROM processing_tasks WHERE id = ?""",
        task_id,
    )
    keys = (
        "stage progress cancel_requested error_code error_message error_details "
        "lease_owner lease_token lease_expires_at attempt not_before"
    ).split()
    return dict(zip(keys, row))


def _chunk_count(db_url: str) -> int:
    return _sql(db_url, "SELECT count(*) FROM chunks")[0][0]


def _revision_count(db_url: str) -> int:
    return _sql(db_url, "SELECT count(*) FROM material_revisions")[0][0]


def _expected_ids(material_id: str, data: bytes, parser_version: str, t: int = 1500, o: int = 200):
    """独立按 D09/D08 算出应有的块 ID（与实现无共享代码路径之外的状态）。"""
    doc = parse_task.parse_document(_fmt_of(parser_version), data)
    chunks = chunk_blocks(doc.blocks, target_chars=t, overlap_chars=o)
    key = RevisionKey(
        document_id=material_id,
        content_hash="sha256:" + hashlib.sha256(data).hexdigest(),
        parser_version=revision_parser_version(parser_version, chunking_version(t, o)),
    )
    return tuple(identity.chunk_id for identity in assign_chunk_identities(COURSE, key, chunks))


def _fmt_of(parser_version: str) -> str:
    return {"txt": "txt", "markdown": "markdown", "docx": "docx", "pdf": "pdf"}[parser_version.split("/")[0]]


def _takeover(db_url: str, task_id: str) -> task_leases.Lease:
    """让当前租约过期并由另一 worker 接管（LEASE-4）。"""
    _sql(db_url, "UPDATE processing_tasks SET lease_expires_at = unixepoch() - 1 WHERE id = ?", task_id)
    lease = task_leases.claim_next(
        db_url, owner="worker-b", lease_seconds=LEASE_SECONDS, max_attempts=MAX_ATTEMPTS
    )
    assert lease is not None and lease.task_id == task_id
    return lease


def _assert_state_accepted_by_c08(row: dict[str, object]) -> None:
    """落库的失败必须是 C08 纯函数可接受的 T9 结果（I4、失败码与阶段匹配）。"""
    details = json.loads(row["error_details"]) if row["error_details"] else None
    event = TransitionEvent("fail", error=TaskError(row["error_code"], row["error_message"], details))
    assert isinstance(apply_event(TaskState("parsing", 0.05), event), Applied)


# --- 成功路径 ------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("fmt", "data", "parser_version"),
    [
        ("txt", TXT, "txt/1"),
        ("markdown", MARKDOWN, "markdown/1"),
        ("docx", DOCX, "docx/1"),
        ("pdf", PDF, parse_task.PDF_PARSER_VERSION),
    ],
)
def test_each_format_reaches_extracting_with_chunks_persisted(db_url, storage, fmt, data, parser_version):
    material_id, task_id = _add_material(db_url, storage, data, fmt)
    lease = _claim(db_url)

    outcome = _run(db_url, lease, storage)

    assert outcome.status is ParseStatus.ADVANCED
    assert outcome.stage == "extracting" and outcome.sse_event == "stage"
    row = _row(db_url, task_id)
    assert row["stage"] == "extracting"
    assert row["progress"] == pytest.approx(0.10)
    assert row["error_code"] is None
    assert row["lease_token"] == lease.token  # 仍持有租约，交给下一阶段
    stored = store.list_chunks(db_url, course_id=COURSE, material_id=material_id)
    assert stored and tuple(c.chunk_id for c in stored) == outcome.chunk_ids
    assert outcome.chunk_ids == _expected_ids(material_id, data, parser_version)
    (revision,) = store.list_task_revisions(db_url, course_id=COURSE, task_id=task_id)
    assert revision.revision_id == outcome.revision_id
    assert revision.parser_version == revision_parser_version(parser_version, chunking_version())
    assert revision.content_hash == "sha256:" + hashlib.sha256(data).hexdigest()
    for chunk in stored:
        for source in chunk.sources:
            if fmt == "pdf":
                assert source.locator.page in (1, 2)
            else:
                assert source.locator.page is None and source.locator.paragraph is not None


def test_pdf_parser_version_has_no_plus_and_names_the_pipeline():
    assert "+" not in parse_task.PDF_PARSER_VERSION
    assert parse_task.PDF_PARSER_VERSION == "pdf/1,cleanup/1,headings/1"
    # ADR-018 修订 1：取 D06 常量，不在 worker 里另拼字符串。
    assert parse_task.PDF_PARSER_VERSION is pdf_headings.CLEANED_PARSER_VERSION


def test_chunk_parameters_enter_the_revision_key(db_url, storage):
    material_id, task_id = _add_material(db_url, storage, TXT, "txt")
    outcome = _run(db_url, _claim(db_url), storage, target_chars=40, overlap_chars=10)

    assert outcome.status is ParseStatus.ADVANCED
    (revision,) = store.list_task_revisions(db_url, course_id=COURSE, task_id=task_id)
    assert revision.parser_version == "txt/1+chunk/1@40-10"
    assert len(outcome.chunk_ids) > 1
    assert outcome.chunk_ids == _expected_ids(material_id, TXT, "txt/1", 40, 10)


def test_mid_stage_progress_is_reported_before_the_checkpoint(db_url, storage, monkeypatch):
    _, task_id = _add_material(db_url, storage, TXT, "txt")
    lease = _claim(db_url)
    seen: list[float] = []
    real_put = parse_task.put_chunks

    def spying_put(database, **kwargs):
        seen.append(database.execute("SELECT progress FROM processing_tasks WHERE id = ?", (task_id,)).fetchone()[0])
        return real_put(database, **kwargs)

    monkeypatch.setattr(parse_task, "put_chunks", spying_put)
    assert _run(db_url, lease, storage).status is ParseStatus.ADVANCED
    assert seen == [pytest.approx(parse_task.PARSED_PROGRESS)]


# --- 边界：重跑、取消、进度、租约心跳 ----------------------------------------------------------


def test_crash_before_commit_leaves_nothing_and_takeover_rerun_yields_same_ids(db_url, storage, monkeypatch):
    material_id, task_id = _add_material(db_url, storage, TXT, "txt")
    lease = _claim(db_url)
    real_put = parse_task.put_chunks

    def crash_after_put(database, **kwargs):
        real_put(database, **kwargs)
        raise _Crash()

    monkeypatch.setattr(parse_task, "put_chunks", crash_after_put)
    with pytest.raises(_Crash):
        _run(db_url, lease, storage)
    assert _chunk_count(db_url) == 0 and _revision_count(db_url) == 0
    assert _row(db_url, task_id)["stage"] == "parsing"

    monkeypatch.setattr(parse_task, "put_chunks", real_put)
    second = _takeover(db_url, task_id)
    assert second.attempt == 2 and second.stage == "parsing"
    outcome = _run(db_url, second, storage)
    assert outcome.status is ParseStatus.ADVANCED
    assert outcome.chunk_ids == _expected_ids(material_id, TXT, "txt/1")


def test_rerun_over_existing_chunks_creates_no_new_chunks(db_url, storage):
    material_id, task_id = _add_material(db_url, storage, TXT, "txt")
    lease = _claim(db_url)
    # 先前尝试已按同一修订写入全部块（例如分事务写入后崩溃）。
    doc = parse_task.parse_document("txt", TXT)
    chunks = chunk_blocks(doc.blocks)
    key = RevisionKey(material_id, "sha256:" + hashlib.sha256(TXT).hexdigest(),
                      revision_parser_version("txt/1", chunking_version()))
    store.persist_revision_chunks(db_url, course_id=COURSE, task_id=task_id, key=key, chunks=chunks)
    before = _sql(db_url, "SELECT chunk_id, created_at FROM chunks ORDER BY chunk_id")

    outcome = _run(db_url, lease, storage)

    assert outcome.status is ParseStatus.ADVANCED
    assert outcome.chunks_inserted == 0
    assert _sql(db_url, "SELECT chunk_id, created_at FROM chunks ORDER BY chunk_id") == before
    assert tuple(sorted(outcome.chunk_ids)) == tuple(row[0] for row in before)


def test_second_task_on_same_material_shares_chunks(db_url, storage):
    material_id, first = _add_material(db_url, storage, TXT, "txt")
    outcome = _run(db_url, _claim(db_url), storage)
    count = _chunk_count(db_url)
    second = f"task{secrets.token_hex(14)}"
    _sql(
        db_url,
        "INSERT INTO processing_tasks (id, course_id, document_id, idempotency_key) VALUES (?, ?, ?, ?)",
        second, COURSE, material_id, "second",
    )
    lease = _claim(db_url, owner="worker-b")
    assert lease.task_id == second

    again = _run(db_url, lease, storage)

    assert again.status is ParseStatus.ADVANCED
    assert again.chunk_ids == outcome.chunk_ids and again.chunks_inserted == 0
    assert _chunk_count(db_url) == count
    assert {r.revision_id for r in store.list_task_revisions(db_url, course_id=COURSE, task_id=second)} == {
        outcome.revision_id
    }


def test_cancel_before_the_stage_starts_cancels_without_parsing(db_url, storage, monkeypatch):
    _, task_id = _add_material(db_url, storage, TXT, "txt")
    lease = _claim(db_url)
    cancel_task(db_url, task_id, course_id=COURSE)

    def must_not_parse(*args, **kwargs):
        raise AssertionError("parser must not run after cancel was requested")

    monkeypatch.setattr(parse_task, "parse_document", must_not_parse)
    outcome = _run(db_url, lease, storage)

    assert outcome.status is ParseStatus.CANCELLED
    assert outcome.stage == "cancelled" and outcome.sse_event == "cancelled"
    row = _row(db_url, task_id)
    assert row["stage"] == "cancelled" and row["cancel_requested"] == 1
    assert row["lease_token"] is None and row["lease_owner"] is None and row["lease_expires_at"] is None
    assert _chunk_count(db_url) == 0


def test_cancel_during_parsing_takes_effect_at_the_checkpoint(db_url, storage, monkeypatch):
    _, task_id = _add_material(db_url, storage, TXT, "txt")
    lease = _claim(db_url)
    real_parse = parse_task.parse_document

    def parse_then_cancel(fmt, data):
        document = real_parse(fmt, data)
        cancel_task(db_url, task_id, course_id=COURSE)
        return document

    monkeypatch.setattr(parse_task, "parse_document", parse_then_cancel)
    outcome = _run(db_url, lease, storage)

    assert outcome.status is ParseStatus.CANCELLED and outcome.sse_event == "cancelled"
    row = _row(db_url, task_id)
    assert row["stage"] == "cancelled" and row["lease_token"] is None
    assert row["progress"] == pytest.approx(parse_task.PARSED_PROGRESS)  # 保持取消时的值
    assert _chunk_count(db_url) == 0 and _revision_count(db_url) == 0


def test_low_progress_report_is_rejected_and_high_one_applied(db_url, storage):
    _, task_id = _add_material(db_url, storage, TXT, "txt")
    lease = _claim(db_url)
    _sql(db_url, "UPDATE processing_tasks SET progress = 0.08 WHERE id = ?", task_id)

    assert report_progress(db_url, lease, 0.05) is False
    assert _row(db_url, task_id)["progress"] == pytest.approx(0.08)
    assert report_progress(db_url, lease, 0.09) is True
    assert _row(db_url, task_id)["progress"] == pytest.approx(0.09)
    assert report_progress(db_url, lease, 0.5) is False  # 超出 parsing 区间
    assert _row(db_url, task_id)["progress"] == pytest.approx(0.09)


def test_takeover_with_higher_progress_never_regresses(db_url, storage, monkeypatch):
    _, task_id = _add_material(db_url, storage, TXT, "txt")
    lease = _claim(db_url)
    _sql(db_url, "UPDATE processing_tasks SET progress = 0.08 WHERE id = ?", task_id)
    seen: list[float] = []
    real_put = parse_task.put_chunks

    def spying_put(database, **kwargs):
        seen.append(database.execute("SELECT progress FROM processing_tasks WHERE id = ?", (task_id,)).fetchone()[0])
        return real_put(database, **kwargs)

    monkeypatch.setattr(parse_task, "put_chunks", spying_put)
    assert _run(db_url, lease, storage).status is ParseStatus.ADVANCED
    assert seen == [pytest.approx(0.08)]  # 0.05 的上报未生效
    assert _row(db_url, task_id)["progress"] == pytest.approx(0.10)


def test_report_progress_after_lease_loss_raises_and_writes_nothing(db_url, storage):
    _, task_id = _add_material(db_url, storage, TXT, "txt")
    lease = _claim(db_url)
    _takeover(db_url, task_id)
    with pytest.raises(task_leases.LeaseLost):
        report_progress(db_url, lease, 0.05)
    assert _row(db_url, task_id)["progress"] == 0


def test_heartbeat_renews_and_detects_a_lost_lease(db_url, storage):
    _, task_id = _add_material(db_url, storage, TXT, "txt")
    lease = _claim(db_url)
    _sql(db_url, "UPDATE processing_tasks SET lease_expires_at = unixepoch() + 1 WHERE id = ?", task_id)

    with LeaseHeartbeat(db_url, lease, lease_seconds=LEASE_SECONDS, interval=0.02) as beat:
        deadline = time.monotonic() + 5
        while beat.renewals == 0 and time.monotonic() < deadline:
            time.sleep(0.01)
        assert beat.renewals >= 1 and not beat.lost.is_set()
        now = _sql(db_url, "SELECT unixepoch()")[0][0]
        assert _row(db_url, task_id)["lease_expires_at"] >= now + LEASE_SECONDS - 2

        _sql(db_url, "UPDATE processing_tasks SET lease_token = ? WHERE id = ?", "f" * 32, task_id)
        assert beat.lost.wait(5)
    assert beat.lost.is_set()


def test_heartbeat_interval_defaults_to_a_third_of_the_lease(db_url, storage):
    _add_material(db_url, storage, TXT, "txt")
    beat = LeaseHeartbeat(db_url, _claim(db_url), lease_seconds=60)
    assert beat.interval == pytest.approx(20)


# --- 失败路径 ------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("fmt", "data", "reason"),
    [
        ("txt", b"\xff\xfe\x00broken" * 3 + b"\x80\x81", "corrupted"),
        ("docx", b"PK\x03\x04 this is not a zip archive", "corrupted"),
        ("pdf", b"%PDF-1.4\nnot really a pdf\n", "corrupted"),
        ("pdf", _pdf([["Secret lecture notes"]], encrypted=True), "encrypted"),
        ("docx", ENCRYPTED_DOCX, "encrypted"),
        ("txt", b"   \n\t\n  \n", "no_text"),
        ("markdown", b"\n\n   \n", "no_text"),
        ("pdf", _pdf([[]]), "no_text"),
    ],
)
def test_unreadable_documents_fail_without_retry(db_url, storage, fmt, data, reason):
    _, task_id = _add_material(db_url, storage, data, fmt)
    lease = _claim(db_url)

    outcome = _run(db_url, lease, storage)

    assert outcome.status is ParseStatus.FAILED
    assert outcome.stage == "failed" and outcome.sse_event == "error"
    assert outcome.error_code == "DOCUMENT_UNREADABLE"
    row = _row(db_url, task_id)
    assert row["stage"] == "failed" and row["error_code"] == "DOCUMENT_UNREADABLE"
    assert json.loads(row["error_details"]) == {"reason": reason}
    assert row["lease_token"] is None and row["lease_expires_at"] is None
    assert row["attempt"] == 1
    _assert_state_accepted_by_c08(row)
    assert _chunk_count(db_url) == 0 and _revision_count(db_url) == 0
    # 不重试：失败任务不再可领取，也不会被回收成别的状态。
    assert task_leases.claim_next(db_url, owner="w", lease_seconds=60, max_attempts=3) is None
    task_leases.reclaim_expired(db_url, max_attempts=MAX_ATTEMPTS)
    assert _row(db_url, task_id)["error_code"] == "DOCUMENT_UNREADABLE"


def test_zero_chunks_after_parsing_is_no_text(db_url, storage, monkeypatch):
    _, task_id = _add_material(db_url, storage, TXT, "txt")
    monkeypatch.setattr(parse_task, "chunk_blocks", lambda blocks, **kwargs: ())
    outcome = _run(db_url, _claim(db_url), storage)

    assert outcome.status is ParseStatus.FAILED and outcome.error_code == "DOCUMENT_UNREADABLE"
    assert json.loads(_row(db_url, task_id)["error_details"]) == {"reason": "no_text"}


def test_missing_file_releases_with_backoff(db_url, storage):
    _, task_id = _add_material(db_url, storage, TXT, "txt")
    lease = _claim(db_url)
    storage_name = _sql(db_url, "SELECT storage_name FROM materials")[0][0]
    storage.path_for(storage_name).unlink()

    outcome = _run(db_url, lease, storage)

    assert outcome.status is ParseStatus.RELEASED
    assert outcome.stage == "parsing" and outcome.sse_event is None
    row = _row(db_url, task_id)
    now = _sql(db_url, "SELECT unixepoch()")[0][0]
    assert row["stage"] == "parsing" and row["error_code"] is None
    assert row["lease_token"] is None and row["attempt"] == 1
    assert now + 25 <= row["not_before"] <= now + 31
    assert outcome.not_before == row["not_before"]


def test_storage_fault_on_the_last_attempt_fails_with_attempts_and_stage(db_url, storage):
    _, task_id = _add_material(db_url, storage, TXT, "txt")
    _sql(db_url, "UPDATE processing_tasks SET attempt = 2 WHERE id = ?", task_id)
    lease = _claim(db_url)
    assert lease.attempt == 3
    storage_name = _sql(db_url, "SELECT storage_name FROM materials")[0][0]
    storage.path_for(storage_name).unlink()

    outcome = _run(db_url, lease, storage)

    assert outcome.status is ParseStatus.FAILED and outcome.sse_event == "error"
    assert outcome.error_code == "STORAGE_UNAVAILABLE"
    row = _row(db_url, task_id)
    assert row["stage"] == "failed" and row["error_code"] == "STORAGE_UNAVAILABLE"
    assert json.loads(row["error_details"]) == {"attempts": 3, "stage": "parsing"}
    _assert_state_accepted_by_c08(row)


def test_sqlite_write_fault_rolls_back_and_releases(db_url, storage, monkeypatch):
    _, task_id = _add_material(db_url, storage, TXT, "txt")
    lease = _claim(db_url)
    real_put = parse_task.put_chunks

    def put_then_fail(database, **kwargs):
        real_put(database, **kwargs)
        raise sqlite3.OperationalError("disk I/O error")

    monkeypatch.setattr(parse_task, "put_chunks", put_then_fail)
    outcome = _run(db_url, lease, storage)

    assert outcome.status is ParseStatus.RELEASED
    assert _chunk_count(db_url) == 0 and _revision_count(db_url) == 0
    row = _row(db_url, task_id)
    assert row["stage"] == "parsing" and row["lease_token"] is None


def test_unexpected_error_is_internal_error_without_original_text(db_url, storage, monkeypatch):
    _, task_id = _add_material(db_url, storage, TXT, "txt")

    def boom(fmt, data):
        raise RuntimeError(f"parser exploded on: {SECRET_TEXT}")

    monkeypatch.setattr(parse_task, "parse_document", boom)
    outcome = _run(db_url, _claim(db_url), storage)

    assert outcome.status is ParseStatus.FAILED and outcome.error_code == "INTERNAL_ERROR"
    row = _row(db_url, task_id)
    assert row["stage"] == "failed" and row["error_code"] == "INTERNAL_ERROR"
    persisted = f"{row['error_message']} {row['error_details']}"
    assert SECRET_TEXT not in persisted and "Traceback" not in persisted and "RuntimeError" not in persisted
    assert row["lease_token"] is None
    _assert_state_accepted_by_c08(row)


def test_existing_chunk_id_with_different_text_is_rejected(db_url, storage):
    material_id, task_id = _add_material(db_url, storage, TXT, "txt")
    lease = _claim(db_url)
    doc = parse_task.parse_document("txt", TXT)
    real = chunk_blocks(doc.blocks)
    forged = (dataclasses.replace(real[0], text="被篡改的块文本"),) + real[1:]
    key = RevisionKey(material_id, "sha256:" + hashlib.sha256(TXT).hexdigest(),
                      revision_parser_version("txt/1", chunking_version()))
    store.persist_revision_chunks(db_url, course_id=COURSE, task_id=task_id, key=key, chunks=forged)
    before = _sql(db_url, "SELECT chunk_id, text_sha256 FROM chunks ORDER BY chunk_id")

    outcome = _run(db_url, lease, storage)

    assert outcome.status is ParseStatus.FAILED and outcome.error_code == "INTERNAL_ERROR"
    assert _sql(db_url, "SELECT chunk_id, text_sha256 FROM chunks ORDER BY chunk_id") == before
    assert _row(db_url, task_id)["stage"] == "failed"


def test_stale_lease_stops_before_any_write(db_url, storage):
    _, task_id = _add_material(db_url, storage, TXT, "txt")
    old = _claim(db_url)
    new = _takeover(db_url, task_id)

    outcome = _run(db_url, old, storage)

    assert outcome.status is ParseStatus.LOST and outcome.stage is None and outcome.sse_event is None
    row = _row(db_url, task_id)
    assert row["stage"] == "parsing" and row["lease_token"] == new.token and row["progress"] == 0
    assert _chunk_count(db_url) == 0


def test_lease_stolen_mid_parse_writes_no_chunks_and_no_t4(db_url, storage, monkeypatch):
    _, task_id = _add_material(db_url, storage, TXT, "txt")
    old = _claim(db_url)
    real_parse = parse_task.parse_document
    holder: dict[str, task_leases.Lease] = {}

    def parse_then_steal(fmt, data):
        document = real_parse(fmt, data)
        holder["new"] = _takeover(db_url, task_id)
        return document

    monkeypatch.setattr(parse_task, "parse_document", parse_then_steal)
    outcome = _run(db_url, old, storage)

    assert outcome.status is ParseStatus.LOST
    row = _row(db_url, task_id)
    assert row["stage"] == "parsing" and row["lease_token"] == holder["new"].token
    assert row["progress"] == 0  # 旧 worker 的进度上报也未生效
    assert _chunk_count(db_url) == 0 and _revision_count(db_url) == 0


def test_lease_stolen_right_before_the_checkpoint_writes_nothing(db_url, storage, monkeypatch):
    """进度已上报、检查点事务开始前被接管：块、修订与 T4 都不得写入（LEASE-4）。"""
    _, task_id = _add_material(db_url, storage, TXT, "txt")
    old = _claim(db_url)
    real_report = parse_task.report_progress
    holder: dict[str, task_leases.Lease] = {}

    def report_then_steal(url, lease, progress):
        written = real_report(url, lease, progress)
        holder["new"] = _takeover(db_url, task_id)
        return written

    monkeypatch.setattr(parse_task, "report_progress", report_then_steal)
    outcome = _run(db_url, old, storage)

    assert outcome.status is ParseStatus.LOST and outcome.sse_event is None
    row = _row(db_url, task_id)
    assert row["stage"] == "parsing" and row["lease_token"] == holder["new"].token
    assert row["progress"] == pytest.approx(parse_task.PARSED_PROGRESS)
    assert _chunk_count(db_url) == 0 and _revision_count(db_url) == 0


def test_lease_stolen_before_failure_write_writes_no_failure(db_url, storage, monkeypatch):
    _, task_id = _add_material(db_url, storage, b"   \n", "txt")
    old = _claim(db_url)
    real_parse = parse_task.parse_document

    def steal_then_parse(fmt, data):
        _takeover(db_url, task_id)
        return real_parse(fmt, data)

    monkeypatch.setattr(parse_task, "parse_document", steal_then_parse)
    outcome = _run(db_url, old, storage)

    assert outcome.status is ParseStatus.LOST
    row = _row(db_url, task_id)
    assert row["stage"] == "parsing" and row["error_code"] is None and row["lease_token"] is not None


def test_lease_stolen_before_storage_release_changes_nothing(db_url, storage, monkeypatch):
    _, task_id = _add_material(db_url, storage, TXT, "txt")
    old = _claim(db_url)
    storage_name = _sql(db_url, "SELECT storage_name FROM materials")[0][0]
    storage.path_for(storage_name).unlink()
    new = _takeover(db_url, task_id)
    before = _row(db_url, task_id)
    # 读行检查在读文件之前；让接管发生在读行之后，覆盖「释放时才发现租约已丢」。
    real_read = parse_task._read_leased_task
    calls = {"n": 0}

    def read_then_pretend_old_owner(url, lease):
        calls["n"] += 1
        return real_read(url, dataclasses.replace(lease, token=new.token))

    monkeypatch.setattr(parse_task, "_read_leased_task", read_then_pretend_old_owner)
    outcome = _run(db_url, old, storage)

    assert calls["n"] >= 1
    assert outcome.status is ParseStatus.LOST
    assert _row(db_url, task_id) == before


def test_course_isolation(db_url, storage):
    material_a, task_a = _add_material(db_url, storage, TXT, "txt", course=COURSE)
    material_b, task_b = _add_material(db_url, storage, MARKDOWN, "markdown", course=OTHER)
    lease = _claim(db_url)
    assert lease.task_id == task_a

    # 伪造课程的租约：拒绝且不写任何数据。
    forged = dataclasses.replace(lease, course_id=OTHER, document_id=material_b)
    with pytest.raises(ValueError):
        _run(db_url, forged, storage)
    assert _row(db_url, task_a)["stage"] == "parsing" and _chunk_count(db_url) == 0

    assert _run(db_url, lease, storage).status is ParseStatus.ADVANCED
    assert store.list_chunks(db_url, course_id=OTHER, material_id=material_a) == ()
    assert store.list_chunks(db_url, course_id=OTHER, material_id=material_b) == ()
    assert set(_sql(db_url, "SELECT DISTINCT course_id FROM chunks")) == {(COURSE,)}
    assert _row(db_url, task_b)["stage"] == "queued"


def test_lease_for_a_non_parsing_task_is_refused(db_url, storage):
    _, task_id = _add_material(db_url, storage, TXT, "txt")
    lease = _claim(db_url)
    assert _run(db_url, lease, storage).status is ParseStatus.ADVANCED
    with pytest.raises(ValueError):
        _run(db_url, dataclasses.replace(lease, stage="extracting"), storage)
    assert _row(db_url, task_id)["stage"] == "extracting"


# --- 运行一次入口 --------------------------------------------------------------------------------


def _settings(db_url: str, storage: FileStorage):
    return load_settings(
        {"SQLITE_URL": db_url, "STORAGE_DIR": str(storage.root), "TASK_LEASE_SECONDS": "15"}
    )


def test_run_once_parses_then_hands_the_task_back(db_url, storage):
    material_id, task_id = _add_material(db_url, storage, TXT, "txt")

    result = run_once(_settings(db_url, storage), owner="worker-a", storage=storage)

    assert result.lease is not None and result.lease.task_id == task_id
    assert result.outcome is not None and result.outcome.status is ParseStatus.ADVANCED
    assert result.handed_back is True
    row = _row(db_url, task_id)
    assert row["stage"] == "extracting" and row["lease_token"] is None and row["attempt"] == 0
    assert _chunk_count(db_url) == len(_expected_ids(material_id, TXT, "txt/1"))


def test_run_once_without_work_does_nothing(db_url, storage):
    result = run_once(_settings(db_url, storage), owner="worker-a", storage=storage)
    assert result.lease is None and result.outcome is None and result.handed_back is False


def test_run_once_hands_back_stages_it_does_not_handle(db_url, storage):
    _, task_id = _add_material(db_url, storage, TXT, "txt")
    _sql(db_url, "UPDATE processing_tasks SET stage = 'extracting', progress = 0.2, attempt = 1 WHERE id = ?", task_id)

    result = run_once(_settings(db_url, storage), owner="worker-a", storage=storage)

    assert result.lease is not None and result.outcome is None and result.handed_back is True
    row = _row(db_url, task_id)
    assert row["stage"] == "extracting" and row["lease_token"] is None and row["attempt"] == 1


def test_run_once_reclaims_before_claiming(db_url, storage):
    _, task_id = _add_material(db_url, storage, TXT, "txt")
    _claim(db_url)
    cancel_task(db_url, task_id, course_id=COURSE)
    _sql(db_url, "UPDATE processing_tasks SET lease_expires_at = unixepoch() - 1 WHERE id = ?", task_id)

    result = run_once(_settings(db_url, storage), owner="worker-b", storage=storage)

    assert [t.task_id for t in result.reclaimed.cancelled] == [task_id]
    assert result.lease is None
    assert _row(db_url, task_id)["stage"] == "cancelled"
