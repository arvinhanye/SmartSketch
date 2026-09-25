"""后台 worker：从 SQLite 任务表领取处理任务并按阶段推进（specs/task-processing.md §8）。

- ``parse_task``：D11，``parsing`` 阶段编排（解析 → 分块 → 块身份 → 来源块持久化 → 检查点）与
  「运行一次」入口。后续阶段（``extracting``、``merging``、``persisting``）由 E12/F13 接入。
"""
