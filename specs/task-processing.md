# 功能规格：文档处理任务生命周期与取消协议

- **状态**：DRAFT（本文 §1～§7 的决定已由 ArvinHan 于 2026-09-23 签收，见 ADR-010；§8 所列 A06 范围尚未编写）
- **负责人**：产品/协调 Agent 维护；后端、前端、数据与 AI Agent 共同消费
- **关联任务**：A03（本文）；后续 A06（租约与幂等，补入本文件）；消费方 B10、C08、C10、C11、C12、E12、F13、G04、H02
- **规范地位**：本文是任务状态机的**唯一规范表述**。`740adb` 的 `src/contracts/events.v1.md` §2「规范转换表」随 B10 迁移时改为指向本文，不再各写一份（Codex R05 的成因正是两份表述分头演进）。取值与大小写仍以 `docs/architecture.md`「API 前缀与 wire 枚举」为准。

## 范围

本文确定：状态转换与触发者、「处理完成」与「审核完成」的区分、取消协议与竞争语义、部分失败、失败码、SSE 关流与重连。

本文**不**确定（写明去向，避免被当作已决）：

| 事项 | 去向 |
| --- | --- |
| worker 原子领取、租约、超时接管、阶段重试上限、去重与幂等 | A06（补入本文件 §8） |
| 中间产物（解析结果、抽取缓存）在取消/失败后保留还是清理 | A06 / E 组 |
| SSE 一次性令牌的签发端点与作用域（Codex S07-R07） | B10 / A05 |
| 发布快照、发布指针与跨库补偿 | A04 |
| 失败/取消后「再处理」的入口（重新上传或新增端点） | C06 / C07（本文只规定必须是新任务） |
| 阈值环境变量登记到 `.env.example` 与 `docs/integrations.md` | A07 |

## 术语

- **处理完成**：`stage = awaiting_review`。worker 对该任务的工作全部结束，草稿已整体写入；此后 worker 不再触碰它。它**不是终态**。
- **审核完成**：`stage = completed`，由教师发布触发（§3）。
- **取消请求**：`cancel_requested = true`，一个持久化的**标志位，不是状态**。取消生效前 `stage` 保持当前阶段。
- **取消完成**：`stage = cancelled`，终态。
- **检查点**：worker 读取 `cancel_requested` 并决定是否转 `cancelled` 的位置——阶段边界，以及 `extracting` 内块与块之间。在途的单次模型调用不被打断（ADR-006 第 3 条）。
- **比较并交换**：对同一任务行的条件更新（`UPDATE … WHERE stage = ? AND …`），影响行数为 0 即视为竞争失败。本文所有转换都以此裁决，失败的一方不产生事件。

## 1. 状态属性

| stage | 类别 | 取消请求的结果 | 可转 `failed` | 推送后服务端关流 | 固定 progress |
| --- | --- | --- | --- | --- | --- |
| `queued` | 等待 | 直接转 `cancelled` | 否 | 否 | 0.00 |
| `parsing` | 处理中 | 置标志 | 是 | 否 | — |
| `extracting` | 处理中 | 置标志 | 是 | 否 | — |
| `merging` | 处理中 | 置标志 | 是 | 否 | — |
| `persisting` | 处理中，**不可中断** | 409 | 是 | 否 | — |
| `awaiting_review` | **处理结束，非终态** | 409 | 否 | **是** | 0.95 |
| `completed` | 终态 | 409 | 否 | 是 | 1.00 |
| `failed` | 终态 | 409 | — | 是 | 保持失败时的值 |
| `cancelled` | 终态 | 409 | — | 是 | 保持取消时的值 |

「—」表示按 `events.v1.md`「阶段与进度映射」在区间内插值，本文不重复该区间表。

## 2. 转换表

