"""B05: FastAPI factory and health contract checks."""

import socket
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import APP_VERSION, create_app
from app.repositories.sqlite import migrate


def _isolated_sqlite(tmp_path, monkeypatch):
    url = f"sqlite:///{(tmp_path / 'state.sqlite3').as_posix()}"
    migrate(url)   # REVIEW-C01-R02：API 启动要求迁移已是最新
    monkeypatch.setenv("SQLITE_URL", url)


def test_factory_needs_no_secrets_or_network(tmp_path, monkeypatch):
    _isolated_sqlite(tmp_path, monkeypatch)
    for name in ("NEO4J_PASSWORD", "LLM_API_KEY", "AUTH_JWT_SECRET"):
        monkeypatch.delenv(name, raising=False)

    with patch.object(socket.socket, "connect", side_effect=AssertionError("network used")):
        first = create_app()
        second = create_app()

    with TestClient(first) as client:
        response = client.get("/health")

    assert first is not second
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "version": APP_VERSION}


def test_health_contract_is_public_and_versioned(tmp_path, monkeypatch):
    _isolated_sqlite(tmp_path, monkeypatch)
    application = create_app()
    with TestClient(application) as client:
        response = client.get("/health")

    assert response.headers["content-type"].startswith("application/json")
    assert response.json() == {"status": "ok", "version": application.version}

    operation = application.openapi()["paths"]["/health"]["get"]
    assert operation["operationId"] == "getHealth"
    assert not operation.get("security")
    response_schema = operation["responses"]["200"]["content"]["application/json"]["schema"]
    schema = application.openapi()["components"]["schemas"][response_schema["$ref"].split("/")[-1]]
    assert set(schema["required"]) == {"status", "version"}
    assert schema["properties"]["status"].get("const") == "ok"


def test_health_path_and_method_boundaries(tmp_path, monkeypatch):
    _isolated_sqlite(tmp_path, monkeypatch)
    with TestClient(create_app()) as client:
        assert client.get("/api/v1/health").status_code == 404
        assert client.post("/health").status_code == 405
