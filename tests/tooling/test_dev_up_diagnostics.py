"""dev-up.sh 在 Neo4j 起不来时的诊断：端口预检、容器退出/反复重启、口令不一致、超时。

全部用记录调用的假 docker，不需要容器引擎。假 docker 按 inspect 的 --format 区分两种查询：
状态行（健康 状态 重启次数）取 FAKE_STATE，诊断行（含 ExitCode）取 FAKE_INFO。
"""

from __future__ import annotations

import os
import shutil
import socket
import stat
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ("_dev-common.sh", "dev-up.sh", "check-apoc.sh")
FAKE_DOCKER = r"""#!/usr/bin/env bash
printf '%s\n' "$*" >> "$FAKE_LOG"
case "$*" in
  "compose version"*) echo 'Docker Compose version fake' ;;
  info*) exit 0 ;;
  "compose ps -q neo4j") [[ -n ${FAKE_RUNNING_CID:-} ]] && echo "$FAKE_RUNNING_CID" ;;
  "compose ps -aq neo4j") echo fakecid ;;
  "compose logs"*) echo "${FAKE_LOGS:-neo4j-1  | INFO  Neo4j Server shutdown initiated by request}" ;;
  inspect*ExitCode*) echo "${FAKE_INFO:-Status=running ExitCode=0 OOMKilled=false RestartCount=0 Error=}" ;;
  inspect*)
    state="$FAKE_STATE"
    if [[ -n ${FAKE_COUNTER:-} ]]; then
      # 每查一次状态重启次数加一，模拟启动后退出、被 restart 策略反复拉起
      n=$(( $(cat "$FAKE_COUNTER" 2>/dev/null || echo 0) + 1 )); echo "$n" > "$FAKE_COUNTER"
      state="starting running $n"
    fi
    echo "$state" ;;
  "compose exec"*)
    if [[ -n ${FAKE_CYPHER_ERROR:-} ]]; then echo "$FAKE_CYPHER_ERROR" >&2; exit 1; fi
    echo 'apoc_version'; echo '"5.26.0"' ;;
  *) exit 0 ;;
esac
"""


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def sandbox(tmp_path: Path, **env_lines: str) -> tuple[Path, Path, dict[str, str]]:
    root = tmp_path / "repo"
    for name in SCRIPTS:
        target = root / "scripts" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / "scripts" / name, target)
    lines = {"NEO4J_PASSWORD": "diag-password", "NEO4J_WAIT_SECONDS": "0",
             "NEO4J_HTTP_PORT": str(free_port()), "NEO4J_BOLT_PORT": str(free_port()), **env_lines}
    (root / ".env").write_text("".join(f"{k}={v}\n" for k, v in lines.items()), encoding="utf-8")
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    docker = bin_dir / "docker"
    docker.write_text(FAKE_DOCKER, encoding="utf-8")
    docker.chmod(docker.stat().st_mode | stat.S_IXUSR)
    log = tmp_path / "docker.log"
    env = {k: v for k, v in os.environ.items() if not k.startswith(("NEO4J_", "COMPOSE_", "STORAGE_DIR", "FAKE_"))}
    env.update(PATH=f"{bin_dir}{os.pathsep}{env['PATH']}", FAKE_LOG=str(log), FAKE_RUNNING_CID="fakecid")
    return root, log, env


def run(root: Path, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["bash", str(root / "scripts/dev-up.sh")], cwd=root, env=env,
                          input="", text=True, capture_output=True, timeout=30)


def calls(log: Path) -> list[str]:
    return log.read_text().splitlines() if log.exists() else []


def test_busy_port_with_stopped_container_fails_before_compose_up(tmp_path: Path):
    with socket.socket() as busy:
        busy.bind(("127.0.0.1", 0))
        busy.listen()
        port = busy.getsockname()[1]
        root, log, env = sandbox(tmp_path, NEO4J_HTTP_PORT=str(port))
        env.update(FAKE_RUNNING_CID="", FAKE_STATE="none created 0")

        result = run(root, env)

    assert result.returncode != 0
    assert f"端口 {port} 已被其他程序占用" in result.stderr
    assert f"lsof -nP -iTCP:{port}" in result.stderr
    assert not any(c.startswith("compose up") for c in calls(log))


