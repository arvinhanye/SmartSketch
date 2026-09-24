# 功能规格：文档处理任务生命周期与取消协议

- **状态**：DRAFT（§1～§7 的决定已由 ArvinHan 于 2026-09-23 签收，见 ADR-010；§8 由 A06 编写，同日签收，见 ADR-011）
- **负责人**：产品/协调 Agent 维护；后端、前端、数据与 AI Agent 共同消费
- **关联任务**：A03（§1～§7）；A06（§8）；消费方 B10、C01、C08、C09、C10、C11、C12、D10、E04、E12、F13、G04、H02、K08
- **规范地位**：本文是任务状态机的**唯一规范表述**。`740adb` 的 `src/contracts/events.v1.md` §2「规范转换表」随 B10 迁移时改为指向本文，不再各写一份（Codex R05 的成因正是两份表述分头演进）。取值与大小写仍以 `docs/architecture.md`「API 前缀与 wire 枚举」为准。

## 范围

本文确定：状态转换与触发者、「处理完成」与「审核完成」的区分、取消协议与竞争语义、部分失败、失败码、SSE 关流与重连。

本文**不**确定（写明去向，避免被当作已决）：

| 事项 | 去向 |
| --- | --- |
| SSE 一次性令牌的签发端点与作用域（Codex S07-R07） | B10 / A05 |
| 发布快照、发布指针与跨库补偿（串行化所用的课程写锁由 §8.5 提供，发布方何时持锁归 A04） | A04 |
| 失败/取消后「再处理」的入口（重新上传或新增端点） | C06 / C07（本文只规定必须是新任务） |
| 阈值与 §8.8 的环境变量登记到 `.env.example` 与 `docs/integrations.md` | A07 |
| 模型调用结果缓存的键与失效策略（§8.4 `merging` 依赖它） | E 组 |

原列的「worker 领取、租约、接管、重试上限、去重与幂等」与「中间产物保留」已由 A06 在 §8 确定。

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
| T2 | `queued` → `parsing` | worker 领取 | `stage = queued`（领取与租约见 §8.2） |
| T3 | `queued` → `cancelled` | **API 取消** | `stage = queued`；与 T2 竞争，先写成功者赢 |
| T4 | `parsing` → `extracting`，`extracting` → `merging` | worker，阶段边界 | `cancel_requested = false` |
| T5 | `merging` → `persisting` | worker | `cancel_requested = false`。**最后一个取消点** |
| T6 | `persisting` → `awaiting_review` | worker | 草稿整体写入成功（含 ADR-009 成环降级）。**处理完成** |
| T7 | `awaiting_review` → `completed` | **教师发布** | 与发布指针切换同一 SQLite 事务；推进该课程中 T6 提交序号 ≤ 本次快照**任务水位**的全部 `awaiting_review` 任务，与其内容是否进入快照无关（§3）。**审核完成** |
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
| `progress(p)` | worker | `parsing`～`persisting` | `p ≥ 旧值` → 阶段不变，`progress = p`；`p < 旧值` → 拒绝（§8.2 接管或 §8.3 重排后的低值上报因此不生效） |
| `persisted` | worker | `persisting` | T6 |
| `fail(error)` | worker | `parsing`～`persisting` | T9；`error` 为空则拒绝 |
| `cancel_request` | API | 任意 | 按 §4 矩阵：T3、置标志、幂等或拒绝 |
| `published` | API 发布 | `awaiting_review` | T7 |

对不合法前置 stage 的任何事件都拒绝且状态不变；拒绝是返回值，不是异常吞掉。

### 不变量

- **I1** `stage` 只沿转换表前进；同阶段内的进度更新不是转换。§8 的接管与重排不改变 `stage`。
- **I2** 持久化的 `progress` 单调不减，跨重试、跨 worker 接管、跨 SSE 连接都成立；低于当前值的上报被拒绝，而不是写入后再修正。
- **I3** 终态不可变：进入终态后 `stage`、`progress`、`error`、`cancel_requested` 不再改变。「再处理」一律新建任务、分配新 `task_id`，不复活旧任务。
- **I4** `stage = failed` ⇔ `error` 非空（修复 Codex S07-R09）。
- **I5** `cancel_requested` 只能由 false 变 true，不回落；只在 `queued`（随 T3 一并置位）与 `parsing`/`extracting`/`merging` 被置位。因此 `stage = cancelled` ⇒ `cancel_requested = true`。
- **I6** 草稿图谱只在 `persisting`（及教师编辑）被写入；`failed` 或 `cancelled` 任务的贡献对草稿读取、审核、融合与发布**一律不可见**，由 §8.4「草稿可见性」保证，不依赖清理是否完成（ADR-006 第 5 条；ADR-011 修订 1）。取消只发生在 T5 之前，因此由取消引起的残留不可能出现；`persisting` 失败后的存储回收见 §8.4。
- **I7** 所有读写按 `course_id` 隔离；跨课程的取消、查询与订阅按 A05 访问矩阵拒绝，且不返回任务快照。

## 3. 处理完成与审核完成

