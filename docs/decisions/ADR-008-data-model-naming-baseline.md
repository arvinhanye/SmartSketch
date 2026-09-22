# ADR-008：统一 S2 方案与仓库文档的数据模型命名

> **编号说明**：本决策在 `claude/tech-plan-review-improvements-ff30e0` 分支上原编号为 ADR-004，与
> `claude/multi-agent-contract-format-209be9` 分支的 [ADR-004](ADR-004-contract-single-source-of-truth.md)
> 撞号。按 `docs/decisions/README.md` 第 4 条「后合并的一方改号」，本文改为 ADR-008，正文未改写。
> 引用本决策的契约文件（`src/contracts/api.v1.yaml`、`errors.v1.md`、`events.v1.md`、
> `scripts/check_contracts.py`）已同步改指 ADR-008。

- **日期**：2026-09-22
- **背景**：S2 V0.4 与仓库 `AGENTS.md` / `docs/architecture.md` / `specs/` 在关系类型、图节点、SQLite 模型和任务状态机上存在四处命名与范围分歧。多 Agent 并行实现会产生接口漂移，且仓库模型缺少用户/角色实体，无法支撑赛题要求的教师端与学生端双角色。
- **决定**：
  1. 同名异称以仓库标识符为准：`RELATED_TO`、`EXAMPLE_OF` 保持不变；文本块节点统一为 `Chunk`（沿用 S2 与所参考开源项目的通用术语）。
  2. 仓库补齐 S2 已设计而缺失的内容：Neo4j 增加 `Chapter`、`Document` 节点与 `HAS_CHAPTER`、`HAS_DOCUMENT`、`HAS_CHUNK`、`EVIDENCE` 结构关系；`KnowledgePoint` 补齐 `aliases`、`type`、`importance`、`difficulty`、`level`、`source`、`locked`、`embedding`；SQLite 增加 `users`、`course_members`、`edit_logs`、`llm_calls` 四张表。
  3. SQLite 以「模型名 / 表名」两列表述，消除 PascalCase 与 snake_case 的伪冲突。
  4. 任务状态机合并两侧：`queued → parsing → extracting → merging → persisting → awaiting_review → completed`，并新增此前两份文档都遗漏的 `cancelled` 终态（S2 接口表已有 `POST /api/tasks/{tid}/cancel`）。**状态机的规范表述以 [ADR-005](ADR-005-task-state-machine.md) 为准，`cancelled` 的可达性以 [ADR-006](ADR-006-implement-task-cancel.md) 为准**；本条只记录「两侧命名必须合并」这一结论，不再单独维护一份状态序列。
- **后果**：`src/contracts/`、Cypher、DTO 与前端类型以本 ADR 为唯一命名基线，不得引入同义别名；`scripts/verify/contracts.sh` 增加命名漂移与状态机门禁。S2 源文档需在下一版本同步三处措辞（图 6.3 的 `RELATED`、`APPLIES_TO`，4.3.2 的状态枚举），该项未在本次变更范围内。
