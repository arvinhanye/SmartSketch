"""Internal compatible_transport responsibilities; public compatibility entry: app.services.ai.compatible."""

from __future__ import annotations

import http.client
import socket
import ssl
import threading
import time
from collections.abc import Callable, Mapping
from typing import Any, Protocol
from urllib.parse import urlsplit

# ---------------------------------------------------------------- transport


class HttpResponse(Protocol):
    """An open HTTP response. ``read`` returns ``b""`` at end of body."""

    status: int

    def header(self, name: str) -> str | None: ...

    def read(self, amount: int, timeout: float) -> bytes: ...

    def close(self) -> None: ...


class HttpTransport(Protocol):
    """Sends one POST and returns once the status line and headers have arrived.

    ``timeout`` is the budget for the whole exchange (ADR-082 决定 3): resolving, connecting,
    TLS, sending, waiting for headers and every later ``HttpResponse.read``. Implementations
    raise ``TimeoutError`` (``socket.timeout``) on timeouts and ``OSError`` or
    ``http.client.HTTPException`` on connection problems, both from ``open`` and from
    ``HttpResponse.read``.
    """

    def open(self, url: str, body: bytes, headers: Mapping[str, str], timeout: float) -> HttpResponse: ...


AddressResolver = Callable[[str, int], list[str]]
Connector = Callable[[tuple[str, int], float], socket.socket]


def system_addresses(host: str, port: int) -> list[str]:
    infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    return list(dict.fromkeys(str(info[4][0]) for info in infos))


def _shutdown(sock: socket.socket) -> None:
    try:
        sock.shutdown(socket.SHUT_RDWR)
    except OSError:
        pass


class ExchangeDeadline:
    """One exchange's absolute deadline plus a watchdog that shuts its socket when it passes.

    Socket timeouts bound each blocking call, but a peer that keeps sending a byte at a time
    never trips them; the watchdog makes the deadline hard, so the exchange really stops
    instead of continuing in the background after the caller gave up.
    """

    def __init__(self, timeout: float) -> None:
        self.deadline = time.monotonic() + timeout
        self.expired = False
        self._sock: socket.socket | None = None
        self._mutex = threading.Lock()
        self._timer = threading.Timer(max(0.0, timeout), self._fire)
        self._timer.daemon = True
        self._timer.start()

    def remaining(self) -> float:
        left = self.deadline - time.monotonic()
        if self.expired or left <= 0:
            raise TimeoutError("outbound deadline reached")
        return left

    def attach(self, sock: socket.socket) -> None:
        with self._mutex:
            self._sock = sock
            expired = self.expired
        if expired:
            _shutdown(sock)

    def _fire(self) -> None:
        with self._mutex:
            self.expired = True
            sock = self._sock
        if sock is not None:
            _shutdown(sock)

    def cancel(self) -> None:
        self._timer.cancel()


def resolve_within(resolver: AddressResolver, host: str, port: int, limit: ExchangeDeadline) -> list[str]:
    """Run a blocking resolver for at most the remaining time; a late answer is discarded unused."""
    outcome: dict[str, Any] = {}
    done = threading.Event()

    def run() -> None:
        try:
            outcome["addresses"] = resolver(host, port)
        except BaseException as error:  # noqa: BLE001 - handed back to the caller below
            outcome["error"] = error
        finally:
            done.set()

    threading.Thread(target=run, daemon=True, name="outbound-resolve").start()
    if not done.wait(limit.remaining()):
        raise TimeoutError("name resolution exceeded the deadline")
    if "error" in outcome:
        raise outcome["error"]
    return list(outcome["addresses"])


def _connect_within(addresses: list[str], port: int, limit: ExchangeDeadline, connector: Connector) -> socket.socket:
    """Try each address in order; every attempt gets only what is left of the one budget."""
    last: OSError | None = None
    for address in addresses:
        try:
            timeout = limit.remaining()
        except TimeoutError:
            break
        try:
            return connector((address, port), timeout)
        except OSError as error:
            last = error
    if limit.expired or time.monotonic() >= limit.deadline:
        raise TimeoutError("connect exceeded the deadline")
    raise last if last is not None else OSError("no address to connect to")