| # | 起点 → 终点 | 触发者 | 守卫（比较并交换条件） |
| --- | --- | --- | --- |
| T1 | ∅ → `queued` | API 上传 | 资料记录与任务记录在同一事务创建；任一失败两者都不存在 |
| T2 | `queued` → `parsing` | worker 领取 | `stage = queued`（领取与租约机制归 A06） |
| T3 | `queued` → `cancelled` | **API 取消** | `stage = queued`；与 T2 竞争，先写成功者赢 |
| T4 | `parsing` → `extracting`，`extracting` → `merging` | worker，阶段边界 | `cancel_requested = false` |
| T5 | `merging` → `persisting` | worker | `cancel_requested = false`。**最后一个取消点** |
| T6 | `persisting` → `awaiting_review` | worker | 草稿整体写入成功（含 ADR-009 成环降级）。**处理完成** |
| T7 | `awaiting_review` → `completed` | **教师发布** | 与发布指针切换同一 SQLite 事务；只推进草稿已含在本次发布快照中的任务。**审核完成** |
| T8 | `parsing` / `extracting` / `merging` → `cancelled` | worker，检查点 | `cancel_requested = true` |
| T9 | `parsing` / `extracting` / `merging` / `persisting` → `failed` | worker | 不可恢复的失败，`error` 必填（§6） |

**禁止的转换**（C08 负例逐条覆盖）：回退或跳级（如 `parsing → merging`）；终态再转任何状态；`awaiting_review → failed`；`awaiting_review → cancelled`；`persisting → cancelled`；`queued → failed`（必须先被领取才可能失败）。

### 迁移事件（C08 纯函数的输入）

C08 实现 `(当前任务状态, 事件) → 新任务状态 | 拒绝`，不做 I/O。事件词表：

| 事件 | 发起方 | 合法前置 stage | 结果 |
| --- | --- | --- | --- |
| `claim` | worker | `queued` | T2 |
| `stage_done` | worker | `parsing` / `extracting` / `merging` | 标志为 false → 下一阶段（T4/T5）；标志为 true → `cancelled`（T8） |
| `checkpoint` | worker | `parsing` / `extracting` / `merging` | 标志为 true → `cancelled`（T8）；否则不变 |
| `progress(p)` | worker | `parsing`～`persisting` | `p ≥ 旧值` → 阶段不变，`progress = p`；`p < 旧值` → 拒绝（A06 重试或接管后的低值上报因此不生效） |
| `persisted` | worker | `persisting` | T6 |
| `fail(error)` | worker | `parsing`～`persisting` | T9；`error` 为空则拒绝 |
| `cancel_request` | API | 任意 | 按 §4 矩阵：T3、置标志、幂等或拒绝 |
| `published` | API 发布 | `awaiting_review` | T7 |

对不合法前置 stage 的任何事件都拒绝且状态不变；拒绝是返回值，不是异常吞掉。

### 不变量

- **I1** `stage` 只沿转换表前进；同阶段内的进度更新不是转换。A06 的同阶段重试不改变 `stage`。
- **I2** 持久化的 `progress` 单调不减，跨重试、跨 worker 接管、跨 SSE 连接都成立；低于当前值的上报被拒绝，而不是写入后再修正。
- **I3** 终态不可变：进入终态后 `stage`、`progress`、`error`、`cancel_requested` 不再改变。「再处理」一律新建任务、分配新 `task_id`，不复活旧任务。
- **I4** `stage = failed` ⇔ `error` 非空（修复 Codex S07-R09）。
- **I5** `cancel_requested` 只能由 false 变 true，不回落；只在 `queued`（随 T3 一并置位）与 `parsing`/`extracting`/`merging` 被置位。因此 `stage = cancelled` ⇒ `cancel_requested = true`。
- **I6** 草稿图谱只在 `persisting` 被写入；`failed` 或 `cancelled` 的任务不得在草稿中留下教师可见的节点或边（ADR-006 第 5 条）。取消只发生在 T5 之前，因此由取消引起的残留不可能出现；`persisting` 失败的清理机制归 F13/A06。
- **I7** 所有读写按 `course_id` 隔离；跨课程的取消、查询与订阅按 A05 访问矩阵拒绝，且不返回任务快照。

## 3. 处理完成与审核完成

