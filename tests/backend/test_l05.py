"""L05：用户填写的模型地址——语法、公网判定、解析后校验与钉 IP（ADR-080 决定 5）。"""
from __future__ import annotations

import http.server
import json
import threading

import pytest

from app.services.ai.client import Message, ModelMalformedResponseError, ModelRequest
from app.services.ai.compatible import CompatibleModelClient
from app.services.ai.outbound import (
    EndpointBlocked,
    GuardedTransport,
    check_endpoint,
    check_endpoint_url,
    is_public_address,
)


@pytest.mark.parametrize("address", [
    "127.0.0.1", "10.0.0.5", "172.16.3.4", "192.168.1.1", "169.254.169.254", "100.64.0.1", "0.0.0.0",
    "224.0.0.1", "::1", "fe80::1", "fc00::1", "::ffff:127.0.0.1", "::ffff:10.0.0.1", "not-an-ip",
])
def test_non_public_addresses(address):
    assert is_public_address(address) is False


@pytest.mark.parametrize("address", ["1.1.1.1", "8.8.8.8", "2606:4700:4700::1111"])
def test_public_addresses(address):
    assert is_public_address(address) is True


@pytest.mark.parametrize("url, reason", [
    ("http://api.example.com/v1", "scheme"),
    ("ftp://api.example.com/v1", "scheme"),
    ("https://user:pw@api.example.com/v1", "credentials"),
    ("https://api.example.com/v1?x=1", "query"),
    ("https://api.example.com/v1#frag", "query"),
    ("https:///v1", "host"),
    ("https://api.example.com:0/v1", "port"),
    ("https://api.exam ple.com/v1", "host"),
])
def test_url_syntax_rejections(url, reason):
    with pytest.raises(EndpointBlocked) as caught:
        check_endpoint_url(url)
    assert caught.value.reason == reason


def test_http_only_with_allow_private():
    assert check_endpoint_url("http://127.0.0.1:9000/v1", allow_private=True).scheme == "http"


def test_resolution_rules():
    def to(addresses):
        return lambda host, port: addresses

    check_endpoint("https://api.example.com/v1", resolver=to(["1.1.1.1"]))
    with pytest.raises(EndpointBlocked) as caught:
        check_endpoint("https://api.example.com/v1", resolver=to(["1.1.1.1", "10.0.0.1"]))
    assert caught.value.reason == "private_address"
    with pytest.raises(EndpointBlocked) as caught:
        check_endpoint("https://api.example.com/v1", resolver=to([]))
    assert caught.value.reason == "unresolvable"

    def failing(host, port):
        raise OSError("no such host")

    with pytest.raises(EndpointBlocked) as caught:
        check_endpoint("https://api.example.com/v1", resolver=failing)
    assert caught.value.reason == "unresolvable"
    check_endpoint("https://internal.test/v1", allow_private=True, resolver=to(["127.0.0.1"]))


class _Provider(http.server.BaseHTTPRequestHandler):
    hosts: list[str] = []
    status = 200

    def do_POST(self):  # noqa: N802
        type(self).hosts.append(self.headers.get("Host", ""))
        self.rfile.read(int(self.headers.get("Content-Length", "0")))
        if type(self).status != 200:
            self.send_response(type(self).status)
            self.send_header("Location", "http://127.0.0.1:1/elsewhere")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        body = json.dumps({"model": "m", "choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}],
                           "usage": {"prompt_tokens": 1, "completion_tokens": 1}}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


@pytest.fixture
def provider():
    _Provider.hosts, _Provider.status = [], 200
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Provider)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield server.server_address[1]
    server.shutdown()
    thread.join()


def _request():
    return ModelRequest(purpose="config_test", model="m", messages=(Message("user", "ping"),), max_output_tokens=1)


def test_transport_connects_to_the_checked_address_only(provider):
    calls = []

    def resolver(host, port):
        calls.append(host)
        return ["127.0.0.1"]

    transport = GuardedTransport(allow_private=True, resolver=resolver)
    client = CompatibleModelClient(f"http://model.test:{provider}/v1", "sk-test", transport=transport)
    assert client.complete(_request()).text == "ok"
    # "model.test" does not resolve on this machine: reaching the server proves the checked IP was used.
    assert _Provider.hosts == [f"model.test:{provider}"]
    assert calls == ["model.test"]


def test_transport_blocks_private_address_without_connecting(provider):
    transport = GuardedTransport(resolver=lambda host, port: ["127.0.0.1"])
    with pytest.raises(EndpointBlocked) as caught:
        transport.open(f"https://model.test:{provider}/v1/chat/completions", b"{}", {}, 2)
    assert caught.value.reason == "private_address"
    assert _Provider.hosts == []


def test_redirect_is_not_followed(provider):
    _Provider.status = 302
    transport = GuardedTransport(allow_private=True, resolver=lambda host, port: ["127.0.0.1"])
    client = CompatibleModelClient(f"http://model.test:{provider}/v1", "sk-test", transport=transport)
    with pytest.raises(ModelMalformedResponseError):
        client.complete(_request())
    assert len(_Provider.hosts) == 1


def test_stdlib_transport_survives_a_server_that_closes_the_connection(provider):
    """回归：服务端读完即关闭连接（HTTP/1.0 或 Connection: close）时，读完响应后不得再碰已关闭的套接字。"""
    from app.services.ai.compatible import StdlibTransport

    client = CompatibleModelClient(f"http://127.0.0.1:{provider}/v1", "sk-test", transport=StdlibTransport())
    assert client.complete(_request()).text == "ok"
