# Claude 交接：计划 C 验收收尾（C-ACC-A～D）

- 日期：2026-10-04
- task_id：C-ACC-A / C-ACC-B / C-ACC-C / C-ACC-D
- **stage_c_status: OPEN**
- **technical_freeze: NOT_PERFORMED**
- review_status: ready_for_review

## 1. 工作区、基线与提交

- 执行工作区：`/Users/arvinhan/SmartSketch/.claude/worktrees/smartsketch-plan-a-fixes-e70a34`
- 分支：`claude/plan-c-acceptance`
- 基线：Codex `codex/plan-c-takeover@4a6308b`，含完整门禁代码提交 `043c274`。用户确认自 `4a6308b` 新建分支。上轮未提交的方案 B 文件中，14 份与 Codex 逐字节相同，2 份不同且 Codex 版更好；原件备份在 `claude/plan-c-b-wip-backup@2692648`，不合并。
- 测量区（严格只读）：`/Users/arvinhan/SmartSketch/.claude/worktrees/smartsketch-c03b-measure`，`deepseek/plan-c-thinking-disabled@88f9f6f`。本轮只读取文件、只读查询，未改证据、未提交、未在其中跑门禁；结束时 `git status --porcelain` 为空。
- 本轮本地提交（未推送、未合并）：

  | 提交 | 内容 |
  | --- | --- |
  | `2f1061c` | docs：认领 C-ACC-A～D |
  | `a094714` | A：持久化出处只读核验工具、测试、报告与证据 |
  | `4304fec` | B：入库阶段子步骤脱敏计时 + 3 例回归 |
  | `452d446` | C：C04 签收入口、用户签收文件、claude-assist 辅助判定 |
  | `03af1b9` | D 决策表、`docs/tasks.md` 状态与证据、本交接 |
  | 本次追加提交 | 签收填写工具 `evaluation/c04_signoff.py`、两课工作表副本、12 例测试 |

## 2. 四件事分开报告

| 项 | 结论 |
| --- | --- |
| 工程门禁通过 | **是**：`4304fec` 代码树完整 `./scripts/verify.sh integration` 实际 exit 0（第 4 节）；之后两个提交只加数据与文档，最终树另跑 `./scripts/verify.sh`（basic）exit 0 |
| 真实测量已完成 | 是，由 DeepSeek 在 `88f9f6f` 完成，Codex 已复核；本轮没有新增真实测量 |
| 人工准确率已签收 | **否**。签收入口已就绪，辅助判定不是签收 |
| 技术冻结已执行 | **否** |

## 3. 交付物

### A. 持久化出处只读核验（DONE）

- 工具 `evaluation/audit_persisted_sources.py`：直接调用 API 知识点详情的服务函数 `read_knowledge_point`（草稿、教师）。
  - 图谱只经 `GraphReader` / `Neo4jRepository.read`，走读路由。
  - 详情路径依赖的 SQLite 连接被临时换成 `mode=ro&immutable=1` + `PRAGMA query_only`；运行前后断言库文件 SHA-256 不变。
  - Neo4j 连接变量按用户授权（「A 选 a」）从测量区 `.env` 只取 `NEO4J_URI`、`NEO4J_USER`、`NEO4J_PASSWORD` 载入进程，不打印、不写盘、不复制。
- 结果（实际 exit 0，`defect_items: 0`）：

  | 项 | course1 PDF | course2 PDF |
  | --- | ---: | ---: |
  | 草稿知识点 | 76 | 68 |
  | `source` 标签 | ai 76 | ai 68 |
  | 详情有可定位 `source_refs` 的 AI 知识点 | 76/76 | 68/68 |
  | `source_refs` 条数（均带页码、章节、文件名） | 79 | 76 |
  | 悬空块 / 他课文档 / 跨课证据边 / 读取失败 | 0 / 0 / 0 / 0 | 0 / 0 / 0 / 0 |

- 报告 `evaluation/reports/c-acc-a-persisted-sources.md`，证据 `evaluation/raw/c-acc-a/sources.json`（只含编号、计数、哈希）。
- 限制：只核验草稿（两门课均未发布）；「可定位」不等于原文支持该知识点，语义正确性归 C04 人工判定。
- 测试 `tests/tooling/test_c_acc_sources.py` 5 passed。红灯阶段只是「工具文件不存在」，行为断言首次真实运行即通过；这不算行为层面的先红后绿，照实记录。

### B. 入库子步骤计时（DONE）

