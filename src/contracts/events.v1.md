# SSE 事件契约 v1

- **版本**：1.0.0，与 `api.v1.yaml` 同步发布
- **适用**：图谱生成任务进度（M0-04b）、问答流式输出（M2-08）
- **数据结构**：由 `api.v1.yaml` 的 `TaskEvent` 与 `ChatEvent` 定义。本文件只定义 OpenAPI 无法表达的部分：事件名、顺序保证、心跳、终止与重连。

OpenAPI 无法描述事件流的时序语义，因此二者缺一不可：**结构看 yaml，时序看本文件**。

> 任务状态转换、取消条件与处理阶段 SSE 关流的唯一规范是 [任务处理规格](../../specs/task-processing.md)（ADR-010）；票据鉴权的唯一规范是 [身份与访问规格](../../specs/identity-access.md) §5（ADR-013）。本文 §2、§4 按二者改写（B10），冲突时以规格为准。

---

## 1. 通用传输约定

| 项 | 约定 |
| --- | --- |
| Content-Type | `text/event-stream; charset=utf-8` |
| 缓冲 | 响应头须带 `Cache-Control: no-cache`、`X-Accel-Buffering: no`，否则反向代理会缓冲住流 |
| 编码 | 每条事件的 `data` 为**单行 JSON**，不换行、不美化 |
| 心跳 | 服务端每 15 秒发送注释行 `:ping`，客户端忽略，仅用于保活 |
| 鉴权（任务流） | `EventSource` 不支持自定义请求头，常规访问令牌**绝不**放进 URL。先用 Bearer 调 `POST /api/v1/tasks/{tid}/event-ticket` 申领一次性票据，再以 `?ticket=` 连接；服务端不读取 `Authorization` 头。详见 [身份与访问规格](../../specs/identity-access.md) §5 |
| 鉴权（问答流） | `fetch` 发起的 POST 流，照常带 `Authorization: Bearer` 头，不使用票据 |

> 票据只对该任务有效、只能核销一次、60 秒后过期，服务端只存其 sha256。票据缺失、无效、过期、已用或与任务不符 → 401 `UNAUTHENTICATED`；把常规访问令牌放进 `?ticket=` 或 `?token=` 同样 401。

---

## 2. 任务进度事件：`GET /api/v1/tasks/{tid}/events`

任务 SSE 只覆盖**处理阶段**：从建连到任务进入 `awaiting_review` 或 `failed` / `cancelled` 为止。**审核完成（`completed`）不通过已有连接送达**（`specs/task-processing.md` §7）。

### 事件名与载荷

每种事件有**独立的 `data` schema**，按 `stage` 判别，结构见 `api.v1.yaml` 的 `TaskEvent`（`oneOf` + `discriminator: stage`）。`data` 为 `{}` 或字段与事件不符的载荷会被结构校验拒绝。

| event | 何时发送 | data schema | 必填字段 | 之后 |
| --- | --- | --- | --- | --- |
| `stage` | 建连快照（非终态）；进入新阶段；阶段内进度变化；`cancel_requested` 由 false 变 true | `TaskStageEvent` | `task_id`、`stage`（`queued`～`awaiting_review`）、`progress`、`cancel_requested` | `stage = awaiting_review` 时服务端关流，其余保持连接 |
| `done` | 仅当建连时任务已 `completed`，作为首条快照 | `TaskDoneEvent` | `task_id`、`stage = completed`、`progress = 1` | 关流 |
| `error` | 处理中进入 `failed`，或建连时已 `failed` | `TaskErrorEvent` | `task_id`、`stage = failed`、`progress`、`error`（非 null） | 关流 |
| `cancelled` | 处理中进入 `cancelled`，或建连时已 `cancelled` | `TaskCancelledEvent` | `task_id`、`stage = cancelled`、`progress`、`cancel_requested = true` | 关流 |

- 事件只带计数（`counts`，含 `chunks_failed`），不带 `failed_chunks` 明细；明细见 `GET /api/v1/tasks/{tid}` 的快照。
- **终态集合**：`completed`、`failed`、`cancelled`。`awaiting_review` 是处理结束的**非终态**，但它是处理期连接的结束事件。

### 状态转换

转换表、触发者与取消条件**只在** [`specs/task-processing.md`](../../specs/task-processing.md) §1、§2 与 §4，本文不另写一份（两份表分头演进正是审查 R05 的成因）。主线为：

