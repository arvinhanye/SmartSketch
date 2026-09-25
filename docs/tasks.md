# 任务看板

## 2026-09-25 并行认领批次

| ID | 状态 | 任务 | 负责人 | 分支 / 基线 | 文件锁（唯一写入者） | 证据 / 同步状态 |
| --- | --- | --- | --- | --- | --- | --- |
| B14 | DONE（PR #214 `342cc3e`；Claude 审查通过；#56 已关闭） | 建立契约导出与漂移检查 | ArvinHan（Codex 子代理） | `codex/b14-contract-drift` / base `a7a0be0` | `scripts/gen-contracts.sh`、`scripts/gen_contracts.py`、`src/contracts/api.v1.yaml`、`src/contracts/v1/generated/`、`tests/contracts/test_b14.py`、`docs/handoffs/codex-b14.md` | 依赖 B09–B13 已在基线；定向 3 passed，`./scripts/verify.sh` exit 0（25 项负例及 B08/B09/B10/B12/B13 回归），`gen-contracts.sh --check`、`git diff --check` 通过；审查修复 `0b1fb6c`；Issue #56 已分配并标记 `status:in-review`；[PR #214](https://github.com/arvinhanye/SmartSketch/pull/214)。
| D08 | DONE（PR #215 `5a0bcdb`；Claude 审查通过，P3 见下；#77 已关闭） | 实现章节内语义分块 | ArvinHan（Codex 子代理） | `codex/d08-semantic-chunking` / base `a7a0be0` | `src/backend/app/services/chunking.py`、`tests/backend/test_d08.py`、`docs/handoffs/codex-d08.md` | 依赖 D02/D03/D04/D06/D07 已在基线，D-13 章节路径前缀已实现；定向 13 passed、后端 1015 passed（1 条既有弃用警告），`./scripts/verify.sh` 与 `git diff --check` 通过；审查修复 `d675d2b`；Issue #77 已分配并标记 `status:in-review`；[PR #215](https://github.com/arvinhanye/SmartSketch/pull/215)。

## 2026-09-25 Codex 认领：E07

| 原子 ID | 状态 | 任务 | 负责人 | 基线与文件范围 | 验收 |
| --- | --- | --- | --- | --- | --- |
| E07 | DONE（PR #217 `8b2c33c`；Claude 审查通过，P3 见下；#87 已关闭） | 实现向量适配与维度检查 | Codex（数据与 AI） | `main@a7a0be0`；`src/backend/app/services/ai/embeddings.py`、`tests/backend/test_e07.py`、相关架构与交接 | 同批/跨批重复请求去重，进程内缓存默认 1024 条 LRU；E07 16 passed；后端全量 1035 passed；`./scripts/verify.sh` exit 0；`docs/handoffs/codex-e07.md` |

- 输入：E02 的 `EmbeddingClient` 与 A07 的模型配置；输出：逐条携带模型和空间标识的向量。依赖 E02、A07 已在当前基线。
- 风险：在线/本地客户端由 E03 接入；E07 通过注入 `EmbeddingClient` 验证模式切换，不引入未经签收的真实供应商依赖。当前工作区的 C03 文件不在 E07 范围内。
- 审查修复：同一次 `embed` 调用按空间与文本哈希合并缓存未命中项，跨批重复只请求一次；LRU 有限缓存超限后重算旧文本。先新增 4 个失败用例复现，再修复为 16 passed；后端全量 1035 passed。
- 验证：项目虚拟环境中 `python -m pytest tests/backend/test_e07.py -q`；通过 Git Bash（设置虚拟环境和前端工具路径）运行 `./scripts/verify.sh`；`git diff --check`。详见交接。

## 2026-09-25 Codex 认领：C03

| 原子 ID | 状态 | 任务 | 负责人 | 基线与文件范围 | 验收 |
| --- | --- | --- | --- | --- | --- |
| C03 | DONE（PR #216 `81aa691`；Claude 审查发现 P1 C03-R01，已修复后合并；#60 已关闭） | 实现身份边界与课程访问依赖 | Codex（后端） | `main@a7a0be0`；`app/api/dependencies.py`、`app/services/access.py`、账号/任务仓储只读入口、`tests/backend/test_c03.py`、相关架构与交接 | C03 17 passed；后端 1019 passed；`./scripts/verify.sh` exit 0；交接 `docs/handoffs/codex-c03.md` |

- 输入：`specs/identity-access.md` §2、§4 访问矩阵；输出：可复用的身份/课程/任务访问依赖。依赖 C02、B09、C13 已在当前基线。
- 风险：下游路由尚未接入，C03 提供依赖接口和测试用路由，不代替 C04/C07 等任务实现；仅持有任务 ID 时需仓储先解析归属课程。
- 验证：`python -m pytest tests/backend/test_c03.py -q`、`./scripts/verify.sh`、`git diff --check`。
- 验收证据：Bearer 身份、停用实时失效、请求身份字段无效、课程内角色、未发布和任务越权同形错误均有定向用例；`.venv/Scripts/python.exe -m pytest tests/backend/test_c03.py -q` 17 passed；后端全量 1019 passed；Git Bash 运行 `./scripts/verify.sh` exit 0（契约负向 24 项、B08/B09/B10/B12/B13 回归）；详见交接。


## B12 进度与推荐契约（2026-09-25）

| ID | 状态 | 任务 | 负责人 | 目标分支 / base HEAD | 文件锁（本轮唯一写入者） | 证据 |
| --- | --- | --- | --- | --- | --- | --- |
| B12 | DONE（PR #202 `d633160`） | 迁移进度和推荐契约 | ArvinHan（Claude 子代理执行） | `claude/b12-progress-contract` / base `8eeac3b` | `src/contracts/api.v1.yaml`、`src/contracts/v1/generated/`、`tests/contracts/test_b12.py`；按 B08～B13 先例接入 `scripts/verify/contracts.sh`；随附 `specs/learning-path.md` 状态标注与 `docs/handoffs/claude-b12.md` | 改真源前 B12 65 failed / 28 passed，改后 93 passed；契约全量 255 passed；`./scripts/gen-contracts.sh --check` exit 0；`./scripts/verify.sh` exit 0（含 B12 回归）；生成 TS `tsc --noEmit --strict` exit 0；`git diff --check` exit 0；反向篡改 6 处均被检出；范围扩展：`src/contracts/errors.v1.md` 登记 `details.diagnostic_id`；`docs/handoffs/claude-b12.md` |

- 输入：`specs/learning-path.md`（LP-1～19、§7）、ADR-014 及修订 1、`docs/atomic-task-plan.md` B12 行；输出：`ProgressEntry` 新字段、GET/PUT 返回全部节点、推荐 DTO 与未发布错误/全部掌握空态区分。
- 依赖：B08、A08 已完成；B11 已合入并释放 YAML 锁（issue #54）。
- 风险：已提交空图按发布快照完整性故障处理，不增加 `no_graph` wire 状态；未舍入 double 分量按 `u→i→c→e` 求和须逐位等于评分。
- 验证：`python3 -m pytest tests/contracts/test_b12.py -q`、`./scripts/gen-contracts.sh --check`、`./scripts/verify.sh`、`git diff --check`。
- 待决（需 ArvinHan 决定，I02/I05 实现前）：
  1. 学生读路径完整性错误的公开码：契约暂用既有 `INTERNAL_ERROR` + 闭合 `details.diagnostic_id`（`LearningIntegrityError`）；是否新增专用码、字段名是否与问答 `details.request_id` 统一。
  2. `PUT /progress` 中 `kp_id` 不在绑定发布版（草稿独有、已删除、他课、发布指针变化后复核失败）时整批拒绝的公开码（422/404/409）与 `details` 形状；契约描述暂写“待定”。
- 待审查的契约决定：进度响应改为 `ProgressResponse{graph_version, entries}`；移除推荐 `target`/`path`（§7，交 O02）；重复 `kp_id` 归 422 `VALIDATION_ERROR`。详见交接。
- 观察：`tests/contracts/test_b11.py` 未接入 `scripts/verify/contracts.sh`，不在 B12 范围内，未改。
- 合并（2026-09-25）：PR #202。合并前协调方补修 `tests/tooling/test_b07.py` 门禁夹具缺 `test_b12.py` 占位（`verify.sh` 与 CI 均不跑 `tests/tooling`，未检出）。B14 现可占用 YAML 与生成物文件锁。

## B11 图谱编辑与版本契约（2026-09-24）

| ID | 状态 | 任务 | 负责人 | 范围与验收 | 证据 |
| --- | --- | --- | --- | --- | --- |
| B11 | DONE（PR #194 `2de97ba`） | 迁移图谱编辑、关系降级及版本发布契约 | Codex（`arvinhanye`） | `src/contracts/api.v1.yaml`、生成物、`tests/contracts/test_b11.py`、相关规格；补节点修订号与编辑前置条件、关系来源及降级解释、发布/回滚结构化响应；负例与生成一致性 | B11 30 passed、契约全量 162 passed、`./scripts/verify.sh` exit 0、`./scripts/gen-contracts.sh --check` exit 0、`git diff --check` exit 0；`docs/handoffs/codex-b11.md`；协调方把 #196、#194 依次临时合到 `a08bd5b` 上复核：生成物一致、契约与工具 176 passed（B11 30）、后端 720 passed、`verify.sh` exit 0；CI 6 项通过；#53 已关闭 |

- 输入：ADR-009、ADR-012（含修订 3）、A02-R01、B08 真源；输出：B11 YAML 真源、全量生成物、契约测试与交接。
- 依赖：B08、A04 已入 main；B12 暂不占用 YAML 锁。风险：新增必填响应字段影响未来实现方；`merged_from` 与 `commit_seq` 只属内部快照/存储，不泄露到 wire DTO。
- 验证：`python3 -m pytest tests/contracts/test_b11.py -q`、`./scripts/gen-contracts.sh --check`、`./scripts/verify.sh`、`git diff --check`。
- 合并后（2026-09-25）：B12 现可占用 YAML 与生成物文件锁。遗留：`downgrade_cycle` 与 `PUBLISH_BLOCKED` 的 `cycle` 首尾同 ID 由 F13、G04 在服务层校验（契约以 `x-closed-cycle: true` 标记）。

> 状态：`TODO` → `IN PROGRESS` → `BLOCKED` / `DONE`。认领或完成任务时更新本表；每个 DONE 项必须指向验收证据和交接文件。

## 当前里程碑：M0 协作与应用骨架

| ID | 状态 | 任务 | 负责人 | 验收条件 | 证据 |
| --- | --- | --- | --- | --- | --- |
| M0-01 | DONE | 建立多 Agent 协作、文档、规格、源码目录骨架 | Codex | 必需文件齐全；基础校验通过 | `scripts/verify.sh`；`docs/handoffs/codex-m0-project-scaffold.md` |
| M0-02 | IN PROGRESS（B01～B04 已完成；B15 待 B14） | 初始化 Vue 3 + TypeScript + Vite 前端 | Frontend Agent | 可启动；具备最小路由、类型检查与测试命令 | B01～B04 见下方验收证据；HTTP 客户端 B15 仍待契约 B14 |
| M0-03 | DONE（B05+B06） | 初始化 FastAPI 后端与健康检查 | Backend Agent | 可启动；`GET /health` 有契约和测试 | B05/B06 测试 38 PASS；基础 verify PASS；`docs/handoffs/codex-b05.md`、`docs/handoffs/codex-b06.md` |
| M0-04 | TODO | 定义第一版 API、SSE 任务事件与图谱 DTO | Backend + Frontend Agent | `src/contracts/` 有版本化契约；双方确认 | 待补充 |
| M0-05 | TODO | 定义 Neo4j/SQLite 开发环境与本地启动方式 | Data/Backend Agent | 无密钥可启动依赖；环境变量文档完整 | 待补充 |

## CI 配置

| ID | 状态 | 任务 | 负责人 | 范围与验收 | 证据 |
| --- | --- | --- | --- | --- | --- |
| CI-01 | DONE（待 GitHub 首次运行确认） | 为当前仓库建立 GitHub Actions 基础质量门禁 | Codex | push、pull request 和手动触发；只运行仓库现有 `scripts/verify.sh`，不把尚未建立的前后端测试标成通过；工作流语法和本地校验通过 | `.github/workflows/ci.yml`；`./scripts/verify.sh` PASS；YAML 解析/关键字段检查 PASS；`git diff --check` PASS；`docs/handoffs/codex-ci-01.md` |
| CI-02 | DONE（待审查；PR #29 已合入 `025cbee`） | 把前端与后端测试接入 CI | Claude | 新增 Frontend（`npm ci`、type-check、`test -- --run`、build）与 Backend（`pip install -e src/backend[test]`、`pip check`、`pytest tests/backend`）两个 job；只读权限、无密钥；不跳过、不吞退出码。依赖：B05/B06 已合入 main（PR #14、#21）；B02（PR #27）未合入前 PR 以 B02 分支为目标。K11 仍负责 E2E 接入 | 分支 `claude/ci-02`；YAML 解析三 job PASS；在含 B02～B06 的临时合并树上以干净环境逐条运行 job 命令：前端 30 passed、build 通过，后端（Python 3.11）58 passed、`pip check` 通过；`docs/handoffs/claude-ci-02.md` |

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
| D-01 | MVP 首批课程示例和脱敏资料来源。所选材料须覆盖一门完整课程的一章，作为赛题抽取硬指标的基准（REQ-01，`specs/course-knowledge-graph.md` 验收 7）；按赛题第 7 节，只用自编示例或许可允许使用的开源教材 | 产品负责人 | M1 开始前 |
| D-02 | 首个 OpenAI 兼容模型供应商与预算上限。A07 已拆为 D-02a～f 六项，签收入口见 `docs/integrations.md`「待签收取值（D-02）」；配置形状与规则已定，取值均未签收 | 技术负责人 | 接入抽取服务前（fake 实现可先行） |
| D-03 | 登录是否先采用本地演示角色。**已关闭**：ADR-013（A05）定为本地账号 + 预置演示账号，不采用纯演示角色；账号类型与课程内角色分离；教师按用户名添加学生（ArvinHan，2026-09-23 签收） | 产品负责人 | 已完成 |
| PLAN-D01 | 两个 Claude 分支 YAML-first/Pydantic-first 唯一源、API 前缀和冲突 ADR 编号如何统一（A01/A02）。**已关闭**：唯一源与 ADR 编号由 ADR-004 签收；API 前缀由 ADR-009（A02）定为 `/api/v1`（均为 ArvinHan，2026-09-22） | 技术负责人 | 已完成 |
| PLAN-D02 | 发布快照/图与向量版本化/双存储补偿方案（A04）。**已关闭**：由 ADR-012（A04）裁定（ArvinHan，2026-09-23 签收） | 技术负责人 | 已完成 |
| PLAN-D03 | worker 队列/租约/取消/重试及部分失败语义（A03/A06）。**已关闭**：取消与部分失败语义由 ADR-010（A03），队列 / 租约 / 重试 / 幂等由 ADR-011（A06）签收（均为 ArvinHan，2026-09-23） | 技术负责人 | 已完成 |
| PLAN-D04 | 哪个 worktree 作为集成基线、分批合并顺序与合并权（A10）。**已关闭**：ADR-016 定为以 main 为基线、按批检出文件导入（每批一个 PR、一个功能边界），Agent 只开 PR、由 ArvinHan 合并并交叉审查；批次顺序见 `docs/reviews/branch-integration-map.md` 第 3 节（ArvinHan，2026-09-23 签收） | 项目负责人 | 已完成 |
| D-08 | 融合自动合并阈值与低置信度阈值的初始取值（沿用 `740adb` 未决问题编号，ADR-016 决定 7） | 技术负责人 | E09/E10 开工前 |
| D-09 | 前端登录页与会话存储缺少原子任务。**已关闭**：补登 **H13 实现前端登录页与会话存储**（依赖 C13、B15、B03、B04；原子清单增至 141 项），负责登录页、`sessionStorage` 会话读写、401 清会话与课程上下文回登录页，并向 B03 的 `getAccountRole` 注入真实来源（ArvinHan，2026-09-24 确认） | 产品负责人 / 协调 Agent | 已完成 |
| D-10 | 迁移文件编号何时确定、表间外键如何约束合并顺序。**已关闭**：编号在合并时取「main 最大编号 + 1」，原子清单中 002～009 改为 `NNN_<名称>.sql`；C02 增加对 C13 的依赖（`course_members.user_id` → `users`）。原因：C01 迁移器拒绝应用比已应用版本更小的编号，按旧计划 C13 的 `008` 先合并会使后到的 004～007 无法应用（ArvinHan，2026-09-24） | 技术负责人 | 已完成 |
| D-11 | 上传单文件大小上限。**已关闭**：50 MiB（52 428 800 字节），环境变量名 `UPLOAD_MAX_BYTES`，超过即 413 `FILE_TOO_LARGE`（`details.limit_bytes`）。与存储目录 `STORAGE_DIR` 一起在 C13 合并后补进 `config.py`、`.env.example`、`docs/integrations.md`（三者当前在 C13 文件锁内）；C05 的 `FileStorage(root, max_bytes)` 由 C06/C07 按此传入（ArvinHan，2026-09-24） | 技术负责人 | 已完成（配置已落地，见「D-11 上传配置落地」） |
| D-12 | Markdown 中 `#` 后不加空格的写法（如 `#第一章`）是否算标题。**已关闭**：放宽，由 D03 在 PR #191 中实现；规则保守，只作用于顶层行，不误伤 `#include`、`#1`、`#tag` 这类行，边界见 `docs/handoffs/claude-d03.md`。D03 首次合并前完成，`parser_version` 仍为 `markdown/1`（ArvinHan，2026-09-24） | 产品负责人 | 已完成 |
| D-13 | 解析器只把标题放进章节路径、标题文字不在块正文里，抽取（D12）看不到标题。**已关闭**：由 D08 分块时在每块正文前拼上章节路径（`section_path`），解析器输出与 D01 模型不变（ArvinHan，2026-09-24） | 技术负责人 | 已完成（D08 实现） |
| D-14 | 只设所有者密码（空用户密码即可打开，仅限制复制、打印等权限）的 PDF 是否放行。**暂定**：与其他加密 PDF 一样按 `DOCUMENT_UNREADABLE`（`encrypted`）拒绝（ArvinHan，2026-09-25）。放行前须决定是否遵守「禁止复制」等权限，涉及版权 | 产品负责人 | 首批课程资料导入前（D-01） |
| D-15 | 赛题「知识抽取准确率不低于 70%」是否同时约束关系（REQ-01）。**已关闭**：实体和关系分别计算、各自不低于 70%，写入 `specs/course-knowledge-graph.md` 验收 7 与 K01/K02（ArvinHan，2026-09-24） | 产品负责人 | 已完成 |
| PLAN-D05 | 学习材料生成分支决定是否同步 main；目标路径是否纳入（O01） | 产品负责人 | 主线验收后、加分项前 |

