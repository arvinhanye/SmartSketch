# 任务看板

> 状态：`TODO` → `IN PROGRESS` → `BLOCKED` / `DONE`。认领或完成任务时更新本表；每个 DONE 项必须指向验收证据和交接文件。

## 当前里程碑：M0 协作与应用骨架

| ID | 状态 | 任务 | 负责人 | 验收条件 | 证据 |
| --- | --- | --- | --- | --- | --- |
| M0-01 | DONE | 建立多 Agent 协作、文档、规格、源码目录骨架 | Codex | 必需文件齐全；基础校验通过 | `scripts/verify.sh`；`docs/handoffs/codex-m0-project-scaffold.md` |
| M0-02 | TODO | 初始化 Vue 3 + TypeScript + Vite 前端 | Frontend Agent | 可启动；具备最小路由、类型检查与测试命令 | 待补充 |
| M0-03 | DONE（B05+B06） | 初始化 FastAPI 后端与健康检查 | Backend Agent | 可启动；`GET /health` 有契约和测试 | B05/B06 测试 38 PASS；基础 verify PASS；`docs/handoffs/codex-b05.md`、`docs/handoffs/codex-b06.md` |
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
| D-02 | 首个 OpenAI 兼容模型供应商与预算上限。A07 已拆为 D-02a～f 六项，签收入口见 `docs/integrations.md`「待签收取值（D-02）」；配置形状与规则已定，取值均未签收 | 技术负责人 | 接入抽取服务前（fake 实现可先行） |
| D-03 | 登录是否先采用本地演示角色。**已关闭**：ADR-013（A05）定为本地账号 + 预置演示账号，不采用纯演示角色；账号类型与课程内角色分离；教师按用户名添加学生（ArvinHan，2026-09-23 签收） | 产品负责人 | 已完成 |
| PLAN-D01 | 两个 Claude 分支 YAML-first/Pydantic-first 唯一源、API 前缀和冲突 ADR 编号如何统一（A01/A02）。**已关闭**：唯一源与 ADR 编号由 ADR-004 签收；API 前缀由 ADR-009（A02）定为 `/api/v1`（均为 ArvinHan，2026-09-22） | 技术负责人 | 已完成 |
| PLAN-D02 | 发布快照/图与向量版本化/双存储补偿方案（A04）。**已关闭**：由 ADR-012（A04）裁定（ArvinHan，2026-09-23 签收） | 技术负责人 | 已完成 |
| PLAN-D03 | worker 队列/租约/取消/重试及部分失败语义（A03/A06）。**已关闭**：取消与部分失败语义由 ADR-010（A03），队列 / 租约 / 重试 / 幂等由 ADR-011（A06）签收（均为 ArvinHan，2026-09-23） | 技术负责人 | 已完成 |
| PLAN-D04 | 哪个 worktree 作为集成基线、分批合并顺序与合并权（A10） | 项目负责人 | 合并前；本轮未代为合并 |
| PLAN-D05 | 学习材料生成分支决定是否同步 main；目标路径是否纳入（O01） | 产品负责人 | 主线验收后、加分项前 |

## Claude 审查批次

