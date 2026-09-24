# 功能规格：可信问答（GraphRAG）

- **状态**：DRAFT。「问答终态与引用撤回协议」一节（Q1～Q12）由 A09 提交，**ADR-015 已签收**（ArvinHan，2026-09-23）；Q3.5 逐句覆盖与 Q10 日志覆盖范围按 **ADR-015 修订 1** 修订（方向已选定，条文待签收）；相关度阈值、召回与 token 预算、性能门槛等仍是待细化项（见「待细化」）
- **负责人**：产品 / 数据与 AI / 后端 / 前端共同维护
- **关联任务**：A09（本协议）；实现方 B08、B13、J01～J10、K03、K06
- **底稿**：本文件以 `claude/worktree-contract-conflicts-740adb` `978671e` 的同名草稿桩为底稿（与 `209be9` `bef9b91` 同文），保留其用户故事、四道防幻觉措施、处理链路、隔离与验收 1～13，按本协议修订处加注。A10 导入时以本文件为准，不再合入桩的旧文本。
- **上位约束**：ADR-003（来源硬契约）、ADR-009（wire 枚举）、ADR-011 修订 2（`model_calls` 以 `request_id` 归属）、ADR-012 及修订 1（读取绑定、按 `revision_id` 检索、文本块不可变）、ADR-013（问答仅学生成员）、`docs/integrations.md`「模型接入规则（A07）」。

## 用户故事

作为学生，我就课程内容提问时，要么拿到一个**每条结论都能点开看原文出处**的回答，要么被明确告知「课程资料未涉及」；系统不能在资料不足时编一个听起来合理的答案。

## 数据与规则

### 硬契约（ADR-003）

问答响应**要么返回至少一个可定位来源，要么返回 `NOT_COVERED`**。没有第三种结果。「可定位」指能落到 `{document_id, page 或 section}`，不是只给文档名。