- worker 的职责在 T6 结束。`awaiting_review` 不可取消、不会失败；教师若要丢弃某份资料带来的内容，走审核中的驳回或删除，而不是取消任务。
- **发布推进哪些任务（T7）**：发布成功时，在切换发布指针的同一 SQLite 事务内，把该课程中「`stage = awaiting_review` 且草稿在发布快照生成前已提交」的全部任务转为 `completed`。
  - 发布时仍在处理中的任务不受影响；它们之后到达 `awaiting_review`，等下一次发布。
  - 某任务带来的内容在审核中被全部驳回，发布时仍转 `completed`——审核完成不等于内容被采纳。
  - 发布失败（含 409 `PUBLISH_BLOCKED`）不改变任何任务状态。
  - 版本回滚不改变任务状态。
  - 课程没有 `awaiting_review` 任务时照样可以发布（例如只有人工编辑）。
- **一致性前提**：同一课程的 `persisting` 提交与发布快照必须串行，保证一个任务的草稿要么整体在快照内、要么整体不在。串行化机制归 A04/A06。

## 4. 取消协议

端点 `POST /api/v1/tasks/{tid}/cancel`，仅该课程教师可调用。**所有受理结果都是 HTTP 200**，响应体是 `Task` 快照，必须含真实 `stage` 与 `cancel_requested`（修复 Codex S07-R08）。不用 202：客户端靠响应体区分「已取消」与「取消中」，不靠状态码。

| 调用时 stage | 处理 | 响应 | SSE |
| --- | --- | --- | --- |
| `queued` | T3，同时置 `cancel_requested = true` | 200，`stage: cancelled` | 推 `cancelled`，关流 |
| `parsing` / `extracting` / `merging`，标志为 false | 置 `cancel_requested = true` | 200，当前 `stage`，`cancel_requested: true` | 推同阶段 `stage` 事件，`cancel_requested: true` |
| 同上，标志已为 true（**重复取消**） | 幂等，不写任何数据 | 200，同上 | 不推新事件 |
| `persisting` | 拒绝 | 409 `TASK_NOT_CANCELLABLE`，`details: {stage: "persisting", reason: "persisting_uninterruptible"}` | 无 |
| `awaiting_review` | 拒绝 | 409，`details: {stage: "awaiting_review", reason: "processing_finished"}` | 无 |
| `completed` / `failed` / `cancelled` | 拒绝（ADR-006 第 4 条：不得静默成功） | 409，`details: {stage: <实际终态>, reason: "already_terminal"}` | 无 |

`details.reason` 取值为 lower_snake（ADR-009 大小写规则）。

**竞争裁决**：取消端点置标志用条件 `stage IN (parsing, extracting, merging)`；worker 的 T5 用条件 `stage = merging AND cancel_requested = false`。二者作用于同一行，SQLite 串行化它们，结果确定：

| 竞争 | 先写成功者 | 结果 |
| --- | --- | --- |
| 取消 vs 领取（`queued`） | 取消 | 任务 `cancelled`；worker 的 T2 影响 0 行，放弃该任务 |
| 同上 | 领取 | 取消端点看到 `parsing`，走置标志分支，200 + `cancel_requested: true` |
| 取消 vs 进入 `persisting` | 取消 | worker 的 T5 影响 0 行，转 `cancelled` |
| 同上 | worker | 取消端点看到 `persisting`，409；任务继续到 `awaiting_review` |
| 标志已置，但到检查点前 worker 失败 | worker 失败 | 任务 `failed`，`cancel_requested` 保持 true；只推一次 `error`（「先到达终态者为准」，ADR-006 第 4 条） |

**生效时延**：上限约为「单块抽取调用超时（A07 配置）+ 一个检查点间隔」。在途模型调用完成后其结果丢弃或进缓存（归 A06/E 组），调用已产生的费用照常计入预算。

**前端呈现**：`cancel_requested = true` 且非终态 → 「取消中」；`stage = cancelled` → 「已取消」；收到 409 时以 `details.stage` 刷新界面，不假装取消成功（H02）。

