# 架构与边界

## 当前审查与实施入口

- 2026-09-22 现状核查与技术全景：[架构审查](architecture-review-2026-09-22.md)。主目录仍是骨架；Claude 两个 worktree 的契约真源冲突尚待裁决。
- 单轮实施范围与依赖：[原子任务清单](atomic-task-plan.md)，机器可读版为 `docs/atomic-tasks.json`。清单中的建议不自动替代已确认 ADR。
- 后续完成后审查：[Claude → Codex 流程](claude-review-workflow.md)。

## 逻辑分层

```text
Vue 3 Web（教师端 / 学生端）
          │ REST + SSE
FastAPI API（认证边界、DTO、依赖注入）
          │
领域服务（导入、抽取、融合、审核、问答、路径）
          │
仓储层 ────────────── Worker
  │                      │
Neo4j（图谱/向量）    SQLite（课程、用户、任务、进度、版本）
```

## 源码映射

| 目录 | 职责 | 不应包含 |
| --- | --- | --- |
| `src/frontend/` | Vue 页面、组件、状态、API/SSE 客户端、G6 适配 | 后端实体规则、Cypher |
| `src/backend/app/api/` | FastAPI 路由与依赖注入 | 业务编排、查询字符串 |
| `src/backend/app/schemas/` | 请求/响应/事件 DTO | 持久化实现 |
| `src/backend/app/services/` | 领域规则、流程编排 | HTTP/框架细节 |
| `src/backend/app/repositories/` | Neo4j / SQLite 读写 | 产品策略 |
| `src/backend/app/workers/` | 长时文档任务与状态迁移；以与 API **同机的独立进程**运行，经 SQLite 租约领取任务（`specs/task-processing.md` §8，ADR-011） | Web 请求处理；跨机器部署 |
| `src/contracts/` | 前后端共享 API 和 SSE 事件约定 | 供应商专用密钥/实现 |

## 契约真源与生成物（ADR-004）

下表是 ADR-004 的裁定（2026-09-22 由 ArvinHan 签收），完整理由见 `docs/decisions.md`。**任何 REST / SSE / 图谱格式变更的第一步必须是改真源**；本节固定分工，避免两端各写一份接口。

| 角色 | 位置 | 谁写 | 规则 |
| --- | --- | --- | --- |
| 人工编辑真源 | `src/contracts/api.v1.yaml`（OpenAPI 3.1） | 后端 Agent | 唯一允许人工编辑的机器可读契约；任何 REST/SSE/图谱格式变更的第一步 |
| 配套语义文档 | `src/contracts/errors.v1.md`、`src/contracts/events.v1.md` | 后端 Agent | 只写 OpenAPI 表达不了的时序与语义，不重复定义结构 |
| 生成物 | `src/contracts/v1/generated/`（`openapi.json`、`schemas/*.schema.json`、`python/`、`typescript/`） | `./scripts/gen-contracts.sh` | 入库、**禁止手工编辑**；两次生成字节一致；`--check` 不通过即拒绝合入 |
| 后端消费 | `src/backend/app/schemas/` | 后端 Agent | 只放不对外暴露的内部模型；对外 DTO 从 `v1/generated/python/` 导入 |
| 前端消费 | `src/frontend/src/api/` | 前端 Agent | 类型从 `v1/generated/typescript/` 导入；不得重写、断言或 `any` 绕过 |

- REST 路径前缀与 wire 枚举已由 A02 裁定（ADR-009），见下一节。
- 生成器及版本锁在 `src/contracts/toolchain.txt`；缺工具时生成脚本必须非 0 退出，只有显式降级才允许跳过并打印未完成验收标记。
- 契约的**表达方式**由 ADR-004 裁定，契约的**内容正确性**不由它保证：来源非空、事件判别联合等约束仍须各自的负例测试复验；「引用确属同一课程同一发布版本」schema 表达不了，必须在服务层校验。

## API 前缀与 wire 枚举（A02 / ADR-009）

> **签收状态：已签收**，ArvinHan，2026-09-22。本节是路径前缀、枚举取值与大小写的规范表；`src/contracts/api.v1.yaml` 导入 main（A10）时必须与本表逐值一致，不一致以本表为准回改真源，并同批重新生成。状态转换语义不在本节，见 `specs/task-processing.md`（A03 / ADR-010）。

### 路径前缀

