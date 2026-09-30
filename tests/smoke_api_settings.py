"""Minimal local API acceptance checks. Does not call any model provider."""
import json
import socket
from urllib.request import Request, urlopen
from urllib.error import HTTPError

def call(path, method="GET", body=None, token=None):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = "Bearer " + token
    request = Request("http://127.0.0.1:18080" + path, data=json.dumps(body).encode() if body is not None else None, headers=headers, method=method)
    try:
        with urlopen(request, timeout=10) as response:
            return response.status, json.load(response)
    except HTTPError as error:
        return error.code, json.load(error)

path = "/api/v1/api-settings"
try:
    with socket.create_connection(("127.0.0.1", 18080), timeout=1):
        pass
except OSError:
    print("SKIP: local service is not running")
    raise SystemExit(0)
assert call(path)[0] == 401
tokens = {}
for role in ("teacher", "student"):
    status, response = call("/api/v1/auth/login", "POST", {"username": "demo_" + role, "password": "smartsketch-demo"})
    assert status == 200
    tokens[role] = response["access_token"]
assert call(path, token=tokens["student"])[0] == 403
status, settings = call(path, token=tokens["teacher"])
assert status == 200
assert "LLM_API_KEY" not in settings and "EMBEDDING_API_KEY" not in settings
assert settings["LLM_API_KEY_configured"] and settings["EMBEDDING_API_KEY_configured"]
assert settings["active"]["LLM_MODE"] == "live"
assert settings["active"]["EMBEDDING_MODE"] == "demo"
assert call(path, "PUT", {"LLM_API_KEY": "", "EMBEDDING_API_KEY": ""}, tokens["teacher"])[0] == 200
assert call(path, "PUT", {"EMBEDDING_MODE": "online"}, tokens["teacher"])[0] == 400
print("PASS: authentication, role permissions, secret redaction, blank-key preservation, active modes, migration guard")
status, discovery = call(path + "/models", "POST", {"kind": "llm", "LLM_BASE_URL": ""}, tokens["teacher"])
assert status == 200 and discovery["ok"] is False
assert {"models", "count", "latency_ms", "provider", "error"} <= discovery.keys()
status, result = call(path + "/test", "POST", {"kind": "embedding", "EMBEDDING_BASE_URL": ""}, tokens["teacher"])
assert status == 200 and result["ok"] is False
assert {"latency_ms", "http_status", "detail", "provider", "error"} <= result.keys()
print("PASS: model discovery and structured connection result, no provider calls")
