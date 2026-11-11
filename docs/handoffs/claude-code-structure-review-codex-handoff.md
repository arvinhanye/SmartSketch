# Claude → Codex：代码结构审查与优化任务交接（OPT-01–OPT-06）

- task_id：CODE-STRUCT-REVIEW-01（只读审查 + 交接，不改代码）
- 状态：审查完成；OPT-01–OPT-06 为 **OPEN / 待认领**，均未开始
- 基线：main `3f26766`（rc-7f8a0cd 预发布之后），Claude 工作区 `claude/code-structure-review-handoff-49e73a`
- 本轮改动：仅本文件与 `docs/tasks.md` 末尾一节认领表
- 挑选标准：**耗 token 但决策少**——要通读大量文件、机械改写、有现成测试兜底；不需要付费模型调用、真实网络、Windows 实机或产品判断

## 0. 审查实测数据（2026-11-05，`git ls-files` 统计）

| 范围 | 文件 | 行数 |
| --- | --- | --- |
| `src/backend/app` | 147 | 31,373 |
| `src/frontend/src` | 114 | 20,109 |
| `tests/backend` / `frontend` / `integration` | 114 / 80 / 28 | 38,889 / 20,391 / 9,374 |
| `docs/tasks.md` | 1 | 2,402 行 / **496 KB** |
| `docs/decisions.md` | 1 | 83 条 ADR / **356 KB** |
| `docs/handoffs/` | 313 | — |

关键发现：

1. **文档是最大的 token 黑洞。** `AGENTS.md` §2 与 `CLAUDE.md` 要求每次任务先读 `docs/tasks.md`，它约 50 万字节，绝大部分是已 DONE 的历史批次；`decisions.md` 同理。每个会话启动都要为此付费。
2. **测试按任务 ID 命名**：后端 93 个、前端 32 个文件形如 `test_e03.py`、`b02.test.ts`，看名字不知道测什么，排查时只能逐个打开。
3. **测试辅助函数大量复制**：后端测试里 `_url` 12 份、`_account` 10 份、`_rewrite` 8 份、`_settings` 6 份、`_insert_task` 5 份；61 个文件各自跑迁移、26 个各自 `create_app`；`tests/backend/conftest.py` 只有 10 行。
4. **固定时长等待 31 处**（`time.sleep`/`waitForTimeout`），集中在 `test_d3.py`、`test_c02_phase_logs.py`、`teacher-viewport.browser.cjs`（各 5 处）、`test_stop_procs.py`、`test_k08.py`（各 3 处）。`docs/tasks.md` FORMAL-RELEASE-01 已记录过两次这类竞态导致的 CI 偶发失败，以及 `test_stop_procs` 在本机 macOS 稳定失败。
5. **后端分层有漏**（违反 `api → schemas → services → repositories`）：
   - `services/versions/materialize.py` 内含 17 处 Cypher，`services/versions/chunk_vectors.py` 2 处，`services/embedding_configs.py` 2 处 Cypher + 11 处 SQL，`services/task_cancel.py`、`services/versions/resolver.py` 各 3 处 SQL。
   - `api/chat.py` 直接构造 `SqliteCallStore` 并调用 `write_chat_log`（`api/chat.py:66`、`api/chat.py:130`），落库逻辑在路由层。
   - 11 个 `api/*.py` 导入 `app.repositories`；其中只导入 `AccountRecord` 类型、`RepositoryError` 做异常映射的属于可接受，真正的问题是上面那几处直接实例化仓储/写库。
6. 大文件：`services/ai/compatible.py` 1,074 行、`workers/extract_task.py` 1,020 行（47 个顶层定义）、`composables/useMaterials.ts` 843 行、`views/StudentGraphView.vue` 792 行。可拆，但收益低于前五项，列为可选。

前端分层基本守规：`views/` 只从 `api/` 导入注入键（`*_API_KEY`）和错误类，不直接发请求。未发现需要立即处理的前端结构问题；`.vue` 里有 189 处硬编码十六进制颜色，但改 tokens 涉及视觉确认，**不建议交给 Codex 单独做**。

## 1. 任务清单（建议顺序）

### OPT-01 文档瘦身：归档 `tasks.md` 与 `decisions.md`（收益最高，先做）