- 所有 REST 与 SSE 端点前缀为 **`/api/v1`**；唯一例外是 `GET /health`（运维探针，不随契约版本变化）。
- 主版本号四处同步：真源文件名 `api.v1.yaml` = URL 前缀 `/api/v1` = 生成物目录 `v1/` = 配套文档 `events.v1.md`/`errors.v1.md`。破坏性变更成套新建 v2，不在 v1 路径下混入。
- S2 方案表 6.6 的 `/api/...` 是省略版本号的书面缩写，不是另一套路径。实现、测试与前端客户端一律写 `/api/v1`；ADR-004 端点迁移表（22 路径 / 29 操作）无需改动。

### 大小写规则

1. **UPPER_SNAKE 只用于两类**：错误码 `ErrorCode`，以及图关系类型 `RelationType`（与 Neo4j 关系类型标签同形）。
2. **其余一切 wire 枚举值一律 lower_snake**，包括领域状态、判别字段取值与 SSE 事件名。
3. 新增枚举若既不是错误码也不是图关系类型，必须 lower_snake；同一概念不得出现大小写变体或同义别名（例如不得写 `canceled`、`md`、`NOT_COVERED` 作 wire 值）。

### wire 枚举表

取值顺序即真源中的顺序。「740adb 核对」指与 `claude/worktree-contract-conflicts-740adb` `978671e` 的 `api.v1.yaml` 逐值比对的结果。

| schema | 取值 | 大小写 | 用于 | 740adb 核对 / 备注 |
| --- | --- | --- | --- | --- |
| `ErrorCode` | `UNAUTHENTICATED`、`COURSE_FORBIDDEN`、`ROLE_FORBIDDEN`、`NOT_FOUND`、`GRAPH_NOT_PUBLISHED`、`UNSUPPORTED_FORMAT`、`FILE_TOO_LARGE`、`VALIDATION_ERROR`、`CYCLE_DETECTED`、`DANGLING_ENDPOINT`、`DUPLICATE_RELATION`、`NODE_LOCKED`、`TASK_NOT_CANCELLABLE`、`PUBLISH_BLOCKED`、`RATE_LIMITED`、`LLM_UNAVAILABLE` | UPPER | `Error.code` | 一致。**不含** `NOT_COVERED`、`TASK_FAILED`：它们是领域状态，不是错误码 |
| `RelationType` | `CONTAINS`、`PREREQUISITE`、`RELATED_TO`、`EXAMPLE_OF` | UPPER | `Relation.type` | 一致。闭集；S2 图 6.3 的 `RELATED`、`APPLIES_TO` 不得使用（ADR-008） |
| `TaskStage` | `queued`、`parsing`、`extracting`、`merging`、`persisting`、`awaiting_review`、`completed`、`failed`、`cancelled` | lower | `Task.stage`、`TaskEvent.stage`、`Document.parse_status` | 一致。终态为 `completed`、`failed`、`cancelled`；转换、触发者与取消语义见 `specs/task-processing.md`（ADR-010） |
| `CourseStatus` | `draft`、`published`、`revising` | lower | `Course.status` | 一致 |
| `KnowledgePointStatus` | `draft`、`low_confidence`、`approved`、`rejected` | lower | `KnowledgePoint.status`、`Relation.status` | 一致。名字带 KnowledgePoint，但关系也复用；自动降级的边取 `low_confidence` |
| `KnowledgePointType` | `concept`、`theorem`、`formula`、`method`、`example` | lower | `KnowledgePoint.type` | 一致 |
| `NodeSource` | `ai`、`manual` | lower | `KnowledgePoint.source`、`Relation.source` | 一致。自动降级只作用于未经教师确认的 `ai` 边（`status ∈ {draft, low_confidence}`，见规格「前置关系成环处理」） |
| `DocumentFormat` | `pdf`、`docx`、`txt`、`markdown` | lower | `Document.format` | 一致。wire 值是 `markdown`，扩展名 `.md` 不是枚举值 |
| `Role` | `teacher`、`student` | lower | `User.role` | 一致 |
| `MasteryStatus` | `unknown`、`learning`、`mastered` | lower | 进度读写 | 一致 |
| `ChatStatus` | `answered`、`not_covered` | lower | `ChatResponse.status`（判别字段）、`ChatMetaEvent.status` | 一致 |
| `NotCoveredReason` | `no_retrieval_hit`、`below_similarity_threshold`、`out_of_course_scope`、`all_citations_invalidated` | lower | `ChatNotCovered.reason` | 一致；`ff30e0` 无此枚举 |
| 内联枚举 | `ChatTurn.role`：`user`、`assistant`；`LoginResponse.token_type`：`bearer`；`/health` 的 `status`：`ok` | lower | 见左 | 一致 |

