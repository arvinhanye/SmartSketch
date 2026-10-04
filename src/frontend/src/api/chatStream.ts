import type { components } from '../../../contracts/v1/generated/typescript/openapi'
import type { InjectionKey } from 'vue'
import {
  AbortedError,
  ApiError,
  InvalidResponseError,
  NetworkError,
  TimeoutError,
  apiPath,
  type FetchLike,
} from './http'
import {
  DEFAULT_MAX_SSE_LINE_LENGTH,
  SseProtocolError,
  createSseParser,
  type SseMessage,
} from './taskEvents'

/**
 * 前端问答流客户端（J08）。
 *
 * - wire 形状看 `api.v1.yaml` 的 `ChatEvent`，时序与文法看 `src/contracts/events.v1.md` §3
 *   与 `specs/grounded-qa.md` Q2、Q6（唯一规范）：`meta` 恰好一条且恒为首条；
 *   `done` / `error` 互斥、恰好一条、恒为末条；`:ping` 心跳不是事件。
 * - 鉴权按 `events.v1.md` §1：问答流由 `fetch` 发起，照常带 `Authorization: Bearer`，
 *   不用任务流的票据，访问令牌绝不进 URL。
 * - SSE 分帧复用 `taskEvents` 的 `createSseParser`（不重写解析器），UTF-8 用
 *   `TextDecoder(..., { stream: true })` 增量解码，多字节字符被切开也不产生替换字符。
 * - **不自动重连、不自动重试、不自动重放提问**（与任务流的退避重连形成对照）：
 *   任何失败都只把结局交给调用方，用户点「重试」是新请求（Q6 第 4 条）。
 * - O15：流未以 `done` / `error` 结束（异常 EOF）、事件 JSON 无法解析、事件不符合文法
 *   → 本地合成 `ChatStreamInterruptedError`，绝不当作成功。
 * - O14：外部 `AbortSignal`（用户停止/切课）触发时立即停止读取并真正取消底层响应体，
 *   抛 `AbortedError`；超时抛 `TimeoutError`。
 * - 开流前的错误（非 200 + `Error` JSON）先看状态码与 `Content-Type`，按 `ErrorCode`
 *   抛 `ApiError`，不进入事件解析（Q6 第 6 条）。
 * - 服务端 `error` **事件**是终态，作为返回值交给调用方；「流中断」是抛出的异常。
 *   二者类型不同，J09 据此区分文案。
 */

export type ChatEvent = components['schemas']['ChatEvent']
export type ChatRequest = components['schemas']['ChatRequest']
export type ChatResponse = components['schemas']['ChatResponse']
export type ChatMetaEvent = components['schemas']['ChatMetaEvent']
export type ChatDeltaEvent = components['schemas']['ChatDeltaEvent']
export type ChatDoneEvent = components['schemas']['ChatDoneEvent']
export type ChatErrorEvent = components['schemas']['ChatErrorEvent']
export type ChatError = components['schemas']['ChatError']
export type ChatStatus = components['schemas']['ChatStatus']
export type NotCoveredReason = components['schemas']['NotCoveredReason']
export type ChatLlmUnavailableReason = components['schemas']['ChatLlmUnavailableReason']

/** 契约中的问答事件名（`events.v1.md` §3） */
export type ChatEventName = ChatEvent['event']

/** 默认超时（毫秒）：覆盖发起到流结束的全过程（链路时限 15 秒，留给网络与渲染余量） */
export const DEFAULT_CHAT_TIMEOUT_MS = 30_000

// ---------------------------------------------------------------- 载荷校验

// 契约闭集的运行时副本，用于校验事件载荷；下方类型断言保证与契约双向一致
const CHAT_EVENT_NAMES = ['meta', 'delta', 'done', 'error'] as const satisfies readonly ChatEventName[]
type MissingChatEventName = Exclude<ChatEventName, (typeof CHAT_EVENT_NAMES)[number]>
const chatEventNamesComplete: [MissingChatEventName] extends [never] ? true : MissingChatEventName = true
void chatEventNamesComplete

