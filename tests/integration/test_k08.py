"""K08: backend/frontend/worker container configuration.

Layers, cheapest first:

* **Static** — compose and Dockerfiles parsed as data: the ``app`` profile keeps F01's
  ``dev-up.sh`` untouched; secrets reach only the backend services; the frontend build
  takes no build arguments and never copies ``.env``; the build context ignores secrets.
* **Image layout** — the backend Dockerfile's ``COPY`` lines are replayed into a temp
  directory so the checked-in paths the runtime loads by relative location (migrations,
  generated contract DTOs, prompts) are proven present; the API then starts from that
  layout and answers ``GET /health``.
* **Worker entry** (``python -m app.workers`` → ``app.workers.runner``, A06 §8.1) — startup gates, supervisor exit
  codes, heartbeat health check, stop handling, with injected steps (no Neo4j, no model).
* **Real build** — ``docker compose --profile app build``; skipped without a Docker daemon
  or with ``SMARTSKETCH_SKIP_DOCKER=1``.
"""

from __future__ import annotations

import os
import re
import shutil
import signal
import socket
import subprocess
import sys
import threading
import time
import urllib.request
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "src/backend"
sys.path.insert(0, str(BACKEND))

from app.config import load_settings  # noqa: E402
from app.repositories.sqlite import migrate  # noqa: E402
from app.workers import runner as worker  # noqa: E402

APP_SERVICES = {"migrate", "api", "worker", "web"}
BACKEND_SERVICES = {"migrate", "api", "worker"}
SECRET_WORD = re.compile(r"KEY|SECRET|PASSWORD|TOKEN|AUTH", re.IGNORECASE)


def _compose() -> dict:
    return yaml.safe_load((ROOT / "docker-compose.yml").read_text(encoding="utf-8"))


def _instructions(dockerfile: Path) -> list[tuple[str, str]]:
    """(INSTRUCTION, arguments) pairs with line continuations joined and comments dropped."""
    text = re.sub(r"\\\n", " ", dockerfile.read_text(encoding="utf-8"))
    pairs = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        keyword, _, rest = line.partition(" ")
        pairs.append((keyword.upper(), rest.strip()))
    return pairs


# ---------------------------------------------------------------- static: compose


def test_app_services_live_in_app_profile_and_neo4j_stays_default() -> None:
    services = _compose()["services"]
    assert APP_SERVICES <= services.keys()
    for name in APP_SERVICES:
        assert services[name].get("profiles") == ["app"], name
    # scripts/dev-up.sh runs `compose up -d neo4j`; neo4j must not require a profile.
    assert "profiles" not in services["neo4j"]


def test_secrets_reach_only_backend_services() -> None:
    services = _compose()["services"]
    for name in BACKEND_SERVICES:
        assert services[name]["env_file"] == [".env"], name
    web = services["web"]
    assert "env_file" not in web and "environment" not in web
    assert "args" not in web["build"]
    # No literal secret value is written into compose for any service.
    for name, service in services.items():
        for key, value in (service.get("environment") or {}).items():
            if SECRET_WORD.search(key) and key != "NEO4J_AUTH":
                pytest.fail(f"{name}.{key} must come from .env, not compose")
    assert "${NEO4J_PASSWORD:?" in services["neo4j"]["environment"]["NEO4J_AUTH"]


def test_backend_services_share_one_local_volume_and_wait_for_migration() -> None:
    compose = _compose()
    services = compose["services"]
    assert "app-data" in compose["volumes"]
    for name in BACKEND_SERVICES:
        assert services[name]["volumes"] == ["app-data:/data"], name
        env = services[name]["environment"]
        assert env["SQLITE_URL"] == "sqlite:////data/smartsketch.sqlite3"
        assert env["NEO4J_URI"] == "bolt://neo4j:7687"
    for name in ("api", "worker"):
        assert services[name]["depends_on"]["migrate"] == {"condition": "service_completed_successfully"}
    assert services["migrate"]["depends_on"]["neo4j"] == {"condition": "service_healthy"}
    command = " ".join(services["migrate"]["command"])
    assert "app.repositories.sqlite" in command and "app.repositories.graph_migrations" in command


