"""Bolt framing evidence, not raw byte-pattern guesses."""
import sys
import io
import json
import subprocess
from pathlib import Path
from types import SimpleNamespace
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'integration'))
import bolt_fault_proxy as proxy_module
from bolt_fault_proxy import BoltFrameObserver
from neo4j.exceptions import ServiceUnavailable, SessionExpired, TransientError
from app.repositories.graph_migrations import GraphMigrationError, apply_migrations
from tests import waiting

CLIENT = bytes.fromhex('6060b017000001ff000808050002040400000003')
VERSION = bytes.fromhex('00000405')
COMMIT = bytes.fromhex('0002b0120000')


def negotiated(manifest=False):
    observer = BoltFrameObserver()
    for byte in CLIENT:
        observer.feed('c2s', bytes([byte]))
    if manifest:
        response = bytes.fromhex('000001ff0200020805000404048001')
        for byte in response:
            observer.feed('s2c', bytes([byte]))
        chosen = bytes.fromhex('0000070500')
        events = observer.feed('c2s', chosen + COMMIT)
        assert [e.signature for e in events if e.phase == 'message'] == [0x12]
    else:
        observer.feed('s2c', VERSION)
    observer.drain('c2s')
    observer.drain('s2c')
    return observer


@pytest.mark.parametrize('manifest', [False, True])
def test_handshake_fragmentation_and_pipelined_commit(manifest):
    observer = negotiated(manifest)
    events = []
    for byte in COMMIT:
        events.extend(observer.feed('c2s', bytes([byte])))
    assert [(e.direction, e.signature, e.phase) for e in events] == [('c2s', 0x12, 'message')]
    assert b''.join(frame for _, frame in observer.drain('c2s')) == COMMIT


def test_chunked_commit_and_noop_are_distinct_from_auth_body():
    observer = negotiated()
    auth = b'\xb1\x01private-token\x12'
    wire = len(auth).to_bytes(2, 'big') + auth + b'\0\0'
    chunked = bytes.fromhex('0001b00001120000')
    events = observer.feed('c2s', wire + b'\0\0' + chunked + COMMIT)
    assert [(e.signature, e.phase) for e in events] == [(1, 'message'), (None, 'noop'),
                                                     (0x12, 'message'), (0x12, 'message')]
    assert 'private-token' not in repr(events)
    assert b''.join(frame for _, frame in observer.drain('c2s')) == wire + b'\0\0' + chunked + COMMIT


def test_truncated_message_is_not_a_commit():
    observer = negotiated()
    assert observer.feed('c2s', COMMIT[:-1]) == []
    with pytest.raises(EOFError):
        observer.finish('c2s')
    assert observer.feed('c2s', COMMIT[-1:])[0].signature == 0x12
    observer.finish('c2s')


def test_noop_client_reset_is_physical_disconnect_not_missing_eof():
    """SO_LINGER produces a real RST, not a simulated cancellation result."""
    import socket
    import struct
    import threading
    from bolt_fault_proxy import BoltFaultProxy
    listener = socket.socket()
    listener.bind(('127.0.0.1', 0))
    listener.listen()
    listener.settimeout(3)
    done = threading.Event()
    errors = []
    def upstream():
        try:
            with listener.accept()[0] as sock:
                sock.settimeout(3)
                data = b''
                while len(data) < 20:
                    data += sock.recv(20 - len(data))
                sock.sendall(VERSION)
                while not done.is_set():
                    if not sock.recv(1024):
                        break
        except OSError as exc:
            if not done.is_set():
                errors.append(type(exc).__name__)
    thread = threading.Thread(target=upstream)
    thread.start()
    try:
        with BoltFaultProxy('127.0.0.1', listener.getsockname()[1], mode='commit_noop') as proxy:
            with socket.create_connection(('127.0.0.1', int(proxy.uri.rsplit(':', 1)[1])), timeout=3) as client:
                client.sendall(CLIENT)
                assert client.recv(4) == VERSION
                client.sendall(COMMIT)
                assert client.recv(2) == b'\0\0'
                assert proxy.forwarded_commits == 1
                client.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, struct.pack('ii', 1, 0))
            signal = getattr(proxy, 'client_disconnected', proxy.client_eof)
            assert signal.wait(2), f'physical reset missed: {proxy.errors}'
            assert proxy.timestamps['client_reset'], 'reset must not be reported as FIN EOF'
        assert proxy.closed
    finally:
        done.set()
        listener.close()
        thread.join(4)
    assert not thread.is_alive() and not errors


