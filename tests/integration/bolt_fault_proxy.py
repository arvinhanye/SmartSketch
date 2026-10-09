"""Test-only loopback Bolt framing/fault relay; never log authentication bodies.

Protocol: https://neo4j.com/docs/bolt/current/bolt/handshake/
"""
from collections import defaultdict
from dataclasses import dataclass
import ipaddress
import json
import select
import shutil
import socket
import subprocess
import threading
import time
import uuid
from typing import Literal

import pytest
from neo4j import GraphDatabase
from app.repositories.graph_migrations import apply_migrations


@dataclass(frozen=True)
class MessageEvent:
    direction: Literal['c2s', 's2c']
    signature: int | None
    phase: Literal['handshake', 'message', 'noop']


def _varint(data, offset):
    value = 0
    for i in range(10):
        if offset + i >= len(data):
            return None
        byte = data[offset + i]
        value |= (byte & 127) << (7 * i)
        if not byte & 128:
            return value, offset + i + 1
    raise ValueError('invalid handshake varint')


class BoltFrameObserver:
    def __init__(self):
        self.buffers = {'c2s': bytearray(), 's2c': bytearray()}
        self.phases = {'c2s': 'initial', 's2c': 'initial'}
        self.payloads = {'c2s': bytearray(), 's2c': bytearray()}
        self.wires = {'c2s': bytearray(), 's2c': bytearray()}
        self.completed = {'c2s': [], 's2c': []}

    def feed(self, direction, data):
        if direction not in self.buffers:
            raise ValueError('invalid direction')
        buffer = self.buffers[direction]
        buffer.extend(data)
        events = []
        while True:
            phase = self.phases[direction]
            size = None
            if phase == 'waiting':
                break
            if phase == 'initial':
                size = 20 if direction == 'c2s' else 4
                if len(buffer) < size:
                    break
                if direction == 'c2s':
                    if buffer[:4] != bytes.fromhex('6060b017'):
                        raise ValueError('invalid Bolt identification')
                    self.phases[direction] = 'waiting'
                elif buffer[:4] == bytes.fromhex('000001ff'):
                    self.phases[direction] = 'manifest'
                    continue
                else:
                    self.phases = {'c2s': 'message', 's2c': 'message'}
            elif phase == 'manifest':
                count = _varint(buffer, 4)
                if count is None:
                    break
                n, offset = count
                if n > 64:
                    raise ValueError('test handshake version list too large')
                caps = _varint(buffer, offset + 4 * n)
                if caps is None:
                    break
                size = caps[1]
                self.phases = {'c2s': 'select', 's2c': 'message'}
            elif phase == 'select':
                caps = _varint(buffer, 4)
                if caps is None:
                    break
                size = caps[1]
                self.phases[direction] = 'message'
            if size is not None:
                wire = bytes(buffer[:size])
                del buffer[:size]
                event = MessageEvent(direction, None, 'handshake')
                events.append(event)
                self.completed[direction].append((event, wire))
                continue
            if len(buffer) < 2:
                break
            length = int.from_bytes(buffer[:2], 'big')
            if len(buffer) < length + 2:
                break
            chunk = bytes(buffer[:length + 2])
            del buffer[:length + 2]
            self.wires[direction].extend(chunk)
            if length:
                self.payloads[direction].extend(chunk[2:])
                continue
            payload = self.payloads[direction]
            signature = payload[1] if len(payload) >= 2 and payload[0] & 0xf0 == 0xb0 else None
            event = MessageEvent(direction, signature, 'message' if payload else 'noop')
            events.append(event)
            self.completed[direction].append((event, bytes(self.wires[direction])))
            payload.clear()
            self.wires[direction].clear()
        return events

    def drain(self, direction):
        frames, self.completed[direction] = self.completed[direction], []
        return frames

    def finish(self, direction):
        if self.buffers[direction] or self.payloads[direction] or self.wires[direction]:
            raise EOFError('truncated Bolt frame')


