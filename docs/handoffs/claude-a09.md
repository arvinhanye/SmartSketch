# A09：定义问答终态和引用撤回协议

- **task_id**：A09（`docs/atomic-task-plan.md` / `docs/atomic-tasks.json`）
- **状态**：DONE（ADR-015 已签收）。决定方向由 ArvinHan 于 2026-09-23 在会话中逐项选定（流式方案、证据不足的表达、截断按默认、问答记录命名），四节设计（链路与文法、流内校验与哨兵、终态矩阵与撤回、历史与跨版本）逐节确认；书面条文 ADR-015 同日**签收**（含第三节所列两处细化）
- **review_status**：ready_for_review（以交付提交为准，提交前不生效）
- **worktree**：`/Users/arvinhan/Desktop/SmartSketch/.claude/worktrees/a09-dev-environment-check-8e5e93`
- **分支 / base**：`claude/a09-dev-environment-check-8e5e93` / base `f9dfc8f`（`origin/main`，含 PR #13、#17、#19）。PR #16（`claude/fix-r01-r02`）与 PR #18（`claude/a10-integration-map`）在开工时仍为 OPEN，未叠放
- **head_commit**：本文件与四个交付文档随同一个交付提交入库（`git log -1 -- docs/handoffs/claude-a09.md` 可查）。内容指纹：`specs/grounded-qa.md` 的 `shasum -a 256` 前 16 位 `149c394cf20b5985`；`git diff f9dfc8f <该提交> -- docs/architecture.md docs/decisions.md docs/tasks.md | shasum -a 256` 前 16 位 `f1975b01b5928ddd`
- **类型**：仅文档任务。无代码、无依赖变更、无合并；未改 `src/contracts/`、`events.v1.md` 或任何分支 worktree

## 一、开工检查

同一会话先做了环境检查，记录在 `docs/handoffs/claude-a09-env-check.md`。该文件保留不删：A10 的 ADR-016（PR #18）按文件名引用它，说明 ADR-015 留给 A09。要点：依赖 A02、A04 已在 main；输入 R03/R04、S2 docx、`740adb` `978671e` 真源均可读；目标文件无人占用；main checkout 落后 `origin/main` 且有 Codex 未提交改动，因此一律在本 worktree 开发。

## 二、交付物

| 文件 | 变更 |
| --- | --- |
| `specs/grounded-qa.md` | main 新建，以 `740adb` `978671e` 草稿桩为底稿（保留用户故事、四道措施、链路、隔离与验收 1～13 的原编号）。新增「问答终态与引用撤回协议」Q1～Q12：术语、开流前后分段与事件文法、允许引用集合 A、标记格式与归一化闭集、流内状态机与不变式 I1/I2、哨兵、终态构造与模板、终态矩阵 O1～O15、客户端撤回规则、JSON 模式、多轮历史、跨版本、日志、接口表、QA-1～35 |
| `docs/decisions.md` | 新增 ADR-015（已签收），8 条决定 |
| `docs/architecture.md` | `NotCoveredReason` 行加注提议改名、取值暂不改；问答 SSE 行补首条 `meta`、断开与撤回；「文档用语 → wire 值」加「临时正文 / 引用撤回」一行；核心数据模型 `QuestionSession` 改为 `ChatLog`（表 `chat_logs`） |
| `docs/tasks.md` | 追加 A09 行（DONE，ADR-015 已签收）与两条说明 |
| `docs/handoffs/claude-a09.md` | 本文件 |

## 三、关键决定（ADR-015）

1. 检索与阈值判定之后才开流；开流前失败为 HTTP 错误；开流后 `meta delta* (done | error)`，`meta` 恰好一条且为首条；`meta` 与 `final` 加 `graph_version`、`request_id`。
2. 流内逐引用校验：只给同课程、属绑定版本修订、可定位的块编号；`[n]` 为规范标记；归一化闭集两条；伪标记与未知编号当场剔除；代码片段内不识别。`answered` 时 `final.answer` 恒等于 delta 拼接。
3. 模型以 `<<INSUFFICIENT_EVIDENCE>>` 开头声明证据不足；`out_of_course_scope` 改名 `insufficient_evidence`。
4. 只有 `done` + `answered` 保留正文，其余一律撤回；中断与超时不做部分校验；截断按正常结束判定；`LLM_UNAVAILABLE` 以 `details.reason ∈ {upstream, stream_interrupted, timeout, auth}` 区分。
5. `not_covered` 的 `answer` 为服务端模板。
6. 服务端不保存会话；历史只用于改写，生成不见历史；`kp_id` 不在版本中则忽略。
7. 回答钉在绑定版本，不追溯撤回。
8. 问答记录定名 `ChatLog` / `chat_logs`（关闭 A10 N5）。

