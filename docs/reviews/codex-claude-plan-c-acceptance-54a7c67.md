# Codex 复审：计划 C 验收收尾（54a7c67）

- 日期：2026-10-04
- 审查基线 / 目标：`4a6308b..54a7c67`，10 个提交、24 个文件。
- 只读被审工区：`/Users/arvinhan/SmartSketch/.claude/worktrees/smartsketch-plan-a-fixes-e70a34`，`claude/plan-c-acceptance@54a7c67`。
- Codex 隔离复审工区：`/Users/arvinhan/.codex/worktrees/plan-c-acceptance-review/SmartSketch`，检出 `54a7c67`；本轮只新增自己的文档与脱敏复审资产，不改业务代码或原证据。
- 测量参考：`/Users/arvinhan/SmartSketch/.claude/worktrees/smartsketch-c03b-measure@88f9f6f`，严格只读。
- **结论：REQUEST_CHANGES。P1 0 项、P2 2 项、P3 2 项。** 已提交签收数据与准确率重算成立，未发现本次入库改动在已审路径上的业务语义回归；签收工具仍有结构校验和批量拒绝不写入的缺口。修复另开一轮，本轮没有修复。
- **stage_c_status: OPEN；technical_freeze: NOT_PERFORMED。**

## 1. 问题（按优先级）

下列源文件与行号全部对应被审提交 `54a7c67`，不是 Codex 修订后的代码。

### P2-01：工作表增行 / 增列可能被静默接受，重复行以末行覆盖判定

- 文件：`/Users/arvinhan/SmartSketch/.claude/worktrees/smartsketch-plan-a-fixes-e70a34/evaluation/c04_signoff.py:69–80`，尤其第 79 行；第 144–153 行。
- 触发：在已填工作表中复制同一节内的一行（行号、ID 相同），给两个副本填相反判定；或者在一行最后追加第八个单元格。
- 实际复现：`duplicate_row_conflicting_first`、`duplicate_row_conflicting_last`、`additional_column` 三种输入均被 `to_judgments` 接受。两个重复副本的先后顺序决定哪个判定保留。
- 原因：`_rows` 以行号作字典键，重复行先被覆盖；随后集合比较已经看不到新增行。转换只比较前五列、读取第六七列，没有要求单元格数量与原行相同。
- 影响：不符合“增删行、修改判定/依据以外的列就拒绝”的契约。工作表可能有冲突判定或额外列，导出的 JSON 却没有提示，损害后续签收的可复查性。
- 最小修复建议：解析阶段保留并校验行出现次数，拒绝重复行号 / 重复 ID；要求每行列数与原行严格一致，结构校验通过后再转换。保留现有 `\|` 处理及合法标记规则。
- 应补回归：实体和关系各自的重复行，正确/错误副本交换顺序，重复但同判定，额外列，少列；均拒绝；对 CLI 验证既有结果文件字节不变。已有真实 263 行没有重复，本问题**不意味着此次签收数字错误**。

### P2-02：默认两课批量转换在第二课拒绝时已覆盖第一课结果

- 文件：`/Users/arvinhan/SmartSketch/.claude/worktrees/smartsketch-plan-a-fixes-e70a34/evaluation/c04_signoff.py:194–206`、`218–233`（第 231 行逐课程立即转换写入）。
- 触发：默认 `convert` 同时处理两门课；course1 全部合法，course2 未填、非法或缺少副本；磁盘上已有上一轮结果。
- 实际复现：以合成预测和四份旧结果哨兵文件运行默认命令，exit 1，但 course1 的 `judgments-user.json` 和 `report-user.json` 都被覆盖，course2 结果未改。
- 原因：逐课程校验并马上写出，不先校验本次全部选中课程；后续拒绝不能撤销已写入的第一课。
- 影响：README 和交接承诺“拒绝时不写任何文件”，默认命令却会留下部分更新的签收批次。用户可能在失败后误认为全部旧结果仍被保留。
- 最小修复建议：将转换拆成全量读取/校验/计算与写出两阶段；选中课程全部通过才写出。写出阶段可用临时文件及替换降低单文件半写风险；不要把“校验失败零写入”和“多文件 I/O 事务原子性”混为一谈。
- 应补回归：默认两课，以及两种显式 `--course` 顺序；任一课程未填/非法/缺失时 exit 非 0，所有既有文件 SHA-256 不变，不新增文件；合法批次仍生成两课结果。单课拒绝的既有测试目前通过。

