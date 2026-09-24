# 分支成果导入映射（A10）

- **任务**：原子任务 A10「整理已有成果导入顺序与任务映射」（`docs/atomic-task-plan.md`）
- **状态**：**已签收**。第 2 节的决定（PLAN-D04a～d、S03-1、N1～N5、ID-1～4）由 ArvinHan 于 2026-09-23 按「建议」一栏全部签收，记为 **ADR-016**；PLAN-D05 不属本文件，仍待产品负责人。本文件本身不触发任何合并，各批由表中执行人另开 PR
- **基线**：main `6881ffe`（合入 PR #13 后）
- **导入来源**：`claude/worktree-contract-conflicts-740adb` @ `978671e`。它已完整包含 `claude/tech-plan-review-improvements-ff30e0` @ `6ccbe5e` 与 `claude/multi-agent-contract-format-209be9` @ `bef9b91`（`git merge-base --is-ancestor` 核对），因此「两个 worktree 的 diff」合并为一份：`740adb` 相对共同基线 `05d214c` 的 92 个文件
- **同时在途**：PR #16（FIX-R01/R02，Claude）、PR #14（B05，Codex）、PR #15（B01，Codex）；Codex A08 在 `codex-a08-learning-path` 有未提交的 `specs/learning-path.md`

## 1 结论

1. **以 main 为集成基线，不对 `740adb` 做 `git merge`（PLAN-D04a、b，已签收）。** main 已合入 13 个 PR（ADR-004、009～014 均已签收），`740adb` 仍停在 9 月 22 日的基线上。整枝合并会同时撞上 10 个双方都改过的文件，还会把 main 已否决或已取代的内容（例如失败即放行的钩子、旧状态机表述、按 Pydantic 写的 ADR-004 旧稿）带回来。建议改为按批从 `978671e` 检出文件，每批一个 PR、只含一个功能边界。
2. **92 个文件的处置**：导入 56，待决 13，不导入 12，随任务导入 6，逐段合并 3，部分导入 2（第 4 节逐文件列出）。不导入的 12 个都已有 main 的签收成果取代，或与之相反。
3. **契约批次不能原样搬入。** 在 `740adb` 自身的副本上补齐生成物后，门禁全部通过（exit 0）。叠到 main 副本上则失败：命名门禁报 6 处，21 项负向测试中 17 项崩溃。原因有三：main 仍用 `SourceChunk`（待 N1 统一）；门禁把 main 里「`RELATED`、`APPLIES_TO` 不得使用」这类说明行当成违规；门禁和测试夹具要求 `specs/grounded-qa.md`、`specs/learning-path.md`，这两份分别要等 A09、A08。见第 3 节批 1。
4. **命名与已签收决定冲突。** 分支的 ADR-008（命名基线）与 main 的现行文档及后来签收的 ADR-011、012 在 5 处用了不同名字，wire 契约与 A04 规格之间也不一致（`document_id` 与 `material_id`）。需先签 N1～N5（第 2 节）。
5. **进度风险最高。** S2 方案 §4.2 写明项目周期为 2026-09-16 至 **10-08（提交截止）**；今天（09-23）处在 M1「主链路打通」窗口（09-20～09-26）。main 目前还没有任何运行时代码；这一日期 main 的任务板里没有记录，只存在于 `740adb` 的任务文件中。
6. **原子清单有缺口**：参赛材料（S2 定稿、PPT、视频、S5、合规自检等）、消融实验、登录与成员管理、重新向量化命令都没有承接任务（第 6 节）。

## 2 需要签收的决定

签收人一栏写角色；本项目目前各角色都由 ArvinHan 担任。

> **签收**：ArvinHan 2026-09-23，按下表「建议」一栏全部签收（N5 即交 A09 定名；PLAN-D05 只是引用，不在本次签收范围）。决定与理由记为 `docs/decisions.md` ADR-016。

