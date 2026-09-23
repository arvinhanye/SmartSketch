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

## CI 配置

| ID | 状态 | 任务 | 负责人 | 范围与验收 | 证据 |
| --- | --- | --- | --- | --- | --- |
| CI-01 | DONE（待 GitHub 首次运行确认） | 为当前仓库建立 GitHub Actions 基础质量门禁 | Codex | push、pull request 和手动触发；只运行仓库现有 `scripts/verify.sh`，不把尚未建立的前后端测试标成通过；工作流语法和本地校验通过 | `.github/workflows/ci.yml`；`./scripts/verify.sh` PASS；YAML 解析/关键字段检查 PASS；`git diff --check` PASS；`docs/handoffs/codex-ci-01.md` |

### CI-01 执行约定

- 输入：当前主分支骨架、`scripts/verify.sh`、仓库现有任务与架构约定。
- 输出：`.github/workflows/ci.yml`、CI 范围说明、交接记录。
- 依赖：GitHub Actions 托管运行器；无项目密钥、数据库或付费模型服务。
- 风险：当前门禁只检查骨架，不能代表尚未实现的前后端测试；后续由 K11 接入实际质量门禁。
- 验证：`./scripts/verify.sh`、工作流 YAML 解析与关键字段检查、`git diff --check`。

## 协作安全修复

| ID | 状态 | 任务 | 负责人 | 范围与验收 | 证据 |
| --- | --- | --- | --- | --- | --- |
| HOOK-01 | DONE | 修复 `block-dangerous.sh` 在命令含双引号时漏检，以及解析失败时放行 | Claude | `.claude/hooks/block-dangerous.sh`、新增 `tests/hooks/test_block_dangerous.sh`、`scripts/verify.sh` 加一行接入回归测试（用户同意）；拦截规则不变，只修命令提取；引号之后的危险命令必须被拦截，无法解析的输入必须拒绝，正常命令不误拦 | 回归测试修复前 10 FAIL / exit 1，修复后 14 PASS / exit 0（含系统 Python 3.9 + `LC_ALL=C`）；会话内实时探针被拦；`./scripts/verify.sh` exit 0 且已包含该测试，换回旧钩子则 verify exit 1；`docs/handoffs/claude-hook-01.md` |

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
| PLAN-D01 | 两个 Claude 分支 YAML-first/Pydantic-first 唯一源、API 前缀和冲突 ADR 编号如何统一（A01/A02）。**已关闭**：唯一源与 ADR 编号由 ADR-004 签收；API 前缀由 ADR-009（A02）定为 `/api/v1`（均为 ArvinHan，2026-09-22） | 技术负责人 | 已完成 |
| PLAN-D02 | 发布快照/图与向量版本化/双存储补偿方案（A04） | 技术负责人 | 发布与学生检索仓储实现前 |
| PLAN-D03 | worker 队列/租约/取消/重试及部分失败语义（A03/A06）。**部分关闭**：取消与部分失败语义由 ADR-010（A03）签收（ArvinHan，2026-09-23）；**队列 / 租约 / 重试仍待 A06** | 技术负责人 | worker 实现前 |
| PLAN-D04 | 哪个 worktree 作为集成基线、分批合并顺序与合并权（A10） | 项目负责人 | 合并前；本轮未代为合并 |
| PLAN-D05 | 学习材料生成分支决定是否同步 main；目标路径是否纳入（O01） | 产品负责人 | 主线验收后、加分项前 |

## Claude 审查批次

| ID | 状态 | 范围 | 负责人 | 验收与证据 |
| --- | --- | --- | --- | --- |
| REVIEW-02 | DONE（分批；S-07 尚有待审范围） | A01 文档交付 `88ea517`/`6c19f25`；S-07 本地脚本 `8865686` | Codex | `docs/reviews/codex-claude-a01-s07-tooling-2026-09-23-0136z.md`；A01 路径映射 22/29 一致；S07-R12～R14 已复现；`docs/handoffs/codex-review-02.md` |

## 原子任务认领（`docs/atomic-task-plan.md`）

