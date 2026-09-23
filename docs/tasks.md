# 任务看板

> 状态：`TODO` → `IN PROGRESS` → `BLOCKED` / `DONE`。认领或完成任务时更新本表；每个 DONE 项必须指向验收证据和交接文件。

## 当前里程碑：M0 协作与应用骨架

| ID | 状态 | 任务 | 负责人 | 验收条件 | 证据 |
| --- | --- | --- | --- | --- | --- |
| M0-01 | DONE | 建立多 Agent 协作、文档、规格、源码目录骨架 | Codex | 必需文件齐全；基础校验通过 | `scripts/verify.sh`；`docs/handoffs/codex-m0-project-scaffold.md` |
| M0-02 | TODO | 初始化 Vue 3 + TypeScript + Vite 前端 | Frontend Agent | 可启动；具备最小路由、类型检查与测试命令 | 待补充 |
| M0-03 | TODO | 初始化 FastAPI 后端与健康检查 | Backend Agent | 可启动；`GET /health` 有契约和测试 | 待补充 |
| M0-04 | TODO | 定义第一版 API、SSE 任务事件与图谱 DTO | Backend + Frontend Agent | `src/contracts/` 有版本化契约；双方确认 | 待补充 |
| M0-05 | TODO | 定义 Neo4j/SQLite 开发环境与本地启动方式 | Data/Backend Agent | 无密钥可启动依赖；环境变量文档完整 | 待补充 |

## 下一里程碑：M1 课程资料到草稿图谱

| ID | 状态 | 任务 | 负责人 | 验收条件 |
| --- | --- | --- | --- | --- |
| M1-01 | TODO | 课程与资料上传 API | Backend Agent | 资料记录、格式校验、任务创建、错误响应均有测试 |
| M1-02 | TODO | 文档解析与分块 | Data/AI Agent | 支持四种格式；分块保留定位来源 |
| M1-03 | TODO | 节点关系抽取与融合 | Data/AI Agent | 四类关系；低置信度项可审核；课程隔离 |
| M1-04 | TODO | 前置关系 DAG 校验 | Backend Agent | 环路拒绝、错误可解释、自动化测试 |
| M1-05 | TODO | 教师审核与发布版本 | Full-stack Agent | 可编辑、发布、读取已发布版本 |

## 架构审查与可执行拆分

| ID | 状态 | 任务 | 负责人 | 范围与验收 | 证据 |
| --- | --- | --- | --- | --- | --- |
| PLAN-01 | DONE | 核对架构现状、汇总技术方案、拆分单轮任务、建立 Claude 完成后审查约定 | Codex | 协调文档交付；127 个未认领叶子任务；5 项初始审查问题；本项目会话可读；heartbeat 已创建 | `docs/handoffs/codex-plan-01.md`；`docs/reviews/validate_atomic_plan.py`；`./scripts/verify.sh` 与 `git diff --check` |

### PLAN-01 执行约定

- 输入：当前 checkout、项目规格/ADR、关联 worktree 的只读状态、当前项目 Claude 会话元数据。
- 输出：架构审查、原子任务清单、Claude → Codex 审查流程及交接。
- 依赖：现有协作骨架；无需模型密钥或数据库服务。
- 风险：Claude 可能在其他 worktree 工作；文档方案不等于已实现；会话包含私有内容，仅提取项目和完成状态所需字段。
- 验证：`./scripts/verify.sh`、`git diff --check`、任务 ID/依赖/文档链接结构检查。

### 原子任务派发入口

- [技术全景与现状](architecture-review-2026-09-22.md)；[127 项原子计划](atomic-task-plan.md)；机器可读 `docs/atomic-tasks.json`。
- 119 项主线、8 项条件性加分项均为 PROPOSED，尚未认领；本轮 DONE 仅指规划和审查交付，不指其中实现任务完成。
- 认领时按原子 ID 新增状态行，写目标 worktree/HEAD 和文件所有权；M0/M1 原行保留为父任务，不把未合并 worktree 的完成状态自动搬到 main。
- Claude 完成后的自动审查已启用，规则见 [审查流程](claude-review-workflow.md)，首轮问题见 [审查报告](reviews/codex-claude-initial-2026-09-22.md)。

## 待确认决策