| ID | 问题 | 选项 | 建议 | 签收人 | 阻塞 |
| --- | --- | --- | --- | --- | --- |
| **PLAN-D04a** | 集成基线 | main；`740adb` | **main**：所有已签收决定都在 main | 项目负责人 | 全部批次 |
| **PLAN-D04b** | 导入方式 | 按批检出文件，每批一个 PR；整枝 `git merge` | **按批检出**：每批最多一个功能边界，冲突在单批内解决；提交信息写明来源提交与路径 | 项目负责人 | 全部批次 |
| **PLAN-D04c** | 合并权 | 维持现行做法；另设规则 | **维持现行做法**：Agent 只开 PR、不直推 main；ArvinHan 合并；Claude 与 Codex 交叉审查；`verify.sh` 与 CI 须通过。取代分支 `AGENTS.md` §6 的「分支与合并（提案）」和分支的 D-04 | 项目负责人 | 全部批次 |
| **PLAN-D04d** | 批次顺序 | 见第 3 节 | 先合 #16、#14、#15，再批 0→批 1→批 3→批 4→批 5→批 6；批 2 可与其他批并行。批 1、3、4 都改 `docs/architecture.md` 模块表与 `README.md` 目录树，须依次合入 | 项目负责人 | — |
| **S03-1** | 分支 S-03 把三个共享文件拆成目录，采纳多少 | A 只拆 ADR；B 三处全拆（ADR、任务板、门禁分发器）；C 都不拆 | **A**：ADR 拆分已由 ADR-004 签收为目标形态，且 `decisions.md` 是冲突最多的文件；任务板拆成 M0～M4 与现行原子清单的编排方式不符，Codex 的审查流程也按单文件任务板读取；门禁分发器交 B07/K11 在真实前后端门禁出现时再定。选 C 需修订 ADR-004 的文件形态条款 | 技术负责人 | 批 5 |
| **N1** | Neo4j 文本块标签 | `Chunk`；`SourceChunk` | **`Chunk`**：ADR-008、S2、结构关系 `HAS_CHUNK` 与 wire 字段 `chunk_id` 一致；main 现行文档共 4 处需改：`docs/architecture.md`、A04 规格（这两处在命名门禁扫描范围内），以及原子清单 D10 的输出说明（md 与 json 各一）；交接、ADR 叙述等历史记录不改 | 技术负责人 | 批 1、批 5 |
| **N2** | 资料实体名 | `Document` / `document_id`；`Material` / `material_id` | **`Document`**：wire 契约（ADR-004 真源）的 `SourceRef`、`Citation`、`Document` 都已用它；需改 A04 快照格式的 `material_id` 与架构 SQLite 列表 | 技术负责人 | 批 5 |
| **N3** | 模型调用表 | `ModelCall` / `model_calls`；`LlmCall` / `llm_calls` | **`model_calls`**：ADR-011 修订 2 已签收，且记录向量调用，`llm_calls` 名不副实 | 技术负责人 | 批 5 |
| **N4** | 版本表 | `GraphVersion`；`GraphSnapshot` / `snapshots` | **`GraphVersion`**：ADR-012 已签收，wire 也用 `GraphVersion` | 技术负责人 | 批 5 |
| **N5** | 问答记录 | `ChatLog` / `chat_logs`；`QuestionSession` | **交 A09 定**：两者都没有签收依据，A09 定义问答终态时一并定名 | 技术负责人 | A09 |
| **ID-1** | 分支 S-06 重号 | — | 「补规格、外部方案链接、推进 D-01」改记 **S-08**（S-07 已被合并任务占用）；「两项范围决策」保留 S-06 | 协调 Agent | 批 6 |
| **ID-2** | 分支 M0-06 重号 | — | `ff30e0` 的「命名统一」（已完成）保留 M0-06；`740adb` 任务板上的「按 ADR 同步规格」（未开始）改记 **M0-11**，其范围已被 A02～A05 与批 5、6 覆盖，不再单独执行 | 协调 Agent | — |
| **ID-3** | M1-05 含义不同 | — | main 的 M1-05（教师审核与发布）保持；分支 M1-05（Neo4j 写入）映射到 F02～F04、F13，不进 main 任务板 | 协调 Agent | — |
| **ID-4** | 分支 D-04～D-08 | — | D-04 并入 PLAN-D04；D-07 并入 PLAN-D05；D-08（融合与低置信度阈值）**以原编号新增到 main「待确认决策」**，E09/E10 开工前签；D-05（M1-05 全栈拆分）因原子清单已拆分而退役；D-06 分支已关闭。D-04～D-07 在 main 不复用 | 协调 Agent | — |
| **PLAN-D05** | 学习材料与目标路径是否纳入 | 已在任务板 | 本文件不代批；它决定批 6 与 ADR-007 | 产品负责人 | 批 6 |

## 3 导入批次

每批一个 PR，只含一个功能边界，由表中负责人执行；本任务（A10）不执行任何批次。「必须同时做」是该批合入前的停止条件，缺一项不合入。

