import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it } from 'vitest'
import type { components } from '../../src/contracts/v1/generated/typescript/openapi'
import { ApiError, createHttpClient, type FetchLike, type HttpClient } from '../../src/frontend/src/api/http'
import {
  DEFAULT_TASK_STREAM_POLICY,
  createSseParser,
  createTaskEventsClient,
  parseTaskEvent,
  type TaskStreamCloseReason,
  type TaskStreamState,
  type TaskStreamTimers,
  type TaskStreamUpdate,
} from '../../src/frontend/src/api/taskEvents'
import { useCourseStore, type CourseRequestScope } from '../../src/frontend/src/stores/course'

type Task = components['schemas']['Task']

// ---------------------------------------------------------------- 夹具

const TID = 't_01'
const STAGE_EXTRACTING = {
  task_id: TID,
  stage: 'extracting',
  progress: 0.34,
  cancel_requested: false,
  counts: { chunks_done: 5, chunks_total: 14, chunks_failed: 0, kp_count: 23, relation_count: 0 },
  elapsed_ms: 18420,
}
const STAGE_AWAITING = { task_id: TID, stage: 'awaiting_review', progress: 0.95, cancel_requested: false }
const DONE = { task_id: TID, stage: 'completed', progress: 1 }
const ERROR = {
  task_id: TID,
  stage: 'failed',
  progress: 0.42,
  error: { code: 'EXTRACTION_INCOMPLETE', message: '抽取失败的块超过阈值', details: { chunks_failed: 3 } },
}
const CANCELLED = { task_id: TID, stage: 'cancelled', progress: 0.3, cancel_requested: true }

function frame(event: string, data: unknown): string {
  return `event: ${event}\ndata: ${JSON.stringify(data)}\n\n`
}

function taskSnapshot(overrides: Partial<Record<string, unknown>> = {}): Task {
  return {
    id: TID,
    course_id: 'c1',
    document_id: 'd1',
    stage: 'extracting',
    progress: 0.4,
    cancel_requested: false,
    created_at: '2026-09-25T00:00:00Z',
    updated_at: '2026-09-25T00:00:01Z',
    ...overrides,
  } as Task
}

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })
}

/** 可控的 SSE 响应：测试逐块推送字节、结束或观察是否被客户端取消 */
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
    response: new Response(body, { status: 200, headers: { 'Content-Type': 'text/event-stream; charset=utf-8' } }),
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

/** 假计时器：记录请求的延迟，由测试决定何时触发 */
function fakeTimers() {
  let nextId = 1
  const pending = new Map<number, { fn: () => void; ms: number }>()
  const delays: number[] = []
  const timers: TaskStreamTimers = {
    setTimeout(fn, ms) {
      const id = nextId++
      pending.set(id, { fn, ms })
      delays.push(ms)
      return id
    },
    clearTimeout(handle) {
      pending.delete(handle as number)
    },
  }
  return {
    timers,
    delays,
    pendingDelays: () => [...pending.values()].map((t) => t.ms),
    /** 触发唯一一个延迟为 ms 的计时器 */
    fire(ms: number) {
      const matches = [...pending.entries()].filter(([, t]) => t.ms === ms)
      if (matches.length !== 1) throw new Error(`期望恰有一个 ${ms}ms 计时器，实际 ${JSON.stringify(this.pendingDelays())}`)
      const [id, t] = matches[0]!
      pending.delete(id)
      t.fn()
    },
  }
}

interface Call {
  url: string
  init: RequestInit
}

/**
 * 假后端：票据申领、事件流与快照查询分别由队列决定响应。
 * 事件流请求取 `streams` 队首；票据默认依次签发 tk-1、tk-2…
 */
