import { describe, expect, it } from 'vitest'
import {
  AbortedError,
  ApiError,
  InvalidResponseError,
  NetworkError,
  TimeoutError,
  type FetchLike,
} from '../../src/frontend/src/api/http'
import {
  DEFAULT_CHAT_TIMEOUT_MS,
  INITIAL_CHAT_GRAMMAR,
  ChatStreamInterruptedError,
  advanceChatGrammar,
  createChatStreamClient,
  parseChatEvent,
  type ChatEvent,
  type ChatMetaEvent,
  type ChatSendOptions,
  type ChatStreamClientOptions,
  type ChatStreamEvent,
  type ChatStreamTimers,
} from '../../src/frontend/src/api/chatStream'

/**
 * J08 问答 fetch 流客户端。
 *
 * 断言口径按验收原子清单：「UTF-8跨字节、CRLF、多行data、空帧、异常EOF、取消；不自动重放提问」，
 * 加 `events.v1.md` §3 的事件文法（Q2）与 §3「开流前错误」：
 * - `parseChatEvent` / `advanceChatGrammar` 是纯函数，直接钉住文法与载荷校验；
 * - 流级用例复用 C12 的手写假 fetch / 可控假 SSE 流风格。
 */

const CID = 'c1'
const REQUEST_ID = '01J8ZQ3N6T7W8X9Y0ZABCDEF12'
const MESSAGE = '什么是栈？'

// ---------------------------------------------------------------- 夹具

const META_ANSWERED = {
  event: 'meta',
  status: 'answered',
  retrieved: 3,
  graph_version: 3,
  request_id: REQUEST_ID,
} as ChatMetaEvent

const META_NOT_COVERED = {
  event: 'meta',
  status: 'not_covered',
  retrieved: 0,
  graph_version: 3,
  request_id: REQUEST_ID,
} as ChatMetaEvent

const DELTA_FIRST = { event: 'delta', delta: '栈是一种' }
const DELTA_SECOND = { event: 'delta', delta: '后进先出的线性表[1]。' }

const ANSWERED_FINAL = {
  status: 'answered',
  answer: '栈是一种后进先出的线性表[1]。',
  citations: [
    {
      index: 1,
      chunk_id: 'c_77',
      document_id: 'd_03',
      section_path: '第3章 > 3.1 栈',
      page: 52,
      text: '栈是限定仅在表尾进行插入和删除操作的线性表。',
    },
  ],
  related_kp_ids: ['kp_12'],
  latency_ms: 6200,
  graph_version: 3,
  request_id: REQUEST_ID,
}

const NOT_COVERED_FINAL = {
  status: 'not_covered',
  answer: '课程资料中没有找到与这个问题相关的内容。',
  citations: [],
  reason: 'no_retrieval_hit',
  latency_ms: 800,
  graph_version: 3,
  request_id: REQUEST_ID,
}

const DONE_ANSWERED = { event: 'done', final: ANSWERED_FINAL }
const DONE_NOT_COVERED = { event: 'done', final: NOT_COVERED_FINAL }
const ERROR_EVENT = {
  event: 'error',
  error: {
    code: 'LLM_UNAVAILABLE',
    message: '回答生成中断，请稍后重试。',
    details: { reason: 'stream_interrupted', request_id: REQUEST_ID },
  },
}

function frame(event: string, data: unknown): string {
  return `event: ${event}\ndata: ${JSON.stringify(data)}\n\n`
}

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })
}

function sseResponse(body: BodyInit | null, contentType = 'text/event-stream; charset=utf-8'): Response {
  return new Response(body, { status: 200, headers: { 'Content-Type': contentType } })
}

/** 可控的 SSE 响应：逐块推送字节、结束，或被客户端取消时记录 */
function sseStream() {
  const encoder = new TextEncoder()
  let controller!: ReadableStreamDefaultController<Uint8Array>
  const state = { cancelled: false, ended: false }
  const body = new ReadableStream<Uint8Array>({
    start(c) {
      controller = c
    },
    cancel() {
      state.cancelled = true
    },
  })
  return {
    state,
    response: sseResponse(body),
    push(chunk: string | Uint8Array) {
      if (state.cancelled || state.ended) return
      controller.enqueue(typeof chunk === 'string' ? encoder.encode(chunk) : chunk)
    },
    end() {
      if (state.cancelled || state.ended) return
      state.ended = true
      controller.close()
    },
  }
}