| ID | 状态 | 范围 | 负责人 | 验收与证据 |
| --- | --- | --- | --- | --- |
| REVIEW-02 | DONE（分批；S-07 尚有待审范围） | A01 文档交付 `88ea517`/`6c19f25`；S-07 本地脚本 `8865686` | Codex | `docs/reviews/codex-claude-a01-s07-tooling-2026-09-23-0136z.md`；A01 路径映射 22/29 一致；S07-R12～R14 已复现；`docs/handoffs/codex-review-02.md` |
| REVIEW-A08 | DONE（不建议签收；R02/R03 已签收为 ADR-014；待 Codex 修 R01～R04） | Codex A08 未提交快照（`codex-a08-learning-path` @ `1a47eb2` + dirty，指纹见报告） | Claude | `docs/reviews/claude-codex-a08-2026-09-23.md`：P2×4（R01 `no_graph` 与 A04 V3 冲突、R02 中心度恒 ≤0.5、R03 合并进度倒退未列签收、R04 外课/历史 ID 判定不可实现）、P3×6；R02/R03 的产品决定见 `docs/decisions.md` ADR-014；`docs/handoffs/claude-review-a08.md` |
| REVIEW-A08-R2 | DONE（R01～R10 已修；R11～R14 由 Codex 修复后第 3 轮复审通过，无新 P1/P2；剩 §7 与 ADR-014 细则待产品签收，R15 待细则 1 签收前写死） | Codex A08 修订稿（`codex-a08-learning-path` @ `1a47eb2` + dirty，规格 `efe23f9e…`，指纹见报告） | Claude | `docs/reviews/claude-codex-a08-r2-2026-09-23.md`：R01～R10 复核通过（R01 在 `atomic-tasks.json` B12 与 I05 仍有“无图”残留）；P2×1（R11 合并继承后进度接口返回原始还是有效状态未定义）、P3×4（R12 谱系终止与不变式、R13 舍入后分量不可还原、R14 任务清单 Markdown/JSON 不一致、R15 细则 1 提案有歧义）；`docs/handoffs/claude-review-a08-r2.md` |

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

- A03 的决定（ArvinHan，2026-09-23 签收）：`awaiting_review` = 处理完成（不可取消、不会失败、推送后关流），`completed` = 发布时推进 T6 提交序号 ≤ 快照任务水位的任务（含内容被全部驳回者；措辞经 A03-R02 修订）；`persisting` 不可取消，`merging → persisting` 是最后取消点；抽取部分失败按 `TASK_MAX_FAILED_CHUNK_RATIO`（默认 0.2）判定；重连由前端封装管理，不依赖 `EventSource` 自动重连。
- A03 交出的后续项（均未认领）：**B10** 补 `Task.cancel_requested`、`TaskCounts.chunks_failed`、`Task.failed_chunks`、`failed ⇔ error` 约束与取消端点描述，并把 `events.v1.md` §2/§4 改为指向本规格；**B08** 加 4 个提议错误码；**A06** 补写 `specs/task-processing.md` §8；**A07** 登记阈值变量；**A04/A06** 定 `persisting` 与发布快照的串行化机制；C06/C07 定再处理入口与 `Document.parse_status` 跟随哪个任务。

| 原子 ID | 状态 | 任务 | 负责人 | 目标 worktree / base HEAD | 文件锁（本轮唯一写入者） | 证据 |
| --- | --- | --- | --- | --- | --- | --- |
| A03-R01/R02 修复 | DONE | 修复 Codex 审查 A03-R01（SSE 在 `awaiting_review` 关流后「全部可通过 SSE 观察 / 终态事件恰好一次」措辞失真）与 A03-R02（T7 发布推进谓词与「全部驳回仍 `completed`」自相矛盾） | Claude | `.claude/worktrees/a03-d430b9`（分支 `claude/a03-task-lifecycle`）/ base `2049129` | `specs/task-processing.md`、`specs/course-knowledge-graph.md` 验收 2、`docs/architecture.md` SSE 事件表一行与「文档用语 → wire 值」映射一行、`docs/decisions.md` ADR-010、本节、`docs/handoffs/claude-a03.md` | 审查报告 `docs/reviews/codex-claude-a03-ci01-s07-2026-09-23-0606z.md`（主目录）；核对脚本新增 12 项先红后绿，共 74 项 ALL PASS；新增 5 个负例（N8～N12），连同原 7 个共 12 个均被逐条检出；A02 枚举核对回归 ALL PASS；`./scripts/verify.sh` exit 0、`git diff --check` exit 0；`docs/handoffs/claude-a03.md` 第九节 |

