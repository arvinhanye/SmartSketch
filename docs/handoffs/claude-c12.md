---
review_status: ready_for_review
task_id: C12
branch: claude/c12-task-stream
base: bdcf165（第八批认领提交，基于 main@d624208）
---

# C12 交接：前端任务流客户端

## 交付物

| 文件 | 内容 |
| --- | --- |
| `src/frontend/src/api/taskEvents.ts` | 新增。`createSseParser()`、`parseTaskEvent()`、`createTaskEventsClient({ client, fetch?, baseUrl?, timers?, policy?, reportError? }).subscribe(taskId, scope, handlers)`，以及 `DEFAULT_TASK_STREAM_POLICY` 和各类型 |
| `tests/frontend/c12.test.ts` | 38 个用例：解析器 7 个，事件校验 4 个，订阅 27 个（`it.each` 展开后计数） |

只放 HTTP/SSE 调用逻辑，不含组件或 composable。没有改 `http.ts`、`router/index.ts`、`main.ts`。

## 接口

```ts
const api = createTaskEventsClient({ client /* B15 会话客户端 */, baseUrl })
const sub = api.subscribe(taskId, courseStore.beginRequest(), {
  onUpdate(u) { /* u.source === 'stream' ? u.data : u.task；u.final 表示处理期结束 */ },
  onState(s) { /* connecting | streaming | reconnecting | polling | closed */ },
  onClose(r) { /* finished{stage} | unsubscribed | scope_invalidated | fatal{error} */ },
})
onUnmounted(() => sub.close())
```

- `onClose` 恰好调用一次。`close()` 可重复调用。回调里抛出的异常交给 `reportError`（默认在微任务中重新抛出），不会中断流。
- `fatal.error` 使用 B15 的错误类型（`ApiError` / `InvalidResponseError`），以及快照课程不符时的 `Error`。

## 关键决定

- **SSE 解析**：按 HTML 标准的 event stream 规则实现。行结束可以是 `\n`、`\r\n` 或单独的 `\r`；`\r` 在块尾时记一个标志，下一块开头的 `\n` 与它算同一个行结束。以 `:` 开头的注释行（`:ping`）忽略；多行 `data` 用 `\n` 连接；没有 `data` 的事件不派发；流末尾没有以空行结束的半条事件丢弃；`retry` 和未知字段忽略。字节解码用 `TextDecoder` 的 `stream: true`，被切开的 UTF-8 多字节字符能正确拼回。单行缓冲超过 1,000,000 字符时抛协议错误。
- **运行时校验**：`TaskStageEvent`、`TaskDoneEvent`、`TaskErrorEvent`、`TaskCancelledEvent` 各自校验，事件名必须与 `stage` 对应。另外检查固定进度（`queued = 0`、`awaiting_review = 0.95`、`completed = 1`）、`error` 为契约中的 `Error`（错误码属于闭集）、`cancelled` 时 `cancel_requested === true`、`counts` 为非负整数。未知事件名和 `task_id` 不符的事件丢弃（events.v1 §5）；已知事件名但载荷不合法视为协议错误，按一次连接失败重连。
- **ErrorCode 运行时副本**：B15 的 `ERROR_CODES` 没有导出，本任务又不能改 `http.ts`，所以在本文件里复制了一份，并用同样的双向类型断言与契约保持一致（契约增删错误码时编译会失败）。后续可以改为从 `http.ts` 导出同一份，见待决 1。
- **鉴权**：票据通过注入的 B15 `HttpClient` 申领（`POST /api/v1/tasks/{tid}/event-ticket`，带 Bearer）。事件流用注入的 `fetch` 请求 `GET …/events?ticket=<encodeURIComponent>`，只带 `Accept: text/event-stream` 和 `cache: 'no-store'`，不带 `Authorization`，URL 中只有 `ticket` 一个参数。
- **结束与关闭**：收到结束事件（`stage = awaiting_review`、`done`、`error`、`cancelled`）后，先投递该事件（`final: true`），然后关闭：中止请求、`reader.cancel()`，清掉所有计时器。之后不再重连。
- **重连**：以下情况都算一次失败：申领票据时出现网络错误、超时或 5xx；事件流网络错误；事件流返回 401（票据可能在申领和建连之间过期）、5xx 或非 `text/event-stream` 响应；流在收到结束事件前 EOF；空闲超时；协议错误。每次失败后都重新申领票据、新建连接。退避为 `min(1000·2^(n-1), 30000)` ms；连续失败达到 5 次时降级为轮询：立即查询一次 `GET /api/v1/tasks/{tid}`，之后每 5 秒一次，直到出现 `awaiting_review` 或终态。轮询后不再切回 SSE。某次连接投递过有效事件后，连续失败计数从 1 重新开始。
- **空闲超时**（新增的可调项，契约没有要求）：开流后超过 45 秒没有收到任何字节，就判定为断线并重连。服务端每 15 秒发一次 `:ping`，所以 45 秒内没有任何字节只可能是连接已经半开或断掉。
- **不可恢复错误**：申领票据返回 401/403/404（401 已由 B15 触发清会话）、事件流返回 403/404、轮询返回 401/403/404、快照的 `course_id` 与作用域不符。遇到这些情况时以 `fatal` 关闭，不再重试。
- **课程隔离**：订阅需要传入 `CourseRequestScope`。作用域的 `signal` 被中止时立即以 `scope_invalidated` 关闭；每次投递前还会检查 `scope.isCurrent()`，所以 A→B→A 之后第一次 A 的迟到事件也会被丢弃。以已失效的作用域订阅时，不发出任何请求，直接关闭。
- **注入点**：`fetch`、`timers`（`setTimeout`/`clearTimeout`，退避、轮询间隔和空闲超时都走这里）、`policy`。实现不读时钟，失败计数也不依赖时间，因此没有注入时钟。测试使用假计时器，不依赖真实时间。

