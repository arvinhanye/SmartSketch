import type { components } from '../../../contracts/v1/generated/typescript/openapi'
import type { CourseRequestScope } from '../stores/course'
import {
  AbortedError,
  ApiError,
  InvalidResponseError,
  NetworkError,
  apiPath,
  type ErrorCode,
  type FetchLike,
  type HttpClient,
} from './http'

/**
 * 前端任务进度流客户端（C12）。
 *
 * - 时序语义以 `src/contracts/events.v1.md` §2、§4 与 `specs/task-processing.md` §7 为准：
 *   每个连接恰好以一条结束事件收尾（`stage = awaiting_review`，或 `done` / `error` / `cancelled`），
 *   客户端收到后主动关闭，不为等待 `done` 保持或重建连接。
 * - 鉴权按 `specs/identity-access.md` §5：先经 B15 客户端（带 Bearer）申领一次性票据，
 *   再以 `?ticket=` 连接；事件流请求不带 `Authorization`，访问令牌绝不进 URL。
 * - 不用 `EventSource`（其自动重连会带着已用票据必然 401）：`fetch` + `ReadableStream`
 *   自行解析 SSE。出错即关闭 → 重新申领票据 → 新建连接，退避 1、2、4… 秒，上限 30 秒；
 *   连续失败 5 次降级为每 5 秒轮询 `GET /api/v1/tasks/{tid}`。默认值可调，非契约。
 * - 订阅绑定课程作用域：作用域失效（切课/离开课程）即关闭，旧课程的迟到事件不投递。
 * - 只放 HTTP/SSE 调用逻辑；组件经 composable 订阅，并在卸载时 `close()`。
 */

export type TaskEvent = components['schemas']['TaskEvent']
export type TaskStageEvent = components['schemas']['TaskStageEvent']
export type TaskDoneEvent = components['schemas']['TaskDoneEvent']
export type TaskErrorEvent = components['schemas']['TaskErrorEvent']
export type TaskCancelledEvent = components['schemas']['TaskCancelledEvent']
export type TaskStage = components['schemas']['TaskStage']
export type Task = components['schemas']['Task']
type ErrorBody = components['schemas']['Error']
type TaskCounts = components['schemas']['TaskCounts']

/** 契约中的任务事件名（`events.v1.md` §2） */
export type TaskEventName = 'stage' | 'done' | 'error' | 'cancelled'

// ---------------------------------------------------------------- SSE 解析

export interface SseMessage {
  /** `event:` 字段；未给出时为 `message` */
  event: string
  /** 多行 `data:` 以 `\n` 连接 */
  data: string
  lastEventId: string
}

export interface SseParserOptions {
  /** 单行（未遇到行结束前）最多缓冲的字符数，超出抛 `SseProtocolError` */
  maxLineLength?: number
}

export const DEFAULT_MAX_SSE_LINE_LENGTH = 1_000_000

export class SseProtocolError extends Error {
  constructor(message: string) {
    super(message)
    this.name = 'SseProtocolError'
  }
}

export interface SseParser {
  /** 输入一段已解码的文本，返回其中完整的事件；半条事件留待后续输入 */
  feed(text: string): SseMessage[]
}

/**
 * 按 HTML Living Standard「event stream interpretation」解析：
 * 行结束可为 `\r\n`、`\n` 或单独的 `\r`（跨块的 `\r` + `\n` 只算一次）；
 * `:` 开头为注释（如 `:ping`）；空行派发事件，无 `data` 的事件不派发；
 * 流末未以空行结束的事件由调用方丢弃（不再 feed 即可）。
 */