type Stream = ReturnType<typeof sseStream>

interface Call {
  url: string
  init: RequestInit
}

/** 假 fetch：每次问答请求依次消费 `streams` 队首；默认不准备任何响应即报错 */
function fakeFetch() {
  const calls: Call[] = []
  const streams: Array<Stream | Response | (() => Response | Promise<Response>)> = []
  const fetch: FetchLike = async (input, init = {}) => {
    calls.push({ url: String(input), init })
    const next = streams.shift()
    if (!next) throw new TypeError('没有准备好的问答响应')
    if (next instanceof Response) return next
    if (typeof next === 'function') return next()
    return next.response
  }
  return { calls, streams, fetch }
}

/** 假计时器：记录请求的延迟，由测试决定何时触发（照抄 C12 的注入风格） */
function fakeTimers() {
  let nextId = 1
  const pending = new Map<number, { fn: () => void; ms: number }>()
  const timers: ChatStreamTimers = {
    setTimeout(fn, ms) {
      const id = nextId++
      pending.set(id, { fn, ms })
      return id
    },
    clearTimeout(handle) {
      pending.delete(handle as number)
    },
  }
  return {
    timers,
    pendingDelays: () => [...pending.values()].map((t) => t.ms),
    fire(ms: number) {
      const matches = [...pending.entries()].filter(([, t]) => t.ms === ms)
      if (matches.length !== 1) throw new Error(`期望恰有一个 ${ms}ms 计时器，实际 ${JSON.stringify(this.pendingDelays())}`)
      const [id, t] = matches[0]!
      pending.delete(id)
      t.fn()
    },
  }
}

async function flush(rounds = 20): Promise<void> {
  for (let i = 0; i < rounds; i += 1) await new Promise<void>((resolve) => setTimeout(resolve, 0))
}

interface Capture<T> {
  status: 'pending' | 'fulfilled' | 'rejected'
  value?: T
  error?: unknown
}

/** 立即挂上处理函数，避免失败被当成 unhandled rejection */
function capture<T>(promise: Promise<T>): Capture<T> {
  const state: Capture<T> = { status: 'pending' }
  promise.then(
    (value) => {
      state.status = 'fulfilled'
      state.value = value
    },
    (error) => {
      state.status = 'rejected'
      state.error = error
    },
  )
  return state
}

function setup(clientOptions: Partial<ChatStreamClientOptions> = {}) {
  const backend = fakeFetch()
  const clock = fakeTimers()
  const events: ChatStreamEvent[] = []
  const expired: unknown[] = []
  const client = createChatStreamClient({
    fetch: backend.fetch,
    baseUrl: 'http://api.test',
    getAccessToken: () => 'secret-jwt',
    onUnauthenticated: (error) => expired.push(error),
    timers: clock.timers,
    ...clientOptions,
  })
  const send = (options: ChatSendOptions = {}) =>
    client.send(CID, { question: MESSAGE }, { onEvent: (event) => events.push(event), ...options })
  return { backend, clock, events, expired, client, send }
}

/** 建流并推入分片，返回句柄供用例继续推进/结束 */
async function start(chunks: Array<string | Uint8Array> = [], options: ChatSendOptions = {}) {
  const t = setup()
  const stream = sseStream()
  t.backend.streams.push(stream)
  const pending = capture(t.send(options))
  await flush()
  for (const chunk of chunks) {
    stream.push(chunk)
    await flush(2)
  }
  await flush()
  return { ...t, stream, pending }
}

// ---------------------------------------------------------------- 载荷校验（纯函数）

