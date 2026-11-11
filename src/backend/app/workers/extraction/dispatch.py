"""Internal extraction.dispatch responsibilities; public compatibility entry: app.workers.extract_task."""

from __future__ import annotations

import sqlite3
from collections.abc import Callable, Sequence
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from typing import Generic, TypeVar
from app.repositories.chunks import StoredChunk
from app.repositories.extraction_checkpoints import read_checkpoints
from app.repositories.sqlite import connect
from app.repositories.task_leases import Lease, LeaseLost
from app.services.ai.relations import SectionEntity
from app.services.task_state import stage_progress_range
from app.workers.extraction.candidates import (
    _group_entities,
    _sections,
    _task_chunks,
)
from app.workers.extraction.state import (
    _boundary,
    _fail,
    _lost,
    _release,
    _write_unit,
)
from app.workers.extraction.types import (
    AUTH_MESSAGE,
    CHUNK_PROGRESS_SHARE,
    ExtractLimits,
    ExtractOutcome,
    ExtractStatus,
    ExtractionToolkit,
    MODEL_ERROR_CODE,
    NEXT_STAGE,
    OUTPUT_INVALID_CODE,
    STAGE,
    _Halt,
    _Progress,
    _Section,
    _UnitResult,
    exceeds_threshold,
    logger,
)
from app.workers.extraction.units import (
    _extract_chunk,
    _extract_section,
)

# ---------------------------------------------------------------- 并发派发

_U = TypeVar("_U")


class _Dispatcher(Generic[_U]):
    """在线程池里处理单元，主线程按完成顺序在块边界写检查点；在途上限 ``limit``。

    ``halt`` 取值：``cancel``（边界读到取消标志）、``lost``、``threshold``（``after_write`` 判定）、
    ``auth``（鉴权失败，任务终止）、``circuit``/``storage``（阶段级临时故障）。出现后不再派发；
    ``cancel``/``lost``/``threshold``/``auth`` 之后完成的单元不写检查点，``circuit``/``storage`` 之后
    正常完成的单元照常写入（结果有效）。
    """

    def __init__(
        self,
        units: Sequence[_U],
        *,
        limit: int,
        work: Callable[[_U], _UnitResult],
        write: Callable[[_U, _UnitResult], bool],
        after_write: Callable[[_U, _UnitResult], bool],
        order: Callable[[_U], object],
    ) -> None:
        self._units = iter(units)
        self._limit = limit
        self._work = work
        self._write = write
        self._after_write = after_write
        self._order = order
        self.halt: str | None = None

    def run(self) -> str | None:
        inflight: dict[Future[_UnitResult], _U] = {}
        with ThreadPoolExecutor(max_workers=self._limit, thread_name_prefix="extract") as pool:
            self._fill(pool, inflight)
            while inflight:
                finished, _ = wait(tuple(inflight), return_when=FIRST_COMPLETED)
                for future in sorted(finished, key=lambda f: self._order(inflight[f])):  # type: ignore[arg-type]
                    unit = inflight.pop(future)
                    self._settle(unit, future)
                self._fill(pool, inflight)
        return self.halt

    def _fill(self, pool: ThreadPoolExecutor, inflight: dict[Future[_UnitResult], _U]) -> None:
        while self.halt is None and len(inflight) < self._limit:
            unit = next(self._units, None)
            if unit is None:
                return
            inflight[pool.submit(self._work, unit)] = unit

    def _settle(self, unit: _U, future: Future[_UnitResult]) -> None:
        try:
            result = future.result()
        except _Halt as halt:
            self.halt = self.halt or halt.reason
            return
        if self.halt in ("cancel", "lost", "threshold", "auth"):
            return
        try:
            if not self._write(unit, result):
                self.halt = "cancel"
                return
        except LeaseLost:
            self.halt = "lost"
            return
        except sqlite3.OperationalError:
            self.halt = self.halt or "storage"
            return
        if self.halt is None and self._after_write(unit, result):
            self.halt = "threshold"


def _threshold_failure(
    sqlite_url: str, lease: Lease, limits: ExtractLimits, progress: _Progress
) -> ExtractOutcome:
    codes = dict(sorted(progress.by_code.items()))
    code = MODEL_ERROR_CODE if set(codes) == {MODEL_ERROR_CODE} else OUTPUT_INVALID_CODE
    details: dict[str, object] = {
        "chunks_failed": progress.chunks_failed,
        "chunks_total": progress.chunks_total,
        "threshold": limits.max_failed_ratio,
    }
    if code == OUTPUT_INVALID_CODE:
        details["by_code"] = codes
    return _fail(sqlite_url, lease, code, details, progress.counts())


def _halted(
    sqlite_url: str, lease: Lease, limits: ExtractLimits, progress: _Progress, halt: str
) -> ExtractOutcome:
    counts = progress.counts()
    if halt == "lost":
        return _lost(lease)
    if halt == "cancel":
        _boundary(sqlite_url, lease, "checkpoint")
        return ExtractOutcome(ExtractStatus.CANCELLED, lease.task_id, "cancelled", "cancelled", **counts)
    if halt == "threshold":
        return _threshold_failure(sqlite_url, lease, limits, progress)
    if halt == "auth":
        logger.warning("extracting task %s: provider rejected the API key, failing the task", lease.task_id)
        return _fail(sqlite_url, lease, MODEL_ERROR_CODE, {"reason": "auth"}, counts, message=AUTH_MESSAGE)
    code = MODEL_ERROR_CODE if halt == "circuit" else "STORAGE_UNAVAILABLE"
    logger.warning("extracting task %s: stage-level fault (%s), releasing", lease.task_id, halt)
    return _release(sqlite_url, lease, code, limits.max_attempts, counts)