- A03-R01/R02 的修复不改变 ADR-010 的决定方向，只澄清措辞：任务 SSE 只覆盖处理阶段，每个连接恰好以一条结束事件收尾，`completed` 通过任务查询或课程发布状态观察；T7 推进谓词统一为「T6 提交序号 ≤ 快照任务水位」。新增 TASK-20～22。

| 原子 ID | 状态 | 任务 | 负责人 | 目标 worktree / base HEAD | 文件锁（本轮唯一写入者） | 证据 |
| --- | --- | --- | --- | --- | --- | --- |
| A06 | DONE（ADR-011 已签收） | 定义 worker 租约和幂等机制 | Claude（协调 Agent） | `.claude/worktrees/a03-d430b9`（分支 `claude/a06-worker-lease`，叠在 `claude/a03-task-lifecycle` 之上）/ base `6345ce1` | `specs/task-processing.md`（§8 及 §1～§7 中指向 A06 的指针、§6「由 A06 定」一行）、`docs/decisions.md`（新增 ADR-011）；**范围扩展（用户同意）**：`docs/architecture.md`（目录表 workers 行、核心数据模型 SQLite 列表）、PLAN-D03 行、本节、`docs/handoffs/claude-a06.md` | `specs/task-processing.md` §8（部署边界、领取/租约/回收、三层重试与耗尽码、各阶段幂等、课程写锁、中间产物、迁移备份与回滚、配置、LEASE-1～17）；`docs/decisions.md` ADR-011；A06 核对脚本 45 项 ALL PASS，9 个篡改副本均被逐条检出；A03 核对（74 项）与 12 个负例、A02 枚举核对回归均通过；`./scripts/verify.sh` exit 0、`git diff --check` exit 0；`docs/handoffs/claude-a06.md` |

- A06 的决定（ArvinHan，2026-09-23 签收）：worker 为与 API 同机的独立进程，共用 SQLite（WAL）作队列，不支持跨机器；单条条件更新领取、60 秒租约心跳续约、令牌防旧写；三层重试（模型调用 / 块 2 次 / 任务 3 次），存储不可用与模型熔断为阶段级临时故障，退避后重排；`extracting` 块级检查点续跑，`persisting` 在课程写锁下单事务 `MERGE`；迁移须停机、`VACUUM INTO` 备份并校验，回滚靠备份恢复。PLAN-D03 至此全部关闭。
- A06 交出的后续项（均未认领）：**B08** 增加 `TASK_ATTEMPTS_EXHAUSTED`；**A07** 登记 §8.8 五个变量；**E 组** 定模型调用缓存键与失效（`merging` 重跑依赖）；**E04** 暴露熔断状态；**A04** 定发布侧何时持课程写锁；C01/C09/E12/F13/K08 按 §8 实现。

| 原子 ID | 状态 | 任务 | 负责人 | 目标 worktree / base HEAD | 文件锁（本轮唯一写入者） | 证据 |
| --- | --- | --- | --- | --- | --- | --- |
| A04 | DONE（ADR-012 已签收） | 定义图谱版本和跨库发布协议 | Claude（协调 Agent） | `.claude/worktrees/a04-f5f479`（分支 `claude/a04-f5f479`）/ base `931361d` | `specs/teacher-review-publish.md`（main 新建，以 `740adb` 草稿桩为底稿）、`docs/architecture.md`；**范围扩展**：`docs/decisions.md`（新增 ADR-012；ADR-010/011 已被 A03/A06 的 PR #5/#6 占用。AGENTS.md §6 要求已确认选择入 ADR）、本节、`docs/handoffs/claude-a04.md` | `specs/teacher-review-publish.md`「图谱版本与跨库发布协议」V1～V11（PUB-1～27：成功 4 / 边界 13 / 失败 10）；`docs/architecture.md`「图谱版本与跨库发布」；`docs/decisions.md` ADR-012（已签收）；对 `740adb` `978671e` YAML、A03 `6345ce1`、A06 `ab04053` 与全部远端分支 ADR 的核对脚本 ALL PASS，三个篡改副本均 exit 1；`./scripts/verify.sh` exit 0、`git diff --cached --check` exit 0；`docs/handoffs/claude-a04.md` |