function fakeBackend() {
  const calls: Call[] = []
  const streams: Array<Stream | Response | (() => Response | Promise<Response>)> = []
  const ticketResponses: Array<() => Response> = []
  const taskResponses: Array<() => Response> = []
  let ticketNo = 0
  const fetch: FetchLike = async (input, init = {}) => {
    const url = String(input)
    calls.push({ url, init })
    const path = new URL(url).pathname
    if (path.endsWith('/event-ticket')) {
      const next = ticketResponses.shift()
      if (next) return next()
      ticketNo += 1
      return json({ ticket: `tk-${ticketNo}+/=`, expires_in: 60 })
    }
    if (path.endsWith('/events')) {
      const next = streams.shift()
      if (!next) throw new TypeError('没有准备好的事件流')
      if (next instanceof Response) return next
      if (typeof next === 'function') return next()
      return next.response
    }
    if (path === `/api/v1/tasks/${TID}`) {
      const next = taskResponses.shift()
      if (!next) throw new TypeError('没有准备好的任务快照')
      return next()
    }
    throw new TypeError(`意外请求 ${url}`)
  }
  const client: HttpClient = createHttpClient({ fetch, baseUrl: 'http://api.test', getAccessToken: () => 'secret-jwt' })
  return {
    calls,
    streams,
    ticketResponses,
    taskResponses,
    fetch,
    client,
    streamCalls: () => calls.filter((c) => new URL(c.url).pathname.endsWith('/events')),
    ticketCalls: () => calls.filter((c) => new URL(c.url).pathname.endsWith('/event-ticket')),
    taskCalls: () => calls.filter((c) => new URL(c.url).pathname === `/api/v1/tasks/${TID}`),
  }
}

async function flush(rounds = 20): Promise<void> {
  for (let i = 0; i < rounds; i += 1) await new Promise<void>((resolve) => setTimeout(resolve, 0))
}

function setup(policy: Partial<typeof DEFAULT_TASK_STREAM_POLICY> = {}) {
  const backend = fakeBackend()
  const clock = fakeTimers()
  const store = useCourseStore()
  store.selectCourse('c1')
  const scope = store.beginRequest()
  const updates: TaskStreamUpdate[] = []
  const states: TaskStreamState[] = []
  const closes: TaskStreamCloseReason[] = []
  const api = createTaskEventsClient({
    client: backend.client,
    fetch: backend.fetch,
    baseUrl: 'http://api.test',
    timers: clock.timers,
    policy,
  })
  const subscribe = (s: CourseRequestScope = scope) =>
    api.subscribe(TID, s, {
      onUpdate: (u) => updates.push(u),
      onState: (s2) => states.push(s2),
      onClose: (r) => closes.push(r),
    })
  return { backend, clock, store, scope, updates, states, closes, subscribe }
}

beforeEach(() => {
  setActivePinia(createPinia())
})

// ---------------------------------------------------------------- SSE 解析器

describe('C12 SSE 解析器', () => {
  it('LF 分帧，:ping 注释与未知字段被忽略', () => {
    const parser = createSseParser()
    const out = parser.feed(`:ping\n\n${frame('stage', STAGE_EXTRACTING)}retry: 10\nfoo: bar\n${frame('done', DONE)}`)
    expect(out.map((m) => m.event)).toEqual(['stage', 'done'])
    expect(JSON.parse(out[0]!.data)).toEqual(STAGE_EXTRACTING)
  })

  it('CRLF 与单独 CR 行结束都能分帧', () => {
    const crlf = createSseParser().feed('event: stage\r\ndata: {"a":1}\r\n\r\n:ping\r\n\r\n')
    expect(crlf).toEqual([{ event: 'stage', data: '{"a":1}', lastEventId: '' }])
    const cr = createSseParser().feed('event: done\rdata: {"b":2}\r\r')
    expect(cr).toEqual([{ event: 'done', data: '{"b":2}', lastEventId: '' }])
  })

  it('CRLF 被切在两块之间时不产生多余空行', () => {
    const parser = createSseParser()
    expect(parser.feed('event: stage\r')).toEqual([])
    expect(parser.feed('\ndata: {"a":1}\r')).toEqual([])
    // 若把跨块的 \r\n 当成两次行结束，这里的 \n 会被误作空行而提前派发
    expect(parser.feed('\n')).toEqual([])
    expect(parser.feed('\r')).toEqual([{ event: 'stage', data: '{"a":1}', lastEventId: '' }])
    expect(parser.feed('\n')).toEqual([])
  })

  it('逐字符分片与一次性输入结果一致', () => {
    const text = `:ping\r\n\r\n${frame('stage', STAGE_EXTRACTING).replace(/\n/g, '\r\n')}${frame('error', ERROR)}`
    const whole = createSseParser().feed(text)
    const parser = createSseParser()
    const pieces = [...text].flatMap((ch) => parser.feed(ch))
    expect(pieces).toEqual(whole)
    expect(whole.map((m) => m.event)).toEqual(['stage', 'error'])
  })

  it('多行 data 以 \\n 连接；冒号后无空格、无冒号字段按规范处理', () => {
    const out = createSseParser().feed('data:line1\ndata: line2\ndata\nid: 7\n\n')
    expect(out).toEqual([{ event: 'message', data: 'line1\nline2\n', lastEventId: '7' }])
  })

  it('没有 data 的事件不派发，流末未完结的事件不派发', () => {
    const parser = createSseParser()
    expect(parser.feed('event: stage\n\n')).toEqual([])
    expect(parser.feed('event: done\ndata: {}')).toEqual([])
    // 事件类型在派发/空行后重置
    expect(parser.feed('\n\ndata: x\n\n')).toEqual([
      { event: 'done', data: '{}', lastEventId: '' },
      { event: 'message', data: 'x', lastEventId: '' },
    ])
  })

  it('超长未结束行抛出协议错误，防止缓冲无限增长', () => {
    const parser = createSseParser({ maxLineLength: 16 })
    expect(() => parser.feed('data: 0123456789abcdefghij')).toThrow()
  })
})