- worker 的职责在 T6 结束。`awaiting_review` 不可取消、不会失败；教师若要丢弃某份资料带来的内容，走审核中的驳回或删除，而不是取消任务。
- **任务水位**：每次 T6 在其提交事务内给任务分配一个 **T6 提交序号**，同一课程内严格单调递增（实现可用 SQLite 自增列或课程级计数器，列名由 C06/G04 定，不上 wire）。发布建立快照时，在与 `persisting` 提交串行化的同一区段内读取该课程当前最大的 T6 提交序号，作为本次快照的任务水位，随版本元数据保存。不用时间戳作水位：时钟精度与回拨会让同一时刻提交的任务归属不确定。
- **发布推进哪些任务（T7）**：发布成功时，在切换发布指针的同一 SQLite 事务内，把满足 `course_id = 本课程 AND stage = awaiting_review AND T6 提交序号 ≤ 任务水位` 的全部任务转为 `completed`。谓词只看提交先后，**不看任务内容是否进入快照**。
  - 发布时仍在处理中的任务不受影响；它们之后到达 `awaiting_review`，等下一次发布。
  - 读取水位之后、切换指针之前才完成 T6 的任务，序号大于水位，本次不推进，等下一次发布。
  - 某任务带来的内容在审核中被全部驳回，快照里没有它的任何节点或边，发布时仍转 `completed`——审核完成不等于内容被采纳。
  - 发布失败（含 409 `PUBLISH_BLOCKED`）不改变任何任务状态。
  - 版本回滚不改变任务状态。
  - 课程没有 `awaiting_review` 任务时照样可以发布（例如只有人工编辑）。
- **一致性前提**：同一课程的 `persisting` 提交与「建立快照 + 读取水位」必须串行，保证水位以内任务的草稿整体进入快照输入（之后再经审核取舍），水位以外的整体不在。串行化机制为 §8.5 的课程写锁；发布方何时持锁归 A04。

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

**生效时延**：上限约为「单块抽取调用超时（A07 配置）+ 一个检查点间隔」。在途模型调用完成后其结果不写检查点（§8.4），是否进模型调用缓存归 E 组，调用已产生的费用照常计入预算。

**前端呈现**：`cancel_requested = true` 且非终态 → 「取消中」；`stage = cancelled` → 「已取消」；收到 409 时以 `details.stage` 刷新界面，不假装取消成功（H02）。

## 5. 部分失败

只有 `extracting` 允许部分失败。`parsing`、`merging` 与 `persisting` 是全有或全无：出错即 T9。

**判定规则**：

- 阈值 `TASK_MAX_FAILED_CHUNK_RATIO`，来自环境变量，默认 `0.2`，取值 `[0, 1)`。`0` 即严格模式，任一块失败整任务失败；上限不含 1，因此全部块失败必然 `failed`。
- 一块在 §8.3 L2 的尝试耗尽后仍失败，才计为失败块；E04 熔断器打开期间的失败不计（§8.3）。
- 全部块结束后判定：`chunks_failed / chunks_total ≤ 阈值`（含等号）→ 继续到 `merging`；否则 T9。
- **允许提前判定**：失败块数一旦超过 `floor(阈值 × chunks_total)`，结论已确定，可立即 T9 以节省预算；结果必须与跑完全部块时相同。
- `chunks_total = 0`（解析后没有可用块）在 `parsing` 就失败（§6），不进入本规则。

**计数**：`chunks_done` 统计已结束的块（成功与最终失败都算），`chunks_failed ⊆ chunks_done`。因此有失败块时进度仍能走到本段终点。

**呈现**：阈值内继续时，任务照常到 `awaiting_review`；`Task.failed_chunks` 列出每个失败块的定位与最终错误码，审核页提示「N 块未抽取」并可跳到原文位置。部分失败**不阻塞发布**，由发布前体检列出（F11/G 组）。ADR-009 的成环降级不是失败，不计入 `chunks_failed`。

## 6. 失败码

`failed` 是任务的领域状态，不是 HTTP 错误；`GET /api/v1/tasks/{tid}` 与 SSE 仍为 200。

| 失败情形 | 阶段 | `error.code` | `details` | 契约现状 |
| --- | --- | --- | --- | --- |
| 文件损坏 / 加密 / 无可提取文本（含 `chunks_total = 0`） | `parsing` | `DOCUMENT_UNREADABLE` | `reason ∈ {corrupted, encrypted, no_text}` | **已纳入 B08** |
| 抽取失败块超阈值，且所有失败块的最终错误都是模型不可用 | `extracting` | `LLM_UNAVAILABLE` | `chunks_failed`、`chunks_total`、`threshold` | 已有 |
| 抽取失败块超阈值，其他或混合原因 | `extracting` | `EXTRACTION_INCOMPLETE` | 同上，另含按错误码的计数 | **已纳入 B08** |
| 自动候选成环且环上无可降级边 | `persisting` | `CYCLE_DETECTED` | `cycle` | 已有（ADR-009） |
| 图库 / 数据库不可用或写入失败 | `persisting`（及任何需读写存储处） | `STORAGE_UNAVAILABLE` | — | **已纳入 B08** |
| 其他未预期错误（含 `merging`） | 任意处理中阶段 | `INTERNAL_ERROR` | 不含堆栈、密钥或原文 | **已纳入 B08** |
| 连续租约过期（崩溃、卡死）导致尝试耗尽 | 任意处理中阶段 | `TASK_ATTEMPTS_EXHAUSTED` | `attempts`、`stage` | **已纳入 B08**（A06，§8.3） |
| 阶段级临时故障导致尝试耗尽 | 任意处理中阶段 | 沿用该故障的码（见上两行） | 另加 `attempts`、`stage` | 见 §8.3 |

