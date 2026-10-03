"""Windows/启动目录回归：相对 SQLITE_URL 必须锚定到后端根，而不是进程的当前目录。

问题（实机复现）：``SQLITE_URL=sqlite:///./storage/smartsketch.sqlite3`` 是相对路径，
而 ``database_path()`` 用 ``Path(raw).resolve()`` 按**进程 CWD** 解析。于是同一个配置：

- 从 ``src/backend`` 启动（``docs/runbook.md`` 与 ``scripts/start-demo.sh`` 的写法）→
  ``src/backend/storage/smartsketch.sqlite3``，有迁移、有数据；
- 从仓库根目录启动（``scripts/import-demo.py``、``seed-demo-accounts.py`` 的自然用法）→
  仓库根下的 ``storage/``，**是一个全新的空库**，脚本随即报
  ``Database has pending migrations (001, ... 014)``，与真实库状态完全脱节。

``STORAGE_DIR=./storage``（``FileStorage`` 的 root）有同样的毛病。

仓库在其它地方已经是正确范式：``sqlite.MIGRATIONS_DIR``、``ai.prompts.DEFAULT_PROMPTS_DIR``、
``schemas.contracts._PATH`` 都锚定到源码位置（``Path(__file__).resolve().parents[N]``）。
本文件把 SQLite 与存储目录也钉到同一基准。
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from app.repositories.sqlite import database_path
from app.services.file_storage import FileStorage

BACKEND = Path(__file__).resolve().parents[2] / "src" / "backend"


def test_relative_sqlite_url_is_anchored_to_the_backend_root() -> None:
    """相对 URL 解析结果必须落在后端根下，与 CWD 无关。"""
    resolved = database_path("sqlite:///./storage/smartsketch.sqlite3")
    assert resolved == (BACKEND / "storage" / "smartsketch.sqlite3").resolve()


def test_relative_sqlite_url_does_not_follow_the_working_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """换一个 CWD 后解析结果必须不变——旧实现会跟着 CWD 跑。

    用 tmp_path 假装成另一个"仓库根"：旧实现会把它当成库文件位置。
    """
    monkeypatch.chdir(tmp_path)
    resolved = database_path("sqlite:///./storage/smartsketch.sqlite3")
    assert resolved != (tmp_path / "storage" / "smartsketch.sqlite3").resolve()
    assert resolved == (BACKEND / "storage" / "smartsketch.sqlite3").resolve()


def test_relative_storage_dir_is_anchored_to_the_backend_root() -> None:
    """``STORAGE_DIR`` 的相对值同样锚定到后端根（FileStorage 自己建目录）。"""
    store = FileStorage("./storage", max_bytes=1024)
    assert Path(store.root) == (BACKEND / "storage").resolve()


def test_absolute_paths_are_untouched(tmp_path: Path) -> None:
    """绝对路径不受影响：容器里 ``/data/...`` 与测试夹具的 tmp 路径都必须原样使用。"""
    absolute = tmp_path / "state.sqlite3"
    assert database_path(f"sqlite:///{absolute}") == absolute.resolve()


def test_every_launch_directory_resolves_to_the_same_database(tmp_path: Path) -> None:
    """端到端判据：从仓库根与从 src/backend 启动，解析出的库文件必须是同一个。"""
    probe = (
        "import sys; sys.path.insert(0, r'{backend}');"
        "from app.repositories.sqlite import database_path;"
        "print(database_path('sqlite:///./storage/smartsketch.sqlite3'))"
    ).format(backend=BACKEND)

    env = {k: v for k, v in os.environ.items() if not k.startswith("PYTHONPATH")}
    results = set()
    for cwd in (BACKEND, tmp_path):
        completed = subprocess.run(
            [sys.executable, "-c", probe],
            cwd=str(cwd), env=env, capture_output=True, encoding="utf-8", errors="replace",
            check=True,
        )
        results.add(completed.stdout.strip())
    assert len(results) == 1, f"不同启动目录解析出了不同的库：{results}"
    assert results.pop() == str((BACKEND / "storage" / "smartsketch.sqlite3").resolve())
