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

## 2. 任务进度事件：`GET /api/tasks/{tid}/events`

### 事件名

| event | 何时发送 | data |
| --- | --- | --- |
| `stage` | 进入新阶段，或同阶段内进度变化 | `TaskEvent` |
| `done` | 任务进入终态 `completed` | `TaskEvent`，`progress = 1` |
| `error` | 任务进入终态 `failed` | `TaskEvent`，`error` 必填 |
| `cancelled` | 任务进入终态 `cancelled` | `TaskEvent` |

### 顺序保证

1. 连接建立后**立即**补发一条 `stage`，反映当前状态。客户端因此不需要先调 `GET /api/tasks/{tid}` 取初始值。
2. `stage` 的取值只能沿 ADR-004 状态机前进，**不得回退**：

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

> `failed` 是**任务的领域状态**，不是 HTTP 错误。SSE 连接本身仍是 200，`GET /api/tasks/{tid}` 也返回 200。

---

## 3. 问答流式事件：`POST /api/courses/{cid}/chat`

`POST` 无法用 `EventSource`，前端使用 `fetch` + `ReadableStream` 读取。

### 事件名

| event | 何时发送 | data |
| --- | --- | --- |
| `meta` | 检索完成、生成开始前 | `ChatEvent`，含 `status` |
| `delta` | 每个 token 增量 | `ChatEvent`，只含 `delta` |
| `done` | 生成结束且引用校验完成 | `ChatEvent`，含最终 `citations`、`related_kp_ids`、`latency_ms` |
| `error` | 生成中断 | `Error` |

### 顺序保证

1. `meta` 恒为第一条，且**只发一条**。
2. `meta.status = not_covered` 时**不再发送任何 `delta`**，直接发 `done`，`citations` 为空数组。这是检索阈值拒答分支，既防幻觉也省耗时（S2 6.4.6）。
3. `citations` 只在 `done` 中给出最终值。`delta` 阶段正文里出现的编号可能指向后续被引用校验剔除的条目，**前端必须等 `done` 才能渲染可点击引用**。
4. 首个 `delta`（或 `not_covered` 的 `done`）须在 3 秒内到达，完整响应 ≤15 秒（规格验收条件 9）。

### 示例

```text
event: meta
data: {"status":"answered"}

event: delta
data: {"delta":"栈是一种"}

event: delta
data: {"delta":"后进先出的线性表[1]。"}

event: done
data: {"status":"answered","citations":[{"index":1,"chunk_id":"c_77","document_id":"d_03","section_path":"第3章 > 3.1 栈","page":52,"text":"栈是限定仅在表尾进行插入和删除操作的线性表。"}],"related_kp_ids":["kp_12","kp_15"],"latency_ms":6200}
```

资料未覆盖时：

```text
event: meta
data: {"status":"not_covered"}

event: done
data: {"status":"not_covered","answer":"课程资料未覆盖该问题：本课程资料中未找到与「操作系统进程调度」相关的内容。","citations":[],"related_kp_ids":[],"latency_ms":800}
```

---

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