### P3-01：异常解栈及解锁抛错时遗漏 `lock_release_ms`

- 文件：`/Users/arvinhan/SmartSketch/.claude/worktrees/smartsketch-plan-a-fixes-e70a34/src/backend/app/workers/persist_graph.py:517–534`，尤其第 527–528 行。
- 触发：`_check_lease` / Neo4j / T6 抛错后，`held.__exit__` 仍执行解锁；或成功主体后 `held.__exit__` 自身抛 SQLite 错误。
- 实际复现：合成替身回放中，基线与新实现都沿原路径调用释放并返回 RELEASED，但新日志没有 `lock_release_ms`。前一种情况未开始解锁计时，后一种情况开始后未 stop；`_PersistSteps.log` 只输出已结束步骤。
- 影响：业务释放/异常传播顺序没有改变，但失败路径最可能需要解释的释放耗时仍留在总时间中，不能据此把日志称为“每个已开始步骤含抛错时都计时”。
- 最小修复建议：用覆盖异常解栈的 `finally` 路径计量 `held` 的退出时间，保持原课程锁释放、`_release` / `_after_failure` 与异常传播行为。
- 应补回归：事务失败并缓慢正常解锁、租约丢失后解锁、T6 后解锁抛 SQLite 错误；都应记录释放时间且业务调用顺序/返回值与基线一致。

### P3-02：当前签收 / 不补测状态与旧模板叙述并存，交接存在歧义

- 文件与行号：
  - `/Users/arvinhan/SmartSketch/.claude/worktrees/smartsketch-plan-a-fixes-e70a34/docs/handoffs/claude-plan-c-acceptance-closeout.md:122–128`、`178–180`：仍写“用户签收 OPEN”“judge 为空”“需要用户签收”。
  - `/Users/arvinhan/SmartSketch/.claude/worktrees/smartsketch-plan-a-fixes-e70a34/evaluation/raw/c04-signoff/README.md:21`：当前文件说明仍写“judge 为空 / null / 由用户独立填写”，与 §5 的已签收、复核后采纳不一致。
  - `/Users/arvinhan/SmartSketch/.claude/worktrees/smartsketch-plan-a-fixes-e70a34/docs/tasks.md:1809–1812`：标为“当前状态”的 MD/浏览器仍 WAITING_USER、出处核验仍 OPEN，准确率签收已在其他位置 DONE。
  - 同一任务板第 1842 行：“MD 抽取的 ≤60 秒只有思考开启时的旧数据（83.97 / 75.51 秒，未达标）”不够准确，这两个数字本身超过 60 秒。
- 触发：接手者读取“未完成”节或按任务 ID 查状态，而没有继续读追加节。
- 影响：可能重复要求签收、再次询问已经拒绝的补测，或误解 MD 的 ≤60 秒证据范围。最新签收段与决策表 §5 本身没有夸大为独立盲判，也没有把 PDF/SSE 当作 MD/页面首字证据。
- 最小修复建议：给旧模板内容明确标“初始化历史，已由 §10 取代”，或更新当前叙述；README 文件表改为实际已签收状态；当前任务行统一 NOT_EXECUTED（用户决定不做）与草稿出处 DONE。MD 改成“关闭思考未测；思考开启旧两次均 >60 秒、未达标”。保持原始证据文件不动。
- 应补回归：文档一致性检查，签收已 DONE 后没有未加历史限定的“judge 为空 / 签收 OPEN”；三项补测统一未测且不再 WAITING_USER；明确 PDF 两次 ≤60 秒不外推 MD，SSE 不代称页面首字。

## 2. 逐提交范围与审查方法

先读目标 AGENTS、任务板、相关规格、Claude 交接 §0 / §9 / §10；按以下顺序检查，不以最后一个文档提交替代代码审查：

| 提交 | 审查内容 |
| --- | --- |
| 2f1061c | C-ACC-A～D 认领、输入/输出/风险 |
| a094714 | 出处只读审计工具、5 个测试、实际证据与报告 |
| 4304fec | 唯一业务代码改动、3 个计时回归 |
| 452d446 | 原始预测/工作表、辅助判定、初始签收模板 |
| 03af1b9 | 决策表、任务板及初始交接 |
| b3c91b6 | 工作表转换工具、12 项测试、两课填写副本 |
| 4c6b56d | apply_marks / read_marks、3 项测试 |
| 7956b72 | 用户工作表/判定/报告、签收登记与措辞 |
| bf81d20 | 用户三项补测均不做的决定 |
| 54a7c67 | 复审请求、最终门禁登记 |