## 5. 部分失败

只有 `extracting` 允许部分失败。`parsing`、`merging` 与 `persisting` 是全有或全无：出错即 T9。

**判定规则**：

- 阈值 `TASK_MAX_FAILED_CHUNK_RATIO`，来自环境变量，默认 `0.2`，取值 `[0, 1)`。`0` 即严格模式，任一块失败整任务失败；上限不含 1，因此全部块失败必然 `failed`。
- 一块在 A06 规定的重试耗尽后仍失败，才计为失败块。
- 全部块结束后判定：`chunks_failed / chunks_total ≤ 阈值`（含等号）→ 继续到 `merging`；否则 T9。
- **允许提前判定**：失败块数一旦超过 `floor(阈值 × chunks_total)`，结论已确定，可立即 T9 以节省预算；结果必须与跑完全部块时相同。
- `chunks_total = 0`（解析后没有可用块）在 `parsing` 就失败（§6），不进入本规则。

**计数**：`chunks_done` 统计已结束的块（成功与最终失败都算），`chunks_failed ⊆ chunks_done`。因此有失败块时进度仍能走到本段终点。

**呈现**：阈值内继续时，任务照常到 `awaiting_review`；`Task.failed_chunks` 列出每个失败块的定位与最终错误码，审核页提示「N 块未抽取」并可跳到原文位置。部分失败**不阻塞发布**，由发布前体检列出（F11/G 组）。ADR-009 的成环降级不是失败，不计入 `chunks_failed`。

## 6. 失败码

`failed` 是任务的领域状态，不是 HTTP 错误；`GET /api/v1/tasks/{tid}` 与 SSE 仍为 200。

| 失败情形 | 阶段 | `error.code` | `details` | 契约现状 |
| --- | --- | --- | --- | --- |
| 文件损坏 / 加密 / 无可提取文本（含 `chunks_total = 0`） | `parsing` | `DOCUMENT_UNREADABLE` | `reason ∈ {corrupted, encrypted, no_text}` | **提议新增** |
| 抽取失败块超阈值，且所有失败块的最终错误都是模型不可用 | `extracting` | `LLM_UNAVAILABLE` | `chunks_failed`、`chunks_total`、`threshold` | 已有 |
| 抽取失败块超阈值，其他或混合原因 | `extracting` | `EXTRACTION_INCOMPLETE` | 同上，另含按错误码的计数 | **提议新增** |
| 自动候选成环且环上无可降级边 | `persisting` | `CYCLE_DETECTED` | `cycle` | 已有（ADR-009） |
| 图库 / 数据库不可用或写入失败 | `persisting`（及任何需读写存储处） | `STORAGE_UNAVAILABLE` | — | **提议新增** |
| 其他未预期错误（含 `merging`） | 任意处理中阶段 | `INTERNAL_ERROR` | 不含堆栈、密钥或原文 | **提议新增** |
| 租约接管或阶段重试耗尽 | 任意处理中阶段 | 由 A06 定 | — | 预留 |

四个新码是提议：由 B08 写入 `api.v1.yaml` 的 `ErrorCode` 并重新生成后，`docs/architecture.md` 的 `ErrorCode` 行随同一次提交更新。在此之前该行不改，以免与真源逐值核对失败。

## 7. SSE 推送、关流与重连

端点 `GET /api/v1/tasks/{tid}/events`。事件名不变：`stage`、`done`、`error`、`cancelled`（ADR-009 表）。

| 时机 | 推送 | 之后 |
| --- | --- | --- |
| 建立连接 | 立即补发当前快照：非终态为 `stage`，终态为对应终态事件 | 视快照所处状态按下面各行处理 |
| 进入新阶段；阶段内进度变化；`cancel_requested` 由 false 变 true | `stage` | 保持连接 |
| **进入 `awaiting_review`**，或建连时已处于该状态 | `stage`（`progress = 0.95`） | **服务端关流** |
| 进入 `completed` / `failed` / `cancelled` | `done` / `error` / `cancelled`，互斥且恰好一次 | 服务端关流 |