> 本节只记录本 worktree 认领的叶子任务。main 的 `docs/tasks.md` 另有 PLAN-01 与 PLAN-D01～D05 行（已提交为 `9ddcef8`）；合并时保留双方，main 的 PLAN-D 行在前、本节在后。

| 原子 ID | 状态 | 任务 | 负责人 | 目标 worktree / base HEAD | 文件锁（本轮唯一写入者） | 证据 |
| --- | --- | --- | --- | --- | --- | --- |
| A01 | DONE（ADR-004 已签收） | 裁决契约唯一来源与 ADR 编号 | Claude（协调 Agent） | `.claude/worktrees/adoring-sinoussi-709263` / base `05d214c` | `docs/decisions.md`、`docs/architecture.md`、本节、`docs/handoffs/claude-a01.md` | `docs/decisions.md` ADR-004；`docs/handoffs/claude-a01.md`；`./scripts/verify.sh` exit 0、`git diff --check` exit 0 |

- A01 的交付物（ADR-004 裁定 + 迁移映射）已于 2026-09-22 由 ArvinHan 签收，成为生效决定。PLAN-D01 的「唯一源」「ADR 编号」两项随之关闭；「API 前缀」按 ADR-004 交给 A02，已由 ADR-009 关闭（见下方 A02 行）。
- A01 未触发任何分支合并；集成基线与合并顺序仍是 PLAN-D04 / 原子任务 A10 的范围。

| 原子 ID | 状态 | 任务 | 负责人 | 目标 worktree / base HEAD | 文件锁（本轮唯一写入者） | 证据 |
| --- | --- | --- | --- | --- | --- | --- |
| M0-09 第一步 | DONE | 安装契约生成工具链并实测生成链（B14 前置） | Claude | 同上 / base `05d214c` | `docs/handoffs/claude-m0-09-toolchain.md`、`docs/decisions.md` 的 ADR-004 实测补注 | 完整生成 exit 0、两次字节一致、`--check` exit 0、四处篡改均非 0、Pydantic import 54 个模型 |

- 工具安装经用户授权：`datamodel-code-generator==0.26.3` 在 venv `~/.local/share/smartsketch/contracts-venv`，`openapi-typescript@7.4.4` 全局。实测在 scratch 副本进行，未修改 `740adb` 的 worktree。
- 实测发现的两个脚本缺陷（Pydantic 产物落成无扩展名文件；`--check` 缺产物时退出 2 并吞掉提示）**已修**：经用户授权直接提交在 `claude/worktree-contract-conflicts-740adb` 的 `8865686`，只改 `scripts/gen-contracts.sh` 一个文件。修复前后对照与 13 项回归矩阵见交接文件。**更正**：该修复在 UTF-8 locale 下引入了新的假绿（Codex S07-R06），已在 `978671e` 修复并加回归测试（13 项矩阵只在 C locale 下跑过）。
- 仍未做：生成物入库（需先定 PLAN-D04 集成基线）；`--check` 顶层陈旧阶段检不出（留给 B14）。`740adb` 的 `verify.sh` 现为 exit 1，原因是产物未入库，不是脚本缺陷（`978671e` 后 C 与 UTF-8 locale 均实测）。

| 原子 ID | 状态 | 任务 | 负责人 | 目标 worktree / base HEAD | 文件锁（本轮唯一写入者） | 证据 |
| --- | --- | --- | --- | --- | --- | --- |
| S07-R06 修复 | DONE | 修复 `8865686` 在 UTF-8 locale 下引入的 `--check` 假绿（Codex 审查 P1） | Claude | `worktree-contract-conflicts-740adb` / base `8865686` | `scripts/gen-contracts.sh`、`tests/contracts/test_contracts.py` | `978671e`；回归测试先红后绿；C / en_US.UTF-8 / zh_CN.UTF-8 缺产物均 exit 1；契约测试 21/21；交接见 `docs/handoffs/claude-m0-09-toolchain.md` 第三节更正 |