| 批 | 功能边界 | 文件 | 前置 | 执行 | 必须同时做 | 验证与补测 |
| --- | --- | --- | --- | --- | --- | --- |
| **先合** | 在途 PR | #16、#14、#15 | 各自审查通过 | ArvinHan | — | 各 PR 自带 |
| **0** | 规划文档对齐 | `docs/atomic-tasks.json`、`docs/atomic-task-plan.md`、`docs/reviews/validate_atomic_plan.py` | PLAN-D04 签收 | 协调 Agent | 按 ADR-004 映射改写 B08～B14、O02、O05 的文件白名单（ADR-004 明确交给 A10 导入批次）；按第 6 节补登缺口任务；校验脚本写死的 127 项改为读取实际数量 | `validate_atomic_plan.py` exit 0；`verify.sh` |
| **1** | 契约真源与生成链（ADR-004 / M0-09 第二步） | `src/contracts/**`、`scripts/gen-contracts.sh`、`scripts/gen_contracts.py`、`scripts/check_contracts.py`、`scripts/verify/contracts.sh`、`tests/contracts/**`、`.github/workflows/ci.yml`、`scripts/verify.sh` 一行；交接 s01、s07、m0-04 | 批 0；**N1 签收** | 后端 Agent | ① 按真源重新生成全部产物（含 `python/`、`typescript/`）并入库，删去 `--allow-scaffold`；② main 文档中 `SourceChunk` 按 N1 改名；③ 命名门禁不再把「不得使用」说明行当违规；④ 扫描清单与测试夹具按**执行时 main** 中实际存在的规格确定：`learning-path.md` 已随 PR #19 合入，保留在清单中；`grounded-qa.md` 在 A09（PR #20）合入前暂缓，合入后加回，每份规格加回时都用一处针对该文件的错误命名负例证明门禁 exit 1（A10-R01）；⑤ `src/contracts/README.md` 的 `not_covered_reason` 改 `reason`；⑥ CI 按 `toolchain.txt` 版本锁安装 `pyyaml`、`openapi-spec-validator`、`jsonschema`、`datamodel-code-generator`、`openapi-typescript`；⑦ main `verify.sh` 加一行调用 `scripts/verify/contracts.sh` | 本机：`gen-contracts.sh --check`、`verify.sh`、21 项负向测试 exit 0；CI 绿；另加负例：临时写回一处 `SourceChunk` 门禁须 exit 1。注意：生成器在独立 venv，门禁依赖在另一个解释器，只把 `datamodel-codegen` 加进 PATH，不要让 venv 的 `python3` 顶替 |
| **2** | 本地 Neo4j 环境 | `docker-compose.yml`、`scripts/dev-up.sh`、`dev-down.sh`、`_dev-common.sh`、`check-apoc.sh`、`.env.example` 与 `docs/integrations.md` 的存储/Neo4j 容器部分；交接 m0-05 | PLAN-D04 | **F01 执行，随后 K07** | F01 白名单需扩到 `.env.example`、`docs/integrations.md` 两处（A07 已定分段归属） | F01 验收：配置检查、APOC 实测、停启后数据仍在；K07：普通停止保留数据、删卷须确认 |
| **3** | 资产与参考目录约定 | `prompts/**`、`evaluation/**`、`datasets/**`、`NOTICE`、`.gitignore` 增补、`docs/references.md`、`docs/references/**`、`AGENTS.md` 角色表中数据与 AI 一行、`docs/architecture.md` 模块表两行、`README.md` 目录树；交接 s04 | PLAN-D04 | 协调 Agent | 参考笔记去掉本机绝对路径 | `git check-ignore` 确认 `datasets/raw/x.pdf`、`evaluation/reports/x` 被忽略；`verify.sh` |
| **4** | 后端分层与测试目录说明 | `src/backend/app/{repositories,schemas,services,workers}/`、`src/backend/app/api/README.md`、`tests/README.md`、`tests/backend/README.md`、`tests/frontend/README.md`、架构模块表 schemas 一行 | **#14（B05）已合入** | 后端 Agent | 不导入 `api/__init__.py`（B05 已建） | B05 的 `tests/backend` 仍通过；`verify.sh` |
| **5** | ADR 拆分与命名基线 | `docs/decisions/**`、`docs/decisions.md` 改为索引、`AGENTS.md`/`CLAUDE.md` 中 ADR 位置、架构「核心数据模型」、规格节点字段；交接 s03、s05、m0-06 | **S03-1、N1～N4 签收**；没有未合并的 PR 改动 `decisions.md` | 协调 Agent | 拆分文件以 main 已签收正文生成；ADR-005/006 以历史记录导入：状态标为 **SUPERSEDED**（被 ADR-010/011 取代，成环失败另由 ADR-009 收窄），文件首段与索引都写明不得作为现行状态转换或取消规则的依据，现行规范为 `specs/task-processing.md`；正文保留原样仅供追溯（A10-R02）。ADR-008 写入 N1～N4 修订；全仓把「见本文件下文」一类引用改成文件链接 | 每个 `ADR-0xx` 引用都能解析到文件；旧核对脚本改读新路径后重跑；`verify.sh` |
| **6** | 范围与产品规格 | `docs/product.md`、`specs/course-knowledge-graph.md` 验收 7～10 与关联任务、ADR-007、D-01 选项清单；交接 s06（两份） | **PLAN-D05 签收** | 产品/协调 Agent | 学习材料行去重；验收 9、10 的数值与 S2 核对 | `verify.sh`；逐条对照 S2 |

**批后收尾**（需另行同意）：全部批次合入后，给 `740adb`、`ff30e0`、`209be9` 打归档标签，再移除它们的 worktree 与本地分支。

## 4 逐文件映射

「来源」列出引入或改动该文件的分支：`209be9`、`ff30e0`、`740adb`（自身修复），以及 `740adb-merge`（其合并提交中的冲突解决）。「main 现状」相对共同基线 `05d214c`。

