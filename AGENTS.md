# AGENTS.md — SmartSketch 共同工作契约

本文件是 Codex、Claude 与人工成员共同遵守的项目规则。所有任务先读本文件，再读与工作范围相关的 `docs/`、`specs/` 和角色规则。

## 1. 项目与当前边界

SmartSketch（中文名：智绘学途）是面向高校课程的 AIGC 知识图谱构建与学习导航系统。MVP 的唯一目标是让教师将课程资料生成、审核并发布为课程知识图谱；学生浏览图谱、标记掌握进度、获得可解释学习路径，并得到带出处的课程问答。

- 前端：Vue 3 + TypeScript + Vite + AntV G6（仅 2D 图谱）。
- 后端：Python + FastAPI。
- 数据：Neo4j（图谱与向量索引）+ SQLite（业务、任务、进度）。
- 文档：PDF、DOCX、TXT、Markdown；关系类型仅限 `CONTAINS`、`PREREQUISITE`、`RELATED_TO`、`EXAMPLE_OF`。
- 不在本阶段实现：3D 图谱、跨课程融合、生产级 SSO、移动端原生应用与多租户计费。

完整产品定义见 `docs/product.md`，技术边界见 `docs/architecture.md`。文档和规格是实现的约束，而不是备忘录。

## 2. 开始任务前

1. 阅读本文件、`docs/tasks.md`（索引）与对应的 `docs/tasks/<里程碑>.md`，以及所涉及的 `specs/<feature>.md`。
2. 在 `docs/tasks/<里程碑>.md` 认领一个未被占用的任务；只改那一行，记录负责人、范围和验收条件。
3. 先写清输入、输出、依赖、风险和验证命令。接口或数据模型变化先更新规格/架构/ADR，再写代码。
4. 若当前工作区已有未提交变更，只处理自己任务所需文件，不覆盖、回退或格式化其他成员的改动。

## 3. 多 Agent 分工与文件所有权

| 角色 | 主要拥有范围 | 交付物 |
| --- | --- | --- |
| 产品/协调 Agent | `docs/`、`specs/`、`docs/tasks/` | 需求、验收、任务拆分、决策记录 |
| 前端 Agent | `src/frontend/` | Vue 页面、G6 图谱交互、SSE 客户端、前端测试 |
| 后端 Agent | `src/backend/`、`src/contracts/` | FastAPI、领域服务、仓储、OpenAPI/DTO |
| 数据与 AI Agent | `src/backend/app/services/`、`workers/`、评测资产 | 解析、抽取、融合、检索、问答、路径算法 |
| 测试 Agent | `tests/`、测试段落与质量报告 | 用例、回归、指标、缺陷复现 |

- 共享边界（DTO、API、Neo4j 模型）由相关 Agent 在同一任务中同步协商，并先更新 `docs/architecture.md` 或规格。
- 不同时编辑同一个功能文件；必须共享时，将任务拆成顺序子任务，并在交接文件中写明基线与未完成项。
- 不提交密钥、真实课程资料、构建产物、数据库文件或本地 IDE 配置。

### 写争用规则

`docs/decisions.md`、`docs/tasks.md`、`scripts/verify.sh` 原本是每个 Agent 每个任务都要改的单文件。
本节上一条写着「不同时编辑同一个功能文件」，流程却强制所有人改同一张表——并行 worktree 必然冲突。
三处已拆成目录（S-03）。此后：

- **新增内容一律新建文件，不追加共享文件。** 一条 ADR 一个 `docs/decisions/ADR-<编号>-<slug>.md`；
  新的门禁写进 `scripts/verify/<领域>.sh`；新的必需文件加进 `scripts/verify/manifests/<领域>.txt`。
- **只有自己认领的那一行允许就地改。** 不要重排、对齐或格式化整张表——纯排版改动会让别人的
  worktree 产生无谓冲突，也曾让门禁因为一个多余空格而红掉。
- **索引文件每次只加一行**（`docs/decisions/README.md`、`docs/tasks.md`）；冲突时保留双方。
- 门禁断言不得锚定某一行的精确文本。要校验的是事实是否成立，而不是它写成什么格式。

## 4. 工程约束

- 前端保持页面、组合式逻辑、API 客户端、图谱适配器分层；不得把请求、图数据转换与组件渲染混写。
- 后端按 `api → schemas → services → repositories` 单向依赖；路由层不得包含业务规则或 Cypher 拼接。
- `PREREQUISITE` 必须是有向无环图；新增或修改此关系时先执行环检测。
- 每个生成的答案必须返回来源片段/文档/页码或章节；资料不足时返回可机读的“资料未覆盖”状态，而非臆测。
- 所有长时文档处理必须创建任务并可查询进度；进度事件格式先在 `src/contracts/` 定义。
- 配置只能从环境变量读取；在 `.env.example` 只保留变量名和无敏感示例值。

## 5. 完成标准

完成一个任务前必须：

1. 更新任务状态和验收证据到 `docs/tasks/<里程碑>.md` 对应的那一行。
2. 更新受影响的规格与架构；新决策新建 `docs/decisions/ADR-<编号>-<slug>.md`，并在 `docs/decisions/README.md` 加一行。
3. 运行 `./scripts/verify.sh`，以及该任务的最小相关测试。
4. 创建 `docs/handoffs/<agent>-<task>.md`，记录交付物、验证、接口/数据变更、风险、下一步。
5. 最终说明只报告已验证的结果、运行的命令与仍需人工决策的事项。

禁止使用破坏性 git 命令清理他人改动；禁止删除文件来规避失败测试。任何迁移、依赖升级或数据模型破坏性变更必须有回滚步骤。

## 6. 决策与沟通

- 已确认选择写成独立 ADR 文件放进 `docs/decisions/`；每条包含背景、决定、后果和日期，索引见该目录的 `README.md`。
- 未决问题写入 `docs/tasks/open-questions.md`，不要靠聊天上下文传递。
- 外部服务、MCP 与环境变量只记录在 `docs/integrations.md` 和 `.env.example`；密钥只存个人本地环境。
- 交接文件是任务的唯一异步上下文载体；详见 `docs/handoffs/README.md`。

### 分支与合并（提案，未生效，待确认 D-04）

1. 一个任务一个分支，从 `main` 切出，命名 `<agent>/<task-id>-<slug>`。
2. 提交信息首行 `<type>: <做了什么>`，正文写验证方式；破坏性变更必须写回滚步骤。
3. 合并前 `./scripts/verify.sh` 必须通过，并在描述里指向本次的交接文件。
4. 不直接向 `main` 推送，不用破坏性 git 命令覆盖他人分支或 stash。
5. 仓库当前没有 git remote：`main` 是否设保护、谁有合并权，需人工确认后本节才生效。