```
queued → parsing → extracting → merging → persisting → awaiting_review → completed
```

`cancel_requested` 是标志位不是状态：取消未生效前 `stage` 仍是当前阶段，事件带 `cancel_requested: true`，前端显示「取消中」。

### 顺序保证

1. 连接建立后**立即**补发一条当前快照：非终态为 `stage`，终态为对应的 `done` / `error` / `cancelled`。客户端因此不需要先调 `GET /api/v1/tasks/{tid}` 取初始值。
2. `stage` 只能沿主线前进，**不得回退**；`progress` 单调不减。跨连接同样成立，重连后的快照不小于断开前。
3. **每个连接恰好以一条结束事件收尾**：`stage = awaiting_review` 的快照，或 `done` / `error` / `cancelled` 之一；同一连接内这几种结束事件互斥，发送后服务端即关流。这是按连接的保证，不是按任务生命周期的保证：一个最终 `completed` 的任务，其处理期的连接都以 `awaiting_review` 收尾，永远收不到 `done`。
4. 客户端收到任何结束事件后必须主动 `close()`，不得为等待 `done` 保持或重建连接。审核完成用 `GET /api/v1/tasks/{tid}`（`stage = completed`）或课程发布状态观察。
5. 同一任务允许多个连接，各自先收快照，此后事件广播给全部连接。worker 崩溃时任务停在原阶段，连接照常心跳。

### 阶段与进度映射

`progress` 为整体进度，按阶段分段推进，段内按 `counts.chunks_done / counts.chunks_total` 线性插值：

| stage | progress 区间 |
| --- | --- |
| `queued` | 0.00 |
| `parsing` | 0.00 – 0.10 |
| `extracting` | 0.10 – 0.60 |
| `merging` | 0.60 – 0.80 |
| `persisting` | 0.80 – 0.95 |
| `awaiting_review` | 0.95 |
| `completed` | 1.00 |
| `failed` / `cancelled` | 保持进入终态时的值 |

前端进度条直接使用 `progress`，阶段名单独展示，不要自行换算。

### 示例

```text
:ping

event: stage
data: {"task_id":"t_01","stage":"extracting","progress":0.34,"cancel_requested":false,"counts":{"chunks_done":5,"chunks_total":14,"chunks_failed":0,"kp_count":23,"relation_count":0},"elapsed_ms":18420}

event: stage
data: {"task_id":"t_01","stage":"awaiting_review","progress":0.95,"cancel_requested":false,"counts":{"chunks_done":14,"chunks_total":14,"chunks_failed":1,"kp_count":47,"relation_count":88},"elapsed_ms":43100}
```

`awaiting_review` 之后服务端关流。任务发布后才建立的连接只收到一条：

```text
event: done
data: {"task_id":"t_01","stage":"completed","progress":1}
```

失败时：

```text
event: error
data: {"task_id":"t_01","stage":"failed","progress":0.42,"error":{"code":"EXTRACTION_INCOMPLETE","message":"抽取失败的块超过阈值","details":{"chunks_failed":3,"chunks_total":10,"threshold":0.2}}}
```

> `failed` 是**任务的领域状态**，不是 HTTP 错误。SSE 连接本身仍是 200，`GET /api/v1/tasks/{tid}` 也返回 200。

---

## 3. 问答流式事件：`POST /api/v1/courses/{cid}/chat`

`POST` 无法用 `EventSource`，前端使用 `fetch` + `ReadableStream` 读取，照常带 `Authorization` 头。

时序与文法、终态矩阵、撤回规则、JSON 模式的**唯一规范**是 [可信问答规格](../../specs/grounded-qa.md) Q2、Q5、Q6、Q7（ADR-015）。本节只摘要 wire 形状，冲突时以规格为准。

### 事件名与载荷

每种事件有**独立的 `data` schema**，且都以 `event` 字段自描述。结构见 `api.v1.yaml`
的 `ChatEvent`（`oneOf` + `discriminator: event`）。

| event | 何时发送 | data schema | 必填字段 |
| --- | --- | --- | --- |
| `meta` | 检索与判定完成、开流即发 | `ChatMetaEvent` | `event`、`status`、`retrieved`（`not_covered` 时为 0）、`graph_version`、`request_id` |
| `delta` | 生成中的正文增量 | `ChatDeltaEvent` | `event`、`delta`（非空串） |
| `done` | 终态已构造 | `ChatDoneEvent` | `event`、`final`（`ChatResponse`，含 `answer`、`citations`、`graph_version`、`request_id`；`not_covered` 另含 `reason`） |
| `error` | 开流后的异常终止（Q5 O7～O13） | `ChatErrorEvent` | `event`、`error`（`ChatError`：`details.request_id` 必填；`LLM_UNAVAILABLE` 另须 `details.reason ∈ {upstream, stream_interrupted, timeout, auth}`） |