| 文件 | 状态 | 来源 | main 现状 | 处置 | 批次/任务 | 说明 |
| --- | --- | --- | --- | --- | --- | --- |
| `.claude/hooks/block-dangerous.sh` | M | 209be9 | main 也改过 | 不导入 | — | main 的 HOOK-01 已取代；209be9 版解析失败即放行，与 HOOK-01 验收「无法解析即拒绝」相反。其「按命令位置匹配」可另立任务 |
| `.env.example` | M | 209be9 | main 也改过 | 部分导入 | 批 2（F01） | 只取 `STORAGE_DIR`、`NEO4J_DATABASE` 与 Neo4j 容器 5 项；模型、预算、任务段以 main 为准（A07 已定） |
| `.gitignore` | M | 209be9 | main 未改 | 导入 | 批 3 | datasets/raw、evaluation/reports、`*.pdf/*.docx/*.pptx` 忽略规则；main 自基线未改此文件 |
| `AGENTS.md` | M | 209be9 | main 未改 | 待决 | S03-1 → 批 5；角色路径 → 批 3 | 写争用规则与任务板/ADR 路径随 S03-1；「分支与合并（提案）」由 PLAN-D04 签收结果取代 |
| `CLAUDE.md` | M | 209be9 | main 未改 | 待决 | S03-1 → 批 5 | 只有一行随 S03-1 的 ADR 路径改动 |
| `NOTICE` | A | 209be9 | main 无 | 导入 | 批 3 | 声明「尚未复制第三方源码」，给日后借用留登记位置 |
| `README.md` | M | 209be9,740adb | main 也改过 | 逐段合并 | 批 3、批 4 | 目录树只写实际已导入的目录；main 自基线只加了 2 行 |
| `datasets/README.md` | A | 209be9 | main 无 | 导入 | 批 3 | K01 的输入；只放标注元数据，原始资料被忽略 |
| `datasets/raw/.gitkeep` | A | 209be9 | main 无 | 导入 | 批 3 | K01 的输入；只放标注元数据，原始资料被忽略 |
| `docker-compose.yml` | A | 209be9 | main 无 | 随任务导入 | 批 2（F01） | M0-05 当时 BLOCKED：APOC 未实测 |
| `docs/architecture.md` | M | 209be9,740adb,740adb-merge,ff30e0 | main 也改过；与 PR #15/#14 重叠 | 逐段合并 | 批 1、3、4、5 | 模块表 contracts 行与契约质量边界 → 批 1；prompts/evaluation 行 → 批 3；schemas 职责 → 批 4（三批改同一张表，须依次合入）；核心数据模型 → 批 5 按 N1～N5；状态机一行不导入（A03 已取代） |
| `docs/decisions.md` | D | 209be9 | main 也改过 | 待决 | S03-1 → 批 5 | 分支上是「删除并拆目录」；拆分文件须以 main 已签收正文重建 |
| `docs/decisions/ADR-001-vue3-g6-2d-graph.md` | A | 209be9 | main 无 | 导入 | 批 5 | 正文与 main 一致（已逐字比对） |
| `docs/decisions/ADR-002-neo4j-sqlite-dual-store.md` | A | 209be9 | main 无 | 导入 | 批 5 | 正文与 main 一致（已逐字比对） |
| `docs/decisions/ADR-003-answer-source-citation.md` | A | 209be9 | main 无 | 导入 | 批 5 | 正文与 main 一致（已逐字比对） |
| `docs/decisions/ADR-004-contract-single-source-of-truth.md` | A | 209be9,740adb-merge | main 无 | 不导入 | 批 5 以 main 重建 | 分支版是 740adb 的改判稿；main 的 A01 签收版更完整，以它为准 |
| `docs/decisions/ADR-005-task-state-machine.md` | A | 209be9,740adb,740adb-merge | main 无 | 导入 | 批 5 | 无签收行；以 SUPERSEDED 历史记录导入：原文的「任一非终态可转 `failed`」「`cancelled` 预留」与现行 `specs/task-processing.md` 相反，首段与索引写明被 ADR-010/011 取代（成环失败另见 ADR-009），不得作现行依据；正文不改（A10-R02） |
| `docs/decisions/ADR-006-implement-task-cancel.md` | A | 209be9,740adb-merge | main 无 | 导入 | 批 5 | 无签收行；「实现取消」的方向由 ADR-010 维持，但「只有非终态任务可取消」与 ADR-010 的取消矩阵（`persisting`、`awaiting_review` 不可取消）不一致；以 SUPERSEDED 历史记录导入，首段与索引指向 ADR-010/011，不得作现行依据（A10-R02） |
| `docs/decisions/ADR-007-study-material-bonus-scope.md` | A | 209be9 | main 无 | 待决 | PLAN-D05 → 批 6 | 无签收行；学习材料加分项范围未拍板 |
| `docs/decisions/ADR-008-data-model-naming-baseline.md` | A | 740adb-merge | main 无 | 导入 | 批 5 | 须同时写入 N1～N5 命名对齐修订；否则与 ADR-011/012 已签收名称冲突 |
| `docs/decisions/README.md` | A | 209be9,740adb-merge | main 无 | 导入 | 批 5 | 索引按 main 实际编号 001～014 重建 |
| `docs/handoffs/claude-m0-04-api-contracts.md` | A | ff30e0 | main 无 | 导入 | 批 1 | 同上 |
| `docs/handoffs/claude-m0-05-local-env.md` | A | 209be9 | main 无 | 导入 | 批 2 | 同上 |
| `docs/handoffs/claude-m0-06-naming-and-scope.md` | A | ff30e0 | main 无 | 导入 | 批 5 | 同上；其中 M0-08 部分对应批 3 |
| `docs/handoffs/claude-s01-contract-format.md` | A | 209be9 | main 无 | 导入 | 批 1 | 历史交接，随其成果入库，不改正文 |
| `docs/handoffs/claude-s03-collab-restructure.md` | A | 209be9 | main 无 | 导入 | 批 5 | 同上 |
| `docs/handoffs/claude-s04-directory-skeleton.md` | A | 209be9 | main 无 | 导入 | 批 3 | 同上 |
| `docs/handoffs/claude-s05-consistency-fixes.md` | A | 209be9 | main 无 | 导入 | 批 5 | 只作记录：其钩子重写不导入 |
| `docs/handoffs/claude-s06-scope-decisions.md` | A | 209be9 | main 无 | 导入 | 批 6 | 同上 |
| `docs/handoffs/claude-s06-specs-and-references.md` | A | 209be9 | main 无 | 导入 | 批 6 | 任务号改记 S-08（ID-1）；文首加注，不改正文 |
| `docs/handoffs/claude-s07-contract-conflicts.md` | A | 740adb | main 无 | 导入 | 批 1 | 同上 |
| `docs/integrations.md` | M | 209be9 | main 也改过 | 部分导入 | 批 2（F01） | 「本地依赖环境」各节与存储、Neo4j 容器变量行；模型接入规则以 main 为准 |
| `docs/product.md` | M | 209be9,740adb-merge,ff30e0 | main 未改 | 待决 | PLAN-D05 → 批 6 | 学习材料、目标路径、多课程、性能指标属范围决定；学习材料行在分支上重复出现两次，需去重 |
| `docs/references.md` | A | 209be9 | main 无 | 导入 | 批 3 | 把仓库与 S2 方案等仓库外权威文档挂钩 |
| `docs/references/参考项目对照笔记.md` | A | 209be9 | main 无 | 导入 | 批 3 | 团队自撰笔记；入库前去掉本机绝对路径（合规去标识化） |
| `docs/tasks.md` | M | 209be9,740adb-merge,ff30e0 | main 也改过；与 PR #15/#14 重叠 | 不导入 | — | 分支把任务板拆成 M0～M4 文件，与 main 现行单文件任务板结构冲突；内容映射见第 5 节 |
| `docs/tasks/M0.md` | A | 209be9,740adb-merge | main 无 | 不导入 | — | 被原子清单取代；未覆盖的 M3-02、M4-02～07 列入第 6 节缺口 |
| `docs/tasks/M1.md` | A | 209be9,740adb-merge | main 无 | 不导入 | — | 被原子清单取代；未覆盖的 M3-02、M4-02～07 列入第 6 节缺口 |
| `docs/tasks/M2.md` | A | 740adb-merge | main 无 | 不导入 | — | 被原子清单取代；未覆盖的 M3-02、M4-02～07 列入第 6 节缺口 |
| `docs/tasks/M3.md` | A | 740adb-merge | main 无 | 不导入 | — | 被原子清单取代；未覆盖的 M3-02、M4-02～07 列入第 6 节缺口 |
| `docs/tasks/M4.md` | A | 740adb-merge | main 无 | 不导入 | — | 被原子清单取代；未覆盖的 M3-02、M4-02～07 列入第 6 节缺口 |
| `docs/tasks/open-questions.md` | A | 209be9,740adb,740adb-merge | main 无 | 不导入 | 批 6 取 D-01 清单 | D-04→PLAN-D04、D-07→PLAN-D05、D-08 新增到 main；D-05、D-06 退役（ID-4） |
| `evaluation/README.md` | A | 209be9,740adb-merge | main 无 | 导入 | 批 3 | K01 的输入 |
| `evaluation/reports/.gitkeep` | A | 209be9 | main 无 | 导入 | 批 3 | K01 的输入 |
| `prompts/MANIFEST.md` | A | 209be9 | main 无 | 导入 | 批 3 | E01 的输入 |
| `prompts/README.md` | A | 209be9,740adb-merge,ff30e0 | main 无 | 导入 | 批 3 | E01 的输入 |
| `prompts/TEMPLATE.yaml` | A | 209be9 | main 无 | 导入 | 批 3 | E01 的输入 |
| `scripts/_dev-common.sh` | A | 209be9 | main 无 | 随任务导入 | 批 2（K07） | 先审后用（K07 验收：普通停止保留数据、删卷须确认） |
| `scripts/check-apoc.sh` | A | 209be9 | main 无 | 随任务导入 | 批 2（F01） | APOC 实测是 F01 验收项 |
| `scripts/check_contracts.py` | A | 740adb,ff30e0 | main 无 | 导入 | 批 1 | 需两处调整（见批 1）：命名扫描误报「不得使用」说明行；扫描清单含 main 尚无的两份规格 |
| `scripts/dev-down.sh` | A | 209be9 | main 无 | 随任务导入 | 批 2（K07） | 同上 |
| `scripts/dev-up.sh` | A | 209be9 | main 无 | 随任务导入 | 批 2（F01、K07） | 同上 |
| `scripts/gen-contracts.sh` | A | 740adb | main 无 | 导入 | 批 1 | `978671e` 已含 S07-R06 修复 |
| `scripts/gen_contracts.py` | A | 740adb | main 无 | 导入 | 批 1 |  |
| `scripts/verify.sh` | M | 209be9 | main 也改过 | 待决 | S03-1 → B07/K11 | 分发器与 main 的 HOOK-01 回归测试一行冲突；批 1 只在 main 版加一行调用契约门禁 |
| `scripts/verify/backend.sh` | A | 209be9 | main 无 | 待决 | S03-1 → B07/K11 | B05 合入后此脚本打印占位并 exit 0，是假绿，不能原样导入 |
| `scripts/verify/contracts.sh` | A | 209be9,740adb | main 无 | 导入 | 批 1 | 生成物补齐后删去 `--allow-scaffold` |
| `scripts/verify/frontend.sh` | A | 209be9 | main 无 | 待决 | S03-1 → B07/K11 | 分发器的子脚本与必需文件清单 |
| `scripts/verify/manifests/backend.txt` | A | 209be9 | main 无 | 待决 | S03-1 → B07/K11 | 分发器的子脚本与必需文件清单 |
| `scripts/verify/manifests/contracts.txt` | A | 209be9,740adb | main 无 | 待决 | S03-1 → B07/K11 | 分发器的子脚本与必需文件清单 |
| `scripts/verify/manifests/core.txt` | A | 209be9,740adb | main 无 | 待决 | S03-1 → B07/K11 | 分发器的子脚本与必需文件清单 |
| `scripts/verify/manifests/frontend.txt` | A | 209be9 | main 无 | 待决 | S03-1 → B07/K11 | 分发器的子脚本与必需文件清单 |
| `scripts/verify/structure.sh` | A | 209be9 | main 无 | 待决 | S03-1 → B07/K11 | 分发器的子脚本与必需文件清单 |
| `specs/course-knowledge-graph.md` | M | 740adb,ff30e0 | main 也改过 | 逐段合并 | 批 5、批 6 | 节点字段 → 批 5；验收 7～10、关联任务 → 批 6（PLAN-D05）；验收 2 状态机不导入（A03 已改） |
| `specs/grounded-qa.md` | A | 209be9 | main 无 | 随任务导入 | A09 | 作 A09 底稿（同 A04 以分支桩为底稿的做法） |
| `specs/learning-path.md` | A | 209be9,740adb | main 无 | 不导入 | — | A08（Codex，进行中）的新规格取代此桩 |
| `specs/teacher-review-publish.md` | A | 209be9,740adb | main 也改过 | 不导入 | — | A04 已以此桩为底稿重写并签收 |
| `src/backend/app/api/README.md` | A | 209be9 | main 无 | 导入 | 批 4 | 须在 B05 合入之后 |
| `src/backend/app/api/__init__.py` | A | 209be9 | main 无；与 PR #14 重叠 | 不导入 | — | Codex B05（PR #14）已新建同名文件 |
| `src/backend/app/repositories/README.md` | A | 209be9 | main 无 | 导入 | 批 4 | 须在 B05 合入之后 |
| `src/backend/app/repositories/__init__.py` | A | 209be9 | main 无 | 导入 | 批 4 | 须在 B05 合入之后 |
| `src/backend/app/schemas/README.md` | A | 209be9 | main 无 | 导入 | 批 4 | 须在 B05 合入之后 |
| `src/backend/app/schemas/__init__.py` | A | 209be9 | main 无 | 导入 | 批 4 | 须在 B05 合入之后 |
| `src/backend/app/services/README.md` | A | 209be9 | main 无 | 导入 | 批 4 | 须在 B05 合入之后 |
| `src/backend/app/services/__init__.py` | A | 209be9 | main 无 | 导入 | 批 4 | 须在 B05 合入之后 |
| `src/backend/app/workers/README.md` | A | 209be9 | main 无 | 导入 | 批 4 | 须在 B05 合入之后 |
| `src/backend/app/workers/__init__.py` | A | 209be9 | main 无 | 导入 | 批 4 | 须在 B05 合入之后 |
| `src/contracts/README.md` | M | 209be9,740adb-merge,ff30e0 | main 未改 | 导入 | 批 1 | `not_covered_reason` 改为 `reason`（A02 移交） |
| `src/contracts/api.v1.yaml` | A | 740adb,ff30e0 | main 无 | 导入 | 批 1 | ADR-004 真源及配套文档 |
| `src/contracts/errors.v1.md` | A | 740adb,ff30e0 | main 无 | 导入 | 批 1 | ADR-004 真源及配套文档 |
| `src/contracts/events.v1.md` | A | 740adb,ff30e0 | main 无 | 导入 | 批 1 | ADR-004 真源及配套文档 |
| `src/contracts/toolchain.txt` | A | 740adb | main 无 | 导入 | 批 1 | ADR-004 真源及配套文档 |
| `src/contracts/v1/generated/openapi.json` | A | 740adb | main 无 | 导入 | 批 1 | 不取分支里不完整的 4 个文件，按真源重新生成（含 python/、typescript/） |
| `src/contracts/v1/generated/schemas/ChatEvent.schema.json` | A | 740adb | main 无 | 导入 | 批 1 | 不取分支里不完整的 4 个文件，按真源重新生成（含 python/、typescript/） |
| `src/contracts/v1/generated/schemas/GraphExchange.schema.json` | A | 740adb | main 无 | 导入 | 批 1 | 不取分支里不完整的 4 个文件，按真源重新生成（含 python/、typescript/） |
| `src/contracts/v1/generated/schemas/TaskEvent.schema.json` | A | 740adb | main 无 | 导入 | 批 1 | 不取分支里不完整的 4 个文件，按真源重新生成（含 python/、typescript/） |
| `tests/README.md` | A | 209be9,740adb | main 无 | 导入 | 批 4 | 目录说明 |
| `tests/backend/README.md` | A | 209be9 | main 无 | 导入 | 批 4 | 目录说明 |
| `tests/contracts/README.md` | A | 209be9,740adb | main 无 | 导入 | 批 1 | 21 项门禁负向测试；夹具清单同 check_contracts 调整 |
| `tests/contracts/_shim/sitecustomize.py` | A | 740adb | main 无 | 导入 | 批 1 | 21 项门禁负向测试；夹具清单同 check_contracts 调整 |
| `tests/contracts/test_contracts.py` | A | 740adb | main 无 | 导入 | 批 1 | 21 项门禁负向测试；夹具清单同 check_contracts 调整 |
| `tests/frontend/README.md` | A | 209be9 | main 无 | 导入 | 批 4 | 目录说明 |