def exchange(*, scheme: str, host: str, port: int, path: str, body: bytes, headers: Mapping[str, str],
             timeout: float, addresses: Callable[[ExchangeDeadline], list[str]],
             connector: Connector, ssl_context: ssl.SSLContext | None, method: str = "POST") -> HttpResponse:
    """Exchange once with ``timeout`` as the hard budget; callers select POST or GET."""
    limit = ExchangeDeadline(timeout)
    connection: http.client.HTTPConnection | None = None
    sock: socket.socket | None = None
    try:
        sock = _connect_within(addresses(limit), port, limit, connector)
        limit.attach(sock)
        if scheme == "https":
            sock.settimeout(limit.remaining())
            sock = (ssl_context or ssl.create_default_context()).wrap_socket(sock, server_hostname=host)
            limit.attach(sock)
            connection = http.client.HTTPSConnection(host, port, timeout=limit.remaining())
        else:
            connection = http.client.HTTPConnection(host, port, timeout=limit.remaining())
        connection.sock = sock          # already connected (and verified); http.client never reconnects
        sock.settimeout(limit.remaining())
        connection.request(method, path or "/", body=body, headers=dict(headers))
        sock.settimeout(limit.remaining())
        response = connection.getresponse()
        if limit.expired:               # headers cut short by the watchdog are not a response
            raise TimeoutError("outbound deadline reached")
    except Exception as error:
        limit.cancel()
        if connection is not None:
            connection.close()
        elif sock is not None:
            sock.close()
        if limit.expired and not isinstance(error, TimeoutError):
            raise TimeoutError("outbound deadline reached") from None
        raise
    return _StdlibResponse(connection, sock, response, limit)


class _StdlibResponse:
    def __init__(self, connection: http.client.HTTPConnection, sock: socket.socket | None,
                 response: http.client.HTTPResponse, limit: ExchangeDeadline | None = None) -> None:
        self._connection = connection
        self._sock = sock
        self._response = response
        self._limit = limit
        self.status = response.status

    def header(self, name: str) -> str | None:
        return self._response.getheader(name)

    def read(self, amount: int, timeout: float) -> bytes:
        # A server that closes the connection (HTTP/1.0, ``Connection: close``) makes http.client
        # close the socket once the body is consumed; the next read is EOF, not a socket call.
        if self._response.isclosed():
            return b""
        if self._sock is not None:
            if self._limit is not None:
                timeout = min(timeout, self._limit.deadline - time.monotonic())
            self._sock.settimeout(max(timeout, 0.001))
        try:
            data = self._response.read1(amount)
        except Exception:
            if self._limit is not None and self._limit.expired:
                raise TimeoutError("outbound deadline reached") from None
            raise
        if self._limit is not None and self._limit.expired:   # EOF caused by the watchdog is not a real end
            raise TimeoutError("outbound deadline reached")
        return data

    def close(self) -> None:
        if self._limit is not None:
            self._limit.cancel()
        try:
            self._response.close()
        finally:
            self._connection.close()


def _plain_connect(address: tuple[str, int], timeout: float) -> socket.socket:
    return socket.create_connection(address, timeout)


class StdlibTransport:
    """Default transport on ``http.client`` (no third-party runtime dependency)."""

    def __init__(self, ssl_context: ssl.SSLContext | None = None, *, resolver: AddressResolver | None = None,
                 connector: Connector | None = None) -> None:
        self._ssl_context = ssl_context
        self._resolver = resolver or system_addresses
        self._connector = connector or _plain_connect

    def open(self, url: str, body: bytes, headers: Mapping[str, str], timeout: float) -> HttpResponse:
        parts = urlsplit(url)
        host = parts.hostname or ""
        port = parts.port or (443 if parts.scheme == "https" else 80)
        return exchange(scheme=parts.scheme, host=host, port=port, path=parts.path, body=body, headers=headers,
                        timeout=timeout, addresses=lambda limit: resolve_within(self._resolver, host, port, limit),
                        connector=self._connector, ssl_context=self._ssl_context)
