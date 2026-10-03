"""Backend test-session defaults.

C13: the served entry ``app.main:app`` refuses to import without AUTH_JWT_SECRET (IAM-23),
and several test modules import ``app.main`` at collection time. Provide a test-only key
unless the environment already sets one; tests that need it missing remove it themselves.

Windows 可移植性：若干用例用 ``subprocess.run([sys.executable, ...], text=True)`` 跑 CLI 脚本，
却不固定编码。此时子进程按**当前 locale** 编码 stdout/stderr——中文 Windows 是 GBK，GitHub 的
Windows 运行器是 cp1252——而评测脚本会打印中文（``评测``、``栈``）与 ``✓``（U+2713），两者都
会抛 ``UnicodeEncodeError``，脚本以非零码退出，用例就在断言 ``returncode == 0`` 时失败，报错
却指向被测脚本，实际原因是测试侧未固定编码。

``PYTHONIOENCODING=utf-8`` 让子进程始终输出 UTF-8，与 Linux/CI 上一致（纯 ASCII 输出时
字节序列不变，因此不影响既有断言）。父进程侧的读取由各用例自己的 ``encoding=`` 决定；
``test_k02`` 等含中文断言的用例已在调用点显式指定 UTF-8。
"""

import os

os.environ.setdefault("AUTH_JWT_SECRET", "backend-tests-only-signing-key-not-a-real-secret")
os.environ.setdefault("PYTHONIOENCODING", "utf-8")
