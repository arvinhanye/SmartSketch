"""K07 lifecycle checks using only temporary files and a fake container command."""

from __future__ import annotations

import os
import pty
import shutil
import stat
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ("_dev-common.sh", "dev-up.sh", "check-apoc.sh")
ENV_BYTES = (
    b"# personal config; preserve whitespace and line endings\r\n"
    b"NEO4J_USER=neo4j\r\n"
    b"NEO4J_PASSWORD=custom-local-password\r\n"
    b"STORAGE_DIR=./custom-storage\r\n"
    b"# untouched custom field\r\n"
)
FAKE_DOCKER = """#!/usr/bin/env bash
printf '%s\\n' "$*" >> "$FAKE_LOG"
case "$*" in
  "compose version"*) echo 'Docker Compose version fake' ;;
  info*) exit 0 ;;
  "compose ps -q neo4j") echo fakecid ;;
  inspect*) echo healthy ;;
  "compose exec"*) echo 'apoc_version'; echo '"5.26.0"' ;;
  *) exit 0 ;;
esac
"""


def sandbox(tmp_path: Path, *, env_bytes: bytes | None = ENV_BYTES) -> tuple[Path, dict[str, str], Path]:
    root = tmp_path / "repo"
    for name in SCRIPTS + (("dev-down.sh",) if (ROOT / "scripts/dev-down.sh").exists() else ()):
        target = root / "scripts" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / "scripts" / name, target)
    (root / ".env.example").write_text("NEO4J_PASSWORD=example\n", encoding="utf-8")
    if env_bytes is not None:
        (root / ".env").write_bytes(env_bytes)
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    docker = bin_dir / "docker"
    docker.write_text(FAKE_DOCKER, encoding="utf-8")
    docker.chmod(docker.stat().st_mode | stat.S_IXUSR)
    log = tmp_path / "docker.log"
    env = {k: v for k, v in os.environ.items() if not k.startswith(("NEO4J_", "COMPOSE_", "STORAGE_DIR"))}
    env.update(PATH=f"{bin_dir}{os.pathsep}{env['PATH']}", FAKE_LOG=str(log))
    return root, env, log


def run_script(root: Path, env: dict[str, str], name: str, *args: str, tty_input: str | None = None) -> subprocess.CompletedProcess[str]:
    command = ["bash", str(root / "scripts" / name), *args]
    if tty_input is None:
        return subprocess.run(command, cwd=root, env=env, input="", text=True, capture_output=True, timeout=10)
    master, slave = pty.openpty()
    try:
        process = subprocess.Popen(command, cwd=root, env=env, stdin=slave, stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE, text=True)
        os.close(slave)
        slave = -1
        os.write(master, tty_input.encode())
        out, err = process.communicate(timeout=10)
        return subprocess.CompletedProcess(command, process.returncode, out, err)
    finally:
        os.close(master)
        if slave >= 0:
            os.close(slave)


def calls(log: Path) -> list[str]:
    return log.read_text().splitlines() if log.exists() else []


def assert_no_volume_removal(log: Path) -> None:
    assert not any(" -v" in f" {call}" or "--volumes" in call for call in calls(log))


def test_default_stop_preserves_data_and_avoids_volume_flags(tmp_path: Path):
    root, env, log = sandbox(tmp_path)
    data = root / "neo4j/data/probe"
    data.parent.mkdir(parents=True)
    data.write_bytes(b"persistent")

    result = run_script(root, env, "dev-down.sh")

    assert result.returncode == 0, result.stderr
    assert any(call == "compose stop neo4j" or call == "compose down" for call in calls(log))
    assert_no_volume_removal(log)
    assert data.read_bytes() == b"persistent"


def test_confirmed_destroy_requires_exact_interactive_phrase(tmp_path: Path):
    root, env, log = sandbox(tmp_path)
    for relative in ("neo4j/data/probe", "neo4j/logs/probe", "storage/keep"):
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"fixture")

    result = run_script(root, env, "dev-down.sh", "--destroy", tty_input="DELETE NEO4J DATA\n")

    assert result.returncode == 0, result.stderr
    assert any(call in ("compose down -v", "compose down --volumes") for call in calls(log))
    # F01 uses bind mounts: deleting Compose-managed volumes does not erase these paths.
    for relative in ("neo4j/data/probe", "neo4j/logs/probe", "storage/keep"):
        assert (root / relative).read_bytes() == b"fixture"


@pytest.mark.parametrize("answer", ["no\n", "delete neo4j data\n", "DELETE NEO4J DATA extra\n"])
def test_declined_or_inexact_destroy_keeps_volumes(tmp_path: Path, answer: str):
    root, env, log = sandbox(tmp_path)

    result = run_script(root, env, "dev-down.sh", "--destroy", tty_input=answer)

    assert result.returncode != 0
    assert_no_volume_removal(log)


