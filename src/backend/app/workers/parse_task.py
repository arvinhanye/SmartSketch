"""D11：``parsing`` 阶段的 worker 编排（specs/task-processing.md §2、§6、§8.2～§8.4；ADR-011、
ADR-012 修订 1、ADR-018；specs/teacher-review-publish.md V2）。

输入是 C09 ``claim_next`` 领到、处于 ``parsing`` 的任务（``Lease``）。``run_parse_stage``：

1. **阶段开头**：按租约令牌读任务行；令牌已失效即停止（``lost``），不做任何写入。课程或资料与租约不符、
   或任务不在 ``parsing`` 时抛 ``ValueError``（调用方缺陷），同样不写。取消标志已为真 → 直接 T8。
2. 按资料 ``storage_name`` 读 C05 已存文件 → 按 ``materials.format`` 选解析器（D02～D07；PDF 为
   「提取 → D07 清洗 → D06 标题判定」）→ D08 分块 → 资料修订 ``RevisionKey``（资料 ID + C05 内容哈希 +
   D09 组合的复合解析器版本，ADR-018）。内容哈希直接取 ``materials.content_hash``，不重读重算
   （REVIEW-D01-R04）。解析完成后上报阶段内进度 ``PARSED_PROGRESS``（C08 ``progress``，低值不生效，I2）。
3. **检查点**：一个 C09 ``leased_transaction``（``BEGIN IMMEDIATE`` + 令牌 fence）内，按 C08
   ``stage_done`` 判定：取消标志为真 → T8（不写块）；否则 D10 ``record_revision`` + ``put_chunks``
   （按块 ID 插入或忽略，已存在 ID 的内容哈希不一致即拒绝）并执行带 ``lease_token`` 与
   ``cancel_requested = 0`` 条件的 T4 ``parsing → extracting``。块与转换同一事务，未提交即全无，
   因此接管后从阶段开头重跑只会得到同一批块 ID（§8.4 ``parsing`` 行）。

失败（§6、§8.3），写入同样带令牌条件并清空租约：

- ``DocumentUnreadableError`` 或分块后 0 块 → T9 ``DOCUMENT_UNREADABLE``，``details = {reason}``，不重试。
- 存储不可用（读文件 ``OSError``、SQLite ``OperationalError``）→ C09 ``release_after_transient_failure``：
  退避释放；最后一次尝试改为 T9 ``STORAGE_UNAVAILABLE``，``details = {attempts, stage}``。
- 其他异常（含 D10 ``ChunkImmutableError``、解析器 ``ParseModelError``）→ T9 ``INTERNAL_ERROR``，
  ``details`` 为空；消息固定，不含堆栈、异常文本或原文；日志只记异常类型名。
- 任一写入遇到 ``LeaseLost``（令牌不再匹配）→ 事务回滚，返回 ``lost``，此后不再写任何数据。

本阶段不写 Neo4j，也不写文件，因此 §8.2「本地截止」规则在此无适用写入；心跳由 ``LeaseHeartbeat``
提供。推送 SSE 事件归 C11：``ParseOutcome.sse_event`` 指明本次写入对应的事件（``stage`` /
``cancelled`` / ``error``，无状态变化为 ``None``）。``run_once`` 是最小的「运行一次」入口，不是守护进程。
"""

from __future__ import annotations

import json
import logging
import os
import secrets
import socket
import sqlite3
import threading
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum

from app.config import Settings
from app.repositories.chunks import put_chunks, record_revision
from app.repositories.materials import get_material
from app.repositories.sqlite import connect
from app.repositories.task_leases import (
    Lease,
    LeaseLost,
    ReclaimResult,
    claim_next,
    leased_transaction,
    reclaim_expired,
    release_after_transient_failure,
    release_on_shutdown,
    renew_lease,
)
from app.services.chunk_identity import derive_chunk_id, revision_parser_version
from app.services.chunking import (
    DEFAULT_OVERLAP_CHARS,
    DEFAULT_TARGET_CHARS,
    SemanticChunk,
    chunk_blocks,
    chunking_version,
)
from app.services.file_storage import FileStorage
from app.services.parsers import cleanup, docx, markdown, pdf, pdf_headings, txt
from app.services.parsers.models import (
    DocumentUnreadableError,
    ParsedDocument,
    RevisionKey,
    UnreadableReason,
)
from app.services.task_state import Applied, TaskError, TaskState, TransitionEvent, apply_event