- `src/backend/app/workers/persist_graph.py`：`run_persist_stage` 外层只负责计时与记录，原主体移入 `_persist_stage`。
  - 每次入库输出一行 INFO：`persist steps task_id=… outcome=… candidates_ms plan_ms chunks_ms lock_wait_ms lease_check_ms neo4j_ms neo4j_attempts t6_ms lock_release_ms task_release_ms total_ms`。
  - 抛错的步骤也记，没走到的步骤不出现。
  - 只记任务编号、结果、毫秒数与次数，不记密钥、提示词、答案或课程正文。
- `tests/backend/test_c02_phase_logs.py` 新增 3 例：RED 3 failed / 3 passed → GREEN 6 passed。
  - 覆盖：成功（Neo4j 工作函数被驱动重跑时 `neo4j_attempts=2`）；锁未获取；Neo4j `RepositoryError` 与租约丢失。
  - 日志中不出现哨兵正文。
- 锁、事务、重试、预算与业务语义不变；没有启动真实抽取。
- **只为以后的运行提供归因能力**；course1 6471 ms 与旧 15.643 秒的根因仍 OPEN，不做事后归因。

### C. C04 人工签收入口（DONE；用户签收 OPEN）

- 目录 `evaluation/raw/c04-signoff/`，说明见该目录 `README.md`。
- 原始 predictions 与工作表从测量区 `evaluation/raw/c04/` 原样复制，SHA-256 一致：
  - `a94bb86c…`、`16a08620…`（course1）；
  - `50fa5348…`、`f11ebc13…`（course2）。
- `*-judgments-user.json`：`judge` 为空，判定为 `null`；未填完时 `judge-report` 直接拒绝计算（已实测）。
- `*-judgments-claude-assist.json`：
  - `judge` 以 `claude-assist` 开头，`is_human_judgment: false`；
  - 144 个实体和 119 条关系逐条给依据，判错写 E/R 编号；
  - 存疑项列在 `needs_review`（course1 7 项、course2 6 项）。
- `judge-report` 按辅助文件实测，报告标注「Claude 辅助判定（非人工验收）」。参考数：

  | 课程 | 实体 | 关系 |
  | --- | --- | --- |
  | course1 | 64/76 | 58/61 |
  | course2 | 61/68 | 45/58 |

  course2 关系离 70% 只差 5 条。辅助报告未入库，只在 README 写复现命令，避免被当作达标结论。

### D. 补测决策表（DONE，仅提案）

`evaluation/reports/c-acc-d-retest-decisions.md`：

| 项 | 建议 |
| --- | --- |
| 浏览器可见首字 | 先用本机假供应商量前端附加时延（免费，需另开开发任务）；如仍需真实数字再跑 3 题，3×13004+13004 = 52016，落在现剩 55549 内 |
| 关闭思考的 MD 抽取 | 只跑 course1 一份，不发布；建议 95000 / 940000，向量 0 |
| v3 + 思考开启 13 题 | 沿用 Codex 185000 / 1030000；相邻 A/B 352000 / 1200000 |

三项都没有执行。

## 4. 实际运行的验证

| 命令 | 结果 |
| --- | --- |
| `pytest tests/backend/test_c02_phase_logs.py tests/tooling/test_c_acc_sources.py -q` | 11 passed |
| `evaluation/audit_persisted_sources.py …`（只读，测量区） | exit 0，`defect_items: 0`，库哈希前后一致 |
| `evaluate_extraction.py judge-report`（两份辅助判定） | exit 0，`is_human_judgment: false` |
| `evaluate_extraction.py judge-report`（未填的用户签收文件） | 拒绝：`None` 不是合法判定 |
| 完整门禁 `./scripts/verify.sh integration`（`4304fec`） | **exit 0**：backend+tooling 3878 passed / 27 登记 skip；frontend 38 文件 934 passed；integration 393 passed / 4 登记 skip；backend-live 44 passed；演示 E2E 2 passed；个人本机假供应商 E2E 4 passed；basic 契约、type-check、build 通过。相对 `043c274` 多 8 例（A 5 + B 3），无新增 skip、删用例或放宽断言 |

完整门禁的运行环境：
- 在不含 `.env` 的临时工作树 `$SCRATCHPAD/gate-4304fec` 运行，只软链 `.venv` 与 `node_modules`；
- 显式 `env -u` 去掉 Neo4j / LLM / 向量 / 密钥相关变量；
- 隔离端口 18100 / 15273 / 17788 / 18990 / 17789，一次性 Neo4j，临时业务库，本机假供应商。

