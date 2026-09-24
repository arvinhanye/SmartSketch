"""B06: environment-only settings and startup validation."""

import os
import sqlite3
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.config import Settings, SettingsError, load_settings
from app.main import create_app
from app.services.startup import validate_embedding_space


def test_fake_defaults_need_no_model_secrets_or_network():
    settings = load_settings({})

    assert settings.LLM_MODE == "fake"
    assert settings.EMBEDDING_MODE == "fake"
    assert settings.API_PORT == 8000
    assert settings.EMBEDDING_DIMENSIONS == 1024
    assert settings.LLM_API_KEY.get_secret_value() == ""


def test_env_example_covers_every_setting():
    env_example = Path(__file__).parents[2] / ".env.example"
    entries = dict(
        line.split("=", 1)
        for line in env_example.read_text(encoding="utf-8").splitlines()
        if line and not line.startswith("#")
    )

    assert set(entries) == set(Settings.model_fields)
    assert load_settings(entries).PUBLISH_LEASE_SECONDS == 60


def test_zero_values_with_defined_meanings_are_valid():
    settings = load_settings(
        {
            "LLM_TASK_TOKEN_BUDGET": "0",
            "LLM_DAILY_TOKEN_BUDGET": "0",
            "TASK_MAX_FAILED_CHUNK_RATIO": "0",
            "TASK_ARTIFACT_RETENTION_DAYS": "0",
            "COURSE_LOCK_WAIT_SECONDS": "0",
        }
    )

    assert settings.LLM_TASK_TOKEN_BUDGET == 0
    assert settings.TASK_MAX_FAILED_CHUNK_RATIO == 0
    assert settings.COURSE_LOCK_WAIT_SECONDS == 0


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("API_PORT", "0"),
        ("API_PORT", "65536"),
        ("API_PORT", "not-a-port"),
        ("LLM_TASK_TOKEN_BUDGET", "-1"),
        ("LLM_DAILY_TOKEN_BUDGET", "-1"),
        ("EMBEDDING_DIMENSIONS", "0"),
        ("EMBEDDING_BATCH_SIZE", "0"),
        ("TASK_MAX_FAILED_CHUNK_RATIO", "1"),
        ("TASK_MAX_FAILED_CHUNK_RATIO", "nan"),
        ("TASK_LEASE_SECONDS", "14"),
        ("PUBLISH_LEASE_SECONDS", "14"),
        ("COURSE_LOCK_WAIT_SECONDS", "-1"),
        ("LLM_REQUEST_TIMEOUT_SECONDS", "0"),
        ("LLM_MAX_RETRIES", "-1"),
    ],
)
def test_invalid_ranges_name_the_variable(name, value):
    with pytest.raises(SettingsError, match=name):
        load_settings({name: value})


@pytest.mark.parametrize(
    ("values", "name"),
    [
        ({"APP_ENV": "staging"}, "APP_ENV"),
        ({"LLM_MODE": "real"}, "LLM_MODE"),
        ({"LLM_MODE": "live"}, "LLM_BASE_URL"),
        ({"LLM_FALLBACK_API_KEY": "backup-key"}, "LLM_FALLBACK_BASE_URL"),
        ({"EMBEDDING_MODE": "online"}, "EMBEDDING_API_KEY"),
        ({"EMBEDDING_MODE": "local"}, "EMBEDDING_MODEL"),
        ({"APP_ENV": "production"}, "LLM_MODE"),
        ({"LLM_CHAT_FIRST_TOKEN_TIMEOUT_SECONDS": "15"}, "LLM_CHAT_TIMEOUT_SECONDS"),
        ({"WEB_ORIGIN": "not-a-url"}, "WEB_ORIGIN"),
        ({"WEB_ORIGIN": ""}, "WEB_ORIGIN"),
        ({"WEB_ORIGIN": "http://bad host:5173"}, "WEB_ORIGIN"),
        ({"WEB_ORIGIN": "http://localhost:5173/path"}, "WEB_ORIGIN"),
        ({"WEB_ORIGIN": "http://user:secret@localhost:5173"}, "WEB_ORIGIN"),
        ({"NEO4J_URI": "http://localhost:7687"}, "NEO4J_URI"),
        ({"SQLITE_URL": "postgres:///data"}, "SQLITE_URL"),
        ({"SQLITE_URL": "sqlite:///:memory:"}, "SQLITE_URL"),
        ({"LLM_BASE_URL": "https://:bad-host"}, "LLM_BASE_URL"),
    ],
)
def test_conditional_and_url_rules(values, name):
    with pytest.raises(SettingsError, match=name):
        load_settings(values)


def test_complete_live_configuration_is_typed_and_redacted():
    settings = load_settings(
        {
            "APP_ENV": "production",
            "API_PORT": "8123",
            "LLM_MODE": "live",
            "LLM_BASE_URL": "https://model.example/v1",
            "LLM_API_KEY": "private-primary-key",
            "LLM_EXTRACTION_MODEL": "extract-v1",
            "LLM_CHAT_MODEL": "chat-v1",
            "EMBEDDING_MODE": "online",
            "EMBEDDING_BASE_URL": "https://embedding.example/v1",
            "EMBEDDING_API_KEY": "private-embedding-key",
            "EMBEDDING_MODEL": "embed-v1",
        }
    )

    assert settings.API_PORT == 8123
    assert settings.LLM_API_KEY.get_secret_value() == "private-primary-key"
    assert "private-primary-key" not in repr(settings)
    assert "private-embedding-key" not in repr(settings)