def test_worker_runs_per_a06_with_health_check() -> None:
    worker_service = _compose()["services"]["worker"]
    assert worker_service["command"] == ["python", "-m", "app.workers"]
    assert worker_service["healthcheck"]["test"] == ["CMD", "python", "-m", "app.workers", "--health"]
    # One container; process count comes from WORKER_PROCESSES, never from replicas (§8.1).
    assert "deploy" not in worker_service and "scale" not in worker_service
    assert worker_service["restart"] == "unless-stopped"


def test_only_web_publishes_a_port_and_only_on_loopback() -> None:
    services = _compose()["services"]
    assert "ports" not in services["api"] and "ports" not in services["worker"]
    assert services["web"]["ports"] == ["127.0.0.1:${WEB_PUBLISH_PORT:-8080}:8080"]
    assert services["web"]["depends_on"]["api"] == {"condition": "service_healthy"}


# ---------------------------------------------------------------- static: Dockerfiles


def test_frontend_build_takes_no_secret_and_copies_only_frontend() -> None:
    steps = _instructions(ROOT / "src/frontend/Dockerfile")
    for keyword, rest in steps:
        if keyword in {"ARG", "ENV"}:
            assert not SECRET_WORD.search(rest), rest
            assert keyword == "ARG" and rest.split("=")[0] in {"NODE_IMAGE", "NGINX_IMAGE"}, rest
        if keyword == "COPY" and not rest.startswith("--from"):
            assert rest.split()[0].startswith("src/frontend/"), rest
    assert "HEALTHCHECK" in {keyword for keyword, _ in steps}


def test_backend_image_has_no_secret_and_runs_as_non_root() -> None:
    steps = _instructions(BACKEND / "Dockerfile")
    env_text = " ".join(rest for keyword, rest in steps if keyword in {"ENV", "ARG"})
    assert not SECRET_WORD.search(env_text)
    assert any(keyword == "USER" and rest != "root" for keyword, rest in steps)
    assert any(keyword == "HEALTHCHECK" and "/health" in rest for keyword, rest in steps)
    for keyword, rest in steps:
        if keyword == "COPY":
            assert ".env" not in rest.split()[0], rest


def test_build_context_ignores_secrets_and_runtime_data() -> None:
    ignored = (ROOT / ".dockerignore").read_text(encoding="utf-8").splitlines()
    for pattern in ("**/.env", "**/.env.*", ".git", "storage/", "neo4j/", "**/node_modules"):
        assert pattern in ignored, pattern


def test_frontend_proxy_keeps_sse_unbuffered() -> None:
    conf = (ROOT / "src/frontend/nginx.conf").read_text(encoding="utf-8")
    api = conf[conf.index("location /api/"):]
    api = api[: api.index("}")]
    assert "proxy_pass http://api:8000;" in api
    assert "proxy_buffering off;" in api
    assert "try_files $uri $uri/ /index.html;" in conf


# ---------------------------------------------------------------- image layout


def _replay_backend_copies(dest: Path) -> Path:
    """Copy what ``src/backend/Dockerfile`` copies into ``dest`` (standing in for ``/``)."""
    workdir = Path("/")
    for keyword, rest in _instructions(BACKEND / "Dockerfile"):
        if keyword == "WORKDIR":
            workdir = Path(rest)
        elif keyword == "COPY":
            source, target = rest.split()
            target_path = Path(target) if target.startswith("/") else workdir / target
            out = dest / target_path.relative_to("/")
            src = ROOT / source
            if src.is_dir():
                shutil.copytree(src, out, ignore=shutil.ignore_patterns("__pycache__"))
            else:
                out.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, out)
    return dest / workdir.relative_to("/")


def _free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def _layout_env(workdir: Path, data: Path, **extra: str) -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if not k.startswith(("LLM_", "EMBEDDING_", "NEO4J_", "AUTH_"))}
    env.update(
        PYTHONPATH=str(workdir),
        SQLITE_URL=f"sqlite:///{(data / 'smartsketch.sqlite3').as_posix()}",
        STORAGE_DIR=str(data / "storage"),
        AUTH_JWT_SECRET="k08-layout-test-secret-at-least-32-bytes",
        APP_ENV="development",
    )
    env.update(extra)
    return env


