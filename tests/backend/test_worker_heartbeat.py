"""Windows 回归：worker 心跳文件的默认路径必须落在当前平台的临时目录里。

背景（实机复现）：``DEFAULT_HEARTBEAT_FILE`` 曾硬编码为 ``/tmp/smartsketch-worker.heartbeat``。
POSIX 上它是绝对路径，能工作；Windows 上它被解析为当前盘符根下的 ``\\tmp\\...``，该目录
通常不存在，于是 ``supervise()`` 里的 ``beat.touch()`` 抛 ``FileNotFoundError``，监督进程
整体退出（``python -m app.workers`` 直接起不来），上传的资料永远停在 ``queued``。

既有覆盖的盲区：``tests/integration/test_k08.py`` 的四个用例**都显式设置** ``HEARTBEAT_ENV``，
因此默认值从未被断言过。本文件补上这一层，作为可跨平台的回归防线：
Linux 上它校验默认值仍是 ``/tmp``（行为不变），Windows 上它会让旧实现立刻变红。
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

from app.workers import runner


def test_default_heartbeat_file_lives_in_the_platform_temp_dir() -> None:
    """默认心跳文件必须与 ``tempfile.gettempdir()`` 同目录。

    硬编码 ``/tmp`` 的实现会让本断言在 Windows 上失败——这正是要防的回归。
    """
    assert Path(runner.DEFAULT_HEARTBEAT_FILE).parent == Path(tempfile.gettempdir())


def test_default_heartbeat_parent_directory_exists() -> None:
    """默认路径的父目录必须已存在，否则 ``beat.touch()`` 在监督进程里直接抛错。"""
    parent = Path(runner.DEFAULT_HEARTBEAT_FILE).parent
    assert parent.is_dir(), f"心跳文件父目录不存在：{parent}"


def test_default_heartbeat_parent_is_writable() -> None:
    """默认路径必须真的可写（Windows 上 ``\\tmp\\`` 既不存在也不可写）。"""
    parent = Path(runner.DEFAULT_HEARTBEAT_FILE).parent
    assert os.access(parent, os.W_OK), f"心跳文件父目录不可写：{parent}"


def test_heartbeat_path_uses_the_default_when_the_env_var_is_absent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """未设置 ``WORKER_HEARTBEAT_FILE`` 时回落到默认值（而不是空路径或相对路径）。"""
    monkeypatch.delenv(runner.HEARTBEAT_ENV, raising=False)
    assert runner.heartbeat_path() == Path(runner.DEFAULT_HEARTBEAT_FILE)


def test_heartbeat_path_prefers_the_environment_override(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """显式覆盖优先于默认值——K08 的集成用例与 start-demo 脚本都依赖这一点。"""
    override = tmp_path / "beat"
    monkeypatch.setenv(runner.HEARTBEAT_ENV, str(override))
    assert runner.heartbeat_path() == override


def test_default_heartbeat_file_is_absolute() -> None:
    """默认值必须是绝对路径：监督进程的工作目录可被调用方改变。"""
    assert Path(runner.DEFAULT_HEARTBEAT_FILE).is_absolute()


def test_supervise_can_touch_the_default_heartbeat(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """回归的核心：在**不设置**覆盖变量的前提下，默认路径必须能被创建与删除。

    旧实现在 Windows 上会在 ``beat.touch()`` 抛 ``FileNotFoundError``；这里直接把那次
    调用抽出来验证，不需要真的起子进程。
    """
    monkeypatch.delenv(runner.HEARTBEAT_ENV, raising=False)
    beat = runner.heartbeat_path()
    beat.touch()
    try:
        assert beat.exists()
        assert runner.health() == 0
    finally:
        beat.unlink(missing_ok=True)
    assert not beat.exists()