最后一次提交除了交接也更新了 `docs/tasks.md` 的门禁登记，但均为文档；`bf81d20..54a7c67` 无代码/数据变化。范围中唯一业务代码是 persist_graph.py；无 API / DTO / 契约 / 迁移 / 依赖变化。24 个源文件均与固定提交内容哈希相符，pending paths 0，清单在 `evaluation/raw/codex-c-acc-review-54a7c67/scope.json`。

### 入库语义核验

静态对比原主体及未改动的 `_release` / `_after_failure` / T6；另外用合成替身在原 `4a6308b` 与新 `54a7c67` 上比较 **27 种情形的业务调用顺序、参数、返回值与传播异常**：正常、驱动重跑、锁缺失、准备步骤 SQLite 错误、准备阶段 RuntimeError、取锁错误、进入持锁上下文失败、租约丢失、有效任务读取错误、Neo4j 存储/成环/关系/RuntimeError/ValueError/未捕获错误、T6 失败、退出解锁失败、释放/失败处理自身抛错、非法阶段。

- 候选读取 / build_plan / chunks 仍先于获取课程锁；锁未取得仍走原 `_release`。
- `_check_lease` 仍在持锁后、读取 `_effective` 和 Neo4j 写之前；scope 参数不变。
- work 每次调用仍写同一计划/来源；新增计数不进入业务判断。驱动重跑两次仍计 `neo4j_attempts=2`。
- Neo4j 成功后仍执行 T6，随后退出课程持锁上下文；失败处理仍在上下文退出后执行。
- `_release` / `_after_failure` 的参数、调用次数、返回值与异常传播在上述探测中等价；新外层不吞异常。
- `persist steps` 的字段仅任务编号、结果/异常类型、毫秒数和次数；没有增加正文、提示词、异常 message 或密钥记录。既有 logger.exception 路径未改。

这是覆盖已审路径的证据，不是对任意运行环境的形式证明。计时失败路径缺口见 P3-01。

### 出处只读路径核验

- `readonly_repositories` 替换 chunks / materials / tasks / services.graph.read 四处 connect，`finally` 恢复原绑定；新增离线探测也确认抛错退出后四处均恢复。
- 详情服务读取 chunks/material_names，使用各仓储模块自身的 connect，替换能覆盖已审路径；工具自己的 effective/material 查询直接走 readonly_connect。未发现本调用链漏用普通写连接。
- readonly_connect 用 `mode=ro&immutable=1`、query_only，只读测试实际拒绝 DELETE，未调用迁移或建目录。
- 图谱链路为 GraphReader → Neo4jRepository.read，查询都是 MATCH/RETURN，没有 write/write_transaction 或写路由调用。读路由是实际代码路径，不把它当作权限隔离的万能保证。
- 报告限制明确记载测量服务已停、WAL 0 字节、库前后哈希一致；immutable 使用依赖此前提。工具本身未强制检查停服/WAL，因此以后复跑须先核前提，不能拿主库哈希不变证明活跃 WAL 的一致性。
- 本轮只核代码、已有报告与主库哈希，不连接共享 Neo4j，不重新跑真实出处核验。已存证据为两课草稿 76/76 与 68/68、79/76 条可定位出处、缺陷计数 0；本轮读取主库 SHA 与其中前后值相同，WAL 当前 0 字节。已发布副本未测，不外推。

## 3. 签收数据与措辞核验

两课原始 predictions / worksheet 共四份 SHA-256 与测量区同名文件**逐字节一致**；两份用户判定 JSON 与 `to_judgments` 从工作表重新生成的对象完全一致；两份报告与 `judge_report` 重算对象完全一致。

| 课程 | 实体 | 关系 | 结论 |
| --- | --- | --- | --- |
| course1 PDF | 64/76 = 84.21% | 58/61 = 95.08% | 两项 ≥70%，实体数量 ≥20 |
| course2 PDF | 61/68 = 89.71% | 45/58 = 77.59% | 两项 ≥70%，实体数量 ≥20 |