def test_backend_layout_loads_contracts_prompts_and_migrations(tmp_path: Path) -> None:
    workdir = _replay_backend_copies(tmp_path / "image")
    data = tmp_path / "data"
    data.mkdir()
    env = _layout_env(workdir, data)
    probe = (
        "import app, app.schemas.contracts as c, app.services.ai.prompts as p, app.repositories.sqlite as s;"
        "print(app.__file__); print(c._PATH); print(p.DEFAULT_PROMPTS_DIR); print(s.MIGRATIONS_DIR)"
    )
    out = subprocess.run([sys.executable, "-c", probe], cwd=workdir, env=env, capture_output=True,
                         text=True, check=True).stdout.splitlines()
    image = str(tmp_path / "image")
    assert all(line.startswith(image) for line in out), out
    assert Path(out[1]).is_file() and Path(out[2]).is_dir() and any(Path(out[3]).glob("*.sql"))
    migrated = subprocess.run([sys.executable, "-m", "app.repositories.sqlite"], cwd=workdir, env=env,
                              capture_output=True, text=True)
    assert migrated.returncode == 0, migrated.stderr


def test_api_starts_from_image_layout_and_answers_health(tmp_path: Path) -> None:
    workdir = _replay_backend_copies(tmp_path / "image")
    data = tmp_path / "data"
    data.mkdir()
    port = _free_port()
    env = _layout_env(workdir, data, API_HOST="127.0.0.1", API_PORT=str(port))
    subprocess.run([sys.executable, "-m", "app.repositories.sqlite"], cwd=workdir, env=env, check=True,
                   capture_output=True)
    server = subprocess.Popen([sys.executable, "-m", "app"], cwd=workdir, env=env,
                              stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    try:
        deadline = time.monotonic() + 30
        while True:
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=2) as response:
                    assert response.status == 200
                    break
            except OSError:
                if server.poll() is not None or time.monotonic() > deadline:
                    pytest.fail(server.stdout.read().decode(errors="replace") if server.stdout else "no output")
                time.sleep(0.2)
    finally:
        server.send_signal(signal.SIGTERM)
        server.wait(timeout=10)


# ---------------------------------------------------------------- worker entry


@pytest.fixture
def settings(tmp_path: Path):
    url = f"sqlite:///{(tmp_path / 'state.sqlite3').as_posix()}"
    migrate(url)
    return load_settings({"SQLITE_URL": url, "STORAGE_DIR": str(tmp_path / "files"), "WORKER_PROCESSES": "2"})