## Claude 审查批次

| ID | 状态 | 范围 | 负责人 | 验收与证据 |
| --- | --- | --- | --- | --- |
| REVIEW-02 | DONE（分批；S-07 尚有待审范围） | A01 文档交付 `88ea517`/`6c19f25`；S-07 本地脚本 `8865686` | Codex | `docs/reviews/codex-claude-a01-s07-tooling-2026-09-23-0136z.md`；A01 路径映射 22/29 一致；S07-R12～R14 已复现；`docs/handoffs/codex-review-02.md` |
| REVIEW-A08 | DONE（不建议签收；R02/R03 已签收为 ADR-014；待 Codex 修 R01～R04） | Codex A08 未提交快照（`codex-a08-learning-path` @ `1a47eb2` + dirty，指纹见报告） | Claude | `docs/reviews/claude-codex-a08-2026-09-23.md`：P2×4（R01 `no_graph` 与 A04 V3 冲突、R02 中心度恒 ≤0.5、R03 合并进度倒退未列签收、R04 外课/历史 ID 判定不可实现）、P3×6；R02/R03 的产品决定见 `docs/decisions.md` ADR-014；`docs/handoffs/claude-review-a08.md` |
| REVIEW-A08-R2 | DONE（R01～R10 已修；R11～R14 由 Codex 修复后第 3 轮复审通过，无新 P1/P2；§7 与 ADR-014 两项细则已由 ADR-014 修订 1 签收，R15 按“以本次连续归属起点为界”写死） | Codex A08 修订稿（`codex-a08-learning-path` @ `1a47eb2` + dirty，规格 `efe23f9e…`，指纹见报告） | Claude | `docs/reviews/claude-codex-a08-r2-2026-09-23.md`：R01～R10 复核通过（R01 在 `atomic-tasks.json` B12 与 I05 仍有“无图”残留）；P2×1（R11 合并继承后进度接口返回原始还是有效状态未定义）、P3×4（R12 谱系终止与不变式、R13 舍入后分量不可还原、R14 任务清单 Markdown/JSON 不一致、R15 细则 1 提案有歧义）；`docs/handoffs/claude-review-a08-r2.md` |
| REVIEW-03 | DONE（仅 R06 修复；S-07 仍待审） | S-07 `978671e` 的 UTF-8 生成物缺失假绿修复 | Codex | `docs/reviews/codex-claude-s07-r06-978671e-2026-09-23-0305z.md`；定向回归 PASS；`verify.sh` 因生成物未入库 exit 1；`docs/handoffs/codex-review-03.md` |
| REVIEW-04 | DONE（固定提交批次；活跃会话与 S-07 仍待审） | A02 `13d586e` 文档决定；HOOK-01 `3c2dfab` 命令提取修复 | Codex | `docs/reviews/codex-claude-a02-hook01-2026-09-23-0528z.md`；A02-R01 P2；HOOK-01 回归 14 PASS；`docs/handoffs/codex-review-04.md` |
| REVIEW-05 | DONE（A03 固定提交；S-07 仍待审） | A03 `2049129` 生命周期规范；CI-01 交接 `43a278c`/`25d96cf`；S-07 四个生成物 | Codex | `docs/reviews/codex-claude-a03-ci01-s07-2026-09-23-0606z.md`；A03-R01/R02 P2；A03 骨架门禁 PASS；`docs/handoffs/codex-review-05.md` |
| REVIEW-06 | DONE（A06 发现 P1；其他旧范围仍待审） | A03 `6345ce1` 修复复核；A06 `ab04053` 租约/清理规范 | Codex | `docs/reviews/codex-claude-a03fix-a06-ab04053-2026-09-23-0649z.md`；A03-R01/R02 文字冲突已修；A06-R01/R02 P1；骨架门禁 PASS；`docs/handoffs/codex-review-06.md` |
| REVIEW-07 | DONE（A04 发现 P1/P2；A05/A07 仍待稳定） | A04 `110f243` 发布协议与合并冲突 `4b2ccb5` | Codex | `docs/reviews/codex-claude-a04-4b2ccb5-2026-09-23-0730z.md`；A04-R01 P1、A04-R02 P2；文档结构检查及 diff check PASS；`docs/handoffs/codex-review-07.md` |
| REVIEW-08 | DONE（A05 无新问题；A07 发现 P2；其他旧范围仍待审） | A05 `e0b7ccd` 身份边界；A07 `af9ff7d` 模型配置 | Codex | `docs/reviews/codex-claude-a05-a07-2026-09-23-0804z.md`；A07-R01 P2；两目标骨架门禁与 diff check PASS；`docs/handoffs/codex-review-08.md` |
| REVIEW-09 | DONE（固定修订复核；新增 2 项 P2；旧待审范围保留） | A04 `02bc228`、A06 `d426170`、A07 `1012b6f` 文档修订 | Codex | `docs/reviews/codex-claude-a04-fixes-1012b6f-2026-09-23-1215z.md`；FIX-R01/R02 P2；目标骨架门禁与 diff check PASS；`docs/handoffs/codex-review-09.md` |
| REVIEW-10 | DONE（FIX-R01/R02 原缺口文档层关闭；新增 FIX-R03 P2） | FIX-R01/R02 修复提交 `5186e09` 的文档复核 | Codex | `docs/reviews/codex-claude-fix-r01-r02-5186e09-2026-09-23-1252z.md`；固定提交目标 `./scripts/verify.sh` PASS、`git diff 1a47eb2..5186e09 --check` PASS；主目录 `./scripts/verify.sh` 与 `git diff --check` PASS；`docs/handoffs/codex-review-10.md`。仅文档、无运行时测试；旧待审范围保留 |
| REVIEW-11 | DONE（仅 S-07 DAG 任务/规格批次；其余待审） | S-07 `978671e` 的合并任务与课程图谱前置关系验收 | Codex | `docs/reviews/codex-claude-s07-dag-plan-2026-09-23-1304z.md`；S07-R15 P2；目标两次稳定，`git diff 05d214c..978671e --check` PASS；`docs/handoffs/codex-review-11.md` |
| REVIEW-12 | DONE（仅 A09 固定文档批次；A10 与旧范围待审） | A09 `1754c96` 问答终态/引用协议 | Codex | `docs/reviews/codex-claude-a09-1754c96-2026-09-23-1400z.md`；A09-R01/R02 P2；目标两次稳定，`./scripts/verify.sh` 与 `git diff f9dfc8f..1754c96 --check` PASS；`docs/handoffs/codex-review-12.md` |
| REVIEW-13 | DONE（仅 A10 固定文档批次；A08 签收与旧范围待审） | A10 `37da669` 导入映射与 ADR-016 | Codex | `docs/reviews/codex-claude-a10-37da669-2026-09-23-1403z.md`；A10-R01/R02 P2；目标稳定，骨架门禁、diff check、映射核对及 8 个负例 PASS；`docs/handoffs/codex-review-13.md` |
| REVIEW-14 | DONE（仅 A08 签收六文件差异；旧范围仍待审） | A08 签收 `f9dfc8f` 上稳定未提交文档 | Codex | `docs/reviews/codex-claude-a08-signoff-f9dfc8f-2026-09-24-0123z.md`；A08S-R01 P2、A08S-R02 P3；目标 `./scripts/verify.sh`、`git diff HEAD --check`、任务 JSON 语法均 PASS；`docs/handoffs/codex-review-14.md` |
| REVIEW-15 | DONE（仅 A09 修复文档批次；旧范围仍待审） | A09 `1754c96..68b1aaf` 逐句引用与日志规则复核 | Codex | `docs/reviews/codex-claude-a09-fix-68b1aaf-2026-09-24-0200z.md`；A09-R02 文档层关闭，A09F-R01/R02 两项 P2；目标 `./scripts/verify.sh` 与 diff check PASS；`docs/handoffs/codex-review-15.md` |
| REVIEW-16 | DONE（仅 A10 批 1 补；其余待审） | `batch1-qa@3da4f2f` 问答规格命名门禁与逐规格负例 | Codex | `docs/reviews/codex-claude-batch1-qa-3da4f2f-2026-09-24-0446z.md`；无新问题；目标 `verify.sh`（24/24 契约负例）与 diff check PASS；`docs/handoffs/codex-review-16.md` |
| REVIEW-17 | DONE（仅 FIX-R03 规格补注；其余待审） | `wrap-fix-pr16@8dcd7b2` 迁移与运行时空间写入边界 | Codex | `docs/reviews/codex-claude-fix-r03-8dcd7b2-2026-09-24-0451z.md`；FIX-R03 文档层关闭，无新问题；目标骨架门禁、diff check PASS；F03/PUB-39 运行时未实现；`docs/handoffs/codex-review-17.md` |
| REVIEW-18 | DONE（仅 B02 固定提交；B03/B04 与旧范围待审） | `a09-dev-environment-check-8e5e93@8e5b707` 前端测试配置 | Codex | `docs/reviews/codex-claude-b02-8e5b707-2026-09-24-0504z.md`；11 个改动文件已审、无新增问题；隔离副本类型检查、5 用例、构建 PASS；`verify.sh` 因本机缺契约依赖 FAIL（验证缺口）；`docs/handoffs/codex-review-18.md` |
| REVIEW-19 | DONE（B03/B04 固定提交审查；集成与旧范围待审） | B03 `8153186`、B04 `225f102` 与共用准备 `9dddcb4` | Codex | `docs/reviews/codex-claude-b03-b04-2026-09-24-0605z.md`；B03-R01、B04-R01 两项 P2；两隔离副本类型检查、定向/全量测试、构建 PASS；`verify.sh` 缺契约依赖 FAIL；`docs/handoffs/codex-review-19.md` |
| REVIEW-20 | DONE（仅 B10 固定提交；B13 与旧范围待审） | B10 `3771ae1` 任务快照、SSE 与票据契约 | Codex | `docs/reviews/codex-claude-b10-3771ae1-2026-09-24-0703z.md`；B10-R01/R02 两项 P2；隔离副本 36 用例与生成物一致性 PASS；`docs/handoffs/codex-review-20.md` |
| REVIEW-21 | DONE（仅 B13 固定提交；发现 2 项 P2） | B13 `14d405d` 问答与事件契约 | Codex | `docs/reviews/codex-claude-b13-14d405d-2026-09-24-1104z.md`；B13-R01/R02；隔离副本 B13 43 用例和 `verify.sh` PASS；`docs/handoffs/codex-review-21.md` |
| REVIEW-22 | DONE（仅 B10 修正固定提交；集成与旧范围待审） | B10 `21de627` 的 R01～R04 契约修正 | Codex | `docs/reviews/codex-claude-b10-fix-21de627-2026-09-24-1556z.md`；旧 B10-R01/R02 在 JSON Schema 层关闭，新增 B10F-R01 P2、B10F-R02 P3；隔离副本 B10 45 用例 PASS，完整门禁最终输出 PASS 但退出码因中断未确认；`docs/handoffs/codex-review-22.md` |
| REVIEW-23 | DONE（仅 A08 修复固定提交；集成与旧范围待审） | A08 `445478e..2f2e4ce` 同值进度写入与任务板修复 | Codex | `docs/reviews/codex-claude-a08-fix-2f2e4ce-2026-09-24-1603z.md`；A08S-R01/R02 文档层关闭、无新问题；目标 `./scripts/verify.sh` 与 diff check PASS；`docs/handoffs/codex-review-23.md` |
| REVIEW-24 | DONE（仅 D02 固定提交；其他新 worktree 与集成待审） | D02 `588d00a..4651700` TXT 解析器三文件 | Codex | `docs/reviews/codex-claude-d02-4651700-2026-09-25-0403z.md`；D02-R01 P2；目标两次稳定，定向 94 PASS，控制字节反例复现，diff check PASS；`docs/handoffs/codex-review-24.md` |
| REVIEW-25 | DONE（仅 C05 固定提交；C06/C07 与集成待审） | C05 `68affa8..d3b7a6c` 文件落盘边界三文件 | Codex | `docs/reviews/codex-claude-c05-d3b7a6c-2026-09-25-0502z.md`；本批无新增问题；两次指纹稳定，定向 61 PASS，diff check PASS；`docs/handoffs/codex-review-25.md` |
| REVIEW-26 | DONE（仅 D01 固定提交；其他新 worktree 与集成待审） | D01 `909ce33..74be60d` 解析模型与 fixture 十文件 | Codex | `docs/reviews/codex-claude-d01-74be60d-2026-09-25-0503z.md`；D01-R01 P3；目标两次稳定，定向 88 PASS，Anaconda 环境完整门禁 PASS，末尾换行反例复现；`docs/handoffs/codex-review-26.md` |

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
| A10 | DONE（ADR-016 已签收） | 整理已有成果导入顺序与任务映射 | Claude（协调 Agent） | `.claude/worktrees/quirky-dijkstra-eca5de`（分支 `claude/a10-integration-map`）/ base `6881ffe` | `docs/reviews/branch-integration-map.md`（新建）、本节与 PLAN-D04 行、`docs/handoffs/claude-a10.md`；**范围扩展**：`docs/decisions.md`（新增 ADR-016 + ADR-004 指针一行，AGENTS.md §6 要求已确认选择入 ADR）、「待确认决策」新增 D-08 行（ID-4 的决定） | `docs/decisions.md` ADR-016；`docs/reviews/branch-integration-map.md`：92 个文件逐一处置（导入 56、待决 13、不导入 12、随任务导入 6、逐段合并 3、部分导入 2），批 0～6 各一个功能边界，15 项待签收决定各有签收人，任务编号与清单缺口映射；`740adb` 副本补齐生成物后门禁 exit 0，批 1 叠到 main 副本上 exit 1（原因与修法见第 3 节）；`check_a10.py` ALL PASS，8 个负例均 exit 1；`./scripts/verify.sh` exit 0、`git diff --check` exit 0；`docs/handoffs/claude-a10.md` |

