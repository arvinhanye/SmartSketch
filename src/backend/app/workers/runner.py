"""常驻 worker 入口（K08）：``python -m app.workers`` 调用本模块 ``main``。

实现不放在 ``__main__.py``：spawn 方式的子进程要按模块名反序列化 ``_child_main``，
而 ``-m`` 启动时的 ``__main__`` 模块无法被子进程按名导入。

按 ``specs/task-processing.md`` §8.1 运行：与 API 同机的独立进程，共用一个 SQLite 文件，
进程数取 ``WORKER_PROCESSES``，多进程互斥完全交给 C09 租约。

1. **启动门禁**：先调 ``validate_schema_current`` 与 ``validate_embedding_space``（与 API lifespan 相同）；
   未迁移或向量空间不一致即以非零退出码拒绝启动，不领取任何任务。
2. **监督进程**：启动 ``WORKER_PROCESSES`` 个子进程，每 ``HEARTBEAT_SECONDS`` 秒刷新心跳文件，供容器健康
   检查（``python -m app.workers --health``）判断；任一子进程意外退出即停掉其余子进程并以非零码退出，
   由容器重启策略拉起，未完成的任务按 §8.2 在租约到期后被接管。
3. **子进程循环**：反复调用 F13 ``run_pipeline_once``（回收 → 领取 → 各阶段推进）；没有可领任务时
   空闲 ``IDLE_SECONDS`` 秒。每轮之间执行 ``maintenance`` 挂点（默认空），供后续定期清扫任务接入。
4. **正常退出**：收到 SIGTERM/SIGINT 后不再领取新任务；进行中的一轮跑完后退出。本入口不在阶段中途打断
   （阶段内没有协作式取消点），因此容器的停止宽限期内没跑完的任务被强杀后按租约过期接管——与崩溃同样安全，
   只是要等满一个租约。

密钥只从环境变量经 ``load_settings`` 读取；本模块不打印设置或异常详情以外的任何配置值。
"""

from __future__ import annotations

import logging
import multiprocessing
import os
import signal
import sys
import threading
import time
from collections.abc import Callable, Sequence
from pathlib import Path
from types import FrameType

from app.config import Settings, SettingsError, load_settings
from app.repositories.model_calls import SqliteCallStore
from app.repositories.neo4j import Neo4jRepository
from app.services.ai.client import ModelClient
from app.services.ai.compatible import CompatibleModelClient
from app.services.ai.entities import EntityExtractor
from app.services.ai.fake import FakeModelClient
from app.services.ai.policy import ModelCallPolicy
from app.services.ai.relations import RelationExtractor
from app.services.startup import validate_embedding_space, validate_schema_current
from app.workers.extract_task import ExtractionToolkit
from app.workers.persist_graph import run_pipeline_once

LOG = logging.getLogger("app.workers")

IDLE_SECONDS = 2.0
HEARTBEAT_SECONDS = 10.0
HEARTBEAT_STALE_SECONDS = 60.0
# 与 K02 评测脚本的缺省值一致（evaluation/run_live_extraction.py）
MAX_OUTPUT_TOKENS = 4096
FAKE_MODEL_ID = "fake"
HEARTBEAT_ENV = "WORKER_HEARTBEAT_FILE"
DEFAULT_HEARTBEAT_FILE = "/tmp/smartsketch-worker.heartbeat"

EXIT_CONFIG = 2
EXIT_CHILD_DIED = 3


def heartbeat_path() -> Path:
    return Path(os.environ.get(HEARTBEAT_ENV) or DEFAULT_HEARTBEAT_FILE)


