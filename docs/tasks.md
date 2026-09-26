# 任务看板

## 2026-09-25 Codex 认领：F03

| ID | 状态 | 任务 | 负责人 | 文件范围 | 验收 |
| --- | --- | --- | --- | --- | --- |
| F03 | DONE（PR #246 已合入 `d624208`） | 建立图唯一约束和索引迁移 | Codex（后端） | `src/backend/migrations/neo4j/001_constraints.cypher`、`src/backend/app/repositories/graph_migrations.py`、`tests/integration/test_f03.py`、本节及相关规格/架构/交接 | [PR #246](https://github.com/arvinhanye/SmartSketch/pull/246)；F03 15 passed（一次性 Neo4j 5.26，含审查修复）；最新 main 基线后端 2277 passed；`./scripts/verify.sh` exit 0；`git diff --check` exit 0；交接 `docs/handoffs/codex-f03.md` |

- 输入：F02 Neo4j 驱动、B11/ADR-012 图模型、E07 `EmbeddedVector`；输出：可重跑的 schema 迁移与带空间标识的向量写入边界。
- 依赖：F02、B11 已在当前 `main`。风险：Neo4j DDL 非整体事务；失败后保留已建对象，修复数据或环境后重跑。
- 验证命令：`python3 -m pytest tests/integration/test_f03.py -q`、`./scripts/verify.sh`、`git diff --check`。
- 验收证据：迁移模块缺失、SQLite/CLI 符号缺失、连接关闭泄漏及缺失 SQLite 文件均先红后绿；真实 Neo4j 首次检出向量索引 DDL 缺闭合大括号，新增结构负例先红后修复；独立审查又指出空间错误细节及同名异构 DDL 跳过风险，先加负例后修复并处理 Neo4j 唯一约束配套索引同名；一次性容器中 `tests/integration/test_f03.py` 15 passed。重基到 `origin/main@8985a16` 后虚拟环境 `tests/backend` 2277 passed；虚拟环境 PATH 下 `./scripts/verify.sh` exit 0；详见交接。


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
## 2026-09-25 Codex 认领：C04

| 原子 ID | 状态 | 任务 | 负责人 | 基线与文件锁 | 验收 |
| --- | --- | --- | --- | --- | --- |
| C04 | DONE（PR #225 `64e643a`） | 实现课程列表和创建 API | Codex（后端） | `origin/main@130e6b6`（含 C03 PR #216）/ `codex/c04-courses-api`；独占 `src/backend/app/api/courses.py`、`src/backend/app/services/courses.py`、`tests/backend/test_c04.py`；扩围 `src/backend/app/main.py` 作路由注册、`src/backend/app/schemas/contracts.py` 加载生成 DTO | C04+C03 29 passed、后端 1060 passed、生成物检查 exit 0、`verify.sh` exit 0（UTF-8 输出环境）；[PR #225](https://github.com/arvinhanye/SmartSketch/pull/225) 初次 CI 六项通过；待负责人合并 |