export function createSseParser(options: SseParserOptions = {}): SseParser {
  const maxLineLength = options.maxLineLength ?? DEFAULT_MAX_SSE_LINE_LENGTH
  let buffer = ''
  // 上一块以 \r 结尾：若下一个字符是 \n，它属于同一个行结束
  let skipLeadingLf = false
  let eventType = ''
  let data = ''
  let lastEventId = ''

  function processLine(line: string, out: SseMessage[]): void {
    if (line === '') {
      if (data !== '') {
        out.push({ event: eventType || 'message', data: data.endsWith('\n') ? data.slice(0, -1) : data, lastEventId })
      }
      data = ''
      eventType = ''
      return
    }
    if (line.startsWith(':')) return
    const colon = line.indexOf(':')
    const field = colon === -1 ? line : line.slice(0, colon)
    let value = colon === -1 ? '' : line.slice(colon + 1)
    if (value.startsWith(' ')) value = value.slice(1)
    switch (field) {
      case 'event':
        eventType = value
        break
      case 'data':
        data += `${value}\n`
        break
      case 'id':
        if (!value.includes('\0')) lastEventId = value
        break
      default:
        // retry 与未知字段忽略：重连节奏由本客户端决定
        break
    }
  }

  return {
    feed(text) {
      const out: SseMessage[] = []
      buffer += text
      let pos = 0
      for (;;) {
        if (skipLeadingLf) {
          if (pos >= buffer.length) break
          if (buffer.charCodeAt(pos) === 10) pos += 1
          skipLeadingLf = false
        }
        let end = -1
        for (let i = pos; i < buffer.length; i += 1) {
          const c = buffer.charCodeAt(i)
          if (c === 10 || c === 13) {
            end = i
            break
          }
        }
        if (end === -1) break
        const line = buffer.slice(pos, end)
        if (buffer.charCodeAt(end) === 13) skipLeadingLf = true
        pos = end + 1
        processLine(line, out)
      }
      buffer = buffer.slice(pos)
      if (buffer.length > maxLineLength) throw new SseProtocolError(`SSE 单行超过 ${maxLineLength} 字符`)
      return out
    },
  }
}

// ---------------------------------------------------------------- 事件校验

const PROCESSING_STAGES = ['queued', 'parsing', 'extracting', 'merging', 'persisting', 'awaiting_review'] as const
const ALL_STAGES = [...PROCESSING_STAGES, 'completed', 'failed', 'cancelled'] as const satisfies readonly TaskStage[]
type MissingStage = Exclude<TaskStage, (typeof ALL_STAGES)[number]>
const stagesComplete: [MissingStage] extends [never] ? true : MissingStage = true
void stagesComplete

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
] as const satisfies readonly ErrorCode[]
type MissingErrorCode = Exclude<ErrorCode, (typeof ERROR_CODES)[number]>
const errorCodesComplete: [MissingErrorCode] extends [never] ? true : MissingErrorCode = true
void errorCodesComplete

const PROCESSING_STAGE_SET: ReadonlySet<string> = new Set(PROCESSING_STAGES)
const STAGE_SET: ReadonlySet<string> = new Set(ALL_STAGES)
const ERROR_CODE_SET: ReadonlySet<string> = new Set(ERROR_CODES)
const EVENT_NAMES: ReadonlySet<string> = new Set<TaskEventName>(['stage', 'done', 'error', 'cancelled'])
/** 处理期连接的结束：`awaiting_review` 与三个终态 */
const END_STAGES: ReadonlySet<string> = new Set(['awaiting_review', 'completed', 'failed', 'cancelled'])
/** `specs/task-processing.md` §1 的固定进度 */
const FIXED_PROGRESS: Readonly<Record<string, number>> = { queued: 0, awaiting_review: 0.95, completed: 1 }
const PROGRESS_EPSILON = 1e-9