以上五个新码已由 B08 写入 `api.v1.yaml` 的 `ErrorCode`，并与生成物、`docs/architecture.md` 同步。

## 7. SSE 推送、关流与重连

端点 `GET /api/v1/tasks/{tid}/events`。事件名不变：`stage`、`done`、`error`、`cancelled`（ADR-009 表）。

**覆盖范围**：任务 SSE 只覆盖**处理阶段**，即从建连到任务进入 `awaiting_review` 或 `failed`/`cancelled` 为止。**审核完成（`completed`）不通过已有连接送达**：任务到 `awaiting_review` 时所有连接都已关闭，之后的发布不会向这些连接补发任何事件。

| 时机 | 推送 | 之后 |
| --- | --- | --- |
| 建立连接 | 立即补发当前快照：非终态为 `stage`，终态为对应终态事件 | 视快照所处状态按下面各行处理 |
| 进入新阶段；阶段内进度变化；`cancel_requested` 由 false 变 true | `stage` | 保持连接 |
| **进入 `awaiting_review`**，或建连时已处于该状态 | `stage`（`progress = 0.95`） | **服务端关流** |
| 处理中进入 `failed` / `cancelled` | `error` / `cancelled` | 服务端关流 |
| 建连时任务已处于终态（含 `completed`） | 对应的 `done` / `error` / `cancelled`，作为首条快照 | 服务端关流 |

- **每个连接恰好以一条结束事件收尾**：`stage = awaiting_review` 的快照，或 `done` / `error` / `cancelled` 之一；同一连接内这几种结束事件互斥，发送后即关流。这是按连接的保证，不是按任务生命周期的保证：一个到达 `completed` 的任务，其处理期的连接都以 `awaiting_review` 收尾，永远收不到 `done`。
- 客户端收到任何结束事件后必须主动 `close()`，不得为等待 `done` 保持或重建连接。
- **审核完成的观察方式**：`GET /api/v1/tasks/{tid}`（`stage = completed`）或课程发布状态（`GET /api/v1/courses/{cid}`、`GET /api/v1/courses/{cid}/versions`）。`done` 只会作为「发布之后才建立的连接」的首条快照出现。
- 若产品将来要求实时推送发布结果，须另定课程级发布事件流（新规格 + ADR）；不得为此恢复处理流在 `awaiting_review` 之后的长连接。
- 心跳：每 15 秒一行 `:ping`。
- 多订阅者：同一任务允许多个连接，各自先收快照，此后事件广播给全部连接。
- worker 崩溃：任务停在原阶段，连接照常心跳，不产生新状态；接管见 §8.2。

**重连**：

- **不依赖 `EventSource` 自动重连。** SSE 令牌一次性且有效期 ≤60 秒，自动重连会携带同一 URL 与旧令牌，必然失败；浏览器对非 200 响应不再重试，连接就此静默中断。
- 重连由 `src/frontend/src/api/` 封装负责：出错即 `close()` → 重新申领令牌 → 新建连接。建议默认值（C12 可调，非契约）：退避 1、2、4… 秒，上限 30 秒；连续失败 5 次降级为每 5 秒轮询 `GET /api/v1/tasks/{tid}`。
- 不使用 `Last-Event-ID`：每次连接先补快照即可恢复，I1/I2 保证跨连接不回退。
- 客户端丢弃 `task_id` 不等于当前订阅任务的事件（切换资料/课程时旧流的迟到事件不得污染当前视图）。

**与现行 `events.v1.md` 的差异**（`740adb`，B10 迁移时改）：§2 顺序保证第 4 条「三个终态事件互斥且恰好发生一次」→ 改为按连接的「每个连接恰好以一条结束事件收尾」，并写明 `completed` 不经已有连接送达；第 5 条「只有终态事件后关流」→ 增加 `awaiting_review` 关流；§4「`EventSource` 自动重连」→ 改为上面的客户端管理重连。该文件 §6 规定终态语义变更须升 v2，但 v1 尚未进入 main、没有任何消费者，此时修改迁移成本为零（与 ADR-005「枚举一次定稿」的理由相同）。

## 8. 租约、重试与幂等（A06 / ADR-011）

本节由 A06 编写，决定已由 ArvinHan 于 2026-09-23 签收（ADR-011）。本节**不改变** §1～§7 的转换表与不变量：下文的「回收」与「主动释放」都以 worker 身份执行 T8、T9 或同阶段操作；接管与重排都不改变 `stage`（I1）。

### 8.1 进程与部署边界

- API 与 worker 是**同一台机器上的不同进程**，共用一个 SQLite 文件，开 WAL 模式并设 `busy_timeout`（取值由 C01 定，建议不小于 5 秒）。
- worker 进程数由 `WORKER_PROCESSES` 决定，默认 1；多个 worker 之间的互斥完全由 §8.2 的租约保证。进程内并发处理多个块，上限由 E04/A07 的并发配置决定。
- **支持**：同一台机器上任意数量的 API 进程与 worker 进程。**不支持**：跨机器部署 worker；把 SQLite 文件放在网络文件系统（NFS、SMB 等）上；引入第二个队列（Redis、Celery 等）。任何一项都须先有新 ADR。
- **时间基准**：租约、退避与保留期的比较一律用 SQLite 在语句执行时求值的当前时间（如 `unixepoch()`），不用 worker 传入的时间戳。worker 的本地截止判断（§8.2）用进程内单调时钟。
- API 进程重启不影响处理中的任务。worker 进程崩溃后，其任务在租约到期后被接管；正常退出时先主动释放（§8.3），不必等满租约。