- A10 的决定（ArvinHan 2026-09-23 签收，ADR-016）：以 main 为集成基线，不对 `740adb` 做 `git merge`，按批检出文件、每批一个 PR；先合在途 PR #16、#14、#15，再按批 0～6 推进。批 1（契约真源）须先签 N1（文本块标签），并同时调整命名门禁与测试夹具；批 5（ADR 拆分与命名基线）须先签 S03-1 与 N1～N4；批 6 须先签 PLAN-D05。
- A10 交出的后续项（均未认领）：批 0～6 的执行；原子清单缺口 G-1～G-6（登录与成员管理、重新向量化命令、消融实验、参赛材料与合规等）在批 0 补登编号；D-08 已写入「待确认决策」。命名按 ADR-016 决定 6：`Chunk`、`Document`、`model_calls`、`GraphVersion`，问答记录名交 A09。ADR-015 留给 A09。

| 原子 ID | 状态 | 任务 | 负责人 | 目标 worktree / base HEAD | 文件锁（本轮唯一写入者） | 证据 |
| --- | --- | --- | --- | --- | --- | --- |
| A04-R01/R02 修复 | DONE（ADR-012 修订 1 已签收） | 修复 Codex 审查 A04-R01（历史版本只按 `material_id` 过滤会检索到后来的文本块）与 A04-R02（换向量模型后幂等发布与回滚规则冲突） | Claude（协调 Agent） | `.claude/worktrees/a04-f5f479`（分支 `claude/a04-r01-r02-fix`）/ base `0630664` | `specs/teacher-review-publish.md`、`docs/decisions.md`（ADR-012 修订 1）、`docs/architecture.md`、`docs/tasks.md`、`docs/handoffs/claude-a04.md`；**范围扩展**：`specs/task-processing.md` §8.4 `parsing` 行与 §8.6 删除规则（块 ID 与删除保护，A06 条文）、`docs/integrations.md` 两处「重新向量化」（A07 条文） | 规格 V2/V3/V5/V6/V8/V10 修订、新增 V12 与 PUB-28～34；ADR-012 修订 1（决定 9～12）；A06 §8.4/§8.6 与 A07 两处已改并加注；核对脚本 55 项 ALL PASS，三个篡改副本 exit 1；`./scripts/verify.sh` exit 0、`git diff --cached --check` exit 0；`docs/handoffs/claude-a04.md` 第十节 |

- A04-R01/R02 的修复（ArvinHan 2026-09-23 签收，ADR-012 修订 1）：文本块按资料修订（资料 + 内容哈希 + 解析器版本）生成 ID 且不可变，快照固定修订列表，检索按 `revision_id` 过滤；失败任务的来源块加删除保护；运行时只有一个向量空间，换模型须停机离线重新向量化全部文本块、草稿与已提交版本，配置与记录不一致即拒绝启动。
- 交出的后续项（均未认领）：**A10** 在清单中为「重新向量化命令」补登叶子任务；**C06/C07** 定义「下线旧资料修订」；**B06/D09/D10/C09/D11/E07/F03** 按 ADR-012 修订 1 的实现依赖落实。

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
| A08 | DONE（ADR-014 及修订 1 已签收；PR #19 `f9dfc8f`） | 定义推荐评分与进度跨版本规则 | Codex | `.claude/worktrees/codex-a08-learning-path`（`codex/a08-learning-path`）/ base `1a47eb2` | `specs/learning-path.md`、`docs/atomic-task-plan.md` B12/I05 行、`docs/atomic-tasks.json` B12/I05 `acceptance`、本任务行及下方说明、`docs/handoffs/codex-a08.md` | `specs/learning-path.md` LP-1～19；R11～R14 第 3 轮复审通过（PR #17 `acb257c`）；修复映射与验证见 `docs/handoffs/codex-a08.md`；未改 `src/contracts/` |

- A08 行的历史基线：PR #19 合入时，§7 的参数、进度接口字段与 ADR-014 两项细则仍待签收，R15 未修订。这些均已由下方「A08 签收」行（ADR-014 修订 1）签收，现行规则以该行与 `specs/learning-path.md` 为准，本段不再列待决项。当前依赖：**ADR-012** 的下一次修订（快照节点 `merged_from` 与版本提交序号，A04 负责）、**B12** 在 YAML 真源落地 `ProgressEntry` 字段、**C01/I01** 为进度行增加写入序号。

| 原子 ID | 状态 | 任务 | 负责人 | 目标 worktree / base HEAD | 文件锁（本轮唯一写入者） | 证据 |
| --- | --- | --- | --- | --- | --- | --- |
| A08 签收 | DONE（ADR-014 修订 1 及 A08S-R01 补注已签收） | 签收 A08 §7 的参数与进度接口字段，以及 ADR-014 的两项细则 | Claude（协调 Agent） | `.claude/worktrees/codex-a08-check-0ae6d7`（分支 `claude/a08-signoff`）/ base `f9dfc8f` | `docs/decisions.md`（ADR-014 修订 1）、`specs/learning-path.md`（§1、§3、§5、§6、§7）、`docs/integrations.md`（学习推荐权重、启动校验）、`.env.example`、本任务行、`docs/handoffs/claude-sign-a08.md` | `docs/decisions.md` ADR-014 修订 1（决定 5～10）；`specs/learning-path.md` LP-1～20；`docs/handoffs/claude-sign-a08.md`；`./scripts/verify.sh` exit 0、`git diff --check` exit 0 |

- A08 签收的决定（ArvinHan 2026-09-23，ADR-014 修订 1）：
  - 缺失属性取 0.5；
  - 权重来自四个 `RECOMMEND_WEIGHT_*` 环境变量，缺省为 S2 值，只设一部分则拒绝启动，不做课程级配置；
  - 推荐上限默认 10、最大 50；
  - 进度接口返回 V 中全部节点，带有效 `status`、`own_status`、`inherited_from[]`、可空 `updated_at`；
  - 细则 1：主节点的显式写入以来源“本次连续归属”的起算版本为界，覆盖来源；
  - 细则 2：谱系作为发布快照节点的 `merged_from` 字段保存。
- 交出的后续项（均未认领）：
  - **A04（ADR-012 下一次修订）**：快照节点增加 `merged_from` 并纳入摘要，版本提交事务取共享序列的提交序号。**已由 ADR-012 修订 3 完成（2026-09-24 签收，PR #179）。**须先于 F10/B11/G04/G06/I01 完成；#16 正在做 ADR-012 修订 2，本项编号排在其后。
  - **B12**：`ProgressEntry` 新字段、GET/PUT 返回全部节点。
  - **C01/I01**：进度行增加写入序号。
  - **I04**：启动时读取并校验权重。
  - **F10**：合并时写入谱系。
- Codex REVIEW-14 修复（A1～A10 收尾，Claude）：**A08S-R01** 同值写入不能只凭原始值相同跳过，按提交时最终绑定版本上是否仍有未被覆盖的来源判定，LP-16/LP-18 补回归，ADR-014 修订 1 决定 9 加补注（ArvinHan 2026-09-24 签收）；**A08S-R02** A08 行说明段改为历史基线并列出当前依赖。审查报告 `docs/reviews/codex-claude-a08-signoff-f9dfc8f-2026-09-24-0123z.md`（主目录）；验证见 `docs/handoffs/claude-sign-a08.md`「第二轮」。

| 原子 ID | 状态 | 任务 | 负责人 | 目标 worktree / base HEAD | 文件锁（本轮唯一写入者） | 证据 |
| --- | --- | --- | --- | --- | --- | --- |
| FIX-R01/R02 修复 | DONE（ADR-011 修订 3、ADR-012 修订 2 已签收） | 修复 Codex REVIEW-09 的 FIX-R01（响应无 usage 时按 0 计费）与 FIX-R02（向量迁移目标集合与单一空间不变式不一致） | Claude（协调 Agent） | `.claude/worktrees/quirky-dijkstra-eca5de`（分支 `claude/fix-r01-r02`）/ base `1a47eb2` | `docs/integrations.md`（预算、调用记录、模型版本与向量空间、D-02a/b）、`specs/task-processing.md`（§8.4「计费不重复」、LEASE）、`specs/teacher-review-publish.md`（V10、V11、V12）、`docs/decisions.md`（ADR-011 修订 3、ADR-012 修订 2）、`docs/architecture.md`（向量空间一行）、本节、`docs/handoffs/claude-a07.md`、`docs/handoffs/claude-a04.md` | 审查报告 `docs/reviews/codex-claude-a04-fixes-1012b6f-2026-09-23-1215z.md`（主目录）；`docs/integrations.md`「预算」「调用记录」第 5 条；LEASE-28～30；V12 第 3/4/6 步与「空间标识随向量走」、PUB-36～38；ADR-011 修订 3、ADR-012 修订 2；`check_fix.py` 修改前 38 FAIL，修改后 40 项 ALL PASS，6 个负例均 exit 1；`check_a07` 347/347、`check_a07r01`、`check_a06` ALL PASS，`check_a04` 除修改前就存在的 2 项过时断言外，仅新增 1 项脚本边界问题（修订 1 之后多了修订 2，见交接）；`./scripts/verify.sh` exit 0、`git diff --check` exit 0；`docs/handoffs/claude-a07.md` 第十节、`docs/handoffs/claude-a04.md` 第十一节 |

- FIX-R01/R02 的修复（ArvinHan 2026-09-23 签收，ADR-011 修订 3、ADR-012 修订 2）：响应不带 usage 时，生成前被拒的错误（`400/401/403/404/413/422/429`）计 0，其余情形按「输入估算 + 输出上限」计，E03 流式请求须请求 usage；重新向量化按 Neo4j 实际存量迁移并按存量核对，缓存与节点外的向量带空间标识，写入按空间标识而非维度拒绝。
- 交出的后续项（均未认领）：**E03** 错误分类含「生成前被拒」、流式请求 usage；**E04** 按修订 3 汇总计费量；**D-02a/b** 签收时注明供应商是否返回 usage；**E07** 缓存键含空间标识；**F03** 写入向量核对空间标识；**A10** 仍须为重新向量化命令补登叶子任务。

| 原子 ID | 状态 | 任务 | 负责人 | 目标 worktree / base HEAD | 文件锁（本轮唯一写入者） | 证据 |
| --- | --- | --- | --- | --- | --- | --- |
| FIX-R03 修复 | DONE（ADR-012 修订 2 补注已签收） | 修复 Codex REVIEW-10 的 FIX-R03（离线迁移写新空间与「只能写当前空间」冲突），并把 `origin/main` 合入本分支解除 PR #16 冲突 | Claude（协调 Agent，A1～A10 收尾） | `.claude/worktrees/wrap-fix-pr16`（分支 `claude/fix-r01-r02`）/ base `5186e09` + 合入 `f9dfc8f` | `specs/teacher-review-publish.md`（V12 第 3 步、「空间标识随向量走」、PUB-39）、`docs/integrations.md`（写入核对一处）、`docs/architecture.md`（向量空间一行）、`docs/decisions.md`（ADR-012 修订 2 补注）、本节、`docs/handoffs/claude-a04.md` 第十二节 | 审查报告 `docs/reviews/codex-claude-fix-r01-r02-5186e09-2026-09-23-1252z.md`（主目录）；`check_fixr03.py` 修改前 13 FAIL、修改后 ALL PASS，负例见交接；`./scripts/verify.sh`、`git diff --check` 结果见 `docs/handoffs/claude-a04.md` 第十二节 |

- FIX-R03 的修复：空间标识按写入上下文核对。运行时写入只接受当前空间，没有绕过参数；只有重新向量化命令在自己的进程内持有迁移上下文，第 3 步只写本次目标空间、不动旧空间，第 5 步提交后失效。不改变 ADR-012 修订 2 已签收的方向。补注由 ArvinHan 2026-09-24 签收。
- 交出的后续项（均未认领）：**F03** 写入接口区分运行时与迁移两种上下文并实现 PUB-39；**重新向量化命令**（A10 批 0 补登的叶子任务）建立并持有迁移上下文。

| 原子 ID | 状态 | 任务 | 负责人 | 目标 worktree / base HEAD | 文件锁（本轮唯一写入者） | 证据 |
| --- | --- | --- | --- | --- | --- | --- |
| A09 | DONE（ADR-015 已签收） | 定义问答终态和引用撤回协议 | Claude（协调 Agent） | `.claude/worktrees/a09-dev-environment-check-8e5e93`（分支 `claude/a09-dev-environment-check-8e5e93`）/ base `f9dfc8f` | `specs/grounded-qa.md`（main 新建，以 `740adb` `978671e` 草稿桩为底稿）；**范围扩展（用户同意）**：`docs/decisions.md`（新增 ADR-015）、`docs/architecture.md`（问答 SSE 行、`NotCoveredReason` 行加注、用语映射一行）、本节、`docs/handoffs/claude-a09.md` | `specs/grounded-qa.md`「问答终态与引用撤回协议」Q1～Q12（终态矩阵 O1～O15、QA-1～35：成功 5 / 边界 18 / 失败 12）；`docs/decisions.md` ADR-015（ArvinHan 2026-09-23 签收）；`docs/architecture.md` 三处加注与 `ChatLog` 定名；核对脚本 45 项 ALL PASS（对 `740adb` `978671e` 真源、IAM 矩阵、A07 切换矩阵、ADR-012 V8 与原子清单），19 个篡改副本均被对应检查项检出（exit 1、无崩溃）；流内状态机参考模型 19/19 PASS（每例 200 种随机分块结果一致，仅作验证、不入库）；`./scripts/verify.sh` exit 0、`git diff --check` exit 0；`docs/handoffs/claude-a09.md` |

- A09 的决定（ArvinHan 2026-09-23 在会话中逐项选定、四节设计逐节确认，ADR-015 同日签收）：检索与阈值判定之后才开流，开流前失败为 HTTP 错误，开流后为 `meta delta* (done | error)`；服务端流内逐引用校验，`answered` 时最终正文恒等于 delta 拼接；模型以 `<<INSUFFICIENT_EVIDENCE>>` 开头声明证据不足，`out_of_course_scope` 改名 `insufficient_evidence`；除 `done` + `answered` 外一律撤回临时正文、不自动重试；输出截断按正常结束判定；历史只用于改写、生成不见历史；回答钉在绑定版本、不追溯撤回；问答记录定名 `ChatLog` / `chat_logs`（关闭 A10 N5）。
- 交出的后续项（均未认领）：**B13** 改 `NotCoveredReason`，`meta` 与 `final` 加 `graph_version`、`request_id`，定 `details.reason` 闭集，`events.v1.md` §3 指向本规格；**B08** 落实 `STORAGE_UNAVAILABLE`、`INTERNAL_ERROR`、`BUDGET_EXCEEDED`，改 `RATE_LIMITED` 措辞；**J03～J10、K03** 按规格 Q11 实现（J06 与 J09 共用代码片段夹具）；**A10** 用本规格替换分支桩，并把它加回批 1 门禁扫描清单。