- A04 的决定（ArvinHan，2026-09-23 签收，ADR-012）：SQLite 规范化快照为真相 + Neo4j 按 `version_id` 物化副本；回滚前滚为新版本号，回滚到当前版本幂等；发布集合摘要等于当前发布版则幂等；回滚不动草稿；排除 `low_confidence`，疑似重复与孤立节点只提示；课程写锁扩大到所有草稿写入（修订 ADR-011 决定 6）。
- A04 交出的后续项（均未认领）：**B08** 新增 `PUBLISH_IN_PROGRESS`、`COURSE_BUSY`；**B11** `PublishResult`/`GraphVersion` 加字段、回滚端点补 409、`details.reasons` 结构；**A07** 登记 `PUBLISH_LEASE_SECONDS`、`COURSE_LOCK_WAIT_SECONDS`；**A10** 导入 A06 规格时在 §8.5 加注指向 ADR-012，并统一文本块标签名；G02 状态名改为 `preparing/materialized/committed/failed`。

| 原子 ID | 状态 | 任务 | 负责人 | 目标 worktree / base HEAD | 文件锁（本轮唯一写入者） | 证据 |
| --- | --- | --- | --- | --- | --- | --- |
| A07 | DONE（形状已定；取值待 D-02a～f 签收） | 落实模型配置形状与预算决策入口 | Claude（协调 Agent） | `.claude/worktrees/a07-297f68`（分支 `claude/a07-model-config`，叠在 `claude/a06-worker-lease` 之上）/ base `ab04053` | `docs/integrations.md`、`.env.example`；**范围扩展**：D-02 行（指向签收入口）、本节、`docs/handoffs/claude-a07.md` | `docs/integrations.md`「运行时环境变量」（38 个变量，类型/约束/样例/状态）与「模型接入规则（A07）」（切换矩阵、预算、模型版本与向量空间、启动校验、待签收取值 D-02a～f）；`.env.example` 与之逐项一致；核对脚本 344 项 ALL PASS（含对 §8.8、ADR-010 阈值与 `740adb` 命名的逐项核对），11 个篡改副本均被检出（exit 1）；`./scripts/verify.sh` exit 0、`git diff --check` exit 0；`docs/handoffs/claude-a07.md` |

- A07 的形状（ArvinHan，2026-09-23 在会话中确认三节设计）：平铺环境变量、沿用 `740adb` 命名；显式 `LLM_MODE` / `EMBEDDING_MODE`，生产禁 fake；每次调用先试主用、熔断器负责粘住备用；鉴权失败不切备用；流式出字后不切换；向量永不跨模型切换；预算按 token 计的软上限（任务 + 每日），`0` 不发请求、无「不限」写法，向量调用不计入；被拒调用走所在环节既有失败路径。**取值未签收**：D-02a～f 见 `docs/integrations.md`，签收后写 ADR。
- A07 交出的后续项（均未认领）：**B08** 加 `BUDGET_EXCEEDED`（D-02f）；**B06** 按「启动校验」实现设置加载；**E03/E04** 实现切换矩阵、熔断与预算，退避参数须有上限；**E07** 发送 `dimensions`、比对返回长度、按 `EMBEDDING_BATCH_SIZE` 分批；**D09/E 组** 缓存键用实际给出结果的模型 ID；**A10** 导入 `740adb` 时 `.env.example` 与 `docs/integrations.md` 会文本冲突，模型与任务段取本分支、存储与 Neo4j 容器段取 `740adb`。