- 输入：`docs/tasks.md`、`docs/decisions.md`、`AGENTS.md`、`CLAUDE.md`、`docs/handoffs/README.md`。
- 输出：
  - `docs/tasks.md` 只留：顶部状态摘要、所有非 DONE/CANCELLED 的条目（OPEN、TODO、IN_PROGRESS、未决、风险）、最近一个大节（FORMAL-RELEASE-01），以及指向归档的索引表（节标题 → 归档文件与锚点）。目标 ≤ 60 KB。
  - 历史节**原样移动**到 `docs/archive/tasks-2026-09.md`、`docs/archive/tasks-2026-10.md`（按节日期分），不改一个字。
  - `docs/decisions.md` 改为 ADR 索引（编号、标题、日期、状态、一句话），正文移到 `docs/archive/decisions-adr-001-040.md` 等分卷；或保留正文但仅把被取代（superseded）的 ADR 移出——两种做法选一，写进交接。
- 必须同步：
  - `tests/tooling/test_worker_network_ci.py:47` 的 ADR 编号唯一性检查只读 `decisions.md`，必须改为同时扫描归档分卷，否则会漏检重复编号。
  - `scripts/verify.sh:19` 检查这些文件存在，保留文件即可。
  - `tests/backend/test_e08.py`、`test_e09.py` 文档字符串引用 `docs/tasks.md` 某批次，改为归档路径（仅注释）。
  - 全库 `grep -rn "docs/tasks.md#\|tasks.md 第"` 找锚点引用并修正。
- 需要用户确认：`AGENTS.md` §2「先读 `docs/tasks.md`」是否改为「先读 `docs/tasks.md`（当前看板）；历史只在需要时查 `docs/archive/`」。这是共同契约，**先问用户再改**。
- 验证：移动前后对拼接文本做 `diff`（历史内容零丢失，可写一个一次性脚本把归档 + 新看板按原顺序拼回再与原文件比较，附在交接里）；`./scripts/verify.sh`；`pytest tests/tooling/test_worker_network_ci.py`。
- 风险：其他工作区有对 `tasks.md` 的未提交改动时会产生大冲突——开工前确认没有其他分支正在改它，开 PR 后尽快合。
- 回滚：revert 该提交。

### OPT-02 测试稳定性：替换固定时长等待（含 `test_stop_procs` macOS 失败）

- 范围：上文第 4 点列出的 31 处；先 `grep -rnE "time\.sleep\(|waitForTimeout\(" tests` 重新取清单。
- 做法：每处判断等的是什么条件，改为带超时的轮询（`wait_until(predicate, timeout)` 之类，放到共享辅助里），或用事件/假时钟。确实是在测「过了 N 秒」的行为（宽限期、超时）则保留并加注释说明为何必须真实等待。
- `tests/tooling/test_stop_procs.py::test_grace_period_is_not_shortened_by_shell_seconds_rounding` 本机 macOS 稳定失败：先复现、定位根因（`docs/tasks.md` 只记录了现象），属于 Bug 修复，按 `.claude/rules/testing.md` 先确认可复现再改。
- 不改产品代码；若发现是产品竞态而非测试竞态，停下来写进交接，不顺手修。
- 验证：改动文件各连跑 20 次（`pytest -p no:randomly --count=20` 或循环）全绿；`./scripts/verify.sh full`；涉及集成的跑 `./scripts/verify.sh integration`（需本机 Neo4j）。

### OPT-03 后端测试夹具收敛

- 依赖：在 OPT-02 之后做（两者都改 `tests/backend`，避免同一文件并行编辑）。
- 做法：把重复的 `_url`/`_account`/`_settings`/`_insert_task`/迁移初始化/`create_app` 抽成 `tests/backend/conftest.py` 的 fixture 或 `tests/backend/helpers/` 模块；**按文件小批迁移**，每批跑一次该批测试。不改断言、不删用例。
- 验收：后端用例总数与改动前一致（先记录 `pytest --collect-only -q | tail -1` 的数字）；`./scripts/verify.sh full` 通过；重复辅助函数计数显著下降（交接里给前后对比）。
- 风险：fixture 作用域写错会让用例之间共享 SQLite 状态——默认 function 作用域，确需加速再单独评估。

### OPT-04 测试索引（不重命名）