| 原子 ID | 状态 | 任务 | 负责人 | 目标 worktree / base HEAD | 文件锁（本轮唯一写入者） | 证据 |
| --- | --- | --- | --- | --- | --- | --- |
| A02 | DONE（ADR-009 已签收） | 统一路径前缀和领域枚举 | Claude（协调 Agent） | `.claude/worktrees/adoring-sinoussi-709263`（分支 `claude/a02-start-4064b7`）/ base `bfa236c` | `specs/course-knowledge-graph.md`、`docs/architecture.md`；**范围扩展**：`docs/decisions.md`（新增 ADR-009 + ADR-004 指针一行，AGENTS.md §6 要求已确认选择入 ADR）、本节、`docs/handoffs/claude-a02.md` | `docs/architecture.md`「API 前缀与 wire 枚举」；`specs/course-knowledge-graph.md`「前置关系成环处理」DAG-1～11；`docs/decisions.md` ADR-009；枚举表对 `740adb` `978671e` YAML 逐值核对 ALL PASS，`ff30e0` 与篡改副本均被检出（exit 1）；`./scripts/verify.sh` exit 0、`git diff --check` exit 0；`docs/handoffs/claude-a02.md` |

- A02 的决定（ArvinHan，2026-09-22 签收）：前缀 `/api/v1`（`/health` 例外）；只有 `ErrorCode`、`RelationType` 用 UPPER_SNAKE，其余 wire 枚举一律 lower_snake，`NOT_COVERED` 是概念名、wire 为 `status: "not_covered"`；自动候选成环降级为 `RELATED_TO` + 送审、不使任务失败，人工编辑成环 409 拒绝。
- A02 交出的后续项（均未认领）：**B11** 须先在 `api.v1.yaml` 给 `Relation` 增加「降级原类型与环路」字段，F13 依赖它；`740adb` `src/contracts/README.md` 的 `not_covered_reason` 应为 `reason`；ADR-005 导入时加注指向 ADR-009；Neo4j 文本块标签 `SourceChunk`（main）与 `Chunk`（ADR-008）不一致，交 A10。状态转换与取消语义仍归 **A03**（现可认领，依赖 A02 已满足）。

| 原子 ID | 状态 | 任务 | 负责人 | 目标 worktree / base HEAD | 文件锁（本轮唯一写入者） | 证据 |
| --- | --- | --- | --- | --- | --- | --- |
| A03 | DONE（ADR-010 已签收） | 定义任务生命周期和取消协议 | Claude（协调 Agent） | `.claude/worktrees/a03-d430b9`（分支 `claude/a03-task-lifecycle`）/ base `931361d` | `specs/task-processing.md`（新建）；**范围扩展（用户同意）**：`docs/decisions.md`（新增 ADR-010 + ADR-004 编号表下指针一行）、`specs/course-knowledge-graph.md` 验收 2、`docs/architecture.md`（三处「归 A03 / A03 复核」占位 + SSE 终止事件一行）、PLAN-D03 行、本节、`docs/handoffs/claude-a03.md` | `specs/task-processing.md`（T1～T9、取消矩阵、部分失败、失败码、SSE 关流与重连、TASK-1～19）；`docs/decisions.md` ADR-010；核对脚本 62 项 ALL PASS（含对 `740adb` `978671e` 真源的缺口核实），7 个篡改副本均被逐条检出（exit 1、无崩溃）；`./scripts/verify.sh` exit 0、`git diff --check` exit 0；`docs/handoffs/claude-a03.md` |

- A03 的决定（ArvinHan，2026-09-23 签收）：`awaiting_review` = 处理完成（不可取消、不会失败、推送后关流），`completed` = 发布时推进快照内的任务；`persisting` 不可取消，`merging → persisting` 是最后取消点；抽取部分失败按 `TASK_MAX_FAILED_CHUNK_RATIO`（默认 0.2）判定；重连由前端封装管理，不依赖 `EventSource` 自动重连。
- A03 交出的后续项（均未认领）：**B10** 补 `Task.cancel_requested`、`TaskCounts.chunks_failed`、`Task.failed_chunks`、`failed ⇔ error` 约束与取消端点描述，并把 `events.v1.md` §2/§4 改为指向本规格；**B08** 加 4 个提议错误码；**A06** 补写 `specs/task-processing.md` §8；**A07** 登记阈值变量；**A04/A06** 定 `persisting` 与发布快照的串行化机制；C06/C07 定再处理入口与 `Document.parse_status` 跟随哪个任务。