describe('J08 事件载荷校验', () => {
  it('四种合法载荷通过，且事件名与 data.event 一致', () => {
    const cases: Array<[string, unknown]> = [
      ['meta', META_ANSWERED],
      ['meta', META_NOT_COVERED],
      ['delta', DELTA_FIRST],
      ['done', DONE_ANSWERED],
      ['done', DONE_NOT_COVERED],
      ['error', ERROR_EVENT],
    ]
    for (const [name, data] of cases) {
      const parsed = parseChatEvent(name, JSON.stringify(data))
      expect(parsed, name).toEqual({ kind: 'event', event: data })
    }
  })

  it('未知事件名、坏 JSON、非对象 data 都是协议错误（不向前兼容）', () => {
    expect(parseChatEvent('message', '{}')).toMatchObject({ kind: 'invalid' })
    expect(parseChatEvent('progress2', '{}')).toMatchObject({ kind: 'invalid' })
    expect(parseChatEvent('delta', '{not json')).toMatchObject({ kind: 'invalid' })
    expect(parseChatEvent('delta', '[1]')).toMatchObject({ kind: 'invalid' })
    expect(parseChatEvent('delta', '{}')).toMatchObject({ kind: 'invalid' })
  })

  it('事件名与 data.event 不一致是协议错误', () => {
    expect(parseChatEvent('delta', JSON.stringify(DELTA_FIRST))).toMatchObject({ kind: 'event' })
    expect(parseChatEvent('error', JSON.stringify(DELTA_FIRST))).toMatchObject({ kind: 'invalid' })
  })

  it.each([
    ['data 为 {}', 'meta', {}],
    ['meta 缺 graph_version', 'meta', { ...META_ANSWERED, graph_version: undefined }],
    ['meta 缺 request_id', 'meta', { ...META_ANSWERED, request_id: '' }],
    ['meta status 不在闭集', 'meta', { ...META_ANSWERED, status: 'pending' }],
    ['meta retrieved 非整数', 'meta', { ...META_ANSWERED, retrieved: 1.5 }],
    ['not_covered 的 meta 带 retrieved', 'meta', { ...META_NOT_COVERED, retrieved: 2 }],
    ['answered 的 meta retrieved 为 0', 'meta', { ...META_ANSWERED, retrieved: 0 }],
    ['delta 为空串', 'delta', { event: 'delta', delta: '' }],
    ['delta 缺 delta', 'delta', { event: 'delta' }],
    ['answered 的 final 无引用', 'done', { event: 'done', final: { ...ANSWERED_FINAL, citations: [] } }],
    ['not_covered 的 final 有引用', 'done', { event: 'done', final: { ...NOT_COVERED_FINAL, citations: ANSWERED_FINAL.citations } }],
    ['not_covered 的 final 缺 reason', 'done', { event: 'done', final: { ...NOT_COVERED_FINAL, reason: 'nope' } }],
    ['引用不可定位', 'done', { event: 'done', final: { ...ANSWERED_FINAL, citations: [{ index: 1, chunk_id: 'c1', document_id: 'd1', text: 't' }] } }],
    ['引用缺 text', 'done', { event: 'done', final: { ...ANSWERED_FINAL, citations: [{ index: 1, chunk_id: 'c1', document_id: 'd1', page: 3 }] } }],
    ['error 码不在闭集', 'error', { event: 'error', error: { code: 'NOPE', message: 'x', details: { request_id: REQUEST_ID } } }],
    ['LLM_UNAVAILABLE 缺 reason', 'error', { event: 'error', error: { code: 'LLM_UNAVAILABLE', message: 'x', details: { request_id: REQUEST_ID } } }],
    ['BUDGET_EXCEEDED 带 reason', 'error', { event: 'error', error: { code: 'BUDGET_EXCEEDED', message: 'x', details: { request_id: REQUEST_ID, reason: 'timeout' } } }],
    ['缺 details.request_id', 'error', { event: 'error', error: { code: 'INTERNAL_ERROR', message: 'x', details: {} } }],
    ['缺 error.message', 'error', { event: 'error', error: { code: 'INTERNAL_ERROR', details: { request_id: REQUEST_ID } } }],
  ] as Array<[string, string, unknown]>)('%s 被拒绝', (_label, name, data) => {
    expect(parseChatEvent(name, JSON.stringify(data))).toMatchObject({ kind: 'invalid' })
  })

  it('四码错误中只有 LLM_UNAVAILABLE 带 reason', () => {
    for (const code of ['BUDGET_EXCEEDED', 'STORAGE_UNAVAILABLE', 'INTERNAL_ERROR']) {
      const ok = { event: 'error', error: { code, message: 'x', details: { request_id: REQUEST_ID } } }
      expect(parseChatEvent('error', JSON.stringify(ok)), code).toMatchObject({ kind: 'event' })
    }
  })
})

// ---------------------------------------------------------------- 事件文法（纯函数）