- 做法：生成 `tests/INDEX.md`：每个按任务 ID 命名的测试文件 → 被测模块/功能一句话 → 对应规格或 ADR。来源是文件头文档字符串和 import。
- **不重命名文件**：重命名会打断 313 份交接、CI 路径和 `git log --follow` 之外的所有引用，收益不抵成本。若用户之后想改名，可以以此索引为映射表另开任务。
- 可选：加一条 tooling 测试，保证新增 `test_<id>.py` 时 `INDEX.md` 有对应条目。
- 验证：脚本校验索引覆盖全部 `tests/backend/test_*.py` 与 `tests/frontend/*.test.ts`；`./scripts/verify.sh`。

### OPT-05 后端分层修正（需要 Neo4j）

- 范围：
  1. `services/versions/materialize.py`、`chunk_vectors.py` 的 Cypher 移入 `repositories/`（可新建 `repositories/version_materialize.py`）。
  2. `services/embedding_configs.py`、`task_cancel.py`、`versions/resolver.py` 的 SQL 移入对应仓储。
  3. `api/chat.py` 的 `SqliteCallStore` 构造与 `write_chat_log` 下沉到 `services/qa/`，路由只做协议转换。
- 规则：纯搬移，语句文本逐字不变（交接里贴 `git diff --color-moved` 的结论）；保持 `course_id` 隔离参数与事务边界不变；`PREREQUISITE` 相关写入不得绕过环检测。
- 可选护栏：加一条 tooling 测试，禁止 `services/**` 出现 `MATCH (`/`MERGE (` 与 `.execute(`，`api/**` 不得实例化仓储类（允许导入类型与异常）。先列白名单再收紧。
- 验证：`./scripts/verify.sh integration`（materialize 走真实 Neo4j）；契约门禁不应有变化。
- 风险：materialize 是发布路径，搬移时若改变事务内/外的调用位置会影响发布原子性——只搬函数，不改调用顺序。

### OPT-06（可选，最后）大文件按职责拆分

- 候选：`services/ai/compatible.py`、`workers/extract_task.py`、`composables/useMaterials.ts`、`views/StudentGraphView.vue`。
- 只在 OPT-03/05 合入后做；每个文件一个 PR；对外导出名不变（旧模块保留再导出）；不改行为。
- 验证：对应后端/前端全量测试、`npm --prefix src/frontend run type-check`、`build`。前端拆 `.vue` 需人工或浏览器走查截图对比，Codex 无法独立签收则写明未验证。

## 2. 明确不交给 Codex 的事项

- 需要付费模型或真实网络的：B-QA-01（比较题截断）、B-QUALITY-01（准确率评估）、B-EVAL-01 的真实首字抓取。
- Windows 实机、签名与公证、Gatekeeper/SmartScreen、旧草稿 Release 删除——需要用户本人或特定机器。
- 前端硬编码颜色收敛为 tokens——需要视觉确认。
- 冒烟测试泄漏 Docker 网络：可以做，但要真实 Docker 环境且单次 7 分钟以上，若 Codex 环境有 Docker 可附在 OPT-02 后，否则留给本机。

## 3. 并行与冲突

| 可并行 | 原因 |
| --- | --- |
| OPT-01 ‖ OPT-02 ‖ OPT-05 | 分别只碰 `docs/`、`tests/`、`src/backend/app/` |
| OPT-03 必须在 OPT-02 后 | 同改 `tests/backend` |
| OPT-04 任意时间 | 只新增 `tests/INDEX.md`；若与 OPT-03 同期，后合入方重新生成一次 |
| OPT-06 最后 | 依赖 OPT-03/05 的结构 |

每个任务一个分支、一个 PR；完成后写 `docs/handoffs/codex-opt-0N.md`，并在 `docs/tasks.md` 末节更新状态。

## 4. 本轮验证

- 只运行了只读统计命令（`git ls-files`、`wc`、`grep`）；未运行测试，未改代码。
- `./scripts/verify.sh`（basic）：exit 0（Scaffold verification passed、contracts gate PASS）；`git diff --check` 通过。
- 未验证：第 5 点的 11 个 `api` 导入逐一确认是否只是类型/异常（已抽查 `chat.py`、`versions.py`、`graph.py`）；31 处等待中哪些是合法的真实时长测试。

## 5. 下一位 Agent 的首个动作

读本文件 → 在 `docs/tasks.md`「代码结构优化（OPT）」节认领一项 → OPT-01 先问用户 `AGENTS.md` §2 措辞是否可改。
