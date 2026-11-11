"""Internal extraction.dispatch responsibilities; public compatibility entry: app.workers.extract_task."""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from dataclasses import replace
from typing import Generic, TypeVar
from app.repositories.chunks import StoredChunk
from app.repositories.extraction_checkpoints import Checkpoint, read_checkpoints
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

    ``next_unit`` 返回目前可派发的单元；暂时无就绪依赖时返回 None，已有工作结束后再次检查。

    ``halt`` 取值：``cancel``（边界读到取消标志）、``lost``、``threshold``（``after_write`` 判定）、
    ``auth``（鉴权失败，任务终止）、``circuit``/``storage``（阶段级临时故障）。出现后不再派发；
    ``cancel``/``lost``/``threshold``/``auth`` 之后完成的单元不写检查点，``circuit``/``storage`` 之后
    正常完成的单元照常写入（结果有效）。
    """

    def __init__(
        self,
        next_unit: Callable[[], _U | None],
        *,
        limit: int,
        work: Callable[[_U], _UnitResult],
        write: Callable[[_U, _UnitResult], bool],
        after_write: Callable[[_U, _UnitResult], bool],
        order: Callable[[_U], object],
    ) -> None:
        self._next_unit = next_unit
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
            unit = self._next_unit()
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

    if exceeds_threshold(progress.chunks_failed, progress.chunks_total, ratio):
        return _threshold_failure(sqlite_url, lease, limits, progress)

    # Keep entity dispatch in document order. Ready sections only fill spare slots
    # once even every unfinished chunk failing could not cross the task threshold.
    # This retains the no-section-checkpoint invariant for threshold failures.
    sections = _sections(chunks)
    section_of = {chunk.chunk_id: section.section_id for section in sections for chunk in section.chunks}
    succeeded_sections = {section_of[c.unit_id] for c in done_chunks.values() if c.status == "done"}
    progress.sections_total = len(succeeded_sections)
    progress.sections_failed = sum(c.status == "failed" for c in existing if c.unit_kind == "section")
    pending_chunks = iter(chunk for chunk in chunks if chunk.chunk_id not in done_chunks)
    pending_sections = {section.section_id: section for section in sections if section.section_id not in done_sections}

    def next_unit() -> StoredChunk | _Section | None:
        chunk = next(pending_chunks, None)
        if chunk is not None:
            return chunk
        worst_failed = progress.chunks_failed + progress.chunks_total - progress.chunks_done
        if exceeds_threshold(worst_failed, progress.chunks_total, ratio):
            return None  # Other chunks are still in flight; reconsider after settling them.
        ready = []
        for section in tuple(pending_sections.values()):
            if any(member.chunk_id not in done_chunks for member in section.chunks):
                continue
            successful = tuple(member for member in section.chunks if done_chunks[member.chunk_id].status == "done")
            if successful:
                # Same membership/order/identity as _sections(successful_chunks).
                ready.append(replace(section, chunks=successful,
                                     order=(successful[0].revision_id, successful[0].ordinal)))
            else:
                del pending_sections[section.section_id]
        if not ready:
            return None
        section = min(ready, key=lambda item: item.order)
        del pending_sections[section.section_id]
        return section

    def work(unit: StoredChunk | _Section) -> _UnitResult:
        if isinstance(unit, StoredChunk):
            return _extract_chunk(toolkit, lease, limits, unit)
        members = [done_chunks[chunk.chunk_id] for chunk in unit.chunks]
        entities = tuple(
            SectionEntity(entity.entity_id, lease.course_id, entity.name, entity.type)
            for entity in _group_entities(lease.task_id, lease.course_id, members)
        )
        return _extract_section(toolkit, lease, limits, unit, entities)

    def write(unit: StoredChunk | _Section, result: _UnitResult) -> bool:
        if isinstance(unit, StoredChunk):
            share = (progress.chunks_done + 1) / progress.chunks_total
            written = _write_unit(sqlite_url, lease, "chunk", unit.chunk_id, result,
                                  lower + width * CHUNK_PROGRESS_SHARE * share)
            if written:
                done_chunks[unit.chunk_id] = Checkpoint("chunk", unit.chunk_id, result.status,
                                                       result.attempts, result.error_code, result.result)
                count(result)
                if result.status == "done":
                    succeeded_sections.add(section_of[unit.chunk_id])
                    progress.sections_total = len(succeeded_sections)
            return written

        # Do not jump into the relation progress range while entity work remains.
        share = CHUNK_PROGRESS_SHARE * progress.chunks_done / progress.chunks_total
        if progress.chunks_done == progress.chunks_total:
            share += (1 - CHUNK_PROGRESS_SHARE) * (len(done_sections) + 1) / max(progress.sections_total, 1)
        written = _write_unit(sqlite_url, lease, "section", unit.section_id, result, lower + width * share)
        if written:
            done_sections.add(unit.section_id)
            if result.status == "failed":
                progress.sections_failed += 1
        return written

    halt = _Dispatcher(
        next_unit,
        limit=limits.max_concurrency,
        work=work,
        write=write,
        after_write=lambda _unit, _result: exceeds_threshold(progress.chunks_failed, progress.chunks_total, ratio),
        # Settle completed chunks/thresholds before sections from the same wait.
        order=lambda unit: (0, unit.revision_id, unit.ordinal) if isinstance(unit, StoredChunk)
            else (1, *unit.order),
    ).run()
    if halt is not None:
        return _halted(sqlite_url, lease, limits, progress, halt)

    state = _boundary(sqlite_url, lease, "stage_done")
    if state.stage == "cancelled":
        return ExtractOutcome(ExtractStatus.CANCELLED, lease.task_id, "cancelled", "cancelled", **progress.counts())
    return ExtractOutcome(ExtractStatus.ADVANCED, lease.task_id, NEXT_STAGE, "stage", **progress.counts())