- 输入：C02 课程仓储、C03 身份依赖、ADR-013、`specs/identity-access.md` §3.2/§4.4、`specs/teacher-review-publish.md` V7、`src/contracts/api.v1.yaml`。输出：GET/POST `/api/v1/courses`，只列可见课程；创建课程和创建者教师成员同事务。
- 调用链：H01 页面/状态经 B15 API 客户端消费生成的 `Course`/`CourseCreate`；路由用 C03 `current_user`/`teacher_account`；课程服务调 C02 仓储；SQLite `courses`/`course_members` 持有数据。无 worker、Neo4j、SSE。路径、字段、枚举、错误码和鉴权均沿用 v1 契约；不改真源或生成物。
- 风险：C03 PR #216 已合入 `main@130e6b6`，C04 在该基线上复验；生成 Python DTO 不在后端安装包的导入路径，扩围 `app/schemas/contracts.py` 加载仓库已生成文件，部署打包须由后续 K08 保证携带该文件。无数据库迁移；回滚仅撤销 C04 提交，不触碰 C03。
- 验收命令：`python -m pytest tests/backend/test_c04.py -q`、`python -m pytest tests/backend -q`、`./scripts/gen-contracts.sh --check`（核对契约未漂移）、`./scripts/verify.sh`、`git diff --check`。测试用隔离 SQLite 与 fake 身份数据，覆盖成功、边界、错误、课程隔离和生成 DTO 匹配。
- 实测：C03 基线 17 passed；C04 首个测试先以 404 失败，接入后 9 passed；独立审查指出显式 `description: null` 被生成 Python 模型放宽，新增先失败 HTTP 用例并在路由拒绝，最终 C04 10 passed、后端全量 1029 passed；`gen-contracts.sh --check` exit 0；`verify.sh` 首次因 Windows GBK 控制台无法输出 ✓ 字符 exit 1，设置 `PYTHONIOENCODING=utf-8` 后 exit 0（契约负例 24 项通过）。无前端功能修改，前端类型检查/构建、CI 和合并后验证未运行。
- 集成基线复验（`origin/main@130e6b6`）：C04+C03 定向 29 passed；后端全量 1060 passed；`gen-contracts.sh --check` exit 0；`verify.sh` exit 0（契约负例 25 项通过）。B14 的 3 个用例在本机出现 6 条 GBK 子进程读取警告但均通过。前端功能未改；本机前端类型检查/构建未运行，PR CI 结果见下。
- PR 证据：[C04 PR #225](https://github.com/arvinhanye/SmartSketch/pull/225) 以 main 为目标、差异仅 C04；首次两次 CI 运行的 Repository scaffold、Frontend、Backend 共六项均通过。本文档证据提交后须再次检查最新 CI，不将此视为合并后验证。

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
| M0-02 | DONE（B01～B04 已完成；B15 PR #228 `f37262c`） | 初始化 Vue 3 + TypeScript + Vite 前端 | Frontend Agent | 可启动；具备最小路由、类型检查与测试命令 | B01～B04 见下方验收证据；HTTP 客户端 B15 仍待契约 B14 |
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
| D-01 | **已关闭**：定为自编「数据结构 第3章 栈与队列」（`evaluation/fixtures/synthetic.json`，ADR-026，ArvinHan 2026-09-26）。原题：MVP 首批课程示例和脱敏资料来源。所选材料须覆盖一门完整课程的一章，作为赛题抽取硬指标的基准（REQ-01，`specs/course-knowledge-graph.md` 验收 7）；按赛题第 7 节，只用自编示例或许可允许使用的开源教材 | 产品负责人 | 已完成 |
| D-02 | 首个 OpenAI 兼容模型供应商与预算上限。A07 已拆为 D-02a～f 六项，签收入口见 `docs/integrations.md`「待签收取值（D-02）」；配置形状与规则已定。**D-02a 已签收**：主用 DeepSeek V4.1 Flash（`deepseek-flash`，ADR-027，ArvinHan 2026-09-26）；D-02d 已签收（ADR-028，按占位值），抽取评测付费调用已确认；D-02b、c、e 仍未签收 | 技术负责人 | 接入抽取服务前（fake 实现可先行） |
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
| D-16 | C07 资料列表的 `Document.parse_status` 取自哪里、失败/取消后的「再处理」入口（A03 交出项）。**已关闭**：`parse_status` 在读时取该资料**最新创建任务**的 `stage`（单一事实来源，worker 不另写）；`materials.parse_status` 列不再维护，保留默认值待后续迁移清理。MVP 的再处理只靠**重新上传**（新资料、新任务），不新增端点、不改契约；再处理端点留作后续任务（ArvinHan，2026-09-25） | 技术负责人 | 已完成（C07 落实） |
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
- 交出的后续项（该记录创建时均未认领）：**F02** 草稿查询必带 V；**F03** 贡献字段约束/索引；**F08/F13** 写入登记贡献；**E10/E11** 融合候选按 V 过滤；**G04** 建快照按 V 过滤。

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

## F02 Neo4j 驱动与作用域仓储

| ID | 状态 | 任务 | 负责人 | 分支 / base | 文件锁（本轮唯一写入者） | 证据 |
| --- | --- | --- | --- | --- | --- | --- |
| F02 | DONE（PR #231 已合入 `d4ba033`） | 实现 Neo4j 驱动与作用域仓储 | ArvinHan（Codex） | `codex/f02-neo4j` / `130e6b6` | `src/backend/app/repositories/neo4j.py`、`src/backend/pyproject.toml`、`tests/backend/test_f02.py`、`docs/atomic-task-plan.md`、`docs/atomic-tasks.json`、`docs/handoffs/codex-f02.md`、本节 | `docs/handoffs/codex-f02.md`；F02 聚焦 **74 passed**，后端 **1124 passed**，`./scripts/verify.sh` exit 0，原子计划校验通过，`git diff --check` 通过。全量离线套件 **1405 passed / 3 skipped / 1 failed**；唯一失败为 B07 假工作区缺少 B14 gate 文件，已在干净 base `130e6b6` 复现；本任务未连接真实 Neo4j。PR #231 |

- 验收：仓储对 course/version 参数化并强制草稿 V 与有效任务集合；teacher/student/worker 意图边界、断连错误和凭据日志边界见 handoff。验证：`python3 -m pytest tests/backend/test_f02.py -q`、`python3 -m pytest tests/backend -q`、`./scripts/verify.sh`。

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
| C09 | DONE（PR #220 `b174b2f`） | 实现 worker 原子领取与租约 | ArvinHan（Claude 子代理） | `claude/c09-task-leases` / `36670a3` | `src/backend/app/repositories/task_leases.py`、`src/backend/migrations/NNN_task_leases.sql`（D-10：现取 005）、`tests/backend/test_c09.py`、`docs/handoffs/claude-c09.md`；不改 `repositories/tasks.py`（C03 #216 在改） | `docs/handoffs/claude-c09.md`；迁移 `005_task_leases.sql`（租约六列，另加任务错误三列与 I4 约束，见交接待决 1）；红灯 3 failed + 45 errors（签名桩）→ C09 50 passed；后端 1052 passed；反向篡改 8 处全部检出；#212 要求的「有效租约阻止迁移」真实表回归已补；`verify.sh`、`git diff --check` exit 0；待决 3 项见交接。**ADR-017 追加（2026-09-25）**：决定 1 登记 `docs/architecture.md` 数据模型；决定 6 C08 码表 `LLM_UNAVAILABLE` 放开 `merging`（`failure_code_allowed` 限定为尝试耗尽，`details` 须含 `attempts`、`stage`），C09 耗尽直接写 `LLM_UNAVAILABLE`，§6 补注；红灯 C08 3 failed、C09 1 failed → C08 137 passed、C09 53 passed；后端 1118 passed；篡改 3 处全部检出；`verify.sh`、`git diff --check` exit 0；待决 1、2 已由 ADR-017 解决，待决 3 仍开 |

- C09 验收：两个连接争同一任务只有一个成功；旧租约 token 禁止续写；到期可接管。验证：`python3 -m pytest tests/backend/test_c09.py -q`。

| 原子 ID | 状态 | 任务 | 负责人 | 分支 / base | 文件锁（本轮唯一写入者） | 证据 |
| --- | --- | --- | --- | --- | --- | --- |
| E03 | DONE（PR #221 `7c891eb`） | 实现兼容 API 适配器 | ArvinHan（Claude 子代理） | `claude/e03-compatible-api` / `36670a3` | `src/backend/app/services/ai/compatible.py`、`tests/backend/test_e03.py`、`docs/handoffs/claude-e03.md`；不改 `ai/embeddings.py`（E07 #217 在改） | `test_e03.py` 先红（无模块 exit 2；名字桩 171 failed）后 173 passed；`tests/backend` 全量 1175 passed（基线 1002）；5 处篡改均检出（2/7/2/1/1 failed），恢复后 `cmp` 一致；`./scripts/verify.sh` exit 0、`git diff --check` exit 0；不联网、无密钥；待决 10 项（含向量 HTTP 归属、`max_tokens` 字段名、流式 usage 实测）见 `docs/handoffs/claude-e03.md`；**ADR-017 追加**（决定 2、3）：`CompatibleEmbeddingClient`（`POST /embeddings` 带 `dimensions`/`encoding_format`，按 `EMBEDDING_BATCH_SIZE` 分批且不超过供应商上限（默认 10，取自 D-02c，可传参），按 `index` 还原顺序，逐条核对维度），`integrations.md` D-02a/b 补注输出上限字段与冒烟实测项；新增 118 条先红（桩 117 failed、另 1 条实现中补）后 `test_e03.py` 291 passed，`test_e07.py` 16 passed，`tests/backend` 全量 1341 passed（基线 1223）；3 处篡改（不还原顺序/不核对维度/不分批）检出 3/6/6 failed，恢复后 `cmp` 一致；`./scripts/verify.sh`、`git diff --check` exit 0；待决 1、2 已解决，新增待决 11～14 |

- E03 验收：按 OpenAI 兼容协议实现；用模拟传输测超时、错误与结构；真实调用需另行配置（供应商取值待 D-02a）。验证：`python3 -m pytest tests/backend/test_e03.py -q`。

| 原子 ID | 状态 | 任务 | 负责人 | 分支 / base | 文件锁（本轮唯一写入者） | 证据 |
| --- | --- | --- | --- | --- | --- | --- |
| I03 | DONE（PR #219 `0c8389b`） | 实现可学集合纯函数 | ArvinHan（Claude 子代理） | `claude/i03-eligible-set` / `36670a3` | `src/backend/app/services/learning/eligible.py`、`tests/backend/test_i03.py`、`docs/handoffs/claude-i03.md` | 新增 `services/learning/__init__.py`（包原不存在）。红：先收集错误（无模块），桩函数 79 failed/1 passed；绿：`test_i03.py` 80 passed；`tests/backend` 全量 1082 passed（基线 1002）；`./scripts/verify.sh` exit 0；`git diff --check` exit 0；6 处反向篡改均检出（36/19/3/3/28/2 failed），恢复后 `cmp` 一致。有环、自环、悬空端点（含外课边）、重复 ID、`V=∅` 抛 `GraphIntegrityError`；`mastered` 含外课 ID 抛 `ProgressOutsideGraphError`（§1）；结果按 `kp_id` UTF-8 字节序。见 `docs/handoffs/claude-i03.md` |

- I03 验收：已掌握集合为空、全部掌握、孤立点、多前置、有环、外课 ID；不修改用户的掌握集合。验证：`python3 -m pytest tests/backend/test_i03.py -q`。

| 原子 ID | 状态 | 任务 | 负责人 | 分支 / base | 文件锁（本轮唯一写入者） | 证据 |
| --- | --- | --- | --- | --- | --- | --- |
| B12-R1 | DONE（PR #224 `c1b812e`） | 进度契约错误细节修订（ADR-017 决定 4、5） | ArvinHan（Claude 子代理） | `claude/b12-r1-progress-errors` / ADR-017 提交 | `src/contracts/api.v1.yaml`、`src/contracts/errors.v1.md`、`src/contracts/v1/generated/`、`tests/contracts/test_b12.py`、`specs/learning-path.md`、`docs/handoffs/claude-b12-r1.md` | 改真源前 B12 34 failed / 88 passed，首版 `75a3775` 后 122 passed；追加提交按 ADR-017 勘误把 `field` 改为点路径 `<i>.kp_id`（先 8 failed / 117 passed，后 125 passed），并补 `tests/tooling/test_b07.py` 夹具 `test_b14.py`（tooling 修前 1 failed / 13 passed，修后 14 passed；ADR-017 与 test_b07 属协调方授权的范围扩展）；`tests/contracts tests/tooling` 305 passed；`./scripts/gen-contracts.sh --check` exit 0；`./scripts/verify.sh` exit 0（含 B12 125 项）；生成 TS `tsc --noEmit --strict` exit 0；`git diff --check` exit 0；反向篡改 5 处均被检出；`docs/handoffs/claude-b12-r1.md` |

- B12-R1 验收：`LearningIntegrityDetails` 只含 `request_id`；`PUT /progress` 422 的 `details.fields[].reason = not_in_published_version` 与 `details.graph_version` 有正负例；重新生成且 `gen-contracts.sh --check`、`tests/tooling` 通过。
- ADR-017 同时追加到 C09（#220：决定 1、6）与 E03（#221：决定 2、3），各自在本节表内更新证据。

- 合并约定：三个分支共用本认领提交。若合并前 main 在本文件末尾又有追加导致冲突，由协调方先在 `claude/batch-0925b-claims` 上解决一次，再并入三个分支，保证三者的解决结果一致。
- 进展（2026-09-25）：四项均已合并（#219 `0c8389b`、#220 `b174b2f`、#221 `7c891eb`、#224 `c1b812e`，按此顺序），合并前四者一起试合无冲突。ADR-017 随 #220 入库，勘误行随 #224 入库。

## 2026-09-25 第三批并行（Claude）

D09、C16、B15 的前置均已合并（D09：D08、A07；C16：C03、C06、B10；B15：B02、B14），issue 无人认领、无远端分支。已核对在途工作并避开：539210 的 C04（课程 API）；arvinhanye 的 F02、K07；本人待合并的 I03 #219、C09 #220（迁移 005）、E03 #221、B12-R1 #224。本认领提交基于第二批认领提交 `6a93cf3`，与上述 PR 无文本冲突。三项各在独立分支上进行，各子任务只改本节中自己那一张表的状态与证据列。

| 原子 ID | 状态 | 任务 | 负责人 | 分支 / base | 文件锁（本轮唯一写入者） | 证据 |
| --- | --- | --- | --- | --- | --- | --- |
| D09 | DONE（PR #226 `abc914d`） | 实现块身份与缓存键 | ArvinHan（Claude 子代理） | `claude/d09-chunk-identity` / 本认领提交 | `src/backend/app/services/chunk_identity.py`、`tests/backend/test_d09.py`、`docs/handoffs/claude-d09.md` | 红：实现前收集错误 `ModuleNotFoundError`；绿：`tests/backend/test_d09.py` 96 passed；后端全量 1146 passed（基线 1050）；反向篡改 5 处（去 course_id、去 model_id、序号补零、修订哈希输入换序、模型 ID 改取响应字段）均变红，改回后 `cmp` 一致；`verify.sh` exit 1 仅因本机缺 `openapi-typescript`（B14 生成类 2 条 + 负例 1 条），base `9116315` 同命令日志逐行相同；`git diff --check` 通过；待决 5 项见 `docs/handoffs/claude-d09.md`；**ADR-018 追加**（`686f57c` ADR 本文 + 其后实现提交）：`chunking.py` 增 `CHUNKER_VERSION`/`chunking_version()`，`chunk_identity.py` 增 `revision_parser_version()` 且修订键拒绝缺分块段的 `parser_version`；红：先改测试时收集错误 `ImportError`；绿：`test_d09.py` 154 passed、`test_d08.py` 13 passed；后端全量 1204 passed；篡改 3 处（不校验分块段 11 failed、分块版本丢参数 4 failed、组合换序 6 failed）改回后 `cmp` 一致；`verify.sh` exit 0；`git diff --check` 通过 |

- D09 验收：同文不同页有独立出处；跨课程不复用身份；提示词/模型变更失效（缓存键用实际给出结果的模型 ID，见 `docs/integrations.md`）；`revision_id` 与块 ID 按 ADR-012 修订 1 确定性派生。验证：`python3 -m pytest tests/backend/test_d09.py -q`。

| 原子 ID | 状态 | 任务 | 负责人 | 分支 / base | 文件锁（本轮唯一写入者） | 证据 |
| --- | --- | --- | --- | --- | --- | --- |
| C16 | DONE（PR #227 `7f9eaf1`） | 实现 SSE 一次性票据申领 | ArvinHan（Claude 子代理） | `claude/c16-event-tickets` / 本认领提交 | `src/backend/app/api/event_tickets.py`、`src/backend/app/repositories/event_tickets.py`、`src/backend/migrations/006_event_tickets.sql`（D-10：005 已由 C09 #220 占用）、`tests/backend/test_c16.py`、`docs/handoffs/claude-c16.md`；范围扩展：`src/backend/app/main.py` 仅加路由注册 | 红灯：仅有测试时收集报 `ImportError`（`app.repositories.event_tickets` 不存在）；绿灯：`tests/backend/test_c16.py` 23 passed；后端全量 1073 passed（基线 1050 + 23）；contracts+tooling 4 failed / 269 passed，与基线 `9116315` 相同，均因环境缺 `openapi-typescript`；反向篡改 5 处（存明文、去 `task_id`、去过期、去 `used_at`、去旧行清理）全部检出，改回后 `cmp` 一致；`verify.sh` 退出 1（contracts gate 的 B14 生成回归缺 `openapi-typescript`，基线同样失败）；`git diff --check` 通过；交接 `docs/handoffs/claude-c16.md` |

- C16 验收（`specs/identity-access.md` §5）：仅保存票据哈希；60 秒过期；重复、跨任务或普通 Bearer 查询票据拒绝；迁移可恢复。验证：`python3 -m pytest tests/backend/test_c16.py -q`。

| 原子 ID | 状态 | 任务 | 负责人 | 分支 / base | 文件锁（本轮唯一写入者） | 证据 |
| --- | --- | --- | --- | --- | --- | --- |
| B15 | DONE（PR #228 `f37262c`） | 建立前端 HTTP 客户端 | ArvinHan（Claude 子代理） | `claude/b15-http-client` / 本认领提交 | `src/frontend/src/api/http.ts`、`tests/frontend/b15.test.ts`、`docs/handoffs/claude-b15.md` | 红灯：实现前 exit 1（无法解析 `api/http`）；绿灯：type-check + B15 23 passed，前端全量 4 files / 53 passed，build 通过；7 处反向篡改（不传 signal、401 不回调、超时并入取消、不解析错误体、令牌进 URL、登录 401 回调、参数不编码）均使测试失败，恢复后 `cmp` 一致；`verify.sh` 在补 `openapi-typescript@7.4.4`（仓库外临时安装）后 exit 0，缺该工具时 B14 两例失败与基线相同；待决 8 项见 `docs/handoffs/claude-b15.md` |

- B15 验收：类型化错误、超时/取消、认证失败处理；组件不自行拼路径；把 `scope.signal` 传给 fetch（B04 交出项）。验证：`npm --prefix src/frontend run type-check && npm --prefix src/frontend run test -- --run ../../tests/frontend/b15.test.ts`。

- 合并约定：三个分支共用本认领提交。若合并前 main 在本文件末尾又有追加导致冲突，由协调方先在 `claude/batch-0925c-claims` 上解决一次，再并入三个分支。C16 的迁移 006 以 C09 #220 的 005 先合并为前提；若 C09 未合并而 C16 先合，按 D-10 改号。
- 进展（2026-09-25）：三项均已合并（#226 `abc914d`、#227 `7f9eaf1`、#228 `f37262c`）。合并前各分支并入新 main 并等 CI 转绿：D09 在 `docs/decisions.md` 末尾与 ADR-017 勘误行冲突（按编号保留两段），C16 在 `main.py` 路由注册处与 C04 #225 冲突（两行都保留）；迁移 005（C09）先于 006（C16）入库。合并后 main@`f37262c` 复核：后端 1676 passed、契约与工具 305 passed、前端 53 passed、`./scripts/verify.sh` exit 0；收尾交接见 `docs/handoffs/claude-batch-0925f-closeout.md`。

## 2026-09-25 第四批（Claude）

C07 前置 C03、C05、C06、B09 均已合并，issue #64 无人认领、无远端分支；规格缺口已由 D-16 关闭（本提交同时补注 `specs/task-processing.md`）。其余新任务的前置均在待合并 PR 中（E04←E03 #221、E05←D09 #226、I04←I03 #219、C10←C09 #220），本轮不领。已核对在途工作：539210 的 C04（课程 API，可能同样改 `main.py` 路由注册）；arvinhanye 的 F02、K07；待合并的 #219、#220、#221、#224、#226、#227、#228。本认领提交基于第三批认领提交 `9116315`。

| 原子 ID | 状态 | 任务 | 负责人 | 分支 / base | 文件锁（本轮唯一写入者） | 证据 |
| --- | --- | --- | --- | --- | --- | --- |
| C07 | DONE（PR #230 `e8e9787`；移植 539210 #229 的先授权后解析） | 实现上传及资料列表 API | ArvinHan（Claude 子代理） | `claude/c07-materials-api` / 本认领提交 | `src/backend/app/api/materials.py`、`src/backend/app/services/materials.py`、`src/backend/app/schemas/materials.py`、`tests/backend/test_c07.py`、`docs/handoffs/claude-c07.md`；范围扩展：`src/backend/app/repositories/materials.py` 仅新增列表查询（按 D-16 关联最新任务），`src/backend/app/main.py` 仅加路由注册 | `docs/handoffs/claude-c07.md`；红：仅测试时收集错误（无 `app.services.materials`），服务桩 39 failed；绿：`test_c07.py` 39 passed；`tests/backend` 1089 passed（基线 1050）；contracts+tooling 272 passed、1 failed 为已知基线 `test_b07[0-PASS]`（#224）；6 处反向篡改（去课程隔离、parse_status 取列、取最早任务、去补偿删除、忽略 `UPLOAD_MAX_BYTES`、去重放删除）全部检出，恢复后 `cmp` 一致；`./scripts/verify.sh`、`git diff --check` exit 0；依赖 `python-multipart==0.0.32` 按 ADR-019（`6bc2ec4`）；待决见交接（契约无幂等键、列表排序、请求体上限前置、无任务回退）；**移植 #229（539210，`8514ecc`）先授权再有界解析**：红 3 failed、绿 `test_c07.py` 42 passed，`tests/backend` 1718 passed，contracts+tooling 305 passed，3 处篡改（恢复 `UploadFile` 参数、去实收字节计数、去 `Content-Length` 预检）全部检出且 `cmp` 一致，`verify.sh`、`git diff --check` exit 0；ADR-019 决定 2 同步改写 |

- C07 验收：非法格式/课程越权拒绝；存盘或建任务失败可补偿（删除新落盘的未引用文件）；长处理不堵请求（只建任务、立即返回 202 `UploadAccepted`）；列表 `parse_status` 按 D-16 取最新任务 `stage`。验证：`python3 -m pytest tests/backend/test_c07.py -q`。

## 2026-09-25 第五批并行（Claude）

D10、E04、E05、C10、I04 的前置均已合入 main@`f37262c`（D10：D09 #226、C01；E04：E03 #221、C01；E05：E02、D09 #226；C10：C09 #220、C03；I04：I03 #219），issue 无人认领、无远端分支。已核对在途工作并避开：arvinhanye（Codex）的 F02 #231（`repositories/neo4j.py`、`pyproject.toml`）、K07 #232（`scripts/`）；本人待合并的 C07 #230（`api/materials.py`、`main.py`）。本认领提交基于第四批认领提交并入 main 后的结果。五项各在独立分支上进行，各子任务只改本节中自己那一张表的状态与证据列。

| 原子 ID | 状态 | 任务 | 负责人 | 分支 / base | 文件锁（本轮唯一写入者） | 证据 |
| --- | --- | --- | --- | --- | --- | --- |
| D10 | DONE（PR #234 已合入 `dde2f9a`） | 实现来源块持久化 | ArvinHan（Claude 子代理） | `claude/d10-chunk-store` / 本认领提交 | `src/backend/app/repositories/chunks.py`、`src/backend/migrations/007_chunks.sql`（D-10：main 最大 006）、`tests/backend/test_d10.py`、`docs/handoffs/claude-d10.md` | 交接 `docs/handoffs/claude-d10.md`；迁移 007 新增 `material_revisions`/`task_revisions`/`chunks`（库层不可变触发器，回滚步骤已测）。红灯：仅有测试时收集 `ImportError`（1 error）；绿灯：`test_d10.py` 36 passed（PUB-28/29/30、课程隔离、V2 删除保护）；后端全量 1712 passed（基线 1676 + 36）；contracts+tooling 305 passed；反向篡改 5 处分别 1/4/1/1/1 failed，改回 `cmp` 一致；`verify.sh` exit 0；`git diff --check` 通过。待决 5 项（已提交版本判定注入待 G02、在途任务共享修订的保守保护等）见交接 |

- D10 验收：重复重试不重复写；按课程/文档定位；删除资料策略不破坏已发布引用；块 ID 按 D09/ADR-018 派生，已存在 ID 内容哈希不一致即拒绝（PUB-30）。验证：`python3 -m pytest tests/backend/test_d10.py -q`。

| 原子 ID | 状态 | 任务 | 负责人 | 分支 / base | 文件锁（本轮唯一写入者） | 证据 |
| --- | --- | --- | --- | --- | --- | --- |
| E04 | DONE（PR #235 已合入 `5df4146`） | 实现模型调用预算与退避 | ArvinHan（Claude 子代理） | `claude/e04-call-policy` / 本认领提交 | `src/backend/app/services/ai/policy.py`、`src/backend/app/repositories/model_calls.py`、`tests/backend/test_e04.py`、`docs/handoffs/claude-e04.md`（`model_calls` 表已在 001，无迁移） | 红灯：实现前收集 `ImportError`；绿灯 `tests/backend/test_e04.py` 66 passed（47 个函数）；全量 `tests/backend` 1742 passed（基线 1676 + 66），`tests/contracts tests/tooling` 305 passed；反向篡改 5 处（鉴权被重试、`Retry-After` 不封顶、任务预算 `>=` 改 `>`、预写失败仍发请求、日志输出提示词）各被检出（5/2/1/2/1 failed），改回 `cmp` 一致；`./scripts/verify.sh` exit 0、`git diff --check` exit 0；待决 9 项（含退避变量登记、生成前被拒的 `error_class` 格式）见 `docs/handoffs/claude-e04.md` |

- E04 验收：429/5xx 有界退避，鉴权错误不重试；预算零不发请求；日志无 token/原文；退避参数有上限（A07 交出项）。验证：`python3 -m pytest tests/backend/test_e04.py -q`。

| 原子 ID | 状态 | 任务 | 负责人 | 分支 / base | 文件锁（本轮唯一写入者） | 证据 |
| --- | --- | --- | --- | --- | --- | --- |
| E05 | DONE（PR #236 已合入 `d5bda28`） | 实现块级实体抽取 | ArvinHan（Claude 子代理） | `claude/e05-entity-extraction` / 本认领提交 | `src/backend/app/services/ai/entities.py`、`prompts/extract_entities.yaml`、`tests/backend/test_e05.py`、`docs/handoffs/claude-e05.md` | `docs/handoffs/claude-e05.md`；红灯：实现前收集错误（模块不存在），绿灯 `test_e05.py` 63 passed；后端全量 1739 passed（基线 1676 + 63），contracts/tooling 305 passed；反向篡改 6 处（证据子串、修复一次、修复不超过一次、类型闭集、长度边界、截断）全被抓到；`./scripts/verify.sh` 与 `git diff --check` 通过；提示词升 v2，越锁改 `prompts/MANIFEST.md` 一行（E01 规则要求同提交更新摘要），待协调方确认；长度上限、修复模板、失败块错误码、缓存存储等见交接待决 |

- E05 验收：五类实体、字段范围、证据必须来自输入；坏 JSON 修复最多一次；只用 E02 fake 客户端测试，不需要密钥。验证：`python3 -m pytest tests/backend/test_e05.py -q`。

| 原子 ID | 状态 | 任务 | 负责人 | 分支 / base | 文件锁（本轮唯一写入者） | 证据 |
| --- | --- | --- | --- | --- | --- | --- |
| C10 | DONE（PR #237 已合入 `38f0ad9`） | 实现任务取消服务与 API | ArvinHan（Claude 子代理） | `claude/c10-task-cancel` / 本认领提交 | `src/backend/app/services/task_cancel.py`、`src/backend/app/api/task_cancel.py`、`tests/backend/test_c10.py`、`docs/handoffs/claude-c10.md`；范围扩展：`src/backend/app/main.py` 仅加路由注册 | `test_c10.py` 先收集错误（ImportError）后 33 passed；`tests/backend` 1709 passed（基线 1676）；`tests/contracts tests/tooling` 305 passed；六处反向篡改（去比较并交换条件、终态可再取消、跳过授权、取消清租约、延迟 BEGIN、去 course_id）均被检出；`verify.sh` exit 0；`git diff --check` 通过；待决 5 项（本地响应模型、SQL 所在层、B10F-R01 影响、快照可选字段、SSE 投递）见 `docs/handoffs/claude-c10.md` |

- C10 验收：queued/运行中/完成后/重复取消；取消和写入竞争有确定结果（与 C09 租约令牌同一写入序列）。审查遗留 B10F-R01/R02（取消快照 `cancel_requested` 非必填）若影响响应校验，写入交接待决，不在本任务改契约。验证：`python3 -m pytest tests/backend/test_c10.py -q`。

| 原子 ID | 状态 | 任务 | 负责人 | 分支 / base | 文件锁（本轮唯一写入者） | 证据 |
| --- | --- | --- | --- | --- | --- | --- |
| I04 | DONE（PR #238 已合入 `11425e4`） | 实现四项评分和结构化理由 | ArvinHan（Claude 子代理） | `claude/i04-ranking` / 本认领提交 | `src/backend/app/services/learning/ranking.py`、`tests/backend/test_i04.py`、`docs/handoffs/claude-i04.md` | 红：仅测试时收集错误 `ModuleNotFoundError`（exit 2）；绿：`test_i04.py` 115 passed；全量 `tests/backend` 1791 passed（基线 1676 + 115）、`tests/contracts tests/tooling` 305 passed；反向篡改 8 处（解锁数改出度 24 failed、同分章节秩颠倒 1、去零分母保护 32、求和顺序颠倒 2、去权重校验 3、排序前舍入 1、kp_id 降序 2；单删"至少一项为正"0 failed，因和校验已覆盖），均 `cmp` 恢复；`./scripts/verify.sh` exit 0；`git diff --check` exit 0；待决 4 项见 `docs/handoffs/claude-i04.md` |

- I04 验收：零分母、全零权重、同分、真实解锁数；分量求和等于 score；理由不用 LLM。验证：`python3 -m pytest tests/backend/test_i04.py -q`。

- 合并约定：五个分支共用本认领提交。只有 D10 新增迁移（007）；C10 与 C07 #230 都改 `main.py` 路由注册，后合者解决一行冲突。

## K07 本地 Neo4j 环境启停脚本

| ID | 状态 | 任务 | 负责人 | 分支 / base | 文件锁（本轮唯一写入者） | 证据 |
| --- | --- | --- | --- | --- | --- | --- |
| K07 | DONE（PR #232 已合入 `ddbeb82`） | 复用并审查环境启停脚本 | ArvinHan（Codex） | `codex/k07-dev-scripts` / `130e6b6` | `scripts/_dev-common.sh`、`scripts/dev-up.sh`、`scripts/dev-down.sh`、`tests/tooling/test_k07.py`、`docs/integrations.md`、`docs/handoffs/codex-k07.md`、本节 | `docs/handoffs/codex-k07.md`；K07 **18 passed**，F01 假 Docker **9 passed / 3 skipped**，`./scripts/verify.sh` exit 0，`git diff --check` 通过；review P3 修复后复审无新发现。普通停止保留数据；显式销毁只在精确交互确认后执行 `compose down -v`，绑定目录保留；未运行真实 Compose。PR #232 |

- 验收：缺失 `.env` 时明确报错、不 source 或改写个人 `.env`；默认停止保留数据；销毁须明确交互确认。验证：`python3 -m pytest tests/tooling/test_k07.py -q`、`SMARTSKETCH_SKIP_DOCKER=1 python3 -m pytest tests/integration/test_f01.py -q`、`./scripts/verify.sh`。

## 2026-09-25 第六批并行（Claude）

D11、E08、C11、J03 的前置均已合入 main@`ddbeb82`（D11：C09 #220、C10 #237、D10 #234；E08：E05 #236；C11：C08 #176、C03 #216、B10、C16 #227；J03：E04 #235、E01 #182）。issue #80（D11）、#88（E08）、#132（J03）无人认领、无远端分支；#68（C11）由 539210 于 2026-09-25 16:53 自行分配并标 `status:in-progress`，远端无分支或 PR，经 ArvinHan 授权转由 Claude 执行（同 C02、C10 先例），已在 #68 留言说明。已核对在途工作：main 无未合并 PR；四项文件互不重叠。本认领提交为四个分支共用的 base，各分支只改本节中自己那一张表的状态与证据列。

| 原子 ID | 状态 | 任务 | 负责人 | 分支 / base | 文件锁（本轮唯一写入者） | 证据 |
| --- | --- | --- | --- | --- | --- | --- |
| D11 | DONE（PR #239 `1df4c33`） | 实现解析阶段 worker 编排 | ArvinHan（Claude） | `claude/d11-parse-worker` / 本认领提交 | `src/backend/app/workers/__init__.py`、`src/backend/app/workers/parse_task.py`、`tests/backend/test_d11.py`、`docs/handoffs/claude-d11.md` | `test_d11.py` 42 passed；`tests/backend` 2147 passed（基线 2105 + 42）；`verify.sh` 通过；反向篡改 7 处全部检出；待决（PDF 管线版本 `pdf/1,cleanup/1,headings/1` 待确认等）见 `docs/handoffs/claude-d11.md` |

- D11 验收：已领取任务（C09 租约）经解析 → 分块 → 块身份（D09）→ 来源块持久化（D10）到 `parsing` 完成检查点（T4 `parsing → extracting`，带令牌条件）；解析失败 T9 `DOCUMENT_UNREADABLE`、取消在检查点 T8、租约丢失即停、重启重跑不产生新块；只做解析阶段，不接真实 LLM。验证：`python3 -m pytest tests/backend/test_d11.py -q`。

| 原子 ID | 状态 | 任务 | 负责人 | 分支 / base | 文件锁（本轮唯一写入者） | 证据 |
| --- | --- | --- | --- | --- | --- | --- |
| E08 | DONE（PR #240 已合入 `b28bf99`） | 实现名称归一和重复候选 | ArvinHan（Claude） | `claude/e08-name-normalize` / 本认领提交 | `src/backend/app/services/fusion/__init__.py`、`src/backend/app/services/fusion/normalize.py`、`tests/backend/test_e08.py`、`docs/handoffs/claude-e08.md` | `test_e08.py` 137 passed（红：`ModuleNotFoundError`）；后端全量 2242 passed（基线 2105 + 137）；NFKC/格式字符/ASCII 小写/圆括号别名·注释·公式组/空白规则；候选 `same_key`/`alias`/`containment` 只列不合并，包含限前缀、有效字符 ≥ 2、比 ≥ 3/5、不切拉丁串，「栈/栈帧」「树/二叉树」「图/图灵机」「C/C++」等反例独立；11 处反向篡改均检出、`cmp` 恢复；`./scripts/verify.sh` exit 0、`git diff --check` exit 0；待决 4 项见 `docs/handoffs/claude-e08.md` |

- E08 验收：全半角、空白、括号（含中英文括号内的别名/缩写）归一为确定性键；归一键相同才列为同键候选，名称包含只列候选、不自动合并；误合并反例（如「栈」与「栈帧」、「树」与「二叉树」）保持独立。纯函数、不调模型。验证：`python3 -m pytest tests/backend/test_e08.py -q`。

| 原子 ID | 状态 | 任务 | 负责人 | 分支 / base | 文件锁（本轮唯一写入者） | 证据 |
| --- | --- | --- | --- | --- | --- | --- |
| C11 | DONE（PR #241 已合入 `d93ccbb`） | 实现任务查询与 GET SSE | ArvinHan（Claude） | `claude/c11-task-events` / 本认领提交 | `src/backend/app/api/tasks.py`、`src/backend/app/services/task_events.py`、`tests/backend/test_c11.py`、`docs/handoffs/claude-c11.md`；范围扩展：`src/backend/app/main.py` 仅加路由注册 | `test_c11.py` 先收集错误（ImportError）后 46 passed；`tests/backend` 2151 passed（基线 2105）；`tests/contracts tests/tooling` 323 passed；九处反向篡改（SSE/GET 跳过授权、awaiting_review 不关流、结束事件两条、断开不释放、票据可重用、进度回退推送、去 aclose、不补快照）均被检出；`verify.sh` exit 0；`git diff --check` 通过；待决 7 项（SQL 所在层、本地响应模型/B10F-R01、可选字段、轮询间隔配置、错过 awaiting_review 的收尾、C10 `sse_event` 未消费、心跳节奏）见 `docs/handoffs/claude-c11.md` |

- C11 验收：`GET /api/v1/tasks/{tid}` 与 `GET /api/v1/tasks/{tid}/events` 先验证课程权限（C03，越权同形拒绝、不含快照）；SSE 用 C16 一次性票据；建连首条为当前快照，`awaiting_review` 与终态推送后关流，每连接恰好一条结束事件；15 秒心跳；客户端断开释放监听器（`specs/task-processing.md` §7、TASK-1/3/11/19/20）。验证：`python3 -m pytest tests/backend/test_c11.py -q`。

| 原子 ID | 状态 | 任务 | 负责人 | 分支 / base | 文件锁（本轮唯一写入者） | 证据 |
| --- | --- | --- | --- | --- | --- | --- |
| J03 | DONE（PR #242） | 实现多轮问题改写 | ArvinHan（Claude） | `claude/j03-query-rewrite` / 本认领提交 | `src/backend/app/services/qa/__init__.py`、`src/backend/app/services/qa/rewrite.py`、`prompts/rewrite_query.yaml`、`tests/backend/test_j03.py`、`docs/handoffs/claude-j03.md`；范围扩展：`prompts/MANIFEST.md` 仅 `rewrite_query` 一行（E01 规则要求升版本同提交更新摘要） | `test_j03.py` 94 passed（与 `test_e01.py` 合计 163 passed）；后端全量 2199 passed（基线 2105 + 94）；`verify.sh` 通过；`git diff --check` 通过；反向篡改 8 处均检出；提示词 v2（草稿）；保留轮数等暂定值与 E04 重试不感知截止时刻等待决见 `docs/handoffs/claude-j03.md` |

- J03 验收：历史按轮数/长度裁剪；只接受 `user`/`assistant` 角色，改写前剔除类标记与哨兵（`specs/grounded-qa.md` H2、QA-19）；改写出错、超时、被预算拒绝、输出为空或不合规均保留原问题；问答调用带 `request_id`、不带 `task_id`（ADR-011 修订 2）；只用 E02 fake 客户端测试。验证：`python3 -m pytest tests/backend/test_j03.py -q`。

- 合并约定：四个分支共用本认领提交。无迁移；只有 C11 改 `main.py` 路由注册。

## TD 技术债四项（2026-09-25，Claude）

来源：D11（#239）、J03（#242）、C10/C11 实现中发现的四个问题，ArvinHan 在会话中确认「按建议修改」。

| ID | 状态 | 任务 | 负责人 | 分支 / base | 文件锁（本轮唯一写入者） | 证据 |
| --- | --- | --- | --- | --- | --- | --- |
| TD-01 | DONE（PR #243 `c333bd1`） | PDF 解析器版本格式定稿（ADR-018 修订 1）+ E04 问答截止时间 + 改写预写失败口径 | ArvinHan（Claude） | `claude/pdf-parser-version-tech-debt-e95eaf` / `ddbeb82` | `src/backend/app/services/parsers/pdf_headings.py`、`src/backend/app/services/chunk_identity.py`、`src/backend/app/services/ai/policy.py`、`tests/backend/test_d06.py`、`tests/backend/test_d09.py`、`tests/backend/test_e04.py`、`docs/decisions.md`（ADR-018 修订 1）、`docs/architecture.md`（资料修订一行）、`docs/integrations.md`（调用记录第 1 条、问答链路截止时间）、`specs/grounded-qa.md`（链路时限、P3）、本节、`docs/handoffs/claude-td-01.md` | `docs/handoffs/claude-td-01.md` |
| TD-02 | 见第八批 | 把服务层里读任务行的 SQL 迁到 `repositories/tasks.py` | 见第八批 | C10、C11（#241）、D11（#239）全部合并后再开始 | `src/backend/app/services/task_cancel.py`（C10）、C11 与 D11 服务层中的任务读取、`src/backend/app/repositories/tasks.py` | 验收：只搬迁不改行为；服务层不再直接执行读取 `processing_tasks` 的 SQL（C10 同文件的取消 UPDATE 一并评估是否迁移）；C10/C11/D11 现有测试不改断言即通过 |

TD-01 带出的跟进项：

- **D11（#239）**：worker 删除自拼的 `PDF_PARSER_VERSION`，改为引用 `pdf_headings.CLEANED_PARSER_VERSION`（取值逐字相同，块 ID 不变）；清洗只用默认阈值。 **已完成**（#239）。
- **J03（#242）**：预写失败改用原问题已有测试覆盖；另绑定 E04 截止时间「链路截止 − 预留」并把 `CallDeadlineExceededError` 归为 `timeout`。**已完成**（#242）。
- **J07（未开始）**：收到请求时计算截止时间，经 `ModelCallPolicy.bind(..., deadline=...)` 传给 J03～J05；把 `CallDeadlineExceededError` 映射为 `LLM_UNAVAILABLE`、`details.reason = timeout`（O9）。不要用关闭重试代替。

## 2026-09-25 第七批并行（Claude）

H13、F03、E06 的前置均已合入 main@`8985a16`（H13：C13、B15、B03、B04；F03：F02 #231、B11 #194；E06：E05 #236）。issue #173（H13）、#95（F03）、#86（E06）无人认领、无远端分支。已核对在途工作：C11 #241（`api/tasks.py`、`main.py`）、E08 #240（`services/fusion/`）待审查，与三项文件不重叠。本认领提交为三个分支共用的 base，各分支只改本节中自己那一张表的状态与证据列。

| 原子 ID | 状态 | 任务 | 负责人 | 分支 / base | 文件锁（本轮唯一写入者） | 证据 |
| --- | --- | --- | --- | --- | --- | --- |
| H13 | DONE（PR #244 已合入 `0ae3cf6`） | 实现前端登录页与会话存储 | ArvinHan（Claude） | `claude/h13-login-session` / 本认领提交 | `src/frontend/src/views/LoginView.vue`、`src/frontend/src/stores/session.ts`、`src/frontend/src/api/auth.ts`、`src/frontend/src/router/index.ts`、`src/frontend/src/main.ts`、`tests/frontend/h13.test.ts`、`docs/handoffs/claude-h13.md` | `h13.test.ts` 28 passed；前端全量 81 passed；type-check、build、`verify.sh` 通过；关闭审查遗留 B03-R01′、B04-R01；`docs/handoffs/claude-h13.md` |

- H13 验收：令牌与 `LoginResponse.user` 只存 `sessionStorage`（不存 localStorage/Cookie）；登录后按 `user.role` 进首页；401、429 分别明确提示；收到 401 清会话与课程上下文并回登录页（同时关闭审查遗留 B03-R01′、B04-R01）；口令/令牌不写日志；不解析 JWT 做授权。验证：`npm --prefix src/frontend run type-check && npm --prefix src/frontend run test -- --run ../../tests/frontend/h13.test.ts`。

| 原子 ID | 状态 | 任务 | 负责人 | 分支 / base | 文件锁（本轮唯一写入者） | 证据 |
| --- | --- | --- | --- | --- | --- | --- |
| F03 | 撤回（改由 Codex 执行） | 建立图唯一约束和索引迁移 | ArvinHan（Claude 子代理） | `claude/f03-graph-constraints` / 本认领提交 | `src/backend/migrations/neo4j/001_constraints.cypher`、`src/backend/app/repositories/graph_migrations.py`、`tests/integration/test_f03.py`、`docs/handoffs/claude-f03.md` | Codex 已在做 F03，本认领撤回避免重复；Claude 子代理未提交的草稿留在本地 worktree `f03-graph-constraints`，未推送 |

- F03 验收：同作用域 ID 唯一；版本不同可共存；迁移可重复执行；迁移失败有回滚/修复说明。验证：`python3 -m pytest tests/integration/test_f03.py -q`。

| 原子 ID | 状态 | 任务 | 负责人 | 分支 / base | 文件锁（本轮唯一写入者） | 证据 |
| --- | --- | --- | --- | --- | --- | --- |
| E06 | DONE（PR #245 已合入 `59b2e5a`） | 实现补漏实体抽取 | ArvinHan（Claude 子代理） | `claude/e06-gleaning` / 本认领提交 | `src/backend/app/services/ai/gleaning.py`、`prompts/extract_entities_gleaning.yaml`、`prompts/MANIFEST.md`（一行）、`tests/backend/test_e06.py`、`docs/handoffs/claude-e06.md` | `tests/backend/test_e06.py` 61 passed；`tests/backend` 全量 2338 passed；`./scripts/verify.sh` 通过；交接 `docs/handoffs/claude-e06.md` |

- E06 验收：不开启时零调用；只加遗漏、不复制已有实体；预算和轮数有上限。验证：`python3 -m pytest tests/backend/test_e06.py -q`。

- 合并约定：三个分支共用本认领提交；无 SQLite 迁移；F03 只新增 Neo4j 迁移文件与运行器。

## 2026-09-25 第八批并行（Claude）

C12、E09、H01、C15、K14 的前置均已合入 main@`d624208`（C12：B15、C11 #241；E09：E07 #217、E08 #240；H01：B03、B04、B15、C04；C15：C03、C04、B09；K14：E01、E05 #236、E06 #245）；TD-02 的前置 C10 #237、C11 #241、D11 #239 均已合并。issue #69（C12）、#89（E09）、#113（H01）、#162（C15）、#167（K14）无人认领、无远端分支。已核对在途工作：无未合并 PR。本认领提交为六个分支共用的 base，各分支只改本节中自己那一张表的状态与证据列。

共享文件分配（避免并行冲突）：`src/frontend/src/router/index.ts`、`src/frontend/src/main.ts` 本轮只由 H01 改；`src/backend/app/main.py` 本轮只由 C15 改；`src/backend/app/repositories/tasks.py` 与 `services/task_cancel.py`、`services/task_events.py`、`workers/parse_task.py` 本轮只由 TD-02 改。

| 原子 ID | 状态 | 任务 | 负责人 | 分支 / base | 文件锁（本轮唯一写入者） | 证据 |
| --- | --- | --- | --- | --- | --- | --- |
| C12 | DONE（PR #252 已合入 `f4a91db`） | 实现前端任务流客户端 | ArvinHan（Claude 子代理） | `claude/c12-task-stream` / 本认领提交 | `src/frontend/src/api/taskEvents.ts`、`tests/frontend/c12.test.ts`、`docs/handoffs/claude-c12.md` | `c12.test.ts` 38 passed；前端全量 6 files / 119 passed；type-check、build、`verify.sh` 通过；交接 `docs/handoffs/claude-c12.md` |

- C12 验收：分片帧/CRLF/心跳/重连；终态和卸载关闭；旧课程事件不污染当前课。验证：`npm --prefix src/frontend run type-check && npm --prefix src/frontend run test -- --run ../../tests/frontend/c12.test.ts`。

| 原子 ID | 状态 | 任务 | 负责人 | 分支 / base | 文件锁（本轮唯一写入者） | 证据 |
| --- | --- | --- | --- | --- | --- | --- |
| E09 | DONE（PR #250 已合入 `5072a48`） | 实现向量候选分层 | ArvinHan（Claude 子代理） | `claude/e09-vector-tiers` / 本认领提交 | `src/backend/app/services/fusion/candidates.py`、`tests/backend/test_e09.py`、`docs/handoffs/claude-e09.md` | `test_e09.py` 94 passed（红：`ModuleNotFoundError`；接口变更后先红 12 failed）；后端全量 2615 passed；自动合并/需裁决返回配对，保留组只返回 `kept_count`（不物化，三组计数和 = n(n-1)/2）；边界：`≥ auto_merge` 自动、`review ≤ s < auto_merge` 裁决、`< review` 保留；阈值须有限、`[0, 1]`、`review < auto_merge`，无默认值（D-08 未签收）；跨课程/跨向量空间混传整体拒绝（`VectorIsolationError`）；反向篡改均检出（首版 11 处、变更后 10 处）；`./scripts/verify.sh` exit 0、`git diff --check` exit 0；待决 3 项见 `docs/handoffs/claude-e09.md` |

- E09 验收：课程隔离；阈值顺序非法拒绝；边界等号有明确规则。验证：`python3 -m pytest tests/backend/test_e09.py -q`。

| 原子 ID | 状态 | 任务 | 负责人 | 分支 / base | 文件锁（本轮唯一写入者） | 证据 |
| --- | --- | --- | --- | --- | --- | --- |
| H01 | DONE（PR #251 已合入 `08ecb35`） | 实现课程首页和创建表单 | ArvinHan（Claude 子代理） | `claude/h01-courses-view` / 本认领提交 | `src/frontend/src/views/CoursesView.vue`、`src/frontend/src/composables/useCourses.ts`、`src/frontend/src/api/courses.ts`（如需）、`src/frontend/src/router/index.ts`、`src/frontend/src/main.ts`、`tests/frontend/h01.test.ts`、`docs/handoffs/claude-h01.md` | h01 31 passed；前端全量 6 files 112 passed；type-check、build、`verify.sh`、`git diff --check` 均 exit 0；交接 `docs/handoffs/claude-h01.md` |

- H01 验收：加载/空/错/禁止访问；重复点提交不重复创建；切课正确。验证：`npm --prefix src/frontend run type-check && npm --prefix src/frontend run test -- --run ../../tests/frontend/h01.test.ts`。

| 原子 ID | 状态 | 任务 | 负责人 | 分支 / base | 文件锁（本轮唯一写入者） | 证据 |
| --- | --- | --- | --- | --- | --- | --- |
| C15 | DONE（PR #248 已合入 `83e9038`） | 实现课程成员管理 API | ArvinHan（Claude 子代理） | `claude/c15-course-members` / 本认领提交 | `src/backend/app/api/members.py`、`src/backend/app/services/members.py`、`src/backend/app/main.py`（路由注册）、`tests/backend/test_c15.py`、`docs/handoffs/claude-c15.md` | `tests/backend/test_c15.py` 26 passed；`tests/backend` 2547 passed；`./scripts/verify.sh` 通过；交接 `docs/handoffs/claude-c15.md` |

- C15 验收：仅课程教师可改；重复添加幂等且不降级教师；跨课与非成员拒绝。验证：`python3 -m pytest tests/backend/test_c15.py -q`。

| 原子 ID | 状态 | 任务 | 负责人 | 分支 / base | 文件锁（本轮唯一写入者） | 证据 |
| --- | --- | --- | --- | --- | --- | --- |
| K14 | DONE（PR #247 已合入 `8ad8345`） | 整理提示词工程完整记录 | ArvinHan（Claude 子代理） | `claude/k14-prompt-record` / 本认领提交 | `docs/submission/prompt-engineering.md`、`docs/handoffs/claude-k14.md` | `docs/handoffs/claude-k14.md`；7 个提示词文件的版本、摘要与 3 个调用方版本常量逐条核对一致；`test_e01/e05/e06/j03` 复跑 288 passed（仅 fake 模型）；尚无真实模型评测（K02、K03 未完成） |

- K14 验收：记录版本、用途、输入输出和修改依据；不含密钥或真实课程资料；引用实际评测证据。验证：`git diff --check`，逐条核对验收矩阵与源文档。

| 原子 ID | 状态 | 任务 | 负责人 | 分支 / base | 文件锁（本轮唯一写入者） | 证据 |
| --- | --- | --- | --- | --- | --- | --- |
| TD-02 | DONE（PR #249 已合入 `4eee6b0`） | 把服务层里读任务行的 SQL 迁到 `repositories/tasks.py` | ArvinHan（Claude 子代理） | `claude/td02-task-repo` / 本认领提交 | `src/backend/app/repositories/tasks.py`、`src/backend/app/services/task_cancel.py`、`src/backend/app/services/task_events.py`、`src/backend/app/workers/parse_task.py`、`tests/backend/test_td02.py`、`docs/handoffs/claude-td-02.md` | `test_td02.py` 14 passed；C10/C11/D11 搬迁前后均 121 passed（断言未改）；后端全量 2535 passed；`verify.sh` 通过；交接 `docs/handoffs/claude-td-02.md` |

- TD-02 验收：只搬迁不改行为；服务层不再直接执行读取 `processing_tasks` 的 SQL；C10/C11/D11 现有测试不改断言即通过。

## 2026-09-26 图谱构建主线：E10 认领（Codex）

| 原子 ID | 状态 | 负责人 | 分支 / base | 范围与文件所有权 | 验收与证据 |
| --- | --- | --- | --- | --- | --- |
| E10 | DONE（PR #253 已合入 `cc53c8d`） | Codex | `codex/e10-fusion-design` / `main@5072a48` | `src/backend/app/services/fusion/judge.py`、`prompts/judge_duplicate.yaml`、`prompts/summarize_definition.yaml`、`prompts/MANIFEST.md`、`tests/backend/test_e10.py`、`specs/course-knowledge-graph.md`、`specs/task-processing.md`、`docs/decisions.md`、`docs/handoffs/codex-e10.md`、设计与计划文件 | E10+邻接测试 468 passed；后端全量 2681 passed、1 个既有 warning（本机回环测试以获准运行方式复跑）；`./scripts/verify.sh` 通过；`git diff --check` 通过。独立审查指出的缓存键与提示词标签问题均已修正。 |

- E10 审查修正（Claude，2026-09-26）：归并提示词带两侧名称、`FusionJudge` 可选 `timeout_seconds`、ADR-017 空行与计划文件 skill 引用；`test_e10.py` 28 passed，后端全量 2683 passed，`verify.sh` 通过；交接 `docs/handoffs/claude-e10-review-fixes.md`。
- **输入**：同课候选对、两侧名称/定义与可定位证据；**输出**：带理由、来源引用、模型/提示词元数据的归并提案或独立待审核结果；**依赖**：E09、E04、E01、E05。**风险**：D-08 阈值未签收；E08/E09 合流与稳定候选 ID 由 E12 定；模型引用能验证来源存在，不能自动证明归并语义正确。后两项及缓存失效规则见 E10 设计规格。

## 2026-09-26 E10 之后第一批：E11、H02、H12 并行（Claude）

| 原子 ID | 状态 | 任务 | 负责人 | 分支 / base | 文件锁（本轮唯一写入者） | 证据 |
| --- | --- | --- | --- | --- | --- | --- |
| E11 | DONE（PR #255 已合入 `6742f6a`） | 实现关系两阶段抽取 | ArvinHan（Claude） | `claude/project-thread-sp1d3a` / `main@5072a48`，已合入含 E10 的 `main@cc53c8d` | `src/backend/app/services/ai/relations.py`、`prompts/extract_relations.yaml`、`tests/backend/test_e11.py`；扩围 `prompts/MANIFEST.md` 一行、`docs/submission/prompt-engineering.md`（K14 交接要求同步） | `test_e11.py` 47 passed；E01/E10/E11 144 passed；后端全量 2702 passed（合入 E10 前）；9 处反向篡改均被检出；`docs/handoffs/claude-e11.md` |
| H02 | DONE（PR #255 已合入 `6742f6a`） | 实现资料上传和进度页面 | ArvinHan（Claude 子代理） | 同上 | `src/frontend/src/views/MaterialsView.vue`、`src/frontend/src/composables/useMaterials.ts`、`src/frontend/src/api/materials.ts`、`tests/frontend/h02.test.ts`；扩围 `router/index.ts`、`CoursesView.vue`、`main.ts`（路由与入口） | `h02.test.ts` 53 passed；7 处反向篡改均被检出；`docs/handoffs/claude-h02.md` |
| H12 | DONE（PR #255 已合入 `6742f6a`） | 实现课程成员管理页面 | ArvinHan（Claude 子代理） | 同上 | `src/frontend/src/views/MembersView.vue`、`src/frontend/src/api/members.ts`、`src/frontend/src/composables/useMembers.ts`、`tests/frontend/h12.test.ts`；扩围同 H02 | `h12.test.ts` 33 passed；5 处反向篡改均被检出；`docs/handoffs/claude-h12.md` |

- 依赖：E11 ← E10（PR #253 已合入）、E05；H02 ← H01、C07、C12；H12 ← C15、B15、H01，均在 main。
- 三项合并后验证：前端 `type-check` exit 0、全量 9 files 236 passed、`build` exit 0；`./scripts/verify.sh` exit 0（需 PATH 含 pytest 与 `openapi-typescript@7.4.4`）；`git diff --check` exit 0。H02/H12 都改了 `router/index.ts`、`CoursesView.vue`、`main.ts`，合并时两段各自保留。
- E11 待决（详见交接）：`PREREQUISITE_CUES` 先修表述清单为本任务暂定；小节范围与实体表上限交 E12；关系抽取缓存键未定。
- H02 待决：~~`Document` 无 `task_id`~~、~~无删除资料端点~~ 已由 ADR-021 解决（见下行）；~~前端 50 MiB 上限写死~~ 已由 ADR-022 解决（见下表）。
- E11 `PREREQUISITE_CUES` 暂定清单：ArvinHan 2026-09-26 确认接受。

| 原子 ID | 状态 | 任务 | 负责人 | 分支 / base | 文件锁（本轮唯一写入者） | 证据 |
| --- | --- | --- | --- | --- | --- | --- |
| ADR-021 | DONE（PR #255 已合入 `6742f6a`） | `Document.task_id` 与删除未产生贡献的资料（`deleteDocument`） | ArvinHan（Claude） | 同上 | `docs/decisions.md`（ADR-021）、`specs/task-processing.md`、`specs/identity-access.md`、`src/contracts/`（真源、错误码、生成物）、后端 `materials` 路由/服务/仓储/schema、`tests/backend/test_adr021.py`、`tests/backend/test_c07.py`（键集合）、前端 `materials.ts`/`useMaterials.ts`/`MaterialsView.vue`/`http.ts`/`taskEvents.ts`、`tests/frontend/h02.test.ts` | 后端红 25 failed → `test_adr021.py` 27 passed；后端全量 2757 passed；契约+工具 323 passed；前端红 11 failed → 全量 254 passed；`gen-contracts.sh --check`、`verify.sh`、`git diff --check` exit 0；`docs/handoffs/claude-adr021.md` |
| ADR-022 | DONE（PR #255 已合入 `6742f6a`） | 上传上限经 `getUploadPolicy` 下发，前端不再写死 50 MiB | ArvinHan（Claude） | 同上 | `docs/decisions.md`（ADR-022）、`specs/identity-access.md`、`docs/integrations.md`、`src/contracts/`（真源、生成物）、后端 `api/materials.py`/`schemas/materials.py`/`main.py`、`tests/backend/test_adr022.py`、前端 `materials.ts`/`useMaterials.ts`/`MaterialsView.vue`、`tests/frontend/h02.test.ts` | 后端红 7 failed → `test_adr022.py` 7 passed；后端全量 2764 passed；前端红 7 failed → `h02.test.ts` 79 passed、全量 262 passed；4 处反向篡改均被检出；`type-check`、`build`、`gen-contracts.sh --check`、`verify.sh`、`git diff --check` exit 0；`docs/handoffs/claude-adr022.md` |

## 2026-09-26 PR #255 合并后：K01、K02 并行（Claude）

依赖：K01 ← A07、E11、J06、I04；K02 ← K01、E11。E11 已随 PR #255 合入（`6742f6a`），A07、I04 已在 main；**J06 未完成**，所以 K01 只交付实体与关系部分，问答口径在 README 中标「待 J06」。D-01（基准章节）与 D-02（模型供应商）未签收、付费调用需另行确认，真实模型判定未执行。

| 原子 ID | 状态 | 任务 | 负责人 | 分支 / base | 文件锁（本轮唯一写入者） | 证据 |
| --- | --- | --- | --- | --- | --- | --- |
| K01 | DONE（部分：问答口径待 J06；D-01 已定为本章，ADR-026） | 建立自编标注集及评测口径 | ArvinHan（Claude 子代理） | `claude/project-thread-sp1d3a` / `main@6742f6a` | `evaluation/README.md`、`evaluation/fixtures/synthetic.json`、`docs/handoffs/claude-k01.md` | 自编「数据结构 第3章 栈与队列」3141 字，金标 45 个实体（五类齐全）、40 条关系（四类齐全），证据全部为原文子串、前置关系无环；夹具校验脚本 ALL PASS，4 份篡改副本均被拒；`docs/handoffs/claude-k01.md` |
| K02 | DONE（真实模型已实测：三项硬指标达标，简化融合下的初步结论） | 实现抽取和融合离线评测 | ArvinHan（Claude 子代理 + 联调） | 同上 | `evaluation/evaluate_extraction.py`、`tests/backend/test_k02.py`、`evaluation/reports/extraction-accuracy.md`、`docs/handoffs/claude-k02.md` | 桩实现 46 failed → 46 passed；联调按 README 对齐 4 处，先 5 failed → `test_k02.py` 52 passed（含 K01 夹具用例）；假模型自检在 K01 标注集上跑通，两次输出 sha256 一致，数值全部过线仍判「不可用于判定（假模型）」；`docs/handoffs/claude-k02.md` |

- 本机真实模型运行脚本 `evaluation/run_live_extraction.py`（`tests/backend/test_k02_run.py` 先 12 failed → 13 passed；假模型端到端：16 块、简化融合后 18 个实体、12 条关系，`score` exit 0 且判「不可用于判定（假模型）」；交接 `docs/handoffs/claude-k02-run.md`）。只做同名合并的简化融合，结果是初步数字，最终判定仍需 E12。
- 联调对齐（以 `evaluation/README.md` 为准）：F1 在 precision 或 recall 为 null 时为 null；各指标只统计 `source = "ai"`；按 `judgments.seed` 重算的抽中项有缺判时写「判定不完整」，准确率只统计抽中项；实体数 < 20 直接「未达标」。
- 待决：
  1. ~~D-01~~：已定为本次自编的「栈与队列」一章，`is_final_benchmark` 改为 `true`（ADR-026）。
  2. ~~**D-02**~~：D-02a、D-02d 与付费调用都已确认（ADR-027、ADR-028）。真实模型已在本机跑通并人工全量判定（2026-09-26，`k02-live-20260926T084922Z`，DeepSeek `deepseek-flash`）：AI 实体 74 个、实体准确率 74/74、关系准确率 61/63，结论「达标」，详见 `evaluation/reports/extraction-accuracy.md` 与 `docs/handoffs/claude-k02-judge.md`。
  3. **J06** 完成后补问答夹具（K01 问答部分）并做 K03。
  4. **E11 先修表述清单**：金标 `g-r03`（证据「基于栈的后进先出特性」）不含清单中的表述，E11 会按 `prerequisite_without_cue` 丢弃；是否把「基于」加入清单待实测召回后决定。审查同时指出「基础」「才能」偏宽。
  5. **E12/F13 须对同一小节产出的反向 `PREREQUISITE` 候选做环检测**（PR #255 审查意见，E11 不去重二元环）。
  6. **完整融合后重跑验收 7**：本次是简化融合（仅同名去重），main 上 E12/F13 的 `merging` 也还是直通（ADR-029）。E08～E10 融合接入后，把本章处理到 `awaiting_review`、导出草稿，按报告第 3 节重新抽样判定。
  7. **抽取改进（报告第 5 节）**：小节「3.3.5 栈与队列的比较」关系抽取因 4096 token 输出上限截断；21 条未命中金标关系中 12 条跨小节；`CONTAINS` 被用于「相关」关系（判错 2 条）。
- 看板同步：本次把已合入 main 却仍标「待 PR 审查/合并」或「IN REVIEW」的 24 行改为「DONE（PR #N 已合入 `sha`）」：F02、F03、K07、D10、E04、E05、C10、I04、E08、C11、H13、E06、C12、E09、H01、C15、K14、TD-02、E10、E11、H02、H12、ADR-021、ADR-022。

## 2026-09-26 E11 之后主线：E12、F04、F06、F13（Claude）

| 原子 ID | 状态 | 任务 | 负责人 | 分支 / base | 文件锁（本轮唯一写入者） | 证据 |
| --- | --- | --- | --- | --- | --- | --- |
| E12 | DONE（PR #256 已合入 `fa00164`） | 实现抽取阶段编排和检查点 | ArvinHan（Claude） | `claude/project-thread-sqwla4` / 起于 PR #255 头 `52db31c`，#255 合并后已合入 `main@6742f6a` | `src/backend/app/workers/extract_task.py`、`tests/backend/test_e12.py`；扩围 `src/backend/migrations/008_extraction_checkpoints.sql`、`src/backend/app/repositories/extraction_checkpoints.py`、`docs/decisions.md`（ADR-023）、`specs/task-processing.md`（§8.4 一段） | 红灯：收集 `ImportError`；`test_e12.py` 37 passed（连跑 5 次稳定）；后端全量 2801 passed；8 处反向篡改均检出；`verify.sh` exit 0；`docs/handoffs/claude-e12.md` |
| F04 | DONE（PR #256 已合入 `fa00164`） | 实现草稿节点和来源批写 | ArvinHan（Claude） | 同上 | `src/backend/app/repositories/graph_nodes.py`、`tests/integration/test_f04.py`；扩围 `docs/decisions.md`（ADR-024）、`docs/architecture.md`（来源关联一句） | 红灯：收集 `ImportError`；`test_f04.py` 21 passed（其中 7 个连真实 Neo4j 5.26）；7 处反向篡改均检出；`docs/handoffs/claude-f04.md` |
| F06 | DONE（PR #256 已合入 `fa00164`） | 实现关系事务写入与并发防环 | ArvinHan（Claude） | 同上 | `src/backend/app/repositories/graph_relations.py`、`src/backend/app/services/graph/relations.py`、`tests/integration/test_f06.py`；扩围 `src/backend/app/repositories/neo4j.py`（`write_transaction`）、`src/backend/migrations/neo4j/001_constraints.cypher` 与 `graph_migrations.py`（守卫约束）、`docs/decisions.md`（ADR-025）、`docs/architecture.md` | `test_f06.py` 28 passed（其中 12 个连真实 Neo4j 5.26，连跑 5 次稳定）；8 处反向篡改均检出；后端全量 2801 passed；`verify.sh` exit 0；`docs/handoffs/claude-f06.md` |
| F13 | DONE（PR #256 已合入 `fa00164`） | 完成图持久化 worker 阶段 | ArvinHan（Claude） | 同上 | `src/backend/app/workers/persist_graph.py`、`tests/integration/test_f13.py`；扩围 `src/backend/migrations/009_course_locks.sql`、`src/backend/app/repositories/course_locks.py`、`src/backend/app/services/graph/downgrade.py`、`graph_relations.py`（降级/撤销语句）、`graph_nodes.py`（事务内写入）、`services/graph/relations.py`（事务内写入）、`task_leases.py`（persisting 失败置 `cleanup_pending`）、`tasks.py`（读 V）、`docs/decisions.md`（ADR-029）、`specs/task-processing.md`（§8.4 一段） | `test_f13.py` 27 passed（其中 10 个连真实 Neo4j 5.26，连跑 5 次稳定）；9 处反向篡改均检出；后端全量 2801 passed；`verify.sh` exit 0；`docs/handoffs/claude-f13.md` |

- 依赖：E12 ← D11（#239）、E04（#235）、E11（#255，已合并）；F04 ← F03（#246）、E12。
- 验收：每块失败只重试该块（L2）；在途块数不超过 `LLM_MAX_CONCURRENCY`；取消在块/小节边界生效，在途结果不写检查点（TASK-4）；接管后已结束的块和小节不再调用模型、来源不重复（LEASE-2）；阈值内继续、恰等于阈值继续、超阈值提前判定（TASK-9/10/13）；熔断打开不记失败块并退避释放（LEASE-6）。
- 已决：小节关系抽取失败不计入失败块阈值（ArvinHan 2026-09-26，ADR-023 决定 4）。
- E12 待决（详见交接）：任务快照与 SSE 尚未带 `chunks_done`/`chunks_failed`/`failed_chunks`（C11 接列）；模型调用结果缓存未实现，块中途崩溃会重新计费；小节实体表与提示词长度无上限；检查点保留期清理（§8.6）未实现；生产装配（`ExtractionToolkit` 的模型、输出上限、补漏开关）未接入启动入口；`merging` 阶段 worker 尚无任务承接。

- F04 已决：加锁知识点完全不动，只记为跳过（ArvinHan 2026-09-26，ADR-024 决定 4）。F04 待决：节点状态与低置信度阈值由调用方给（D-08）；§8.4 的「撤销旧贡献 + 写入」同一事务由 F13 组合。
- F06 验收：两个连接并发写 A→B / B→A 恰有一方 `CYCLE_DETECTED`；四个连接并发写成环的四条边恰有一方冲突；读图、环检测与提交在同一写事务里并由课程守卫节点串行（ADR-025）。F06 待决：SQLite 课程写锁 `course_locks` 与 `draft_revision+1` 仍未落地（V4，归 API/发布任务）；ADR-009 自动降级与「撤销旧贡献 + 写入」同一事务由 F13 组合。
- F13 已决（ArvinHan 2026-09-26，ADR-029）：`merging` 先用直通版（不做跨资料融合）；D-08 签收前自动写入的节点和关系状态一律 `draft`。F13 同时补上迁移 009 的 `course_locks` 与 `t6_seq`，F06 待决中的课程写锁表因此已有；`draft_revision+1` 仍归教师编辑（F08）。F13 待决：融合编排（E08～E10 接入 `merging`）无任务承接；D-08 签收后需重算状态；等锁超时消耗一次尝试。

## 2026-09-26 F07 图谱读取（Claude）

| 原子 ID | 状态 | 任务 | 负责人 | 分支 / base | 文件锁（本轮唯一写入者） | 证据 |
| --- | --- | --- | --- | --- | --- | --- |
| F07 | DONE（PR #258 已合入 `608be90`） | 实现草稿图读取与详情服务 | ArvinHan（Claude） | `claude/project-thread-sqwla4` / `main@fa00164`（#256 合并后重开） | `src/backend/app/services/graph/read.py`、`src/backend/app/api/graph.py`、`tests/backend/test_f07.py`；扩围 `src/backend/app/repositories/graph_read.py`（读取 Cypher）、`src/backend/app/schemas/contracts.py`（导出图谱模型）、`src/backend/app/main.py`（注册路由）、`tests/integration/test_f07_live.py`、`docs/decisions.md`（ADR-030） | `test_f07.py` 20 passed；`test_f07_live.py` 4 passed（真实 Neo4j 5.26）；10 处反向篡改均检出；后端全量 2821 passed；`verify.sh` exit 0；`docs/handoffs/claude-f07.md` |

- 验收：教师不带 `version` 读草稿（按 V 过滤），学生只读当前发布版本；空图 200、未发布 404 `GRAPH_NOT_PUBLISHED`、版本不符 404 `NOT_FOUND`；每条来源都有 `page` 或 `section_path`，知识点来源按证据区间定位到解析块并带原文（ADR-030）。
- F07 待决：历史版本读取等 G02 版本表；人工添加且无来源的知识点详情会 500，需 F08 保证新建带来源或改契约；`getKnowledgePoint` 每次整图计算层级。

## 2026-09-26 G 组：发布版本（Claude）

| 原子 ID | 状态 | 任务 | 负责人 | 分支 / base | 文件锁（本轮唯一写入者） | 证据 |
| --- | --- | --- | --- | --- | --- | --- |
| G01 | DONE（PR #259 已合入 `b92c65b`；#106 已关闭） | 实现快照序列化和摘要 | ArvinHan（Claude） | `claude/project-thread-sqwla4` / `main@608be90`（#258 合并后重开） | `src/backend/app/services/versions/snapshot.py`、`tests/backend/test_g01.py`；扩围 `src/backend/app/services/versions/__init__.py`、`docs/decisions.md`（ADR-031） | `test_g01.py` 49 passed；12 处反向篡改均检出；后端全量 2870 passed；`verify.sh` exit 0；`docs/handoffs/claude-g01.md` |
| G02 | DONE（PR #259 已合入 `b92c65b`；#107 已关闭） | 实现版本元数据与发布操作记录 | ArvinHan（Claude） | 同上 | `src/backend/app/repositories/versions.py`、`src/backend/migrations/010_versions.sql`、`tests/backend/test_g02.py`；扩围 `tests/integration/test_f13.py`（009 回滚用例先回滚更新的迁移）、`docs/decisions.md`（ADR-032） | `test_g02.py` 22 passed；10 处反向篡改均检出；后端全量 2892 passed；集成（真实 Neo4j）103 passed、4 skipped；`verify.sh` exit 0；`docs/handoffs/claude-g02.md` |
| G03 | DONE（PR #259 已合入 `b92c65b`；#108 已关闭） | 实现版本图与向量构建 | ArvinHan（Claude） | 同上 | `src/backend/app/services/versions/materialize.py`、`tests/integration/test_g03.py`；扩围 `src/backend/app/services/graph/read.py` 与 `src/backend/app/repositories/graph_read.py`（读版本副本、不回传向量）、`tests/backend/test_f07.py`（1 个用例）、`docs/decisions.md`（ADR-033） | `test_g03.py` 12 passed（其中 11 个连真实 Neo4j 5.26）；8 处反向篡改 7 处检出，第 8 处（删草稿）由 F02 作用域校验兜住；后端全量 2893 passed；集成 115 passed、4 skipped；`verify.sh` exit 0；`docs/handoffs/claude-g03.md` |
| G04 | DONE（PR #261 已合入 `ba761dd`；#109 已关闭） | 实现原子发布指针切换 | ArvinHan（Claude） | `claude/project-thread-sqwla4` / `main@ebb0f42` | `src/backend/app/services/versions/publish.py`、`tests/integration/test_g04.py`；扩围 `src/backend/app/repositories/versions.py`（P4 读取与 T7）、`src/backend/app/repositories/course_locks.py`（`current_holder`）、`src/backend/app/repositories/graph_read.py`（投影加 `merged_from`）、`tests/backend/test_g04_sqlite.py`、`docs/decisions.md`（ADR-034） | `test_g04.py` 19 passed（真实 Neo4j 5.26）；`test_g04_sqlite.py` 3 passed；9 处反向篡改 8 处检出，1 处（C1 提交后仍删副本）补用例后检出；后端全量 2962 passed；集成 134 passed、4 skipped；`verify.sh` exit 0；`docs/handoffs/claude-g04.md` |
| G05 | DONE（待 PR 审查/合并） | 实现发布失败补偿与恢复 | ArvinHan（Claude） | `claude/project-thread-sqwla4` / `main@95d5c9a` | `src/backend/app/services/versions/reconcile.py`、`tests/integration/test_g05.py`；扩围 `src/backend/app/services/versions/publish.py`（C1 改走 reconcile）、`src/backend/app/repositories/versions.py`（过期尝试、课程列表）、`src/backend/app/repositories/graph_read.py`（`stored_version_ids`）、`tests/integration/test_g04.py`（1 行打桩目标）、`src/backend/app/services/versions/snapshot.py`、`src/backend/app/services/versions/materialize.py`、`tests/backend/test_g01.py`（审查修复）、`tests/backend/test_g05_sqlite.py`、`docs/decisions.md`（ADR-036） | `test_g05.py` 14 passed（真实 Neo4j 5.26）；`test_g05_sqlite.py` 2 passed；9 处反向篡改均检出；后端全量 2965 passed；集成 148 passed、4 skipped；`verify.sh` exit 0；`docs/handoffs/claude-g05.md` |
| G06 | DONE（待 PR 审查/合并） | 实现回滚和版本列表 API | ArvinHan（Claude） | `claude/project-thread-sqwla4` / `main@a44c680`（与 G05 同一 PR #264） | `src/backend/app/api/versions.py`、`src/backend/app/services/versions/rollback.py`、`tests/backend/test_g06.py`；扩围 `POST /publish` 路由（ArvinHan 2026-09-26 同意）、`src/backend/app/services/versions/materialize.py`（`copy_version`）、`src/backend/app/main.py`、`src/backend/app/schemas/contracts.py`、`tests/integration/test_g06.py`、`docs/decisions.md`（ADR-041） | `test_g06.py`（后端）15 passed；`tests/integration/test_g06.py` 9 passed（真实 Neo4j 5.26）；7 处反向篡改均检出；后端全量 2980 passed；集成 157 passed、4 skipped；`verify.sh` exit 0；`docs/handoffs/claude-g06.md` |

- 验收：规范化字节键序与数组顺序稳定（PUB-10，乱序构造摘要相同）；端点缺失、来源无效、成环、空图、谱系违规逐条拒绝并符合契约 `PublishBlockedDetails`；`load_snapshot` 读回与原快照逐字节相同、不丢任何属性；PUB-8 排除计数、PUB-9、PUB-11 均有用例。
- G01 待决：从 Neo4j/SQLite 读出可见草稿与修订的装载归 G04（P4～P7）；快照章节带 `parent_id`，而 Neo4j 章节与契约 `Chapter` 尚无此字段，章节层级落地时需同步（ADR-031）。
- G02 验收：同一尝试（幂等键 `version_id`）至多成为一个版本；版本号按课程连续、失败不占号，`(course_id, version)` 唯一；失败行带原因永久可查且不进版本列表；已提交版本不可删改。G02 待决：清扫过期尝试归 G05；租约时长由调用方传入（G04 读 `PUBLISH_LEASE_SECONDS`）。
- G03 验收：物化只写 `(course_id, 新 version_id)`，旧版本副本与发布指针不变，学生照读旧版；向量空间或维度不符、缺向量在连库前失败，缺来源块整体回滚；重试同一版本先删后建、不重复；P9 读回复算摘要一致。G03 已决：已发布知识点对外状态恒为 `approved`、来源类别恒为 `manual`（ArvinHan 2026-09-26，ADR-033 第 5 条）。G03 待决：已发布详情的来源没有原文片段。
- G04 验收：先按 V3 校验（成环、来源无效、空图）再切指针；P7～P11 任一失败、提交指针被移动、写锁超时都保留旧指针且不留副本；版本号无空洞；同课程并发发布或发布与回滚并发返回 `PUBLISH_IN_PROGRESS`；内容未变走幂等路径不占号不写 Neo4j；T7 只完成水位以内的任务，锁释放后的编辑不进本次快照（PUB-1/2/4/5/6/12/21/22/23/35）。G04 待决：`POST /publish` 路由未分配任务（建议并入 G06 的 `api/versions.py`）；G04 依赖 F12 仅因谱系，发布不写审计日志（ADR-034 第 7 条）；过期尝试的清扫归 G05。
- G05 验收：P7～P11 各阶段注入失败（含 SQLite 写失败、Neo4j 删除失败）都保留旧指针，副本或被删除、或置 `cleanup_pending` 且清扫后删除；P8 之后崩溃在租约到期后由清扫执行 C1，之后可再发布；提交与清扫以同一行的条件更新互斥；清扫只删 `failed` 尝试的副本，从不删已提交版本与租约内尝试；补偿与清扫可重复执行（PUB-18/19/20）。G05 另修独立审查（2026-09-26）四项：发布前回收本课过期尝试；清扫已判失败后写入的副本就地删除；悬空章节引用按未归章发布；副本删除/列出按标签匹配（ADR-036 第 6～9 条）。G05 待决：`sweep` 尚未接入 worker 周期回收（A06 §8.6 无调度实现）；孤儿副本与缺副本只告警，处理归 K10；同一审查的其余项（无来源人工节点详情 500，归 F08/F07 口径；worker 清理重试空等课程锁；任务重跑覆盖教师已审核状态）未在本 PR 处理。
- G06 验收：回滚以历史版本内容前滚为新版本（`kind = rollback`、`source_version`），向量随副本复制不调用模型；回滚到当前版本或摘要相同的旧版本幂等；不存在、失败或他课版本 404 且无写入；源副本缺失或向量空间不符时失败、指针不变；回滚不改草稿、不执行 T7，R6 等锁超时仍成功（状态 `revising`，随后发布走幂等纠正）；版本列表按版本号降序、不含失败尝试；三个接口仅限本课程教师（PUB-3/7/15/16/25/26）。G06 待决：学生读取的统一版本解析归 G07。

## 2026-09-26 H03 图谱适配（Claude）

| 原子 ID | 状态 | 任务 | 负责人 | 分支 / base | 文件锁（本轮唯一写入者） | 证据 |
| --- | --- | --- | --- | --- | --- | --- |
| H03 | DONE（PR #262 已合入 `95d5c9a`；#115 已关闭） | 实现契约到 G6 数据适配 | ArvinHan（Claude） | `claude/project-thread-m4mk7n` / `main@ebb0f42` | `src/frontend/src/graph/adapter.ts`、`tests/frontend/h03.test.ts` | `h03.test.ts` 22 passed；11 处反向篡改均检出；前端全量 285 passed；type-check、build、`verify.sh` exit 0；`docs/handoffs/claude-h03.md` |

- 验收：四类边样式两两可区分且带中文图例名；`source/target` 取 `from_id/to_id`，仅 `RELATED_TO` 无箭头；缺端点、外课、重复 ID 的元素不进画布并逐条报告；空图得空数组；元素 ID 为 `kp:`/`rel:` 前缀且按码点排序，输入乱序输出逐字节相同；深冻结输入照常转换，输出不引用输入对象。
- H03 待决：边颜色为占位方案未经设计签收；`rejected`/`low_confidence` 的样式与过滤、`issues` 是否提示给教师，留给 H04/H05。

## 2026-09-26 可开工清单与 issue 同步（Claude，基线 `main@95d5c9a`）

依据 `docs/atomic-tasks.json` 的 `depends_on` 与 GitHub issue 状态计算：以下任务前置全部完成且无人认领。进行中不列入：G05→G06（主线线程，#110/#111 标 `status:in-progress`）、F08（草稿 PR #263，#100 标 `status:in-review`）。

| 原子 ID | 组 | 任务 | 前置（均已完成） | Issue | 备注 |
| --- | --- | --- | --- | --- | --- |
| G07 | 发布版本和补偿 | 实现统一发布版本解析器 | G04 | #112 | 解锁 H11、I01、I05、J01、J02，关键路径优先 |
| H04 | 教师与学生图谱界面 | 实现 G6 生命周期组件 | H03 | #116 | 解锁 H05、H06、H08 |
| F14 | 图存储与教师编辑 | 实现离线重新向量化命令 | E07、D10、F03、G04 | #164 | 与 G05 同属版本/向量区域，开工前核对文件锁 |
| K08 | 评测部署与交付 | 实现前后端与 worker 容器配置 | K07、B05、B01、F13 | #147 | 解锁 K10、K12 |
| K13 | 评测部署与交付 | 实现抽取消融实验 | K02、E06 | #166 | 需真实模型调用，开工前须用户确认预算 |

- 等 F08 合并后可开工：F09、F10（再到 F11、F12）。等 G07：I01、J01、J02。等 H04：H05、H06、H08。
- Issue 同步：关闭已合并任务 #92（E12）、#96（F04）、#98（F06）、#105（F13）、#99（F07）、#106～#109（G01～G04）、#115（H03）、#140（K01，问答口径随 K03）、#141（K02），均附 PR 评论并标 `status:done`；141 个原子任务各有一个 issue，无缺漏。

## 2026-09-26 F08 教师节点编辑与人工编辑锁（Claude）

| 原子 ID | 状态 | 任务 | 负责人 | 分支 / base | 文件锁（本轮唯一写入者） | 证据 |
| --- | --- | --- | --- | --- | --- | --- |
| F08 | DONE（待 PR 审查/合并） | 实现教师节点编辑与手改锁 | ArvinHan（Claude） | `claude/project-thread-z0m8yg` / `main@ebb0f42` | `src/backend/app/services/graph/edit_node.py`、`src/backend/app/api/graph_nodes.py`、`tests/backend/test_f08.py`；扩围 `src/backend/app/repositories/graph_edit.py`（Cypher 与 SQLite 查询）、`src/backend/app/main.py` 与 `src/backend/app/schemas/contracts.py`（各一处注册）、`tests/integration/test_f08.py`、契约（`api.v1.yaml`、`errors.v1.md`、生成物）、`src/frontend/src/api/http.ts` 与 `taskEvents.ts`（错误码副本）、`docs/decisions.md`（ADR-035）、`docs/architecture.md`（错误码表）、`specs/teacher-review-publish.md`（待细化四条） | `test_f08.py` 62 passed（实现前 61 failed）；`tests/integration/test_f08.py` 8 passed（真实 Neo4j 5.26）；后端全量 3024 passed；集成全量 142 passed / 4 skipped；前端 type-check 通过、285 passed（合入 main 后复跑）；`verify.sh` exit 0；`docs/handoffs/claude-f08.md` |

- 验收：后写者 `expected_revision` 过期 → 409 `REVISION_CONFLICT` 带当前内容，不覆盖；教师修改（含只改状态）置 `locked = true`；解锁只能经单独的 `unlockKnowledgePoint`，修改接口带 `locked` 字段 → 422；F04 自动写入跳过加锁节点，解锁后恢复更新；新建知识点必须带至少一条本课程、已提交修订的来源（ADR-035）。
- F08 已决（ArvinHan 2026-09-26，ADR-035）：人工新建节点 `status = approved`、置信度 1.0；任何课程教师均可解锁。
- F08 待决：前端尚无为新建知识点选择来源块的接口与交互（无按资料列块的 API）；审计日志归 F12；删除与合并归 F09/F10。

## 2026-09-26 G07 发布版本解析器（Claude）

| 原子 ID | 状态 | 任务 | 负责人 | 分支 / base | 文件锁（本轮唯一写入者） | 证据 |
| --- | --- | --- | --- | --- | --- | --- |
| G07 | DONE（待 PR 审查/合并） | 实现统一发布版本解析器 | ArvinHan（Claude） | `claude/project-thread-8wzxew` / `main@95d5c9a` | `src/backend/app/services/versions/resolver.py`、`tests/backend/test_g07.py`；扩围 `docs/decisions.md`（ADR-037） | `test_g07.py` 32 passed；13 处反向篡改 10 处直接检出，补 1 个用例后第 11 处检出，余 2 处为多重防护中的冗余分支（见交接）；后端全量 2994 passed；`verify.sh` exit 0；`docs/handoffs/claude-g07.md` |

- 验收：从未发布返回 404 `GRAPH_NOT_PUBLISHED`（带 `version` 亦然，进行中或失败的尝试不算发布）；解析结果不可变，请求内提交 v2 不混读，下一次解析读到 v2（PUB-13）；`?version=1` 在指针指向 v2 时可读，不存在、他课、非正数版本号 404 `NOT_FOUND`（PUB-14 解析部分）；回滚得到新版本号与源版本修订；同一结果提供图谱作用域、`graph_version` 与问答修订过滤；指针或已提交版本损坏报 `INTERNAL_ERROR`，不回退、不缓存。
- G07 待决：F07 `resolve_target`、推荐与问答服务尚未接入解析器（F07 改用后即可读历史版本，完成 PUB-14）；修订列表缓存上限 256 为占位值。

## 2026-09-26 H04 G6 画布生命周期（Claude）

| 原子 ID | 状态 | 任务 | 负责人 | 分支 / base | 文件锁（本轮唯一写入者） | 证据 |
| --- | --- | --- | --- | --- | --- | --- |
| H04 | DONE（待 PR 审查/合并） | 实现 G6 生命周期组件 | ArvinHan（Claude） | `claude/project-thread-3eixq2` / `main@95d5c9a` | `src/frontend/src/graph/lifecycle.ts`、`src/frontend/src/components/GraphCanvas.vue`、`tests/frontend/h04.test.ts`；另含 `src/frontend/package.json`/`package-lock.json`（新增 `@antv/g6`） | `h04.test.ts` 27 passed；16 处反向篡改均检出；前端全量 312 passed；type-check、build、`verify.sh` exit 0；Chromium 冒烟通过；`docs/handoffs/claude-h04.md`；ADR-040 |

- 验收：挂载按容器尺寸建图，尺寸为 0 时推迟；更新走 `setData` + `render`，渲染中连续更新只画最后一次；resize 下一帧合并，`setSize` 后适应视口，隐藏（尺寸 0）与未变不动；销毁后图、观察器、帧、window 监听归零，迟到的建图与渲染不生效；路由来回切换 20 次无泄漏；节点点击回传知识点 ID；加载、空图、失败（可重试）状态与画布无障碍标签。
- H04 待决：H03 的边颜色仍为占位；`rejected`/`low_confidence` 的样式与过滤仍留给 H05；画布本身不可键盘操作，键盘可达由 H11 卡片视图承担。

## 2026-09-26 F14 离线重新向量化（Claude）

| 原子 ID | 状态 | 任务 | 负责人 | 分支 / base | 文件锁（本轮唯一写入者） | 证据 |
| --- | --- | --- | --- | --- | --- | --- |
| F14 | DONE（待 PR 审查/合并） | 实现离线重新向量化命令 | ArvinHan（Claude） | `claude/project-thread-200r6n` / `main@95d5c9a` | `scripts/reembed.py`、`tests/integration/test_f14.py`；扩围 `docs/decisions.md`（ADR-038）、`specs/teacher-review-publish.md`（V12 启动门禁一句）、`src/backend/README.md`（一句） | 红灯：收集错误（`scripts/reembed.py` 不存在）；`test_f14.py` 32 passed（其中 2 个连真实 Neo4j 5.26）；9 处反向篡改均检出；后端全量 2962 passed；集成 165 passed、5 skipped；`verify.sh` exit 0；`docs/handoffs/claude-f14.md` |

- 验收：有未过期租约、课程写锁或任何未完成的发布/回滚尝试即拒绝，不备份、不调模型、不动 Neo4j；按 Neo4j 存量枚举全部文本块、全部草稿知识点（不论状态）与全部已提交副本；模型失败、存量在运行中变化、缺向量或维度不符、已提交副本数不等于 `node_count`、块无原文、记录空间被他人改动时都保留旧空间（旧属性与索引完好）；切换后运行时写入只接受新空间；第 6 步失败退出码 3，重跑完成清理；命令打印回滚步骤。
- F14 与 G05/G06 文件不重叠。F14 待决：K10 Neo4j 备份脚本未实现，暂以 `--neo4j-backup-confirmed` 由操作者确认；worker 入口尚未调用启动门禁（C09 待办，非本任务）。

## 2026-09-26 K13 抽取消融（Claude）

| 原子 ID | 状态 | 任务 | 负责人 | 分支 / base | 文件锁（本轮唯一写入者） | 证据 |
| --- | --- | --- | --- | --- | --- | --- |
| K13 | DONE（真实模型三组已跑，自动比对；人工判定未做） | 实现抽取消融实验 | ArvinHan（Claude） | `claude/project-thread-yswyz2` / `main@a44c680` | `evaluation/ablation.py`、`evaluation/reports/ablation.md`、`tests/backend/test_k13.py`；扩围 `evaluation/prompts/extract_joint.yaml`、`evaluation/README.md`（目录）、`docs/decisions.md`（ADR-045）、`docs/integrations.md`（D-02d 备注） | `test_k13.py` 22 passed；5 处反向篡改均检出；K02/E01 回归通过；`docs/handoffs/claude-k13.md`；#166 |

- 验收：同一标注集、同一模型、同一计分口径记录三组结果、成本与版本；空样本标「空样本」，失败组与未运行组保留行并写明原因；fake 结果一律标「假模型」且不给达标判定。
- 实测（ArvinHan 本机，2026-09-26）：三组全部 ok，合计计费 331155 token。实体召回：单阶段 0.9111、两阶段 0.7556、补漏 0.8222；关系召回：0.4250、0.2000、0.1750；调用次数 17、33、54。详见报告第 4 节。
- 待决：结论只对简化融合、每组单次运行成立；完整融合接入后建议每组至少跑两次并做人工判定，再定生产配置。生产维持两阶段、补漏默认关闭。

## 2026-09-26 K08 应用容器（Claude）

| 原子 ID | 状态 | 任务 | 负责人 | 分支 / base | 文件锁（本轮唯一写入者） | 证据 |
| --- | --- | --- | --- | --- | --- | --- |
| K08 | DONE（待 PR 审查/合并；真实镜像构建未在本机运行） | 实现前后端与 worker 容器配置 | ArvinHan（Claude） | `claude/project-thread-cd4etm` / `main@95d5c9a` | `src/backend/Dockerfile`、`src/frontend/Dockerfile`、`docker-compose.yml`、`tests/integration/test_k08.py`；**范围扩展**：`src/backend/app/workers/__main__.py`、`src/backend/app/workers/runner.py`（仓库原无常驻 worker 入口）、`src/frontend/nginx.conf`、`.dockerignore`、`.env.example`、`docs/integrations.md`「应用容器（K08）」、`docs/architecture.md` worker 行、`docs/decisions.md` ADR-039、本节、`docs/handoffs/claude-k08.md` | `test_k08.py` 22 项：21 passed、1 skipped（真实构建，本机无 Docker 守护进程）；后端全量 2962 passed；F01 9 passed；`verify.sh` exit 0；`docker compose --profile app config` exit 0 |

- 验收：worker 按 A06 §8.1 运行（同机、同 SQLite 卷、`WORKER_PROCESSES` 个进程、启动门禁与 API 相同）；API/worker/web 均有健康检查；密钥只经 `env_file` 进后端三服务；前端 Dockerfile 无构建参数、只 COPY `src/frontend/`，`.dockerignore` 排除 `.env*`。
- K08 待决：镜像真实构建与整套启动未在本机跑（无 Docker 守护进程），须在有 Docker 的机器上跑 `docker compose --profile app up -d --build` 复验；worker 优雅停止不释放在途任务（ADR-039 第 2 条）；`maintenance` 挂点是否接 G05 清扫留给后续任务；镜像基底未钉摘要。

## 2026-09-26 I01 学习进度仓储（Codex 认领）

| ID | 状态 | 任务 | 负责人 | 范围 | 验收 |
| --- | --- | --- | --- | --- | --- |
| I01 | DONE（待 PR 审查） | 实现学习进度仓储 | Codex（后端） | `src/backend/migrations/011_progress.sql`、`src/backend/app/repositories/progress.py`、`tests/backend/test_i01.py`、相关规格/架构/交接 | 用户与课程隔离；原始行和 dormant 行保留；仅允许发布版节点写入；同值无操作及显式覆盖；`write_seq` 与版本提交共用事务序列；I01 6 passed，I01+G02 28 passed，`verify.sh` exit 0；交接 `docs/handoffs/codex-i01.md`。 |

- 输入：已认证 `user_id`/`course_id`、绑定发布版节点集合、原始状态；输出：SQLite 原始进度行及可供 I02 投影的隔离读取结果。
- 依赖：C01、A08、G07 已在本地代码中；I02 负责图谱谱系投影及 HTTP 校验。风险：迁移新增持久表，回滚需停 API/worker 后恢复迁移前 SQLite 备份。
- 验证命令：`.venv/Scripts/python.exe -m pytest tests/backend/test_i01.py tests/backend/test_g02.py -q`、`./scripts/verify.sh`、`git diff --check`。
- 验收证据：审查发现原 `write_progress` 总是另开事务，无法加入 I02 的版本绑定写事务；新增一个用例先因缺少事务入口而失败，修复后 I01 6 passed、I01+G02 28 passed。隔离 worktree 的 `verify.sh` exit 0。此次未重跑后端全量；原始交接记录中的全量结果仅属修复前快照。

## 2026-09-26 第九批并行：F10→F09、I01、J02、H06、H05、H08、K10（Claude）

基线 `main@0b8aa73`；分支 `claude/upbeat-ramanujan-p4ccbq`（各任务在本地子分支开发后合入本分支）。J01 在 PR #271 进行中，不在本批。ADR 号预分配避免冲突：F10 = ADR-047、F09 = ADR-048、I01 = ADR-049、J02 = ADR-050、H06 = ADR-051、H05 = ADR-052、H08 = ADR-053、K10 = ADR-054（不需要 ADR 的任务空号）。SQLite 迁移号：I01 = `011_progress.sql`。

| 原子 ID | 状态 | 任务 | 负责人 | 文件锁（本轮唯一写入者） | 证据 |
| --- | --- | --- | --- | --- | --- |
| F10 | DONE（本分支 `claude/upbeat-ramanujan-p4ccbq`，待 PR 审查/合并） | 实现节点合并与重接边 | ArvinHan（Claude） | `src/backend/app/services/graph/merge_nodes.py`、`tests/integration/test_f10.py`；与 F09 同一执行者顺序修改 `src/backend/app/repositories/graph_edit.py`、`src/backend/app/api/graph_nodes.py` | `test_f10.py` 27 passed（真实 Neo4j 5.26 + SQLite）；红灯为模块缺失；14 处反向篡改全部检出（1 处补强用例后）；扩围 `graph_edit.py`、`graph_nodes.py`（`POST /kp/merge`）、`schemas/contracts.py`、契约 `MergeRequest.expected_revisions`；ADR-047；`docs/handoffs/claude-f10.md` |
| F09 | DONE（同上） | 实现节点删除与关系清理 | ArvinHan（Claude） | `src/backend/app/services/graph/delete_node.py`、`tests/integration/test_f09.py`；共享文件同上 | `test_f09.py` 17 passed（真实 Neo4j + SQLite，并发用例连跑 5 次通过）；9 处反向篡改全部检出（1 处补强用例后）；扩围 `DELETE /kp/{kid}`（204，可选 `expected_revision`）与契约；ADR-048；`docs/handoffs/claude-f09.md` |
| I01 | SUPERSEDED（`main` 已合入 Codex 的 I01，PR #272；本批实现未采用） | 实现学习进度仓储 | ArvinHan（Claude） | `src/backend/app/repositories/progress.py`、`src/backend/migrations/011_progress.sql`、`tests/backend/test_i01.py` | 本批实现（提交 `9b9231e`，含读时投影与 46 个用例）在合入 `main` 时让位于 PR #272；投影逻辑可供 I02 参考 |
| J02 | DONE（同上） | 实现图结构检索 | ArvinHan（Claude） | `src/backend/app/repositories/graph_search.py`、`tests/integration/test_j02.py` | `test_j02.py` 38 passed（真实 Neo4j 5.26）；15 处反向篡改检出 13，存活 2 处为冗余防护；上限在 Cypher `LIMIT` 生效（缺省 2 跳/30 节点，硬上限 3 跳/200）；ADR-050；`docs/handoffs/claude-j02.md` |
| H06 | DONE（同上） | 实现知识点详情和来源浏览 | ArvinHan（Claude） | `src/frontend/src/components/KnowledgeDetail.vue`、`src/frontend/src/composables/useKnowledgeDetail.ts`、`tests/frontend/h06.test.ts` | `h06.test.ts` 47 passed；16 处反向篡改全部检出；扩围新建 `api/knowledgeDetail.ts`；未接入页面（留 H11）；ADR-051；`docs/handoffs/claude-h06.md` |
| H05 | DONE（同上） | 实现图搜索筛选与布局切换 | ArvinHan（Claude） | `src/frontend/src/composables/useGraphFilters.ts`、`src/frontend/src/components/GraphToolbar.vue`、`tests/frontend/h05.test.ts` | `h05.test.ts` 44 passed；21 处反向篡改全部检出；真实 G6 Chromium 冒烟通过；扩围 `graph/lifecycle.ts`（`setLayout`、状态样式）、`GraphCanvas.vue`（`layout` 属性）、architecture 一行；ADR-052；`docs/handoffs/claude-h05.md` |
| H08 | DONE（同上；后端无 `/relations` 路由，仅假 API 验证） | 实现教师连边编辑交互 | ArvinHan（Claude） | `src/frontend/src/components/RelationEditor.vue`、`src/frontend/src/composables/useRelationEditor.ts`、`tests/frontend/h08.test.ts` | `h08.test.ts` 35 passed；11 处反向篡改全部检出；扩围新建 `api/relations.ts`；ADR-053；`docs/handoffs/claude-h08.md` |
| K10 | DONE（同上；compose 整套实机演练待人工） | 建立备份和恢复演练 | ArvinHan（Claude） | `scripts/backup-demo.sh`、`scripts/restore-demo.sh`、`tests/integration/test_k10.py` | `test_k10.py` 20 passed（含 neo4j-admin dump/load 真实 Docker 容器）；13 处反向篡改全部检出；`.gitignore` 增 `backups/`；ADR-054；`docs/handoffs/claude-k10.md` |

- 共享文件（`docs/decisions.md`、`docs/architecture.md`、`src/contracts/`、`src/frontend/src/api/`、`src/frontend/src/router/`）的扩围改动由各执行者在交接中列明，合入本分支时由协调者解决冲突。
- 合并后复验（协调者，HEAD 含八项合入）：后端 + 契约 + tooling 3465 passed；集成（真实 Neo4j 5.26）321 passed、3 skipped、1 failed——`test_k08.py::test_images_build`，本机 Docker 构建拉镜像遇 Docker Hub 429/构建内无网络，属环境问题，此前无 Docker 守护进程时该用例跳过，K08 镜像实机构建仍待人工复验；前端 438 passed、type-check 与 build 通过；`./scripts/verify.sh` 通过；`git diff --check` 干净。
- 第九批待决（均需 ArvinHan）：ADR-047～054 签收；F10/F09 删除或合并后抽取重建同 ID 节点（F04 查 `merged_from` 或删除留墓碑）；关系是否加修订号（H08）；后端缺关系编辑路由 `/relations`（F06 仅服务层，H08 未联调）；H06 学生端资料名来源；J02 检索上限占位值；K10 compose 下 neo4j-admin 卷挂载与 F14 `--neo4j-backup-confirmed` 换接 K10 备份。
- 本批合入后新解锁：F11、F12（F10+F09）、H07（H06+F09）、H11（H05+H06）、I02（I01）；J04 待 J01（PR #271）合并。

## 2026-09-26 J01 发布来源向量检索（Claude）

| 原子 ID | 状态 | 任务 | 负责人 | 分支 / base | 文件锁（本轮唯一写入者） | 证据 |
| --- | --- | --- | --- | --- | --- | --- |
| J01 | DONE（PR #271，已合并 main 解决冲突） | 建立发布来源向量检索 | ArvinHan（Claude） | `claude/project-thread-sqwla4` / `main@5ff441b` | `src/backend/app/repositories/vector_search.py`、`tests/integration/test_j01.py`；扩围 `docs/decisions.md`（ADR-046） | 红灯：收集错误（模块不存在）；`test_j01.py` 16 passed（真实 Neo4j 5.26）；9 处反向篡改 7 处检出，余 2 处为冗余防护；后端全量与 `verify.sh` 见 `docs/handoffs/claude-j01.md` |

- 验收：只返回本课程、修订属于绑定版本修订列表的文本块，他课和版本外新修订即使更近也不返回；近邻被挤占时自动扩大取数补足召回，到 `max_fetch` 封顶时告警并返回已有结果；无命中或修订列表为空时返回空；查询向量空间、维度、数值不符和草稿作用域在查询前拒绝；当前空间没有索引时抛仓储错误。
- J01 待决：运行时没有任何环节为文本块写向量（F04/F13 只建 `Chunk` 节点，G03 只为知识点算向量，仅 F14 迁移会写），J04 以后接上问答之前需要先补上这一步；`fetch_factor`、`max_fetch` 为占位值（ADR-046）。

## 2026-09-26 J04 检索合并与上下文预算（Claude）

| 原子 ID | 状态 | 任务 | 负责人 | 分支 / base | 文件锁（本轮唯一写入者） | 证据 |
| --- | --- | --- | --- | --- | --- | --- |
| J04 | DONE（待 PR 审查/合并，issue #133；**独立审查 APPROVE_WITH_NOTES，必改项已修**） | 实现检索合并与上下文预算 | ArvinHan（Claude） | `claude/project-thread-ohmwyv` / `main@a7d8075` | `src/backend/app/services/qa/context.py`、`tests/backend/test_j04.py`；扩围 `docs/decisions.md`（ADR-065）、`specs/grounded-qa.md`（Q3.1 与「待细化」各一条） | 红灯：收集错误（模块不存在）；`test_j04.py` 44 passed；21 处反向篡改全部检出；后端全量 3146 passed；审查独立复跑 44 passed / 全量 3146 passed / 4 处反向篡改检出；已修 docstring 接线示例（M1）并把 ①② 落成规格文字；`verify.sh` 通过；`docs/handoffs/claude-j04.md` |

- 验收：两路候选按 `chunk_id` 去重并保留出处（`origins`、`kp_ids`）；他课、修订不在绑定版本内、不可定位或读不到的块不获得编号（QA-17）；H 为空 → `no_retrieval_hit`，H 非空但无向量候选达到 fake 阈值 → `below_similarity_threshold`（QA-6、QA-7 的 J04 部分）；token 预算整块取舍，不截断文本与定位；图谱上下文无编号。
- J04 待决：阈值与 `ContextBudget` 三个值无缺省，待 K01 调参、J07 配置；「只有向量相似度能打开闸门」与「预算放不下任何块时按 `below_similarity_threshold` 拒答」待签收（ADR-065）；运行时文本块向量写入缺口（J01 待决）仍未补，接上前问答总会拒答。