const CHAT_STATUSES = ['answered', 'not_covered'] as const satisfies readonly ChatStatus[]
type MissingChatStatus = Exclude<ChatStatus, (typeof CHAT_STATUSES)[number]>
const chatStatusesComplete: [MissingChatStatus] extends [never] ? true : MissingChatStatus = true
void chatStatusesComplete

const NOT_COVERED_REASONS = [
  'no_retrieval_hit',
  'below_similarity_threshold',
  'insufficient_evidence',
  'all_citations_invalidated',
] as const satisfies readonly NotCoveredReason[]
type MissingNotCoveredReason = Exclude<NotCoveredReason, (typeof NOT_COVERED_REASONS)[number]>
const notCoveredReasonsComplete: [MissingNotCoveredReason] extends [never] ? true : MissingNotCoveredReason = true
void notCoveredReasonsComplete

/** 问答开流后错误的码闭集：`LLM_UNAVAILABLE` 必带 `details.reason`，其余三码不带 */
const CHAT_ERROR_CODES = [
  'LLM_UNAVAILABLE',
  'BUDGET_EXCEEDED',
  'STORAGE_UNAVAILABLE',
  'INTERNAL_ERROR',
] as const satisfies readonly ChatError['code'][]
type MissingChatErrorCode = Exclude<ChatError['code'], (typeof CHAT_ERROR_CODES)[number]>
const chatErrorCodesComplete: [MissingChatErrorCode] extends [never] ? true : MissingChatErrorCode = true
void chatErrorCodesComplete

const LLM_UNAVAILABLE_REASONS = [
  'upstream',
  'stream_interrupted',
  'timeout',
  'auth',
  'truncated',
] as const satisfies readonly ChatLlmUnavailableReason[]
type MissingLlmReason = Exclude<ChatLlmUnavailableReason, (typeof LLM_UNAVAILABLE_REASONS)[number]>
const llmReasonsComplete: [MissingLlmReason] extends [never] ? true : MissingLlmReason = true
void llmReasonsComplete

const CHAT_EVENT_NAME_SET: ReadonlySet<string> = new Set(CHAT_EVENT_NAMES)
const STATUS_SET: ReadonlySet<string> = new Set(CHAT_STATUSES)
const NOT_COVERED_REASON_SET: ReadonlySet<string> = new Set(NOT_COVERED_REASONS)
const CHAT_ERROR_CODE_SET: ReadonlySet<string> = new Set(CHAT_ERROR_CODES)
const LLM_UNAVAILABLE_REASON_SET: ReadonlySet<string> = new Set(LLM_UNAVAILABLE_REASONS)