const grammarEvent = (value: unknown): ChatEvent => value as ChatEvent

describe('J08 事件文法（Q2）', () => {
  const advance = (state: ReturnType<typeof advanceChatGrammar>, value: unknown) => {
    if (!state.ok) throw new Error('前置状态已违规')
    return advanceChatGrammar(state.state, grammarEvent(value))
  }

  it('answered：meta → delta* → done/error 通过', () => {
    let s = advanceChatGrammar(INITIAL_CHAT_GRAMMAR, grammarEvent(META_ANSWERED))
    s = advance(s, DELTA_FIRST)
    s = advance(s, DELTA_SECOND)
    s = advance(s, DONE_ANSWERED)
    expect(s).toEqual({ ok: true, state: { phase: 'terminal', deltaCount: 2 } })
  })

  it('not_covered：meta → done(not_covered) 且无 delta', () => {
    const meta = advanceChatGrammar(INITIAL_CHAT_GRAMMAR, grammarEvent(META_NOT_COVERED))
    const done = advance(meta, DONE_NOT_COVERED)
    expect(done).toEqual({ ok: true, state: { phase: 'terminal', deltaCount: 0 } })
  })

  it.each([
    ['首条不是 meta', INITIAL_CHAT_GRAMMAR, DELTA_FIRST],
    ['第二条 meta', { phase: 'meta_answered', deltaCount: 1 } as const, META_ANSWERED],
    ['not_covered 的 meta 后出现 delta', { phase: 'meta_not_covered', deltaCount: 0 } as const, DELTA_FIRST],
    ['not_covered 的 meta 后出现 error', { phase: 'meta_not_covered', deltaCount: 0 } as const, ERROR_EVENT],
    ['terminal 之后再来 delta', { phase: 'terminal', deltaCount: 1 } as const, DELTA_FIRST],
    ['terminal 之后再来 done', { phase: 'terminal', deltaCount: 1 } as const, DONE_ANSWERED],
    ['insufficient_evidence 却已下发 delta', { phase: 'meta_answered', deltaCount: 1 } as const, { event: 'done', final: { ...NOT_COVERED_FINAL, reason: 'insufficient_evidence' } }],
  ] as Array<[string, { phase: string; deltaCount: number }, unknown]>)('%s → 违规', (_label, state, value) => {
    const result = advanceChatGrammar(state as never, grammarEvent(value))
    expect(result.ok).toBe(false)
  })

  it('insufficient_evidence 且没有 delta 是合法的', () => {
    const state = { phase: 'meta_answered', deltaCount: 0 } as const
    const result = advanceChatGrammar(state, grammarEvent({ event: 'done', final: { ...NOT_COVERED_FINAL, reason: 'insufficient_evidence' } }))
    expect(result.ok).toBe(true)
  })
})

// ---------------------------------------------------------------- 开流前

