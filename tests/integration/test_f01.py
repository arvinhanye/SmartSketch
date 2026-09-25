"""F01: local Neo4j environment — compose file, dev-up and APOC check.

Two layers:

* Script behaviour runs everywhere against a fake ``docker`` on PATH that records every call,
  so the checks (missing .env, unhealthy container, missing APOC, password never on a
  command line) need no container engine.
* ``TestRealContainer`` starts a real Neo4j in an isolated sandbox (its own compose project,
  free ports and data directory) and is skipped when no Docker daemon answers. It pulls the
  ``neo4j:5.26-community`` image on first run. Set ``SMARTSKETCH_SKIP_DOCKER=1`` to skip it.
"""

from __future__ import annotations

import os
import shutil
import socket
import stat
import subprocess
import uuid
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SANDBOX_FILES = (
    "docker-compose.yml",
    ".env.example",
    "scripts/_dev-common.sh",
    "scripts/dev-up.sh",
    "scripts/check-apoc.sh",
)
PASSWORD = "f01-sandbox-password"

FAKE_DOCKER = r"""#!/usr/bin/env bash
# Records argv (one call per line) and answers like a docker CLI with a running daemon.
printf '%s\n' "$*" >> "$FAKE_LOG"
case "$*" in
  "compose version"*) echo "Docker Compose version v2.99.0-fake" ;;
  info*) exit 0 ;;
  "compose up"*) exit 0 ;;
  "compose ps -q neo4j") echo "fakecid" ;;
  inspect*) echo "${FAKE_HEALTH:-healthy}" ;;
  "compose exec"*)
    if [[ ${FAKE_APOC:-ok} == ok ]]; then echo "apoc_version"; echo '"5.26.0"'; exit 0; fi
    echo "Unknown function 'apoc.version'" >&2; exit 1 ;;
  *) exit 0 ;;
esac
"""


def _sandbox(tmp_path: Path, env_lines: dict[str, str] | None = None) -> Path:
    root = tmp_path / "repo"
    for name in SANDBOX_FILES:
        target = root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / name, target)
    if env_lines is not None:
        text = (root / ".env.example").read_text(encoding="utf-8")
        text += "".join(f"\n{key}={value}" for key, value in env_lines.items()) + "\n"
        (root / ".env").write_text(text, encoding="utf-8")
    return root


def _fake_bin(tmp_path: Path) -> Path:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    docker = bin_dir / "docker"
    docker.write_text(FAKE_DOCKER, encoding="utf-8")
    docker.chmod(docker.stat().st_mode | stat.S_IXUSR)
    return bin_dir


def _env(extra_path: Path | None = None, **extra: str) -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if not k.startswith(("NEO4J_", "COMPOSE_"))}
    if extra_path is not None:
        env["PATH"] = f"{extra_path}{os.pathsep}{env['PATH']}"
    env.update(extra)
    return env


