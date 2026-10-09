"""Attempt-owned asynchronous Bolt transport behind a synchronous facade.

No managed retries, background commit, or transaction context auto-commit.
The caller unwinds its SQLite fence before calling close().
"""
from __future__ import annotations

import asyncio
import math
import time
from collections.abc import Callable, Mapping
from typing import Any, Literal

from neo4j import AsyncDriver

AsyncDriverFactory = Callable[[], AsyncDriver]
Phase = Literal['open', 'run', 'commit', 'exit']


class TransportTimeout(RuntimeError):
    def __init__(self, phase: Phase, commit_started: bool) -> None:
        self.phase = phase
        self.commit_started = commit_started
        super().__init__('NEO4J_TRANSPORT_TIMEOUT')


class PersistTransport:
    def __init__(self, factory: AsyncDriverFactory, *, deadline: float,
                 remaining: Callable[[], float], check: Callable[[], None],
                 commit_timeout: float, cleanup_timeout: float) -> None:
        for value, cap in ((commit_timeout, 3.0), (cleanup_timeout, 5.0)):
            if not math.isfinite(value) or not 0 < value <= cap:
                raise ValueError('invalid persist transport budget')
        if not math.isfinite(deadline):
            raise ValueError('invalid persist transport deadline')
        self._factory = factory
        self._deadline = deadline
        self._remaining = remaining
        self._check = check
        self._commit_timeout = commit_timeout
        self._cleanup_timeout = cleanup_timeout
        self._runner: asyncio.Runner | None = None
        self._driver = self._session = self._tx = None
        self._commit_started = self._committed = self._cancelled = False
        self._closed = False

    @property
    def deadline(self) -> float:
        return self._deadline

    @property
    def commit_started(self) -> bool:
        return self._commit_started

    @property
    def committed(self) -> bool:
        return self._committed

    @staticmethod
    def _reject_active_loop() -> None:
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return
        raise RuntimeError('persist facade requires a synchronous caller')

    def _cancel(self) -> None:
        if self._session is not None and not self._cancelled:
            self._cancelled = True
            self._session.cancel()

    async def _bounded(self, phase: Phase, deadline: float,
                       work: Callable[[], Any], *, guarded: bool = True) -> Any:
        if guarded:
            self._check()
        delay = deadline - time.monotonic()
        if delay <= 0 and phase != 'exit':
            self._cancel()
            raise TransportTimeout(phase, self.commit_started)
        try:
            async with asyncio.timeout(max(0.0, delay)):
                try:
                    return await work()
                except asyncio.CancelledError:
                    self._cancel()
                    raise
        except TimeoutError:
            raise TransportTimeout(phase, self.commit_started) from None

    def open(self) -> None:
        self._reject_active_loop()  # before Runner, factory, or coroutine creation
        if self._runner is not None or self._closed:
            raise RuntimeError('persist transport already opened or closed')
        self._runner = asyncio.Runner()
        self._runner.run(self._bounded('open', self.deadline, self._open))

    async def _open(self) -> None:
        self._driver = self._factory()
        self._session = self._driver.session(database='neo4j')
        self._tx = await self._session.begin_transaction(
            timeout=max(.001, self.deadline - time.monotonic()))

    def _require_open(self) -> None:
        self._reject_active_loop()
        if self._runner is None or self._tx is None or self._closed or self._cancelled:
            raise RuntimeError('persist transport is not usable')

    def run(self, query: str, parameters: Mapping[str, Any]) -> list[dict[str, Any]]:
        self._require_open()
        async def execute():
            result = await self._tx.run(query, dict(parameters))
            return await result.data()
        rows = self._runner.run(self._bounded('run', self.deadline, execute))
        self._check()
        return rows

    def commit(self, *, started_at: float) -> None:
        if self.commit_started:
            raise RuntimeError('persist transaction commit already dispatched')
        self._require_open()
        self._check()
        now = time.monotonic()
        cutoff = min(self.deadline, started_at + self._commit_timeout,
                     now + self._remaining())
        async def execute():
            self._check()
            self._commit_started = True  # conservative: call start, not bytes sent
            await self._tx.commit()
            self._committed = True  # no retroactive guard check after success
        self._runner.run(self._bounded('commit', cutoff, execute))

    def close(self) -> None:
        self._reject_active_loop()
        if self._closed:
            return
        self._closed = True
        if self._runner is None:
            return
        try:
            self._runner.run(self._close())
        finally:
            self._runner.close()

    async def _close(self) -> None:
        cutoff = time.monotonic() + self._cleanup_timeout
        error: BaseException | None = None
        resources = (self._tx, self._session, self._driver)
        for resource in resources:
            if resource is None:
                continue
            try:
                await self._bounded('exit', cutoff, resource.close, guarded=False)
            except BaseException as exc:
                self._cancel()
                if error is None:
                    error = exc
        # No producer may leave network tasks for Runner.close() to await.
        pending = [task for task in asyncio.all_tasks()
                   if task is not asyncio.current_task() and not task.done()]
        if pending:
            self._cancel()
            for task in pending:
                task.cancel()
            error = error or RuntimeError('persist transport left pending tasks')
        if error is not None:
            raise error