### 8.2 领取、租约、续约与接管

任务行新增以下**内部字段**（只存在 SQLite，不上 wire）：

| 字段 | 含义 |
| --- | --- |
| `lease_owner` | 持有者标识（主机名、进程号、随机串），仅用于排查 |
| `lease_token` | 每次领取重新生成的随机令牌（不少于 128 位），防旧写的唯一依据 |
| `lease_expires_at` | 租约到期时间；NULL 表示无人持有 |
| `attempt` | 已被领取的次数，初值 0 |
| `not_before` | 最早可领取时间，初值为任务创建时间 |
| `cleanup_pending` | `persisting` 失败后的清理尚未完成（§8.4） |

**可领取条件**（记为 *C*）：`attempt < TASK_MAX_ATTEMPTS AND not_before ≤ 现在 AND cancel_requested = false AND (stage = queued OR (stage ∈ {parsing, extracting, merging, persisting} AND (lease_expires_at IS NULL OR lease_expires_at < 现在)))`。

**领取**：一条语句 `UPDATE … WHERE id = (SELECT id … WHERE C ORDER BY created_at, id LIMIT 1) AND C RETURNING …`，写入新的 `lease_owner`、`lease_token`，`lease_expires_at = 现在 + L`，`attempt = attempt + 1`；若 `stage = queued`，同一语句执行 T2。影响 0 行即未领到（被抢先或无任务），不对同一行重试。`L = TASK_LEASE_SECONDS`。

**续约**：持有期间由独立心跳每 `L/3` 执行 `UPDATE … SET lease_expires_at = 现在 + L WHERE id = ? AND lease_token = ?`；影响 0 行即租约已丢。心跳与处理逻辑并发运行，长时间的模型调用不会让租约过期。

**防旧写**：worker 对任务行及其附属表（块检查点、T6 提交序号）的每一次写入，都在同一 SQLite 事务内附带一条 `WHERE id = ? AND lease_token = ?` 的任务行更新；该更新影响 0 行则回滚整个事务，worker 立即停止处理该任务，不再做任何写入（包括 Neo4j）。

**本地截止**：Neo4j 写入无法携带 SQLite 的令牌条件，因此 worker 记录最近一次成功续约的单调时钟时刻 *r*；一旦 `单调现在 − r > L − L/3`，不得发起任何新的外部写入（Neo4j 事务、文件写入），已开启但未提交的 Neo4j 事务回滚。该规则依赖同机时钟，这也是 §8.1 不支持跨机器的原因之一。

**回收**（每个 worker 每次领取前执行，也周期执行）：对 `stage ∈ {parsing, extracting, merging, persisting} AND (lease_expires_at IS NULL OR lease_expires_at < 现在)` 的任务，按顺序：

1. `cancel_requested = true` → T8，由回收者代行检查点，推送 `cancelled`（§4 保证此时 `stage ≠ persisting`）。
2. 否则 `attempt ≥ TASK_MAX_ATTEMPTS` → T9，`error` 按 §8.3 的耗尽码。
3. 否则保持不动，等待被领取（接管）。

另对 `stage = failed AND cleanup_pending = true` 的任务重试 §8.4 的清理。

**接管**：`stage` 不变；新 worker 从 §8.4 的检查点继续；低于当前值的进度上报被拒绝（I2）。

### 8.3 三层重试

| 层 | 范围 | 重试什么 | 上限 | 耗尽后 |
| --- | --- | --- | --- | --- |
| **L1 模型调用** | 单次 HTTP 调用 | 429、5xx、超时，有界退避；鉴权与参数错误不重试 | 由 E04/A07 定 | 本次块级尝试失败 |
| **L2 块** | `extracting` 中的一个块 | L1 耗尽仍失败；输出不合规（坏 JSON 按 E05 修复一次后仍坏、校验不通过） | `TASK_CHUNK_MAX_ATTEMPTS`，默认 2 次尝试，每次含完整 L1 | 记为**失败块**，参与 §5 阈值 |
| **L3 任务尝试** | 整个任务 | 租约过期被接管；阶段级临时故障后主动释放 | `TASK_MAX_ATTEMPTS`，默认 3 次（按领取次数计） | T9 |

**阶段级临时故障**只有两种：存储不可用（Neo4j 或 SQLite 连不上、写入超时），以及模型整体不可用（E04 的熔断器处于打开状态）。熔断器打开时**当前块不记为失败块**，整个阶段退避重排，避免一次模型宕机被算作抽取质量问题、触发 §5 的部分失败阈值。熔断器关闭时单块失败走 L2。

**主动释放**：`UPDATE … SET lease_owner = NULL, lease_token = NULL, lease_expires_at = NULL, not_before = 现在 + 30 秒 × 2^(attempt − 1) WHERE id = ? AND lease_token = ?`，即依次等 30 秒、60 秒。若此刻 `attempt ≥ TASK_MAX_ATTEMPTS`，改为直接 T9。

**正常退出**：worker 收到停止信号时，对手上的任务做主动释放，但 `not_before = 现在` 且 `attempt = attempt − 1`（同一条带令牌条件的语句），不计入尝试次数——部署重启不是故障。

