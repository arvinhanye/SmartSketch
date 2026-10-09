"""scripts/_stop-procs.sh：结束后台服务不能因为某个服务忽略 SIGTERM 而无限挂住（CI 上曾卡到 30 分钟作业超时）。"""

import os
import subprocess
import time
from pathlib import Path

HELPER = Path(__file__).resolve().parents[2] / "scripts" / "_stop-procs.sh"


def run(script: str, timeout: float = 30) -> tuple[subprocess.CompletedProcess, float]:
    started = time.monotonic()
    result = subprocess.run(
        ["bash", "-c", f'set -euo pipefail; set -m; . "{HELPER}"; {script}'],
        capture_output=True, text=True, timeout=timeout,
    )
    return result, time.monotonic() - started


def alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


def test_a_service_that_ignores_sigterm_is_force_killed_after_the_grace_period():
    result, elapsed = run(
        '(trap "" TERM; exec python3 -c "import signal,time; signal.signal(signal.SIGTERM, signal.SIG_IGN); time.sleep(120)") & pid=$!; '
        'sleep 0.5; stop_process_groups 2 "$pid"; echo "pid=$pid"'
    )
    assert result.returncode == 0, result.stderr
    assert "强制结束" in result.stderr
    assert 2 <= elapsed < 15
    pid = int(result.stdout.strip().split("=")[1])
    assert not alive(pid)


def test_a_well_behaved_service_stops_immediately_without_waiting_for_the_grace_period():
    result, elapsed = run('sleep 120 & pid=$!; sleep 0.3; stop_process_groups 10 "$pid"; echo "pid=$pid"')
    assert result.returncode == 0, result.stderr
    assert "强制结束" not in result.stderr
    assert elapsed < 5
    assert not alive(int(result.stdout.strip().split("=")[1]))


def test_services_that_already_exited_are_fine():
    result, elapsed = run('true & pid=$!; wait "$pid" || true; stop_process_groups 5 "$pid"')
    assert result.returncode == 0, result.stderr
    assert elapsed < 5
