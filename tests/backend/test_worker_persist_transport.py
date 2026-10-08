"""Bound the real synchronous facade; only the external driver is doubled."""
import asyncio
import threading
import time
import warnings

import pytest

from app.repositories.persist_transport import PersistTransport, TransportTimeout


class FakeDriver:
    def __init__(self, *, commit_delay=0, run_delay=0, consume_delay=0,
                 tx_close_delay=0, session_close_delay=0, driver_close_delay=0,
                 begin_error=False):
        self.delays = locals()
        self.cancel_calls = self.commit_calls = self.factory_calls = 0
        self.calls = []
        self.loops = []
        self.tasks = []
        self.open_resources = set()
        self.cancelled = False

    def factory(self):
        self.factory_calls += 1
        self.record('driver')
        self.open_resources.add('driver')
        return self

    def record(self, name):
        self.calls.append((name, threading.get_ident()))
        self.loops.append(asyncio.get_running_loop())
        self.tasks.append(asyncio.current_task())

    @property
    def pending_tasks(self):
        return [t for t in self.tasks if not t.done()]

    def session(self, **kwargs):
        assert kwargs == {'database': 'neo4j'}
        self.open_resources.add('session')
        driver = self

        class Session:
            async def begin_transaction(self, *, timeout):
                driver.record('begin')
                assert timeout > 0
                if driver.delays['begin_error']:
                    raise OSError('private-host private-token')
                driver.open_resources.add('tx')
                return Tx()

            def cancel(self):
                driver.record('cancel')
                driver.cancel_calls += 1
                driver.cancelled = True
                driver.open_resources.discard('tx')
                driver.open_resources.discard('session')

            async def close(self):
                driver.record('session_close')
                try:
                    if not driver.cancelled:
                        await asyncio.sleep(driver.delays['session_close_delay'])
                finally:
                    driver.open_resources.discard('session')

        class Tx:
            async def run(self, query, parameters):
                driver.record('run')
                await asyncio.sleep(driver.delays['run_delay'])
                return Result()

            async def commit(self):
                driver.record('commit')
                driver.commit_calls += 1
                await asyncio.sleep(driver.delays['commit_delay'])
                driver.open_resources.discard('tx')

            async def close(self):
                driver.record('tx_close')
                if not driver.cancelled:
                    await asyncio.sleep(driver.delays['tx_close_delay'])
                driver.open_resources.discard('tx')

        class Result:
            async def data(self):
                driver.record('consume')
                await asyncio.sleep(driver.delays['consume_delay'])
                return [{'answer': 42}]

        return Session()

    async def close(self):
        self.record('driver_close')
        try:
            await asyncio.sleep(self.delays['driver_close_delay'])
        finally:
            self.open_resources.discard('driver')


def transport(fake, *, budget=.3, commit_timeout=.04, cleanup_timeout=.04):
    return PersistTransport(fake.factory, deadline=time.monotonic() + budget,
                            remaining=lambda: budget, check=lambda: None,
                            commit_timeout=commit_timeout, cleanup_timeout=cleanup_timeout)


def test_timeout_cancels_connection_and_finishes_task():
    fake = FakeDriver(commit_delay=10)
    tx = transport(fake)
    tx.open()
    with pytest.raises(TransportTimeout) as caught:
        tx.commit(started_at=time.monotonic())
    assert caught.value.phase == 'commit'
    assert caught.value.commit_started is True
    assert str(caught.value) == 'NEO4J_TRANSPORT_TIMEOUT'
    tx.close()
    assert fake.cancel_calls == 1
    assert fake.commit_calls == 1
    assert not fake.pending_tasks
    assert not fake.open_resources
    assert not tx.committed


def test_run_consumption_uses_original_deadline():
    fake = FakeDriver(run_delay=.03, consume_delay=.03)
    tx = transport(fake, budget=.05)
    original = tx.deadline
    tx.open()
    with pytest.raises(TransportTimeout) as caught:
        tx.run('RETURN 42', {})
    assert caught.value.phase == 'run'
    assert tx.deadline == original
    tx.close()
    assert not fake.pending_tasks


def test_active_loop_rejects_before_factory():
    fake = FakeDriver()
    tx = transport(fake)
    async def caller():
        with pytest.raises(RuntimeError):
            tx.open()
    with warnings.catch_warnings(record=True) as captured:
        warnings.simplefilter('always')
        asyncio.run(caller())
    assert fake.factory_calls == 0
    assert not captured


def test_each_attempt_owns_loop_and_closes_partial_factory_resources():
    fakes = [FakeDriver(), FakeDriver(begin_error=True)]
    for fake in fakes:
        tx = transport(fake)
        try:
            tx.open()
        except OSError:
            pass
        finally:
            tx.close()
        assert not fake.open_resources
        assert len(set(fake.loops)) == 1
        assert {thread for _, thread in fake.calls} == {threading.get_ident()}
        assert not fake.pending_tasks
    assert fakes[0].loops[0] is not fakes[1].loops[0]


def test_cleanup_layers_share_one_deadline():
    fake = FakeDriver(tx_close_delay=.03, session_close_delay=.03)
    tx = transport(fake, cleanup_timeout=.05)
    tx.open()
    started = time.monotonic()
    with pytest.raises(TransportTimeout) as caught:
        tx.close()
    assert caught.value.phase == 'exit'
    assert time.monotonic() - started < .15
    assert not fake.open_resources
    assert not fake.pending_tasks


def test_rollback_stall_forces_cancel():
    fake = FakeDriver(tx_close_delay=10)
    tx = transport(fake)
    tx.open()
    with pytest.raises(TransportTimeout):
        tx.close()
    assert fake.cancel_calls == 1
    assert not fake.open_resources
    assert not fake.pending_tasks


def test_commit_is_not_repeated_after_uncertainty():
    fake = FakeDriver(commit_delay=10)
    tx = transport(fake)
    tx.open()
    with pytest.raises(TransportTimeout):
        tx.commit(started_at=time.monotonic())
    with pytest.raises(RuntimeError):
        tx.commit(started_at=time.monotonic())
    tx.close()
    assert fake.commit_calls == 1