__all__ = [
    "PARSED_PROGRESS",
    "PDF_PARSER_VERSION",
    "LeaseHeartbeat",
    "ParseOutcome",
    "ParseStatus",
    "RunOnceResult",
    "default_owner",
    "parse_document",
    "report_progress",
    "run_once",
    "run_parse_stage",
]

logger = logging.getLogger(__name__)

STAGE = "parsing"
NEXT_STAGE = "extracting"
#: 解析与分块完成、写检查点之前上报的阶段内进度（``parsing`` 区间为 [0, 0.10]）。
PARSED_PROGRESS = 0.05
#: PDF 管线（D05 提取 → D07 清洗 → D06 标题判定）的解析器段版本，取 D06 给出的常量
#: （ADR-018 修订 1：``pdf/1,cleanup/1,headings/1``），任一段变化即新修订、新块 ID。
#: 清洗只用 D07 默认阈值（阈值变化须递增 ``CLEANUP_VERSION``）。
PDF_PARSER_VERSION = pdf_headings.CLEANED_PARSER_VERSION

_NOW_TEXT = "strftime('%Y-%m-%dT%H:%M:%fZ', 'now')"
_UNREADABLE_MESSAGES = {
    UnreadableReason.CORRUPTED: "资料文件已损坏，无法解析",
    UnreadableReason.ENCRYPTED: "资料已加密，无法解析，请上传未加密的版本",
    UnreadableReason.NO_TEXT: "资料中没有可提取的文本",
}
_INTERNAL_MESSAGE = "解析阶段发生未预期的错误"


class ParseStatus(StrEnum):
    ADVANCED = "advanced"  # T4：块已持久化，任务到 extracting，仍持有租约
    CANCELLED = "cancelled"  # T8：检查点发现取消标志
    FAILED = "failed"  # T9：DOCUMENT_UNREADABLE / STORAGE_UNAVAILABLE（耗尽）/ INTERNAL_ERROR
    RELEASED = "released"  # 存储临时故障，已主动释放并退避，stage 不变
    LOST = "lost"  # 令牌已失效：本 worker 未做任何写入，必须放手


@dataclass(frozen=True)
class ParseOutcome:
    status: ParseStatus
    task_id: str
    stage: str | None
    sse_event: str | None
    revision_id: str | None = None
    chunk_ids: tuple[str, ...] = ()
    chunks_inserted: int = 0
    error_code: str | None = None
    not_before: int | None = None


@dataclass(frozen=True)
class _LeasedRow:
    course_id: str
    document_id: str
    state: TaskState


class _StorageFault(Exception):
    """已存文件读不到（存储不可用），属于阶段级临时故障（§8.3）。"""


# ---------------------------------------------------------------- 解析器分派


def _parse_pdf(data: bytes) -> ParsedDocument:
    extraction = pdf.extract_pdf(data)
    cleaned = cleanup.clean_pages(extraction)
    return pdf_headings.to_sectioned_document(cleaned.lines, parser_version=PDF_PARSER_VERSION)


_PARSERS: Mapping[str, Callable[[bytes], ParsedDocument]] = {
    "txt": txt.parse_txt,
    "markdown": markdown.parse_markdown,
    "docx": docx.parse_docx,
    "pdf": _parse_pdf,
}


def parse_document(source_format: str, data: bytes) -> ParsedDocument:
    """按 ``materials.format`` 选择解析器；无法解析时抛 ``DocumentUnreadableError``。"""
    parser = _PARSERS.get(source_format)
    if parser is None:
        raise ValueError(f"unsupported material format: {source_format!r}")
    return parser(data)


def _read_bytes(storage: FileStorage, storage_name: str) -> bytes:
    path = storage.path_for(storage_name)  # 非本服务生成的存储名 → ValueError（数据缺陷）
    try:
        return path.read_bytes()
    except OSError as exc:
        raise _StorageFault(type(exc).__name__) from exc


# ---------------------------------------------------------------- 带令牌的读写


def _leased_row(database: sqlite3.Connection, lease: Lease) -> _LeasedRow | None:
    row = database.execute(
        """SELECT course_id, document_id, stage, progress, cancel_requested
           FROM processing_tasks WHERE id = ? AND lease_token = ?""",
        (lease.task_id, lease.token),
    ).fetchone()
    if row is None:
        return None
    return _LeasedRow(row[0], row[1], TaskState(row[2], float(row[3]), bool(row[4])))