- 263/263 判定与辅助一致，35 条判错。辅助依据含 `#行号` 前缀，用户依据没有该展示前缀；去除前缀后，30 条依据正文相同，5 条移除含“请复核”的括号注释。不是声称 30 份 notes 原始字节相同。
- tasks 的最新签收段、README §5、交接 §2/§10 均明确“逐条复核后采纳辅助判定、不是独立盲判”，这些关键段落没有夸大。
- 人工复核过程依据用户在本轮请求中的明确确认；本轮没有独立观察那次网页操作，`is_human_judgment=true` 本身也不是人类操作的技术证明。
- course2 关系再改错 4 条仍为 41/58 ≥70%，改错 5 条成为 40/58 <70%；保留质量余量风险。
- 正常 `\|` 单元格解析、apply_marks 只更改判定/依据列、`|` 转全角替代字符、清空后原数据行逐字节恢复均通过离线核验。判定人是单独的允许填写元信息。
- 未填、非法标记、✗ 无依据、空判定人、大小写混合的 CLAUDE-ASSIST、删行均确实拒绝；重复行/增列和批量零写入例外见两项 P2。

## 4. 不补测决定与未测边界

决策表 §5 的三项结论清楚且正确：

1. 浏览器可见首字未测；服务端首 delta 779–2918ms 与客户端 SSE 783–2927ms **不等于页面首字 ≤3 秒**。
2. 关闭思考的新 Markdown 抽取未测；≤60 秒证据仅是两份 PDF 20.90 / 28.08 秒。旧思考开启 MD 83.97 / 75.51 秒均未达标，既有 MD 课程 QA 不是新 MD 抽取。
3. v3 + 思考开启同 13 题基线未测；可以报告当前 v3 + 关闭思考下 11 answered / 2 not_covered / 0 error，不能隔离地量化关闭思考贡献。

尊重用户三项都不做的决定；本轮未补测，未寻求或使用新增预算。course1 persisting 6471ms、旧末段 15.643 秒根因仍 OPEN，新埋点不补造历史成因。

## 5. Codex 本轮实际验证

执行前读取了测试与门禁脚本。新 worktree 无 `.env` 与业务 SQLite，依赖仅软链既有安装，不安装/升级。完整门禁用 `env -i` 清空继承环境（比逐项 env -u 更完整），仅保留运行必需变量；PATH 包含 `~/.docker/bin`；缓存 Neo4j 镜像、一次性容器、临时库、本机假供应商。未在 Claude 或测量区执行门禁。

| 本轮命令 | 实际结果 |
| --- | --- |
| `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src/backend .venv/bin/python -m pytest tests/backend/test_c02_phase_logs.py tests/tooling/test_c_acc_sources.py tests/tooling/test_c04_signoff_sheet.py tests/tooling/test_c04_accuracy.py -q -p no:cacheprovider` | **33 passed**；日志 `/private/tmp/codex-c-acc-54a7c67-targeted.log` |
| `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src/backend .venv/bin/python evaluation/raw/codex-c-acc-review-54a7c67/review_checks.py`（最终脚本首次在 /private/tmp 运行） | exit 0；27 个语义比较一致、四份源哈希一致、签收重算一致；发现三种结构异常被接受及批量 exit 1 部分写入。探测脚本 exit 0 表示证据采集完成，**不是没有缺陷** |
| 隔离 `./scripts/verify.sh integration`，54a7c67 代码树 | **exit 0**；计数见下表；日志 `/private/tmp/codex-c-acc-54a7c67-integration.log`，退出码 `/private/tmp/codex-c-acc-54a7c67-integration.exit` |
| `git diff --check 4a6308b..54a7c67` | exit 2；唯一提示 `docs/tasks.md:1844: new blank line at EOF`，文档空白告警，未修改被审分支 |

| 层 | PASS | 登记 SKIP | FAIL |
| --- | ---: | ---: | ---: |
| backend + tooling | 3893 | 27 | 0 |
| frontend（38 文件，type-check/build 通过） | 934 | 0 | 0 |
| integration | 393 | 4 | 0 |
| backend-live | 44 | 0 | 0 |
| 演示 E2E | 2 | 0 | 0 |
| 个人本机假供应商 E2E | 4 | 0 | 0 |

文档落盘后又运行了定向测试与最终复审脚本，均实际 exit 0；补充 basic 文档门禁的会话被中断，未收集最终退出码（日志 `/private/tmp/codex-c-acc-54a7c67-basic-final.log`），不登记为 PASS，也不拼接为完整门禁结果。此前整次 integration 已独立取得 exit 0。

实际计数与 Claude 最终报告一致，但上述是 Codex 自己运行，不借用其 PASS。31 个既有登记 SKIP 不算 PASS；测试没有改动。两项 P2 的新边界尚未纳入原测试，门禁通过不消除复审发现。

完整门禁复现（仅此隔离工区，先检查端口）：

