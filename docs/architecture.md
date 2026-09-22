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
| `src/backend/app/schemas/` | 请求/响应/事件 DTO | 持久化实现 |
| `src/backend/app/services/` | 领域规则、流程编排 | HTTP/框架细节 |
| `src/backend/app/repositories/` | Neo4j / SQLite 读写 | 产品策略 |
| `src/backend/app/workers/` | 长时文档任务与状态迁移 | Web 请求处理 |
| `src/contracts/` | 前后端共享 API 和 SSE 事件约定 | 供应商专用密钥/实现 |
| `prompts/` | 版本化提示词资产（含版本、模型、温度、修改说明） | 密钥、课程原始资料 |
| `evals/` | 标注集、评测脚本与报告（抽取准确率、问答测试集、性能实测） | 真实课程版权资料 |

## 核心数据模型

命名基线见 ADR-004；`src/contracts/` 与实现代码不得引入同义别名。

- SQLite（模型名 / 表名）：`User`/`users`、`Course`/`courses`、`CourseMember`/`course_members`、
  `Document`/`documents`、`ProcessingTask`/`tasks`、`GraphSnapshot`/`snapshots`、
  `LearningProgress`/`progress`、`ChatLog`/`chat_logs`、`EditLog`/`edit_logs`、`LlmCall`/`llm_calls`。
- Neo4j 节点：`Course`、`Chapter`、`Document`、`KnowledgePoint`、`Chunk`。
- Neo4j 关系：课程结构 `HAS_CHAPTER`、`HAS_DOCUMENT`、`HAS_CHUNK`、`EVIDENCE`；
  教学关系仅限 `CONTAINS`、`PREREQUISITE`、`RELATED_TO`、`EXAMPLE_OF`。
- `KnowledgePoint` 必含：`id`、`course_id`、`name`、`aliases`、`type`、`definition`、
  `importance`、`difficulty`、`level`、`confidence`、`status`、`source`、`locked`、`embedding`。
  `level` = 该节点在前置关系图中的最长前置路径长度，供层次布局与路径排序使用。
- 所有查询和写入均以 `course_id` 为第一隔离条件。`PREREQUISITE` 只能形成 DAG。

## 数据流

1. 上传资料 → SQLite 创建任务/资料记录 → Worker 解析和分块。
2. Worker 调用模型抽取候选节点/关系 → 融合消歧 → DAG 校验 → 写入草稿图谱。
3. Worker 更新任务状态，API 经 SSE 发送进度；教师审核并发布不可变图谱版本。
4. 学生浏览发布版本；学习进度保存在 SQLite，路径服务查询 Neo4j 前置关系并计算候选与理由。
5. 问答服务检索课程图谱与来源片段，生成带引用答案；若证据不足返回 `NOT_COVERED`。

## 关键质量边界

- API 响应、任务事件、图谱导入/导出格式先在 `src/contracts/` 版本化。
- LLM 是可替换适配器，基础 URL、模型和密钥均来自环境变量。
- 每次教师修改与发布都保留版本号和审计信息；破坏性迁移需提供回滚说明。