def test_busy_port_is_ignored_when_neo4j_itself_is_running(tmp_path: Path):
    with socket.socket() as busy:
        busy.bind(("127.0.0.1", 0))
        busy.listen()
        root, log, env = sandbox(tmp_path, NEO4J_HTTP_PORT=str(busy.getsockname()[1]))
        env.update(FAKE_STATE="healthy running 0")

        result = run(root, env)

    assert result.returncode == 0, result.stderr
    assert "Neo4j 已就绪" in result.stdout


def test_container_left_in_created_state_reports_docker_error_and_port_hint(tmp_path: Path):
    root, log, env = sandbox(tmp_path)
    env.update(
        FAKE_RUNNING_CID="",
        FAKE_STATE="none created 0",
        FAKE_INFO="Status=created ExitCode=128 OOMKilled=false RestartCount=0 Error=driver failed programming "
                  "external connectivity: Bind for 127.0.0.1:7474 failed: port is already allocated",
    )

    result = run(root, env)

    assert result.returncode != 0
    assert "没有在运行（状态：created）" in result.stderr
    assert "port is already allocated" in result.stderr
    assert "lsof -nP" in result.stderr
    assert any(c.startswith("compose up -d neo4j") for c in calls(log))


def test_restarting_container_fails_fast_with_exit_code_3_hint_and_logs(tmp_path: Path):
    root, log, env = sandbox(tmp_path, NEO4J_WAIT_SECONDS="180")
    env.update(
        FAKE_STATE="starting restarting 4",
        FAKE_INFO="Status=restarting ExitCode=3 OOMKilled=false RestartCount=4 Error=",
    )

    result = run(root, env)

    assert result.returncode != 0
    assert "反复重启" in result.stderr
    assert "退出码 3" in result.stderr and "docker-compose.override.yml" in result.stderr
    assert "shutdown initiated by request" in result.stderr
    assert any(c.startswith("compose logs --tail 40 neo4j") for c in calls(log))


def test_restart_count_growing_while_waiting_fails_fast(tmp_path: Path):
    root, _, env = sandbox(tmp_path, NEO4J_WAIT_SECONDS="180")
    env.update(FAKE_COUNTER=str(tmp_path / "restarts"),
               FAKE_INFO="Status=running ExitCode=137 OOMKilled=true RestartCount=2 Error=")

    result = run(root, env)

    assert result.returncode != 0
    assert "反复重启" in result.stderr
    assert "内存不够" in result.stderr


def test_memory_error_in_logs_is_named_even_after_exit_code_reset(tmp_path: Path):
    # 反复重启时容器正在运行，Docker 已把 ExitCode 重置为 0；提示只能从日志判断。
    root, _, env = sandbox(tmp_path, NEO4J_WAIT_SECONDS="180")
    env.update(
        FAKE_STATE="starting restarting 1",
        FAKE_LOGS="neo4j-1  | 2026-10-01 ERROR Invalid memory configuration - exceeds physical memory.",
    )

    result = run(root, env)

    assert result.returncode != 0
    assert "内存不够" in result.stderr and "NEO4J_HEAP_MAX=512M" in result.stderr
    assert "退出码 3" not in result.stderr


def test_unhealthy_with_authentication_failure_names_password_mismatch(tmp_path: Path):
    root, _, env = sandbox(tmp_path, NEO4J_WAIT_SECONDS="180")
    env.update(FAKE_STATE="unhealthy running 0",
               FAKE_CYPHER_ERROR="The client is unauthorized due to authentication failure.")

    result = run(root, env)

    assert result.returncode != 0
    assert "NEO4J_PASSWORD" in result.stderr
    assert "mv neo4j/data neo4j/data.bak-$(date +%s)" in result.stderr
    assert "diag-password" not in result.stderr


def test_unhealthy_without_auth_error_waits_until_deadline_then_reports_probe(tmp_path: Path):
    root, log, env = sandbox(tmp_path)
    env.update(FAKE_STATE="unhealthy running 0", FAKE_CYPHER_ERROR="Connection refused")

    result = run(root, env)

    assert result.returncode != 0
    assert "0 秒内未就绪（当前：unhealthy）" in result.stderr
    assert "Connection refused" in result.stderr
    assert "logs neo4j" in result.stderr
    assert not any("apoc" in c for c in calls(log))