SSE 事件名（`event:` 行；问答流的 `data.event` 判别字段与之同值）：

| 流 | 事件名 | 终止事件 |
| --- | --- | --- |
| 任务进度 `GET /api/v1/tasks/{tid}/events` | `stage`、`done`、`error`、`cancelled` | 只覆盖处理阶段。每个连接恰好以一条结束事件收尾：`stage = awaiting_review` 快照或 `done` / `error` / `cancelled` 之一（互斥），随后关流；`completed` 不经已有连接送达，通过任务查询或课程发布状态观察（ADR-010） |
| 问答 `POST /api/v1/courses/{cid}/chat` | `meta`、`delta`、`done`、`error` | `done` / `error` 互斥且恰好一次 |

### 文档用语 → wire 值

AGENTS.md、ADR-003、`.claude/rules/backend.md` 等共同契约沿用概念名；它们不是 wire 字面值。新代码、测试断言与前端分支**只使用右列**。

| 文档用语 | wire 表达 | 说明 |
| --- | --- | --- |
| `NOT_COVERED`、「资料未覆盖」 | HTTP 200 + `status: "not_covered"` + `reason: NotCoveredReason` + `citations: []` | 概念名。字段名是 `reason`，不是 `not_covered_reason`（740adb 的 `src/contracts/README.md` 写法有误，以 YAML 为准） |
| `TASK_FAILED`、「任务失败」 | HTTP 200 + `stage: "failed"` + `error: Error` | 同上，领域状态不是 HTTP 错误 |
| S2「已上传」 | `queued` | |
| S2「入库中」、前端文案「校验入库」 | `persisting` | 覆盖 DAG 校验与草稿写入 |
| S2「完成」（处理流程结束） | `awaiting_review` | 处理完成待审核；`completed` 由教师发布触发，发布时按任务水位推进（含内容被全部驳回的任务），不经 SSE 送达（A03 已复核，ADR-010） |
| 「已取消」 | `cancelled` | 双 l |
| 前置 / 包含 / 相关 / 应用实例 | `PREREQUISITE` / `CONTAINS` / `RELATED_TO` / `EXAMPLE_OF` | S2 成环降级的目标「相关」即 `RELATED_TO` |

## 核心数据模型

- SQLite：`Course`、`Material`、`ProcessingTask`（含租约与尝试字段）、`TaskChunkCheckpoint`、`CourseLock`、`ModelCall`、`GraphVersion`、`LearningProgress`、`QuestionSession`。其中 `ProcessingTask`、`TaskChunkCheckpoint`、`CourseLock`、`ModelCall` 的字段与迁移规则见 `specs/task-processing.md` §8（ADR-011）。`GraphVersion` 保存每个版本的规范化快照与摘要，`Course` 保存发布指针与草稿修订号（见下节「图谱版本与跨库发布」）。
- Neo4j：`Course`、`KnowledgePoint`、`SourceChunk`；关系 `CONTAINS`、`PREREQUISITE`、`RELATED_TO`、`EXAMPLE_OF`，以及来源关联。知识点、关系、章节带 `version_id`（草稿为保留值 `"draft"`）；文本块不可变、各版本共享。
- 所有查询和写入均以 `course_id` 为第一隔离条件，图查询同时以 `version_id` 为第二条件。`PREREQUISITE` 只能形成 DAG。

## 图谱版本与跨库发布（A04 / ADR-012）

> **签收状态：已签收**，ArvinHan，2026-09-23（ADR-012，含修订 1）。规范文本只有一份，在 `specs/teacher-review-publish.md`「图谱版本与跨库发布协议」V1～V12；本节只列架构层面的结论，不复制步骤表。