class BoltFaultProxy:
    MODES = {'healthy', 'commit_blackhole', 'commit_noop', 'commit_fragment',
             'disconnect_before', 'disconnect_after', 'begin_blackhole',
             'pull_blackhole', 'rollback_blackhole'}

    def __init__(self, upstream_host, upstream_port, *, mode):
        if not ipaddress.ip_address(upstream_host).is_loopback or mode not in self.MODES:
            raise ValueError('test proxy requires loopback and a known fault')
        self.upstream = (upstream_host, upstream_port)
        self.mode = mode
        self.forwarded_commits = 0
        self.timestamps = defaultdict(list)
        self.client_eof = threading.Event()
        self.client_disconnected = threading.Event()
        self.commit_seen = threading.Event()
        self.stop = threading.Event()
        self.closed = False
        self.errors = []
        self.sockets = []
        self.before_forward_commit = lambda: None

    def stamp(self, name):
        self.timestamps[name].append(time.monotonic())

    def _client_closed(self, reason):
        if not self.client_disconnected.is_set():
            self.stamp(reason)
            self.stamp('client_disconnected')
            if reason == 'client_eof':
                self.client_eof.set()
            self.client_disconnected.set()

    def _recv_client(self, client, size, flags=0):
        try:
            data = client.recv(size, flags)
        except ConnectionResetError:
            self._client_closed('client_reset')
            return b''
        if not data:
            self._client_closed('client_eof')
        return data

    def _send_client(self, client, data):
        try:
            client.sendall(data)
            return True
        except ConnectionResetError:
            self._client_closed('client_reset')
            return False
        except BrokenPipeError:
            # A write failure alone is not peer-closure evidence. Confirm an
            # EOF/reset on the actual client socket; do not count proxy teardown.
            timeout = client.gettimeout()
            client.settimeout(0)
            try:
                if not self._recv_client(client, 1, socket.MSG_PEEK):
                    return False
            finally:
                client.settimeout(timeout)
            raise

    def __enter__(self):
        self.listener = socket.socket()
        self.listener.bind(('127.0.0.1', 0))
        self.listener.listen()
        self.listener.settimeout(.1)
        self.uri = f'bolt://127.0.0.1:{self.listener.getsockname()[1]}'
        self.thread = threading.Thread(target=self._serve, daemon=True)
        self.thread.start()
        return self

    def _serve(self):
        try:
            while not self.stop.is_set():
                try:
                    client, _ = self.listener.accept()
                    break
                except socket.timeout:
                    continue
            else:
                return
            upstream = socket.create_connection(self.upstream, timeout=2)
            self.sockets = [client, upstream]
            for sock in self.sockets:
                sock.settimeout(2)
            observer = BoltFrameObserver()
            fault = False
            fragment = bytearray()
            next_fragment = next_noop = time.monotonic()
            deadline = time.monotonic() + 90
            while not self.stop.is_set() and time.monotonic() < deadline:
                readable, _, _ = select.select(self.sockets, [], [], .01)
                for source in readable:
                    data = self._recv_client(client, 65536) if source is client else source.recv(65536)
                    if not data:
                        return
                    direction = 'c2s' if source is client else 's2c'
                    target = upstream if source is client else client
                    observer.feed(direction, data)
                    for event, wire in observer.drain(direction):
                        if direction == 'c2s' and event.phase == 'message':
                            if event.signature == 0x12:
                                self.stamp('commit_seen')
                                self.commit_seen.set()
                                if self.mode == 'disconnect_before':
                                    return
                                self.before_forward_commit()
                                # Never inject a buffered request after the client has gone.
                                readable_client, _, _ = select.select([client], [], [], 0)
                                if readable_client and not self._recv_client(client, 1, socket.MSG_PEEK):
                                    return
                                target.sendall(wire)
                                self.forwarded_commits += 1
                                self.stamp('commit_forwarded')
                                if self.mode == 'disconnect_after':
                                    return
                                fault = self.mode.startswith('commit_')
                                continue
                            trigger = {'begin_blackhole': 0x11, 'pull_blackhole': 0x3f,
                                       'rollback_blackhole': 0x13}.get(self.mode)
                            if event.signature == trigger:
                                fault = True
                                self.stamp('fault_started')
                        if direction == 's2c' and fault:
                            self.stamp('reply_dropped')
                            if self.mode == 'commit_fragment':
                                fragment.extend(wire)
                            continue
                        if target is client:
                            if not self._send_client(client, wire):
                                return
                        else:
                            target.sendall(wire)
                now = time.monotonic()
                if fault and self.mode == 'commit_noop' and now >= next_noop:
                    if not self._send_client(client, b'\0\0'):
                        return
                    next_noop = now + .02
                if fragment and now >= next_fragment:
                    if not self._send_client(client, bytes(fragment[:1])):
                        return
                    del fragment[:1]
                    next_fragment = now + 1.5
            if not self.stop.is_set():
                self.errors.append('proxy_watchdog')
        except (OSError, EOFError) as exc:
            if not self.stop.is_set():
                self.errors.append(type(exc).__name__)  # no payload/address
        finally:
            for sock in self.sockets:
                sock.close()

    def __exit__(self, *exc):
        self.stop.set()
        self.listener.close()
        for sock in self.sockets:
            try:
                sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
        self.thread.join(timeout=3)
        self.closed = not self.thread.is_alive()
        if not self.closed:
            raise AssertionError('proxy thread did not exit')


@pytest.fixture(scope='module')
def owned_neo4j():
    docker = shutil.which('docker') or '/Users/arvinhan/.docker/bin/docker'
    def command(*args):
        result = subprocess.run([docker, *args], capture_output=True, text=True, timeout=30)
        if result.returncode:
            raise AssertionError(f'owned fixture Docker command failed: {args[0]}')
        return result.stdout.strip()
    nonce = uuid.uuid4().hex
    password = 'fixture-' + nonce
    cid = command('run', '-d', '--rm', '--name', 'smartsketch-bolt-' + nonce,
                  '--label', 'smartsketch.fixture=' + nonce, '-p', '127.0.0.1::7687',
                  '-e', 'NEO4J_AUTH=neo4j/' + password,
                  '-e', 'NEO4J_server_memory_heap_initial__size=256m',
                  '-e', 'NEO4J_server_memory_heap_max__size=512m',
                  '-e', 'NEO4J_server_memory_pagecache_size=128m', 'neo4j:5.26-community')
    try:
        info = json.loads(command('inspect', cid))[0]
        port = int(info['NetworkSettings']['Ports']['7687/tcp'][0]['HostPort'])
        uri = f'bolt://127.0.0.1:{port}'
        deadline = time.monotonic() + 120
        while True:
            try:
                with GraphDatabase.driver(uri, auth=('neo4j', password), connection_timeout=1) as driver:
                    driver.verify_connectivity()
                    apply_migrations(driver)
                    driver.execute_query('RETURN 1')
                break
            except Exception:
                if time.monotonic() >= deadline:
                    raise AssertionError('owned Neo4j did not start') from None
                time.sleep(.5)
        yield {'uri': uri, 'host': '127.0.0.1', 'port': port,
               'auth': ('neo4j', password), 'id': cid, 'docker': docker}
    finally:
        info = json.loads(command('inspect', cid))[0]
        if info['Config']['Labels'].get('smartsketch.fixture') != nonce:
            raise AssertionError('fixture ownership changed; leave container intact')
        command('rm', '-f', cid)