| 原子 ID | 状态 | 任务 | 负责人 | 目标 worktree / base HEAD | 文件锁（本轮唯一写入者） | 证据 |
| --- | --- | --- | --- | --- | --- | --- |
| A05 | DONE（ADR-013 已签收） | 定义课程成员与本地身份边界 | Claude（协调 Agent） | `.claude/worktrees/a05-aa1561`（分支 `claude/a05-identity-access`）/ base `931361d` | `specs/identity-access.md`（新建）、`docs/decisions.md`（新增 ADR-013）；**范围扩展**：本节与 D-03 行、`docs/handoffs/claude-a05.md` | `specs/identity-access.md` 访问矩阵 33 行 + IAM-1～25；`docs/decisions.md` ADR-013；对 `740adb` `978671e` 契约逐项核对 150 PASS，6 个篡改负例均 exit 1；`./scripts/verify.sh` exit 0、`git diff --check` exit 0；`docs/handoffs/claude-a05.md` |

- A05 的决定（ArvinHan，2026-09-23 签收）：本地账号登录，演示账号由种子脚本创建、口令只来自环境变量，无注册端点；调用者身份只来自已验证的令牌，不读请求中的 `user_id`；`users.role` 只决定首页和能否建课，课程内授权只看 `course_members.role` 并每次回查；教师按用户名添加学生；进度、推荐、问答仅学生成员可用，教师不开放；SSE 改用一次性票据（Codex S07-R07、A03 移交项）。
- A05 交出的后续项（均未认领）：**B08 / B09 / B10** 按 `specs/identity-access.md` §7 改契约（`my_role`、成员三操作、票据端点与安全方案、补 `401`）；**原子清单缺口**：登录端点与令牌签发、账号命令行与演示种子、成员管理 API、成员管理页面、票据申领端点，清单均无承接任务，需协调 Agent 拆分编号；`event_tickets` 表补登命名基线交 **A10**（`docs/architecture.md` 现由 A04 持锁）；`AUTH_JWT_SECRET` 等三个变量写入 `.env.example` 交 **A07 或 C03**。
- ADR 编号：ADR-010、011、012 分别由 A03、A06、A04 使用（PR #5、#6、#7；A04 原与 A03 同撞 010，已改用预留的 012），A05 取 013。

| 原子 ID | 状态 | 任务 | 负责人 | 目标 worktree / base HEAD | 文件锁（本轮唯一写入者） | 证据 |
| --- | --- | --- | --- | --- | --- | --- |
| A04-R01/R02 修复 | DONE（ADR-012 修订 1 已签收） | 修复 Codex 审查 A04-R01（历史版本只按 `material_id` 过滤会检索到后来的文本块）与 A04-R02（换向量模型后幂等发布与回滚规则冲突） | Claude（协调 Agent） | `.claude/worktrees/a04-f5f479`（分支 `claude/a04-r01-r02-fix`）/ base `0630664` | `specs/teacher-review-publish.md`、`docs/decisions.md`（ADR-012 修订 1）、`docs/architecture.md`、`docs/tasks.md`、`docs/handoffs/claude-a04.md`；**范围扩展**：`specs/task-processing.md` §8.4 `parsing` 行与 §8.6 删除规则（块 ID 与删除保护，A06 条文）、`docs/integrations.md` 两处「重新向量化」（A07 条文） | 规格 V2/V3/V5/V6/V8/V10 修订、新增 V12 与 PUB-28～34；ADR-012 修订 1（决定 9～12）；A06 §8.4/§8.6 与 A07 两处已改并加注；核对脚本 55 项 ALL PASS，三个篡改副本 exit 1；`./scripts/verify.sh` exit 0、`git diff --cached --check` exit 0；`docs/handoffs/claude-a04.md` 第十节 |

- A04-R01/R02 的修复（ArvinHan 2026-09-23 签收，ADR-012 修订 1）：文本块按资料修订（资料 + 内容哈希 + 解析器版本）生成 ID 且不可变，快照固定修订列表，检索按 `revision_id` 过滤；失败任务的来源块加删除保护；运行时只有一个向量空间，换模型须停机离线重新向量化全部文本块、草稿与已提交版本，配置与记录不一致即拒绝启动。
- 交出的后续项（均未认领）：**A10** 在清单中为「重新向量化命令」补登叶子任务；**C06/C07** 定义「下线旧资料修订」；**B06/D09/D10/C09/D11/E07/F03** 按 ADR-012 修订 1 的实现依赖落实。