```bash
cd /Users/arvinhan/.codex/worktrees/plan-c-acceptance-review/SmartSketch
/usr/bin/env -i HOME="$HOME" USER="$USER" LANG=en_US.UTF-8 \
  PATH="$PWD/.venv/bin:$PWD/node_modules/.bin:$HOME/.docker/bin:/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin" \
  PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$PWD/src/backend" PYTHON=.venv/bin/python \
  E2E_API_PORT=19000 E2E_WEB_PORT=16073 E2E_NEO4J_PORT=18588 \
  E2E_PROVIDER_PORT=19790 VERIFY_NEO4J_PORT=18589 \
  PLAYWRIGHT_CHROMIUM_EXECUTABLE='/Applications/Google Chrome.app/Contents/MacOS/Google Chrome' \
  /bin/bash ./scripts/verify.sh integration
```

隔离 E2E 证据保存在本工区 `.e2e/20261004-061221`（演示）、`.e2e/20261004-061335`（个人假供应商），属于忽略的测试产物，没有复制真实业务库/课程正文/凭据。复审资产只有代码、计数、编号、哈希及状态。

复审核对脚本曾先后两次因按字节比较辅助依据展示前缀/复核注释而停下；修正的是 Codex 自己的核对脚本，未改源数据。最终按显式去行号前缀、去复核注释规则得到 30+5，保留最终可复现脚本与结果，不把早期失败当成签收不一致。

## 6. 四项结论与未验证范围

| 项 | 结论 |
| --- | --- |
| 工程门禁通过 | **是**：Codex 在 54a7c67 隔离工作副本整次 integration 实际 exit 0；不等于复审无问题 |
| 真实测量已完成 | **是，仅已执行范围**：DeepSeek 的两份 PDF 与当前配置 13 题 QA；本轮无新增测量，三项不补测仍写未测 |
| 人工准确率已签收 | **是**：用户 arvin 已确认逐条复核后采纳辅助判定，非独立盲判；263 项记录与报告重算一致 |
| 技术冻结已执行 | **否**：stage_c_status OPEN、technical_freeze NOT_PERFORMED |

未验证：共享 Neo4j 当前数据没有本轮重读；两课发布副本出处没有真实测量；临时签收网页源码不在提交范围，本轮不核其监听/Host/Origin/保存实现；人工操作过程不由本轮复演；三项补测按用户决定不做；历史慢段根因未定位。上述不通过模型或假供应商门禁补成真实证据。

Claude tracked 文件与固定提交的 24 个哈希一致；未跟踪 `.claude/launch.json` 不属于交付、未读内容；测量分支 HEAD 88f9f6f、工作区干净。未修改/提交/合并/推送它们。真实生成、在线向量增量均 0；台账 **844451 / 900000**、向量 **12005** 另计。

## 7. 需要用户决定的事项

1. **是否执行技术冻结**：本轮不代为决定。建议先另开一轮修复两项 P2，并处理 P3 文档/日志问题后再复审；若选择带已知问题冻结，应明确哪些评测工具/未测项不在冻结承诺内。
2. 是否将异常解锁计时、当前文档状态统一纳入下一轮修复；本轮只报告，不改代码。
3. 冻结时接受并保留：浏览器可见首字、关闭思考 MD 新抽取、v3 开启基线未测，历史慢段根因 OPEN，草稿出处核验不外推发布副本。用户已决定不补测，不再重复询问是否跑这三项。

下一位修复者应从固定 54a7c67（或明确包含它的更新基线）开始，先为本报告 P2/P3 写失败回归，再最小修复；不修改已签收原始证据，不重新花钱测 PDF/QA。

## 后续修复轮勘误与状态指针（2026-10-04）

用户随后批准先修复再自行检查。本文件仍是对 54a7c67 的历史复审，不用修复后的 PASS 覆盖历史结果；当前交接改用 `docs/handoffs/codex-plan-c-acceptance-fixes.md`。

P2-01 初次 `review_checks.py` 的 `additional_column` 探测实际上使用 `row[:-1] + ...`，把文字填到了合法的第七列「依据」，不是新增第八列，因此该探测的接受不能作为增列漏洞证据。重复行探测和源码缺列数校验的归因不变。修复轮已用实体/关系真正追加第八列、删至六列及新增畸形行的回归，在原代码上实测失败（连同重复行/批量测试共 23 failed / 16 passed）；修复后相关套件通过。新探测改用 `row + ...` 且断言拒绝，旧探测/JSON 不覆盖。本勘误不修改真实签收文件或原始测量数字。