describe('J08 开流前', () => {
  it('POST 到契约路径：JSON 请求体、Accept 事件流、Bearer 令牌不进 URL', async () => {
    const t = setup()
    const stream = sseStream()
    t.backend.streams.push(stream)
    const pending = capture(t.send())
    await flush()

    expect(t.backend.calls).toHaveLength(1)
    const call = t.backend.calls[0]!
    const url = new URL(call.url)
    expect(url.origin + url.pathname).toBe(`http://api.test/api/v1/courses/${CID}/chat`)
    expect(url.search).toBe('')
    expect(call.url).not.toContain('secret-jwt')
    expect(call.init.method).toBe('POST')
    expect(call.init.body).toBe(JSON.stringify({ question: MESSAGE }))
    const headers = new Headers(call.init.headers)
    expect(headers.get('Authorization')).toBe('Bearer secret-jwt')
    expect(headers.get('Accept')).toBe('text/event-stream')
    expect(headers.get('Content-Type')).toBe('application/json')

    stream.push(frame('meta', META_ANSWERED) + frame('done', DONE_ANSWERED))
    await flush()
    expect(pending.status).toBe('fulfilled')
  })

  it('无令牌时不带 Authorization 头', async () => {
    const t = setup({ getAccessToken: () => null })
    const stream = sseStream()
    t.backend.streams.push(stream)
    t.send()
    await flush()
    expect(new Headers(t.backend.calls[0]!.init.headers).get('Authorization')).toBeNull()
  })

  it.each([
    [401, 'UNAUTHENTICATED'],
    [403, 'COURSE_FORBIDDEN'],
    [404, 'GRAPH_NOT_PUBLISHED'],
    [422, 'VALIDATION_ERROR'],
    [429, 'RATE_LIMITED'],
    [503, 'LLM_UNAVAILABLE'],
  ] as Array<[number, string]>)('非 200 + Error JSON（%i %s）抛 ApiError，不进入事件解析', async (status, code) => {
    const t = setup()
    t.backend.streams.push(json({ code, message: '失败', details: { request_id: REQUEST_ID } }, status))
    const pending = capture(t.send())
    await flush()
    expect(pending.status).toBe('rejected')
    expect(pending.error).toBeInstanceOf(ApiError)
    expect((pending.error as ApiError).status).toBe(status)
    expect((pending.error as ApiError).code).toBe(code)
    expect(t.events).toEqual([])
    expect(t.backend.calls).toHaveLength(1)
  })

  it('401 先回调 onUnauthenticated（清会话）再抛出', async () => {
    const t = setup()
    t.backend.streams.push(json({ code: 'UNAUTHENTICATED', message: '令牌失效' }, 401))
    const pending = capture(t.send())
    await flush()
    expect(pending.error).toBeInstanceOf(ApiError)
    expect(t.expired).toEqual([pending.error])
  })

  it('非 200 但 Content-Type 不是 JSON：抛 InvalidResponseError，不解析 HTML 错误页', async () => {
    const t = setup()
    t.backend.streams.push(
      new Response('<html>502 Bad Gateway</html>', { status: 502, headers: { 'Content-Type': 'text/html' } }),
    )
    const pending = capture(t.send())
    await flush()
    expect(pending.error).toBeInstanceOf(InvalidResponseError)
    expect((pending.error as InvalidResponseError).status).toBe(502)
    expect(t.events).toEqual([])
  })

  it('非 200 且 Content-Type 是 JSON 但不是契约 Error：抛 InvalidResponseError', async () => {
    const t = setup()
    t.backend.streams.push(json({ oops: true }, 500))
    const pending = capture(t.send())
    await flush()
    expect(pending.error).toBeInstanceOf(InvalidResponseError)
  })

  it('非 200 且 Content-Type 不是 JSON：响应体再像契约 Error 也不当成 ApiError', async () => {
    const t = setup()
    // 反向代理用自己的 HTML 页包装了一段长得像契约 Error 的 JSON
    t.backend.streams.push(
      new Response('{"code":"UNAUTHENTICATED","message":"网关伪造"}', {
        status: 401,
        headers: { 'Content-Type': 'text/html' },
      }),
    )
    const pending = capture(t.send())
    await flush()
    expect(pending.error).toBeInstanceOf(InvalidResponseError)
    // 与 B15 一致：401 一律视为会话失效（先清会话），但与错误体形状是哪一种无关
    expect(t.expired).toEqual([pending.error])
  })

  it('200 但不是 text/event-stream：抛 InvalidResponseError，不进入解析', async () => {
    const t = setup()
    t.backend.streams.push(json({ status: 'answered', answer: 'x' }))
    const pending = capture(t.send())
    await flush()
    expect(pending.error).toBeInstanceOf(InvalidResponseError)
    expect(t.events).toEqual([])
  })

  it('200 且 Content-Type 正确但响应体为空：抛 InvalidResponseError', async () => {
    const t = setup()
    t.backend.streams.push(sseResponse(null))
    const pending = capture(t.send())
    await flush()
    expect(pending.error).toBeInstanceOf(InvalidResponseError)
  })

  it('fetch 本身失败：抛 NetworkError 且不重试', async () => {
    const t = setup()
    t.backend.streams.push(() => {
      throw new TypeError('network down')
    })
    const pending = capture(t.send())
    await flush()
    expect(pending.error).toBeInstanceOf(NetworkError)
    expect(t.backend.calls).toHaveLength(1)
  })

  it('调用方传入已取消的 signal：不发请求', async () => {
    const t = setup()
    const controller = new AbortController()
    controller.abort()
    const pending = capture(t.send({ signal: controller.signal }))
    await flush()
    expect(pending.error).toBeInstanceOf(AbortedError)
    expect(t.backend.calls).toEqual([])
  })
})

