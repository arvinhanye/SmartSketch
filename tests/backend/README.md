# 后端测试

归 Backend Agent 与 Data/AI Agent。被测对象：`src/backend/app/` 的 api、schemas、services、repositories、workers。

- 命名：`test_<被测单元>_<场景>.py`，例如 `test_prerequisite_cycle_rejected.py`。
- 按层组织：路由测协议与错误码，服务测领域规则，仓储测 `course_id` 隔离与 Cypher 结果。
- 运行器配置属于 M0-03；落地后把命令接进 `scripts/verify/backend.sh` 的预留调用点。
- 覆盖优先级见 [`../README.md`](../README.md) 的六项清单，其中 1～6 大部分落在这里。