function isPlainObject(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function isNonEmptyString(value: unknown): value is string {
  return typeof value === 'string' && value !== ''
}

function isIntegerAtLeast(value: unknown, min: number): value is number {
  return typeof value === 'number' && Number.isInteger(value) && value >= min
}

/** 引用必须可定位：`page ≥ 1` 或 `section_path` 非空（ADR-003） */
function isCitation(value: unknown): boolean {
  if (!isPlainObject(value)) return false
  if (!isIntegerAtLeast(value.index, 1)) return false
  if (!isNonEmptyString(value.chunk_id)) return false
  if (!isNonEmptyString(value.document_id)) return false
  if (!isNonEmptyString(value.text)) return false
  if (value.page === undefined && value.section_path === undefined) return false
  if (value.page !== undefined && !isIntegerAtLeast(value.page, 1)) return false
  if (value.section_path !== undefined && !isNonEmptyString(value.section_path)) return false
  return true
}

function hasValidResponseOptionals(value: Record<string, unknown>): boolean {
  if (value.latency_ms !== undefined && !(typeof value.latency_ms === 'number' && value.latency_ms >= 0)) return false
  if (value.related_kp_ids !== undefined) {
    if (!Array.isArray(value.related_kp_ids)) return false
    if (!value.related_kp_ids.every(isNonEmptyString)) return false
  }
  return true
}

/** `ChatResponse`：按 `status` 分支——answered 至少一条引用，not_covered 引用必须为空且有闭集 reason */
function isChatResponse(value: unknown): value is ChatResponse {
  if (!isPlainObject(value)) return false
  if (!isNonEmptyString(value.answer)) return false
  if (!Array.isArray(value.citations) || !value.citations.every(isCitation)) return false
  if (!isIntegerAtLeast(value.graph_version, 1)) return false
  if (!isNonEmptyString(value.request_id)) return false
  if (!hasValidResponseOptionals(value)) return false
  if (value.status === 'answered') return value.citations.length >= 1
  if (value.status === 'not_covered') {
    return value.citations.length === 0 && NOT_COVERED_REASON_SET.has(value.reason as string)
  }
  return false
}

function isChatError(value: unknown): value is ChatError {
  if (!isPlainObject(value)) return false
  if (typeof value.code !== 'string' || !CHAT_ERROR_CODE_SET.has(value.code)) return false
  if (!isNonEmptyString(value.message)) return false
  if (!isPlainObject(value.details)) return false
  // 两支都必带 details.request_id（B13）
  if (!isNonEmptyString(value.details.request_id)) return false
  if (value.code === 'LLM_UNAVAILABLE') {
    return typeof value.details.reason === 'string' && LLM_UNAVAILABLE_REASON_SET.has(value.details.reason)
  }
  // 其余三码不带 reason（契约「闭合对象」）
  return value.details.reason === undefined
}

function isChatMetaEvent(value: Record<string, unknown>): value is ChatMetaEvent {
  if (typeof value.status !== 'string' || !STATUS_SET.has(value.status)) return false
  if (!isIntegerAtLeast(value.retrieved, 0)) return false
  if (!isIntegerAtLeast(value.graph_version, 1)) return false
  if (!isNonEmptyString(value.request_id)) return false
  // not_covered 当且仅当检索阶段拒答，此时 retrieved = 0；answered 进入生成，A 非空（Q2、Q3.1）
  return value.status === 'not_covered' ? value.retrieved === 0 : value.retrieved >= 1
}

export type ParsedChatEvent = { kind: 'event'; event: ChatEvent } | { kind: 'invalid'; reason: string }

/**
 * 按 `ChatEvent` 各分支对单条 SSE 事件做运行时校验：事件名必须闭集内、且与 `data.event` 一致。
 * 未知事件名不是「向前兼容」（对比任务流的 `parseTaskEvent`）：文法要求未知事件即 O15。
 */
export function parseChatEvent(name: string, data: string): ParsedChatEvent {
  if (!CHAT_EVENT_NAME_SET.has(name)) return { kind: 'invalid', reason: `未知事件名 ${name}` }
  let value: unknown
  try {
    value = JSON.parse(data)
  } catch {
    return { kind: 'invalid', reason: `事件 ${name} 的 data 不是 JSON` }
  }
  if (!isPlainObject(value)) return { kind: 'invalid', reason: `事件 ${name} 的 data 不是对象` }
  if (value.event !== name) return { kind: 'invalid', reason: `事件名 ${name} 与 data.event 不一致` }

  switch (name) {
    case 'meta':
      if (!isChatMetaEvent(value)) return { kind: 'invalid', reason: 'meta 载荷不符合契约' }
      break
    case 'delta':
      if (!isNonEmptyString(value.delta)) return { kind: 'invalid', reason: 'delta 载荷不符合契约' }
      break
    case 'done':
      if (!isChatResponse(value.final)) return { kind: 'invalid', reason: 'done.final 不符合契约' }
      break
    case 'error':
      if (!isChatError(value.error)) return { kind: 'invalid', reason: 'error 载荷不符合契约' }
      break
  }
  return { kind: 'event', event: value as ChatEvent }
}

// ---------------------------------------------------------------- 事件文法（Q2）

export type ChatGrammarPhase = 'expect_meta' | 'meta_answered' | 'meta_not_covered' | 'terminal'

export interface ChatGrammarState {
  readonly phase: ChatGrammarPhase
  /** 已下发的 delta 条数：`insufficient_evidence` 的终态要求恰为 0 条 */
  readonly deltaCount: number
}

export const INITIAL_CHAT_GRAMMAR: ChatGrammarState = Object.freeze({ phase: 'expect_meta', deltaCount: 0 })

export type ChatGrammarStep = { ok: true; state: ChatGrammarState } | { ok: false; reason: string }

/**
 * `events.v1.md` §3 / `specs/grounded-qa.md` Q2 的事件文法状态机：
 *
 * ```text
 * stream := meta(not_covered) done(not_covered)
 *         | meta(answered)    delta*  ( done | error )
 * ```
 */
export function advanceChatGrammar(state: ChatGrammarState, event: ChatEvent): ChatGrammarStep {
  switch (state.phase) {
    case 'expect_meta': {
      if (event.event !== 'meta') return { ok: false, reason: `首条事件必须是 meta，实际收到 ${event.event}` }
      return {
        ok: true,
        state: { phase: event.status === 'not_covered' ? 'meta_not_covered' : 'meta_answered', deltaCount: 0 },
      }
    }
    case 'meta_not_covered': {
      if (event.event !== 'done') return { ok: false, reason: `meta(status=not_covered) 之后只能跟 done，实际收到 ${event.event}` }
      if (event.final.status !== 'not_covered') return { ok: false, reason: 'meta(status=not_covered) 之后只能是 not_covered 的 done' }
      return { ok: true, state: { phase: 'terminal', deltaCount: 0 } }
    }
    case 'meta_answered': {
      switch (event.event) {
        case 'meta':
          return { ok: false, reason: 'meta 恰好一条且恒为首条' }
        case 'delta':
          return { ok: true, state: { phase: 'meta_answered', deltaCount: state.deltaCount + 1 } }
        case 'done':
          if (
            event.final.status === 'not_covered' &&
            event.final.reason === 'insufficient_evidence' &&
            state.deltaCount > 0
          ) {
            return { ok: false, reason: 'insufficient_evidence 时 delta 必须恰为 0 条' }
          }
          return { ok: true, state: { phase: 'terminal', deltaCount: state.deltaCount } }
        case 'error':
          return { ok: true, state: { phase: 'terminal', deltaCount: state.deltaCount } }
      }
      return { ok: false, reason: `无法识别的事件 ${String((event as ChatEvent).event)}` }
    }
    case 'terminal':
      return { ok: false, reason: `done / error 之后不允许再出现事件（收到 ${event.event}）` }
  }
}

// ---------------------------------------------------------------- 错误类型

/** O15 的中断原因：异常 EOF、协议/文法违规、读流本身失败 */
export type ChatStreamInterruption = 'eof' | 'protocol' | 'read_error'

/**
 * 客户端本地合成的「连接中断」（O15）：EOF 未到终态、事件 JSON 无法解析、事件不符合文法。
 * 与**服务端 `error` 事件**（作为 `ChatStreamOutcome` 返回）类型不同，J09 据此区分文案。
 */
export class ChatStreamInterruptedError extends Error {
  readonly kind = 'interrupted' as const
  readonly reason: ChatStreamInterruption

  constructor(reason: ChatStreamInterruption, message: string, options?: { cause?: unknown }) {
    super(`问答流中断（${reason}）：${message}`, options)
    this.name = 'ChatStreamInterruptedError'
    this.reason = reason
  }
}

// ---------------------------------------------------------------- 客户端

export interface ChatStreamEventMap {
  meta: ChatMetaEvent
  delta: ChatDeltaEvent
  done: ChatDoneEvent
  error: ChatErrorEvent
}

/** 逐条下发给 `onEvent` 的事件（含终态事件，便于回调驱动的消费者） */
export type ChatStreamEvent = { [K in ChatEventName]: { kind: K; data: ChatStreamEventMap[K] } }[ChatEventName]

/** `send` 的终态返回值：服务端 `done` / `error` 事件，互斥且恰好一条 */
export type ChatStreamOutcome =
  | { kind: 'done'; final: ChatResponse }
  | { kind: 'error'; error: ChatError }

export interface ChatSendOptions {
  /** 外部取消信号（用户停止、切课作用域失效）：立即停止读取并取消底层响应体 */
  signal?: AbortSignal
  /** 覆盖客户端默认超时（毫秒） */
  timeoutMs?: number
  /** 每收到一条事件即回调（含终态）；回调抛错会终止本次流 */
  onEvent?: (event: ChatStreamEvent) => void
}

export interface ChatStreamTimers {
  setTimeout(fn: () => void, ms: number): unknown
  clearTimeout(handle: unknown): void
}

export interface ChatStreamClientOptions {
  /** 事件流请求用的 fetch；默认全局 fetch，测试注入假实现 */
  fetch?: FetchLike
  /** API 源（协议+主机+端口），默认空串即同源 */
  baseUrl?: string
  /** 每次请求时读取当前访问令牌；无令牌返回 null/undefined */
  getAccessToken?: () => string | null | undefined
  /** 401 时调用（H13：清会话并回登录页）；随后仍抛出该错误 */
  onUnauthenticated?: (error: ApiError | InvalidResponseError) => void
  /** 默认超时（毫秒），覆盖发起到读完事件流的全过程 */
  timeoutMs?: number
  timers?: ChatStreamTimers
  /** SSE 单行上限，透传给 `createSseParser` */
  maxSseLineLength?: number
}

export interface ChatStreamClient {
  /**
   * 发送一次提问并读到终态。**不重试、不重放**：
   * - 解析出 `done` / `error` 事件即返回对应结局；
   * - 开流前错误抛 `ApiError` / `InvalidResponseError` / `NetworkError`；
   * - O15 抛 `ChatStreamInterruptedError`；
   * - 取消抛 `AbortedError`，超时抛 `TimeoutError`。
   */
  send(cid: string, request: ChatRequest, options?: ChatSendOptions): Promise<ChatStreamOutcome>
}

export const CHAT_STREAM_CLIENT_KEY: InjectionKey<ChatStreamClient> = Symbol('smartsketch.chat-stream')

const EVENT_STREAM_CONTENT_TYPE = /^text\/event-stream\b/i
const JSON_CONTENT_TYPE = /^application\/(?:problem\+)?json\b/i

export function createChatStreamClient(options: ChatStreamClientOptions = {}): ChatStreamClient {
  const fetchImpl: FetchLike = options.fetch ?? ((input, init) => globalThis.fetch(input, init))
  const baseUrl = (options.baseUrl ?? '').replace(/\/+$/, '')
  const defaultTimeoutMs = options.timeoutMs ?? DEFAULT_CHAT_TIMEOUT_MS
  const timers: ChatStreamTimers = options.timers ?? {
    setTimeout: (fn, ms) => globalThis.setTimeout(fn, ms),
    clearTimeout: (handle) => globalThis.clearTimeout(handle as ReturnType<typeof globalThis.setTimeout>),
  }
  const maxSseLineLength = options.maxSseLineLength ?? DEFAULT_MAX_SSE_LINE_LENGTH

  function notifyUnauthenticated(error: ApiError | InvalidResponseError): void {
    try {
      options.onUnauthenticated?.(error)
    } catch (callbackError) {
      // 回调自身的异常不覆盖原 401 错误，改为异步上报
      queueMicrotask(() => {
        throw callbackError
      })
    }
  }

  async function send(cid: string, request: ChatRequest, sendOptions: ChatSendOptions = {}): Promise<ChatStreamOutcome> {
    const external = sendOptions.signal
    if (external?.aborted) throw new AbortedError(external.reason)

    const url = `${baseUrl}${apiPath('/api/v1/courses/{cid}/chat', { cid })}`
    const headers = new Headers({ Accept: 'text/event-stream', 'Content-Type': 'application/json' })
    // 问答流用 Bearer（不是任务流的票据），令牌绝不进 URL（events.v1.md §1）
    const token = options.getAccessToken?.()
    if (token) headers.set('Authorization', `Bearer ${token}`)

    const timeoutMs = sendOptions.timeoutMs ?? defaultTimeoutMs
    const controller = new AbortController()
    let timedOut = false
    const onExternalAbort = (): void => controller.abort(external?.reason)
    external?.addEventListener('abort', onExternalAbort, { once: true })
    const timer = timers.setTimeout(() => {
      if (controller.signal.aborted) return
      timedOut = true
      controller.abort(new DOMException('请求超时', 'TimeoutError'))
    }, timeoutMs)
    const cancelledError = (): AbortedError | TimeoutError =>
      timedOut ? new TimeoutError(timeoutMs, controller.signal.reason) : new AbortedError(controller.signal.reason)

    let reader: ReadableStreamDefaultReader<Uint8Array> | undefined
    // 取消/终态/失败都要真正断开底层响应体（O14、Q6 第 3 条）
    const disconnect = (): void => {
      reader?.cancel(controller.signal.reason).catch(() => undefined)
    }
    controller.signal.addEventListener('abort', disconnect, { once: true })

    try {
      let response: Response
      try {
        response = await fetchImpl(url, {
          method: 'POST',
          headers,
          body: JSON.stringify(request),
          cache: 'no-store',
          signal: controller.signal,
        })
      } catch (cause) {
        if (controller.signal.aborted) throw cancelledError()
        throw new NetworkError(cause)
      }
      if (controller.signal.aborted) {
        response.body?.cancel(controller.signal.reason).catch(() => undefined)
        throw cancelledError()
      }

      // 开流前：先看状态码与 Content-Type，再决定是否进入事件解析（Q6 第 6 条）
      if (!response.ok) {
        const error = await errorFromResponse(response)
        // 401 表示会话失效：清会话由 H13 接线；读体失败（NetworkError）不作会话失效处理
        if (response.status === 401 && (error instanceof ApiError || error instanceof InvalidResponseError)) {
          notifyUnauthenticated(error)
        }
        throw error
      }
      const contentType = response.headers.get('Content-Type') ?? ''
      if (!EVENT_STREAM_CONTENT_TYPE.test(contentType)) {
        response.body?.cancel().catch(() => undefined)
        throw new InvalidResponseError(response.status, `响应 Content-Type 不是 text/event-stream：${contentType || '(缺失)'}`)
      }
      if (response.body === null) throw new InvalidResponseError(response.status, '事件流响应体为空')

      reader = response.body.getReader()
      if (controller.signal.aborted) disconnect()
      const decoder = new TextDecoder('utf-8')
      const parser = createSseParser({ maxLineLength: maxSseLineLength })
      let grammar = INITIAL_CHAT_GRAMMAR
      const onEvent = sendOptions.onEvent

      for (;;) {
        let chunk: ReadableStreamReadResult<Uint8Array>
        try {
          chunk = await reader.read()
        } catch (cause) {
          if (controller.signal.aborted) throw cancelledError()
          throw new ChatStreamInterruptedError('read_error', '读取事件流失败', { cause })
        }
        if (controller.signal.aborted) throw cancelledError()
        // 未收到 done / error 即 EOF：O15，不是成功（对比任务流的断线重连）
        if (chunk.done) throw new ChatStreamInterruptedError('eof', '事件流在 done / error 之前结束')

        let messages: SseMessage[]
        try {
          messages = parser.feed(decoder.decode(chunk.value, { stream: true }))
        } catch (cause) {
          const message = cause instanceof SseProtocolError ? cause.message : 'SSE 分帧失败'
          throw new ChatStreamInterruptedError('protocol', message, { cause })
        }

        // 同一批里终态之后再来事件也是文法违规（QA-23）：因此不提前 return，
        // 让状态机把后续事件判为 terminal 违规，整批处理完再交还终态。
        let outcome: ChatStreamOutcome | undefined
        for (const message of messages) {
          if (controller.signal.aborted) throw cancelledError()
          const parsed = parseChatEvent(message.event, message.data)
          if (parsed.kind === 'invalid') throw new ChatStreamInterruptedError('protocol', parsed.reason)
          const step = advanceChatGrammar(grammar, parsed.event)
          // 非法顺序（首条非 meta、二次 meta、done 之后又来事件等）同样是 O15
          if (!step.ok) throw new ChatStreamInterruptedError('protocol', step.reason)
          grammar = step.state

          const event = parsed.event
          switch (event.event) {
            case 'meta':
              onEvent?.({ kind: 'meta', data: event })
              break
            case 'delta':
              onEvent?.({ kind: 'delta', data: event })
              break
            case 'done':
              onEvent?.({ kind: 'done', data: event })
              outcome = { kind: 'done', final: event.final }
              break
            case 'error':
              onEvent?.({ kind: 'error', data: event })
              outcome = { kind: 'error', error: event.error }
              break
          }
        }
        if (outcome) return outcome
      }
    } finally {
      timers.clearTimeout(timer)
      external?.removeEventListener('abort', onExternalAbort)
      disconnect()
    }
  }

  return { send }
}

/** 开流前的非 2xx 响应转换为 B15 错误类型；Content-Type 不是 JSON 时不解析 HTML 错误页 */
async function errorFromResponse(response: Response): Promise<ApiError | InvalidResponseError | NetworkError> {
  const contentType = response.headers.get('Content-Type') ?? ''
  let text: string
  try {
    text = await response.text()
  } catch (cause) {
    return new NetworkError(cause)
  }
  if (!JSON_CONTENT_TYPE.test(contentType)) {
    return new InvalidResponseError(response.status, `错误响应 Content-Type 不是 JSON：${contentType || '(缺失)'}`)
  }
  let parsed: unknown
  try {
    parsed = JSON.parse(text)
  } catch (cause) {
    return new InvalidResponseError(response.status, '错误响应体不是 JSON', cause)
  }
  if (!isErrorBody(parsed)) return new InvalidResponseError(response.status, '错误响应体不是契约 Error')
  return new ApiError(response.status, parsed)
}

// 契约 ErrorCode 的运行时副本（B15 的同名常量未导出）；类型断言保证与契约双向一致
const ERROR_CODES = [
  'UNAUTHENTICATED',
  'COURSE_FORBIDDEN',
  'ROLE_FORBIDDEN',
  'NOT_FOUND',
  'GRAPH_NOT_PUBLISHED',
  'UNSUPPORTED_FORMAT',
  'FILE_TOO_LARGE',
  'VALIDATION_ERROR',
  'CYCLE_DETECTED',
  'DANGLING_ENDPOINT',
  'DUPLICATE_RELATION',
  'NODE_LOCKED',
  'TASK_NOT_CANCELLABLE',
  'PUBLISH_BLOCKED',
  'RATE_LIMITED',
  'LLM_UNAVAILABLE',
  'DOCUMENT_UNREADABLE',
  'EXTRACTION_INCOMPLETE',
  'STORAGE_UNAVAILABLE',
  'INTERNAL_ERROR',
  'TASK_ATTEMPTS_EXHAUSTED',
  'PUBLISH_IN_PROGRESS',
  'COURSE_BUSY',
  'BUDGET_EXCEEDED',
  'DOCUMENT_NOT_DELETABLE',
  'REVISION_CONFLICT',
  'USERNAME_TAKEN',
  'MODEL_CONFIG_REQUIRED',
] as const satisfies readonly components['schemas']['ErrorCode'][]
type MissingErrorCode = Exclude<components['schemas']['ErrorCode'], (typeof ERROR_CODES)[number]>
const errorCodesComplete: [MissingErrorCode] extends [never] ? true : MissingErrorCode = true
void errorCodesComplete
const ERROR_CODE_SET: ReadonlySet<string> = new Set(ERROR_CODES)

function isErrorBody(value: unknown): value is components['schemas']['Error'] {
  return (
    isPlainObject(value) &&
    typeof value.code === 'string' &&
    ERROR_CODE_SET.has(value.code) &&
    typeof value.message === 'string' &&
    (value.details === undefined || isPlainObject(value.details))
  )
}