| 问题 | 结论 |
| --- | --- |
| 版本标识 | 内部 `version_id`（ULID，尝试开始时生成、永不复用）；对外整数 `version`（按课程、提交时分配 `max+1`，无空洞） |
| 快照位置 | SQLite `GraphVersion.snapshot_json` 是版本内容的真相，附 sha256 摘要；Neo4j 按 `version_id` 物化副本供遍历与向量检索 |
| 文本块固定 | 文本块按资料修订（资料 + 内容哈希 + 解析器版本）生成 ID，一经写入不可变；快照固定修订列表，检索按 `revision_id` 过滤，不按 `material_id`（修订 1） |
| 向量版本 | 知识点向量随版本复制；文本块向量共享；Neo4j 向量索引「多取再过滤」 |
| 向量空间 | 运行时只有一个空间（模型 + 维度）；换模型须停机离线重新向量化 Neo4j 实际存量中的全部文本块、草稿知识点与已提交版本副本，并按存量核对；缓存与中间产物中的向量带空间标识；运行时写入只接受当前空间，只有迁移命令可写迁移目标空间（修订 2 补注）；配置与记录不一致即拒绝启动；向量是派生数据，重算不产生新版本（修订 1、修订 2） |
| 提交点 | 唯一：SQLite 中「CAS 切换发布指针 + 分配版本号 + T7 推进任务」的单个事务。之前任一步失败，按 `(course_id, version_id)` 删除 Neo4j 副本并把尝试记为 `failed`，学生继续读旧版本 |
| 互斥 | 同课程同时至多一个发布/回滚（SQLite 部分唯一索引）；草稿写入与建快照共用 A06 的 SQLite 课程写锁，发布只在读草稿的几秒内持锁 |
| 回滚编号 | 以历史版本内容前滚为新版本号；目标与当前版本摘要相同则幂等，不产生新号；回滚不改草稿、不推进任务 |
| 重复发布 | 发布集合摘要等于当前发布版 → 幂等返回 `unchanged: true`，不产生新号 |
| 读取绑定 | 学生请求开始时读一次指针，全程使用同一 `version_id`；MVP 不回收已提交版本 |
| 崩溃恢复 | worker 周期回收步骤清扫过期尝试与 `cleanup_pending`；Neo4j 有而 SQLite 无的版本只告警不删除 |

跨任务影响：ADR-012 修订 ADR-011 决定 6（课程写锁由「两处持有」扩大到所有草稿写入）；修订 1 再修订 ADR-011 决定 5、7（块 ID 按资料修订生成、来源块删除保护）；新增错误码 `PUBLISH_IN_PROGRESS`、`COURSE_BUSY` 交 B08，DTO 字段交 B11，配置 `PUBLISH_LEASE_SECONDS`、`COURSE_LOCK_WAIT_SECONDS` 交 A07。

## 数据流

1. 上传资料 → SQLite 创建任务/资料记录 → Worker 进程经租约领取任务 → 解析和分块。
2. Worker 调用模型抽取候选节点/关系 → 融合消歧 → DAG 校验 → 写入草稿图谱。草稿按任务记录贡献，T6 提交后才可见，失败任务的内容从失败起即不可见（ADR-011 修订 1）。DAG 校验在 `persisting` 阶段：自动候选成环时把环上未经教师确认的 `ai` 边中置信度最低者降级为 `RELATED_TO` 并送审核，任务不因此失败；人工编辑成环直接 409 拒绝。两者区别见 `specs/course-knowledge-graph.md`「前置关系成环处理」。
3. Worker 更新任务状态，API 经 SSE 发送进度；教师审核并发布不可变图谱版本：持课程写锁读取草稿建快照 → SQLite 写快照 → Neo4j 按 `version_id` 物化并核对摘要 → SQLite 单事务切换发布指针（唯一提交点）。协议见上节「图谱版本与跨库发布」。
4. 学生浏览发布版本（请求开始时绑定一个 `version_id`）；学习进度保存在 SQLite，路径服务查询 Neo4j 前置关系并计算候选与理由。
5. 问答服务检索课程图谱与来源片段，生成带引用答案；若证据不足返回 `NOT_COVERED`（wire：`status: "not_covered"` + `reason`，见上方「文档用语 → wire 值」）。

## 关键质量边界

- API 响应、任务事件、图谱导入/导出格式先在 `src/contracts/` 版本化。
- LLM 是可替换适配器，基础 URL、模型和密钥均来自环境变量。
- 每次教师修改与发布都保留版本号和审计信息；破坏性迁移需提供回滚说明。

## 持续集成（当前骨架阶段）

- `.github/workflows/ci.yml` 在 push、pull request 和手动触发时运行 `scripts/verify.sh`，并检查该脚本的 Bash 语法；工作流只使用只读仓库权限，不注入项目密钥。
- 现阶段前后端只有目录骨架，CI 的成功仅表示基础文件、JSON 和文档约束通过，不代表应用构建或业务测试通过。
- 前后端依赖清单、实际测试与契约漂移检查就绪后，由原子任务 K11 扩展同一质量门禁；新增检查应失败即退出，不能以静默跳过冒充通过。