## B05 后端应用工厂与健康检查

| 原子 ID | 状态 | 任务 | 负责人 | 目标分支 / base HEAD | 文件锁（本轮唯一写入者） | 证据 |
| --- | --- | --- | --- | --- | --- | --- |
| B05 | DONE | 初始化 FastAPI 应用工厂与匿名 `GET /health` | Codex（后端） | `codex/b05-fastapi-health` / base `50a15c9` | `src/backend/pyproject.toml`、`src/backend/app/main.py`、`src/backend/app/api/health.py`、`tests/backend/test_b05.py`；**范围扩展**：`src/backend/app/api/__init__.py`（包标记）、`src/backend/README.md`（启动与测试说明）、任务板、架构说明和 `docs/handoffs/codex-b05.md` | pytest 3 PASS；基础 verify PASS；Uvicorn 实际启动并返回 HTTP 200；`docs/handoffs/codex-b05.md` |

- 输入：已签收的 ADR-004、ADR-009，以及 `740adb` 分支现有 `/health` 契约（`status = ok`、`version` 为字符串）；B05 不引入第二套契约真源。
- 输出：可由 Uvicorn 启动的应用工厂、无鉴权健康检查、后端依赖及 pytest 配置、成功/边界/失败测试。
- 依赖：A01 已完成；A10 导入完整 `api.v1.yaml` 与 B06 配置校验仍是后续任务，不阻塞无密钥健康检查。
- 风险：当前主分支尚无契约真源或数据库实现；本任务的健康检查只表示 API 进程可响应，不探测 Neo4j、SQLite 或模型服务。
- 验证：`python -m pytest tests/backend/test_b05.py -q`（本机 Windows 的 `python3` 等价命令）3 PASS；`./scripts/verify.sh` PASS；`git diff --check` PASS；Uvicorn HTTP 冒烟 200，响应含 `status` 与 `version`。详细命令、版本和限制见交接。
- B05 只完成后端最小启动与健康检查；父任务 M0-03 的 B06 设置加载仍待完成。A10 导入契约真源后，生成 DTO 应替换 B05 的临时响应模型。

## B06 后端设置加载与启动验证

| 原子 ID | 状态 | 任务 | 负责人 | 目标分支 / base HEAD | 文件锁（本轮唯一写入者） | 证据 |
| --- | --- | --- | --- | --- | --- | --- |
| B06 | DONE（审查修复） | 从环境变量加载类型化设置并在启动时校验 | Codex（后端） | `codex/b06-settings` / base `e8ce796` | `src/backend/app/config.py`、`tests/backend/test_b06.py`；范围扩展：`src/backend/app/main.py`（接入启动校验）、`src/backend/README.md`、`docs/architecture.md`、`docs/integrations.md`、`.env.example`（登记发布锁参数）、本任务板、`docs/handoffs/codex-b06.md`；审查修复增加 `src/backend/app/repositories/embedding_space.py`、`src/backend/app/services/startup.py`、`src/backend/app/__main__.py`、`tests/backend/test_b05.py` 与发布规格同步 | B05+B06 47 PASS；基础 verify PASS；`git diff --check` PASS；见 `docs/handoffs/codex-b06.md` |