- 客户端收到 `stage = awaiting_review` 或任何终态事件后必须主动 `close()`。其后状态（是否已 `completed`）通过 `GET /api/v1/tasks/{tid}` 或课程发布状态获得，不挂着 SSE 等。
- 由于处理流在 `awaiting_review` 已结束，`done` 实际只出现在「发布之后才建立的连接」的首条补发中。
- 心跳：每 15 秒一行 `:ping`。
- 多订阅者：同一任务允许多个连接，各自先收快照，此后事件广播给全部连接。
- worker 崩溃：任务停在原阶段，连接照常心跳，不产生新状态；接管归 A06。

**重连**：

- **不依赖 `EventSource` 自动重连。** SSE 令牌一次性且有效期 ≤60 秒，自动重连会携带同一 URL 与旧令牌，必然失败；浏览器对非 200 响应不再重试，连接就此静默中断。
- 重连由 `src/frontend/src/api/` 封装负责：出错即 `close()` → 重新申领令牌 → 新建连接。建议默认值（C12 可调，非契约）：退避 1、2、4… 秒，上限 30 秒；连续失败 5 次降级为每 5 秒轮询 `GET /api/v1/tasks/{tid}`。
- 不使用 `Last-Event-ID`：每次连接先补快照即可恢复，I1/I2 保证跨连接不回退。
- 客户端丢弃 `task_id` 不等于当前订阅任务的事件（切换资料/课程时旧流的迟到事件不得污染当前视图）。

**与现行 `events.v1.md` 的差异**（`740adb`，B10 迁移时改）：§2 顺序保证第 4、5 条「只有终态事件后关流」→ 增加 `awaiting_review` 关流；§4「`EventSource` 自动重连」→ 改为上面的客户端管理重连。该文件 §6 规定终态语义变更须升 v2，但 v1 尚未进入 main、没有任何消费者，此时修改迁移成本为零（与 ADR-005「枚举一次定稿」的理由相同）。

## 8. 租约、重试与幂等（A06 待补）

本节由 A06 填写：原子领取、租约与续约、超时接管、阶段重试上限、重跑去重、单机/多进程边界、中间产物保留。A06 不得改变 §1～§7 的转换表与不变量；若必须改变，先修订 ADR-010。

## 验收矩阵

独立编号 TASK-n，不占用其他规格的序号。「实现方」指负责让该条变成自动化测试的原子任务。

- 成功路径
  - **TASK-1**（C08、C11、F13）完整处理：任务依次经过 `queued → parsing → extracting → merging → persisting → awaiting_review`；SSE 按序推 `stage`，`progress` 单调不减；推送 `awaiting_review` 后服务端关流。
  - **TASK-2**（G04）发布推进：课程有任务 A（`awaiting_review`）与 B（`extracting`），发布成功 → A 为 `completed`，B 不变；B 之后到达 `awaiting_review`，直到下一次发布前保持不变。
  - **TASK-3**（C10、C11）`queued` 取消：200 且 `stage = cancelled`、`cancel_requested = true`；worker 此后不会领取；SSE 推 `cancelled` 后关流。
  - **TASK-4**（C10、E12）运行中取消：`extracting` 中取消 → 200，`stage = extracting`、`cancel_requested = true`；SSE 推一条同阶段 `stage` 事件；下一个块边界后转 `cancelled`；草稿中没有该任务的任何节点或边。