function isPlainObject(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function isProgress(value: unknown): value is number {
  return typeof value === 'number' && Number.isFinite(value) && value >= 0 && value <= 1
}

function hasFixedProgress(stage: string, progress: number): boolean {
  const fixed = FIXED_PROGRESS[stage]
  return fixed === undefined || Math.abs(progress - fixed) <= PROGRESS_EPSILON
}

function isOptionalCount(value: unknown): boolean {
  return value === undefined || (typeof value === 'number' && Number.isInteger(value) && value >= 0)
}

function isCounts(value: unknown): value is TaskCounts {
  if (!isPlainObject(value)) return false
  const keys: Array<keyof TaskCounts> = ['chunks_done', 'chunks_total', 'kp_count', 'relation_count', 'chunks_failed']
  return keys.every((key) => isOptionalCount(value[key]))
}

function isErrorBody(value: unknown): value is ErrorBody {
  return (
    isPlainObject(value) &&
    typeof value.code === 'string' &&
    ERROR_CODE_SET.has(value.code) &&
    typeof value.message === 'string' &&
    (value.details === undefined || isPlainObject(value.details))
  )
}

/** 事件与快照共有的可选字段 */
function hasValidOptionals(value: Record<string, unknown>): boolean {
  if (value.counts !== undefined && !isCounts(value.counts)) return false
  if (value.elapsed_ms !== undefined && !(typeof value.elapsed_ms === 'number' && value.elapsed_ms >= 0)) return false
  if (value.cancel_requested !== undefined && typeof value.cancel_requested !== 'boolean') return false
  return true
}

function eventMatches(name: TaskEventName, value: Record<string, unknown>): boolean {
  const stage = value.stage
  const progress = value.progress
  if (typeof stage !== 'string' || !isProgress(progress) || !hasValidOptionals(value)) return false
  switch (name) {
    case 'stage':
      return (
        PROCESSING_STAGE_SET.has(stage) && typeof value.cancel_requested === 'boolean' && hasFixedProgress(stage, progress)
      )
    case 'done':
      return stage === 'completed' && progress === 1
    case 'error':
      return stage === 'failed' && isErrorBody(value.error)
    case 'cancelled':
      return stage === 'cancelled' && value.cancel_requested === true
  }
}

export type ParsedTaskEvent =
  | { kind: 'event'; event: TaskEventName; data: TaskEvent; final: boolean }
  /** 未知事件名（向前兼容）或不属于本任务的事件：丢弃 */
  | { kind: 'ignored' }
  /** 已知事件名但载荷不符合契约：协议错误 */
  | { kind: 'invalid'; reason: string }

/** 按 `TaskEvent` 各分支对单条 SSE 事件做运行时校验；事件名必须与 `stage` 对应 */
export function parseTaskEvent(name: string, data: string, taskId: string): ParsedTaskEvent {
  if (!EVENT_NAMES.has(name)) return { kind: 'ignored' }
  const eventName = name as TaskEventName
  let value: unknown
  try {
    value = JSON.parse(data)
  } catch {
    return { kind: 'invalid', reason: `事件 ${name} 的 data 不是 JSON` }
  }
  if (!isPlainObject(value) || typeof value.task_id !== 'string') {
    return { kind: 'invalid', reason: `事件 ${name} 的 data 缺少 task_id` }
  }
  if (value.task_id !== taskId) return { kind: 'ignored' }
  if (!eventMatches(eventName, value)) return { kind: 'invalid', reason: `事件 ${name} 的载荷不符合契约` }
  const event = value as TaskEvent
  return { kind: 'event', event: eventName, data: event, final: END_STAGES.has(event.stage) }
}

/** 校验 `GET /api/v1/tasks/{tid}` 快照；课程不符单独报告以便按不可恢复处理 */
function checkTaskSnapshot(value: unknown, taskId: string, courseId: string): Task | 'invalid' | 'foreign' {
  if (!isPlainObject(value) || value.id !== taskId) return 'invalid'
  if (value.course_id !== courseId) return 'foreign'
  const { stage, progress } = value
  if (typeof stage !== 'string' || !STAGE_SET.has(stage) || !isProgress(progress)) return 'invalid'
  if (typeof value.cancel_requested !== 'boolean' || !hasValidOptionals(value)) return 'invalid'
  if (!hasFixedProgress(stage, progress)) return 'invalid'
  if (stage === 'failed' ? !isErrorBody(value.error) : value.error !== undefined && value.error !== null) return 'invalid'
  if (stage === 'cancelled' && value.cancel_requested !== true) return 'invalid'
  return value as Task
}

// ---------------------------------------------------------------- 订阅

export type TaskStreamUpdate =
  | { source: 'stream'; event: TaskEventName; data: TaskEvent; final: boolean }
  | { source: 'poll'; task: Task; final: boolean }

/** `connecting`：申领票据/建连；`streaming`：已开流；`reconnecting`：退避等待；`polling`：已降级轮询 */
export type TaskStreamState = 'connecting' | 'streaming' | 'reconnecting' | 'polling' | 'closed'

export type TaskStreamCloseReason =
  /** 收到结束事件（或轮询到 `awaiting_review` / 终态）；`stage` 为该结束状态 */
  | { kind: 'finished'; stage: TaskStage }
  /** 调用方 `close()`（如组件卸载） */
  | { kind: 'unsubscribed' }
  /** 课程作用域失效（切课、离开课程） */
  | { kind: 'scope_invalidated' }
  /** 不可恢复：401/403/404、快照课程不符等；`error` 为 B15 错误类型或 `Error` */
  | { kind: 'fatal'; error: unknown }

export interface TaskStreamHandlers {
  onUpdate(update: TaskStreamUpdate): void
  onState?(state: TaskStreamState): void
  /** 恰好调用一次 */
  onClose?(reason: TaskStreamCloseReason): void
}

export interface TaskSubscription {
  /** 关闭连接并停止重连/轮询；幂等 */
  close(): void
  readonly closed: boolean
}

export interface TaskStreamTimers {
  setTimeout(fn: () => void, ms: number): unknown
  clearTimeout(handle: unknown): void
}

export interface TaskStreamPolicy {
  /** 第一次失败后的退避 */
  initialBackoffMs: number
  /** 退避上限 */
  maxBackoffMs: number
  /** 连续失败达到此次数后降级为轮询 */
  maxConsecutiveFailures: number
  pollIntervalMs: number
  /** 开流后超过此时长未收到任何字节（含 `:ping`，服务端 15 秒一次）视为断线 */
  idleTimeoutMs: number
}

/** `specs/task-processing.md` §7 的建议默认值（非契约，可调） */
export const DEFAULT_TASK_STREAM_POLICY: Readonly<TaskStreamPolicy> = Object.freeze({
  initialBackoffMs: 1_000,
  maxBackoffMs: 30_000,
  maxConsecutiveFailures: 5,
  pollIntervalMs: 5_000,
  idleTimeoutMs: 45_000,
})

export interface TaskEventsClientOptions {
  /** B15 客户端（带 Bearer）：申领票据与轮询快照 */
  client: HttpClient
  /** 事件流请求用的 fetch；默认全局 fetch */
  fetch?: FetchLike
  /** API 源，应与 B15 客户端一致；默认同源 */
  baseUrl?: string
  timers?: TaskStreamTimers
  policy?: Partial<TaskStreamPolicy>
  /** 回调异常的上报；默认异步重新抛出 */
  reportError?: (error: unknown) => void
}

export interface TaskEventsClient {
  subscribe(taskId: string, scope: CourseRequestScope, handlers: TaskStreamHandlers): TaskSubscription
}

/** 单次连接的结局：流失败（可重试）或不可恢复 */
class FatalError extends Error {
  constructor(readonly error: unknown) {
    super('不可恢复的任务流错误')
  }
}

const FATAL_STATUSES: ReadonlySet<number> = new Set([401, 403, 404])

function isFatalHttpError(error: unknown): boolean {
  return (error instanceof ApiError || error instanceof InvalidResponseError) && FATAL_STATUSES.has(error.status)
}

export function createTaskEventsClient(options: TaskEventsClientOptions): TaskEventsClient {
  const fetchImpl: FetchLike = options.fetch ?? ((input, init) => globalThis.fetch(input, init))
  const baseUrl = (options.baseUrl ?? '').replace(/\/+$/, '')
  const timers: TaskStreamTimers = options.timers ?? {
    setTimeout: (fn, ms) => globalThis.setTimeout(fn, ms),
    clearTimeout: (handle) => globalThis.clearTimeout(handle as ReturnType<typeof globalThis.setTimeout>),
  }
  const policy: TaskStreamPolicy = { ...DEFAULT_TASK_STREAM_POLICY, ...options.policy }
  const reportError =
    options.reportError ??
    ((error: unknown) =>
      queueMicrotask(() => {
        throw error
      }))

  function subscribe(taskId: string, scope: CourseRequestScope, handlers: TaskStreamHandlers): TaskSubscription {
    // 订阅生命周期：close()、作用域失效或结束时中止，连带取消在途请求与读流
    const lifetime = new AbortController()
    let closed = false
    const activeTimers = new Set<unknown>()

    function safely(fn: () => void): void {
      try {
        fn()
      } catch (error) {
        reportError(error)
      }
    }

    function setState(state: TaskStreamState): void {
      if (!closed || state === 'closed') safely(() => handlers.onState?.(state))
    }

    function close(reason: TaskStreamCloseReason): void {
      if (closed) return
      closed = true
      scope.signal.removeEventListener('abort', onScopeAbort)
      for (const handle of activeTimers) timers.clearTimeout(handle)
      activeTimers.clear()
      lifetime.abort(new AbortedError())
      setState('closed')
      safely(() => handlers.onClose?.(reason))
    }

    function onScopeAbort(): void {
      close({ kind: 'scope_invalidated' })
    }

    /** 作用域仍有效且未关闭时投递，否则关闭并丢弃 */
    function deliver(update: TaskStreamUpdate): boolean {
      if (closed) return false
      if (!scope.isCurrent()) {
        close({ kind: 'scope_invalidated' })
        return false
      }
      safely(() => handlers.onUpdate(update))
      return !closed
    }

    function schedule(fn: () => void, ms: number): unknown {
      const handle = timers.setTimeout(() => {
        activeTimers.delete(handle)
        fn()
      }, ms)
      activeTimers.add(handle)
      return handle
    }

    function cancelTimer(handle: unknown): void {
      activeTimers.delete(handle)
      timers.clearTimeout(handle)
    }

    /** 等待 ms；关闭时立即返回（调用方随后检查 closed） */
    function sleep(ms: number): Promise<void> {
      return new Promise((resolve) => {
        if (closed) return resolve()
        const handle = schedule(done, ms)
        function done(): void {
          lifetime.signal.removeEventListener('abort', onAbort)
          resolve()
        }
        function onAbort(): void {
          cancelTimer(handle)
          resolve()
        }
        lifetime.signal.addEventListener('abort', onAbort, { once: true })
      })
    }

    /** 一次连接：返回 true 表示收到结束事件；false 表示本次连接失败（可重试） */
    async function connectOnce(onDelivered: () => void): Promise<boolean> {
      let ticket: string
      try {
        const issued = await options.client.request('post', '/api/v1/tasks/{tid}/event-ticket', {
          params: { tid: taskId },
          signal: lifetime.signal,
        })
        if (!isPlainObject(issued) || typeof issued.ticket !== 'string' || issued.ticket === '') return false
        ticket = issued.ticket
      } catch (error) {
        if (closed) return false
        if (isFatalHttpError(error)) throw new FatalError(error)
        return false
      }
      if (closed) return false

      const attempt = new AbortController()
      const abortAttempt = () => attempt.abort(lifetime.signal.reason)
      lifetime.signal.addEventListener('abort', abortAttempt, { once: true })
      let reader: ReadableStreamDefaultReader<Uint8Array> | undefined
      let idleTimer: unknown
      const stopReading = () => {
        reader?.cancel().catch(() => undefined)
      }
      attempt.signal.addEventListener('abort', stopReading, { once: true })
      const armIdle = () => {
        if (idleTimer !== undefined) cancelTimer(idleTimer)
        idleTimer = schedule(() => attempt.abort(new Error('任务流空闲超时')), policy.idleTimeoutMs)
      }

      try {
        const url = `${baseUrl}${apiPath('/api/v1/tasks/{tid}/events', { tid: taskId })}?ticket=${encodeURIComponent(ticket)}`
        let response: Response
        try {
          // 不带 Authorization：该端点只认票据（identity-access §5.2）
          response = await fetchImpl(url, {
            method: 'GET',
            headers: { Accept: 'text/event-stream' },
            cache: 'no-store',
            signal: attempt.signal,
          })
        } catch {
          return false
        }
        if (closed || attempt.signal.aborted) {
          response.body?.cancel().catch(() => undefined)
          return false
        }
        if (!response.ok) {
          const error = await errorFromResponse(response)
          if (FATAL_STATUSES.has(response.status) && response.status !== 401) throw new FatalError(error)
          // 401：票据可能在申领与建连之间过期，重新申领即可；账号停用会在下次申领时以 401 终止
          return false
        }
        const contentType = response.headers.get('Content-Type') ?? ''
        if (!/^text\/event-stream\b/i.test(contentType) || response.body === null) {
          response.body?.cancel().catch(() => undefined)
          return false
        }

        reader = response.body.getReader()
        if (attempt.signal.aborted) stopReading()
        setState('streaming')
        armIdle()
        const decoder = new TextDecoder('utf-8')
        const parser = createSseParser()
        for (;;) {
          let chunk: ReadableStreamReadResult<Uint8Array>
          try {
            chunk = await reader.read()
          } catch {
            return false
          }
          if (closed || attempt.signal.aborted) return false
          if (chunk.done) return false // 未收到结束事件即 EOF：断线
          armIdle()
          let messages: SseMessage[]
          try {
            messages = parser.feed(decoder.decode(chunk.value, { stream: true }))
          } catch {
            return false
          }
          for (const message of messages) {
            const parsed = parseTaskEvent(message.event, message.data, taskId)
            if (parsed.kind === 'ignored') continue
            if (parsed.kind === 'invalid') return false
            if (!deliver({ source: 'stream', event: parsed.event, data: parsed.data, final: parsed.final })) return false
            onDelivered()
            if (parsed.final) {
              close({ kind: 'finished', stage: parsed.data.stage })
              return true
            }
          }
        }
      } finally {
        if (idleTimer !== undefined) cancelTimer(idleTimer)
        lifetime.signal.removeEventListener('abort', abortAttempt)
        attempt.abort()
      }
    }

    async function poll(): Promise<void> {
      setState('polling')
      while (!closed) {
        let value: unknown
        let fetched = false
        try {
          value = await options.client.request('get', '/api/v1/tasks/{tid}', {
            params: { tid: taskId },
            signal: lifetime.signal,
          })
          fetched = true
        } catch (error) {
          if (closed) return
          if (isFatalHttpError(error)) return close({ kind: 'fatal', error })
          // 瞬时错误（网络、超时、5xx）：下个周期再试
        }
        if (closed) return
        if (fetched) {
          const task = checkTaskSnapshot(value, taskId, scope.courseId)
          if (task === 'foreign') {
            return close({ kind: 'fatal', error: new Error('任务快照不属于当前课程') })
          }
          if (task !== 'invalid') {
            const final = END_STAGES.has(task.stage)
            if (!deliver({ source: 'poll', task, final })) return
            if (final) return close({ kind: 'finished', stage: task.stage })
          }
        }
        await sleep(policy.pollIntervalMs)
      }
    }

    async function run(): Promise<void> {
      if (scope.signal.aborted || !scope.isCurrent()) return close({ kind: 'scope_invalidated' })
      scope.signal.addEventListener('abort', onScopeAbort, { once: true })
      let failures = 0
      while (!closed) {
        setState('connecting')
        let delivered = false
        let finished: boolean
        try {
          finished = await connectOnce(() => {
            delivered = true
          })
        } catch (error) {
          if (error instanceof FatalError) return close({ kind: 'fatal', error: error.error })
          throw error
        }
        if (finished || closed) return
        failures = delivered ? 1 : failures + 1
        if (failures >= policy.maxConsecutiveFailures) return poll()
        setState('reconnecting')
        await sleep(Math.min(policy.initialBackoffMs * 2 ** (failures - 1), policy.maxBackoffMs))
      }
    }

    void run().catch((error: unknown) => close({ kind: 'fatal', error }))

    return {
      close: () => close({ kind: 'unsubscribed' }),
      get closed() {
        return closed
      },
    }
  }

  return { subscribe }
}

/** 事件流的非 2xx 响应转换为 B15 错误类型，供调用方按 `instanceof` / `code` 分支 */
async function errorFromResponse(response: Response): Promise<ApiError | InvalidResponseError | NetworkError> {
  let text: string
  try {
    text = await response.text()
  } catch (cause) {
    return new NetworkError(cause)
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