def _run(root: Path, script: str, env: dict[str, str], timeout: int = 60):
    return subprocess.run(
        ["bash", str(root / "scripts" / script)],
        cwd=root,
        env=env,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


# --- script behaviour against a fake docker -------------------------------------------------


@pytest.mark.parametrize("script", ["_dev-common.sh", "dev-up.sh", "check-apoc.sh"])
def test_scripts_parse(script):
    assert subprocess.run(["bash", "-n", str(ROOT / "scripts" / script)]).returncode == 0


def test_dev_up_without_env_file_exits_with_hint_and_starts_nothing(tmp_path):
    root = _sandbox(tmp_path)
    log = tmp_path / "docker.log"

    result = _run(root, "dev-up.sh", _env(_fake_bin(tmp_path), FAKE_LOG=str(log)))

    assert result.returncode != 0
    assert "cp .env.example .env" in result.stderr
    assert "compose up" not in log.read_text() if log.exists() else True


def test_dev_up_waits_for_healthy_then_checks_apoc(tmp_path):
    root = _sandbox(tmp_path, {"NEO4J_PASSWORD": PASSWORD})
    log = tmp_path / "docker.log"

    result = _run(root, "dev-up.sh", _env(_fake_bin(tmp_path), FAKE_LOG=str(log)))

    assert result.returncode == 0, result.stderr
    calls = log.read_text().splitlines()
    assert any(c.startswith("compose up -d neo4j") for c in calls)
    assert any(c.startswith("compose exec -T neo4j") for c in calls)
    assert (root / "neo4j" / "data").is_dir() and (root / "storage").is_dir()
    assert "5.26" in result.stdout


def test_unhealthy_container_is_not_reported_ready(tmp_path):
    root = _sandbox(tmp_path, {"NEO4J_PASSWORD": PASSWORD})
    log = tmp_path / "docker.log"

    result = _run(
        root, "dev-up.sh", _env(_fake_bin(tmp_path), FAKE_LOG=str(log), FAKE_HEALTH="unhealthy")
    )

    assert result.returncode != 0
    assert "logs neo4j" in result.stderr
    assert not any(c.startswith("compose exec") for c in log.read_text().splitlines())


def test_missing_apoc_fails_with_hint(tmp_path):
    root = _sandbox(tmp_path, {"NEO4J_PASSWORD": PASSWORD})
    log = tmp_path / "docker.log"

    result = _run(
        root, "check-apoc.sh", _env(_fake_bin(tmp_path), FAKE_LOG=str(log), FAKE_APOC="missing")
    )

    assert result.returncode != 0
    assert "APOC" in result.stderr


def test_password_never_appears_on_a_host_command_line(tmp_path):
    root = _sandbox(tmp_path, {"NEO4J_PASSWORD": PASSWORD})
    log = tmp_path / "docker.log"

    result = _run(root, "dev-up.sh", _env(_fake_bin(tmp_path), FAKE_LOG=str(log)))

    assert result.returncode == 0, result.stderr
    assert PASSWORD not in log.read_text()
    assert PASSWORD not in result.stdout + result.stderr


def test_compose_file_keeps_data_in_ignored_paths_and_has_no_fixed_container_name():
    compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")

    assert "container_name" not in compose  # sandboxes and worktrees need their own project
    assert "./neo4j/data:/data" in compose and "./neo4j/logs:/logs" in compose
    assert "NEO4J_PLUGINS" in compose and "apoc" in compose
    ignored = (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert {"neo4j/data/", "neo4j/logs/", "storage/"} <= set(ignored)


# --- real container ---------------------------------------------------------------------------


def _docker_available() -> bool:
    if os.environ.get("SMARTSKETCH_SKIP_DOCKER") == "1" or shutil.which("docker") is None:
        return False
    return subprocess.run(["docker", "info"], capture_output=True).returncode == 0


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


needs_docker = pytest.mark.skipif(not _docker_available(), reason="no Docker daemon available")


@needs_docker
def test_compose_config_requires_a_password(tmp_path):
    root = _sandbox(tmp_path)
    (root / ".env").write_text("NEO4J_PASSWORD=\n", encoding="utf-8")

    result = subprocess.run(
        ["docker", "compose", "config"], cwd=root, env=_env(), capture_output=True, text=True
    )

    assert result.returncode != 0
    assert "NEO4J_PASSWORD" in result.stderr


@needs_docker
class TestRealContainer:
    @pytest.fixture(scope="class")
    def sandbox(self, tmp_path_factory):
        tmp_path = tmp_path_factory.mktemp("f01")
        project = f"smartsketch-f01-{uuid.uuid4().hex[:8]}"
        root = _sandbox(
            tmp_path,
            {
                "NEO4J_PASSWORD": PASSWORD,
                "NEO4J_BOLT_PORT": str(_free_port()),
                "NEO4J_HTTP_PORT": str(_free_port()),
                "COMPOSE_PROJECT_NAME": project,
            },
        )
        env = _env(COMPOSE_PROJECT_NAME=project)
        yield root, env
        subprocess.run(
            ["docker", "compose", "down", "-v", "--remove-orphans"],
            cwd=root, env=env, capture_output=True, timeout=120,
        )

    def _cypher(self, root: Path, env: dict[str, str], query: str) -> str:
        result = subprocess.run(
            [
                "docker", "compose", "exec", "-T", "neo4j", "sh", "-c",
                'NEO4J_USERNAME="${NEO4J_AUTH%%/*}" NEO4J_PASSWORD="${NEO4J_AUTH#*/}" '
                'exec cypher-shell --format plain "$1"',
                "cypher", query,
            ],
            cwd=root, env=env, capture_output=True, text=True, timeout=60,
        )
        assert result.returncode == 0, result.stderr
        return result.stdout

    def test_dev_up_starts_healthy_neo4j_with_apoc(self, sandbox):
        root, env = sandbox

        result = _run(root, "dev-up.sh", env, timeout=600)

        assert result.returncode == 0, result.stdout + result.stderr
        assert "APOC" in result.stdout and "5.26" in result.stdout
        assert PASSWORD not in result.stdout + result.stderr

    def test_data_survives_stop_and_start(self, sandbox):
        root, env = sandbox
        marker = uuid.uuid4().hex
        self._cypher(root, env, f"CREATE (:F01Probe {{marker: '{marker}'}})")

        down = subprocess.run(
            ["docker", "compose", "down"], cwd=root, env=env, capture_output=True, timeout=120
        )
        assert down.returncode == 0
        again = _run(root, "dev-up.sh", env, timeout=600)
        assert again.returncode == 0, again.stdout + again.stderr

        out = self._cypher(root, env, f"MATCH (p:F01Probe {{marker: '{marker}'}}) RETURN count(p)")
        assert out.strip().splitlines()[-1] == "1"