def _read_leased_task(sqlite_url: str, lease: Lease) -> _LeasedRow | None:
    """按令牌读任务行；``None`` 表示租约已不属于本 worker。"""
    with connect(sqlite_url) as database:
        return _leased_row(database, lease)


def _state_in(database: sqlite3.Connection, lease: Lease) -> TaskState:
    row = _leased_row(database, lease)
    if row is None:  # fence 已在同一事务里确认令牌；走到这里说明调用顺序有误
        raise LeaseLost(f"lease on task {lease.task_id} is no longer held by this token")
    return row.state


def report_progress(sqlite_url: str, lease: Lease, progress: float) -> bool:
    """阶段内进度上报（C08 ``progress`` 事件）：低于当前值或超出阶段区间时不写，返回 ``False``。

    写入带令牌条件；令牌失效抛 ``LeaseLost``，不写任何数据。
    """
    with leased_transaction(sqlite_url, lease.task_id, lease.token) as database:
        state = _state_in(database, lease)
        decision = apply_event(state, TransitionEvent("progress", progress=progress))
        if not isinstance(decision, Applied) or not decision.changed:
            return False
        return database.execute(
            f"""UPDATE processing_tasks SET progress = ?, updated_at = {_NOW_TEXT}
                WHERE id = ? AND lease_token = ? AND stage = ? AND progress <= ?""",
            (decision.state.progress, lease.task_id, lease.token, state.stage, decision.state.progress),
        ).rowcount == 1


def _write_cancelled(database: sqlite3.Connection, lease: Lease) -> None:
    """T8：带令牌与取消标志条件，同时清空租约。"""
    changed = database.execute(
        f"""UPDATE processing_tasks
            SET stage = 'cancelled', lease_owner = NULL, lease_token = NULL,
                lease_expires_at = NULL, updated_at = {_NOW_TEXT}
            WHERE id = ? AND lease_token = ? AND stage = ? AND cancel_requested = 1""",
        (lease.task_id, lease.token, STAGE),
    ).rowcount
    if changed != 1:
        raise RuntimeError(f"T8 compare-and-swap on task {lease.task_id} matched no row")


def _write_advanced(database: sqlite3.Connection, lease: Lease, progress: float) -> None:
    """T4 ``parsing → extracting``：带令牌与 ``cancel_requested = 0`` 条件；租约继续持有。"""
    changed = database.execute(
        f"""UPDATE processing_tasks SET stage = ?, progress = ?, updated_at = {_NOW_TEXT}
            WHERE id = ? AND lease_token = ? AND stage = ? AND cancel_requested = 0""",
        (NEXT_STAGE, progress, lease.task_id, lease.token, STAGE),
    ).rowcount
    if changed != 1:
        raise RuntimeError(f"T4 compare-and-swap on task {lease.task_id} matched no row")


def _checkpoint(
    sqlite_url: str,
    lease: Lease,
    key: RevisionKey | None,
    chunks: Sequence[SemanticChunk] | None,
) -> ParseOutcome:
    """阶段边界：取消 → T8；否则持久化修订与块并 T4。全部在一个带令牌的事务内。"""
    event = "checkpoint" if key is None else "stage_done"
    with leased_transaction(sqlite_url, lease.task_id, lease.token) as database:
        decision = apply_event(_state_in(database, lease), TransitionEvent(event))
        if not isinstance(decision, Applied):
            raise RuntimeError(f"{event} rejected for task {lease.task_id}: {decision.reason}")
        if decision.state.stage == "cancelled":
            _write_cancelled(database, lease)
            return ParseOutcome(ParseStatus.CANCELLED, lease.task_id, "cancelled", "cancelled")
        if key is None or chunks is None:  # 取消标志只会由假变真（I5），开头读到为真这里必为真
            raise RuntimeError(f"task {lease.task_id} lost its cancel flag")
        revision = record_revision(database, course_id=lease.course_id, task_id=lease.task_id, key=key)
        written = put_chunks(
            database, course_id=lease.course_id, revision_id=revision.revision_id, chunks=chunks
        )
        _write_advanced(database, lease, decision.state.progress)
    return ParseOutcome(
        ParseStatus.ADVANCED,
        lease.task_id,
        NEXT_STAGE,
        "stage",
        revision_id=revision.revision_id,
        chunk_ids=tuple(derive_chunk_id(revision.revision_id, index) for index in range(len(chunks))),
        chunks_inserted=len(written.inserted),
    )