def test_worker_refuses_to_start_on_unmigrated_database(tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
                                                        capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setenv("SQLITE_URL", f"sqlite:///{(tmp_path / 'fresh.sqlite3').as_posix()}")
    monkeypatch.setenv("STORAGE_DIR", str(tmp_path / "files"))
    started = []
    monkeypatch.setattr(worker, "supervise", lambda _s: started.append(1) or 0)
    assert worker.main([]) == worker.EXIT_CONFIG
    assert started == []
    assert "python -m app.repositories.sqlite" in capsys.readouterr().err


def test_worker_starts_supervisor_when_gates_pass(settings, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SQLITE_URL", settings.SQLITE_URL)
    monkeypatch.setenv("STORAGE_DIR", settings.STORAGE_DIR)
    seen = []
    monkeypatch.setattr(worker, "supervise", lambda s: seen.append(s.SQLITE_URL) or 0)
    assert worker.main([]) == 0
    assert seen == [settings.SQLITE_URL]


def test_worker_rejects_unknown_arguments() -> None:
    assert worker.main(["--bogus"]) == worker.EXIT_CONFIG


class _Result:
    def __init__(self, lease: object | None) -> None:
        self.lease = lease


def test_run_loop_idles_only_when_nothing_was_claimed(settings) -> None:
    results = iter([_Result("lease"), _Result(None), _Result("lease")])
    waits: list[float] = []
    calls: list[str] = []

    class _Stop(threading.Event):
        def wait(self, timeout: float | None = None) -> bool:
            waits.append(timeout or 0)
            return False

    stop = _Stop()

    def step() -> _Result:
        result = next(results)
        if calls.count("step") == 2:
            stop.set()
        calls.append("step")
        return result

    rounds = worker.run_loop(settings, stop, step=step, maintenance=[lambda: calls.append("hook")], idle_seconds=7)
    assert rounds == 3
    assert calls == ["step", "hook", "step", "hook", "step", "hook"]
    assert waits == [7]


def test_run_loop_does_nothing_once_stopped(settings) -> None:
    stop = threading.Event()
    stop.set()
    assert worker.run_loop(settings, stop, step=lambda: pytest.fail("claimed after stop")) == 0


def _exit_at_once() -> None:
    sys.exit(0)


def _sleep_until_terminated() -> None:
    time.sleep(60)


def test_supervisor_exits_nonzero_when_a_child_dies(settings, tmp_path: Path,
                                                    monkeypatch: pytest.MonkeyPatch) -> None:
    beat = tmp_path / "beat"
    monkeypatch.setenv(worker.HEARTBEAT_ENV, str(beat))
    previous = signal.getsignal(signal.SIGTERM), signal.getsignal(signal.SIGINT)
    try:
        assert worker.supervise(settings, target=_exit_at_once) == worker.EXIT_CHILD_DIED
    finally:
        signal.signal(signal.SIGTERM, previous[0])
        signal.signal(signal.SIGINT, previous[1])
    assert not beat.exists()


def test_supervisor_beats_while_children_live_and_stops_them_on_sigterm(settings, tmp_path: Path,
                                                                       monkeypatch: pytest.MonkeyPatch) -> None:
    beat = tmp_path / "beat"
    monkeypatch.setenv(worker.HEARTBEAT_ENV, str(beat))
    monkeypatch.setattr(worker, "HEARTBEAT_SECONDS", 0.1)
    previous = signal.getsignal(signal.SIGTERM), signal.getsignal(signal.SIGINT)
    seen: list[int] = []

    def watch() -> None:
        deadline = time.monotonic() + 20
        while not beat.exists() and time.monotonic() < deadline:
            time.sleep(0.05)
        seen.append(worker.health())
        os.kill(os.getpid(), signal.SIGTERM)

    watcher = threading.Thread(target=watch)
    watcher.start()
    try:
        started = time.monotonic()
        assert worker.supervise(settings, target=_sleep_until_terminated) == 0
        assert time.monotonic() - started < 30
    finally:
        watcher.join()
        signal.signal(signal.SIGTERM, previous[0])
        signal.signal(signal.SIGINT, previous[1])
    assert seen == [0]
    assert not beat.exists() and worker.health() == 1


def test_module_entry_spawns_real_children(settings, tmp_path: Path) -> None:
    """``python -m app.workers`` end to end: children import by module name under spawn and reach
    Neo4j; with Neo4j unreachable they die and the supervisor exits non-zero for a restart."""
    env = {k: v for k, v in os.environ.items() if not k.startswith(("LLM_", "EMBEDDING_", "NEO4J_"))}
    env.update(PYTHONPATH=str(BACKEND), SQLITE_URL=settings.SQLITE_URL, STORAGE_DIR=settings.STORAGE_DIR,
               NEO4J_URI="bolt://127.0.0.1:1", **{worker.HEARTBEAT_ENV: str(tmp_path / "beat")})
    result = subprocess.run([sys.executable, "-m", "app.workers"], cwd=BACKEND, env=env,
                            capture_output=True, text=True, timeout=120)
    assert result.returncode == worker.EXIT_CHILD_DIED, result.stderr[-2000:]
    assert "NEO4J_CONNECTION_FAILED" in result.stderr
    assert "Can't get attribute" not in result.stderr


def test_health_rejects_stale_heartbeat(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    beat = tmp_path / "beat"
    monkeypatch.setenv(worker.HEARTBEAT_ENV, str(beat))
    assert worker.health() == 1
    beat.touch()
    assert worker.health() == 0
    old = time.time() - worker.HEARTBEAT_STALE_SECONDS - 5
    os.utime(beat, (old, old))
    assert worker.health() == 1


def test_toolkit_in_fake_mode_needs_no_key(settings) -> None:
    toolkit = worker.build_toolkit(settings)
    assert settings.LLM_MODE == "fake"
    assert toolkit.entities is not None and toolkit.relations is not None


# ---------------------------------------------------------------- real build


def _docker_ready() -> bool:
    if os.environ.get("SMARTSKETCH_SKIP_DOCKER") == "1" or shutil.which("docker") is None:
        return False
    return subprocess.run(["docker", "info"], capture_output=True).returncode == 0


@pytest.mark.skipif(not _docker_ready(), reason="no Docker daemon (or SMARTSKETCH_SKIP_DOCKER=1)")
def test_images_build(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text((ROOT / ".env.example").read_text(encoding="utf-8") + "\nNEO4J_PASSWORD=k08-build\n",
                        encoding="utf-8")
    result = subprocess.run(
        ["docker", "compose", "--env-file", str(env_file), "--profile", "app", "build", "api", "web"],
        cwd=ROOT, capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr[-4000:]
