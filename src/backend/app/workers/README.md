# workers/

长时文档处理任务与状态迁移，任务状态和 SSE 事件使用 `src/contracts/` 的契约（ADR-005）。

不放：Web 请求处理（→ `api/`）、领域规则（→ `services/`）、直接拼 Cypher（→ `repositories/`）。