| ID | 问题 | 决策人 | 需要在何时确认 |
| --- | --- | --- | --- |
| D-01 | MVP 首批课程示例和脱敏资料来源 | 产品负责人 | M1 开始前 |
| D-02 | 首个 OpenAI 兼容模型供应商与预算上限 | 技术负责人 | 接入抽取服务前 |
| D-03 | 登录是否先采用本地演示角色 | 产品负责人 | M0-03 前 |
| PLAN-D01 | 两个 Claude 分支 YAML-first/Pydantic-first 唯一源、API 前缀和冲突 ADR 编号如何统一（A01/A02）。**部分关闭**：唯一源与 ADR 编号已由 ADR-004 签收（ArvinHan，2026-09-22）；**API 前缀仍待 A02** | 技术负责人 | 契约消费者开工前；最高优先 |
| PLAN-D02 | 发布快照/图与向量版本化/双存储补偿方案（A04） | 技术负责人 | 发布与学生检索仓储实现前 |
| PLAN-D03 | worker 队列/租约/取消/重试及部分失败语义（A03/A06） | 技术负责人 | worker 实现前 |
| PLAN-D04 | 哪个 worktree 作为集成基线、分批合并顺序与合并权（A10） | 项目负责人 | 合并前；本轮未代为合并 |
| PLAN-D05 | 学习材料生成分支决定是否同步 main；目标路径是否纳入（O01） | 产品负责人 | 主线验收后、加分项前 |

## 原子任务认领（`docs/atomic-task-plan.md`）

> 本节只记录本 worktree 认领的叶子任务。main 的 `docs/tasks.md` 另有 PLAN-01 与 PLAN-D01～D05 行（已提交为 `9ddcef8`）；合并时保留双方，main 的 PLAN-D 行在前、本节在后。

| 原子 ID | 状态 | 任务 | 负责人 | 目标 worktree / base HEAD | 文件锁（本轮唯一写入者） | 证据 |
| --- | --- | --- | --- | --- | --- | --- |
| A01 | DONE（ADR-004 已签收） | 裁决契约唯一来源与 ADR 编号 | Claude（协调 Agent） | `.claude/worktrees/adoring-sinoussi-709263` / base `05d214c` | `docs/decisions.md`、`docs/architecture.md`、本节、`docs/handoffs/claude-a01.md` | `docs/decisions.md` ADR-004；`docs/handoffs/claude-a01.md`；`./scripts/verify.sh` exit 0、`git diff --check` exit 0 |

- A01 的交付物（ADR-004 裁定 + 迁移映射）已于 2026-09-22 由 ArvinHan 签收，成为生效决定。PLAN-D01 的「唯一源」「ADR 编号」两项随之关闭；「API 前缀」按 ADR-004 交给 A02，仍开着。
- A01 未触发任何分支合并；集成基线与合并顺序仍是 PLAN-D04 / 原子任务 A10 的范围。

| 原子 ID | 状态 | 任务 | 负责人 | 目标 worktree / base HEAD | 文件锁（本轮唯一写入者） | 证据 |
| --- | --- | --- | --- | --- | --- | --- |
| M0-09 第一步 | DONE | 安装契约生成工具链并实测生成链（B14 前置） | Claude | 同上 / base `05d214c` | `docs/handoffs/claude-m0-09-toolchain.md`、`docs/decisions.md` 的 ADR-004 实测补注 | 完整生成 exit 0、两次字节一致、`--check` exit 0、四处篡改均非 0、Pydantic import 54 个模型 |

- 工具安装经用户授权：`datamodel-code-generator==0.26.3` 在 venv `~/.local/share/smartsketch/contracts-venv`，`openapi-typescript@7.4.4` 全局。实测在 scratch 副本进行，未修改 `740adb` 的 worktree。
- 实测发现的两个脚本缺陷（Pydantic 产物落成无扩展名文件；`--check` 缺产物时退出 2 并吞掉提示）**已修**：经用户授权直接提交在 `claude/worktree-contract-conflicts-740adb` 的 `8865686`，只改 `scripts/gen-contracts.sh` 一个文件。修复前后对照与 13 项回归矩阵见交接文件。
- 仍未做：生成物入库（需先定 PLAN-D04 集成基线）；`--check` 顶层陈旧阶段检不出（留给 B14）。`740adb` 的 `verify.sh` 现为 exit 1，原因是产物未入库，不是脚本缺陷。