**不重试、直接 T9 的错误**：`DOCUMENT_UNREADABLE`、`EXTRACTION_INCOMPLETE`（块级重试已做过）、`CYCLE_DETECTED`、`INTERNAL_ERROR`。程序缺陷若导致进程崩溃，由 L3 上限止住，不会反复循环。

**耗尽码**（填补 §6「租约接管或重试耗尽」一行）：

| 耗尽方式 | `error.code` | `details` |
| --- | --- | --- |
| 最后一次失败是已知的阶段级临时故障 | 沿用该故障的码：`STORAGE_UNAVAILABLE` 或 `LLM_UNAVAILABLE` | 另加 `attempts`、`stage` |
| 原因不明：连续租约过期（崩溃、卡死） | `TASK_ATTEMPTS_EXHAUSTED`（已纳入 B08） | `attempts`、`stage` |

`attempt` 暂不上 wire：前端只需终态与失败原因。若要在进度中展示「第 N 次尝试」，另交 B10 加字段。

### 8.4 各阶段检查点与幂等

| 阶段 | 接管后 | 幂等依据 |
| --- | --- | --- |
| `parsing` | 从阶段开头重跑 | 来源块 ID 由「资料修订 ID + 块序号」确定性生成（资料修订 = 资料 ID + 内容哈希 + 解析器版本），按 ID 覆盖写入，重跑不产生新块；已存在的 ID 内容哈希不一致即拒绝写入（D10） |
| `extracting` | **块级检查点**：每块结束（成功或最终失败）时写 `(task_id, chunk_id) → 状态 ∈ {done, failed}、尝试次数、候选结果或错误码`，与带令牌条件的任务行更新同事务；接管后跳过已有检查点的块 | 已结束的块不再调用模型；块中途崩溃时该块没有检查点，接管后重新获得完整的 L2 尝试（单块总尝试上限因此为 L2 × L3） |
| `merging` | 从阶段开头重跑 | 重复裁决与定义归并（E10）也调用模型；其结果按「课程 + 候选对 + 提示词版本 + 模型版本」缓存，重跑命中缓存即不再计费。缓存键与失效策略归 E 组 |
| `persisting` | 整段重跑 | 见下 |

> **`parsing` 行已被 ADR-012 修订 1（A04-R01，2026-09-23 签收）修订**：原公式「文档 ID + 解析器版本 + 块序号」不含内容，同一资料换内容再处理会原地覆盖已发布版本引用的原文。现改为按资料修订生成，文本块一经写入不可变。见 `specs/teacher-review-publish.md` V2。

**`persisting`**（落实 I6，F13 实现；ADR-011 修订 1 修订第 1、3、4 条并新增「草稿可见性」）：

1. 取得课程写锁（§8.5），在**一个 Neo4j 事务**内：先撤销本任务此前尝试留下的全部贡献（见下「贡献记录」），再用确定性 ID 以 `MERGE` 写入草稿（含 ADR-009 降级），为每个涉及的节点、关系与来源关联登记本任务的贡献。新节点 ID 由「课程 + 任务 + 候选键」确定；关系 ID 由「课程 + 类型 + 起点 + 终点」确定，两份资料产生的同一条关系合并为一条、各自登记贡献。环检测与降级的对象是「当前可见草稿 + 本任务候选」。
2. Neo4j 提交后，在带令牌条件的 SQLite 事务内执行 T6 并分配 T6 提交序号（§3），然后释放课程写锁。**T6 提交即本任务贡献变为可见的时刻。**
3. 在第 1、2 步之间崩溃：本任务尚不在有效任务集合内，写入的内容对任何读取都不可见；接管者重跑第 1 步（先撤销旧贡献再写），随后补做 T6。
4. `persisting` 以 `failed` 结束（T9）时，本任务的贡献立即不可见；清理只回收存储：在课程写锁下撤销本任务的全部贡献，再删除已无任何贡献（无任务贡献且无人工贡献）的节点与关系。清理失败（如 Neo4j 不可用）时任务照样 T9，并置 `cleanup_pending = true`，由回收步骤重试，成功后清除该标记；这期间正确性不受影响。

**贡献记录**（仅存在于 Neo4j 草稿，不复制到已发布副本）：

- 节点与关系各带 `contrib_tasks`（贡献过它的任务 ID 集合）与 `contrib_manual`（教师任何写入置为 true，不回落）。
- 知识点到文本块的来源关联带 `task_id`，缺省表示人工添加；关系的来源按「(贡献方, 文本块 ID)」成对保存，编码由 F03/F13 定。
- 取代原先「仅在创建时写入」的 `created_by_task`：后者无法表达多个任务复用同一元素（Codex A06-R01）。

**草稿可见性**（Codex A06-R02）：

- **有效任务集合 V** = 本课程 `stage ∈ {awaiting_review, completed}` 的任务，以 SQLite 为准。V 只增不减（`awaiting_review` 不会失败，`completed` 是终态），用稍旧的 V 只会漏看刚提交的内容。
- 节点或关系**可见**，当且仅当 `contrib_manual` 为真，或 `contrib_tasks` 与 V 相交；关系另要求两个端点都可见。来源关联可见，当且仅当它是人工添加的，或其 `task_id ∈ V`。
- 一切草稿读取在开始时读一次 V，由 F02 作为必填参数传入仓储；缺少该参数的草稿查询被拒绝执行。适用于：教师读草稿、审核队列、教师编辑时的环检测、`merging` 的融合候选查找（E10/E11）、`persisting` 第 1 步的环检测、A04 发布的建快照与回滚的草稿摘要（`specs/teacher-review-publish.md` V3）。
- 清理与可见性分离：失败任务的内容从 T9 起就不可见，清理晚于读取也不会暴露它；清理只按贡献撤销，不会删除仍有其他任务或人工贡献的元素。
- **已知限制**：按 ADR-009，任务在第 1 步可能把其他任务的未确认 AI 边降级为 `RELATED_TO`；该任务最终失败时，降级不撤销（降级只朝保守方向，并进入审核）。教师删除一条关系后，另一个尚未提交的任务可能以同一关系 ID 重新写出它，归「节点加锁」的待细化处理。

