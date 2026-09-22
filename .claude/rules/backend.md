# 后端规则

- 使用 FastAPI、Pydantic 与类型标注；路由仅做协议转换和依赖注入。
- 业务规则放入 `services/`，持久化/Cypher 放入 `repositories/`，请求响应模型放入 `schemas/`。
- 所有数据查询必须按 `course_id` 隔离；新增 `PREREQUISITE` 关系前执行 DAG 环检测。
- 文档处理必须异步建任务，任务状态和 SSE 事件使用 `src/contracts/` 中的契约。
- 问答响应必须返回来源；不足以回答时返回 `NOT_COVERED` 状态和可解释原因。
