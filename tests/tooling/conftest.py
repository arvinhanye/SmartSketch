"""tooling 测试的公共夹具与守卫。

本目录的用例分两类：

1. **纯 Python**（``test_b07.py`` 的多数用例、``test_k11.py`` 的 gate 用例）：任何平台都跑。
2. **需要 bash 解释器**：``scripts/*.sh`` 只由 bash 执行。Windows 上直接
   ``subprocess.run(["scripts/verify.sh", ...])`` 会得到
   ``OSError: [WinError 193] %1 不是有效的 Win32 应用程序``；而写死 ``"bash"`` 又踩另一个坑——
   ``C:\\Windows\\System32\\bash.exe`` 是 **WSL 的启动器**，不是 Git Bash，传给它的 Windows
   路径会被当成 Linux 路径，脚本行为完全不是被测行为。因此需要 bash 的用例统一通过下面的
   ``bash`` 夹具取解释器，并在确实拿不到时**带登记原因跳过**
   （原因写在 ``scripts/verify/allowed-skips.txt``，K11 门禁要求每条 SKIP 都有登记）。

``tests/contracts/test_contracts.py`` 早已用同样的 ``SMARTSKETCH_BASH`` 约定，本夹具把它提取
出来供本目录复用。

另一个 Windows 专属陷阱是**文本解码**：这些用例捕获子进程输出，而中文 Windows 的默认 locale
编码是 GBK，子进程按 UTF-8 打印的 ``✓``（U+2713）在父进程侧解码时会抛
``UnicodeEncodeError``/``UnicodeDecodeError``。``utf8_subprocess_env`` / ``capture_text``
把两端都固定成 UTF-8，避免「测试失败但缺陷不在被测代码」。
"""

from __future__ import annotations

import os
import shutil
import subprocess
from typing import Any

import pytest

BASH_SKIP_REASON = "bash interpreter not available"

# WSL 的 bash 启动器：会启动 Linux 发行版，而不是解释当前 Windows 路径下的脚本。
_WSL_BASH = "windows\\system32\\bash.exe"


def find_bash() -> str | None:
    """返回可用的 **Git Bash** 解释器路径；没有则返回 None。

    ``SMARTSKETCH_BASH`` 优先（显式指定），否则在 PATH 上找 bash。命中 ``System32\\bash.exe``
    （WSL 启动器）时视为不可用：它能执行文件，但语义与 CI/Linux 上的 bash 不同，用它跑出来的
    结果没有参考价值。
    """
    explicit = os.environ.get("SMARTSKETCH_BASH")
    if explicit:
        return explicit
    found = shutil.which("bash")
    if found and found.lower().endswith(_WSL_BASH):
        return None
    return found


@pytest.fixture(scope="session")
def bash() -> str:
    """Git Bash 解释器的路径；找不到时跳过，而不是抛 WinError 193 或误用 WSL bash。"""
    executable = find_bash()
    if executable is None:
        pytest.skip(BASH_SKIP_REASON)
    return executable


@pytest.fixture
def utf8_subprocess_env() -> dict[str, str]:
    """子进程环境：两端都用 UTF-8，避免中文 Windows 的 GBK 解码把用例判红。"""
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    return env


def capture_text(args: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
    """``subprocess.run`` 的包装：捕获输出时显式按 UTF-8 解码。"""
    kwargs.setdefault("capture_output", True)
    return subprocess.run(args, encoding="utf-8", errors="replace", **kwargs)
