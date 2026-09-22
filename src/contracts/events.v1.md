# SSE 事件契约 v1

- **版本**：1.0.0，与 `api.v1.yaml` 同步发布
- **适用**：图谱生成任务进度（M0-04b）、问答流式输出（M2-08）
- **数据结构**：由 `api.v1.yaml` 的 `TaskEvent` 与 `ChatEvent` 定义。本文件只定义 OpenAPI 无法表达的部分：事件名、顺序保证、心跳、终止与重连。

OpenAPI 无法描述事件流的时序语义，因此二者缺一不可：**结构看 yaml，时序看本文件**。

---

## 1. 通用传输约定

| 项 | 约定 |
| --- | --- |
| Content-Type | `text/event-stream; charset=utf-8` |
| 缓冲 | 响应头须带 `Cache-Control: no-cache`、`X-Accel-Buffering: no`，否则反向代理会缓冲住流 |
| 编码 | 每条事件的 `data` 为**单行 JSON**，不换行、不美化 |
| 心跳 | 服务端每 15 秒发送注释行 `:ping`，客户端忽略，仅用于保活 |
| 鉴权 | `EventSource` 不支持自定义请求头；令牌通过 `?token=` 查询参数传递，服务端只接受一次性短时效令牌 |

> 鉴权方式是 SSE 的已知限制。查询参数会进入访问日志，因此该令牌**必须**与常规 Bearer 令牌分离、有效期 ≤60 秒且仅对该任务的读取有效。

---

## 2. 任务进度事件：`GET /api/v1/tasks/{tid}/events`

### 事件名

| event | 何时发送 | data |
| --- | --- | --- |
| `stage` | 进入新阶段，或同阶段内进度变化 | `TaskEvent` |
| `done` | 任务进入终态 `completed` | `TaskEvent`，`progress = 1` |
| `error` | 任务进入终态 `failed` | `TaskEvent`，`error` 必填 |
| `cancelled` | 任务进入终态 `cancelled` | `TaskEvent` |

### 规范转换表

状态机的**唯一规范表述**在这里。`docs/architecture.md`、`specs/` 与 `api.v1.yaml` 的
`TaskStage` 都引用本表，不各写一份——两份表述分头演进正是 codex 审查 R05 的成因。

| 起点 | 终点 | 触发者 | 条件 |
| --- | --- | --- | --- |
| （无） | `queued` | API（`POST /api/v1/courses/{cid}/documents`） | 资料落盘、任务记录创建 |
| `queued` | `parsing` | worker | 领取任务 |
| `parsing` | `extracting` | worker | 分块完成 |
| `extracting` | `merging` | worker | 实体与关系抽取完成 |
| `merging` | `persisting` | worker | 融合消歧完成 |
| `persisting` | `awaiting_review` | worker | DAG 校验通过且草稿图谱写入成功 |
| `awaiting_review` | `completed` | **教师**（`POST /api/v1/courses/{cid}/publish`） | 审核通过并发布。worker 不会自行把 `awaiting_review` 推到 `completed` |
| 任一非终态 | `failed` | worker | 该阶段不可恢复地失败，`error` 必填 |
| 任一非终态 | `cancelled` | worker | 取消标记已置且 worker 到达阶段边界（ADR-006） |

- **终态集合**：`completed`、`failed`、`cancelled`。终态之后不再发送该任务的任何事件。
- **`queued` 阶段的取消由谁执行**：任务尚未被 worker 领取时，取消端点直接把任务置为 `cancelled`
  并返回；worker 领取前先检查该标记，已取消的任务不再领取。运行中的取消由 worker 在阶段边界执行。
- **`cancel_requested` 是标志位不是状态**：取消未生效前 `stage` 仍是当前阶段，事件里带
  `cancel_requested: true`，前端把按钮显示为「取消中」。它不占用状态枚举，因此不是破坏性变更。
- **取消与完成竞争**：以先到达终态者为准，取消端点返回任务当前实际状态（ADR-006 第 4 条）。

### 顺序保证

1. 连接建立后**立即**补发一条 `stage`，反映当前状态。客户端因此不需要先调 `GET /api/v1/tasks/{tid}` 取初始值。
2. `stage` 的取值只能沿上表前进，**不得回退**：

   ```
   queued → parsing → extracting → merging → persisting → awaiting_review → completed
   ```

3. `progress` 单调不减。
4. 三个终态事件（`done` / `error` / `cancelled`）**互斥且恰好发生一次**，发送后服务端关闭连接。
5. 客户端收到终态事件后必须主动 `close()`，否则 `EventSource` 会自动重连并再次收到补发的终态事件。

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

前端进度条直接使用 `progress`，阶段名单独展示，不要自行换算。

### 示例

```text
:ping

event: stage
data: {"task_id":"t_01","stage":"extracting","progress":0.34,"counts":{"chunks_done":5,"chunks_total":14,"kp_count":23,"relation_count":0},"elapsed_ms":18420}

event: done
data: {"task_id":"t_01","stage":"completed","progress":1,"counts":{"chunks_done":14,"chunks_total":14,"kp_count":47,"relation_count":88},"elapsed_ms":43100}
```

失败时：

```text
event: error
data: {"task_id":"t_01","stage":"failed","progress":0.42,"error":{"code":"LLM_UNAVAILABLE","message":"主备模型均不可用，请稍后重试"}}
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
| 任务进度流断开 | `EventSource` 自动重连；服务端在新连接上按第 2 节补发当前状态。**不使用 `Last-Event-ID`**，因为补发当前快照即可恢复，无需重放历史 |
| 任务已终态后重连 | 立即发送对应终态事件并关闭 |
| 问答流断开 | **不自动重连**。已消费的 `delta` 不可重放，前端提示用户重新提问 |

---

## 5. 前端消费约束

- SSE 客户端封装在 `src/frontend/src/api/`，组件不得直接 `new EventSource`（`.claude/rules/frontend.md`）。
- 组件卸载时必须关闭连接，否则任务页反复进出会累积连接。
- 进度、错误、取消三种终态都要有对应 UI 态；空态与加载态同样必须覆盖。

## 6. 变更策略

事件名、顺序保证与终态语义属于破坏性变更，必须新增 `events.v2.md` 并在 `api.v2.yaml` 中同步，不得原地修改本文件。新增可选字段不算破坏性变更。
