"""进程启动时刻：用于判断「设置已保存但还没重启」。

只记一次；重启后重新取值，因此保存过配置的进程会一直显示「需要重启」，
直到用户真正重启软件。
"""

from __future__ import annotations

from time import time

#: 本进程开始服务的时刻（秒）
_STARTED_AT: float = time()


def process_started_at() -> float:
    return _STARTED_AT
