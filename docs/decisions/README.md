# 架构决策记录（ADR）索引

一条决策一个文件。本文件只做索引，**不要把决策正文写进来**。

| 编号 | 决定 | 日期 |
| --- | --- | --- |
| [ADR-001](ADR-001-vue3-g6-2d-graph.md) | 前端采用 Vue 3 + AntV G6 的 2D 图谱 | 2026-09-22 |
| [ADR-002](ADR-002-neo4j-sqlite-dual-store.md) | Neo4j + SQLite 双存储 | 2026-09-22 |
| [ADR-003](ADR-003-answer-source-citation.md) | 可信问答以来源引用为硬契约 | 2026-09-22 |
| [ADR-004](ADR-004-contract-single-source-of-truth.md) | 契约以 Pydantic 为单一真源，生成 OpenAPI 与 TypeScript 类型 | 2026-09-22 |
| [ADR-005](ADR-005-task-state-machine.md) | 统一文档处理任务状态机，保留 `cancelled` 但 MVP 不实现取消（第 2 条已被 ADR-006 修订） | 2026-09-22 |
| [ADR-006](ADR-006-implement-task-cancel.md) | MVP 实现任务取消，修订 ADR-005 第 2 条 | 2026-09-22 |
| [ADR-007](ADR-007-study-material-bonus-scope.md) | 学习材料生成纳入范围，定位为加分项 | 2026-09-22 |

## 新增一条 ADR

1. 新建 `docs/decisions/ADR-<下一个编号>-<英文 slug>.md`，**不要追加到任何已有文件**——
   这是 S-03 拆分单文件写争用点的目的（见 `AGENTS.md` §3「写争用规则」）。
2. 正文四段固定：`**日期**`、`**背景**`、`**决定**`、`**后果**`。
3. 在上表末尾加一行。索引每次只加一行，并行任务冲突时保留双方即可。
4. 编号取当前最大值 +1；两个 worktree 同时占用同一编号时，后合并的一方改号并同步引用。