> `data` 为 `{}` 的事件**不合法**，会被结构校验拒绝（codex 审查 R04）。

### 事件文法（Q2）

```text
stream := meta(status = not_covered) done(not_covered: no_retrieval_hit | below_similarity_threshold)
        | meta(status = answered)    delta*  ( done(answered | not_covered: insufficient_evidence | all_citations_invalidated)
                                             | error )
```

1. `meta` 恰好一条且恒为首条。`meta.status = not_covered` 当且仅当检索阶段拒答，其后没有 `delta`、没有 `error`，直接发 `done`。
2. `meta.status = answered` 表示进入生成，**不是承诺**：终态仍可能是 `not_covered`（`insufficient_evidence`、`all_citations_invalidated`）或 `error`。前端不得在 `meta` 阶段锁定结局。
3. `done` 与 `error` 互斥、恰好一条、恒为末条，发送后关流。`:ping` 心跳可出现在任意位置，不是事件。
4. `insufficient_evidence` 时 `delta` 恰为 0 条；`error` 前可以有 0 条或多条 `delta`。
5. 客户端断开后服务端停止生成，不再发送任何事件（O14）。
6. 首个 `delta`（或 `not_covered` 的 `done`）须在 3 秒内到达，完整响应 ≤15 秒（`specs/course-knowledge-graph.md` 验收条件 9；链路时限见 A07）。
7. 任意网络分片都必须能解析：每条事件的 `data` 是单行 JSON，跨分片的半条事件要缓冲到完整行再解析。

### 最终正文与撤回（Q6）

1. **临时正文**：从首个 `delta` 起以「生成中」样式显示；其中的 `[n]` 只作普通文本，不可点击；不写入对话历史。
2. **唯一保留正文的结局是 `done` 且 `final.status = answered`**：此时 `final.answer` 与已下发全部 `delta` 的逐字拼接**完全相等**（不变式 I1），以 `final.answer` 为准显示，标记变为可点击。若两者不一致，显示 `final.answer` 并上报异常。
3. **其余一切结局整段撤回临时正文**，不保留部分答案：
   - `not_covered`（任一 `reason`）→ 显示 `final.answer`（服务端固定模板，不含模型输出）；
   - `error` → 按 `error.code` 与 `details.reason` 显示前端文案；
   - 用户停止或客户端断开（O14）→「已停止」；
   - 流未以 `done` / `error` 结束（异常 EOF）、事件 JSON 无法解析、事件不符合上面的文法（**O15**）→ 客户端本地合成 `stream_interrupted` 错误，显示连接中断文案。
4. 不自动重试，也不自动重放提问；用户点「重试」即新请求（新 `request_id`，重新绑定版本）。同一对话同时最多一个在途请求。
5. 开流前的错误以非 200 状态与 `Error` JSON 返回：客户端先检查状态码与 `Content-Type`，再读取事件流。
6. 每个回答属于它的绑定版本 `graph_version`；同一会话中后续回答的版本不同时，前面的回答标注「基于第 N 版」（Q9）。

### 示例

```text
event: meta
data: {"event":"meta","status":"answered","retrieved":6,"graph_version":3,"request_id":"01J8ZQ3N6T7W8X9Y0ZABCDEF12"}

event: delta
data: {"event":"delta","delta":"栈是一种"}

event: delta
data: {"event":"delta","delta":"后进先出的线性表[1]。"}

event: done
data: {"event":"done","final":{"status":"answered","answer":"栈是一种后进先出的线性表[1]。","citations":[{"index":1,"chunk_id":"c_77","document_id":"d_03","section_path":"第3章 > 3.1 栈","page":52,"text":"栈是限定仅在表尾进行插入和删除操作的线性表。"}],"related_kp_ids":["kp_12","kp_15"],"latency_ms":6200,"graph_version":3,"request_id":"01J8ZQ3N6T7W8X9Y0ZABCDEF12"}}
```

检索阶段拒答（没有 delta）：