合计 92 个文件：导入 56，待决 13，不导入 12，随任务导入 6，逐段合并 3，部分导入 2。

## 5 任务编号映射（分支任务板 → main）

分支任务板上的 ID 不进 main 任务板，这里给出去向，供读分支交接时对照。

| 分支 ID | 分支状态 | 去向 |
| --- | --- | --- |
| S-01 契约格式与单一真源 | DONE | A01（ADR-004，已签收） |
| S-03 拆分写争用点 | DONE（分支） | S03-1 → 批 5；门禁分发器交 B07/K11 |
| S-04 目录骨架 | DONE（仅交接，未登记） | 批 3、批 4 |
| S-05 钩子与路径修复 | DONE（仅交接，未登记） | 钩子被 HOOK-01 取代；路径修复随批 3 |
| S-06 两项范围决策 | DONE | ADR-006 由 ADR-010 复核维持（批 5）；ADR-007 待 PLAN-D05（批 6） |
| S-06 补规格与参考 → **S-08** | DONE（仅交接，未登记） | 批 3（参考）、批 6；三份规格桩中 `grounded-qa` 交 A09，其余两份已被取代 |
| S-07 合并两个 worktree | DONE | 批 1 的来源 |
| M0-02 / M0-03 | TODO | B01（PR #15）、B02 / B05（PR #14）、B06 |
| M0-04a～d REST、SSE、图谱交换、错误码 | DONE（分支） | 批 1 导入；B08～B13 校核与补齐 |
| M0-05 本地依赖环境 | BLOCKED | 批 2 / F01、K07 |
| M0-06 命名统一（`ff30e0`） | DONE（分支） | 批 5（ADR-008 + N1～N4） |
| M0-06 → **M0-11** 按 ADR 同步规格 | TODO | 已被 A02～A05 与批 5、6 覆盖，不单独执行 |
| M0-07 修正契约 README | DONE（分支） | 批 1 |
| M0-08 prompts/evaluation 目录 | DONE（分支） | 批 3 |
| M0-09 生成链与生成物入库 | TODO | 第一步已在 main 完成（工具链实测）；第二步即批 1；B14 再加固 |
| M0-10 前端消费生成类型 | TODO | B15 |
| M1-01 课程与上传 | TODO | C04～C07 |
| M1-02a/b/c 解析、清洗、分块 | TODO | D01～D06 / D07 / D08、D09（「块 ID = 内容哈希」已被 ADR-012 修订 1 改为按资料修订生成） |
| M1-03a/b/c 实体、规范化、关系 | TODO | E01、E02、E05、E06 / E08 / E11 |
| M1-04a/b 规则校验、环检测降级 | TODO | E11 / F05、F13 |
| M1-05 Neo4j 写入（分支含义） | TODO | F02～F04、F13（ID-3） |
| M1-06 编排、SSE、取消 | TODO | C08～C11、E12 |
| M1-07 / M1-08 上传进度页 / G6 图谱 | TODO | H02、C12 / H03～H06 |
| M1-09 端到端跑通一章 | TODO | K05 |
| M2-01 三级融合 | TODO | E08～E10；阈值待 D-08 |
| M2-02 / M2-03 / M2-04 编辑 / 审核队列 / 发布回滚 | TODO | F08～F10、H07、H08 / F11、H09 / G01～G07、H10 |
| M2-05 / M2-06 进度 / 推荐 | TODO | I01、I02、I06 / I03～I05（A08） |
| M2-07 目标路径 | TODO | O01～O04（PLAN-D05） |
| M2-08 / M2-09 问答 / 问答联动 | TODO | J01～J07（A09） / J08、J09 |
| M2-10 卡片视图 | TODO | H11 |
| M2-11 学习材料 | TODO | O05～O08（PLAN-D05、ADR-007） |
| M2-12 多课程示例 | TODO | K09、C02；课程来源待 D-01 |
| M3-01 / M3-03 / M3-04 标注集 / 问答评测 / 性能 | TODO | K01、K02 / K03 / K04 |
| M3-02 消融实验 | TODO | **缺口 G-3** |
| M3-05 / M3-06 回归 / 门禁负向测试 | TODO | K05、K06 与各任务自带测试 / B07、B14 |
| M4-01 系统使用说明 | TODO | K12 |
| M4-02～M4-07 参赛材料与合规 | TODO | **缺口 G-4** |

