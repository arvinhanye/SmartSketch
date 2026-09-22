# 架构与边界

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
| `src/backend/app/schemas/` | 后端内部模型与依赖装配；对外 DTO 从 `src/contracts/` 导入 | 对外 DTO 的重复定义、持久化实现 |
| `src/backend/app/services/` | 领域规则、流程编排 | HTTP/框架细节 |
| `src/backend/app/repositories/` | Neo4j / SQLite 读写 | 产品策略 |
| `src/backend/app/workers/` | 长时文档任务与状态迁移 | Web 请求处理 |
| `src/contracts/` | 前后端共享契约的单一真源（Pydantic）与生成物（OpenAPI / JSON Schema / TS） | 供应商专用密钥、实现代码、手工编辑的生成物 |

## 核心数据模型

- SQLite：`Course`、`Material`、`ProcessingTask`、`GraphVersion`、`LearningProgress`、`QuestionSession`。
- Neo4j：`Course`、`KnowledgePoint`、`SourceChunk`；关系 `CONTAINS`、`PREREQUISITE`、`RELATED_TO`、`EXAMPLE_OF`，以及来源关联。
- 所有查询和写入均以 `course_id` 为第一隔离条件。`PREREQUISITE` 只能形成 DAG。

## 数据流

1. 上传资料 → SQLite 创建任务/资料记录 → Worker 解析和分块。
2. Worker 调用模型抽取候选节点/关系 → 融合消歧 → DAG 校验 → 写入草稿图谱。
3. Worker 更新任务状态，API 经 SSE 发送进度；教师审核并发布不可变图谱版本。
4. 学生浏览发布版本；学习进度保存在 SQLite，路径服务查询 Neo4j 前置关系并计算候选与理由。
5. 问答服务检索课程图谱与来源片段，生成带引用答案；若证据不足返回 `NOT_COVERED`。

## 关键质量边界

- REST 响应、SSE 任务事件与图谱导入/导出格式的单一真源是 `src/contracts/v1/python/` 的 Pydantic 模型；OpenAPI 与 TypeScript 类型全部由 `./scripts/gen-contracts.sh` 生成并入库，不得手工编辑（ADR-004）。
- 接口变更必须先改契约真源，再改后端与前端；前端不在 `src/frontend/` 内自行定义契约类型。目录结构、命名与版本化规则见 `src/contracts/README.md`。
- 文档处理任务状态机为 `queued → parsing → extracting → merging → persisting → awaiting_review → completed`，任一非终态可转 `failed`；`cancelled` 是 v1 预留终态，MVP 不产生，也不提供取消端点（ADR-005）。
- LLM 是可替换适配器，基础 URL、模型和密钥均来自环境变量。
- 每次教师修改与发布都保留版本号和审计信息；破坏性迁移需提供回滚说明。