// ---------------------------------------------------------------- 事件校验

describe('C12 事件运行时校验', () => {
  it('四种事件的合法载荷通过', () => {
    for (const [name, data] of [
      ['stage', STAGE_EXTRACTING],
      ['stage', STAGE_AWAITING],
      ['done', DONE],
      ['error', ERROR],
      ['cancelled', CANCELLED],
    ] as const) {
      const result = parseTaskEvent(name, JSON.stringify(data), TID)
      expect(result, name).toMatchObject({ kind: 'event', event: name, data })
    }
  })

  it('结束事件的判定', () => {
    const final = (name: string, data: unknown) => {
      const r = parseTaskEvent(name, JSON.stringify(data), TID)
      return r.kind === 'event' && r.final
    }
    expect(final('stage', STAGE_EXTRACTING)).toBe(false)
    expect(final('stage', STAGE_AWAITING)).toBe(true)
    expect(final('done', DONE)).toBe(true)
    expect(final('error', ERROR)).toBe(true)
    expect(final('cancelled', CANCELLED)).toBe(true)
  })

  it('未知事件名与其他任务的事件被忽略', () => {
    expect(parseTaskEvent('message', '{}', TID)).toEqual({ kind: 'ignored' })
    expect(parseTaskEvent('progress2', '{}', TID)).toEqual({ kind: 'ignored' })
    expect(parseTaskEvent('stage', JSON.stringify({ ...STAGE_EXTRACTING, task_id: 't_other' }), TID)).toEqual({
      kind: 'ignored',
    })
  })

  it('不合法载荷被拒绝', () => {
    const invalid: Array<[string, unknown]> = [
      ['stage', {}],
      ['stage', { ...STAGE_EXTRACTING, stage: 'completed' }],
      ['stage', { ...STAGE_EXTRACTING, progress: 1.5 }],
      ['stage', { ...STAGE_EXTRACTING, progress: '0.3' }],
      ['stage', { ...STAGE_EXTRACTING, cancel_requested: undefined }],
      ['stage', { ...STAGE_EXTRACTING, counts: { chunks_done: -1 } }],
      ['stage', { ...STAGE_AWAITING, progress: 0.9 }],
      ['stage', { ...STAGE_EXTRACTING, stage: 'queued' }],
      ['done', { ...DONE, progress: 0.99 }],
      ['done', { ...DONE, stage: 'failed' }],
      ['error', { ...ERROR, error: null }],
      ['error', { ...ERROR, error: { code: 'NOPE', message: 'x' } }],
      ['error', { ...ERROR, error: { code: 'INTERNAL_ERROR' } }],
      ['cancelled', { ...CANCELLED, cancel_requested: false }],
      ['cancelled', [CANCELLED]],
    ]
    for (const [name, data] of invalid) {
      expect(parseTaskEvent(name, JSON.stringify(data), TID).kind, JSON.stringify(data)).toBe('invalid')
    }
    expect(parseTaskEvent('stage', '{not json', TID).kind).toBe('invalid')
  })
})

// ---------------------------------------------------------------- 订阅：鉴权与分帧