// ---------------------------------------------------------------- 分片解析

describe('J08 分片解析', () => {
  it('UTF-8 多字节被切在分片中间：stream 解码，不产生替换字符', async () => {
    const text = `${frame('meta', META_ANSWERED)}${frame('delta', { event: 'delta', delta: '栈是一种🙂后进先出的线性表[1]。' })}${frame('done', DONE_ANSWERED)}`
    const bytes = new TextEncoder().encode(text)
    const chunks: Uint8Array[] = []
    // 5 字节切块：必然切开中文（3 字节）与 emoji（4 字节）
    for (let i = 0; i < bytes.length; i += 5) chunks.push(bytes.slice(i, i + 5))

    const t = await start(chunks)
    expect(t.pending.status).toBe('fulfilled')
    const delta = t.events.find((e) => e.kind === 'delta')
    expect(delta?.data).toEqual({ event: 'delta', delta: '栈是一种🙂后进先出的线性表[1]。' })
    expect(JSON.stringify(t.events)).not.toContain('\uFFFD')
  })

  it('CRLF 行结束与跨块的 \\r + \\n 都能分帧', async () => {
    const crlf = `${frame('meta', META_ANSWERED)}${frame('delta', DELTA_FIRST)}${frame('done', DONE_ANSWERED)}`.replace(
      /\n/g,
      '\r\n',
    )
    // 切在第一个 \r\n 的 \r 与 \n 之间：跨块的 \r + \n 只能算一次行结束
    const splitAt = crlf.indexOf('\r\n') + 1
    expect(crlf.slice(splitAt - 1, splitAt + 1)).toBe('\r\n')
    const t = await start([crlf.slice(0, splitAt), crlf.slice(splitAt)])
    expect(t.pending.status).toBe('fulfilled')
    expect(t.events.map((e) => e.kind)).toEqual(['meta', 'delta', 'done'])
  })

  it('多行 data: 以 \\n 连接后解析 JSON', async () => {
    const multi = [
      'event: delta',
      'data: {"event":"delta",',
      'data: "delta":"多行 data 拼接"}',
      '',
      '',
    ].join('\n')
    const t = await start([frame('meta', META_ANSWERED), multi, frame('done', DONE_ANSWERED)])
    expect(t.pending.status).toBe('fulfilled')
    expect(t.events.map((e) => e.kind)).toEqual(['meta', 'delta', 'done'])
    expect(t.events[1]?.data).toEqual({ event: 'delta', delta: '多行 data 拼接' })
  })

  it(':ping 心跳与空帧不产生事件、不报错', async () => {
    const t = await start([
      ':ping\n\n',
      '\n\n',
      ':ping\r\n\r\n',
      frame('meta', META_ANSWERED),
      ':ping\n\n',
      frame('done', DONE_ANSWERED),
      ':ping\n\n',
    ])
    expect(t.pending.status).toBe('fulfilled')
    expect(t.events.map((e) => e.kind)).toEqual(['meta', 'done'])
  })
})

// ---------------------------------------------------------------- 终态与文法（流级）

