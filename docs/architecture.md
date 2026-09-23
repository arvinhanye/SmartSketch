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
| `src/backend/app/workers/` | 长时文档任务与状态迁移 | Web 请求处理 |
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

- REST 路径前缀现状为 `/api/v1`，与生成物目录 `v1/` 同步升级；`/health` 不带前缀。前缀与 wire 枚举的最终裁定属原子任务 A02。
- 生成器及版本锁在 `src/contracts/toolchain.txt`；缺工具时生成脚本必须非 0 退出，只有显式降级才允许跳过并打印未完成验收标记。
- 契约的**表达方式**由 ADR-004 裁定，契约的**内容正确性**不由它保证：来源非空、事件判别联合等约束仍须各自的负例测试复验；「引用确属同一课程同一发布版本」schema 表达不了，必须在服务层校验。

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

- API 响应、任务事件、图谱导入/导出格式先在 `src/contracts/` 版本化。
- LLM 是可替换适配器，基础 URL、模型和密钥均来自环境变量。
- 每次教师修改与发布都保留版本号和审计信息；破坏性迁移需提供回滚说明。

## 持续集成（当前骨架阶段）

- `.github/workflows/ci.yml` 在 push、pull request 和手动触发时运行 `scripts/verify.sh`，并检查该脚本的 Bash 语法；工作流只使用只读仓库权限，不注入项目密钥。
- 现阶段前后端只有目录骨架，CI 的成功仅表示基础文件、JSON 和文档约束通过，不代表应用构建或业务测试通过。
- 前后端依赖清单、实际测试与契约漂移检查就绪后，由原子任务 K11 扩展同一质量门禁；新增检查应失败即退出，不能以静默跳过冒充通过。