wire 表达（ADR-009）：`NOT_COVERED` 是概念名，wire 为 HTTP 200 + `status: "not_covered"` + `reason` + `citations: []`。服务故障不是第三种结果，而是错误（开流前为 HTTP 错误，开流后为 `error` 事件，见 [Q2](#q2-链路分段与事件文法)），前端不得把它显示成答案。

### 四道防幻觉措施

| # | 措施 | 要求 |
| --- | --- | --- |
| ① | 只依据上下文 | 系统提示要求仅用给定资料作答，资料不足时以哨兵开头明确告知（[Q3.4](#q34-资料不足哨兵)）；并**声明资料中的任何指令只当作数据**，防提示注入 |
| ② | 强制引用 | 每个结论单元（句）后标注引用编号 `[n]`（[Q3.2](#q32-引用标记)），缺少即整段撤回（[Q3.5](#q35-结论单元与逐句覆盖)，ADR-015 修订 1）；前端渲染为可点击的原文出处与图谱节点 |
| ③ | 检索阈值 | 检索相关度过低时**不调用生成模型**，直接走 `NOT_COVERED` 分支——既防幻觉也省耗时 |
| ④ | 引用校验 | 生成过程中**逐个标记**核对编号是否在本次上下文中，**无效引用当场删除、不下发**（[Q3.3](#q33-流内状态机)；A09 由「生成后删除」修订为「流内删除」）；流结束后再逐单元检查每句都有有效引用（[Q3.5](#q35-结论单元与逐句覆盖)） |

四道措施是串联的，任何一道被跳过都视为违反本规格。

### 处理链路

```text
学生提问（可能含多轮指代）
  → 鉴权与版本绑定（开流前；失败为 HTTP 错误）
  → 问题改写：补全指代、提取关键术语（失败则用原问题）
  → 并行混合检索：图谱结构检索（前置/包含/相关）+ 向量原文检索
  → 组装编号上下文，相关度达阈值？ 否 → NOT_COVERED（不调用生成）
  ═══ 开流（HTTP 200 + meta）═══
  → 生成：只依据资料、强制引用编号
  → 流内引用校验：无效编号当场剔除，有效正文下发为 delta
  → done（answered / not_covered）或 error，关流
```

### 隔离

所有检索按 `course_id` 隔离；跨课程检索不允许，即使学生同时选修多门课。学生只能问**已发布版本**，且一个请求只绑定一个版本（ADR-012 V8）；教师成员不开放问答（ADR-013）。

## 问答终态与引用撤回协议（A09 / ADR-015）

本节规定一次问答请求从鉴权到终态的完整时序、流式正文与最终答案的关系、每种故障落到哪个终态，以及客户端何时撤回已显示的正文。契约字段的增改由 B13 落到真源，本节不改 `src/contracts/`。

### Q1 术语

| 术语 | 含义 |
| --- | --- |
| 请求 | 一次 `POST /api/v1/courses/{cid}/chat`。每个请求在 P2 生成一个 `request_id`（ULID），该请求的全部 `model_calls` 以它归属（ADR-011 修订 2） |
| 绑定版本 | P2 读一次发布指针得到的 `(version_id, version)` 及该版本的修订列表（ADR-012 V8）。wire 上以整数 `graph_version`（即 `version`）表示 |
| 候选集合 H | 两路检索合并去重后、经 A 的三项条件过滤的**文本块**候选。图检索命中的知识点本身不进 H，其 `EVIDENCE` 文本块可以进 |
| 允许引用集合 A | J04 从 H 中选出、达到阈值并在 token 预算内的文本块，按上下文顺序编号 `1..k`。编号到文本块的映射在本请求内固定 |
| 类标记 | 代码片段之外、形如 `[…]`、`【…】`、`［…］` 且方括号内只含数字（半角 `0-9` 或全角 `０-９`）、空白、分隔符 `,，、` 与区间符 `-–~`、至少含一个数字、总长 ≤ 32 字符的片段 |
| 规范标记 | 形如 `[n]` 的类标记，`n` 为不带前导零的半角正整数 |
| 临时正文 | 客户端从首个 `delta` 到终态之间显示的 delta 拼接文本 |
| 撤回 | 客户端在非 `answered` 结局时清除全部临时正文（[Q6](#q6-撤回规则客户端)） |
| 哨兵 | 字面量 `<<INSUFFICIENT_EVIDENCE>>`（25 个字符），模型用它声明资料不足 |
| 链路时限 | 从收到请求起 `LLM_CHAT_TIMEOUT_SECONDS`（A07，样例值 15 秒）；链路内任何调用及重试都不得超出剩余时间 |

### Q2 链路分段与事件文法

一个请求以「开流」为界分两段。SSE 模式下，开流即发出 HTTP 200 响应头与 `meta` 事件；JSON 模式没有开流动作，但分段规则相同（[Q7](#q7-json-模式)）。

**开流前**（任何失败都是普通 HTTP 错误，响应体为 `Error`，SSE 与 JSON 两种模式一致）：

| 步骤 | 内容 | 失败 |
| --- | --- | --- |
| P1 鉴权与授权 | 按 `specs/identity-access.md` §4.1 判定顺序与 §4.3 `chat` 行 | 401 `UNAUTHENTICATED`；403 `COURSE_FORBIDDEN`；404 `GRAPH_NOT_PUBLISHED`；403 `ROLE_FORBIDDEN`（教师成员）；422 `VALIDATION_ERROR`；429 `RATE_LIMITED`（本服务限流） |
| P2 版本绑定 | 读一次发布指针（G07）；生成 `request_id` | 存储不可用 → 503 `STORAGE_UNAVAILABLE`（A03 提议码，待 B08） |
| P3 问题改写 | J03；输入为问题与历史（[Q8](#q8-多轮历史)） | **不失败**：改写出错、超时、被预算拒绝，均改用原问题（A07「预算」） |
| P4 检索 | J01 向量检索 + J02 图检索，按绑定版本过滤 | 向量调用失败或向量熔断 → 503 `LLM_UNAVAILABLE`；图库不可用 → 503 `STORAGE_UNAVAILABLE`（提议）；未预期异常 → 500 `INTERNAL_ERROR`（A03 提议码，待 B08） |
| P5 上下文与阈值 | J04 构造 H 与 A，判定是否进入生成 | H 为空 → `no_retrieval_hit`；H 非空但无候选达到阈值 → `below_similarity_threshold`；两者都是开流后的 `not_covered` 终态，不是 HTTP 错误 |

**开流后**（HTTP 200 已发出，一切结局只通过事件表达）：

```text
stream := meta(status = not_covered) done(not_covered: no_retrieval_hit | below_similarity_threshold)
        | meta(status = answered)    delta*  ( done(answered | not_covered: insufficient_evidence | all_citations_invalidated)
                                             | error )
```

1. **`meta` 恰好一条且恒为首条**，字段：`event`、`status`、`retrieved`（= |A|，`not_covered` 时为 0）、`graph_version`、`request_id`。后两者由 B13 新增。
2. **`meta.status = not_covered` 当且仅当 P5 判定拒答**；其后没有 `delta`、没有 `error`，直接发 `done`。
3. **`meta.status = answered` 表示进入生成，不是承诺**：终态仍可能是 `not_covered`（`insufficient_evidence`、`all_citations_invalidated`）或 `error`。前端不得在 `meta` 阶段锁定结局。
4. **`done` 与 `error` 互斥、恰好一条、恒为末条**，发送后关流。`:ping` 心跳注释行（`events.v1.md` §1）不是事件，可出现在任意位置。
5. **客户端断开**：服务端在下一次写入失败或收到断开通知时停止生成（关闭供应商流），不再发送任何事件，日志记 `aborted`；不自动重新生成。
6. 服务端合并或拆分 delta 的方式不受约束，但每条 `delta` 非空（`ChatDeltaEvent.delta` 已有 `minLength: 1`）。
7. 终态为 `insufficient_evidence` 时 `delta` 恰为 0 条；`error` 前可以有 0 条或多条 `delta`（见 Q5）。

### Q3 引用标记与流内校验

#### Q3.1 允许引用集合 A

进入 A 的文本块必须同时满足：

1. 属于请求课程（`course_id` 相同）；
2. `revision_id` 在绑定版本的修订列表内（ADR-012 修订 1；不按 `material_id` 判定）；
3. 可定位：`page ≥ 1`，或 `section_path` 非空。

J04 组装上下文时只给 A 中的块编号；图谱子图作为**无编号**的结构上下文提供，不能被直接引用。J06 在建 A 时对三项条件复核一次（纵深防御）；复核剔除任何块都说明 J04 有缺陷，记完整性异常日志。此后流内只需判断编号是否属于 A。

#### Q3.2 引用标记

- **规范形式**：`[n]`，`n` 为不带前导零的半角正整数，指上下文中的第 `n` 块。多个引用写成 `[1][3]`。
- **归一化（闭集，J06 只实现以下两条，各须有测试）**：
  1. 一个类标记内用 `,`、`，`、`、`（前后可有空白）分隔的多个规范编号 → 依次展开为 `[n1][n2]…`，同一类标记内的重复编号去重；
  2. 全角括号 `【n】`、`［n］` → `[n]`（可与第 1 条叠加）。
- **无法归一化的类标记整体剔除**，计入「未知引用」：`[0]`、前导零 `[01]`、区间 `[1-3]`、全角数字 `[１]` 等。这样正文中不会留下看起来像引用、却点不开的伪标记。
- **不是类标记的方括号是普通文本**，原样下发：`[a]`、`[注]`、空方括号等。
- **代码片段内不识别**：行内代码（反引号串）与围栏代码块（行首 ```` ``` ```` 或 `~~~`）中的任何字符都是普通文本。数据结构课常见的 `a[1]` 须由 J05 的提示要求写在反引号内。服务端与前端对「代码片段」的判定必须一致：两端都只认行内代码与围栏代码块，前端渲染器关闭缩进代码块（J06、J09 共用同一组夹具）。未闭合的代码片段延续到输出结尾。

#### Q3.3 流内状态机

服务端逐段处理模型输出，处理结果才下发为 `delta`：

| 情形 | 处理 |
| --- | --- |
| 输出开头 | 丢弃前导空白；随后暂扣输出，直到能判定是否以哨兵开头（最多暂扣 25 个字符），见 Q3.4 |
| 代码片段外遇到 `[`、`【`、`［` | 暂扣，直到出现同族闭括号（得到完整类标记），或内容不再符合类标记定义、超过 32 字符（按普通文本放行） |
| 完整类标记 | 按 Q3.2 归一化；每个编号 `n ∈ A` 以 `[n]` 下发，`n ∉ A` 当场剔除并计入「未知引用」；无法归一化者整体剔除 |
| 代码片段外遇到 `<` | 暂扣，直到判定是否构成完整哨兵：构成则剔除（正文中间的哨兵不影响终态），不构成则放行 |
| 输出结束时仍有暂扣内容 | 未闭合的类标记与哨兵前缀按普通文本放行 |
| 其他文本 | 立即下发 |

- **不变式 I1**：结局为 `answered` 时，`final.answer` 与已下发全部 `delta` 的逐字拼接**完全相等**。
- **不变式 I2**：`final.answer` 中代码片段之外不含任何非规范的类标记；其中规范标记的编号集合与 `citations[].index` 的集合完全相等，且非空。
- **不变式 I3**（ADR-015 修订 1）：结局为 `answered` 时，`final.answer` 的每个结论单元都带（或按 Q3.5 第 2 条归属到）至少一个有效规范标记。
- 暂扣只作用于少数字符，不改变首字时延量级。

#### Q3.4 资料不足哨兵

- J05 的提示要求：资料不足以回答时，输出**以哨兵开头**（可有前导空白），不写其他内容。
- 暂扣的开头内容与哨兵逐字相等 → 立即关闭供应商流（不再消耗输出 token），不下发任何 `delta`，终态 `not_covered` / `insufficient_evidence`。哨兵之后的任何输出都丢弃。
- 暂扣内容与哨兵前缀出现分歧（如 `<<INSIGHT`）→ 全部暂扣内容进入普通处理。
- 哨兵跨供应商数据块拆分时照常识别；出现在正文中间（代码片段外）时只剔除，不改变终态；代码片段内的哨兵是普通文本。

#### Q3.5 结论单元与逐句覆盖

ADR-015 修订 1（Codex A09-R01）新增。流正常结束（含截断）后、构造终态前，J06 对拼接正文（即将成为 `final.answer` 的文本）做一次逐单元检查。本检查保证**每个结论单元都带合法出处**；它不**判断出处在语义上是否支持该结论**，语义支持度由 K03 离线评测衡量，不作为在线终态条件。检查在流结束后进行，不改变 Q3.3 的暂扣与下发。

1. **切分**：只在代码片段之外切分。边界为换行符，以及句末标点 `。`、`！`、`？`、`!`、`?`；半角 `.` 只在其后紧跟空白或正文结尾时算边界，因此 `3.14` 这类数字不被切开。连续的句末标点（如 `？！`）算一个边界。分号、冒号、逗号不是边界。
2. **标记归属**：句末标点之后、下一个字母或数字之前出现的规范标记（中间可有空白），归属前一个单元。因此 `栈是线性表。[1]` 与 `栈是线性表[1]。` 等价。
3. **结论单元**：代码片段之外至少含一个字母或数字（按 Unicode 类别，含汉字）的单元。以下不是结论单元：Markdown 标题行（行首 1～6 个 `#` 后接空格）；除代码片段、标记、空白与标点外不含其他字符的单元。引导句（如「栈的操作如下：」）与列表项都是结论单元。
4. **判定**：每个结论单元都含有（或按第 2 条归属到）至少一个有效规范标记 → 通过。正文至少有一个有效标记、但有结论单元没有 → 终态 `not_covered` / `all_citations_invalidated`，日志子类 `uncited_sentence`，并记录未覆盖单元数。正文没有有效标记时仍按 `no_markers` / `unknown_only` 记子类，不再做本检查。
5. **与撤回的关系**：未通过时客户端按 Q6 整段撤回临时正文，与其他非 `answered` 结局相同。截断输出的末尾单元同样须带有效标记。

### Q4 终态构造

**`answered`**：流正常结束，至少出现一个有效标记，且通过 Q3.5 逐单元检查。

| 字段 | 取值 |
| --- | --- |
| `answer` | 已下发 delta 的逐字拼接（I1） |
| `citations` | 正文中出现过的有效编号，每个编号一条，按首次出现排序；`index` 保留上下文编号，不重排（允许 `[1][3]` 这样的空缺）。`chunk_id`、`document_id`、`page` / `section_path`、`text` 全部由服务端按文本块数据填写，**不取自模型输出**；`text` 为该块原文或其连续子串（截取规则归 J06） |
| `related_kp_ids` | 被引用文本块经 `EVIDENCE` 边关联的知识点 ∪ J02 图检索命中的知识点，去重，全部属于绑定版本 |
| `graph_version`、`request_id` | 绑定版本号与请求 ID（B13 新增） |
| `latency_ms` | 收到请求到构造终态的毫秒数 |

**`not_covered`**：

| 字段 | 取值 |
| --- | --- |
| `reason` | 见 [Q5](#q5-终态矩阵) 的 O1、O2、O3、O5 |
| `answer` | 服务端按 `reason` 套用的**固定模板**，绝不含模型输出，不含任何结论性内容。模板文案由 J06 定稿，下列为示意：`no_retrieval_hit`「课程资料中没有找到与这个问题相关的内容。」；`below_similarity_threshold`「课程资料中与这个问题相关的内容不够充分，无法给出有出处的回答。」；`insufficient_evidence`「检索到的课程资料不足以回答这个问题。」；`all_citations_invalidated`「生成的回答无法与课程资料对应，已撤回。可以换一种问法或缩小问题范围。」 |
| `citations` | 空数组 |
| `related_kp_ids` | 可为空；也可给图检索命中的知识点作导航提示（全部属于绑定版本），不构成结论 |
| `graph_version`、`request_id`、`latency_ms` | 同上 |

**`all_citations_invalidated` 的三个子类**只进日志、不上 wire：`no_markers`（模型完全没写类标记）、`unknown_only`（写了，但无一有效）与 `uncited_sentence`（有有效标记，但有结论单元没有，Q3.5；ADR-015 修订 1）。wire 上三者同为 `all_citations_invalidated`，语义为「生成的回答未能通过引用校验」。

**`NotCoveredReason` 改名（ADR-015 决定 3，B13 落实）**：`740adb` 真源中的 `out_of_course_scope` 没有任何环节负责判定，改为 `insufficient_evidence`，语义为「生成模型以哨兵声明已检索证据不足」。改后闭集为 `no_retrieval_hit`、`below_similarity_threshold`、`insufficient_evidence`、`all_citations_invalidated`，前两者不调用生成，后两者调用了生成。

### Q5 终态矩阵

「生成调用」指答案生成用途的 `model_calls` 条数（按 `request_id` 统计，问题改写与向量调用不计）。「撤回」列指客户端是否须清除已显示的临时正文。

| # | 情形 | 事件序列 | 终态 | 生成调用 | 撤回 |
| --- | --- | --- | --- | --- | --- |
| O1 | H 为空 | meta(not_covered) → done | `not_covered` / `no_retrieval_hit` | 0 | 无正文 |
| O2 | H 非空，无候选达到阈值 | meta(not_covered) → done | `not_covered` / `below_similarity_threshold` | 0 | 无正文 |
| O3 | 模型输出以哨兵开头 | meta(answered) → done | `not_covered` / `insufficient_evidence` | ≥ 1 | 无正文 |
| O4 | 正常结束，每个结论单元都有有效标记（Q3.5） | meta → delta* → done | `answered` | ≥ 1 | 否，标记变为可点击 |
| O5 | 正常结束，零有效标记（`no_markers` 或 `unknown_only`），或有结论单元缺少有效标记（`uncited_sentence`） | meta → delta* → done | `not_covered` / `all_citations_invalidated` | ≥ 1 | **是** |
| O6 | 达到输出上限（`finish_reason = length`） | 同 O4 或 O5 | 按 O4 / O5 判定，被截断的末尾单元无有效标记即为 `uncited_sentence`；日志标 `truncated` | ≥ 1 | 同 O4 / O5 |
| O7 | 首字前主用失败或首字超时，已切备用且备用也失败（或主用熔断且无可用备用） | meta → error | `LLM_UNAVAILABLE`，`details.reason = upstream` | ≥ 0 | 无正文 |
| O8 | 已下发 delta 后供应商流中断（A07：不切备用） | meta → delta+ → error | `LLM_UNAVAILABLE`，`details.reason = stream_interrupted` | ≥ 1 | **是** |
| O9 | 链路时限到期（无论是否已出字） | meta → delta* → error | `LLM_UNAVAILABLE`，`details.reason = timeout`；已生成部分**不**校验成 `answered` | ≥ 0 | **是**（若已出字） |
| O10 | 供应商鉴权失败（A07：不切备用） | meta → error | `LLM_UNAVAILABLE`，`details.reason = auth` | 1 | 无正文 |
| O11 | 生成调用被预算拒绝（A07：不返回 `not_covered`） | meta → error | `BUDGET_EXCEEDED`（A07 提议码，待 D-02f / B08） | 0 | 无正文 |
| O12 | 生成调用的 `model_calls` 预写失败（不发请求） | meta → error | `STORAGE_UNAVAILABLE`（A03 提议码，待 B08） | 0 | 无正文 |
| O13 | 未预期的服务端异常，含供应商参数错误（400 / 404 / 422，A07：不重试、不切备用） | meta → delta* → error | `INTERNAL_ERROR`（A03 提议码，待 B08） | ≥ 0 | **是**（若已出字） |
| O14 | 客户端断开或用户点「停止」 | 服务端不再发事件 | 日志 `aborted` | ≥ 0 | **是**，显示「已停止」 |
| O15 | 流未以 `done` / `error` 结束（异常 EOF）、事件 JSON 无法解析、事件不符合 Q2 文法 | — | 客户端本地合成 `stream_interrupted` 错误 | — | **是** |

- **`details.reason` 闭集**：问答场景下 `LLM_UNAVAILABLE` 的 `details.reason ∈ {upstream, stream_interrupted, timeout, auth}`；`timeout` 当且仅当链路时限到期，其余首字前失败（含两路首字超时）一律 `upstream`。J05 验收「超时为独立错误」据此以字段区分，不新增错误码。
- **`error.message`** 是面向用户的固定文案，不含模型输出、堆栈、密钥或原文。
- **供应商 429**：按 A07 矩阵首字前切备用，最终失败记 `upstream`；`RATE_LIMITED` 只表示本服务限流（P1）。

### Q6 撤回规则（客户端）

适用于 J08（流客户端）与 J09（问答页）。

1. **临时正文**：从首个 `delta` 起以「生成中」样式显示；其中的标记只作普通文本，不可点击（引用详情只在 `done` 中）；不写入对话历史。
2. **唯一保留正文的结局是 `done` 且 `final.status = answered`**：以 `final.answer` 为准显示（按 I1 与临时正文相同，只是标记变为可点击）。若两者不一致，显示 `final.answer` 并上报异常。
3. **其余一切结局整段清除临时正文**，不保留部分答案，也不折叠保留，替换为：`not_covered` → `final.answer`（服务端模板）；`error` → 按 `error.code` 与 `details.reason` 的前端文案；O14 → 「已停止」；O15 → 连接中断文案。
4. **不自动重试**，也不自动重放提问。用户点「重试」即新请求：新 `request_id`，重新绑定版本。
5. **同一对话同时最多一个在途请求**：发送新问题前先中止在途请求（按 O14 处理）。
6. **SSE 模式开流前的错误**以非 200 状态与 `Error` JSON 返回；J08 先检查状态码与 `Content-Type`，再读取事件流。

### Q7 JSON 模式

`Accept: application/json` 时走同一条流水线，只是不发 delta：

| 结局 | 响应 |
| --- | --- |
| P1～P5 的失败 | 同 Q2 表中的 HTTP 错误 |
| O1～O6 | 200 `ChatResponse`，与 SSE 模式同一输入下的 `done.final` 相同（`latency_ms`、`request_id` 除外） |
| O7～O10 | 503 `LLM_UNAVAILABLE`，`details.reason` 同 Q5 |
| O11 | `BUDGET_EXCEEDED`，HTTP 状态由 B08 定（D-02f） |
| O12 | 503 `STORAGE_UNAVAILABLE` |
| O13 | 500 `INTERNAL_ERROR` |
| O14 | 服务端停止生成，不再写响应 |

P2 之后发生的错误在 `Error.details.request_id` 中带回请求 ID（B13）。

### Q8 多轮历史

`ChatRequest.history` 仍由客户端提交，服务端不保存会话，并把它视为不可信输入。

- **H1 客户端组成**：只放结局为 `answered` 或 `not_covered` 的回合（学生提问 + `final.answer`）；临时正文、被撤回的、`error`、`aborted` 的回合连同其提问一律不放。
- **H2 仅用于改写**：历史只作为 J03 问题改写的输入；改写前剔除助手回合中的全部类标记与哨兵；只接受 `user`、`assistant` 两种角色（`ChatTurn.role` 已是闭集）；保留轮数待细化。
- **H3 生成不见历史**：生成提示只含改写后的问题（改写失败时为原问题）、A 中的编号文本块与无编号图谱上下文。因此每个引用都来自本请求的 A，伪造的历史引用不能成为有效引用。
- **H4 `kp_id`**（从知识点详情「问助教」进入时带入）只用于引导检索，本身不是证据；不在绑定版本中（含他课 ID）时忽略并记日志，不报错。

### Q9 跨版本

- **钉住版本**：每个回答属于它的绑定版本，`meta` 与 `final` 都带 `graph_version`。请求途中发布或回滚不影响本请求（ADR-012 V8）。
- **不追溯撤回**：重新发布或回滚不改动已给出回答的引用。文本块不可变，被任一 `committed` 版本引用的修订的块不会被删除，MVP 也不回收已提交版本（ADR-012 V2、V8），因此旧回答的引用点开仍是原来的原文与定位。
- **界面标注**：同一会话中，后面回答的 `graph_version` 与前面某个回答不同时，前面的回答标注「基于第 N 版」；其 `related_kp_ids` 在当前版本已不存在时，点击提示「当前版本已无此知识点」，不跳转。
- **新提问自动绑定新版本**；旧版本回合仍可作为改写用的历史（H2），因为它只是文字。切换课程时清空对话（J09）。
- 日志记录 `version_id`；将来若增加历史读取接口，同样按原版本展示，不重新解析引用。

### Q10 日志

**每个通过 P2 的请求**（已认证、已授权、已绑定版本）恰好一条问答日志（J10）。实体名 `ChatLog`、SQLite 表名 `chat_logs`（A10 N5 交 A09 定名，ADR-015 决定 8）；服务端不保存会话，因此不设 `QuestionSession`。P1 拒绝与 P2 失败的请求没有 `request_id`，也可能没有已认证身份或绑定版本，因此**不写 `chat_logs`**：由统一错误处理写一条结构化应用日志（HTTP 状态、错误码、路径中的课程 ID、已认证时的 `user_id`），不伪造缺失字段（ADR-015 修订 1，Codex A09-R02）。开流前在 P3～P4 失败的请求已通过 P2，照常写 `chat_logs`，结局为 `error`。结局取闭集 `answered`、`not_covered`、`error`、`aborted` 之一，字段至少包括：`request_id`、`user_id`（取自调用者身份，ADR-013）、`course_id`、`version_id`（四者均非空）、原问题、结局与 `reason` / `error.code` / `details.reason`、`citations` 的编号与文本块 ID、「未知引用」计数、`all_citations_invalidated` 的子类与未覆盖单元数、`truncated`、`latency_ms` 与首个 delta 的时延。模型用量不在日志中重复，按 `request_id` 从 `model_calls` 汇总。被撤回的临时正文不作为回答记录；是否留存模型原始输出供评测，与留存期、脱敏一并归 J10。用户重试是新请求、新日志行。

### Q11 与其他任务的接口

| 对象 | 本协议的要求 | 去向 |
| --- | --- | --- |
| B13 问答契约 | `NotCoveredReason` 把 `out_of_course_scope` 改为 `insufficient_evidence`；`ChatMetaEvent` 增加 `graph_version`、`request_id`；`ChatAnswered`、`ChatNotCovered` 增加 `graph_version`、`request_id`；问答 `LLM_UNAVAILABLE` 的 `details.reason` 闭集；JSON 模式错误的 `details.request_id`；`events.v1.md` §3 的时序、替换与撤回条文改为指向本规格 Q2、Q5、Q6，并补 `error` 后撤回与 O15 | B13 改真源并重新生成；`docs/architecture.md` 的 `NotCoveredReason` 行随同一次提交更新 |
| B08 公共错误码 | 问答使用 `STORAGE_UNAVAILABLE`、`INTERNAL_ERROR`（A03 提议）与 `BUDGET_EXCEEDED`（A07 提议，D-02f）；`errors.v1.md` 中 `RATE_LIMITED` 的「模型 API 限流」措辞与 A07 矩阵不一致，改为仅指本服务限流 | B08 |
| J03 问题改写 | H2：剔除历史中的类标记与哨兵；改写出错、超时、被预算拒绝均用原问题 | J03 |
| J04 上下文 | Q3.1 的 A 与编号；图谱上下文无编号；P5 的 `no_retrieval_hit` / `below_similarity_threshold` 判定；H4 | J04 |
| J05 生成 | 提示要求哨兵（Q3.4）、`[n]` 标记（逐单元标注：每句、每个引导句与列表项都以引用结尾，Q3.5）与代码写在反引号内；生成提示不含历史（H3）；首字前切备用、出字后不切（A07） | J05 |
| J06 引用与终态 | Q3.1 复核、Q3.2 归一化闭集、Q3.3 状态机、Q3.5 逐单元检查、Q4 终态构造与模板；与 J09 共用代码片段夹具 | J06 |
| J07 问答 API | Q2 分段与文法、客户端断开、Q7 JSON 模式、链路时限 | J07 |
| J08 流客户端 | O15 本地合成错误；Q6 第 6 条；不自动重放 | J08 |
| J09 问答页 | Q6 撤回规则、Q9 版本标注；Markdown 渲染关闭缩进代码块 | J09 |
| J10 日志 | Q10 覆盖范围（只记通过 P2 的请求）、结局闭集与字段；表名 `chat_logs`、实体 `ChatLog` | J10 |
| K03 离线评测 | `insufficient_evidence` 与 `all_citations_invalidated` 分别统计，后者按三个子类统计，其中 `uncited_sentence` 的撤回率用于评估逐句覆盖的代价；「编号有效」不等于「支持结论」，语义支持度只在评测中衡量（Q3.5） | K03 |
| A10 导入 | 本文件替换 `740adb` / `209be9` 的桩；N5 定为 `ChatLog` / `chat_logs`（`docs/architecture.md` 核心数据模型已改）；批 1 门禁扫描清单加回本文件；`740adb` `src/contracts/README.md` §5.4 的 `not_covered_reason` 已由 ADR-009 裁定为 `reason` | 导入批次 |

### Q12 验收（QA-n）

独立编号，不占用下方主验收序号。括号内为落地测试的任务。「fake 模型」指按脚本逐块输出文本、并记录被调用次数与收到的提示的测试替身。

- 成功路径
  - **QA-1**（J06、J07）正常回答：A = {1,2,3}，fake 模型输出「栈是后进先出的线性表[1]。入栈操作见[2]。」→ `meta`（`status = answered`、`retrieved = 3`、带 `graph_version` 与 `request_id`）→ 若干 `delta` → `done`：`answered`，`answer` 等于 delta 拼接（I1），`citations` 编号为 [1, 2] 且按首次出现排序，每条的定位字段与 `text` 取自文本块数据、可定位。
  - **QA-2**（J06）部分无效：A = {1,2,3}，输出「栈是后进先出的线性表[1][9]。」→ 任何 `delta` 都不含 `[9]`；`done` 为 `answered`，`citations` 只有 1；日志「未知引用」计数为 1。
  - **QA-3**（J06）归一化：A = {1,2,3}，`[1,3]` → `[1][3]`；`【2】` → `[2]`；`[1，9]` → `[1]`；`[2、2]` → `[2]`。
  - **QA-4**（J07）JSON 模式：同一 fake 输出下，`Accept: application/json` 返回 200 `ChatResponse`，除 `latency_ms`、`request_id` 外与 SSE 模式的 `done.final` 相同。
  - **QA-5**（J09）`done` 为 `answered` 后正文不变，标记变为可点击；点击展示该引用的原文与页码或章节。
- 边界路径
  - **QA-6**（J04、J05、J07）检索零命中 → `meta`（`not_covered`、`retrieved = 0`）→ `done`：`not_covered` / `no_retrieval_hit`；无 `delta`；按 `request_id` 统计的生成调用为 **0**（断言调用次数，不能只断言返回值）。
  - **QA-7**（J04、J05）命中但全部低于阈值（阈值用 fake 值）→ `below_similarity_threshold`，生成调用为 0，`reason` 与 QA-6 不同。
  - **QA-8**（J05、J06）哨兵：fake 输出「\n  <<INSUFFICIENT_EVIDENCE>>资料里没有……」→ 无 `delta`；`done` 为 `not_covered` / `insufficient_evidence`；fake 记录到供应商流在哨兵后被关闭；`answer` 为模板。
  - **QA-9**（J06）哨兵跨块：`<<INSUFF` 与 `ICIENT_EVIDENCE>>` 分两块到达 → 仍按 QA-8 处理，任何 `delta` 都不含哨兵的片段。
  - **QA-10**（J06）哨兵前缀分歧：输出以 `<<INSIGHT>>` 开头 → 按普通文本处理，终态由引用决定。
  - **QA-11**（J06）正文中间出现哨兵 → 被剔除，终态由引用决定。
  - **QA-12**（J06、J09）零有效标记：无任何类标记 → `all_citations_invalidated`，日志子类 `no_markers`；只有 `[7]`、`[8]`（A = {1,2}）→ 同一 `reason`，子类 `unknown_only`；两种情况下前端都清除已显示的临时正文、显示模板。
  - **QA-13**（J06、J09）代码片段：行内代码 `` `a[1]` `` 与围栏代码块中的 `[2]` 原样下发、不成为引用；若它们是仅有的方括号 → `all_citations_invalidated`。同一夹具下前端渲染出的代码范围与服务端判定一致。
  - **QA-14**（J06）标记跨块：`[`、`1`、`]` 分三块到达 → 按一个标记处理；输出以未闭合的 `[12` 结束 → 按普通文本放行。
  - **QA-15**（J06）伪标记：`[0]`、`[01]`、`[1-3]`、`[１]` 被剔除并计入「未知引用」；`[a]`、`[注]` 原样保留。
  - **QA-16**（J06）截断：`finish_reason = length`，已有有效标记且每个结论单元都被覆盖 → `answered`，日志 `truncated = true`；末尾被截断的单元没有标记 → `all_citations_invalidated`，子类 `uncited_sentence`，`truncated = true`；无有效标记 → `all_citations_invalidated`，`truncated = true`。
  - **QA-17**（J04、J06）A 的条件：不可定位、他课、或 `revision_id` 不在绑定版本修订列表内的文本块不获得编号；人为注入这样的块时，J06 复核将其剔除并记完整性异常。
  - **QA-18**（J07、G07）请求途中发布新版本 → 本请求 `meta` 与 `final` 的 `graph_version` 仍为旧版本号，引用全部属于旧版本；下一请求绑定新版本。
  - **QA-19**（J03、J05）伪造历史：`history` 中的助手回合含「……[1]」→ 改写输入中不含类标记；fake 模型收到的生成提示不含任何历史内容；`citations` 只来自本请求的 A。
  - **QA-20**（J09）历史组成：被撤回、`error`、`aborted` 的回合及其提问不进入下一请求的 `history`；`answered` 与 `not_covered` 回合以 `final.answer` 进入。
  - **QA-21**（J04）`kp_id` 不在绑定版本中（含他课 ID）→ 请求照常处理、不返回 4xx，日志记录被忽略的 `kp_id`。
  - **QA-22**（J09）同一会话前后两个回答的 `graph_version` 不同 → 前者标注「基于第 N 版」；点击其引用仍显示原文；其知识点在当前版本已删除时提示「当前版本已无此知识点」。
  - **QA-23**（J08）文法违规：第二条 `meta`、`not_covered` 的 `meta` 之后出现 `delta`、`done` 之后又有事件 → 均按 O15 处理并撤回。
  - **QA-36**（J06、J09）逐句覆盖（Codex A09-R01 回归）：A = {1}，fake 输出「栈是线性表[1]。太阳由奶酪构成。」→ `done` 为 `not_covered` / `all_citations_invalidated`，日志子类 `uncited_sentence`、未覆盖单元数 1；前端清除临时正文、显示模板。输出改为「栈是线性表[1]。栈只能在一端插入和删除[1]。」→ `answered`。
  - **QA-37**（J06）切分边界，A = {1,2}：「栈是线性表。[1]」（标记在句末标点之后，归属前一单元）、「## 栈\n栈是线性表[1]。」（标题行不是结论单元）、「π 约为 3.14[2]。」（`3.14` 不被切开）、「栈是线性表[1]。」之后接一个只含 `push(x)` 的围栏代码块（纯代码单元不是结论单元）均为 `answered`；「栈的操作如下：\n- 入栈[1]\n- 出栈」→ 引导句与第二个列表项没有标记，`uncited_sentence`，未覆盖单元数 2。
- 失败路径
  - **QA-24**（J05、J07）首字前主用失败、备用也失败 → `meta` → `error`：`LLM_UNAVAILABLE`、`details.reason = upstream`；无 `delta`。
  - **QA-25**（J05、J07、J09）已下发 delta 后供应商流中断 → `error`：`stream_interrupted`；此后没有备用调用（`model_calls` 中无出字后的新生成调用）；前端清除临时正文。
  - **QA-26**（J07、J09）fake 时钟使链路时限在已出字后到期 → `error`：`timeout`；已生成部分不成为 `answered`；前端清除。
  - **QA-27**（J05）供应商返回 401 → `error`：`auth`；无备用调用。
  - **QA-28**（J05、E04）生成调用被预算拒绝 → `error`：`BUDGET_EXCEEDED`；没有发出供应商请求；结局不是 `not_covered`。
  - **QA-29**（J05、E04）生成调用的 `model_calls` 预写失败 → `error`：`STORAGE_UNAVAILABLE`；没有发出供应商请求。
  - **QA-30**（J07）客户端在出字后断开 → 服务端在有界时间内停止读取供应商流，不再写事件；日志 `aborted`；此后没有新的生成调用。
  - **QA-31**（J08、J09）异常 EOF、坏 JSON 事件 → 本地合成 `stream_interrupted`，清除临时正文；不发第二次 `POST`。
  - **QA-32**（J07）开流前故障：向量调用不可用 → 两种模式均为 503 `LLM_UNAVAILABLE` 且未开流；图库不可用 → 503 `STORAGE_UNAVAILABLE`。
  - **QA-33**（J06）模板：四个 `reason` 的 `final.answer` 各等于对应模板；fake 模型输出中嵌入唯一标识串，断言它不出现在任何 `not_covered` 的 `answer` 与任何 `error.message` 中。
  - **QA-34**（J10）每个通过 P2 的请求恰好一条 `chat_logs` 行，`request_id`、`user_id`、`course_id`、`version_id` 均非空，结局属于闭集；用户重试产生新的 `request_id` 与新日志行。
  - **QA-35**（C03、J07）访问控制按 `specs/identity-access.md` IAM-12 等条目：教师成员 403 `ROLE_FORBIDDEN`，非成员 403 `COURSE_FORBIDDEN`，从未发布 404 `GRAPH_NOT_PUBLISHED`；均在开流前返回。
  - **QA-38**（J10、C03、J07）日志覆盖范围（Codex A09-R02 回归）：匿名请求 401、非成员 403、教师成员 403、P2 读发布指针时存储不可用 503 → 均不产生 `chat_logs` 行、不生成 `request_id`，只有一条应用日志（HTTP 状态与错误码；已认证时含 `user_id`）；通过 P2 后在 P4 向量调用失败（503 `LLM_UNAVAILABLE`）→ `chat_logs` 恰好一行，结局 `error`，四个必填字段均非空。

A09 原子验收与本节的对应：「answered 必有定位来源」→ QA-1、QA-17、QA-36（每个结论单元都有出处）；「临时正文失败后清除」→ QA-12、QA-25、QA-26、QA-31；「空检索不调用生成」→ QA-6、QA-7；「与未知引用区分」→ QA-6、QA-7 与 QA-12 的 `reason` 及生成调用数互不相同。

## 验收条件

### 成功路径

1. 资料覆盖的问题 → 返回至少一个引用，每个引用可定位到 `{document_id, page 或 section}`。（→ QA-1）
2. 回答中出现的**每个引用编号**都能在本次上下文片段中找到对应项；每个结论单元（句）都至少带一个有效引用，否则降级为 `NOT_COVERED` 并撤回（ADR-015 修订 1）。（→ I2、I3、QA-2、QA-36）
3. 返回「涉及的知识点」列表，每项可定位到**绑定版本**中的实际节点 id。（→ Q4）
4. 输出为 SSE 流式，可增量渲染。（→ Q2、QA-1）

### 边界路径

5. 检索相关度**低于阈值** → 返回 `NOT_COVERED`，且**生成模型未被调用**（测试需断言调用次数为 0，不能只断言返回值）。（→ QA-7）
6. 模型输出了上下文中不存在的引用编号 → 该引用**在流内被剔除、不下发**；**若最终不剩任何有效引用，必须降级为 `NOT_COVERED`**，不得返回无来源的答案，客户端撤回已显示正文。这是硬契约的兜底。（A09 修订措辞；→ QA-2、QA-12）
7. 多轮对话中出现指代（「它」「这个」）→ 问题改写补全后再检索；补全失败时按原问题检索，不得静默丢弃指代。（→ H2）
8. 检索命中但片段总量超出 token 预算 → 按预算截断，且截断后仍满足第 1、2 条。
9. 问题与课程无关但用词相近 → 应走阈值分支返回 `NOT_COVERED`，而不是强行用低相关片段作答。

### 失败路径

10. **提示注入**：上下文片段中含「忽略以上指令」「你现在是…」之类的文本 → 一律当作数据。回答内容不得因此改变行为，不得泄露系统提示，不得跳过引用要求。需有专门用例，注入文本放在**检索到的原文片段**里，而不是学生问题里。
11. 生成模型调用超时或返回错误 → 返回**可机读的错误状态**，不得返回空答案，不得用模型常识兜底；已显示的临时正文被撤回。（A09 补「撤回」；→ Q5 O7～O13、QA-24～QA-27）
12. 未发布课程、越权访问、跨课程 `course_id` → 拒绝并返回明确错误码。（→ QA-35）
13. 上下文组装后为空（检索返回 0 条）→ `NOT_COVERED`，与第 5 条同分支但原因不同，需可区分。（→ QA-6）

## 待细化

以下保留**未签收**标记，签收前实现只用 fake 值与字面量写测试：

- **相关度阈值的具体值与调参方法**：阈值直接决定 `NOT_COVERED` 的误报/漏报比，必须在标注集上调（K01），不能拍脑袋；依赖 D-01 的样例资料。
- **性能是硬门槛还是目标**：S2 写「首字 ≤3 秒、完整回答 ≤10 秒」（目标值），S2 表 6.7 与赛题另给问答 ≤15 秒；`LLM_CHAT_TIMEOUT_SECONDS`、`LLM_CHAT_FIRST_TOKEN_TIMEOUT_SECONDS` 取值待 D-02e。
- **`BUDGET_EXCEEDED` 的码与 HTTP 状态**：D-02f / B08；`STORAGE_UNAVAILABLE`、`INTERNAL_ERROR` 为 A03 提议码，待 B08。
- **多轮对话保留轮数**与历史压缩策略（J03）。
- **检索召回条数、图谱扩展跳数、token 预算分配**（图谱子图与原文片段各占多少，J01 / J02 / J04）。
- **`not_covered` 模板与错误文案的定稿**（J06 / J09，产品审阅）；`Citation.text` 的截取规则（J06）。
- **防注入的实现层次**：仅靠系统提示，还是加输入侧检测。仅靠提示词是否足够需在评测中验证（K03）。
- **日志留存期、脱敏与模型原始输出是否留存**（J10）。
- **教师是否开放问答**：ADR-013 推翻条件 2；放开时本规格 Q2 P1 一行随之修改。

由 A09 给出、ADR-015 已签收，不再列为待细化：引用编号格式（Q3.2）；`NOT_COVERED` 原因分类及是否可区分（Q4、Q5）；SSE 事件时序与撤回（Q2、Q6）。