describe('J08 终态', () => {
  it('answered：meta → delta* → done，逐条投递并返回最终响应', async () => {
    const t = await start([frame('meta', META_ANSWERED) + frame('delta', DELTA_FIRST) + frame('delta', DELTA_SECOND) + frame('done', DONE_ANSWERED)])
    expect(t.pending.status).toBe('fulfilled')
    expect(t.pending.value).toEqual({ kind: 'done', final: ANSWERED_FINAL })
    expect(t.events).toEqual([
      { kind: 'meta', data: META_ANSWERED },
      { kind: 'delta', data: DELTA_FIRST },
      { kind: 'delta', data: DELTA_SECOND },
      { kind: 'done', data: DONE_ANSWERED },
    ])
  })

  it('检索阶段拒答：meta(not_covered) → done(not_covered)，没有 delta', async () => {
    const t = await start([frame('meta', META_NOT_COVERED) + frame('done', DONE_NOT_COVERED)])
    expect(t.pending.value).toEqual({ kind: 'done', final: NOT_COVERED_FINAL })
    expect(t.events.filter((e) => e.kind === 'delta')).toEqual([])
  })

  it('服务端 error 事件：与流中断区分，作为终态返回而非抛错', async () => {
    const t = await start([frame('meta', META_ANSWERED) + frame('delta', DELTA_FIRST) + frame('error', ERROR_EVENT)])
    expect(t.pending.status).toBe('fulfilled')
    expect(t.pending.value).toEqual({ kind: 'error', error: ERROR_EVENT.error })
    expect(t.events.at(-1)).toEqual({ kind: 'error', data: ERROR_EVENT })
  })

  it('收到终态后主动断开底层响应体', async () => {
    const t = await start([frame('meta', META_ANSWERED) + frame('done', DONE_ANSWERED)])
    expect(t.stream.state.cancelled).toBe(true)
  })

  it.each([
    ['首条不是 meta', [frame('delta', DELTA_FIRST) + frame('done', DONE_ANSWERED)]],
    ['meta 出现两次', [frame('meta', META_ANSWERED) + frame('meta', META_ANSWERED) + frame('done', DONE_ANSWERED)]],
    ['not_covered 的 meta 之后出现 delta', [frame('meta', META_NOT_COVERED) + frame('delta', DELTA_FIRST)]],
    ['done 之后同批还有事件', [frame('meta', META_ANSWERED) + frame('done', DONE_ANSWERED) + frame('delta', DELTA_FIRST)]],
    ['insufficient_evidence 却已下发 delta', [frame('meta', META_ANSWERED) + frame('delta', DELTA_FIRST) + frame('done', { ...DONE_NOT_COVERED, final: { ...NOT_COVERED_FINAL, reason: 'insufficient_evidence' } })]],
    ['未知事件名', [frame('meta', META_ANSWERED) + frame('hello', { x: 1 }) + frame('done', DONE_ANSWERED)]],
    ['data 为 {}', [frame('meta', META_ANSWERED) + frame('delta', {})]],
  ] as Array<[string, string[]]>)('文法违规：%s → 中断错误', async (_label, chunks) => {
    const t = await start(chunks)
    expect(t.pending.status).toBe('rejected')
    expect(t.pending.error).toBeInstanceOf(ChatStreamInterruptedError)
    expect((t.pending.error as ChatStreamInterruptedError).reason).toBe('protocol')
  })

  it('坏 JSON 事件 → 中断错误，不当成成功', async () => {
    const t = await start([frame('meta', META_ANSWERED), 'event: delta\ndata: {not json}\n\n'])
    expect(t.pending.status).toBe('rejected')
    expect((t.pending.error as ChatStreamInterruptedError).reason).toBe('protocol')
  })
})

// ---------------------------------------------------------------- 异常 EOF / 取消

