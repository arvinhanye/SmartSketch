"""Outbound guard for user-supplied model endpoints (ADR-080 决定 5).

A user controls ``base_url``, so every connection is made only after the host has been
resolved and every resolved address is public; the socket then connects to that checked
address (TLS still verifies the original host name), so a DNS answer that changes between
check and connect has no effect. Redirects are never followed (``compatible.py`` treats a
3xx as a malformed response).
"""

from __future__ import annotations

import http.client
import ipaddress
import socket
import ssl
from collections.abc import Callable, Mapping
from urllib.parse import SplitResult, urlsplit

from app.config import Settings
from app.services.ai.compatible import HttpResponse, _StdlibResponse

Resolver = Callable[[str, int], list[str]]


class EndpointBlocked(OSError):
    """The endpoint is refused; ``reason`` is machine-readable and safe to show."""

    def __init__(self, reason: str) -> None:
        super().__init__(f"model endpoint blocked: {reason}")
        self.reason = reason


def system_resolver(host: str, port: int) -> list[str]:
    infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    return list(dict.fromkeys(str(info[4][0]) for info in infos))


def is_public_address(value: str) -> bool:
    try:
        address = ipaddress.ip_address(value.split("%", 1)[0])
    except ValueError:
        return False
    mapped = getattr(address, "ipv4_mapped", None)
    if mapped is not None:
        address = mapped
    return address.is_global and not address.is_multicast


def check_endpoint_url(url: str, *, allow_private: bool = False) -> SplitResult:
    if not isinstance(url, str) or not url or any(c.isspace() or ord(c) < 32 for c in url):
        raise EndpointBlocked("host")
    try:
        parts = urlsplit(url)
        port = parts.port
    except ValueError:
        raise EndpointBlocked("port") from None
    if parts.scheme != "https" and not (allow_private and parts.scheme == "http"):
        raise EndpointBlocked("scheme")
    if parts.username is not None or parts.password is not None:
        raise EndpointBlocked("credentials")
    if not parts.hostname:
        raise EndpointBlocked("host")
    if port == 0:
        raise EndpointBlocked("port")
    if parts.query or parts.fragment or url.endswith(("?", "#")):
        raise EndpointBlocked("query")
    return parts


def _default_port(parts: SplitResult) -> int:
    return parts.port or (443 if parts.scheme == "https" else 80)


def resolve_endpoint(host: str, port: int, *, allow_private: bool = False,
                     resolver: Resolver = system_resolver) -> list[str]:
    try:
        addresses = resolver(host, port)
    except OSError:
        raise EndpointBlocked("unresolvable") from None
    if not addresses:
        raise EndpointBlocked("unresolvable")
    if not allow_private and not all(is_public_address(address) for address in addresses):
        raise EndpointBlocked("private_address")
    return addresses


def check_endpoint(url: str, *, allow_private: bool = False, resolver: Resolver = system_resolver) -> None:
    parts = check_endpoint_url(url, allow_private=allow_private)
    resolve_endpoint(parts.hostname or "", _default_port(parts), allow_private=allow_private, resolver=resolver)


class _PinnedHTTPConnection(http.client.HTTPConnection):
    def __init__(self, host: str, port: int, *, ip: str, timeout: float) -> None:
        super().__init__(host, port, timeout=timeout)
        self._pinned_ip = ip

    def connect(self) -> None:
        self.sock = socket.create_connection((self._pinned_ip, self.port), self.timeout)


class _PinnedHTTPSConnection(http.client.HTTPSConnection):
    def __init__(self, host: str, port: int, *, ip: str, timeout: float, context: ssl.SSLContext) -> None:
        super().__init__(host, port, timeout=timeout, context=context)
        self._pinned_ip = ip
        self._pinned_context = context

    def connect(self) -> None:
        sock = socket.create_connection((self._pinned_ip, self.port), self.timeout)
        self.sock = self._pinned_context.wrap_socket(sock, server_hostname=self.host)


class GuardedTransport:
    """``HttpTransport`` that resolves, checks and pins on every ``open``."""

    def __init__(self, *, allow_private: bool = False, resolver: Resolver = system_resolver,
                 ssl_context: ssl.SSLContext | None = None) -> None:
        self._allow_private = allow_private
        self._resolver = resolver
        self._ssl_context = ssl_context

    def open(self, url: str, body: bytes, headers: Mapping[str, str], timeout: float) -> HttpResponse:
        parts = check_endpoint_url(url, allow_private=self._allow_private)
        host, port = parts.hostname or "", _default_port(parts)
        ip = resolve_endpoint(host, port, allow_private=self._allow_private, resolver=self._resolver)[0]
        connection: http.client.HTTPConnection
        if parts.scheme == "https":
            context = self._ssl_context or ssl.create_default_context()
            connection = _PinnedHTTPSConnection(host, port, ip=ip, timeout=timeout, context=context)
        else:
            connection = _PinnedHTTPConnection(host, port, ip=ip, timeout=timeout)
        try:
            connection.request("POST", parts.path or "/", body=body, headers=dict(headers))
            sock = connection.sock
            response = connection.getresponse()
        except BaseException:
            connection.close()
            raise
        return _StdlibResponse(connection, sock, response)


def build_transport(settings: Settings) -> GuardedTransport:
    return GuardedTransport(allow_private=settings.MODEL_ENDPOINT_ALLOW_PRIVATE)