## 6 原子清单缺口

以下事项已有签收决定或赛题要求，但 127 项原子任务中没有承接者。编号在批 0 补登时确定，这里只给建议。

| ID | 事项 | 来源 | 建议编号 |
| --- | --- | --- | --- |
| G-1 | 登录端点与令牌签发、账号命令行与演示种子、成员管理 API、成员管理页面、SSE 票据申领端点 | A05 交接（ADR-013） | C13～C16、H12 |
| G-2 | 重新向量化命令（按实际存量枚举与核对） | ADR-012 修订 1、修订 2 | F14 |
| G-3 | 消融实验：单阶段、两阶段、两阶段 + 补漏 | 分支 M3-02；S2 评测章节 | K13 |
| G-4 | 提示词工程完整记录、图谱构建示例、S2 定稿（含 ADR-008 三处措辞）、S1 概要/PPT/演示视频、S5 团队过程、合规自检（去标识化、原创承诺） | 分支 M4-02～07；S2 §4.2 M4 | K14～K19 |
| G-5 | `event_tickets` 等 A05/A06 新表并入命名基线 | A05 交接 | 并入批 5 |
| G-6 | `AUTH_JWT_SECRET` 等三个变量写入 `.env.example` | A05 交接 | 并入 C03 或 G-1 |