describe('J08 异常 EOF 与取消', () => {
  it('done / error 之前 EOF → stream_interrupted（不是成功）', async () => {
    const t = await start([frame('meta', META_ANSWERED) + frame('delta', DELTA_FIRST)])
    t.stream.end()
    await flush()
    expect(t.pending.status).toBe('rejected')
    expect(t.pending.error).toBeInstanceOf(ChatStreamInterruptedError)
    expect((t.pending.error as ChatStreamInterruptedError).reason).toBe('eof')
    expect(t.backend.calls).toHaveLength(1)
  })

  it('一个字都没收到就 EOF → stream_interrupted', async () => {
    const t = await start([])
    t.stream.end()
    await flush()
    expect(t.pending.error).toBeInstanceOf(ChatStreamInterruptedError)
    expect((t.pending.error as ChatStreamInterruptedError).reason).toBe('eof')
  })

  it('外部 signal 取消：抛 AbortedError、真正取消底层 body、此后事件不再投递', async () => {
    const t = setup()
    const stream = sseStream()
    t.backend.streams.push(stream)
    const controller = new AbortController()
    const pending = capture(t.send({ signal: controller.signal }))
    await flush()
    stream.push(frame('meta', META_ANSWERED))
    await flush()
    expect(t.events).toHaveLength(1)

    controller.abort()
    await flush()
    expect(pending.status).toBe('rejected')
    expect(pending.error).toBeInstanceOf(AbortedError)
    expect(stream.state.cancelled).toBe(true)
    expect((t.backend.calls[0]!.init.signal as AbortSignal).aborted).toBe(true)

    stream.push(frame('delta', DELTA_FIRST))
    await flush()
    expect(t.events).toHaveLength(1)
    expect(t.backend.calls).toHaveLength(1)
  })

  it('同一分片的首条事件回调取消后，不投递剩余事件', async () => {
    const t = setup()
    const stream = sseStream()
    t.backend.streams.push(stream)
    const controller = new AbortController()
    const pending = capture(t.send({
      signal: controller.signal,
      onEvent(event) {
        t.events.push(event)
        if (event.kind === 'meta') controller.abort()
      },
    }))
    await flush()
    stream.push(frame('meta', META_ANSWERED) + frame('delta', DELTA_FIRST))
    await flush()

    expect(pending.error).toBeInstanceOf(AbortedError)
    expect(t.events.map((event) => event.kind)).toEqual(['meta'])
    expect(stream.state.cancelled).toBe(true)
  })

  it('fetch 尚未返回时取消：抛 AbortedError，且不再读取事件流', async () => {
    const t = setup()
    let release!: (response: Response) => void
    const gate = new Promise<Response>((resolve) => (release = resolve))
    t.backend.streams.push(() => gate)
    const controller = new AbortController()
    const pending = capture(t.send({ signal: controller.signal }))
    await flush()
    controller.abort()
    release(sseResponse(new ReadableStream<Uint8Array>({ start(c) { c.close() } })))
    await flush()
    expect(pending.status).toBe('rejected')
    expect(pending.error).toBeInstanceOf(AbortedError)
    expect(t.events).toEqual([])
  })

  it('超时：抛 TimeoutError 并取消底层 body', async () => {
    const t = setup({ timeoutMs: 15_000 })
    const stream = sseStream()
    t.backend.streams.push(stream)
    const pending = capture(t.send())
    await flush()
    stream.push(frame('meta', META_ANSWERED))
    await flush()
    expect(t.clock.pendingDelays()).toEqual([15_000])

    t.clock.fire(15_000)
    await flush()
    expect(pending.status).toBe('rejected')
    expect(pending.error).toBeInstanceOf(TimeoutError)
    expect(stream.state.cancelled).toBe(true)
  })

  it('默认超时是 30 秒，且终态后清除计时器', async () => {
    expect(DEFAULT_CHAT_TIMEOUT_MS).toBe(30_000)
    const t = await start([frame('meta', META_ANSWERED) + frame('done', DONE_ANSWERED)])
    expect(t.pending.status).toBe('fulfilled')
    expect(t.clock.pendingDelays()).toEqual([])
  })

  it('任何失败都不自动重放提问：开流前错误、中断、EOF、取消各只发一次请求', async () => {
    // 开流前 503
    const pre = setup()
    pre.backend.streams.push(json({ code: 'STORAGE_UNAVAILABLE', message: 'x' }, 503))
    capture(pre.send())
    await flush()
    expect(pre.backend.calls).toHaveLength(1)

    // 事件文法违规
    const bad = await start([frame('meta', META_ANSWERED) + frame('hello', {}) + frame('done', DONE_ANSWERED)])
    expect(bad.pending.status).toBe('rejected')
    expect(bad.backend.calls).toHaveLength(1)

    // 异常 EOF
    const eof = await start([frame('meta', META_ANSWERED)])
    eof.stream.end()
    await flush()
    expect(eof.pending.status).toBe('rejected')
    expect(eof.backend.calls).toHaveLength(1)

    // 取消
    const abort = setup()
    abort.backend.streams.push(sseStream())
    const controller = new AbortController()
    const pending = capture(abort.send({ signal: controller.signal }))
    await flush()
    controller.abort()
    await flush()
    expect(pending.status).toBe('rejected')
    expect(abort.backend.calls).toHaveLength(1)
  })

  it('同一客户端可连续发起新提问（用户重试是新请求，不是自动重放）', async () => {
    const t = setup()
    const first = sseStream()
    const second = sseStream()
    t.backend.streams.push(first, second)

    const a = capture(t.send())
    await flush()
    first.end()
    await flush()
    expect(a.status).toBe('rejected')

    const b = capture(t.send())
    await flush()
    second.push(frame('meta', META_ANSWERED) + frame('done', DONE_ANSWERED))
    await flush()
    expect(b.status).toBe('fulfilled')
    expect(t.backend.calls).toHaveLength(2)
  })
})
