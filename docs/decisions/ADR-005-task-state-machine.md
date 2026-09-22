# ADR-005：统一文档处理任务状态机，保留 `cancelled` 但 MVP 不实现取消

> **部分修订**：第 2 条「MVP 不实现取消」已被 [ADR-006](ADR-006-implement-task-cancel.md) 取代——
> 取消端点改为在 MVP 实现，`cancelled` 成为正常可达终态。本文其余内容（状态机序列、`persisting`
> 阶段、枚举一次定稿原则）仍然有效，保留原文不改写。


- **日期**：2026-09-22
- **背景**：`specs/course-knowledge-graph.md` 验收条件 2 的状态机为 `queued → parsing → extracting → merging → awaiting_review → completed/failed`；参考方案 S2 §4.3.2 的状态机另有「入库中」与「已取消」，§6.5 还提供 `POST /api/tasks/{tid}/cancel`。两者必须统一：按 ADR-004，状态枚举是 SSE 事件契约的一部分，而对做穷尽分支的前端来说**枚举增值是破坏性变更**，留到以后补就要把契约升到 v2。
- **决定**：v1 契约采用如下状态机，规范表述落在 `src/contracts/README.md`：

```text
queued → parsing → extracting → merging → persisting → awaiting_review → completed
         └── 任一非终态 ──→ failed
         └── （v1 预留，MVP 不产生）──→ cancelled
```

  1. **采纳「入库中」，命名 `persisting`**，位于 `merging` 与 `awaiting_review` 之间。理由：`docs/architecture.md` 数据流第 2 步已经存在「DAG 校验 → 写入草稿图谱」这一真实阶段，它跨 Neo4j 与 SQLite 两个存储（ADR-002），其失败原因（前置关系成环被拒、图库不可用、跨存储写入需补偿）与解析/抽取/融合失败完全不同；不单独建模就无法向教师说明失败发生在哪一步。对应 `docs/product.md` 教师流程中的「校验」，前端展示文案为「校验入库」。
  2. **保留 `cancelled` 为终态枚举值，但 MVP 不产生该状态，也不提供 `POST /api/v1/tasks/{task_id}/cancel`**。理由：取消需要 worker 协作式中断、跨两个存储的部分写入补偿，以及「取消与完成竞争」的处理，超出 AGENTS.md §1 的 MVP 目标；而在枚举里先占位是向后兼容的，将来上线取消功能不必升 v2。
  3. 前端必须把 `cancelled` 当作终态渲染；后端必须有一条测试断言 MVP 的 worker 不会发出该状态。取消端点需先有独立规格与任务，才能实现。
- **后果**：
  - `specs/course-knowledge-graph.md` 验收条件 2 与本 ADR 不一致，由产品/协调 Agent 按 M0-06 同步；本任务不拥有 `specs/`，未直接修改。
  - 状态机在 M0-04b 变成契约真源 `api.v1.yaml` 里的 `TaskStage` 枚举（ADR-004 改判后真源是 YAML，不是 Pydantic），`persisting` 的 SSE 事件与失败原因分类同批定稿。
  - v1 存在一个当前不可达的枚举值，代价是它无法被状态转换测试覆盖，且可能诱使 Agent 去实现取消功能；因此契约中显式标注为「预留，MVP 不产生」。