**计费不重复**（ADR-011 修订 2、修订 3 修订，Codex A07-R01、FIX-R01）：每次**实际**向供应商发出的调用一条 `model_calls` 记录，以发请求前生成的 `call_id` 为身份与去重键；L1 重试、备用调用、E05 修复调用都是新调用、各计一次。发请求前先预写记录（预写失败则不发请求，按阶段级临时故障处理），收到响应后按 `call_id` 回写真实 usage；未收到响应的调用按「输入估算 + 声明的输出上限」计入。收到响应但缺少可解析的 usage 时（修订 3）：生成前被拒的错误（`400/401/403/404/413/422/429`）计 0，其余（成功响应、`408`、`5xx`、流中途断开、响应无法解析）同样按估算计入，不再记 0。同一 `call_id` 的重放写入只计一次。原键「任务 + 块 + 用途 + 尝试序号」区分不了同一块尝试内的多次调用，也无法标识无任务 ID 的问答调用，现只作归属字段。字段与计费量规则见 `docs/integrations.md`「调用记录（`model_calls`）」。

### 8.5 课程写锁

§3 要求同一课程的 `persisting` 提交与「建立快照 + 读取水位」串行，机制如下：

- 表 `course_locks(course_id 主键, holder, token, expires_at)`，与任务租约同构：用 `INSERT … ON CONFLICT(course_id) DO UPDATE … WHERE course_locks.expires_at < 现在 RETURNING …` 获取，心跳每 `L/3` 续约，释放时 `DELETE … WHERE token = ?`，过期即可被他人获取。§8.2 的本地截止规则同样适用于持锁期间的 Neo4j 写入。
- **只有两处持锁**：`persisting` 的「Neo4j 写入 + T6」；发布的「建立快照 + 读取水位」。发布方在何时取锁、持锁多久由 A04 决定。
  > **已被 ADR-012（A04，2026-09-23 签收）修订**：持有方扩大为所有草稿写入（含教师编辑）；发布只在读草稿建快照期间持锁、回滚只在读草稿摘要期间持锁，API 侧有界等待，超时 409 `COURSE_BUSY`。见 `specs/teacher-review-publish.md` V4。
- 等锁时轮询退避，同时照常续约自己的任务租约；等待本身不另设超时，上限由持锁者的租约决定。同一 worker 同一时刻最多持有一把课程写锁，不嵌套，因此不会死锁。
- `merging` **不持锁**（含模型调用，耗时长）。代价：两份资料同时处理时可能产生跨任务的重复节点，它们进入审核队列的「疑似重复」（F11），由教师合并。

### 8.6 中间产物保留

| 产物 | 保留规则 |
| --- | --- |
| 块检查点 | 任务进入终态或 `awaiting_review` 后保留 `TASK_ARTIFACT_RETENTION_DAYS` 天（默认 7），供排查，之后删除 |
| `failed` / `cancelled` 任务的来源块 | 与该任务的检查点同批删除；**但**其修订若属于任何已到 `awaiting_review` / `completed` 的任务，或在任何已提交版本的修订列表中，则保留 |
| 到达 `awaiting_review` 的任务的来源块 | 永久保留：答案引用依赖它们 |
| `model_calls` | 永久保留，用于预算审计 |

> **`failed` / `cancelled` 行已被 ADR-012 修订 1（A04-R01，2026-09-23 签收）修订**：块 ID 按资料修订生成后，处理同一修订的多个任务共享同一批文本块，按任务删除会删掉其他任务或已发布版本依赖的块，故加删除保护。见 `specs/teacher-review-publish.md` V2。

清理由 worker 的回收步骤周期执行（建议每小时一次），按任务与课程隔离，不跨课程批量删除。

### 8.7 迁移的备份与回滚

§8.2～§8.5 的字段与表由 C01、C06、C09、E12、G02 的 SQLite 迁移创建。对这些任务表的**每一次**迁移（含将来的字段变更）遵守：

1. **停机迁移**：存在任何未过期的任务租约或课程写锁时，迁移运行器非 0 退出并提示先停止 worker 与 API；不支持处理中的在线迁移。
2. **迁移前备份**：执行 `VACUUM INTO '<数据目录>/backups/<UTC 时间>-before-<迁移号>.sqlite'`，再对副本执行 `PRAGMA integrity_check`，结果必须为 `ok`，否则中止迁移，原库不变。
3. **单事务迁移**：迁移失败自动回滚，原库不变。
4. **只向前，不写 down 脚本**；回滚 = 停止 API 与 worker → 用备份文件替换数据库文件 → 重启。C01 把这组命令写入运行手册，并在测试中实际执行一次恢复。
5. **恢复之后**：备份时刻处于处理中的任务，其租约均已过期，按 §8.2 正常接管（`attempt + 1`），无需额外处理。
6. Neo4j 图模型的变更不在本规则内，归 A04 / F 组。

