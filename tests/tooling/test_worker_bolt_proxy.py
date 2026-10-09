"""Bolt framing evidence, not raw byte-pattern guesses."""
import sys
from pathlib import Path
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'integration'))
from bolt_fault_proxy import BoltFrameObserver

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