- 边界路径
  - **TASK-5**（C10）重复取消：取消中再次取消 → 200，快照相同，不推新事件；已 `cancelled` 后再取消 → 409，`details.reason = already_terminal`、`details.stage = cancelled`。
  - **TASK-6**（C10、F13）取消 vs 进入 `persisting`：标志先写 → `cancelled`；worker 先进入 → 取消得 409 `persisting_uninterruptible`，任务到 `awaiting_review`。两种顺序各一条测试。
  - **TASK-7**（C08、C10）取消 vs 失败：标志已置、检查点前 worker 失败 → `failed`，`cancel_requested` 仍为 true，SSE 只推一次 `error`。
  - **TASK-8**（C09、C10）取消 vs 领取：两个连接并发，恰好一方成功；领取赢时取消走置标志分支，取消赢时 worker 放弃该任务。
  - **TASK-9**（E12）阈值内部分失败：10 块失败 2 块、阈值 0.2 → `awaiting_review`；`chunks_done = 10`、`chunks_failed = 2`；`failed_chunks` 两项均带定位与错误码。
  - **TASK-10**（E12）阈值边界：失败比例恰等于阈值 → 继续；阈值为 0 时 1 块失败 → `failed`；提前判定与跑完全部块的结论一致。
  - **TASK-11**（C11、C12）重连：断线后客户端重新申领令牌建连，首条为当前快照且 `progress` 不小于断线前；对已处于 `awaiting_review` 的任务建连 → 收到快照后被关流；对终态任务建连 → 收到终态事件后被关流；旧任务的迟到事件被丢弃。
  - **TASK-12**（C10）`awaiting_review` 取消 → 409 `processing_finished`；任务与草稿均不变。
- 失败路径
  - **TASK-13**（E12）超阈值：10 块失败 3 块、阈值 0.2 → `failed`，`EXTRACTION_INCOMPLETE`，`details` 含计数与阈值；若失败块最终错误全为模型不可用 → `LLM_UNAVAILABLE`。
  - **TASK-14**（D 组、C08）解析失败：加密 PDF → `failed`，`DOCUMENT_UNREADABLE`、`reason = encrypted`；解析后 0 块 → `reason = no_text`；二者都不进入 `extracting`。
  - **TASK-15**（F13）入库失败：图库不可用 → `failed`，`STORAGE_UNAVAILABLE`；草稿中没有该任务任何可见的节点或边。
  - **TASK-16**（C08）非法转换：终态再写、回退、跳级、`awaiting_review → failed`、`awaiting_review → cancelled`、`persisting → cancelled`、`queued → failed`、`progress` 倒退，均被拒绝且状态不变。
  - **TASK-17**（B10）契约拒绝：`stage = failed` 而 `error` 缺失或为 null 的 `Task` / `TaskEvent` 被结构校验拒绝；非 `failed` 却带非 null `error` 同样拒绝。
  - **TASK-18**（G04）发布失败（含 `PUBLISH_BLOCKED`）→ 所有 `awaiting_review` 任务保持不变。
  - **TASK-19**（C10、C11）跨课程：其他课程的教师取消、查询或订阅本课程任务 → 按 A05 拒绝，响应中不含任务快照。

## 交给后续任务的契约缺口

以下均须先改 `api.v1.yaml` 真源再重新生成（ADR-004），本文不代改：

| 缺口 | 负责 |
| --- | --- |
| `Task` 增加 `cancel_requested`（当前只在 `TaskEvent` 上） | B10 |
| 取消端点 200 描述「已转入 cancelled」改为「请求已受理，以响应体 `stage` 与 `cancel_requested` 为准」；409 描述写明三种 `reason` | B10 |
| `TaskCounts` 增加 `chunks_failed` | B10 |
| `Task` 增加 `failed_chunks: [{chunk_id, page?, section_path?, code}]`；只在快照中返回，SSE 事件只带计数 | B10 |
| `stage = failed` ⇔ `error` 非空（`if/then` 或按状态拆分，Codex S07-R09） | B10 |
| `TaskStage` 描述「任意阶段可转 failed，任意非终态可转 cancelled」改为指向本文 §2 | B10 |
| `ErrorCode` 增加 `DOCUMENT_UNREADABLE`、`EXTRACTION_INCOMPLETE`、`STORAGE_UNAVAILABLE`、`INTERNAL_ERROR` | B08 |
| `events.v1.md` §2 转换表改为指向本文；§2 关流规则与 §4 重连按本文 §7 改写 | B10 |
| SSE 令牌签发端点 | B10 / A05 |
