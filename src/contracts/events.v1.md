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

`POST` 无法用 `EventSource`，前端使用 `fetch` + `ReadableStream` 读取。

### 事件名与载荷

每种事件有**独立的 `data` schema**，且都以 `event` 字段自描述。结构见 `api.v1.yaml`
的 `ChatEvent`（`oneOf` + `discriminator: event`）。

| event | 何时发送 | data schema | 必填字段 |
| --- | --- | --- | --- |
| `meta` | 检索完成、生成开始前 | `ChatMetaEvent` | `event`、`status` |
| `delta` | 每个 token 增量 | `ChatDeltaEvent` | `event`、`delta`（非空串） |
| `done` | 生成结束且引用校验完成 | `ChatDoneEvent` | `event`、`final` |
| `error` | 生成中断 | `ChatErrorEvent` | `event`、`error` |

> `data` 为 `{}` 的事件**不合法**，会被结构校验拒绝。这是 codex 审查 R04 的直接修复：
> 原先四种事件共用一个没有 `required` 的宽松对象，`{}` 也能通过。

### 最终正文的替换协议

这是本节最容易出错的地方，独立成条：

1. **`done.final` 是唯一权威正文。** 它是一个完整的 `ChatResponse`（`answered` 或
   `not_covered` 分支），含 `answer`、`citations`、`related_kp_ids`、`latency_ms`。
2. **前端收到 `done` 后用 `final.answer` 整体替换**累积的 delta 文本，不得把 delta
   拼接结果当作最终答案。两者可能不同：引用校验会剔除无效编号，正文需相应改写。
3. **delta 阶段的正文是临时态。** 其中出现的编号可能指向后续被剔除的条目，
   因此 `delta` 阶段**不得渲染可点击引用**，只能显示为普通文本或占位样式。
4. **全部引用失效时降级为未覆盖终态。** 若生成完成但引用校验后无一条有效，
   `done.final` 必须是 `not_covered` 分支，`reason = all_citations_invalidated`，
   `citations` 为空数组。**前端此时必须清除已显示的 delta 正文**，代之以
   `final.answer` 的解释——不得留下一段无依据却看起来已完成的答案（ADR-003）。
5. **`error` 与 `done` 互斥**，各自恰好一次，发送后关闭连接。`error` 表示生成过程
   异常中断（模型不可用、超时、上游报错），与「资料未覆盖」是两回事：后者是 `done`。

### 顺序保证

1. `meta` 恒为第一条，且**只发一条**。
2. `meta.status = not_covered` 时**不再发送任何 `delta`**，直接发 `done`。这是检索阈值
   拒答分支，既防幻觉也省耗时。
3. `meta.status = answered` 不是承诺——引用校验发生在生成之后，`done.final` 仍可能是
   `not_covered`（见上条第 4 点）。前端不得在 `meta` 阶段就锁定 UI 分支。
4. 首个 `delta`（或 `not_covered` 的 `done`）须在 3 秒内到达，完整响应 ≤15 秒
   （`specs/course-knowledge-graph.md` 验收条件 9）。
5. 任意网络分片都必须能解析：每条事件的 `data` 是单行 JSON，跨分片的半条事件要缓冲到
   完整行再解析，不得按分片边界切分。

### 示例

```text
event: meta
data: {"event":"meta","status":"answered","retrieved":6}

event: delta
data: {"event":"delta","delta":"栈是一种"}

event: delta
data: {"event":"delta","delta":"后进先出的线性表[1]。"}

event: done
data: {"event":"done","final":{"status":"answered","answer":"栈是一种后进先出的线性表[1]。","citations":[{"index":1,"chunk_id":"c_77","document_id":"d_03","section_path":"第3章 > 3.1 栈","page":52,"text":"栈是限定仅在表尾进行插入和删除操作的线性表。"}],"related_kp_ids":["kp_12","kp_15"],"latency_ms":6200}}
```

资料未覆盖时（检索阶段就拒答，没有 delta）：

```text
event: meta
data: {"event":"meta","status":"not_covered","retrieved":0}

event: done
data: {"event":"done","final":{"status":"not_covered","answer":"课程资料未覆盖该问题：本课程资料中未找到与「操作系统进程调度」相关的内容。","citations":[],"reason":"no_retrieval_hit","latency_ms":800}}
```

生成完成但引用全部失效（前端必须清除已显示的 delta 正文）：

```text
event: meta
data: {"event":"meta","status":"answered","retrieved":3}

event: delta
data: {"event":"delta","delta":"根据资料[1]，"}

event: done
data: {"event":"done","final":{"status":"not_covered","answer":"生成的回答无法与课程资料对应，已撤回。可换一种问法或缩小问题范围。","citations":[],"reason":"all_citations_invalidated","latency_ms":5400}}
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