- 输入：A07 环境变量表及启动校验规则、A03/A06 任务配置、ADR-012 发布锁参数、B05 应用工厂。
- 输出：只读环境变量的类型化设置、非法值拒绝启动、密钥脱敏、fake 模式无真实模型凭据可启动。
- 依赖：B05、A07 已完成；真实模型供应商取值 D-02a～f 待签收，不影响 fake 验证。
- 风险：既有 `.env.example` 未登记 `PUBLISH_LEASE_SECONDS`、`COURSE_LOCK_WAIT_SECONDS`；本轮同步补齐，不改变已签收的默认值。
- 验证：`python -m pytest tests/backend/test_b06.py -q`、B05 回归、`./scripts/verify.sh`、`git diff --check`。
- 实际结果：B06 35 PASS、B05 回归 3 PASS；默认 fake、合法 live、非法范围与条件、密钥脱敏、应用导入时拒绝非法配置均有实际测试；基础 verify 与 diff check exit 0。D-02 真实模型取值仍待签收。

### B06 审查修复

- 输入：B06 固定提交 `ca353b1`、审查指出的 PUB-32 启动门禁、URL 漏检和监听参数未接线；`specs/teacher-review-publish.md` V12、ADR-012 修订 1。
- 输出：SQLite 单行向量空间启动门禁、严格 URL 校验、读取 `API_HOST`/`API_PORT` 的启动入口及回归测试。
- 依赖：Python 标准库 SQLite；C01 后续迁移须接管并保留引导表，worker 入口须调用同一门禁。
- 风险：新增 SQLite 引导表；首次启动会写入配置空间，已有空间不一致必须保持旧值并拒绝启动。回滚需停机并从变更前 SQLite 备份恢复，不能删除空间记录绕过检查。
- 验证：先运行新增负例复现；再运行 B05/B06 pytest、`./scripts/verify.sh`、`git diff --check`。
- 结果：新增负例先为 5 FAIL；修复后 B05+B06 共 47 PASS、基础 verify PASS、`git diff --check` PASS。API lifespan 已接入门禁；C09 尚无 worker 入口，须复用 `validate_embedding_space()`；离线重新向量化命令仍归后续任务。
| 原子 ID | 状态 | 任务 | 负责人 | 目标 worktree / base HEAD | 文件锁（本轮唯一写入者） | 证据 |
| --- | --- | --- | --- | --- | --- | --- |
| A06-R01/R02 修复 | DONE（ADR-011 修订 1 已签收） | 修复 Codex 审查 A06-R01（失败清理会删除被其他任务复用的图元素）与 A06-R02（`cleanup_pending` 期间失败任务仍可暴露草稿） | Claude（协调 Agent） | `.claude/worktrees/a04-f5f479`（分支 `claude/a06-r01-r02-fix`）/ base `50a15c9` | `specs/task-processing.md`（I6、§8.4、§8.9）、`docs/decisions.md`（ADR-011 修订 1）、`docs/tasks.md`、`docs/handoffs/claude-a06.md`；**范围扩展**：`specs/teacher-review-publish.md` V3 与 PUB-35（A04 条文）、`docs/architecture.md` | I6、§8.4（贡献记录、草稿可见性、`persisting` 第 1/3/4 条）、LEASE-12 修订与 LEASE-18～23；ADR-011 修订 1（决定 9～11）；A04 V3 可见性前提与 PUB-35；`check_a06.py` 第二版 55 项 ALL PASS、四个篡改副本 exit 1；A04 核对脚本 ALL PASS；`./scripts/verify.sh` exit 0、`git diff --cached --check` exit 0；`docs/handoffs/claude-a06.md` 第九节 |

- A06-R01/R02 的修复（ArvinHan 2026-09-23 签收，ADR-011 修订 1）：草稿按任务记录贡献（`contrib_tasks`、`contrib_manual`、来源关联带 `task_id`），可见性由 SQLite 有效任务集合 V 决定，T6 提交才可见、T9 起即不可见；清理按贡献撤销，只删无贡献元素，降为存储回收。
- 交出的后续项（均未认领）：**F02** 草稿查询必带 V；**F03** 贡献字段约束/索引；**F08/F13** 写入登记贡献；**E10/E11** 融合候选按 V 过滤；**G04** 建快照按 V 过滤。