@pytest.mark.parametrize('failure, transient', [
    (ServiceUnavailable('offline'), True),
    (SessionExpired('restarting'), True),
    (TransientError('retryable server failure'), True),
    (ValueError('invalid schema'), False),
])
def test_readiness_classifies_real_migration_wrappers(failure, transient):
    class FailingDriver:
        def execute_query(self, *args, **kwargs):
            raise failure

    with pytest.raises(GraphMigrationError) as caught:
        apply_migrations(FailingDriver())
    assert caught.value.__context__ is failure
    assert proxy_module._readiness_is_transient(caught.value) is transient


def test_readiness_retries_with_only_the_remaining_probe_budget(monkeypatch):
    now = [0.0]
    budgets = []
    clock = SimpleNamespace(monotonic=lambda: now[0])
    monkeypatch.setattr(proxy_module, 'time', clock)
    monkeypatch.setattr(waiting, 'time', clock)

    def probe(command, *, input, timeout, **kwargs):
        budgets.append(timeout)
        assert 'fixture-password' not in repr(command)
        assert json.loads(input)['auth'] == ['neo4j', 'fixture-password']
        if len(budgets) == 1:
            now[0] += 8
            return SimpleNamespace(returncode=75, stderr='', stdout='')
        now[0] += timeout
        raise subprocess.TimeoutExpired(command, timeout)

    monkeypatch.setattr(proxy_module.subprocess, 'run', probe)
    with pytest.raises(AssertionError, match='Timed out'):
        proxy_module.wait_for_neo4j('bolt://127.0.0.1:1', ('neo4j', 'fixture-password'),
                                   timeout=12, interval=.001)
    # A separate short attempt cap would kill healthy, still-running schema DDL.
    assert budgets == pytest.approx([12, 4])


def test_readiness_permanent_error_stops_without_echoing_stderr(monkeypatch):
    calls = []

    def probe(*args, **kwargs):
        calls.append(1)
        return SimpleNamespace(returncode=2, stderr='private fixture password: do-not-print', stdout='')

    monkeypatch.setattr(proxy_module.subprocess, 'run', probe)
    with pytest.raises(AssertionError, match='readiness probe failed: exit 2') as caught:
        proxy_module.wait_for_neo4j('bolt://127.0.0.1:1', ('neo4j', 'do-not-print'), timeout=1)
    assert len(calls) == 1 and 'do-not-print' not in str(caught.value)


@pytest.mark.parametrize('failure, code', [(ServiceUnavailable('private'), 75), (ValueError('private'), 2)])
def test_readiness_probe_reports_only_safe_failure_class(monkeypatch, capsys, failure, code):
    def driver(*args, **kwargs):
        raise failure

    monkeypatch.setattr(proxy_module.GraphDatabase, 'driver', driver)
    monkeypatch.setattr(sys, 'stdin', io.StringIO(json.dumps({
        'uri': 'bolt://127.0.0.1:1', 'auth': ['neo4j', 'private'], 'migrate': True,
    })))
    assert proxy_module._neo4j_probe_main() == code
    output = capsys.readouterr()
    assert not output.out
    assert output.err == ('' if code == 75 else 'ValueError\n')


def test_readiness_hard_timeout_reaps_a_stuck_probe(monkeypatch):
    original_run = subprocess.run
    original_popen = subprocess.Popen
    children = []

    def record_child(*args, **kwargs):
        child = original_popen(*args, **kwargs)
        children.append(child)
        return child

    def stalled_probe(command, **kwargs):
        # A real blocked child verifies subprocess.run's kill-and-wait behavior.
        return original_run([sys.executable, '-c', 'import threading; threading.Event().wait()'], **kwargs)

    monkeypatch.setattr(proxy_module.subprocess, 'Popen', record_child)
    monkeypatch.setattr(proxy_module.subprocess, 'run', stalled_probe)
    with pytest.raises(AssertionError, match='Timed out'):
        proxy_module.wait_for_neo4j('bolt://127.0.0.1:1', ('neo4j', 'fixture'), timeout=.2)
    assert children and all(child.poll() is not None for child in children)