def test_complete_fallback_and_local_embedding_are_accepted():
    settings = load_settings(
        {
            "LLM_FALLBACK_BASE_URL": "https://backup.example/v1",
            "LLM_FALLBACK_API_KEY": "backup-key",
            "LLM_FALLBACK_EXTRACTION_MODEL": "backup-extract",
            "LLM_FALLBACK_CHAT_MODEL": "backup-chat",
            "EMBEDDING_MODE": "local",
            "EMBEDDING_MODEL": "local-embedding-v1",
        }
    )

    assert settings.LLM_FALLBACK_API_KEY.get_secret_value() == "backup-key"
    assert settings.EMBEDDING_MODE == "local"


def test_errors_and_logs_never_include_secret_values(caplog):
    secret = "secret-canary-do-not-log"
    with pytest.raises(SettingsError) as error:
        load_settings({"API_PORT": "bad-port", "LLM_API_KEY": secret})

    assert "API_PORT" in str(error.value)
    assert secret not in str(error.value)
    assert secret not in caplog.text


def test_invalid_environment_prevents_app_creation(monkeypatch):
    monkeypatch.setenv("API_PORT", "0")
    with pytest.raises(SettingsError, match="API_PORT"):
        create_app()


def test_module_import_rejects_invalid_startup_without_exposing_secret():
    secret = "startup-secret-canary"
    result = subprocess.run(
        [sys.executable, "-c", "import app.main"],
        env={**os.environ, "API_PORT": "0", "LLM_API_KEY": secret},
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode != 0
    assert "API_PORT" in result.stderr
    assert secret not in result.stderr


def test_valid_app_stores_settings_without_external_connections(monkeypatch):
    monkeypatch.setenv("API_PORT", "8123")
    application = create_app()

    assert application.state.settings.API_PORT == 8123


def test_first_start_persists_embedding_space_and_restarts_cleanly(tmp_path, monkeypatch):
    database = tmp_path / "state.sqlite3"
    monkeypatch.setenv("SQLITE_URL", f"sqlite:///{database.as_posix()}")

    with TestClient(create_app()) as client:
        assert client.get("/health").status_code == 200
    with sqlite3.connect(database) as connection:
        assert connection.execute(
            "SELECT model, dimensions, is_fake FROM embedding_space_state WHERE singleton = 1"
        ).fetchone() == ("", 1024, 1)
    with TestClient(create_app()) as client:
        assert client.get("/health").status_code == 200


def test_changed_embedding_space_rejects_startup_without_mutating_record(tmp_path, monkeypatch):
    database = tmp_path / "state.sqlite3"
    monkeypatch.setenv("SQLITE_URL", f"sqlite:///{database.as_posix()}")
    with TestClient(create_app()):
        pass

    monkeypatch.setenv("EMBEDDING_DIMENSIONS", "512")
    with pytest.raises(SettingsError, match="1024.*512.*重新向量化"):
        with TestClient(create_app()):
            pass
    with sqlite3.connect(database) as connection:
        assert connection.execute(
            "SELECT model, dimensions, is_fake FROM embedding_space_state WHERE singleton = 1"
        ).fetchone() == ("", 1024, 1)


def test_listener_uses_configured_host_and_port(monkeypatch):
    from app.__main__ import main as serve_main

    monkeypatch.setenv("API_HOST", "127.0.0.2")
    monkeypatch.setenv("API_PORT", "8123")
    with patch("uvicorn.run") as run:
        serve_main()
    assert run.call_args.kwargs["host"] == "127.0.0.2"
    assert run.call_args.kwargs["port"] == 8123


def test_worker_can_reuse_space_gate_and_model_changes_fail(tmp_path):
    sqlite_url = f"sqlite:///{(tmp_path / 'state.sqlite3').as_posix()}"
    validate_embedding_space(
        load_settings(
            {"SQLITE_URL": sqlite_url, "EMBEDDING_MODE": "local", "EMBEDDING_MODEL": "model-a"}
        )
    )
    with pytest.raises(SettingsError, match="model-a.*model-b.*重新向量化"):
        validate_embedding_space(
            load_settings(
                {"SQLITE_URL": sqlite_url, "EMBEDDING_MODE": "local", "EMBEDDING_MODEL": "model-b"}
            )
        )


RECOMMEND_WEIGHTS = (
    "RECOMMEND_WEIGHT_UNLOCK",
    "RECOMMEND_WEIGHT_IMPORTANCE",
    "RECOMMEND_WEIGHT_CHAPTER",
    "RECOMMEND_WEIGHT_EASE",
)


def _weights(*values):
    return dict(zip(RECOMMEND_WEIGHTS, values))


@pytest.mark.parametrize("values", [{}, _weights("", "", "", "")])
def test_unset_or_empty_recommend_weights_use_s2_defaults(values):
    assert load_settings(values).recommend_weights == (0.35, 0.25, 0.20, 0.20)


def test_complete_recommend_weights_are_used_in_fixed_order():
    settings = load_settings(_weights("0.4", "0.3", "0.2", "0.1"))

    assert settings.recommend_weights == (0.4, 0.3, 0.2, 0.1)


@pytest.mark.parametrize(
    "values",
    [
        {"RECOMMEND_WEIGHT_UNLOCK": "1"},
        _weights("0.5", "0.5", "", ""),
        _weights("-0.1", "0.5", "0.3", "0.3"),
        _weights("nan", "0.5", "0.3", "0.2"),
        _weights("inf", "0", "0", "0"),
        _weights("0", "0", "0", "0"),
        _weights("0.4", "0.3", "0.2", "0.2"),
        _weights("0.25", "0.25", "0.25", "0.2499"),
    ],
)
def test_invalid_recommend_weight_group_rejects_startup(values):
    with pytest.raises(SettingsError, match="RECOMMEND_WEIGHT_"):
        load_settings(values)