```text
event: meta
data: {"event":"meta","status":"not_covered","retrieved":0,"graph_version":3,"request_id":"01J8ZQ4A1B2C3D4E5F6G7H8J9K"}

event: done
data: {"event":"done","final":{"status":"not_covered","answer":"课程资料中没有找到与这个问题相关的内容。","citations":[],"reason":"no_retrieval_hit","latency_ms":800,"graph_version":3,"request_id":"01J8ZQ4A1B2C3D4E5F6G7H8J9K"}}
```

模型以哨兵声明证据不足（`insufficient_evidence`，没有 delta）：

```text
event: meta
data: {"event":"meta","status":"answered","retrieved":3,"graph_version":3,"request_id":"01J8ZQ5B2C3D4E5F6G7H8J9K0M"}

event: done
data: {"event":"done","final":{"status":"not_covered","answer":"检索到的课程资料不足以回答这个问题。","citations":[],"reason":"insufficient_evidence","latency_ms":2100,"graph_version":3,"request_id":"01J8ZQ5B2C3D4E5F6G7H8J9K0M"}}
```

生成完成但引用校验不通过（前端必须撤回已显示的 delta 正文）：

```text
event: meta
data: {"event":"meta","status":"answered","retrieved":3,"graph_version":3,"request_id":"01J8ZQ6C3D4E5F6G7H8J9K0M1N"}

event: delta
data: {"event":"delta","delta":"根据资料，栈是后进先出的。"}

event: done
data: {"event":"done","final":{"status":"not_covered","answer":"生成的回答无法与课程资料对应，已撤回。可以换一种问法或缩小问题范围。","citations":[],"reason":"all_citations_invalidated","latency_ms":5400,"graph_version":3,"request_id":"01J8ZQ6C3D4E5F6G7H8J9K0M1N"}}
```

出字后供应商流中断（撤回已显示的正文）：

```text
event: meta
data: {"event":"meta","status":"answered","retrieved":4,"graph_version":3,"request_id":"01J8ZQ7D4E5F6G7H8J9K0M1N2P"}

event: delta
data: {"event":"delta","delta":"栈的基本操作包括"}

event: error
data: {"event":"error","error":{"code":"LLM_UNAVAILABLE","message":"回答生成中断，请稍后重试。","details":{"reason":"stream_interrupted","request_id":"01J8ZQ7D4E5F6G7H8J9K0M1N2P"}}}
```

## 4. 重连

| 场景 | 行为 |
| --- | --- |
| 任务进度流断开 | **不依赖 `EventSource` 自动重连**：票据一次性，自动重连会带着已用票据必然 401，浏览器随后静默停止重试。由 `src/frontend/src/api/` 封装负责：出错即 `close()` → 重新申领票据 → 新建连接；新连接按 §2 先补当前快照。**不使用 `Last-Event-ID`**。建议退避 1、2、4… 秒，上限 30 秒；连续失败 5 次降级为每 5 秒轮询 `GET /api/v1/tasks/{tid}`（C12 可调，非契约） |
| 任务已 `awaiting_review` 或终态后建连 | 收到快照（`stage = awaiting_review`，或对应的 `done` / `error` / `cancelled`）后被关流，客户端不再重建 |
| 问答流断开 | **不自动重连**。已消费的 `delta` 不可重放，前端提示用户重新提问 |

---

## 5. 前端消费约束

- SSE 客户端封装在 `src/frontend/src/api/`，组件不得直接 `new EventSource`（`.claude/rules/frontend.md`）。
- 组件卸载时必须关闭连接，否则任务页反复进出会累积连接。
- 丢弃 `task_id` 不等于当前订阅任务的事件：切换资料或课程时，旧流的迟到事件不得污染当前视图。
- 进度、错误、取消三种终态都要有对应 UI 态；空态与加载态同样必须覆盖。

## 6. 变更策略

事件名、顺序保证与终态语义属于破坏性变更，必须新增 `events.v2.md` 并在 `api.v2.yaml` 中同步，不得原地修改本文件。新增可选字段不算破坏性变更。

> 例外记录：B10（2026-09-24）按 ADR-010、ADR-013 原地改写了 §1 鉴权、§2 关流语义与 §4 重连，并收紧了 `TaskEvent` 结构。依据是 `specs/task-processing.md` §7：v1 尚无任何消费者（C11/C12 未实现），此时修改迁移成本为零。此后再改须按本节升 v2。