describe('C12 任务流订阅', () => {
  it('Bearer 只用于申领票据；事件流以 ?ticket= 连接且不带令牌', async () => {
    const t = setup()
    const s = sseStream()
    t.backend.streams.push(s)
    t.subscribe()
    await flush()

    const [ticketCall] = t.backend.ticketCalls()
    expect(ticketCall!.init.method).toBe('POST')
    expect(new Headers(ticketCall!.init.headers).get('Authorization')).toBe('Bearer secret-jwt')

    const [streamCall] = t.backend.streamCalls()
    const url = new URL(streamCall!.url)
    expect(url.origin + url.pathname).toBe(`http://api.test/api/v1/tasks/${TID}/events`)
    expect(url.searchParams.get('ticket')).toBe('tk-1+/=')
    expect([...url.searchParams.keys()]).toEqual(['ticket'])
    expect(streamCall!.url).not.toContain('secret-jwt')
    const headers = new Headers(streamCall!.init.headers)
    expect(headers.get('Authorization')).toBeNull()
    expect(headers.get('Accept')).toBe('text/event-stream')
    expect(t.states).toContain('streaming')
  })

  it('跨块分片（含 UTF-8 多字节被切开）、CRLF 与心跳下正确投递', async () => {
    const t = setup()
    const s = sseStream()
    t.backend.streams.push(s)
    t.subscribe()
    await flush()

    const bytes = new TextEncoder().encode(
      `:ping\r\n\r\n${frame('stage', STAGE_EXTRACTING).replace(/\n/g, '\r\n')}${frame('error', ERROR)}`,
    )
    // 按 7 字节切块，必然切开中文字符
    for (let i = 0; i < bytes.length; i += 7) {
      s.push(bytes.slice(i, i + 7))
      await flush(2)
    }
    await flush()
    expect(t.updates).toEqual([
      { source: 'stream', event: 'stage', data: STAGE_EXTRACTING, final: false },
      { source: 'stream', event: 'error', data: ERROR, final: true },
    ])
    expect(t.closes).toEqual([{ kind: 'finished', stage: 'failed' }])
  })

  it.each([
    ['stage', STAGE_AWAITING, 'awaiting_review'],
    ['done', DONE, 'completed'],
    ['error', ERROR, 'failed'],
    ['cancelled', CANCELLED, 'cancelled'],
  ] as const)('收到结束事件 %s 后主动关闭且不再重连', async (name, data, stage) => {
    const t = setup()
    const s = sseStream()
    t.backend.streams.push(s)
    t.subscribe()
    await flush()
    s.push(frame(name, data))
    await flush()

    expect(t.closes).toEqual([{ kind: 'finished', stage }])
    expect(s.state.cancelled).toBe(true)
    expect(t.clock.pendingDelays()).toEqual([])
    // 服务端随后关流也不触发重连
    s.end()
    await flush()
    expect(t.backend.streamCalls()).toHaveLength(1)
    expect(t.backend.ticketCalls()).toHaveLength(1)
    expect(t.states.at(-1)).toBe('closed')
  })

  it('未知事件名被忽略，其他任务的事件不投递', async () => {
    const t = setup()
    const s = sseStream()
    t.backend.streams.push(s)
    t.subscribe()
    await flush()
    s.push('event: hello\ndata: {"x":1}\n\ndata: plain\n\n')
    s.push(frame('stage', { ...STAGE_EXTRACTING, task_id: 't_other' }))
    s.push(frame('stage', STAGE_EXTRACTING))
    await flush()
    expect(t.updates).toHaveLength(1)
    expect(t.closes).toEqual([])
  })

  // -------------------------------------------------------------- 关闭

  it('取消订阅（组件卸载）立即关闭连接，之后不再投递', async () => {
    const t = setup()
    const s = sseStream()
    t.backend.streams.push(s)
    const sub = t.subscribe()
    await flush()
    s.push(frame('stage', STAGE_EXTRACTING))
    await flush()
    sub.close()
    sub.close() // 幂等
    expect(sub.closed).toBe(true)
    await flush()
    s.push(frame('stage', { ...STAGE_EXTRACTING, progress: 0.5 }))
    await flush()

    expect(s.state.cancelled).toBe(true)
    expect(t.updates).toHaveLength(1)
    expect(t.closes).toEqual([{ kind: 'unsubscribed' }])
    expect(t.clock.pendingDelays()).toEqual([])
    expect(t.backend.streamCalls()).toHaveLength(1)
  })

  it('申领票据期间取消订阅：不再建立事件流', async () => {
    const t = setup()
    let release!: (r: Response) => void
    const gate = new Promise<Response>((resolve) => (release = resolve))
    const origFetch = t.backend.fetch
    const api = createTaskEventsClient({
      client: createHttpClient({
        fetch: async (input, init) => (String(input).endsWith('/event-ticket') ? gate : origFetch(input, init)),
        baseUrl: 'http://api.test',
      }),
      fetch: origFetch,
      baseUrl: 'http://api.test',
      timers: t.clock.timers,
    })
    const closes: TaskStreamCloseReason[] = []
    const sub = api.subscribe(TID, t.scope, { onUpdate: () => undefined, onClose: (r) => closes.push(r) })
    await flush()
    sub.close()
    release(json({ ticket: 'late', expires_in: 60 }))
    await flush()
    expect(t.backend.streamCalls()).toHaveLength(0)
    expect(closes).toEqual([{ kind: 'unsubscribed' }])
  })

  it('切换课程使作用域失效：关闭连接，旧课程的迟到事件不投递', async () => {
    const t = setup()
    const s = sseStream()
    t.backend.streams.push(s)
    t.subscribe()
    await flush()
    s.push(frame('stage', STAGE_EXTRACTING))
    await flush()

    t.store.selectCourse('c2')
    s.push(frame('stage', { ...STAGE_EXTRACTING, progress: 0.5 }))
    await flush()

    expect(t.updates).toHaveLength(1)
    expect(t.closes).toEqual([{ kind: 'scope_invalidated' }])
    expect(s.state.cancelled).toBe(true)
    expect(t.clock.pendingDelays()).toEqual([])
  })

  it('A→B→A：以旧作用域订阅的流在回到 A 后仍不投递', async () => {
    const t = setup()
    const s = sseStream()
    t.backend.streams.push(s)
    t.subscribe()
    await flush()
    t.store.selectCourse('c2')
    t.store.selectCourse('c1')
    s.push(frame('stage', STAGE_EXTRACTING))
    await flush()
    expect(t.updates).toEqual([])
    expect(t.closes).toEqual([{ kind: 'scope_invalidated' }])
  })

  it('以已失效的作用域订阅：不发任何请求，直接关闭', async () => {
    const t = setup()
    const stale = t.scope
    t.store.selectCourse('c2')
    t.subscribe(stale)
    await flush()
    expect(t.backend.calls).toEqual([])
    expect(t.closes).toEqual([{ kind: 'scope_invalidated' }])
  })

  // -------------------------------------------------------------- 重连与降级

  it('流意外结束：关闭 → 重新申领票据 → 新建连接，退避 1、2、4、8 秒，第 5 次失败降级为 5 秒轮询', async () => {
    const t = setup()
    for (let i = 0; i < 5; i += 1) {
      const s = sseStream()
      t.backend.streams.push(s)
    }
    const all = [...t.backend.streams] as Stream[]
    t.subscribe()
    await flush()

    const expected = [1000, 2000, 4000, 8000]
    for (let i = 0; i < 4; i += 1) {
      all[i]!.end() // 未收到结束事件即 EOF
      await flush()
      expect(t.clock.pendingDelays()).toEqual([expected[i]])
      expect(t.states.at(-1)).toBe('reconnecting')
      t.clock.fire(expected[i]!)
      await flush()
      expect(t.backend.streamCalls()).toHaveLength(i + 2)
    }
    // 每次重连都用新票据
    const tickets = t.backend.streamCalls().map((c) => new URL(c.url).searchParams.get('ticket'))
    expect(new Set(tickets).size).toBe(5)

    t.backend.taskResponses.push(() => json(taskSnapshot({ progress: 0.5 })))
    t.backend.taskResponses.push(() => json(taskSnapshot({ stage: 'awaiting_review', progress: 0.95 })))
    all[4]!.end()
    await flush()
    expect(t.states.at(-1)).toBe('polling')
    expect(t.backend.taskCalls()).toHaveLength(1)
    expect(new Headers(t.backend.taskCalls()[0]!.init.headers).get('Authorization')).toBe('Bearer secret-jwt')
    expect(t.updates.at(-1)).toMatchObject({ source: 'poll', final: false, task: { progress: 0.5 } })
    expect(t.clock.pendingDelays()).toEqual([5000])

    t.clock.fire(5000)
    await flush()
    expect(t.updates.at(-1)).toMatchObject({ source: 'poll', final: true, task: { stage: 'awaiting_review' } })
    expect(t.closes).toEqual([{ kind: 'finished', stage: 'awaiting_review' }])
    expect(t.backend.streamCalls()).toHaveLength(5)
    expect(t.clock.pendingDelays()).toEqual([])
  })

  it('退避上限 30 秒，默认值可调', async () => {
    expect(DEFAULT_TASK_STREAM_POLICY).toMatchObject({
      initialBackoffMs: 1000,
      maxBackoffMs: 30000,
      maxConsecutiveFailures: 5,
      pollIntervalMs: 5000,
    })
    const t = setup({ initialBackoffMs: 10_000, maxConsecutiveFailures: 10 })
    const all: Stream[] = []
    for (let i = 0; i < 4; i += 1) {
      const s = sseStream()
      all.push(s)
      t.backend.streams.push(s)
    }
    t.subscribe()
    await flush()
    const seen: number[] = []
    for (let i = 0; i < 3; i += 1) {
      all[i]!.end()
      await flush()
      const [delay] = t.clock.pendingDelays()
      seen.push(delay!)
      t.clock.fire(delay!)
      await flush()
    }
    expect(seen).toEqual([10_000, 20_000, 30_000])
  })

  it('收到有效事件后连续失败计数清零', async () => {
    const t = setup()
    const a = sseStream()
    const b = sseStream()
    const c = sseStream()
    t.backend.streams.push(a, b, c)
    t.subscribe()
    await flush()
    a.end()
    await flush()
    t.clock.fire(1000)
    await flush()
    b.push(frame('stage', STAGE_EXTRACTING))
    b.end()
    await flush()
    // b 投递过有效事件，失败计数从 1 重新开始
    expect(t.clock.pendingDelays()).toEqual([1000])
  })

  it('心跳保活；超过空闲时限无任何字节则视为断线并重连', async () => {
    const t = setup({ idleTimeoutMs: 45_000 })
    const a = sseStream()
    const b = sseStream()
    t.backend.streams.push(a, b)
    t.subscribe()
    await flush()
    expect(t.clock.pendingDelays()).toEqual([45_000])
    a.push(':ping\n\n')
    await flush()
    // 心跳重置空闲计时
    expect(t.clock.pendingDelays()).toEqual([45_000])
    expect(t.clock.delays.filter((d) => d === 45_000).length).toBeGreaterThanOrEqual(2)
    t.clock.fire(45_000)
    await flush()
    expect(a.state.cancelled).toBe(true)
    expect(t.clock.pendingDelays()).toEqual([1000])
    t.clock.fire(1000)
    await flush()
    expect(t.backend.streamCalls()).toHaveLength(2)
  })

  it('事件流网络错误、401（票据过期）、5xx 与非 SSE 响应都按失败重连', async () => {
    const t = setup()
    t.backend.streams.push(
      () => {
        throw new TypeError('network down')
      },
      json({ code: 'UNAUTHENTICATED', message: '票据无效' }, 401),
      json({ code: 'INTERNAL_ERROR', message: 'x' }, 500),
      new Response('<html>', { status: 200, headers: { 'Content-Type': 'text/html' } }),
    )
    const ok = sseStream()
    t.backend.streams.push(ok)
    t.subscribe()
    await flush()
    for (const delay of [1000, 2000, 4000, 8000]) {
      expect(t.clock.pendingDelays()).toEqual([delay])
      t.clock.fire(delay)
      await flush()
    }
    ok.push(frame('stage', STAGE_AWAITING))
    await flush()
    expect(t.closes).toEqual([{ kind: 'finished', stage: 'awaiting_review' }])
  })

  it('不合法的事件载荷按协议错误断开并重连', async () => {
    const t = setup()
    const a = sseStream()
    const b = sseStream()
    t.backend.streams.push(a, b)
    t.subscribe()
    await flush()
    a.push('event: stage\ndata: {}\n\n')
    await flush()
    expect(a.state.cancelled).toBe(true)
    expect(t.updates).toEqual([])
    expect(t.clock.pendingDelays()).toEqual([1000])
  })

  it('申领票据遇到 5xx 或网络错误按失败重试', async () => {
    const t = setup()
    t.backend.ticketResponses.push(() => json({ code: 'STORAGE_UNAVAILABLE', message: 'db' }, 503))
    const s = sseStream()
    t.backend.streams.push(s)
    t.subscribe()
    await flush()
    expect(t.clock.pendingDelays()).toEqual([1000])
    t.clock.fire(1000)
    await flush()
    expect(t.backend.streamCalls()).toHaveLength(1)
  })

  it.each([401, 403, 404])('申领票据返回 %i 是不可恢复错误：停止且不重试', async (status) => {
    const t = setup()
    const code = status === 401 ? 'UNAUTHENTICATED' : status === 403 ? 'ROLE_FORBIDDEN' : 'NOT_FOUND'
    t.backend.ticketResponses.push(() => json({ code, message: 'x' }, status))
    t.subscribe()
    await flush()
    expect(t.closes).toHaveLength(1)
    const reason = t.closes[0]!
    expect(reason.kind).toBe('fatal')
    expect(reason.kind === 'fatal' && reason.error instanceof ApiError && reason.error.status).toBe(status)
    expect(t.clock.pendingDelays()).toEqual([])
    expect(t.backend.streamCalls()).toHaveLength(0)
  })

  it.each([403, 404])('事件流返回 %i 是不可恢复错误', async (status) => {
    const t = setup()
    const code = status === 403 ? 'ROLE_FORBIDDEN' : 'NOT_FOUND'
    t.backend.streams.push(json({ code, message: 'x' }, status))
    t.subscribe()
    await flush()
    expect(t.closes).toHaveLength(1)
    const reason = t.closes[0]!
    expect(reason.kind === 'fatal' && reason.error instanceof ApiError && reason.error.code).toBe(code)
    expect(t.clock.pendingDelays()).toEqual([])
  })

  it('轮询：瞬时错误继续轮询，404 停止；快照课程不符视为不可恢复', async () => {
    const t = setup({ maxConsecutiveFailures: 1 })
    t.backend.streams.push(() => {
      throw new TypeError('down')
    })
    t.backend.taskResponses.push(() => json({ code: 'STORAGE_UNAVAILABLE', message: 'x' }, 503))
    t.backend.taskResponses.push(() => json({ code: 'NOT_FOUND', message: 'x' }, 404))
    t.subscribe()
    await flush()
    expect(t.states.at(-1)).toBe('polling')
    expect(t.clock.pendingDelays()).toEqual([5000])
    t.clock.fire(5000)
    await flush()
    expect(t.closes).toHaveLength(1)
    expect(t.closes[0]!.kind).toBe('fatal')

    const u = setup({ maxConsecutiveFailures: 1 })
    u.backend.streams.push(() => {
      throw new TypeError('down')
    })
    u.backend.taskResponses.push(() => json(taskSnapshot({ course_id: 'c_other' })))
    u.subscribe()
    await flush()
    expect(u.updates).toEqual([])
    expect(u.closes).toHaveLength(1)
    expect(u.closes[0]!.kind).toBe('fatal')
  })

  it('轮询期间取消订阅：清除计时器，不再请求', async () => {
    const t = setup({ maxConsecutiveFailures: 1 })
    t.backend.streams.push(() => {
      throw new TypeError('down')
    })
    t.backend.taskResponses.push(() => json(taskSnapshot()))
    const sub = t.subscribe()
    await flush()
    expect(t.clock.pendingDelays()).toEqual([5000])
    sub.close()
    expect(t.clock.pendingDelays()).toEqual([])
    expect(t.closes).toEqual([{ kind: 'unsubscribed' }])
  })

  it('回调抛出异常不影响后续投递', async () => {
    const t = setup()
    const s = sseStream()
    t.backend.streams.push(s)
    const api = createTaskEventsClient({
      client: t.backend.client,
      fetch: t.backend.fetch,
      baseUrl: 'http://api.test',
      timers: t.clock.timers,
      reportError: () => undefined,
    })
    const seen: string[] = []
    api.subscribe(TID, t.scope, {
      onUpdate: (u) => {
        seen.push(u.source === 'stream' ? u.data.stage : u.task.stage)
        throw new Error('组件出错')
      },
    })
    await flush()
    s.push(frame('stage', STAGE_EXTRACTING) + frame('stage', STAGE_AWAITING))
    await flush()
    expect(seen).toEqual(['extracting', 'awaiting_review'])
    expect(s.state.cancelled).toBe(true)
  })
})