def _fail(
    sqlite_url: str, lease: Lease, code: str, message: str, details: Mapping[str, object] | None
) -> ParseOutcome:
    """T9：C08 ``fail`` 判定后带令牌写入并清空租约；令牌失效时返回 ``lost``。"""
    error = TaskError(code, message, details)
    encoded = None if details is None else json.dumps(dict(details), ensure_ascii=False, sort_keys=True)
    try:
        with leased_transaction(sqlite_url, lease.task_id, lease.token) as database:
            decision = apply_event(_state_in(database, lease), TransitionEvent("fail", error=error))
            if not isinstance(decision, Applied):
                raise RuntimeError(f"fail rejected for task {lease.task_id}: {decision.reason}")
            changed = database.execute(
                f"""UPDATE processing_tasks
                    SET stage = 'failed', error_code = ?, error_message = ?, error_details = ?,
                        lease_owner = NULL, lease_token = NULL, lease_expires_at = NULL,
                        updated_at = {_NOW_TEXT}
                    WHERE id = ? AND lease_token = ? AND stage = ?""",
                (code, message, encoded, lease.task_id, lease.token, STAGE),
            ).rowcount
            if changed != 1:
                raise LeaseLost(f"lease on task {lease.task_id} is no longer held by this token")
    except LeaseLost:
        return _lost(lease)
    return ParseOutcome(ParseStatus.FAILED, lease.task_id, "failed", "error", error_code=code)


def _release(sqlite_url: str, lease: Lease, max_attempts: int) -> ParseOutcome:
    """存储不可用：C09 主动释放（退避）；最后一次尝试由 C09 改为 T9 ``STORAGE_UNAVAILABLE``。"""
    code = "STORAGE_UNAVAILABLE"
    released = release_after_transient_failure(
        sqlite_url, lease.task_id, lease.token, code=code, max_attempts=max_attempts
    )
    if released.status == "released":
        return ParseOutcome(ParseStatus.RELEASED, lease.task_id, STAGE, None, not_before=released.not_before)
    if released.status == "failed":
        return ParseOutcome(ParseStatus.FAILED, lease.task_id, "failed", "error", error_code=code)
    return _lost(lease)


def _lost(lease: Lease) -> ParseOutcome:
    return ParseOutcome(ParseStatus.LOST, lease.task_id, None, None)


# ---------------------------------------------------------------- 阶段编排


def run_parse_stage(
    sqlite_url: str,
    lease: Lease,
    *,
    storage: FileStorage,
    max_attempts: int,
    target_chars: int = DEFAULT_TARGET_CHARS,
    overlap_chars: int = DEFAULT_OVERLAP_CHARS,
) -> ParseOutcome:
    """把一个已领取的 ``parsing`` 任务推进到阶段检查点（见模块说明）。"""
    chunking = chunking_version(target_chars, overlap_chars)  # 参数非法 → ValueError，未写任何数据
    head = _read_leased_task(sqlite_url, lease)
    if head is None:
        return _lost(lease)
    if (head.course_id, head.document_id) != (lease.course_id, lease.document_id):
        raise ValueError(f"lease does not match the course or material of task {lease.task_id}")
    if head.state.stage != STAGE or lease.stage != STAGE:
        raise ValueError(f"task {lease.task_id} is not in the parsing stage")

    try:
        if head.state.cancel_requested:
            return _checkpoint(sqlite_url, lease, None, None)
        material = get_material(sqlite_url, lease.document_id, course_id=lease.course_id)
        if material is None:
            raise RuntimeError(f"material of task {lease.task_id} is missing")
        document = parse_document(material.format, _read_bytes(storage, material.storage_name))
        chunks = chunk_blocks(document.blocks, target_chars=target_chars, overlap_chars=overlap_chars)
        if not chunks:
            raise DocumentUnreadableError(UnreadableReason.NO_TEXT, "分块后没有可用块")
        key = RevisionKey(
            document_id=material.id,
            content_hash=material.content_hash,
            parser_version=revision_parser_version(document.parser_version, chunking),
        )
        report_progress(sqlite_url, lease, PARSED_PROGRESS)
        return _checkpoint(sqlite_url, lease, key, chunks)
    except LeaseLost:
        return _lost(lease)
    except DocumentUnreadableError as exc:
        return _fail(
            sqlite_url,
            lease,
            "DOCUMENT_UNREADABLE",
            _UNREADABLE_MESSAGES[exc.reason],
            {"reason": exc.reason.value},
        )
    except (_StorageFault, sqlite3.OperationalError) as exc:
        logger.warning("parsing task %s: storage unavailable (%s)", lease.task_id, type(exc).__name__)
        return _release(sqlite_url, lease, max_attempts)
    except Exception as exc:  # noqa: BLE001 - 未预期错误一律 INTERNAL_ERROR，只记类型名
        logger.error("parsing task %s: unexpected %s", lease.task_id, type(exc).__name__)
        return _fail(sqlite_url, lease, "INTERNAL_ERROR", _INTERNAL_MESSAGE, None)