def build_toolkit(settings: Settings) -> ExtractionToolkit:
    """按 ``LLM_MODE`` 建模型客户端，外包 E04 策略（调用记录写应用 SQLite 的 ``model_calls``）。"""
    fallback: ModelClient | None = None
    primary: ModelClient
    if settings.LLM_MODE == "live":
        primary = CompatibleModelClient.from_settings(settings, role="primary")
        if settings.LLM_FALLBACK_BASE_URL.strip():
            fallback = CompatibleModelClient.from_settings(settings, role="fallback")
    else:
        primary = FakeModelClient()
    model = settings.LLM_EXTRACTION_MODEL.strip() or FAKE_MODEL_ID
    policy = ModelCallPolicy.from_settings(
        settings, primary=primary, fallback=fallback, store=SqliteCallStore(settings.SQLITE_URL)
    )
    return ExtractionToolkit(
        policy=policy,
        entities=lambda client: EntityExtractor(client, model=model, max_output_tokens=MAX_OUTPUT_TOKENS),
        relations=lambda client: RelationExtractor(client, model=model, max_output_tokens=MAX_OUTPUT_TOKENS),
    )


def run_loop(
    settings: Settings,
    stop: threading.Event,
    *,
    step: Callable[[], object] | None = None,
    maintenance: Sequence[Callable[[], object]] = (),
    idle_seconds: float = IDLE_SECONDS,
) -> int:
    """反复推进直到 ``stop`` 置位；返回完成的轮数。``step`` 只供测试注入（替代真实流水线）。"""
    if step is None:
        toolkit = build_toolkit(settings)
        repo = Neo4jRepository.from_settings(settings)

        def step() -> object:
            return run_pipeline_once(settings, toolkit=toolkit, repo=repo)

    rounds = 0
    while not stop.is_set():
        result = step()
        rounds += 1
        for hook in maintenance:
            hook()
        if getattr(result, "lease", None) is None:
            stop.wait(idle_seconds)
    return rounds


def _install_stop(stop: threading.Event) -> None:
    def handler(_signum: int, _frame: FrameType | None) -> None:
        stop.set()

    signal.signal(signal.SIGTERM, handler)
    signal.signal(signal.SIGINT, handler)


def _child_main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    stop = threading.Event()
    _install_stop(stop)
    settings = load_settings()
    rounds = run_loop(settings, stop)
    LOG.info("worker pid=%s stopped after %s rounds", os.getpid(), rounds)


def check_startup(settings: Settings) -> None:
    """与 API lifespan 相同的两道门禁（C01 R02、B06）。"""
    validate_schema_current(settings)
    validate_embedding_space(settings)


def supervise(settings: Settings, *, target: Callable[[], None] = _child_main) -> int:
    """启动 ``WORKER_PROCESSES`` 个子进程并维持心跳；返回退出码。"""
    stop = threading.Event()
    _install_stop(stop)
    context = multiprocessing.get_context("spawn")
    children = [context.Process(target=target, name=f"worker-{index}") for index in range(settings.WORKER_PROCESSES)]
    for child in children:
        child.start()
    beat = heartbeat_path()
    code = 0
    try:
        while not stop.is_set():
            dead = [child for child in children if not child.is_alive()]
            if dead:
                LOG.error("worker child %s exited with %s", dead[0].name, dead[0].exitcode)
                code = EXIT_CHILD_DIED
                break
            beat.touch()
            stop.wait(HEARTBEAT_SECONDS)
    finally:
        for child in children:
            if child.is_alive():
                child.terminate()  # 子进程收到 SIGTERM：跑完当前一轮后退出
        for child in children:
            child.join()
        beat.unlink(missing_ok=True)
    return code


def health() -> int:
    """容器健康检查：心跳文件存在且在 ``HEARTBEAT_STALE_SECONDS`` 内刷新过。"""
    try:
        age = time.time() - heartbeat_path().stat().st_mtime
    except OSError:
        return 1
    return 0 if age <= HEARTBEAT_STALE_SECONDS else 1


def main(argv: Sequence[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if args == ["--health"]:
        return health()
    if args:
        print("usage: python -m app.workers [--health]", file=sys.stderr)
        return EXIT_CONFIG
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    try:
        settings = load_settings()
        check_startup(settings)
    except SettingsError as error:
        print(str(error), file=sys.stderr)
        return EXIT_CONFIG
    return supervise(settings)
