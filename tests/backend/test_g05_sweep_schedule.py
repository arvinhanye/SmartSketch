"""遗留 1（PR #264 独立审查）：``sweep`` 接入 worker 周期回收（A06 §8.6；ADR-036 第 5 条待决，ADR-072）。

用可注入的时钟与清扫函数做确定性测试：不必等真实间隔、不连 Neo4j。
覆盖「到点才调用」「抛错不打断 worker 主循环」「0 关闭」「配置来自环境变量」。
端到端调度（真实 worker 子进程按小时调用）不在单测内，用同一 ``run_loop`` 的 maintenance 挂点验证。
"""

from __future__ import annotations

import threading
from types import SimpleNamespace

from app.config import SettingsError, load_settings
from app.workers import runner


class Clock:
    def __init__(self, start: float = 0.0) -> None:
        self.now = start

    def __call__(self) -> float:
        return self.now


def _repo() -> object:
    return object()  # 只需一个不透明的仓储对象；清扫函数由测试注入


def test_sweep_runs_only_when_the_interval_has_elapsed():
    clock = Clock()
    calls: list[float] = []
    hook = runner.PublishSweep("sqlite:///x.sqlite3", _repo(), 10.0,
                               sweep_fn=lambda url, repo: calls.append(clock.now) or [], now=clock)

    hook()  # 首轮：没有上次时间，立即执行
    clock.now = 5.0
    hook()  # 未到点
    clock.now = 9.999
    hook()  # 未到点
    clock.now = 10.0
    hook()  # 到点
    clock.now = 15.0
    hook()
    clock.now = 20.0
    hook()

    assert calls == [0.0, 10.0, 20.0]


def test_failed_sweep_is_logged_and_does_not_break_the_worker_loop():
    clock = Clock()
    attempts: list[float] = []

    def boom(url, repo):
        attempts.append(clock.now)
        raise RuntimeError("neo4j down")

    hook = runner.PublishSweep("sqlite:///x.sqlite3", _repo(), 10.0, sweep_fn=boom, now=clock)
    settings = load_settings({"PUBLISH_SWEEP_INTERVAL_SECONDS": "10"})
    stop = threading.Event()
    rounds: list[int] = []

    def step() -> SimpleNamespace:
        rounds.append(1)
        clock.now += 10.0  # 每轮推进一个周期；清扫钩子在本轮 step 之后执行
        if len(rounds) == 3:
            stop.set()
        return SimpleNamespace(lease=None)

    completed = runner.run_loop(settings, stop, step=step, maintenance=[hook], idle_seconds=0)

    assert completed == 3 and len(rounds) == 3  # 清扫抛错三轮都在推进
    assert attempts == [10.0, 20.0, 30.0]


def test_interval_zero_disables_the_hook_and_defaults_to_hourly():
    off = load_settings({"PUBLISH_SWEEP_INTERVAL_SECONDS": "0"})
    assert runner.build_maintenance(off, _repo()) == ()
    # 缺省启用且是 A06 §8.6 的建议周期；配置只能来自环境变量。
    on = load_settings({"PUBLISH_SWEEP_INTERVAL_SECONDS": "3600"})
    hooks = runner.build_maintenance(on, _repo())
    assert len(hooks) == 1 and isinstance(hooks[0], runner.PublishSweep)
    assert load_settings({}).PUBLISH_SWEEP_INTERVAL_SECONDS == 3600


def test_interval_must_be_a_non_negative_integer():
    for bad in ("-1", "abc", "1.5"):
        try:
            load_settings({"PUBLISH_SWEEP_INTERVAL_SECONDS": bad})
        except SettingsError as error:
            assert "PUBLISH_SWEEP_INTERVAL_SECONDS" in str(error)
        else:  # pragma: no cover - 失败路径
            raise AssertionError(f"{bad!r} should be rejected")


def test_production_loop_wires_the_publish_sweep_by_default(monkeypatch):
    """未注入 ``step`` 时 ``run_loop`` 自建仓储并把 ``PublishSweep`` 接进 maintenance（不连 Neo4j）。"""
    settings = load_settings({"PUBLISH_SWEEP_INTERVAL_SECONDS": "60"})
    built: list[object] = []
    monkeypatch.setattr(runner, "build_toolkit", lambda _s: object())
    monkeypatch.setattr(runner.Neo4jRepository, "from_settings", classmethod(lambda _cls, _s: "repo"))
    monkeypatch.setattr(runner, "build_maintenance", lambda _s, repo: built.append(repo) or ())
    stop = threading.Event()
    stop.set()  # 不进循环：只验证 step 为 None 时的装配分支

    assert runner.run_loop(settings, stop) == 0

    assert built == ["repo"]