| 原子 ID | 状态 | 任务 | 负责人 | 目标 worktree / base HEAD | 文件锁（本轮唯一写入者） | 证据 |
| --- | --- | --- | --- | --- | --- | --- |
| A09-R01/R02 修复 | DONE（ADR-015 修订 1 已签收） | 修复 Codex REVIEW-12 的 A09-R01（一个有效引用即可让无出处的结论成为 `answered`）与 A09-R02（每请求一条日志与鉴权前置顺序冲突） | Claude（协调 Agent，A1～A10 收尾） | `.claude/worktrees/a09-dev-environment-check-8e5e93`（分支 `claude/a09-dev-environment-check-8e5e93`）/ base `1754c96` | `specs/grounded-qa.md`、`docs/decisions.md`（ADR-015 修订 1）、`docs/architecture.md`（`ChatLog` 一处）、本节、`docs/handoffs/claude-a09.md` 第九节 | 审查报告 `docs/reviews/codex-claude-a09-1754c96-2026-09-23-1400z.md`（主目录）；Q3.5、I3、QA-36～38；核对脚本修改前 27 FAIL、修改后 ALL PASS，负例见交接；`./scripts/verify.sh`、`git diff --check` 结果见 `docs/handoffs/claude-a09.md` 第九节 |

- A09-R01/R02 的修复（ArvinHan 2026-09-24 选定方向并签收条文，ADR-015 修订 1）：每个结论单元（句）都须带有效引用，否则整段撤回为 `not_covered` / `all_citations_invalidated`（日志子类 `uncited_sentence`），wire 枚举不变；语义支持度只在 K03 评测中衡量。`chat_logs` 只记通过 P2 的请求，四个必填字段非空；P1/P2 拒绝只写应用日志。
- 交出的后续项（均未认领）：**J05** 提示要求逐句标注；**J06** 实现 Q3.5；**J10** 按新覆盖范围建表；**K03** 统计 `uncited_sentence` 撤回率；**C03/J07** 的统一错误处理写应用日志。

| 原子 ID | 状态 | 任务 | 负责人 | 目标 worktree / base HEAD | 文件锁（本轮唯一写入者） | 证据 |
| --- | --- | --- | --- | --- | --- | --- |
| A10-R01/R02 修复 | DONE（ADR-016 修订 1 已签收） | 修复 Codex REVIEW-13 的 A10-R01（批 1 把已合入的学习路径规格移出命名门禁）与 A10-R02（批 5 拟原样导入与现行状态机相反的 ADR-005/006） | Claude（协调 Agent，A1～A10 收尾） | `.claude/worktrees/wrap-a10-fix`（分支 `claude/a10-r01-r02-fix`）/ base `37da669`（PR #18） | `docs/reviews/branch-integration-map.md`（第 3 节批 1/5、第 4 节 ADR-005/006、第 7 节风险 2/6）、`docs/decisions.md`（ADR-016 修订 1）、本节、`docs/handoffs/claude-a10.md` 第十节 | 审查报告 `docs/reviews/codex-claude-a10-37da669-2026-09-23-1403z.md`（主目录）；核对脚本修改前 10 FAIL、修改后 ALL PASS，负例与 `check_a10.py` 回归见交接；`./scripts/verify.sh`、`git diff --check` 结果见 `docs/handoffs/claude-a10.md` 第十节 |

- A10-R01/R02 的修复（ADR-016 修订 1，ArvinHan 2026-09-24 签收）：批 1 的扫描集合按执行时 main 中已存在的规格确定，`learning-path.md` 保留，`grounded-qa.md` 待 A09 合入后加回并补负例；ADR-005/006 在批 5 以 SUPERSEDED 历史记录导入，不得作现行依据。
- 交出的后续项（均未认领）：**批 1 补**（后端 Agent）：A09 合入后把 `specs/grounded-qa.md` 加回 `scripts/check_contracts.py` 扫描清单与 `tests/contracts/test_contracts.py` 夹具，并加该文件的错误命名负例；**批 5**（协调 Agent）按修订 1 导入 ADR-005/006。

## A10 批 0：规划文档对齐

| 原子 ID | 状态 | 任务 | 负责人 | 目标分支 / base | 文件锁 | 验收证据 |
| --- | --- | --- | --- | --- | --- | --- |
| A10-批0 | DONE（本地，待审查） | 按 ADR-016 更新契约任务白名单并补齐 G-1～G-6 清单缺口 | Codex（协调） | `codex/a10-batch0` / A10 `37da669`，已合入 `origin/main@f9dfc8f` | `docs/atomic-task-plan.md`、`docs/atomic-tasks.json`、`docs/reviews/validate_atomic_plan.py`、本任务板、`docs/handoffs/codex-a10-batch0.md` | 140 项清单校验 PASS；无环、路径与链接检查 PASS；基础 verify PASS；负例（缺依赖）被拒；`docs/handoffs/codex-a10-batch0.md` |

- 输入：A10/ADR-016 的导入映射第 3 节批 0 与第 6 节 G-1～G-6；ADR-004 YAML 真源裁定；A05/ADR-013 身份与票据规则。
- 输出：B08～B14、O02、O05 的 YAML 真源与生成物白名单；新增 C13～C16、F14、H12、K13～K19 共 13 个叶子任务；验证器动态计数并可在当前 checkout 运行。
- 依赖：A10 决定已签收；批 1 必须在批 0 验收后开始。
- 风险：A10 本身尚未进入远端 `main`；本轮只在独立分支工作，不改动 B02/B06 工作区。新增任务均为计划，未声称实现。
- 验证：`python docs/reviews/validate_atomic_plan.py`、负例、`./scripts/verify.sh`、`git diff --check`。

## A10 批 1：契约真源与生成链

| 原子 ID | 状态 | 任务 | 负责人 | 目标分支 / base | 文件锁 | 验收证据 |
| --- | --- | --- | --- | --- | --- | --- |
| A10-批1 / M0-09 第二步 | DONE（本地，待 PR 与 CI） | 按 ADR-016 导入 OpenAPI 真源、生成类型、契约门禁及 CI 工具链 | Codex（后端） | `codex/a10-batch1` / `codex/a10-batch0@c795741` | `src/contracts/**`、`scripts/{gen-contracts.sh,gen_contracts.py,check_contracts.py,verify.sh,verify/contracts.sh}`、`tests/contracts/**`、`.github/workflows/ci.yml`、`.gitattributes`、命名相关架构/规格/计划段、本任务板与交接 | `docs/handoffs/codex-a10-batch1.md`；`gen-contracts.sh --check`、22 项契约负例、`verify.sh`、计划校验、生成模型导入与 `pip check` 均通过；远端 CI 待 PR |

- 输入：A10 [导入映射](reviews/branch-integration-map.md) 第 3 节批 1、ADR-004/009/010/016、来源分支 `claude/worktree-contract-conflicts-740adb@978671e`。
- 输出：`api.v1.yaml`、配套语义文档、完整 Python/TypeScript/JSON 生成物、严格契约校验及 CI 安装步骤；N1 的 `Chunk` 命名同步到架构、A04 规格、D10 计划。
- 依赖与风险：批 0 已在本地提交；A10 与前置 PR 仍未全部进入 `main`，本批不能直接合入主线。`events.v1.md` §2 的旧状态机叙述留给 B10 迁移，已在文首标明现行规范的优先级。远端 CI 尚未运行。
- 验证命令：`./scripts/gen-contracts.sh --check`、`./scripts/verify.sh`、`python docs/reviews/validate_atomic_plan.py`、生成模型导入、`python -m pip check`、`git diff --check`；具体结果与回滚见交接。

## A1～A10 收尾（2026-09-24）

> 盘点基线 `origin/main@f9dfc8f`；合并后基线 `origin/main@2819701`。本节只登记状态与去向，不代替各 PR 自己的任务行。

| 原子 ID | 决定 | 合入 main | Codex 审查意见 | 余项 |
| --- | --- | --- | --- | --- |
| A01 | ADR-004 已签收 | PR #1 | 无未决 | — |
| A02 | ADR-009 已签收 | PR #2 | **A02-R01**（P2）：YAML 真源 `Relation.required` 未含 `status`、`source`、`source_refs`，与规格「关系至少含」不一致 | 交 **B11**（见下） |
| A03 | ADR-010 已签收 | PR #5（含 A03-R01/R02 修复） | 无未决 | — |
| A04 | ADR-012 及修订 1、修订 2（含补注）已签收 | PR #7、#10、#16 | FIX-R02、FIX-R03 已修 | 待 Codex 复核 FIX-R03（`970c582`） |
| A05 | ADR-013 已签收 | PR #9 | 无未决 | — |
| A06 | ADR-011 及修订 1 已签收 | PR #6、#11 | 无未决 | — |
| A07 | 形状已定；ADR-011 修订 2、3 已签收 | PR #8、#12、#16 | A07-R01、FIX-R01 已修 | 取值待 D-02a～f |
| A08 | ADR-014 及修订 1（含决定 9 补注）已签收 | PR #19、#23 | A08S-R01/R02 已修 | 待 Codex 复核（`39633fe`） |
| A09 | ADR-015 及修订 1 已签收 | PR #20 | A09-R01/R02 已修 | 待 Codex 复核（`097f248`） |
| A10 | ADR-016 及修订 1 已签收 | PR #18、#24；批 0/1 为 PR #22 | A10-R01/R02 已修 | 待 Codex 复核（`fae2212`）；批 2～6 未执行 |

- **合并记录**：2026-09-24 由 Claude 按 ArvinHan 在会话中的明确指示依次合并 #16 → #23 → #20 → #18 → #24 → #22（ADR-016 规定由 ArvinHan 合并，本次为其授权的代执行）。每个 PR 合并前先同步 main、解决文末追加冲突，本地 `./scripts/verify.sh` 与 `git diff --check` 通过，且 CI 在新的头提交上成功后才合并；#22 合并前本地运行了含契约门禁（22 项负向测试）的完整 `verify.sh`，exit 0。
- **四处补注**已由 ArvinHan 于 2026-09-24 签收：ADR-012 修订 2 补注、ADR-014 修订 1 决定 9 补注、ADR-015 修订 1、ADR-016 修订 1。
- **A 组关闭条件**：仅剩 Codex 复核上表四个修复提交，无新的 P1/P2 即关闭。A 组没有未认领的原子任务。
- **仍开放、但不阻塞 A 组关闭的决定**：D-01（示例课程资料）、D-02a～f（模型供应商与预算取值）、PLAN-D05（学习材料分支）、D-08（A10 登记）。

| 原子 ID | 状态 | 任务 | 负责人 | 目标 worktree / base HEAD | 文件锁（本轮唯一写入者） | 证据 |
| --- | --- | --- | --- | --- | --- | --- |
| A1～A10 收尾 | DONE（修复已合入、四处补注已签收；待 Codex 复核） | 盘点 A01～A10，修复 Codex 未决意见 FIX-R03、A08S-R01/R02、A09-R01/R02、A10-R01/R02，按授权依次合并 PR，登记 A02-R01 去向 | Claude（协调 Agent） | `.claude/worktrees/a1-a10-meta-task-wrap-ddbf4b`（分支 `claude/a1-a10-meta-task-wrap-ddbf4b`）/ base `f9dfc8f`，合并后同步 `2819701` | 本节、`docs/handoffs/claude-a1-a10-wrap.md`；各修复的文件锁见对应任务行 | `docs/handoffs/claude-a1-a10-wrap.md`；各修复的核对脚本先红后绿、篡改负例全部检出；合并后 main 上 `./scripts/verify.sh` exit 0 |

- **A02-R01 → B11**（已由 B11 完成，PR #194 `2de97ba`）：在 `src/contracts/api.v1.yaml` 把 `status`、`source`、`source_refs` 加入 `Relation.required`（若允许空来源，须写明适用场景并与 `specs/course-knowledge-graph.md` 对齐），重新生成并加「缺任一字段即拒绝」的 schema 负例；`RelationCreate` 仍可由服务端补齐这三个字段。契约真源已随 PR #22 进入 main，可以开始。审查报告：主目录 `docs/reviews/codex-claude-a02-hook01-2026-09-23-0528z.md`。
- **批 1 补**（未认领，后端 Agent）：A09 已合入，现可把 `specs/grounded-qa.md` 加回 `scripts/check_contracts.py` 扫描清单与 `tests/contracts/test_contracts.py` 夹具，并加该文件的错误命名负例（ADR-016 修订 1）。
- Codex 在主目录未入库的审查记录（REVIEW-03～26 的任务行、`docs/reviews/codex-claude-*.md` 报告 24 份、`docs/handoffs/codex-review-*.md` 交接 24 份与 `claude-review-state.json`）已于 2026-09-25 经 ArvinHan 同意由 Claude 原样代为入库（见 `docs/handoffs/claude-archive-codex-reviews.md`）；各交接中「主目录 `docs/reviews/…`」的引用现在按仓库内同名路径解析。

## A10 批 1 补：问答规格加回契约门禁

| 原子 ID | 状态 | 任务 | 负责人 | 目标 worktree / base HEAD | 文件锁（本轮唯一写入者） | 证据 |
| --- | --- | --- | --- | --- | --- | --- |
| A10-批1补 | DONE | 把 `specs/grounded-qa.md` 加回契约命名门禁的扫描清单与测试夹具，并为每份被扫描的规格加错误命名负例（ADR-016 修订 1） | Claude（后端 Agent） | `.claude/worktrees/batch1-qa`（分支 `claude/batch1-grounded-qa`）/ base `548c4f8` | `scripts/check_contracts.py`（`NAMING_DRIFT_DOCS`）、`tests/contracts/test_contracts.py`、本节、`docs/handoffs/claude-a10-batch1-supplement.md` | 新增 `test_alias_in_each_guarded_spec_fails`、`test_guarded_spec_missing_fails`：去掉扫描项时两项均只因 `grounded-qa.md` 失败，加回后通过；契约负向测试 24/24；`./scripts/verify.sh` exit 0（命名基线 10 份文档）；`git diff --check` exit 0；`docs/handoffs/claude-a10-batch1-supplement.md` |

- 输入：ADR-016 修订 1 决定 1；A09 已随 PR #20 合入 main。输出：`specs/grounded-qa.md` 进入命名门禁扫描清单与测试工作区；四份受保护规格（课程图谱、学习路径、教师发布、问答）各有一处 `SourceChunk` 注入负例和一处缺文件负例。测试中的受保护清单独立列出，不从门禁导入，避免同源漏扫。
- 本项关闭 A1～A10 收尾一节登记的「批 1 补」。

## B01 前端构建与单页挂载

| 原子 ID | 状态 | 任务 | 负责人 | 目标分支 / base HEAD | 文件锁（本轮唯一写入者） | 证据 |
| --- | --- | --- | --- | --- | --- | --- |
| B01 | DONE | 初始化 Vue 3 + TypeScript + Vite 构建及单个挂载页面 | Codex（前端） | `codex/b01-vue-scaffold` / base `50a15c9` | `src/frontend/package.json`、`src/frontend/package-lock.json`、`src/frontend/tsconfig.json`、`src/frontend/vite.config.ts`、`src/frontend/index.html`、`src/frontend/src/main.ts`、`src/frontend/src/App.vue`；文档范围：`src/frontend/README.md`、`docs/architecture.md`、本任务板、`docs/handoffs/codex-b01.md` | `npm ci`、`vue-tsc`、Vite build、浏览器挂载烟测、`./scripts/verify.sh` 均通过；见 `docs/handoffs/codex-b01.md` |

- 输入：A01 已确认的前端技术栈与 `docs/atomic-task-plan.md` B01 验收条件；不新增 REST、SSE 或业务 DTO。
- 输出：锁定依赖的最小 Vue 应用、严格类型检查、可构建产物与单页挂载烟测。
- 依赖：A01 已完成；B02 的测试配置与 B03 的角色路由在本轮范围外。
- 风险：构建工具对 Node 版本有下限；本轮以实际本机版本核验。锁文件和构建产物必须分开，`dist/` 不入库。
- 验证：`npm --prefix src/frontend run type-check`、`npm --prefix src/frontend run build`、浏览器挂载烟测、`./scripts/verify.sh`、`git diff --check`。
- 实际结果：Node 24.16.0 / npm 11.13.0；锁文件重装成功；类型检查与生产构建 exit 0；本地 Vite 页面在浏览器显示标题和挂载内容；基础 verify 与 diff check exit 0。正式测试脚本归 B02。
- Claude 审查（REVIEW-B01，2026-09-23）：无 P1/P2；P3×3（B01-R01～R03）不阻塞。合入 `origin/main@548c4f8` 后在合并结果上重跑 `npm ci`、type-check、build、浏览器挂载烟测与 `./scripts/verify.sh` 均通过；见 `docs/handoffs/claude-review-b01.md`。

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
- Claude 审查（REVIEW-B05，2026-09-24）：无 P1/P2；P3×3（B05-R01～R03）。合入 `origin/main@dddafb3` 后 test_b05 3 passed、uvicorn 实测与契约一致、`verify.sh` 通过；见 `docs/handoffs/claude-review-b05.md`。

