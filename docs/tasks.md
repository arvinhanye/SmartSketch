# 任务看板

> 状态：`TODO` → `IN PROGRESS` → `BLOCKED` / `DONE`。认领或完成任务时更新本表；每个 DONE 项必须指向验收证据和交接文件。

## 当前里程碑：M0 协作与应用骨架

| ID | 状态 | 任务 | 负责人 | 验收条件 | 证据 |
| --- | --- | --- | --- | --- | --- |
| M0-01 | DONE | 建立多 Agent 协作、文档、规格、源码目录骨架 | Codex | 必需文件齐全；基础校验通过 | `scripts/verify.sh`；`docs/handoffs/codex-m0-project-scaffold.md` |
| M0-02 | TODO | 初始化 Vue 3 + TypeScript + Vite 前端 | Frontend Agent | 可启动；具备最小路由、类型检查与测试命令 | 待补充 |
| M0-03 | TODO | 初始化 FastAPI 后端与健康检查 | Backend Agent | 可启动；`GET /health` 有契约和测试 | 待补充 |
| M0-04a | TODO | 起草 v1 契约真源（REST DTO、SSE 任务事件、图谱导入/导出）与 `scripts/gen-contracts.sh` | Backend Agent | 三类契约在 `src/contracts/v1/python/` 齐全并符合 ADR-004、ADR-005；生成物已入库；`./scripts/gen-contracts.sh --check` 通过 | 待补充 |
| M0-04b | TODO | 前端消费 v1 生成类型并回送契约反馈（依赖 M0-04a 为 DONE） | Frontend Agent | `src/frontend/` 只从 `src/contracts/v1/generated/typescript/` 导入契约类型，无本地重定义或 `any` 绕过；任务状态穷尽分支含 `cancelled`；反馈写入交接文件 | 待补充 |
| M0-05 | TODO | 定义 Neo4j/SQLite 开发环境与本地启动方式 | Data/Backend Agent | 无密钥可启动依赖；环境变量文档完整 | 待补充 |
| M0-06 | TODO | 按 ADR-004、ADR-005 同步 `specs/course-knowledge-graph.md` | 产品/协调 Agent | 验收条件 2 的状态序列与 ADR-005 一致并标注 `cancelled` 为 MVP 不产生的预留终态；「待细化」中失效的 M0-04 引用改为 M0-04a | 待补充 |
| S-01 | DONE | 确定 `src/contracts/` 的契约格式与单一真源，并拆分 M0-04 | Claude（协调） | ADR-004、ADR-005 已记录；契约目录与命名规则可供冷启动 Agent 使用；M0-04 已拆分为顺序子任务 | `./scripts/verify.sh`；`docs/handoffs/claude-s01-contract-format.md` |

> **M0-04a 与 M0-04b 顺序执行，不并行。** `src/contracts/` 只由 M0-04a 写入，`src/frontend/` 只由 M0-04b 写入；前端不得直接改契约，需求通过交接文件回送后端 Agent 改真源后重新生成（ADR-004、AGENTS.md §3）。

## 下一里程碑：M1 课程资料到草稿图谱

| ID | 状态 | 任务 | 负责人 | 验收条件 |
| --- | --- | --- | --- | --- |
| M1-01 | TODO | 课程与资料上传 API | Backend Agent | 资料记录、格式校验、任务创建、错误响应均有测试 |
| M1-02 | TODO | 文档解析与分块 | Data/AI Agent | 支持四种格式；分块保留定位来源 |
| M1-03 | TODO | 节点关系抽取与融合 | Data/AI Agent | 四类关系；低置信度项可审核；课程隔离 |
| M1-04 | TODO | 前置关系 DAG 校验 | Backend Agent | 环路拒绝、错误可解释、自动化测试 |
| M1-05 | TODO | 教师审核与发布版本 | Full-stack Agent | 可编辑、发布、读取已发布版本 |

## 未决问题

| ID | 问题 | 决策人 | 需要在何时确认 |
| --- | --- | --- | --- |
| D-01 | MVP 首批课程示例和脱敏资料来源 | 产品负责人 | M1 开始前 |
| D-02 | 首个 OpenAI 兼容模型供应商与预算上限 | 技术负责人 | 接入抽取服务前 |
| D-03 | 登录是否先采用本地演示角色 | 产品负责人 | M0-03 前 |