日志在会话临时目录 `scratchpad/logs/c-acc-gate.log`（22224 字节，SHA-256 前 16 位 `6ff40c3f7935f3e9`），不入库；临时工作树已用 `git worktree remove` 移除。

最终树（含 C、D 与本交接）另跑 `./scripts/verify.sh`（basic）：exit 0。

## 5. 付费调用与预算

- 本轮真实生成调用 **0**，在线向量调用 **0**。
- 台账不变：生成 **844451 / 批准上限 900000，剩 55549**；向量另计 12005。

## 6. 未完成、未验证与 OPEN

- **C04 人工准确率签收**：需要用户本人在 `*-worksheet-user.md` 填 ✓ / ✗ 后运行 `evaluation/c04_signoff.py convert`（或直接填 JSON 后跑 `judge-report`）。这是技术冻结前唯一的必需项。
- 浏览器可见首字、关闭思考的 MD 抽取、v3 + 思考开启基线：均未测，是否补测由用户按决策表决定。
- course1 6471 ms 与旧 15.643 秒的根因：仍 OPEN；B 的日志只对以后的运行有效。
- 已发布版本副本中的出处没有核验（两门课都未发布）。

## 7. 回滚

各提交彼此独立，按需 `git revert <提交>`，不涉及迁移或数据。

| 提交 | 回滚影响 |
| --- | --- |
| `4304fec` | 失去子步骤日志，入库行为不变 |
| `a094714`、`452d446` | 只删工具、证据与签收文件，不影响应用 |

## 8. 用户只需确认

1. **准确率签收**：在 `evaluation/raw/c04-signoff/` 两份 `*-worksheet-user.md` 里填判定人和每行 ✓ / ✗（判 ✗ 写依据），运行 `.venv/bin/python evaluation/c04_signoff.py convert`；实体、关系各 ≥70% 才算达标。
2. **补测**：D1 / D2 / D3 各选「做 / 不做」。要做的项须确认增量停止线、累计上限和向量上限。
3. **冻结**：签收与补测决定之后，再决定是否执行技术冻结。在此之前保持 `stage_c_status: OPEN`、`technical_freeze: NOT_PERFORMED`。

## 9. 追加：签收填写工具（用户要求「在工作表里填 ✓ ✗」）

- `evaluation/c04_signoff.py`：`init` 从原工作表生成 `*-worksheet-user.md`（多「填法」「判定人」两行，已存在不覆盖）；`convert` 校验副本后写 `*-judgments-user.json`、`*-report-user.json` 并打印准确率。
- 拒绝条件（拒绝时不写任何文件）：有行未填；标记不是 ✓ / ✗（也认 √ ✔ × ✘）；判 ✗ 没写依据；判定人为空或以 `claude-assist` 开头；改动「判定」「依据」以外的列或增删行。判 ✗ 依据里没有 E/R 编号只提示，不拒绝。
- 测试 `tests/tooling/test_c04_signoff_sheet.py` 12 例：先用占位模块得到行为层 RED（2 failed / 10 errors，均为 `NotImplementedError`），实现后 GREEN 12 passed；连同 `test_c04_accuracy.py` 共 19 passed。
- 真实数据试运行：在会话临时目录用辅助判定试填两课副本，`convert` 结果与辅助数逐条一致（course1 64/76、58/61；course2 61/68、45/58），263 行含转义 `\|` 的名称全部正确解析。试填产物只在临时目录，不入库，不是签收。
- 仓库内两份副本为空白待填；对它们运行 `convert` 时已实测拒绝并列出未填条数（137 / 126），没有写文件。
- 回滚：`git revert` 该提交；签收仍可走直接编辑 JSON 的路径。
- 追加 `read_marks` / `apply_marks`（网页回写用：只改「判定」「依据」两列，`|` 换全角，清空后与原行逐字节相同）；新增 3 例 RED 3 failed → GREEN，文件共 15 passed（连同 `test_c04_accuracy.py` 22 passed）。
- 用户要求「做成临时网页」：本机临时服务只在会话临时目录（`scratchpad/c04web/`，不入库），只监听 127.0.0.1，校验 Host / Origin，只写 `*-worksheet-user.md`（经 `apply_marks`）与转换结果；转换复用 `to_judgments`，拒绝规则不变。先在临时副本目录走通：快捷键判定、依据回写、全部填满后转换与辅助数一致、缺 1 条时拒绝且不写文件；之后才对真实目录启动，真实副本仍为空白。