# ---------------------------------------------------------------- 心跳与运行一次


class LeaseHeartbeat:
    """持有租约期间每 ``interval``（默认 ``L/3``）续约一次（§8.2 续约）。

    续约影响 0 行即租约已丢，置 ``lost`` 并停止；SQLite 暂时不可用时下个周期重试。
    心跳只延长租约，不能代替写入时的令牌条件。
    """

    def __init__(
        self, sqlite_url: str, lease: Lease, *, lease_seconds: int, interval: float | None = None
    ) -> None:
        if isinstance(lease_seconds, bool) or not isinstance(lease_seconds, int) or lease_seconds < 1:
            raise ValueError("lease_seconds must be a positive integer")
        self.interval = lease_seconds / 3 if interval is None else interval
        if not self.interval > 0:
            raise ValueError("interval must be positive")
        self.lost = threading.Event()
        self.renewals = 0
        self._url = sqlite_url
        self._lease = lease
        self._lease_seconds = lease_seconds
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def __enter__(self) -> LeaseHeartbeat:
        self._thread = threading.Thread(
            target=self._run, name=f"lease-heartbeat-{self._lease.task_id}", daemon=True
        )
        self._thread.start()
        return self

    def __exit__(self, *exc_info: object) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join()

    def _run(self) -> None:
        while not self._stop.wait(self.interval):
            try:
                expires = renew_lease(
                    self._url, self._lease.task_id, self._lease.token, lease_seconds=self._lease_seconds
                )
            except sqlite3.Error:
                continue
            if expires is None:
                self.lost.set()
                return
            self.renewals += 1


@dataclass(frozen=True)
class RunOnceResult:
    reclaimed: ReclaimResult
    lease: Lease | None
    outcome: ParseOutcome | None
    handed_back: bool


def default_owner() -> str:
    """租约持有者标识（主机名、进程号、随机串），仅用于排查（§8.2）。"""
    return f"{socket.gethostname()}:{os.getpid()}:{secrets.token_hex(4)}"[:255]


def run_once(
    settings: Settings, *, owner: str | None = None, storage: FileStorage | None = None
) -> RunOnceResult:
    """回收 → 领取一个任务 → 若在 ``parsing`` 则在心跳下跑完本阶段。

    本入口只处理 ``parsing``：领到其他阶段的任务，或本阶段推进到 ``extracting`` 后，以 C09
    ``release_on_shutdown`` 交还（不计尝试次数），留给后续阶段的 worker（E12/F13 接入前见交接风险）。
    """
    url = settings.SQLITE_URL
    store = storage or FileStorage(settings.STORAGE_DIR, settings.UPLOAD_MAX_BYTES)
    reclaimed = reclaim_expired(url, max_attempts=settings.TASK_MAX_ATTEMPTS)
    lease = claim_next(
        url,
        owner=owner or default_owner(),
        lease_seconds=settings.TASK_LEASE_SECONDS,
        max_attempts=settings.TASK_MAX_ATTEMPTS,
    )
    if lease is None:
        return RunOnceResult(reclaimed, None, None, False)
    if lease.stage != STAGE:
        return RunOnceResult(reclaimed, lease, None, release_on_shutdown(url, lease.task_id, lease.token))
    with LeaseHeartbeat(url, lease, lease_seconds=settings.TASK_LEASE_SECONDS):
        outcome = run_parse_stage(url, lease, storage=store, max_attempts=settings.TASK_MAX_ATTEMPTS)
    handed_back = False
    if outcome.status is ParseStatus.ADVANCED:
        handed_back = release_on_shutdown(url, lease.task_id, lease.token)
    return RunOnceResult(reclaimed, lease, outcome, handed_back)