**比设计讨论多出的两处细化**（均为落实已确认设计所需，已随 ADR-015 一并签收）：`ChatAnswered` / `ChatNotCovered` 也带 `request_id`（JSON 模式没有 `meta`，否则无从取得）；Q6 第 5 条「同一对话同时最多一个在途请求」（否则历史组成 H1 无法定义）。

## 四、验证

| 命令 / 方法 | 结果 |
| --- | --- |
| `./scripts/verify.sh` | exit 0（`block-dangerous hook tests passed.`、`Scaffold verification passed.`） |
| `git add -N specs/grounded-qa.md && git diff --check` | exit 0（随后 `git reset` 撤销意向添加） |
| 核对脚本 `check_a09.py`（草稿区，不入库） | **45/45 PASS**。覆盖：章节与锚点；QA 编号连续且任务标签均为原子任务 ID；O1～O15 结构与撤回列；A09 四条原子验收均映射到 QA；验收 1～13 与桩原编号逐条一致；`NotCoveredReason` 架构行与 `978671e` YAML 逐值一致、规格改后闭集正确；事件名在文法、YAML、架构三处一致；错误码均为现有码或已标「提议」；IAM `chat` 行与 IAM-12；A07 首字前 / 出字后切换规则与预算拒绝规则；两个问答超时变量已登记；ADR 引用存在、ADR-015 已签收且决定 3、8 内容对应；哨兵字面量与长度处处一致；A04 / A07 移交原文存在；YAML 尚无 `graph_version` / `request_id`（「新增」措辞准确）；Q11 覆盖全部消费方；`740adb` 命名门禁的禁用别名；`NOT_COVERED` 未作 wire 值；任务行与 `ChatLog` 定名 |
| 篡改负例 `tamper_a09.py`（草稿区） | **19/19 被检出**，每个都由其目标检查项报出、exit 1、无崩溃：删 QA-20、ADR 哨兵漂移、O8 改为切备用、O11 去「提议」、`QuestionSession` 回归、P1 教师码写错、验收 10↔13 换号、臆造 `LLM_TIMEOUT`、断锚点、架构枚举提前改名、O5 不撤回、`NOT_COVERED` 作 wire、A07 行翻转、删 B13 接口行、暂扣长度写错、坏任务标签、ADR 签收状态被改回待签收、任务行仍标待签收、O1 调用生成 |
| 流内状态机参考模型 `ref_stream.py`（草稿区，一次性，不入库） | **19/19 PASS**：QA-1～3、8～16 的示例与规格结论一致；answered 时 I1、I2 成立；每例 200 种随机分块加逐字分块结果完全相同（分块无关）；哨兵与标记跨块时不下发任何残片 |

未运行：`docs/reviews/validate_atomic_plan.py`（其 `ROOT` 写死为 main checkout，且本任务未改 `docs/atomic-tasks.json` / `docs/atomic-task-plan.md`）；任何后端、前端或契约生成测试（尚无实现，契约未改）。

## 五、接口 / 数据 / 配置变更

- **契约**：本任务不改 `src/contracts/`。提议的改动全部列在规格 Q11，由 B13 / B08 落实：`NotCoveredReason` 改名；`ChatMetaEvent`、`ChatAnswered`、`ChatNotCovered` 加 `graph_version`、`request_id`；`details.reason` 闭集；`Error.details.request_id`；`events.v1.md` §3 指向规格；三个提议错误码；`errors.v1.md` 的 `RATE_LIMITED` 措辞。
- **数据**：问答记录实体 `ChatLog`、表 `chat_logs`，一请求一行；字段下限见规格 Q10，建表归 J10。
- **配置**：不新增变量；沿用 A07 的 `LLM_CHAT_TIMEOUT_SECONDS`、`LLM_CHAT_FIRST_TOKEN_TIMEOUT_SECONDS`。

## 六、未完成项与风险

- **ADR-015 已签收**（ArvinHan 2026-09-23），规格、ADR、架构注记与任务行的状态已同步。
- **待细化仍未签收**：阈值取值与调参（K01，依赖 D-01）；性能 3 / 10 / 15 秒的关系与超时取值（D-02e）；`BUDGET_EXCEEDED` 的码与 HTTP 状态（D-02f）；历史保留轮数；召回、跳数、token 预算；模板与错误文案定稿；防注入层次；日志留存与脱敏。
- **已知局限**（已写入规格）：未放进反引号的 `a[1]` 会被当作类标记，编号在集合内时成为一个引用，不在时被剔除。J05 用提示约束，K03 评测统计误判。
- **合并冲突预期**：PR #16 与 PR #18 都改 `docs/tasks.md`、`docs/decisions.md`（PR #16 另改 `docs/architecture.md` 一行，PR #18 不改该文件）。PR #16 改的是架构文档原第 124 行（向量空间），本任务改的是原第 84、92、100（其后插一行）、110 行，互不相邻；`docs/tasks.md`、`docs/decisions.md` 三方都在文件末尾追加，合并时会有文本冲突，手工保留各方内容即可。A10 的 N1（`SourceChunk` → `Chunk`）在其批 1 执行、不在 PR #18 中；它要改的原第 111 行紧挨本任务改的原第 110 行，届时可能出现相邻行冲突，按行合并即可。
- **A10 门禁耦合**：PR #18 的批 1 门禁扫描清单需在本规格合入后加回 `specs/grounded-qa.md`，并用负例证明。