| 原子 ID | 状态 | 任务 | 负责人 | 目标 worktree / base HEAD | 文件锁（本轮唯一写入者） | 证据 |
| --- | --- | --- | --- | --- | --- | --- |
| A07-R01 修复 | DONE（ADR-011 修订 2 已签收） | 修复 Codex 审查 A07-R01（`model_calls` 去重键未覆盖物理重试与问答调用） | Claude（协调 Agent） | `.claude/worktrees/a04-f5f479`（分支 `claude/a07-r01-fix`）/ base `8340b1e` | `docs/integrations.md`（预算）、`specs/task-processing.md`（§8.4「计费不重复」、LEASE-17、LEASE-24～27）、`docs/decisions.md`（ADR-011 修订 2）、`docs/tasks.md`、`docs/handoffs/claude-a07.md` | §8.4「计费不重复」、LEASE-17 修订与 LEASE-24～27；`docs/integrations.md`「预算」四条与新增「调用记录（`model_calls`）」；ADR-011 修订 2（决定 12）；专项核对 17 项 ALL PASS、四个篡改副本 exit 1；`check_a07.py` 329/329、`check_a06.py` 第二版与 A04 核对脚本 ALL PASS；`./scripts/verify.sh` exit 0、`git diff --cached --check` exit 0；`docs/handoffs/claude-a07.md` 第九节 |

- A07-R01 的修复（ArvinHan 2026-09-23 签收，ADR-011 修订 2）：每次实际供应商调用一条 `model_calls`，以发请求前生成的 `call_id` 为身份与去重键；预写失败不发请求；未收到响应按「输入估算 + 声明的输出上限」计入；问答以 `request_id` 归属。
- 交出的后续项（均未认领）：**E03** 每个 LLM 请求声明输出上限并估算输入；**E04** 预写、回写与预算汇总；**E05** 修复调用独立记录；**J03/J05** 问答调用带 `request_id`；**C01** 建表以 `call_id` 为主键。

| 原子 ID | 状态 | 任务 | 负责人 | 目标 worktree / base HEAD | 文件锁（本轮唯一写入者） | 证据 |
| --- | --- | --- | --- | --- | --- | --- |
| A08 | IN REVIEW（R01～R14 第 3 轮复审通过；待 §7 产品签收） | 定义推荐评分与进度跨版本规则 | Codex | `.claude/worktrees/codex-a08-learning-path`（`codex/a08-learning-path`）/ base `1a47eb2` | `specs/learning-path.md`、`docs/atomic-task-plan.md` B12/I05 行、`docs/atomic-tasks.json` B12/I05 `acceptance`、本任务行及下方说明、`docs/handoffs/codex-a08.md` | `specs/learning-path.md` LP-1～19；R11～R14 第 3 轮复审通过（`claude/codex-a08-check-0ae6d7@acb257c`）；修复映射与验证见 `docs/handoffs/codex-a08.md`；未改 `src/contracts/` |

- A08 输入：S2 §6.4.7、A04/ADR-012、A02 掌握枚举、Claude 第 1 轮 R01～R10 与第 2 轮 R11～R14 报告、第 3 轮复审、已签收 ADR-014。输出：修订后的可学/评分/跨版本读时继承与批量写入规格；进度接口有效/原始状态及来源提案；B12/I05 的 Markdown 与 JSON 验收同步。依赖：ADR-014 已随 `origin/main@6881ffe` 集成，B12 需在 YAML 真源落地进度响应字段；风险与待决：缺值、权重来源、展示上限、进度响应字段名及 `updated_at` 语义，以及显式降级覆盖继承与谱系存放位置均见 `specs/learning-path.md` §7；R15 未在本轮修订，未改 DTO、仓储或发布快照格式。验证命令：`./scripts/verify.sh`、`git diff --check`、`python3 -m json.tool docs/atomic-tasks.json > /dev/null` 及两项 grep，实际结果见交接。