## B07 契约门禁缺依赖假绿

| 原子 ID | 状态 | 任务 | 负责人 | 目标 worktree / base HEAD | 文件锁（本轮唯一写入者） | 证据 |
| --- | --- | --- | --- | --- | --- | --- |
| B07 | DONE（PR #187 已合入 `1d3e20c`） | 校验结果显式 PASS/SKIP/FAIL，缺依赖与坏契约失败 | Codex（后端） | `b07-main` / 初始 `origin/main@28b09b4` | `scripts/check_contracts.py`、`scripts/verify/contracts.sh`、`src/backend/pyproject.toml`、`tests/tooling/test_b07.py`；文档 `docs/architecture.md`、本节、`docs/handoffs/codex-b07.md` | 最新主线临时合并副本：B07 14 PASS、全量 620 PASS、`./scripts/verify.sh` exit 0、diff check PASS；PR 六项 CI 全绿；[审查复核](reviews/codex-b07-pr187-2026-09-25.md)；[PR #187](https://github.com/arvinhanye/SmartSketch/pull/187)；`docs/handoffs/codex-b07.md` |

- 输入：R02 审查结论与已导入 main 的契约门禁；输出：一套门禁的显式状态及后端测试依赖声明，不引入第二套校验入口。
- 依赖：A01、B05、C13 已合入；实际合并保留 C13 的 `argon2-cffi==25.1.0` 和 B07 的三项测试依赖。
- 验收：缺依赖、坏 `$ref`、坏关系枚举均非 0；显式骨架降级标为 `SKIP` / `INCOMPLETE`；运行 `python3 -m pytest tests/tooling/test_b07.py -q`、`./scripts/verify.sh`、`git diff --check`。
- 结果：定向 14 项覆盖正常通过、PyYAML/OpenAPI 校验器/JSON Schema 缺依赖、显式骨架跳过、坏引用、坏枚举、畸形结构的显式 FAIL、聚合门禁状态与测试依赖；最新主线临时合并副本全仓 620 项通过，`./scripts/verify.sh` 通过。PR #187 于 2026-09-25 UTC 合入 `main@1d3e20c`。

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
- Claude 审查（REVIEW-B06，2026-09-24）：P2×2 已签收（ArvinHan 2026-09-24，见 `docs/decisions.md`「ADR-012 补注：启动门禁的当前空间记录表与职责拆分」）——**B06-R01** 启动时建 SQLite 表 `embedding_space_state`（超出原子范围的数据模型决定，表名与「C01 接管」约定待签收）；**B06-R02** 修改已签收的 ADR-012 规格两处职责标注。P3×2。同步 main 后补 `RECOMMEND_WEIGHT_*` 四项成组校验（集成修复 `dbfb63d`）；后端 58 passed、启动门禁/密钥脱敏实测通过；见 `docs/handoffs/claude-review-b06.md`。

## B02 前端测试配置

| 原子 ID | 状态 | 任务 | 负责人 | 目标分支 / base HEAD | 文件锁（本轮唯一写入者） | 证据 |
| --- | --- | --- | --- | --- | --- | --- |
| B02 | DONE（REVIEW-18 已审，无问题） | 初始化前端测试配置，使仓库外层 `tests/frontend` 被实际发现 | Claude（前端） | `claude/frontend-dev-04eee7` / base `dddafb3` | `src/frontend/vitest.config.ts`、`src/frontend/package.json`、`src/frontend/package-lock.json`、`tests/frontend/setup.ts`、`tests/frontend/b02.test.ts`；因 B01-R01 需要时扩到 `src/frontend/tsconfig*.json`；文档：`src/frontend/README.md`、`docs/architecture.md`、本任务板、`docs/handoffs/claude-b02.md` | 计划验收命令 exit 0（5 passed）；三处反向篡改（去 setup、`passWithNoTests`、脚本吞退出码）均被检出；类型检查覆盖测试与 Node 侧配置，应用代码不可见 Node 类型；`npm ci`、build、`./scripts/verify.sh`、`git diff --check` 通过；见 `docs/handoffs/claude-b02.md` |

- 输入：B01 已合入的 Vue 3 + Vite 骨架（PR #15）；`docs/atomic-task-plan.md` B02 验收；审查意见 B01-R01（Node 侧配置不得混入浏览器类型）。
- 输出：Vitest 配置与 `test` 脚本；DOM 测试环境与全局 setup；`tests/frontend/b02.test.ts` 同时验证 SFC 挂载、setup 生效，以及「故意失败用例使命令非 0」「零用例不算通过」两条门禁行为。
- 依赖：B01；npm 公共源。无后端、契约或环境变量变化。
- 风险：`tests/frontend` 位于 Vite 根目录外，裸模块解析与类型检查可能找不到 `src/frontend/node_modules`；测试依赖可能抬高 Node 版本下限。
- 验证：`npm --prefix src/frontend run type-check && npm --prefix src/frontend run test -- --run ../../tests/frontend/b02.test.ts`、`./scripts/verify.sh`、`git diff --check`。
- 实际结果：新增 `src/frontend/tsconfig.node.json`（文件锁中预留的扩展，处理 B01-R01）；`engines` 收紧为 `^22.22.2 || ^24.15.0 || >=26.0.0`（Vitest 5 / jsdom 30 下限）；B01-R02 的 README 命令块已改为 `bash`。CI 仍未跑前端命令，归 K11。

## B03 / B04 前端路由壳与课程上下文（并行）

| 原子 ID | 状态 | 任务 | 负责人 | 目标分支 / base HEAD | 文件锁（本轮唯一写入者） | 证据 |
| --- | --- | --- | --- | --- | --- | --- |
| B03/B04 准备 | DONE | 安装 `vue-router@5.3.1`、`pinia@4.0.3`，`main.ts` 接入 Pinia；认领两项任务 | Claude（协调） | `claude/b03-b04-prep` / base `8e5b707`（B02，PR #27 未合） | `src/frontend/package.json`、`package-lock.json`、`src/frontend/src/main.ts`、本任务板 | type-check、B02 测试、build 通过 |
| B03 | DONE（REVIEW-19 已审；B03-R01′ P2 未修，见下方「审查遗留」） | 建立路由壳和角色入口 | Claude（前端子代理） | `claude/b03-router-shell` / base 准备提交 | `src/frontend/src/router/index.ts`、`src/frontend/src/views/TeacherHome.vue`、`src/frontend/src/views/StudentHome.vue`、`tests/frontend/b03.test.ts`；为接线需改 `src/frontend/src/main.ts`（仅加路由）与 `src/frontend/src/App.vue`；`docs/handoffs/claude-b03.md` | 计划验收命令 exit 0（13 passed）；去守卫/去错角色分支/去提示元素三处篡改均被检出；集成后全量 30 passed、build、`verify.sh` 通过；浏览器访问 `/teacher` 落到 `/?notice=unauthenticated` 并显示提示；`docs/handoffs/claude-b03.md` |
| B04 | DONE（REVIEW-19 已审；B04-R01 P2 未修，见下方「审查遗留」） | 建立 Pinia 课程上下文 | Claude（前端子代理） | `claude/b04-course-store` / base 准备提交 | `src/frontend/src/stores/course.ts`、`tests/frontend/b04.test.ts`、`docs/handoffs/claude-b04.md` | 计划验收命令 exit 0（12 passed）；六处篡改（按 courseId 代替代次、不清空、不中止、去幂等、去 course_id 校验、信任 `isCurrent`）均被检出；store 无 fetch/XHR/HTTP 导入；`docs/handoffs/claude-b04.md` |

- 并行约束：B03、B04 的文件锁互不相交；两者都不改 `package.json`、锁文件、`docs/tasks.md`、`docs/architecture.md`，这些由协调方在集成时统一更新。
- 依赖：B02（PR #27 待审查）；B03 另依赖 A05（`specs/identity-access.md` §2.4：路由守卫只用 `user.role` 选首页、`Course.my_role` 选课程视图，仅作界面引导）。
- 风险：原子清单没有前端登录页与会话存储任务（G-1 只列 C13～C16 后端与 H12 成员页），B03 只能以注入方式取得账号类型；缺口在集成时登记。
- 集成：`claude/b03-b04` = 准备提交 + 两个任务分支的 `--no-ff` 合并 + 本次文档更新；两分支文件锁不相交，合并无冲突。
- 协调方审查意见（P3，不阻塞）：**B03-R01** `App.vue` 用 `inject(routeLocationKey, null)` 兼容未装路由的挂载，只为让 B02 两个直接挂载 `App` 的用例不改；产品入口总会装路由。若日后改回 `useRoute()`，同批把 B02 两个挂载用例改为装内存路由。**B04-R01** 图谱/问答槽位对组件仍可直接赋值，绕过作用域校验只靠注释与审查约束；H03/J08 接入时可改为只读暴露。
- 交出的后续项（均未认领）：B15 须把 `scope.signal` 传给 fetch，旧请求才会在网络层真正取消；路由 `cid` 与 `selectCourse` 的接线归 H01；登录页、会话存储与 `getAccountRole` 的真实来源归 H13（D-09）；问答「最新回答与引用」槽位由 J08/J09 决定是否加入并在切课时清空。

## B08 公共错误与来源契约

| 原子 ID | 状态 | 任务 | 负责人 | 目标分支 / base | 文件锁 | 验收证据 |
| --- | --- | --- | --- | --- | --- | --- |
| B08 | DONE（本地，审查问题已修复） | 迁移公共错误和来源契约 | Codex（后端） | `kongsc/b08-contracts` / `codex/a10-batch1@b801553` | `src/contracts/api.v1.yaml`、`src/contracts/errors.v1.md`、生成物、`tests/contracts/test_b08.py`、`scripts/verify/contracts.sh`、相关规格与架构、本任务板、`docs/handoffs/codex-b08.md` | `tests/contracts/test_b08.py` 5 passed；`./scripts/verify.sh` exit 0（含 22 项契约负例及 B08 回归）；`./scripts/gen-contracts.sh --check` PASS；`docs/handoffs/codex-b08.md` |

- 输入：A10 批 1 的 OpenAPI 真源、ADR-010/011/012 与 A07 已确认的错误语义。
- 输出：公共错误码闭集、同步与异步失败语义、已有 SourceRef 定位及四类关系约束的回归测试、更新的生成物。
- 依赖：A10 批 1 已完成；B05 后端运行时尚未进入本基线，B08 只改契约。
- 风险：新增枚举值需下游按未知码兜底；BUDGET_EXCEEDED 的 HTTP 状态由本任务定为 429，并在共享 429 响应中与可重试的 RATE_LIMITED 区分。
- 验证：`python -m pytest tests/contracts/test_b08.py -q`、`./scripts/gen-contracts.sh --check`、`./scripts/verify.sh`、`git diff --check`。

## B09 课程与资料 REST 契约