## 七、回滚

仅文档变更。未提交前：`git checkout -- docs/architecture.md docs/decisions.md docs/tasks.md` 并删除 `specs/grounded-qa.md` 与本文件。提交后：`git revert <交付提交>`。不涉及数据、依赖或其他工作区。

## 八、下一位的首个动作

请 Codex 按 `docs/claude-review-workflow.md` 审查本范围（以交付提交为准）；修复另开一轮。实现方从 B13 开始：先改真源中的 `NotCoveredReason` 与四个字段，再按 Q11 分派 J 组。

## 九、第二轮：Codex 审查修复（A09-R01 / A09-R02）

- **task_id**：A09-R01/R02 修复（Codex REVIEW-12），A1～A10 收尾的一部分
- **状态**：DONE。A09-R01 的方向由 ArvinHan 于 2026-09-24 在会话中选定（逐句引用，否则撤回）；ADR-015 修订 1 的书面条文与决定 10 已由 ArvinHan 于 2026-09-24 签收
- **review_status**：ready_for_review（以交付提交为准）
- **worktree / 分支**：同上，base `1754c96`
- **审查报告**：主目录 `docs/reviews/codex-claude-a09-1754c96-2026-09-23-1400z.md`（尚未入库）

| 问题 | 修改 |
| --- | --- |
| **A09-R01**（P2）只要有一个有效编号，无出处的结论也能成为 `answered` | 新增 Q3.5「结论单元与逐句覆盖」：流结束后，在代码片段外以换行与句末标点切分（`3.14` 不切开、句末标点后的标记归属前一单元、标题行与纯代码单元除外），每个结论单元至少带一个有效标记才可 `answered`（新不变式 I3），否则为 `not_covered` / `all_citations_invalidated`，日志子类 `uncited_sentence`，客户端整段撤回。wire 枚举不变。明确验收边界：在线只保证每句有合法出处，语义支持度由 K03 衡量。同步措施②④、Q4、O4～O6、Q11（J05/J06/K03）、QA-2、QA-16、主验收第 2 条，新增 QA-36（审查示例）、QA-37（切分边界） |
| **A09-R02**（P2）「每请求一条日志」与鉴权前置冲突 | Q10 改为只记通过 P2 的请求，`request_id`、`user_id`、`course_id`、`version_id` 均非空；P1/P2 拒绝不写 `chat_logs`，只写结构化应用日志，不伪造缺失字段。QA-34 限定范围，新增 QA-38；`docs/architecture.md` 的 `ChatLog` 一行同步 |

**为何复用 `all_citations_invalidated`**：前端对它的处理（撤回 + 模板「生成的回答无法与课程资料对应，已撤回」）对逐句未覆盖同样适用；新增 wire 值会让 B13 与前端多一处分支。代价是名称字面上只说「全部引用无效」，因此在 Q4 把 wire 语义写成「未能通过引用校验」，以三个日志子类区分。签收时确认沿用该值；日后若要单独的 wire 值，只需改 Q3.5 第 4 条、Q4、O5 与 B13 一行。

**验证**（本 worktree，脚本在会话草稿区，未入库）：

```text
python3 check_a09r.py .（修改前）       27 FAIL / exit 1
python3 check_a09r.py .（修改后）       ALL PASS / exit 0
python3 neg_a09r.py . <scratch>        9 个篡改副本全部 exit 1，各自命中目标断言
python3 ref_q35.py                     11/11 PASS：按 Q3.5 条文写的参考切分器，对 QA-1、2、13、16、36、37 的示例得出与规格相同的结局与未覆盖单元数
./scripts/verify.sh                     exit 0
git diff --check                        exit 0
```

参考切分器首跑有 1 项失败（QA-13），原因是参考模型把反引号内的 `[1]` 当成有效标记，属于模型实现缺陷而非规格问题，修正后通过。

**已知局限**（已写入 Q3.5 与推翻条件）：引导句、过渡句也须带引用，模型漏标时会多出 `not_covered`；`e.g. ` 这类缩写后接空格会被切开，J05 提示应避免。K03 统计 `uncited_sentence` 撤回率。

**签收**：ArvinHan 2026-09-24 在会话中签收 ADR-015 修订 1，规格状态行、ADR 与任务行已同步。

**下一步**：请 Codex 按交付提交复核。
