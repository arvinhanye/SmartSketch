# 源码布局

此目录只放应用代码与共享契约；产品、架构、决策和任务信息分别位于根目录 `docs/` 与 `specs/`。

- `frontend/`：Vue 3 应用（页面、组件、组合式逻辑、API/SSE 客户端、G6 适配）。
- `backend/app/`：FastAPI 分层应用。
- `contracts/`：前后端共享的 REST、SSE、图谱导入/导出协议。
