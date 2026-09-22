# 架构决策记录（ADR）

## ADR-001：前端采用 Vue 3 + AntV G6 的 2D 图谱

- **日期**：2026-09-22
- **背景**：当前赛题 MVP 需要稳定呈现关系、筛选和编辑；早期方案中的 3D 模式会增加渲染与交互复杂度。
- **决定**：使用 Vue 3、TypeScript、Vite 和 AntV G6，只交付 2D 图谱。
- **后果**：优先建设图谱可读性与审核体验；后续若引入 3D，作为独立规格与 ADR。

## ADR-002：Neo4j + SQLite 双存储

- **日期**：2026-09-22
- **背景**：图谱遍历/向量检索与业务任务、进度、版本的数据访问模式不同。
- **决定**：Neo4j 保存图谱与向量索引，SQLite 保存课程业务、任务、进度和版本元数据。
- **后果**：跨存储操作由服务层编排，必须记录失败状态并支持重试/补偿。

## ADR-003：可信问答以来源引用为硬契约

- **日期**：2026-09-22
- **背景**：课程问答必须可复核，不能仅依赖模型生成内容。
- **决定**：问答 API 要么返回至少一个可定位来源，要么返回 `NOT_COVERED`。
- **后果**：检索、提示词和响应 DTO 都需要来源字段；引用校验纳入测试。

## ADR-004：统一 S2 方案与仓库文档的数据模型命名

- **日期**：2026-09-22
- **背景**：S2 V0.4 与仓库 `AGENTS.md` / `docs/architecture.md` / `specs/` 在关系类型、图节点、SQLite 模型和任务状态机上存在四处命名与范围分歧。多 Agent 并行实现会产生接口漂移，且仓库模型缺少用户/角色实体，无法支撑赛题要求的教师端与学生端双角色。
- **决定**：
  1. 同名异称以仓库标识符为准：`RELATED_TO`、`EXAMPLE_OF` 保持不变；文本块节点统一为 `Chunk`（沿用 S2 与所参考开源项目的通用术语）。
  2. 仓库补齐 S2 已设计而缺失的内容：Neo4j 增加 `Chapter`、`Document` 节点与 `HAS_CHAPTER`、`HAS_DOCUMENT`、`HAS_CHUNK`、`EVIDENCE` 结构关系；`KnowledgePoint` 补齐 `aliases`、`type`、`importance`、`difficulty`、`level`、`source`、`locked`、`embedding`；SQLite 增加 `users`、`course_members`、`edit_logs`、`llm_calls` 四张表。
  3. SQLite 以「模型名 / 表名」两列表述，消除 PascalCase 与 snake_case 的伪冲突。
  4. 任务状态机合并两侧：`queued → parsing → extracting → merging → persisting → awaiting_review → completed`，并新增此前两份文档都遗漏的 `cancelled` 终态（S2 接口表已有 `POST /api/tasks/{tid}/cancel`）。
- **后果**：`src/contracts/`、Cypher、DTO 与前端类型以本 ADR 为唯一命名基线，不得引入同义别名；`scripts/verify.sh` 增加命名漂移与状态机门禁。S2 源文档需在下一版本同步三处措辞（图 6.3 的 `RELATED`、`APPLIES_TO`，4.3.2 的状态枚举），该项未在本次变更范围内。