def _run(sqlite_url: str, lease: Lease, toolkit: ExtractionToolkit, limits: ExtractLimits) -> ExtractOutcome:
    chunks = _task_chunks(sqlite_url, lease.course_id, lease.task_id)
    if not chunks:
        raise RuntimeError(f"task {lease.task_id} reached {STAGE} without source chunks")
    by_id = {chunk.chunk_id: chunk for chunk in chunks}
    with connect(sqlite_url) as database:
        existing = read_checkpoints(database, course_id=lease.course_id, task_id=lease.task_id)
    done_chunks = {c.unit_id: c for c in existing if c.unit_kind == "chunk" and c.unit_id in by_id}
    done_sections = {c.unit_id for c in existing if c.unit_kind == "section"}

    progress = _Progress(len(chunks))
    lower, upper = stage_progress_range(STAGE)
    width = upper - lower

    def count(result: _UnitResult) -> None:
        progress.chunks_done += 1
        if result.status == "failed":
            progress.chunks_failed += 1
            progress.by_code[result.error_code or OUTPUT_INVALID_CODE] += 1

    for checkpoint in done_chunks.values():
        count(_UnitResult(checkpoint.status, checkpoint.attempts, checkpoint.error_code))
    ratio = limits.max_failed_ratio

    # -- 块阶段
    if progress.chunks_failed == 0 or not exceeds_threshold(progress.chunks_failed, progress.chunks_total, ratio):

        def write_chunk(chunk: StoredChunk, result: _UnitResult) -> bool:
            share = (progress.chunks_done + 1) / progress.chunks_total
            written = _write_unit(sqlite_url, lease, "chunk", chunk.chunk_id, result,
                                  lower + width * CHUNK_PROGRESS_SHARE * share)
            if written:
                count(result)
            return written

        halt = _Dispatcher(
            [chunk for chunk in chunks if chunk.chunk_id not in done_chunks],
            limit=limits.max_concurrency,
            work=lambda chunk: _extract_chunk(toolkit, lease, limits, chunk),
            write=write_chunk,
            after_write=lambda _chunk, _result: exceeds_threshold(progress.chunks_failed, progress.chunks_total, ratio),
            order=lambda chunk: (chunk.revision_id, chunk.ordinal),
        ).run()
        if halt is not None:
            return _halted(sqlite_url, lease, limits, progress, halt)
    if exceeds_threshold(progress.chunks_failed, progress.chunks_total, ratio):
        return _threshold_failure(sqlite_url, lease, limits, progress)

    # -- 小节关系
    with connect(sqlite_url) as database:
        chunk_checkpoints = read_checkpoints(database, course_id=lease.course_id, task_id=lease.task_id,
                                             unit_kind="chunk")
    succeeded = {c.unit_id: c for c in chunk_checkpoints if c.status == "done"}
    sections = _sections(by_id[chunk_id] for chunk_id in succeeded if chunk_id in by_id)
    progress.sections_total = len(sections)
    with connect(sqlite_url) as database:
        for checkpoint in read_checkpoints(database, course_id=lease.course_id, task_id=lease.task_id,
                                           unit_kind="section"):
            if checkpoint.status == "failed":
                progress.sections_failed += 1
    finished = [0 + len(done_sections)]

    def section_entities(section: _Section) -> tuple[SectionEntity, ...]:
        members = [succeeded[chunk.chunk_id] for chunk in section.chunks]
        return tuple(
            SectionEntity(entity.entity_id, lease.course_id, entity.name, entity.type)
            for entity in _group_entities(lease.task_id, lease.course_id, members)
        )

    def write_section(section: _Section, result: _UnitResult) -> bool:
        share = (finished[0] + 1) / max(progress.sections_total, 1)
        written = _write_unit(
            sqlite_url, lease, "section", section.section_id, result,
            lower + width * (CHUNK_PROGRESS_SHARE + (1 - CHUNK_PROGRESS_SHARE) * share),
        )
        if written:
            finished[0] += 1
            if result.status == "failed":
                progress.sections_failed += 1
        return written

    halt = _Dispatcher(
        [section for section in sections if section.section_id not in done_sections],
        limit=limits.max_concurrency,
        work=lambda section: _extract_section(toolkit, lease, limits, section, section_entities(section)),
        write=write_section,
        after_write=lambda _section, _result: False,  # 小节关系失败不计入阈值（ArvinHan 2026-09-26）
        order=lambda section: section.order,
    ).run()
    if halt is not None:
        return _halted(sqlite_url, lease, limits, progress, halt)

    state = _boundary(sqlite_url, lease, "stage_done")
    if state.stage == "cancelled":
        return ExtractOutcome(ExtractStatus.CANCELLED, lease.task_id, "cancelled", "cancelled", **progress.counts())
    return ExtractOutcome(ExtractStatus.ADVANCED, lease.task_id, NEXT_STAGE, "stage", **progress.counts())