### 8.8 配置

| 变量 | 类型与取值 | 默认 |
| --- | --- | --- |
| `WORKER_PROCESSES` | 整数，≥ 1 | 1 |
| `TASK_LEASE_SECONDS` | 整数，≥ 15 | 60 |
| `TASK_MAX_ATTEMPTS` | 整数，≥ 1 | 3 |
| `TASK_CHUNK_MAX_ATTEMPTS` | 整数，≥ 1 | 2 |
| `TASK_ARTIFACT_RETENTION_DAYS` | 整数，≥ 0；0 表示进入终态或 `awaiting_review` 即清理 | 7 |

取值非法时 worker 拒绝启动并指出变量名，不静默回落默认值。登记到 `.env.example` 与 `docs/integrations.md` 归 A07。

### 8.9 验收（LEASE-n）

独立编号 LEASE-n，不占用上方 TASK-n 的序号。

- 成功路径
  - **LEASE-1**（C09）两个连接同时领取同一 `queued` 任务 → 恰好一个成功，`attempt = 1`、`stage = parsing`；另一个影响 0 行。
  - **LEASE-2**（C09、E12）崩溃接管续跑：`extracting` 共 10 块、已完成 6 块时 worker 被杀；租约过期后另一 worker 领取 → `attempt = 2`，`stage` 仍为 `extracting`，只对剩余 4 块调用模型，前 6 块在 `model_calls` 中无新增记录，`progress` 不回退。
  - **LEASE-3**（F13）`persisting` 在 Neo4j 提交后、T6 前崩溃 → 接管重跑，节点与边的数量与一次成功运行相同，任务到 `awaiting_review`。
- 边界路径
  - **LEASE-4**（C09）旧令牌：worker A 的租约过期、被 B 接管后，A 的进度上报、块检查点与 T6 写入均影响 0 行，A 停止；B 的数据不受影响。
  - **LEASE-5**（C09）续约：单次模型调用耗时超过 `L` 时，心跳续约使租约不过期，不发生接管。
  - **LEASE-6**（E12）熔断：`extracting` 中熔断器打开 → 当前块不记失败块，任务主动释放，`not_before = 现在 + 30 秒`；熔断恢复后被领取，从检查点续跑。
  - **LEASE-7**（C09）尝试耗尽：同一任务连续 3 次租约过期 → 回收时 `failed`，`TASK_ATTEMPTS_EXHAUSTED`，`details.attempts = 3`；第 3 次尝试因存储不可用而失败 → `failed`，`STORAGE_UNAVAILABLE`，`details.attempts = 3`。
  - **LEASE-8**（C09、C10）租约过期且已请求取消 → 回收者转 `cancelled` 并推送 `cancelled`，此后不再被领取。
  - **LEASE-9**（C09）正常退出：worker 收到停止信号主动释放，`attempt` 回退；重启后再次领取，`attempt` 与退出前相同。
  - **LEASE-10**（G04、F13）课程写锁：发布持锁建快照期间，`persisting` 等待；发布释放后 `persisting` 获得锁；持锁者崩溃，锁过期后可被他人获取。
  - **LEASE-11**（E12）块尝试：一块连续 2 次输出不合规 → 记为失败块并计入 §5 阈值，不再重试。
  - **LEASE-20**（F02、F13、G04）T6 前不可见：任务 A 的 Neo4j 写入已提交、T6 尚未执行（含其间崩溃）→ 教师读草稿、审核队列与发布快照都不含 A 的内容；接管后完成 T6 → A 的内容可见。
  - **LEASE-21**（F13）重跑撤销旧贡献：A 第一次尝试写入元素 X、Y 后崩溃，第二次尝试只写 X → T6 后 X 可见；Y 若无其他贡献即被删除，不可见。