## 7 风险

1. **截止日期**：距 10-08 提交还有 15 天，主链路尚未开始编码。批次本身都只是文档与脚本迁移，但批 1、批 5 各需要一项签收；签收越晚，B08～B13 与 F 组越晚开工。
2. **契约与规格耦合**：批 1 的门禁要求 A08、A09 的规格存在。`learning-path.md` 已随 PR #19 合入，不得移出；只有 `grounded-qa.md` 在 A09 合入前暂缓，合入后加回并由负例证明（A10-R01）。
3. **门禁分发器**：若日后原样导入 `scripts/verify/backend.sh`，B05 合入后它会打印占位并 exit 0，形成假绿。B07 须先改掉。
4. **双解释器**：生成器与门禁依赖分装在两个 Python 里；本机与 CI 的安装方式不同，批 1 要把两处都写清。
5. **合规**：分支参考笔记与 main 多处文档含本机绝对路径和个人目录名；赛题要求去标识化，归 G-4 的合规自检，批 3 先处理新导入的文件。
6. **未提交成果**：A08 的规格已随 PR #19 合入 main；A08 签收稿（PR #23）与 A09（PR #20）仍在途，批 1 的扫描清单在 A09 合入后加回 `grounded-qa.md`。

## 8 核对方法与证据

所有命令都在 main `6881ffe` 的只读检出或临时副本上运行，没有修改 `740adb` 的 worktree。