| 原子 ID | 状态 | 任务 | 负责人 | 目标分支 / base | 文件锁 | 验收证据 |
| --- | --- | --- | --- | --- | --- | --- |
| B09 | DONE（GitHub CI 已验证） | 迁移课程与资料 REST 契约 | Codex（后端） | `kongsc/b09-contracts` / `kongsc/b08-contracts@21253f8`，已纳入 `15dacce` | `src/contracts/api.v1.yaml`、生成物、`tests/contracts/test_b09.py`、`scripts/verify/contracts.sh`、`.github/workflows/ci.yml`、`src/contracts/toolchain.txt`；文档为身份规格、任务板与 `docs/handoffs/codex-b09.md` | B09/B08 专项 9 passed；GitHub Actions [run 35944829534](https://github.com/arvinhanye/SmartSketch/actions/runs/35944829534) 的 `./scripts/verify.sh` 通过（B08 5 项、B09 4 项）；`./scripts/gen-contracts.sh --check` PASS；`docs/handoffs/codex-b09.md` |

- 输入：现有课程/资料 OpenAPI 路径、ADR-013 与 `specs/identity-access.md` §3～§7。
- 输出：带课程内角色的 Course、成员管理 DTO 与 REST 操作、课程列表可见性及现有资料接口的错误响应契约。
- 依赖：B08、A05 已完成；B09 分支已纳入 B08 审查修复 `15dacce`，不修改 B05 运行时文件。
- 风险：B09 只定义协议，成员权限和课程过滤须由后续 C03/C04/C15 实现；当前基线 A10 批 1 尚待集成。
- 验证：`python -m pytest tests/contracts/test_b09.py -q`、`./scripts/gen-contracts.sh --check`、`./scripts/verify.sh`、`git diff --check`。
- CI 修复（2026-09-24）：首次 GitHub 运行因 Python 环境未安装 `pytest` 报 `No module named pytest`；`aa1c3e9` 将 `pytest==8.3.5` 加入工作流依赖和工具链清单，随后 GitHub Actions run 35944829534 通过。
- Claude 审查（REVIEW-B08-B09，2026-09-24）：审查通过；同步 main 后修正 B09-R01（`getCourse` 404 描述与 identity-access §4.1 冲突，先加测试再改并重新生成）；`verify.sh` 通过（B08 5、B09 5）；见 `docs/handoffs/claude-review-b08-b09.md`。自 2026-09-24 起后端由 ArvinHan 接手，B10 起的后端任务负责人记为 ArvinHan（Claude 执行）。

## B10 任务与 SSE 契约

| 原子 ID | 状态 | 任务 | 负责人 | 目标分支 / base HEAD | 文件锁（本轮唯一写入者） | 证据 |
| --- | --- | --- | --- | --- | --- | --- |
| B10 | DONE（REVIEW-20 两项已在 `21de627` 修复；REVIEW-22 的 B10F-R01 P2、B10F-R02 P3 未修，见下方「审查遗留」） | 迁移任务与 SSE 契约 | ArvinHan（Claude 执行） | `claude/b10-task-sse-contract` / base `9d2437e` | `src/contracts/api.v1.yaml`、`src/contracts/events.v1.md`、`src/contracts/v1/generated/`、`tests/contracts/test_b10.py`；按 B08/B09 先例接入 `scripts/verify/contracts.sh`；随附状态标注：`specs/task-processing.md` §9、`specs/identity-access.md` §7、`src/contracts/README.md`、`docs/handoffs/claude-b10.md` | `test_b10.py` 先 27 failed 后 36 passed；六处反向篡改均被检出；`gen-contracts.sh --check` 一致；`verify.sh` exit 0（22 负例 + B08 5 + B09 5 + B10 36）；生成的 TS 经 `tsc --strict` 通过；`docs/handoffs/claude-b10.md` |

- 输入：`specs/task-processing.md`「交给后续任务的契约缺口」B10 各行与 §4、§5、§7、TASK-17；`specs/identity-access.md` §5、§7 B10 行、访问矩阵任务行（ADR-010、ADR-013 已签收）。
- 输出：`TaskEvent` 按事件拆成四个独立 schema（按 `stage` 判别）；`Task` 增加 `cancel_requested`、`failed_chunks`，并约束 `failed ⇔ error`；`TaskCounts.chunks_failed`；`issueEventTicket` 与 `EventTicket`；`streamTaskEvents` 改用 `eventTicket`；取消端点 200/409 描述；任务类 403/404 语义；`events.v1.md` §1、§2、§4 按规格改写。
- 依赖：B08（已合入）、A03、A05。无运行时代码、数据库或环境变量改动。
- 风险：`events.v1.md` §6 要求破坏性变更升 v2；依据 ADR-010（`specs/task-processing.md` §7）——v1 尚无消费者（C11/C12 未实现），原地修改。
- 验证：`python3 -m pytest tests/contracts/test_b10.py -q`、`./scripts/gen-contracts.sh --check`、`./scripts/verify.sh`、`git diff --check`。
- Claude 审查（REVIEW-B10，2026-09-24）：P2×4 已修——R01 `Task` 按 `stage` 拆为四个分支（生成器可见 `failed ⇔ error`）、R02 固定进度 `queued = 0` / `awaiting_review = 0.95`、R03 快照补 I5 与 `completed ⇒ progress = 1`、R04 新增 `TaskNotCancellableError` 闭集；P3×4（R05～R08）不阻塞、未改。B10 测试 36 → 45，`verify.sh` 通过；见 `docs/handoffs/claude-review-b10.md`。

## 2026-09-24 协作状态核对与 C08 认领

状态依据：交接基线 `origin/main@62cbbc7` 已包含 PR #175；PR #176 创建后先同步 `origin/main@248b895`，本轮再同步 `origin/main@1bce2c6`（含 B13 R09 修复 PR #177）。交接稿是当时快照，以下为本轮最新 issue/PR 核对；本轮只认领 C08，不改其他成员的源码。

| 分类 | 当前整理结果 |
| --- | --- |
| 已交付并入 main | A01～A10、B01～B06、B08～B10、B13、C01、C08、CI-01/02、HOOK-01、A10 批 0/1/1 补；B13 #55、C01 #58 与 C08 #65 已关闭并标 `status:done` |
| 有 PR、尚未并入 | 无（本节范围内）；B13 #32、C01 #174、C08 #176 均已合入，不再列为待审 PR |
| 阻塞/待认领 | B11 #53 仍按其 issue 处理；C02 #59 已分配 539210，C01 依赖现已合入，不重复认领 |
| 可接取但未认领 | D01、B12、E01、F01、B07、C05；依赖以交接稿第 5 节为起点，开工前再核对 issue 与文件锁 |
| 本轮认领 | C08 #65：已分配 `arvinhanye`，PR #176 已于 2026-09-24 合入 `main@f0b4afe`，issue 已关闭并标 `status:done`，见 [issue 验收记录](https://github.com/arvinhanye/SmartSketch/issues/65#issuecomment-5818583257) |

| 原子 ID | 状态 | 任务 | 负责人 | 目标分支 / base HEAD | 文件锁（本轮唯一写入者） | 验收与证据 |
| --- | --- | --- | --- | --- | --- | --- |
| C08 | DONE（PR #176 已合入 `f0b4afe`；#65 已关闭） | 实现状态迁移纯函数 | Codex（后端） | `codex/c08-task-state` / 初始 `62cbbc7`、已同步 `1bce2c6`；隔离 worktree `c08-task-state` | `src/backend/app/services/task_state.py`、`tests/backend/test_c08.py`；协作文档仅本节和 `docs/handoffs/codex-c08.md` | §2 合法边与 TASK-16 拒绝路径已实现；C08 定向 67 例、最新 main 上后端 143 例通过、B13 53 例通过，`./scripts/verify.sh`、`git diff --check` 通过。证据与边界见 `docs/handoffs/codex-c08.md`。REVIEW-C08 R01～R04 由 Claude 经授权在同分支修复并同步 `main@28b09b4`：C08 122 例、后端 198 例通过，见 `docs/handoffs/claude-review-fix-c08.md`。PR #176 CI 全绿后由 ArvinHan 授权于 2026-09-24 合入 `main@f0b4afe`。 |

- 输入：B10 已合入的 `Task`/事件契约；ADR-010 签收的 `specs/task-processing.md` §1～§4、TASK-16。
- 输出：无 I/O 的 `(当前任务状态, 事件) → 新任务状态 | 拒绝` 逻辑和定向测试，不变更 API、数据库或既有 DTO。
- 依赖：A03、B10、C01、B13 均已合入；C09、C11、F13 后续消费 C08，C08 已合入，这三项对 C08 的依赖已满足。
- 风险：并发 CAS、租约与持久化不属于本轮纯函数；固定进度及 `failed ⇔ error` 已由运行时校验覆盖。认领时缺依赖的环境缺口已用锁定版本的隔离 venv 解决，`verify.sh` 已通过。
- 当前协作状态：B13 #55 与 C01 #58 已关闭、标 `status:done`；C08 #65 已关闭、标 `status:done`；C02 #59 已分配 539210，现不再受 C01 未合入阻塞。其余任务仍需逐项按 issue/文件锁复核后再认领。

### HANDOFF-0924 固定范围复审（本节覆盖上文各任务行的旧「待审查」标记）

| 审查 ID | 状态 | 固定范围 | 负责人 | 验收与证据 |
| --- | --- | --- | --- | --- |
| REVIEW-HANDOFF-0924 | DONE（B02 Windows 缺口保留；B13 R09 已修） | B10 `f00a3e8..bb48429`；B02 `9d2437e..3fedd4e`；B03/B04 `3fedd4e..06f33aa`；CI-02 `06f33aa..025cbee`；B13 PR #32 `bb48429..791b1d8` | Codex | B10、B02、B03/B04、CI-02 固定范围未发现新增 P1/P2；B13 固定提交发现 P2×7、P3×2。Claude 在 `8a4992c` 修 R01～R07 后 PR #32 已合入；R09 后续由 PR #177 修复并合入，[#178](https://github.com/arvinhanye/SmartSketch/issues/178) 已关闭；本轮未跨文件锁修改契约。Windows 缺口及原始证据见 `docs/handoffs/codex-review-handoff-0924.md`。 |

- 复审只检查固定提交与实际运行的命令，不修改 Claude 的源码；B13 结论不等于新头提交已审。旧自动审查状态文件 `docs/reviews/claude-review-state.json` 在主目录有其他 Codex 未提交改动，本分支不覆盖它；本次增量状态另记 `docs/reviews/codex-handoff-0924-state.json`。
- C08 纯函数已实现并通过本地验证；B10 生成类型忽略固定阶段进度条件的已知限制由 C08 运行时及后续 C11 序列化路径承担。PR #176 已合入 `main@f0b4afe`，issue #65 已关闭；实现验收另记在 `docs/handoffs/codex-c08.md`，不与审查完成混算。REVIEW-C08（PR #176 评论）的 R01 错误详情序列化、R02 失败码按 §6 绑定阶段、R03 `invalid_event`、R04 契约对齐测试已修复，见 `docs/handoffs/claude-review-fix-c08.md`。

## B13 问答与事件契约

| 原子 ID | 状态 | 任务 | 负责人 | 目标分支 / base HEAD | 文件锁（本轮唯一写入者） | 证据 |
| --- | --- | --- | --- | --- | --- | --- |
| B13 | DONE（已合入；R09 已修） | 迁移问答与事件契约 | ArvinHan（Claude 执行） | `claude/b13-chat-contract` / 叠在 B10 `3771ae1`（PR #31）上 | `src/contracts/api.v1.yaml`、`src/contracts/events.v1.md` §3、`src/contracts/v1/generated/`、`tests/contracts/test_b13.py`；接入 `scripts/verify/contracts.sh`；随附：`docs/architecture.md` 的 `NotCoveredReason` 行（Q11 要求同一次提交）、`src/contracts/errors.v1.md` 的 `RATE_LIMITED` 措辞（Q11 交 B08 的遗留）、`specs/grounded-qa.md` Q11 状态标注、`docs/handoffs/claude-b13.md` | `test_b13.py` 先 17 failed 后 43 passed；六处反向篡改均被检出；门禁实例级夹具按新必填字段补齐；`gen-contracts.sh --check` 一致；`verify.sh` exit 0；生成的 TS 经 `tsc --strict` 通过；`docs/handoffs/claude-b13.md` |

- 输入：`specs/grounded-qa.md` Q2、Q4、Q5、Q6、Q7、Q9、Q11 B13 行（ADR-015 及修订 1 已签收）。
- 输出：`NotCoveredReason` 改名为 `insufficient_evidence`；`ChatMetaEvent`、`ChatAnswered`、`ChatNotCovered` 增加 `graph_version`、`request_id`；问答错误事件带 `details.request_id`，`LLM_UNAVAILABLE` 的 `details.reason` 取闭集；问答接口补 404/500；`events.v1.md` §3 改为指向规格。
- 依赖：B08（已合入）、A09；叠在 B10 上以避免生成物冲突。
- 风险：同 B10，v1 问答事件尚无消费者（J07/J08 未实现），原地修改。
- 验证：`python3 -m pytest tests/contracts/test_b13.py -q`、`./scripts/gen-contracts.sh --check`、`./scripts/verify.sh`、`git diff --check`。
- Claude 审查（REVIEW-B13，2026-09-24）：修 R01～R07——`ChatError` 按 `code` 拆为两支、错误码闭集、`reason` 只属于 `LLM_UNAVAILABLE`（R01～R03）；`meta.status = answered ⇒ retrieved ≥ 1`（R04）；问答 503 引用 `ChatUnavailableError`（R05）；`events.v1.md` §6 补登 B13 例外（R06）；`ChatError` 与 B10 取消 409 的 `details` 改为具名 schema（R07）。R08 未改。B13 测试 43 → 52；见 `docs/handoffs/claude-review-b13.md`。Codex 另发现 R09（`ChatDoneEvent` 描述与 I1 矛盾），合并后另开 PR 修正，B13 测试 53。
- Codex 固定头 `791b1d8` 复审另发现 R09；随后 PR #177 已合入 `main@1bce2c6` 并新增回归测试。原跟踪 [#178](https://github.com/arvinhanye/SmartSketch/issues/178) 经回归验证后已标 DONE 并关闭；本 C08 分支只保留历史审查证据，不重改契约文件。

## C01 SQLite 连接与迁移运行器

| 原子 ID | 状态 | 任务 | 负责人 | 目标分支 / base HEAD | 文件锁（本轮唯一写入者） | 验收 |
| --- | --- | --- | --- | --- | --- | --- |
| C01 | DONE（审查 P1/P2 已修） | 建立 SQLite 连接和迁移运行器 | Codex（后端） | `codex/c01-sqlite` / `9d2437e` | `src/backend/app/repositories/sqlite.py`、`src/backend/migrations/001_base.sql`、`tests/backend/test_c01.py`；文档：`docs/architecture.md`、`src/backend/README.md`、本任务板、`docs/handoffs/codex-c01.md` | 临时库迁移可重复；单事务失败回滚；活跃及到期秒租约拒绝；迁移前备份及恢复演练；B06 向量空间记录保留。审查修复：`model_calls` 预写、按 `call_id` 重放去重与归属查询；迁移返回后立即移动备份。专项 13 passed、后端 71 passed、`./scripts/verify.sh` exit 0，见交接。 |

- 输入：B06 的 `SQLITE_URL` 与 `embedding_space_state`，ADR-011 的停机迁移协议，ADR-012 的空间记录约束。
- 输出：WAL/外键/超时连接函数、只向前的版本化迁移、`001_base.sql` 和恢复步骤。
- 依赖：B06、A04、A06 均已完成；不改 REST/SSE 契约。
- 风险：迁移必须在 API/worker 停机时执行；后续表迁移需沿用同一备份与租约检查协议。
- 验证：`python -m pytest tests/backend/test_c01.py -q`、B05/B06 回归、`./scripts/verify.sh`、`git diff --check`。
- Claude 同步与审查（REVIEW-C01，2026-09-24）：同步 main `6790d22`（本节按编号移到 B13 之后，内容不变）；后端 71 passed、CI 三个 job 通过。P2×3（R01 迁移文件换行影响校验和、R02 启动不检查迁移版本、R03 `embedding_space_state` 建表有两处）已由 Claude 修正（ArvinHan 决定；ADR-012 补注修订 1：建表只在迁移，API 启动先检查迁移版本），后端 76 passed；P3×6 未改；见 `docs/handoffs/claude-review-c01.md`。

## ADR-012 修订 3：快照谱系与共享提交序号（解除 B11 阻塞）

| ID | 状态 | 任务 | 负责人 | 目标分支 / base HEAD | 文件锁（本轮唯一写入者） | 证据 |
| --- | --- | --- | --- | --- | --- | --- |
| ADR-012 修订 3 | DONE（ArvinHan 2026-09-24 在会话中签收，PR #179） | 落实 ADR-014 修订 1 决定 9、10 交给 ADR-012 的两项：快照节点 `merged_from` 的形状与摘要纳入、版本提交从共享序列取 `commit_seq` | ArvinHan（Claude 起草） | `claude/adr-012-r3` / base `248b895` | `docs/decisions.md`（ADR-012 修订 3 一节与引言一行）、`specs/teacher-review-publish.md`（V2、V3、V5、V6、V10）、`specs/learning-path.md`（§7 细则 1、2 的指向）、本节、`docs/handoffs/claude-adr-012-r3.md` | `docs/handoffs/claude-adr-012-r3.md`；`./scripts/verify.sh` 通过 |

- 输入：ADR-014 修订 1 决定 9、10 与「后果」；`specs/learning-path.md` §5、LP-9、LP-17～LP-20；`specs/teacher-review-publish.md` V2～V6。
- 输出：决定 15～25——`merged_from` 为本版本中归属到该节点的全部来源、链已展平；不变式与 `invalid_lineage` 校验；草稿维护规则；纳入摘要、不升 `snapshot_format`；不进 wire DTO；单行表 `commit_sequence` 与 `commit_seq` / `write_seq`。
- 依赖与风险：已签收，B11、F10、G01、G02、G04、G06、I01 可按本条实现；B11 须同时并入 A02-R01。
- 验证：`./scripts/verify.sh`、`git diff --check`；LP-9、LP-19、LP-20 三个谱系场景已在交接中逐一推演。

## 2026-09-24 并行批次（Claude）

同一批并行开工的四项，各在独立 worktree 与分支上进行，文件锁互不相交；任务板由协调方（本会话）统一更新，各子任务只写自己的交接文件。

| 原子 ID | 状态 | 任务 | 负责人 | 分支 / base | 文件锁（本轮唯一写入者） | 证据 |
| --- | --- | --- | --- | --- | --- | --- |
| C13 | DONE（PR #186 `6639e16`） | 实现本地账号登录与访问令牌签发 | Claude（后端子代理） | `claude/c13-auth` / `origin/main` | `src/backend/app/api/auth.py`、`src/backend/app/services/auth.py`、`src/backend/app/repositories/accounts.py`、`src/backend/migrations/NNN_accounts.sql`、`tests/backend/test_c13.py`、`src/backend/app/config.py`、`.env.example`、`docs/integrations.md`；接线所需的 `src/backend/app/main.py`；依赖变化时 `src/backend/pyproject.toml` | `docs/handoffs/claude-c13.md`；REVIEW-C13 R01～R06 已修（`9265580`、`7d8deb7`）；C13 58 passed，合入 main 后后端 474 passed，`verify.sh` exit 0；CI 三个 job 通过；#160 已关闭 |
| D01 | DONE（PR #183 `cfec20e`） | 定义解析输出与自编 fixture | Claude（数据子代理） | `claude/d01-parse-model` / `origin/main` | `src/backend/app/services/parsers/`（仅 `__init__.py`、`models.py`）、`tests/fixtures/documents/`、`tests/backend/test_d01.py` | `docs/handoffs/claude-d01.md`；REVIEW-D01 R01～R05 已修（`74be60d`）；D01 88 passed，合并前复核后端 416 passed、`verify.sh` exit 0；CI 通过；#70 已关闭 |
| E01 | DONE（PR #182 `dc20326`） | 建立版本化提示词装载器 | Claude（AI 子代理） | `claude/e01-prompts` / `origin/main` | `src/backend/app/services/ai/`（仅 `__init__.py`、`prompts.py`）、`prompts/`、`tests/backend/test_e01.py` | `docs/handoffs/claude-e01.md`；E01 69 passed、后端全部通过；CI 三个 job 通过 |
| C05 | DONE（PR #181 `3f1f059`） | 实现文件落盘边界 | Claude（后端子代理） | `claude/c05-file-storage` / `origin/main` | `src/backend/app/services/file_storage.py`、`tests/backend/test_c05.py` | `docs/handoffs/claude-c05.md`；C05 61 passed、后端全部通过；CI 三个 job 通过；配置项待补（D-11） |

- 进展（2026-09-24）：C05、E01、D01、C13 均已合并，本批完成。C13 引入的全局 422 处理器输出 `details.fields = [{in, field, reason}]`，已登记到 `src/contracts/errors.v1.md`。
- ~~待认领：按 D-11 把 `UPLOAD_MAX_BYTES`、`STORAGE_DIR` 补进 `config.py`、`.env.example`、`docs/integrations.md`~~（已完成，见「D-11 上传配置落地」）；D02～D05 现可并行认领（只依赖 D01）；C02、C03、C14、H13 的前置 C13 已满足。
- 不在本批：B12（与 539210 的 B11 同改 `api.v1.yaml`）、B07（与 C13 可能同改 `pyproject.toml`）、F01（需要本机 Docker/Neo4j）。
- 并行约束：四项都不改 `docs/tasks.md`、`docs/architecture.md`、`scripts/verify.sh`；需要改共享文件时停下来交给协调方。

## 2026-09-24 解析并行批次（Claude）

D02～D05 只依赖已合并的 D01，四项同时开工，各在独立 worktree 与分支上进行。任务板由协调方统一更新，各子任务只写自己的交接文件。

| 原子 ID | 状态 | 任务 | 负责人 | 分支 / base | 文件锁（本轮唯一写入者） | 证据 |
| --- | --- | --- | --- | --- | --- | --- |
| D02 | DONE（PR #190 `d2c465e`） | 实现 TXT 编码与标题解析 | Claude（数据子代理） | `claude/d02-txt-parser` / `origin/main` | `src/backend/app/services/parsers/txt.py`、`tests/backend/test_d02.py`、`docs/handoffs/claude-d02.md` | `docs/handoffs/claude-d02.md`；标准库、无新依赖；D02 94 passed，协调方复核后端 568 passed；CI 通过；#71 已关闭 |
| D03 | DONE（PR #191 `2694e3e`） | 实现 Markdown AST 解析 | Claude（数据子代理） | `claude/d03-markdown-parser` / `origin/main` | `src/backend/app/services/parsers/markdown.py`、`tests/backend/test_d03.py`、`docs/handoffs/claude-d03.md`；新增依赖时 `src/backend/pyproject.toml` 的 `dependencies` 一行 | `docs/handoffs/claude-d03.md`；`markdown-it-py==4.2.0`（MIT）；含 D-12 放宽；D03 66 passed，协调方复核后端 634 passed；CI 通过；#72 已关闭 |
| D04 | DONE（PR #193 `ebed3cd`） | 实现 DOCX 段落和表格解析 | Claude（数据子代理） | `claude/d04-docx-parser` / `origin/main` | `src/backend/app/services/parsers/docx.py`、`tests/backend/test_d04.py`、`docs/handoffs/claude-d04.md`；新增依赖时 `src/backend/pyproject.toml` 的 `dependencies` 一行 | `docs/handoffs/claude-d04.md`；标准库自解析、无新依赖；D04 53 passed，协调方复核后端 527 passed，billion-laughs 样例被拒；CI 通过；#73 已关闭 |
| D05 | DONE（PR #197 `a08bd5b`） | 实现 PDF 正文与页码提取 | Claude（数据子代理） | `claude/d05-pdf-parser` / `origin/main` | `src/backend/app/services/parsers/pdf.py`、`tests/backend/test_d05.py`、`docs/handoffs/claude-d05.md`；新增依赖时 `src/backend/pyproject.toml` 的 `dependencies` 一行 | `docs/handoffs/claude-d05.md`；`pdfminer.six==20260107`（MIT）；协调方解决依赖行冲突（`93d5971`）；D05 33 passed，协调方从 PyPI 完整安装后复核后端 720 passed，CI 中 `pip check` 无冲突；#74 已关闭 |

- 依赖约定：D02 只用标准库。D03～D05 如需解析库，只选 MIT/BSD/Apache 类许可，禁用 AGPL（如 PyMuPDF），版本固定为 `==`，只在 `dependencies` 加一行，不动 `test` 组（B07 PR #187 在改 `test` 组）。三者在 `pyproject.toml` 若有文本冲突，由协调方在合并时顺序解决。选库理由写入各自交接，由协调方统一登记到 `docs/integrations.md`。
- 共享文件不改：`parsers/__init__.py`、`parsers/models.py`、`tests/fixtures/documents/`、`docs/tasks.md`、`docs/architecture.md`、`docs/integrations.md`、`scripts/verify.sh`。测试用的 DOCX/PDF 在测试里生成到 `tmp_path`，不入库。需要改共享文件时，停下来交给协调方。
- D05 须给 D06（PDF 标题判定）留下逐行的字号和字重信息，D07 需要的逐页行也要能取到；接口形状写入 D05 交接。
- 进展（2026-09-25）：D02～D05 均已合并，本批完成。解析依赖已登记到 `docs/integrations.md`「文档解析依赖（D02～D05）」。D06、D07 现可认领（依赖 D05，中间结构见 `docs/handoffs/claude-d05.md`）；D08 须按 D-13 在块前拼章节路径。
- 遗留风险：PDF 解析没有限制页数与耗时，恶意文件可能拖慢 worker，由后续 worker 超时机制兜底；DOCX 主文档路径固定为 `word/document.xml`，不按关系文件解析。

## REQ-01 赛题抽取硬指标补登

| ID | 状态 | 任务 | 负责人 | 分支 / base | 文件锁（本轮唯一写入者） | 证据 |
| --- | --- | --- | --- | --- | --- | --- |
| REQ-01 | DONE（文档补登；指标尚未实测） | 把赛题「技术要求与指标（一）」的两项硬指标（单章实体 ≥ 20、人工抽样准确率 ≥ 70%）补进规格和原子任务 | ArvinHan（Claude 执行） | `claude/pdf-course-model-training-0b0f46` / `6639e16` | `specs/course-knowledge-graph.md`（关联任务、验收 7）、`docs/product.md`（MVP 表「抽取质量」行）、`docs/atomic-task-plan.md` 与 `docs/atomic-tasks.json`（K01、K02 行，人工决策门 D-01 行）、本节与 D-01 行、`docs/handoffs/claude-req-01.md` | `validate_atomic_plan.py` PASS（141 项，MD/JSON 一致）；`./scripts/verify.sh` exit 0；`git diff --check` exit 0；`docs/handoffs/claude-req-01.md` |

- 输入：赛题原文 `【A10】基于AIGC的课程知识图谱智能构建与学习导航系统【金扬智能】.docx`（在主目录，不入库）第 6 节「技术要求与指标（一）」与第 7 节。
- 输出：验收 7 规定了基准材料、实体数、准确率、判定对象、报告内容和失败路径；K01 负责口径与一章量的标注材料，K02 负责计算、判定并新增 `evaluation/reports/extraction-accuracy.md`。
- 核对：赛题其余指标已有覆盖——格式 ≥ 2 种、关系 ≥ 3 种（四格式、四关系）；问答 ≤ 15 秒（`LLM_CHAT_TIMEOUT_SECONDS`、K04）；讲解与练习题（O05/O06）；赛题不要求训练模型。
- 决策 D-15（ArvinHan，2026-09-24 确认；原拟编号 D-14 已被 PR #199 的 PDF 权限决策占用，合并时改号）：70% 按「实体、关系分别达标」执行。

## D-11 上传配置落地

| ID | 状态 | 任务 | 负责人 | 分支 / base | 文件锁（本轮唯一写入者） | 证据 |
| --- | --- | --- | --- | --- | --- | --- |
| D-11 落地 | DONE（PR #205 `50dca8c`） | 把 `STORAGE_DIR`、`UPLOAD_MAX_BYTES` 补进设置、示例与集成登记 | Claude（协调方） | `claude/d11-upload-config` / `04f8ac6` | `src/backend/app/config.py`、`.env.example`、`docs/integrations.md`（应用运行与存储表、启动校验）、`tests/backend/test_d11_upload_config.py`、本节与 D-11 行、`docs/handoffs/claude-d11-upload-config.md` | `docs/handoffs/claude-d11-upload-config.md`；先红 10 failed，后绿 D-11 10 passed；后端全量 730 passed |

- 输入：D-11（50 MiB、变量名 `UPLOAD_MAX_BYTES`）；`STORAGE_DIR=./storage` 沿用 740adb（A10 导入映射「批 2 只取 `STORAGE_DIR`」）。输出：`Settings.STORAGE_DIR`、`Settings.UPLOAD_MAX_BYTES`，C06/C07 按 `FileStorage(settings.STORAGE_DIR, max_bytes=settings.UPLOAD_MAX_BYTES)` 使用。
- 验收：缺省值与 D-11 一致；0、负数、小数、带单位、空串拒绝并指出变量名；空白 `STORAGE_DIR` 拒绝；设置值能直接构造 `FileStorage` 并在超限时给出 `limit_bytes`；`.env.example` 覆盖全部设置（B06 回归）。

## 2026-09-25 Codex 认领：C06

| 原子 ID | 状态 | 任务 | 负责人 | 目标 worktree / base HEAD | 文件锁（本轮唯一写入者） | 验收条件 |
| --- | --- | --- | --- | --- | --- | --- |
| C06 | DONE（PR #209 `8309c03`；#63 已关闭） | 实现资料和任务创建事务 | Codex（后端） | `.claude/worktrees/c06-material-task-transaction`，分支 `codex/c06-material-task-transaction` / `origin/main@a80519c` | `src/backend/app/repositories/materials.py`、`src/backend/app/repositories/tasks.py`、`src/backend/migrations/003_tasks.sql`、`tests/backend/test_c06.py`、`tests/backend/test_c13.py`（范围扩展：仅更新新增 003 后的默认迁移序列断言）、`docs/handoffs/codex-c06.md` | 原子创建、回滚、课程隔离幂等与按课程限定读取已验证；C06 7 passed；后端 763 passed（1 条既有 Starlette/httpx 弃用警告）；`./scripts/verify.sh` 与 `git diff --check` 通过。交接：`docs/handoffs/codex-c06.md`；实现锚点 `7117683`；课程隔离评审修正 `34c73c9`；PR #209。迁移编号按 D-10 已对 `origin/main@a80519c` 复核，最大版本仍为 002。 |

- 输入 / 输出：接收已校验的文件元数据，原子地产生 material 与 queued task。依赖 C01、B10 均已合入 `origin/main`；C05 已合入，上传 API 留给 C07。
- 风险 / 回滚：C13 默认迁移序列测试随新增 003 更新，范围扩展仅限其期望序列；其余只写入上列文件。迁移需遵循 C01 停机、备份与恢复流程；合并前若编号冲突，按 D-10 改号并重跑迁移测试。C07 需在幂等重放时删除新落盘的未引用文件；再处理与 parse_status 语义留待 C07。

## C14 账号管理命令与演示账号种子

| ID | 状态 | 任务 | 负责人 | 分支 / base | 文件锁（本轮唯一写入者） | 证据 |
| --- | --- | --- | --- | --- | --- | --- |
| C14 | DONE（PR #210） | 实现账号管理命令与演示账号种子 | Claude | `claude/c14-account-seed` / `04f8ac6` | `scripts/manage-accounts.py`、`scripts/seed-demo-accounts.py`、`tests/backend/test_c14.py`；**范围扩展**（后端分层规则要求业务放 services、持久化放 repositories，#161 已登记）：`src/backend/app/services/account_admin.py`（新建）、`src/backend/app/repositories/accounts.py`（只追加函数）；`docs/integrations.md`（本地账号登录节）、本节、`docs/handoffs/claude-c14.md` | `docs/handoffs/claude-c14.md`；C14 26 passed（先红：缺模块收集失败，后续逐步转绿）；9 处反向篡改中 7 处被抓到，另 2 处是等价变异（原因见交接）；后端全量 746 passed；`verify.sh` exit 0 |

- 输入：`specs/identity-access.md` §1.1、§1.2（ADR-013）；C13 的 `create_account` 与 `users` 表。输出：两个命令脚本，以及服务函数 `set_disabled`、`reset_password`、`list_accounts`、`seed_demo_accounts`。
- 验收：创建和停用都能用 `list` 复查；重复停用保留首次时间；重复种子不新增、不改已有口令和停用状态；缺少或空白的 `SEED_DEMO_PASSWORD` 非 0 退出且不写库；同名账号类型不符整批拒绝；未迁移的库非 0 退出且不建库文件；口令不作为命令行参数，也不出现在任何输出里。
- 不在本任务：协作教师经命令行加入课程（§3.3）需要 C02 的课程和成员表，交 C02/C15。

## 2026-09-25 并行批次（Claude）

F05、E02、D06、D07、C02 前置均已合并，与 B12（改 `api.v1.yaml`）无共享文件，五项同时开工，各在独立 worktree 与分支上进行。C02 原分配 539210（2026-09-24 回复“正在做”，远端无分支或 PR），经 ArvinHan 授权转由 Claude 执行，见 issue #59。

| 原子 ID | 状态 | 任务 | 负责人 | 分支 / base | 文件锁（本轮唯一写入者） | 证据 |
| --- | --- | --- | --- | --- | --- | --- |
| F05 | DONE（PR #203 `b4ed883`） | 实现 DAG 环检测纯函数 | ArvinHan（Claude 子代理） | `claude/f05-dag-cycle` / `8eeac3b` | `src/backend/app/services/graph/dag.py`、`tests/backend/test_f05.py`、`docs/handoffs/claude-f05.md` | 红：仅测试时收集错误（无 `app.services.graph`）；桩函数 72 failed。绿：`test_f05.py` 73 passed；`tests/backend` 793 passed（基线 720）；5 处篡改全部被检出（其中旋转篡改首轮漏检，已补测试）；`./scripts/verify.sh`、`git diff --check` exit 0。另补 `services/graph/__init__.py`。见 `docs/handoffs/claude-f05.md` |

- F05 验收：自环、三节点环、反转造环、断开图、大链条；复杂度边界明确。验证：`python3 -m pytest tests/backend/test_f05.py -q`。

| 原子 ID | 状态 | 任务 | 负责人 | 分支 / base | 文件锁（本轮唯一写入者） | 证据 |
| --- | --- | --- | --- | --- | --- | --- |
| E02 | DONE（PR #207 `aaae534`） | 建立模型接口和 fake 适配器 | ArvinHan（Claude 子代理） | `claude/e02-ai-client` / `8eeac3b` | `src/backend/app/services/ai/client.py`、`src/backend/app/services/ai/fake.py`、`tests/backend/test_e02.py`、`docs/handoffs/claude-e02.md` | `docs/handoffs/claude-e02.md`；实现 `c87ae5c`；E02 先红（收集错误 exit 2）后 65 passed；后端 785 passed；`verify.sh` exit 0；`git diff --check` exit 0；5 处篡改均被检出；无新依赖；待决见交接（fake 模式模型 ID、缓存键取哪个模型 ID） |

- E02 验收：固定输入输出可复现；超时/坏 JSON/限流可模拟；无需密钥。验证：`python3 -m pytest tests/backend/test_e02.py -q`。

| 原子 ID | 状态 | 任务 | 负责人 | 分支 / base | 文件锁（本轮唯一写入者） | 证据 |
| --- | --- | --- | --- | --- | --- | --- |
| D06 | DONE（PR #208 `1ffda90`） | 实现 PDF 标题判定 | ArvinHan（Claude 子代理） | `claude/d06-pdf-headings` / `8eeac3b` | `src/backend/app/services/parsers/pdf_headings.py`、`tests/backend/test_d06.py`、`docs/handoffs/claude-d06.md` | `docs/handoffs/claude-d06.md`；无新依赖；先红（模块缺失，收集错误 exit 2）后绿：D06 34 passed，后端 754 passed，6 项反向篡改均被检出；`./scripts/verify.sh` exit 0；`git diff --check` exit 0 |

- D06 验收：正文加粗不误做所有标题；标题跨页、无字号层级有退路。验证：`python3 -m pytest tests/backend/test_d06.py -q`。

| 原子 ID | 状态 | 任务 | 负责人 | 分支 / base | 文件锁（本轮唯一写入者） | 证据 |
| --- | --- | --- | --- | --- | --- | --- |
| D07 | DONE（PR #204 `003dd20`） | 实现重复页眉页脚清洗 | ArvinHan（Claude 子代理） | `claude/d07-header-footer` / `8eeac3b` | `src/backend/app/services/parsers/cleanup.py`、`tests/backend/test_d07.py`、`docs/handoffs/claude-d07.md` | `docs/handoffs/claude-d07.md`；标准库、无新依赖；先红（收集错误 exit 2）后绿 D07 43 passed；6 处反向篡改均被检出；后端 763 passed（venv，Python 3.13.5）；`./scripts/verify.sh` exit 0；`git diff --check` exit 0 |

- D07 验收：重复正文不被误删；删除页码不丢原始页定位；支持关掉清洗。验证：`python3 -m pytest tests/backend/test_d07.py -q`。

| 原子 ID | 状态 | 任务 | 负责人 | 分支 / base | 文件锁（本轮唯一写入者） | 证据 |
| --- | --- | --- | --- | --- | --- | --- |
| C02 | DONE（PR #206 `a7a0be0`） | 实现课程和成员仓储 | ArvinHan（Claude 子代理；原 539210） | `claude/c02-course-repo` / `8eeac3b` | `src/backend/app/repositories/courses.py`、`src/backend/migrations/NNN_courses.sql`（D-10：合并时取 main 最大编号 + 1）、`tests/backend/test_c02.py`、`docs/handoffs/claude-c02.md` | 迁移取 `004_courses.sql`（C06 #209 先占 003，按 D-10 改号；同步适配 `test_c13.py`、`test_c06.py` 迁移断言）。`test_c02.py`：实现前收集失败（ImportError，0 passed），实现后 21 passed；4 处反向篡改分别 2/2/1/2 failed，恢复后全绿。`tests/backend` 初为 1 failed / 740 passed（`test_c13.py` 断言迁移目录只到 002）；协调方以单独提交把该用例改为只含 001、002 的临时目录（范围扩展），复跑 741 passed。`./scripts/verify.sh` exit 0；`git diff --check` exit 0。交接 `docs/handoffs/claude-c02.md` |

- C02 验收：课程成员唯一；同用户不同课程角色独立；读写外键正确（`course_members.user_id` → C13 的 `users`）。验证：`python3 -m pytest tests/backend/test_c02.py -q`。

- 进展（2026-09-25）：五项均已合并，本批完成。合并前协调方统一了本节五行、把 C02 迁移改号为 004（C06 #209 先占 003），并修复 C01 迁移器与 C06 任务表不兼容（FIX-MIGRATE-LEASE，#212）。合并后 main 复核：后端 1002 passed、契约与工具 269 passed、`verify.sh` exit 0；收尾交接见 `docs/handoffs/claude-batch-0925-closeout.md`。
- 并行约束：各子任务只写自己的文件锁与交接文件，并只改本节自己那一张表的状态与证据；不改 `docs/architecture.md`、`docs/integrations.md`、`scripts/verify.sh`、`parsers/__init__.py`、`parsers/models.py` 等共享文件，需要时停下交协调方。

## F01 复用本地 Neo4j 环境并验证

| ID | 状态 | 任务 | 负责人 | 分支 / base | 文件锁（本轮唯一写入者） | 证据 |
| --- | --- | --- | --- | --- | --- | --- |
| F01 | DONE（PR #211） | 复用本地 Neo4j 环境并验证 | Claude | `claude/f01-neo4j-env` / `a80519c` | `docker-compose.yml`、`scripts/dev-up.sh`、`scripts/check-apoc.sh`、`tests/integration/test_f01.py`；按导入映射「批 2」扩到 `scripts/_dev-common.sh`（dev-up 依赖它）、`.env.example`（仅容器变量注释行）、`docs/integrations.md`（本地依赖环境一节与计划集成 Neo4j 行）；本节、`docs/handoffs/claude-f01.md` | `docs/handoffs/claude-f01.md`；真实 Docker 12 passed（Neo4j 5.26.31 + APOC 5.26.31 可用，停启后数据仍在）；原脚本红灯 4 failed，两处缺陷（unhealthy 被判就绪、口令出现在宿主机命令行）已单独取证并修复；反向篡改 5 处全被抓到；后端 756 passed |

- 输入：740adb `978671e` 的 compose 与脚本（M0-05，当时因 APOC 未实测而 BLOCKED）；ArvinHan 本机 Docker Desktop 29.8、Compose v5.5。输出：可启动、可健康检查、已验证 APOC、停启后数据仍在的本地 Neo4j。
- 验收：先审原脚本（审查结论与两处缺陷的取证见交接）；缺 `.env`、容器不健康、APOC 缺失都以非 0 退出并给出提示；口令不出现在任何命令行参数里；真实容器上 APOC 可用、停启后数据仍在。
- 不在本任务：`dev-down.sh` 与启停行为审查（K07）；Neo4j 驱动与仓储（F02）；约束与索引迁移（F03）。

## FIX-MIGRATE-LEASE 迁移器租约检查与 C06 任务表不兼容（2026-09-25）

| ID | 状态 | 任务 | 负责人 | 分支 / base | 文件锁（本轮唯一写入者） | 证据 |
| --- | --- | --- | --- | --- | --- | --- |
| FIX-MIGRATE-LEASE | DONE（PR #212 `4e42a5d`） | C01 迁移器只对有租约列的表检查租约，解除 C06 `processing_tasks`（无租约列）对 003 之后所有迁移的阻塞 | ArvinHan（Claude 协调方） | `claude/fix-migrate-lease-guard` / `1ffda90` | `src/backend/app/repositories/sqlite.py`、`tests/backend/test_c01.py`、`docs/handoffs/claude-fix-migrate-lease.md` | 复现用例 3 个修前 failed、修后 C01 21 passed；后端 981 passed；`docs/handoffs/claude-fix-migrate-lease.md` |

- 后续：C09 加租约列时，补一条真实表上“有效租约阻止迁移”的回归。

## 审查遗留（2026-09-25 核对）

把「待审查」状态逐项对照 Codex 审查报告（REVIEW-18～22，已于 PR #201 入库），并在 `origin/main@36670a3` 上复现。下面 4 项仍然存在，还没有任务跟踪：

| 编号 | 级别 | 来源 | 现状（main 上复现） | 建议归属 |
| --- | --- | --- | --- | --- |
| B03-R01′ | P2 | REVIEW-19（`docs/reviews/codex-claude-b03-b04-2026-09-24-0605z.md`）。加 ′ 是为了和上方 B03 节里协调方自提的 P3「B03-R01」区分 | `src/frontend/src/main.ts` 仍为 `getAccountRole: () => null`，真实入口里教师和学生页面都不可达 | H13（登录页与会话存储）：从 `LoginResponse.user.role` 提供角色，登录、登出、401 时导航，并补真实入口的集成测试 |
| B04-R01 | P2 | 同上 | `stores/course.ts` 的 `selectCourse` 遇到相同课程 ID 直接返回；同一标签页里换账号后，旧 `graph`、`chatHistory` 和已签发的作用域仍然有效 | H13：增加会话重置入口，在登出、401、换账号时调用；或者把用户身份纳入作用域键 |
| B10F-R01 | P2 | REVIEW-22（`docs/reviews/codex-claude-b10-fix-21de627-2026-09-24-1556z.md`） | 生成的 `TaskCancelled.cancel_requested` 是 `Literal[True] = True`（有默认值、非必填），缺字段的取消快照能通过 `Task.model_validate`，而 JSON Schema 会拒绝 | 契约修复，建议在 C10/C11 实现取消响应前完成：让生成模型把该字段设为必填，并补缺字段与 `exclude_unset` 的回归测试 |
| B10F-R02 | P3 | 同上 | `TaskNotCancellableError.details` 的三个分支没有 `additionalProperties: false`，`{stage, reason, secret}` 能通过 JSON Schema | 与 B10F-R01 一起修：三个分支加 `additionalProperties: false`，并补负例 |
| D08-P3 | P3 | PR #215 审查（Claude） | `chunking._render` 给窗口里的每个来源段落各拼一次 `section_path`；同一窗口里有多个短段落时，路径重复出现，抽取时多耗 token。D-13「在每块正文前拼上章节路径」对「块」的理解存在歧义 | D12 接入抽取时一并确认：每个窗口拼一次，还是每个来源段落拼一次 |
| E07-P3 | P3 | PR #217 审查（Claude） | `EmbeddingAdapter.embed` 末尾的 `if vector is not None` 过滤，一旦有向量漏填，结果会静默变短并与输入错位 | 改为断言全部填满；可在 E03 接入时顺手修 |

C03-R01（P1，PR #216 审查）：拒绝错误是模块级的单例异常，反复 raise 会累积 `__traceback__` 并持有每次请求的令牌。已在合并前修复（`fe5ae64`，交接 `docs/handoffs/claude-c03-r01-fix.md`），不再是遗留项。

## 2026-09-25 第二批并行（Claude）

C09、E03、I03 前置均已合并，issue 无人认领，与在途工作不共享文件：539210 的 C03（#216，改 `repositories/tasks.py`）、C04、E07（#217，`ai/embeddings.py`），以及 arvinhanye 的 B14（#214）、D08（#215）、F02、K07。三项各在独立 worktree 与分支上进行。各子任务只改本节中自己那一张表的状态与证据列。

| 原子 ID | 状态 | 任务 | 负责人 | 分支 / base | 文件锁（本轮唯一写入者） | 证据 |
| --- | --- | --- | --- | --- | --- | --- |
| C09 | IN PROGRESS | 实现 worker 原子领取与租约 | ArvinHan（Claude 子代理） | `claude/c09-task-leases` / `36670a3` | `src/backend/app/repositories/task_leases.py`、`src/backend/migrations/NNN_task_leases.sql`（D-10：现取 005）、`tests/backend/test_c09.py`、`docs/handoffs/claude-c09.md`；不改 `repositories/tasks.py`（C03 #216 在改） | 待补 |

- C09 验收：两个连接争同一任务只有一个成功；旧租约 token 禁止续写；到期可接管。验证：`python3 -m pytest tests/backend/test_c09.py -q`。

| 原子 ID | 状态 | 任务 | 负责人 | 分支 / base | 文件锁（本轮唯一写入者） | 证据 |
| --- | --- | --- | --- | --- | --- | --- |
| E03 | IN PROGRESS | 实现兼容 API 适配器 | ArvinHan（Claude 子代理） | `claude/e03-compatible-api` / `36670a3` | `src/backend/app/services/ai/compatible.py`、`tests/backend/test_e03.py`、`docs/handoffs/claude-e03.md`；不改 `ai/embeddings.py`（E07 #217 在改） | 待补 |

- E03 验收：按 OpenAI 兼容协议实现；用模拟传输测超时、错误与结构；真实调用需另行配置（供应商取值待 D-02a）。验证：`python3 -m pytest tests/backend/test_e03.py -q`。

| 原子 ID | 状态 | 任务 | 负责人 | 分支 / base | 文件锁（本轮唯一写入者） | 证据 |
| --- | --- | --- | --- | --- | --- | --- |
| I03 | IN PROGRESS | 实现可学集合纯函数 | ArvinHan（Claude 子代理） | `claude/i03-eligible-set` / `36670a3` | `src/backend/app/services/learning/eligible.py`、`tests/backend/test_i03.py`、`docs/handoffs/claude-i03.md` | 待补 |

- I03 验收：已掌握集合为空、全部掌握、孤立点、多前置、有环、外课 ID；不修改用户的掌握集合。验证：`python3 -m pytest tests/backend/test_i03.py -q`。

- 合并约定：三个分支共用本认领提交。若合并前 main 在本文件末尾又有追加导致冲突，由协调方先在 `claude/batch-0925b-claims` 上解决一次，再并入三个分支，保证三者的解决结果一致。

## 2026-09-25 第三批并行（Claude）

D09、C16、B15 的前置均已合并（D09：D08、A07；C16：C03、C06、B10；B15：B02、B14），issue 无人认领、无远端分支。已核对在途工作并避开：539210 的 C04（课程 API）；arvinhanye 的 F02、K07；本人待合并的 I03 #219、C09 #220（迁移 005）、E03 #221、B12-R1 #224。本认领提交基于第二批认领提交 `6a93cf3`，与上述 PR 无文本冲突。三项各在独立分支上进行，各子任务只改本节中自己那一张表的状态与证据列。

| 原子 ID | 状态 | 任务 | 负责人 | 分支 / base | 文件锁（本轮唯一写入者） | 证据 |
| --- | --- | --- | --- | --- | --- | --- |
| D09 | DONE（待 PR 审查/合并） | 实现块身份与缓存键 | ArvinHan（Claude 子代理） | `claude/d09-chunk-identity` / 本认领提交 | `src/backend/app/services/chunk_identity.py`、`tests/backend/test_d09.py`、`docs/handoffs/claude-d09.md` | 红：实现前收集错误 `ModuleNotFoundError`；绿：`tests/backend/test_d09.py` 96 passed；后端全量 1146 passed（基线 1050）；反向篡改 5 处（去 course_id、去 model_id、序号补零、修订哈希输入换序、模型 ID 改取响应字段）均变红，改回后 `cmp` 一致；`verify.sh` exit 1 仅因本机缺 `openapi-typescript`（B14 生成类 2 条 + 负例 1 条），base `9116315` 同命令日志逐行相同；`git diff --check` 通过；待决 5 项见 `docs/handoffs/claude-d09.md` |

- D09 验收：同文不同页有独立出处；跨课程不复用身份；提示词/模型变更失效（缓存键用实际给出结果的模型 ID，见 `docs/integrations.md`）；`revision_id` 与块 ID 按 ADR-012 修订 1 确定性派生。验证：`python3 -m pytest tests/backend/test_d09.py -q`。

| 原子 ID | 状态 | 任务 | 负责人 | 分支 / base | 文件锁（本轮唯一写入者） | 证据 |
| --- | --- | --- | --- | --- | --- | --- |
| C16 | IN PROGRESS | 实现 SSE 一次性票据申领 | ArvinHan（Claude 子代理） | `claude/c16-event-tickets` / 本认领提交 | `src/backend/app/api/event_tickets.py`、`src/backend/app/repositories/event_tickets.py`、`src/backend/migrations/006_event_tickets.sql`（D-10：005 已由 C09 #220 占用）、`tests/backend/test_c16.py`、`docs/handoffs/claude-c16.md`；范围扩展：`src/backend/app/main.py` 仅加路由注册 | 待补 |

- C16 验收（`specs/identity-access.md` §5）：仅保存票据哈希；60 秒过期；重复、跨任务或普通 Bearer 查询票据拒绝；迁移可恢复。验证：`python3 -m pytest tests/backend/test_c16.py -q`。

| 原子 ID | 状态 | 任务 | 负责人 | 分支 / base | 文件锁（本轮唯一写入者） | 证据 |
| --- | --- | --- | --- | --- | --- | --- |
| B15 | IN PROGRESS | 建立前端 HTTP 客户端 | ArvinHan（Claude 子代理） | `claude/b15-http-client` / 本认领提交 | `src/frontend/src/api/http.ts`、`tests/frontend/b15.test.ts`、`docs/handoffs/claude-b15.md` | 待补 |

- B15 验收：类型化错误、超时/取消、认证失败处理；组件不自行拼路径；把 `scope.signal` 传给 fetch（B04 交出项）。验证：`npm --prefix src/frontend run type-check && npm --prefix src/frontend run test -- --run ../../tests/frontend/b15.test.ts`。

- 合并约定：三个分支共用本认领提交。若合并前 main 在本文件末尾又有追加导致冲突，由协调方先在 `claude/batch-0925c-claims` 上解决一次，再并入三个分支。C16 的迁移 006 以 C09 #220 的 005 先合并为前提；若 C09 未合并而 C16 先合，按 D-10 改号。
