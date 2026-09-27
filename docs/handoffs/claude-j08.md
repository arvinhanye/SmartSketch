# claude-j08 — 实现问答 fetch 流客户端

- **任务**：J08 实现问答 fetch 流客户端（依赖 J07 后端 SSE API、B15 HTTP 客户端）
- **状态**：IMPLEMENTED / 待审查验证（TDD 红→绿，定向 73 passed，type-check exit 0）
- **分支 / worktree**：`claude/impl-j08` @ `/Users/arvinhan/Desktop/SmartSketch/.worktrees/impl-j08`
- **base**：`f6325fe`（`origin/main`）；分支已 rebase 到 main 之上，只含 1 个提交（3 个新文件）
- **PR**：[#300](https://github.com/arvinhanye/SmartSketch/pull/300)（base `main` ← head `claude/impl-j08`）
- **review_status**：ready_for_review

## 1. 交付物（本轮仅 3 个文件，未触碰文件锁外任何文件）

| 文件 | 说明 |
| --- | --- |
| `src/frontend/src/api/chatStream.ts`（新建，574 行） | 问答 `POST /api/v1/courses/{cid}/chat` 的 `fetch` + `ReadableStream` 客户端 |
| `tests/frontend/j08.test.ts`（新建，745 行） | 73 个用例：载荷校验、文法、分片、开流前错误、EOF、取消、不重放 |
| `docs/handoffs/claude-j08.md`（本文件） | 交接 |

未改动：`taskEvents.ts`（只 import）、`http.ts`、生成物 `openapi.d.ts`、契约真源、`package.json`。未新增依赖。

## 2. 接口形状（J09 消费面）

```ts
// 类型全部取自生成物：components['schemas'][...]
type ChatRequest / ChatResponse / ChatEvent / ChatMetaEvent / ChatDeltaEvent /
     ChatDoneEvent / ChatErrorEvent / ChatError / ChatStatus / NotCoveredReason /
     ChatLlmUnavailableReason
type ChatEventName = 'meta' | 'delta' | 'done' | 'error'
type ChatStreamEvent =                       // 逐条投递给 onEvent（含终态）
  | { kind: 'meta';  data: ChatMetaEvent }  | { kind: 'delta'; data: ChatDeltaEvent }
  | { kind: 'done';  data: ChatDoneEvent }  | { kind: 'error'; data: ChatErrorEvent }
type ChatStreamOutcome =                     // send 的返回值：服务端终态事件
  | { kind: 'done';  final: ChatResponse }  | { kind: 'error'; error: ChatError }

function createChatStreamClient(options?: ChatStreamClientOptions): ChatStreamClient
interface ChatStreamClient {
  send(cid: string, request: ChatRequest, options?: ChatSendOptions): Promise<ChatStreamOutcome>
}
interface ChatSendOptions { signal?: AbortSignal; timeoutMs?: number; onEvent?: (e: ChatStreamEvent) => void }
interface ChatStreamClientOptions {
  fetch?: FetchLike; baseUrl?: string; getAccessToken?: () => string | null | undefined
  onUnauthenticated?: (e: ApiError | InvalidResponseError) => void
  timeoutMs?: number; timers?: ChatStreamTimers; maxSseLineLength?: number
}

// 纯函数（可直接单测）
function parseChatEvent(name: string, data: string):
  { kind: 'event'; event: ChatEvent } | { kind: 'invalid'; reason: string }
function advanceChatGrammar(state: ChatGrammarState, event: ChatEvent):
  { ok: true; state: ChatGrammarState } | { ok: false; reason: string }
const INITIAL_CHAT_GRAMMAR: ChatGrammarState      // { phase: 'expect_meta', deltaCount: 0 }
const DEFAULT_CHAT_TIMEOUT_MS = 30_000
class ChatStreamInterruptedError extends Error     // O15：kind='interrupted'，reason='eof'|'protocol'|'read_error'
```

### 结局判别（J09 用法）

| 情形 | 表现 | J09 文案（Q6） |
| --- | --- | --- |
| `done` | `send` 返回 `{ kind:'done', final }` | `final.status='answered'` → 以 `final.answer` 替换临时正文、引用可点击；`not_covered` → 撤回 + 显示 `final.answer` |
| 服务端 `error` 事件 | `send` 返回 `{ kind:'error', error }` | 按 `error.code` / `details.reason` 显示，撤回临时正文 |
| 异常 EOF / 坏 JSON / 文法违规（O15） | `throw ChatStreamInterruptedError` | 连接中断文案，撤回 |
| 取消（O14，外部 signal） | `throw AbortedError` | 「已停止」，撤回 |
| 超时 | `throw TimeoutError` | 连接中断文案 |
| 开流前错误 | `throw ApiError` / `InvalidResponseError` / `NetworkError` | 普通错误提示（无临时正文） |

- 请求：`POST {baseUrl}/api/v1/courses/{cid}/chat`，体为 `JSON.stringify(request)`，`Accept: text/event-stream`、
  `Content-Type: application/json`，`Authorization: Bearer <token>`；**令牌绝不进 URL**。
- `onEvent` 收到全部四条事件（含终态），`send` 的 promise 再给终态；回调抛错会终止本次流（在 `finally` 中断开底层体）。
- 明确**不重连、不重试、不自动重放提问**（与 `taskEvents.ts` 的退避重连形成对照，Q6 第 4 条）：任何失败路径只发 1 次请求，由用例钉住。

## 3. 已运行命令与实测结果

```bash
# 1) 红灯（实现前，模块不存在）——真实输出
npm --prefix src/frontend run test -- --run ../../tests/frontend/j08.test.ts
#   Error: Failed to resolve import "../../src/frontend/src/api/chatStream" from "../../tests/frontend/j08.test.ts".
#   Does the file exist?          → Test Files 1 failed (1) / Tests no tests   EXIT=1

# 2) 绿灯（实现后）
npm --prefix src/frontend run type-check                → EXIT=0
npm --prefix src/frontend run test -- --run ../../tests/frontend/j08.test.ts
#   ✓ 73 passed (73)   Test Files 1 passed (1)   EXIT=0

# 3) 前端全量回归
npm --prefix src/frontend run test -- --run
#   Test Files 1 failed | 19 passed (20)   Tests 2 failed | 707 passed (709)   EXIT=1
#   失败两条都在 tests/frontend/b02.test.ts「npm test 的退出码」：
#     × 断言失败时命令非 0（26672ms）  × 一个用例都没收集到时命令非 0（6399ms）
#   均为已知本机 flake（B02 用 spawnSync 再跑一次嵌套 vitest，本机 jsdom 环境创建慢，超 5s 默认超时）。

# 4) 推送与 CI（PR #300；rebase 到 origin/main f6325fe 后重跑，结论同上）
#   git push origin claude/impl-j08  → PR #300（changedFiles=3，MERGEABLE）
#   gh api repos/.../commits/89eff9c/check-runs →
#     Backend: success | Frontend: success | Repository scaffold: success（各 2 条 run 全绿）
```

**b02 flake 对照实验（证明与 J08 无关）**：把本轮两个新文件移出后单跑 `b02.test.ts`，仍失败并超时
（`Test Files 1 failed (1) / Tests 1 failed | 4 passed (5)`，`B02_WITHOUT_J08_EXIT=1`）；移回后一致。除 b02 外 19 个文件全绿。

## 4. 反向篡改矩阵（10 处，逐处判红后复原；`diff` 确认与原文件逐字节相同）

| # | 篡改 | 判红的用例 |
| --- | --- | --- |
| T1 | `decoder.decode(chunk.value, { stream: true })` → 非 stream 解码 | UTF-8 多字节被切在分片中间：stream 解码，不产生替换字符 |
| T2 | 不复用 `createSseParser`，自写只按 `\n\n` 分帧（丢 CRLF / 跨块 `\r\n`） | CRLF 行结束与跨块的 `\r + \n` 都能分帧 |
| T3 | 未知事件名 / 非法载荷不再中断，直接 `continue` 忽略 | 文法违规：未知事件名；文法违规：`data` 为 `{}`；坏 JSON 事件不当成成功；不自动重放（共判红 4 条） |
| T4 | 异常 EOF 本地合成 `done`（当作成功） | done/error 之前 EOF；一个字都没收到就 EOF；不自动重放；连续发起新提问（共 4 条） |
| T5 | 取消不再 abort 底层响应体（去掉 `abort` → `disconnect`） | 外部 signal 取消；超时取消底层 body；不自动重放（共 3 条） |
| T6 | 去掉 `meta` 首条校验 | 首条不是 meta → 违规（纯函数）；文法违规：首条不是 meta（流级） |
| T7 | 允许多条 `meta`（去掉唯一性校验） | 第二条 meta → 违规（纯函数）；文法违规：meta 出现两次（流级） |
| T8 | 收到 `done` 立即返回，不再检同批后续事件 | 文法违规：done 之后同批还有事件 |
| T9 | 非 200 不看 `Content-Type`，直接按 JSON 解析 | 非 200 且 Content-Type 不是 JSON：响应体再像契约 Error 也不当成 ApiError |
| T10 | `insufficient_evidence` 不再要求 delta 恰为 0 条 | insufficient_evidence 却已下发 delta（纯函数）；同名的流级用例 |

## 5. 关键决定

1. **复用 `createSseParser`** 处理 CRLF / 跨块 `\r\n` / 多行 `data:` / `:ping`，不重写解析器（`taskEvents.ts` 只读 import）。
2. **未知事件名即 O15**（与 `parseTaskEvent` 的「未知即忽略」向前兼容不同）：chat 文法要求闭集，Q2/§3 明示未知事件中断。
3. **终态不提前 return**：同批里 `done` 之后还有事件也要判违规（QA-23），所以整批过完状态机再交还终态。
4. **服务端 `error` 事件 = 返回值；流中断 = 异常**：J09 用 `instanceof ChatStreamInterruptedError` 区分 O15 与服务端 error。
5. **`meta` 载荷额外收紧**：`not_covered` ⟹ `retrieved = 0`，`answered` ⟹ `retrieved ≥ 1`（Q3.1「A 非空」）；
   `done.final` 按 `status` 分支校验（answered 至少一条可定位引用、not_covered 空引用 + 闭集 reason）；
   `error` 按四码闭集校验，`LLM_UNAVAILABLE` 必带 `details.reason`，其余三码不带 reason。
6. **开流前先看 `Content-Type`**：非 200 时若 Content-Type 不是 JSON，即使体长得像契约 `Error` 也抛
   `InvalidResponseError`（防反向代理 HTML 页 / 伪造体）。
7. **401 与 B15 对齐**：401 一律回调 `onUnauthenticated`（清会话），与错误体是 `ApiError` 还是 `InvalidResponseError` 无关。
8. **超时可注入 `timers`**：与 C12 的假计时器风格一致，超时用例可确定性判红/绿；默认 30 秒。
9. `Citation` 的生成类型因 yaml `oneOf` 带 `| unknown`，运行时校验按 ADR-003 自实现（`index/chunk_id/document_id/text` + `page` 或 `section_path`）。

## 6. 未做 / 风险 / 待决

- **未做**：`Accept: application/json` 的 JSON 模式（Q7）不在 J08 范围；delta 的 I1 拼接一致性检查（`final.answer` 是否等于 delta 拼接）留给 J09（Q6 第 2 条要求「显示 final.answer 并上报异常」）；未做空闲超时（首字 3s / 全程 15s）的分段时限，只有整体超时。
- **风险**：`onEvent` 回调抛错会终止整条流（未吞异常、也未 `reportError`），与 `taskEvents` 的「回调异常不影响后续投递」策略不同；若 J09 期望后者需在集成时确认。
- **风险**：`answered` ⟹ `retrieved ≥ 1` 的收紧如果后端在生成阶段确实允许空 A，会成为误判；依据是 Q3.1「允许引用集合 A 非空」。
- **待决（协调方）**：`docs/tasks.md` 的 J08 状态行与验收证据未由本 Agent 更新——worktree 任务给了严格文件锁（3 个文件），该文件不在锁内，请协调者按本交接补记。
- **待决（协调方）**：`tests/frontend/b02.test.ts` 的嵌套 vitest 探针用例在本机稳定超时，属既有 flake；是否放宽其 timeout 或改为 `pool: 'vmThreads'` 不在本轮范围。

## 7. 下一步（J09 消费本模块）

1. `const chat = createChatStreamClient({ getAccessToken, onUnauthenticated })`（与 H13 会话客户端同源；`baseUrl` 与 B15 一致）。
2. 发起：`const p = chat.send(cid, { question, history, kp_id }, { signal: scope.signal, onEvent })`；
   用 `onEvent` 累积 `delta.data.delta` 渲染临时正文（标记不可点击），用返回值决定撤回/保留。
3. `try/catch`：`ChatStreamInterruptedError` → 连接中断文案；`AbortedError` → 「已停止」；`TimeoutError` → 中断文案；`ApiError` → 开流前错误提示。
4. 用户点「重试」= 新 `send`（新 `request_id`）；同一对话同一时刻只保留一个在途 `send`，发新问题前先 `abort` 旧的（Q6 第 5 条）。
5. 本模块不做历史裁剪；`ChatRequest.history` 由 J09 按 H1 组装（只放 `answered`/`not_covered` 回合）。

## 8. 回滚

本轮新增两个文件、无破坏性改动：删除 `src/frontend/src/api/chatStream.ts` 与 `tests/frontend/j08.test.ts` 即回到 `origin/main` 行为；未改任何既有文件。