## 实际命令与结果

| 步骤 | 命令 | 结果 |
| --- | --- | --- |
| 依赖 | `npm ci --prefix src/frontend` | 成功 |
| 红灯 | `npm --prefix src/frontend run test -- --run ../../tests/frontend/c12.test.ts`（实现前） | 测试文件加载失败，`no tests`（模块不存在） |
| 绿灯 | 同上 | `38 passed`；另外单独连续运行 8 次，均为 38 passed |
| 变异检查 | 临时去掉「跨块 `\r\n`」处理后运行同上命令 | 4 个用例失败（CRLF、跨块 CRLF、逐字符分片、UTF-8 分片投递）；随后恢复源码 |
| 前端全量 | `npm --prefix src/frontend run test -- --run` | `6 files, 119 passed`。注意：第 1 次全量运行报告 `1 failed | 118 passed`，但当时没有保存失败用例名；此后又运行了 12 次（其中 3 次并发），全部为 119 passed，未能复现，见风险 1 |
| 类型检查 | `npm --prefix src/frontend run type-check` | 退出码 0（`tsconfig.node.json` 覆盖 `tests/frontend`） |
| 构建 | `npm --prefix src/frontend run build` | 退出码 0 |
| 门禁 | `./scripts/verify.sh` | 退出码 0，`Scaffold verification passed.` |
| 空白 | `git diff --check` | 无输出 |

未做：没有连接真实后端（C11/C16）在浏览器里联调，只用假 `fetch` 和 `ReadableStream` 验证。

## 接口 / 数据变更

- 没有改契约、后端或其他前端文件。新增的前端模块 API 见上文。

## 风险

1. **全量测试偶发 1 个失败**：没有抓到用例名，后续 12 次运行也没有复现，无法确认是否与 C12 有关。c12 单文件连续 8 次均通过。c12 测试用 20 轮 `setTimeout(0)` 冲刷异步链，如果在极端负载下不够，会表现为偶发失败。建议 CI 上观察一段时间；一旦复现，先记录用例名再处理。
2. `fetch` 在浏览器中收到 `signal` 中止后会取消响应体；测试里的假 `fetch` 不会这样做，所以实现同时显式调用了 `reader.cancel()`，测试以流的 `cancel` 回调作为关闭的证据。
3. 固定进度的校验比较严格（容差 1e-9）。如果后端以后对 `awaiting_review` 发出 0.95 以外的值，客户端会把它当作协议错误并重连，最终降级为轮询；轮询快照也做同样的校验，会被忽略。后端 C11 目前固定使用 0.95。

## 待决

1. 是否把 `http.ts` 的 `ERROR_CODES` / `isErrorBody` 导出，供本模块复用，以消除重复（需要改 B15 文件，本轮未获分配）。
2. 组合式封装（`useTaskProgress`：注入客户端、`onUnmounted` 时关闭、把作用域接到课程 store）留给使用它的页面任务（如 H02），本任务不写组件或 composable。
3. 降级为轮询后是否要定期尝试切回 SSE：规格没有要求，目前不切回。

## 回滚

只需还原本任务新增的三个文件和 `docs/tasks.md` 的 C12 行：`git revert <C12 提交>`。没有迁移、依赖或数据变更。
