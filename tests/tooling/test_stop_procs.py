"""scripts/_stop-procs.sh：结束后台服务不能因为某个服务忽略 SIGTERM 而无限挂住（CI 上曾卡到 30 分钟作业超时）。"""

import os
import select
import shlex
import signal
import subprocess
import sys
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


def stop_ready_service(grace: int, *, ignore_term: bool, near_tick: bool = False):
    """Measure stop only, after the child confirms its signal handler is ready."""
    service = (
        "import os,signal; "
        f"signal.signal(signal.SIGTERM, signal.{'SIG_IGN' if ignore_term else 'SIG_DFL'}); "
        'print(f"ready={os.getpid()}", flush=True); signal.pause()'
    )
    script = (
        f'set -euo pipefail; set -m; . {shlex.quote(str(HELPER))}; '
        f'{shlex.quote(sys.executable)} -c {shlex.quote(service)} & pid=$!; '
        # The parent starts its stopwatch before releasing this handshake.
        'read -r go; '
        f'stop_process_groups {grace} "$pid"; echo "pid=$pid"'
    )
    proc = subprocess.Popen(
        ["bash", "-c", script], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, text=True,
    )
    pid = None
    sent_stop = False
    try:
        readable, _, _ = select.select([proc.stdout], [], [], 5)
        assert readable, "service did not report signal-handler readiness within 5s"
        ready = proc.stdout.readline().strip()
        assert ready.startswith("ready="), f"unexpected service readiness: {ready!r}"
        pid = int(ready.split("=", 1)[1])
        if near_tick:
            # This regression deliberately crosses a real wall-clock tick to catch
            # Bash SECONDS rounding. A fake clock cannot advance the shell's clock.
            time.sleep((0.85 - time.time() % 1) % 1)
        # Keep both readings in this process: macOS Python 3.9's monotonic epoch
        # is process-local, so subtracting two `python3 -c` readings is invalid.
        started = time.monotonic()
        sent_stop = True
        stdout, stderr = proc.communicate("stop\n", timeout=30)
        elapsed = time.monotonic() - started
        return subprocess.CompletedProcess(proc.args, proc.returncode, stdout, stderr), elapsed
    finally:
        if pid is not None and alive(pid):
            try:
                os.killpg(pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        if proc.poll() is None:
            # Let the shell reap its service even if readiness or timing failed.
            try:
                proc.communicate(None if sent_stop else "stop\n", timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.communicate(timeout=5)


def test_a_service_that_ignores_sigterm_is_force_killed_after_the_grace_period():
    # Exercise the real two-second grace period and SIGKILL, not a fake clock.
    result, elapsed = stop_ready_service(2, ignore_term=True)
    assert result.returncode == 0, result.stderr
    assert "强制结束" in result.stderr
    assert 2 <= elapsed < 15
    pid = int(result.stdout.strip().split("=")[1])
    assert not alive(pid)


def test_a_well_behaved_service_stops_immediately_without_waiting_for_the_grace_period():
    result, elapsed = stop_ready_service(10, ignore_term=False)
    assert result.returncode == 0, result.stderr
    assert "强制结束" not in result.stderr
    assert elapsed < 5
    assert not alive(int(result.stdout.strip().split("=")[1]))


def test_grace_period_is_not_shortened_by_shell_seconds_rounding():
    result, elapsed = stop_ready_service(2, ignore_term=True, near_tick=True)
    assert result.returncode == 0, result.stderr
    assert "强制结束" in result.stderr
    pid = result.stdout.strip()
    assert 2 <= elapsed < 15
    assert not alive(int(pid.split("=")[1]))


def test_services_that_already_exited_are_fine():
    result, elapsed = run('true & pid=$!; wait "$pid" || true; stop_process_groups 5 "$pid"')
    assert result.returncode == 0, result.stderr
    assert elapsed < 5