- 失败路径
  - **LEASE-12**（F13）`persisting` 最终失败的清理：本任务的贡献被撤销，只删除已无任何贡献的节点与边，仍有其他贡献的元素保留；清理时 Neo4j 不可用 → 任务仍 `failed`、`cleanup_pending = true`，Neo4j 恢复后回收步骤完成清理并清除标记。
  - **LEASE-13**（C01）存在未过期租约时执行迁移 → 运行器非 0 退出，原库不变。
  - **LEASE-14**（C01）备份副本 `integrity_check` 不为 `ok` → 迁移中止，原库不变。
  - **LEASE-15**（C01）恢复演练：迁移后按运行手册用备份恢复并重启；备份时刻处理中的任务被接管，`attempt + 1`。
  - **LEASE-16**（C09）配置非法（如 `TASK_MAX_ATTEMPTS=0`、`TASK_LEASE_SECONDS=5`）→ worker 拒绝启动并指出变量名。
  - **LEASE-17**（E04、E12）同一 `call_id` 的 `model_calls` 记录重放写入两次 → 只有一条记录，统计只计一次。
  - **LEASE-24**（E04）主用调用超时、未收到响应，L1 重试成功（Codex A07-R01 回归）→ 两条记录：第一条停在 `sent` 按估算计入，第二条按真实 usage 计入；任务与每日预算都含两者。
  - **LEASE-25**（E04、E05）主用失败、切备用成功，随后对输出做一次 E05 修复 → 三条记录各计一次；每条回写都重放两次，记录数与统计不变。
  - **LEASE-26**（E04、J05）问答调用无任务 ID → 记录带 `request_id`、`task_id` 为空；计入每日预算，不计入任何任务预算。
  - **LEASE-27**（E04）预写后、回写前进程崩溃 → 记录停在 `sent`，按估算计入预算，接管后不补写；预写本身失败 → 请求不发出，worker 按存储不可用主动释放。
  - **LEASE-28**（E03、E04）成功响应不带 usage（Codex FIX-R01 回归）→ 记录回写为 `ok`、usage 为空，按估算（`input_tokens_est + max_output_tokens`）计入任务与每日预算，`usage_estimated` 为真；同一回写重放两次，计费量不变。
  - **LEASE-29**（E03、E04）错误响应不带 usage：`5xx`、`408`、流式首字后断开、响应体无法解析 → 各按估算计入；主用 `5xx` 后切备用成功 → 两条记录，前者按估算、后者按真实 usage。
  - **LEASE-30**（E03、E04）生成前被拒：`429` 不带 usage → 计 0、`usage_estimated` 为假，L1 重试照常且次数有界；`401` 不带 usage → 计 0、不重试；错误响应带 usage（任一状态码）→ 按其 usage 计，不按 0 或估算。
  - **LEASE-18**（F13）复用不被误删（Codex A06-R01 回归）：A 写入关系 r 后在 T6 前崩溃；B 以同一关系 ID 写入 r、登记自己的来源并完成 T6；A 最终失败并清理 → r 与 B 的来源仍在、仍可见；A 的来源关联被删除。
  - **LEASE-19**（F02、F13、G04）清理未完成时不可见（Codex A06-R02 回归）：A 在 T6 时遇存储故障 → T9、`cleanup_pending = true`；Neo4j 恢复后、清理完成前，教师读草稿、审核队列、融合候选与发布快照都不含 A 的任何内容。
  - **LEASE-22**（F08、F13）人工贡献受保护：A 为教师新建的节点 X 添加关系与来源后失败 → 清理删除只由 A 贡献的关系与来源，X 保留。
  - **LEASE-23**（F02）缺少有效任务集合参数的草稿查询 → 仓储层拒绝执行。

## 验收矩阵

独立编号 TASK-n，不占用其他规格的序号。TASK-20～22 为 Codex 审查修复轮（A03-R01/R02）新增，追加在所属类别末尾，已有编号不重排。「实现方」指负责让该条变成自动化测试的原子任务。

- 成功路径
  - **TASK-1**（C08、C11、F13）完整处理：任务依次经过 `queued → parsing → extracting → merging → persisting → awaiting_review`；SSE 按序推 `stage`，`progress` 单调不减；推送 `awaiting_review` 后服务端关流。
  - **TASK-2**（G04）发布推进：课程有任务 A（`awaiting_review`，T6 提交序号 ≤ 任务水位）与 B（`extracting`），发布成功 → A 为 `completed`，B 不变；B 之后到达 `awaiting_review`，其序号大于本次任务水位，直到下一次发布前保持不变。
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
  - **TASK-20**（C11、C12、H02）订阅先于发布：教师在 `extracting` 时订阅；收到 `stage = awaiting_review` 快照后连接被关闭，客户端不重建连接；随后发布 → 该连接不再收到任何事件，前端不等待 `done`；`GET /api/v1/tasks/{tid}` 返回 `stage = completed`；发布后新建的连接首条即 `done` 并被关流。
  - **TASK-21**（G04）全部驳回：任务 A 在 `awaiting_review`，其带来的全部节点与边在审核中被驳回，快照中没有 A 的任何内容；发布成功 → A 仍转 `completed`。
  - **TASK-22**（G04）水位竞争：发布已读取任务水位、尚未切换指针时，任务 C 完成 T6 → C 的序号大于水位，本次发布后 C 仍为 `awaiting_review`，下一次发布才转 `completed`。
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
| `Task` 增加 `cancel_requested`（当前只在 `TaskEvent` 上） | B10 已完成 |
| 取消端点 200 描述「已转入 cancelled」改为「请求已受理，以响应体 `stage` 与 `cancel_requested` 为准」；409 描述写明三种 `reason` | B10 已完成 |
| `TaskCounts` 增加 `chunks_failed` | B10 已完成 |
| `Task` 增加 `failed_chunks: [{chunk_id, page?, section_path?, code}]`；只在快照中返回，SSE 事件只带计数 | B10 已完成 |
| `stage = failed` ⇔ `error` 非空（`if/then` 或按状态拆分，Codex S07-R09） | B10 已完成 |
| `TaskStage` 描述「任意阶段可转 failed，任意非终态可转 cancelled」改为指向本文 §2 | B10 已完成 |
| `ErrorCode` 增加 `DOCUMENT_UNREADABLE`、`EXTRACTION_INCOMPLETE`、`STORAGE_UNAVAILABLE`、`INTERNAL_ERROR`、`TASK_ATTEMPTS_EXHAUSTED`（后者来自 A06 §8.3） | B08 已完成 |
| `events.v1.md` §2 转换表改为指向本文；§2 顺序保证第 4、5 条（结束事件按连接、`awaiting_review` 关流、只覆盖处理阶段）与 §4 重连按本文 §7 改写 | B10 已完成 |
| SSE 令牌签发端点 | B10 已完成（`issueEventTicket`，A05 §5） |