def test_noninteractive_destroy_keeps_volumes_even_with_matching_input(tmp_path: Path):
    root, env, log = sandbox(tmp_path)
    result = subprocess.run(["bash", str(root / "scripts/dev-down.sh"), "--destroy"], cwd=root,
                            env=env, input="DELETE NEO4J DATA\n", text=True, capture_output=True, timeout=10)
    assert result.returncode != 0
    assert_no_volume_removal(log)


@pytest.mark.parametrize("name", ["dev-up.sh", "dev-down.sh"])
def test_missing_env_reports_setup_and_never_operates_on_containers(tmp_path: Path, name: str):
    root, env, log = sandbox(tmp_path, env_bytes=None)

    result = run_script(root, env, name)

    assert result.returncode != 0
    assert "cp .env.example .env" in result.stderr
    assert not any("compose up" in call or "compose stop" in call or "compose down" in call for call in calls(log))


def test_existing_env_bytes_survive_start_and_stop(tmp_path: Path):
    root, env, log = sandbox(tmp_path)
    before = (root / ".env").read_bytes()

    started = run_script(root, env, "dev-up.sh")
    stopped = run_script(root, env, "dev-down.sh")

    assert started.returncode == 0, started.stderr
    assert stopped.returncode == 0, stopped.stderr
    assert (root / ".env").read_bytes() == before
    assert (root / "custom-storage").is_dir()
    assert any(call.startswith("compose up -d neo4j") for call in calls(log))


def test_env_file_is_not_executed_as_shell_code(tmp_path: Path):
    root, env, _ = sandbox(tmp_path, env_bytes=ENV_BYTES + b"MALICIOUS=$(touch pwned)\n")

    result = run_script(root, env, "dev-up.sh")

    assert result.returncode == 0, result.stderr
    assert not (root / "pwned").exists()


def test_unknown_destroy_option_fails_without_stopping(tmp_path: Path):
    root, env, log = sandbox(tmp_path)

    result = run_script(root, env, "dev-down.sh", "--destructive")

    assert result.returncode != 0
    assert not any("compose stop" in call or "compose down" in call for call in calls(log))


def test_missing_env_hint_precedes_engine_probe(tmp_path: Path):
    root, env, _ = sandbox(tmp_path, env_bytes=None)
    # No fake Docker (and no Docker Desktop shim) should be needed to give setup guidance.
    env["PATH"] = "/usr/bin:/bin"

    result = run_script(root, env, "dev-up.sh")

    assert result.returncode != 0
    assert "cp .env.example .env" in result.stderr


def test_invalid_wait_setting_fails_before_start(tmp_path: Path):
    root, env, log = sandbox(tmp_path, env_bytes=ENV_BYTES + b"NEO4J_WAIT_SECONDS=not-a-number\n")

    result = run_script(root, env, "dev-up.sh")

    assert result.returncode != 0
    assert "NEO4J_WAIT_SECONDS" in result.stderr
    assert not any(call.startswith("compose up") for call in calls(log))


def test_unquoted_storage_inline_comment_is_not_part_of_directory(tmp_path: Path):
    content = ENV_BYTES.replace(b"STORAGE_DIR=./custom-storage\r\n", b"STORAGE_DIR=./data # note\r\n")
    root, env, _ = sandbox(tmp_path, env_bytes=content)

    result = run_script(root, env, "dev-up.sh")

    assert result.returncode == 0, result.stderr
    assert (root / "data").is_dir()
    assert not (root / "data # note").exists()
    assert (root / ".env").read_bytes() == content


def test_unquoted_wait_inline_comment_is_accepted(tmp_path: Path):
    content = ENV_BYTES + b"NEO4J_WAIT_SECONDS=30 # note\r\n"
    root, env, log = sandbox(tmp_path, env_bytes=content)

    result = run_script(root, env, "dev-up.sh")

    assert result.returncode == 0, result.stderr
    assert any(call.startswith("compose up -d neo4j") for call in calls(log))
    assert (root / ".env").read_bytes() == content


@pytest.mark.parametrize(
    "setting",
    [
        b'STORAGE_DIR="./data # literal" # note\r\n',
        b"STORAGE_DIR='./data # literal' # note\r\n",
    ],
)
def test_quoted_storage_keeps_hash_and_strips_comment_after_quote(
    tmp_path: Path, setting: bytes,
):
    content = ENV_BYTES.replace(b"STORAGE_DIR=./custom-storage\r\n", setting)
    root, env, _ = sandbox(tmp_path, env_bytes=content)

    result = run_script(root, env, "dev-up.sh")

    assert result.returncode == 0, result.stderr
    assert (root / "data # literal").is_dir()
    assert (root / ".env").read_bytes() == content


def test_hash_without_preceding_space_stays_literal(tmp_path: Path):
    content = ENV_BYTES.replace(b"STORAGE_DIR=./custom-storage\r\n", b"STORAGE_DIR=./data#tag\r\n")
    root, env, _ = sandbox(tmp_path, env_bytes=content)

    result = run_script(root, env, "dev-up.sh")

    assert result.returncode == 0, result.stderr
    assert (root / "data#tag").is_dir()
    assert (root / ".env").read_bytes() == content