| 核对 | 命令或方法 | 结果 |
| --- | --- | --- |
| 分支包含关系 | `git merge-base --is-ancestor <ff30e0/209be9> 740adb` | 两者都包含于 `740adb` |
| 文件普查 | `git diff --name-status 05d214c 978671e`，每个文件再查引入提交、main 是否改过、是否与 PR #14/#15 重叠 | 92 个文件；main 也改过的 10 个；与在途 PR 重叠 3 个 |
| 处置全覆盖 | 生成脚本对每个文件匹配唯一规则，无规则即退出 | 92/92 有处置 |
| `740adb` 自身门禁 | 临时副本 `./scripts/verify.sh` | 修改前 exit 1（缺 `python/`、`typescript/` 生成物）；补齐生成后 exit 0，21 项负向测试通过，`--check` exit 0 |
| 批 1 试导入 | main 临时副本叠加批 1 文件，重新生成后运行 `scripts/verify/contracts.sh` | exit 1：命名 6 处（2 处说明行误报、2 处 `SourceChunk`、2 份规格缺失）；负向测试 4/21，其余 17 项因夹具缺规格文件崩溃 |
| ADR-001～003 | 分支拆分文件与 main `decisions.md` 对应节去空白后逐字比较 | 一致 |
| 截止日期 | 读 S2 方案 docx（仓库外，只读转文本）§4.2 与表 4.2 | 9-16 至 10-08（提交截止），M1 为 9.20～9.26 |
| 在途 PR 文件 | `git diff origin/main...origin/codex/b0{1,5}-*` | B01 11 个文件、B05 9 个；与本表重叠 3 个 |
