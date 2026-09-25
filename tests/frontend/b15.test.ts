import { createPinia, setActivePinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { components } from '../../src/contracts/v1/generated/typescript/openapi'
import {
  API_PREFIX,
  AbortedError,
  ApiError,
  HttpClientError,
  InvalidResponseError,
  NetworkError,
  TimeoutError,
  apiPath,
  createHttpClient,
  type FetchLike,
  type HttpClientOptions,
} from '../../src/frontend/src/api/http'
import { useCourseStore } from '../../src/frontend/src/stores/course'

type GraphExchange = components['schemas']['GraphExchange']

const graph: GraphExchange = {
  format_version: '1.0',
  course_id: 'c1',
  graph_version: 1,
  generated_at: '2026-09-25T00:00:00Z',
  nodes: [],
  edges: [],
}

function json(body: unknown, init: ResponseInit = {}): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    ...init,
    headers: { 'Content-Type': 'application/json', ...(init.headers as Record<string, string>) },
  })
}

interface Call {
  url: string
  init: RequestInit
}

/** 记录调用的假 fetch；handler 决定返回什么，默认返回图谱 */
function fakeFetch(handler: (call: Call) => Promise<Response> | Response = () => json(graph)) {
  const calls: Call[] = []
  const fn = vi.fn<FetchLike>(async (input, init = {}) => {
    const call = { url: String(input), init }
    calls.push(call)
    return handler(call)
  })
  return { fn, calls }
}

/** 模拟真实 fetch：直到 signal 中止前一直挂起，中止时以 signal.reason 拒绝 */
function hangingUntilAbort(call: Call): Promise<Response> {
  return new Promise((_, reject) => {
    const signal = call.init.signal
    if (!signal) return
    if (signal.aborted) reject(signal.reason)
    signal.addEventListener('abort', () => reject(signal.reason), { once: true })
  })
}

function client(fetch: FetchLike, extra: Partial<HttpClientOptions> = {}) {
  return createHttpClient({ fetch, baseUrl: 'http://api.test', ...extra })
}

function headersOf(call: Call): Headers {
  return new Headers(call.init.headers)
}

async function rejectionOf(promise: Promise<unknown>): Promise<unknown> {
  try {
    await promise
  } catch (error) {
    return error
  }
  throw new Error('期望 promise 被拒绝，但它成功了')
}

describe('B15 路径构造', () => {
  it('前缀集中为 /api/v1，路径参数按模板替换并编码', () => {
    expect(API_PREFIX).toBe('/api/v1')
    expect(apiPath('/api/v1/courses/{cid}/kp/{kid}', { cid: 'c 1/x', kid: 'k?#&' })).toBe(
      '/api/v1/courses/c%201%2Fx/kp/k%3F%23%26',
    )
    expect(apiPath('/api/v1/courses/{cid}/versions/{version}/rollback', { cid: 'c1', version: 3 })).toBe(
      '/api/v1/courses/c1/versions/3/rollback',
    )
    expect(apiPath('/api/v1/courses')).toBe('/api/v1/courses')
  })

  it('拒绝空参数与 . / .. 段，防止路径被浏览器归一化到别的资源', () => {
    expect(() => apiPath('/api/v1/courses/{cid}', { cid: '' })).toThrow()
    expect(() => apiPath('/api/v1/courses/{cid}', { cid: '..' })).toThrow()
    expect(() => apiPath('/api/v1/courses/{cid}', { cid: '.' })).toThrow()
    expect(() => apiPath('/api/v1/courses/{cid}', {} as { cid: string })).toThrow()
  })

  it('路径、方法与参数在类型层面受契约约束', () => {
    // 只做类型检查，不执行
    const typeOnly = (c: ReturnType<typeof createHttpClient>) => {
      // @ts-expect-error 契约里没有这个路径
      apiPath('/api/v1/nope')
      // @ts-expect-error /health 不在 /api/v1 前缀下，不经本客户端
      apiPath('/health')
      // @ts-expect-error 缺少路径参数
      apiPath('/api/v1/courses/{cid}')
      // @ts-expect-error 该路径没有 delete 方法
      void c.request('delete', '/api/v1/courses')
      // @ts-expect-error 查询参数不在契约里
      void c.request('get', '/api/v1/courses/{cid}/graph', { params: { cid: 'c' }, query: { bogus: 1 } })
      const ok: Promise<GraphExchange> = c.request('get', '/api/v1/courses/{cid}/graph', { params: { cid: 'c' } })
      const none: Promise<undefined> = c.request('delete', '/api/v1/courses/{cid}/members/{uid}', {
        params: { cid: 'c', uid: 'u' },
      })
      return [ok, none]
    }
    expect(typeof typeOnly).toBe('function')
  })
})

describe('B15 请求与响应', () => {
  it('拼出 baseUrl + 契约路径 + 查询串；数组重复键，undefined 省略；带 Accept 头', async () => {
    const { fn, calls } = fakeFetch()
    const result = await client(fn).request('get', '/api/v1/courses/{cid}/graph', {
      params: { cid: 'c1' },
      query: { relation_types: ['PREREQUISITE', 'CONTAINS'], version: 2, chapter_id: undefined },
    })
    expect(result).toEqual(graph)
    expect(calls).toHaveLength(1)
    expect(calls[0].url).toBe(
      'http://api.test/api/v1/courses/c1/graph?relation_types=PREREQUISITE&relation_types=CONTAINS&version=2',
    )
    expect(calls[0].init.method).toBe('GET')
    expect(headersOf(calls[0]).get('Accept')).toBe('application/json')
  })

  it('JSON 请求体序列化并带 Content-Type；FormData 不设 Content-Type 由浏览器补边界', async () => {
    const { fn, calls } = fakeFetch(() => json({ task_id: 't1' }, { status: 202 }))
    const c = client(fn)
    const merge = { primary_id: 'a', merged_ids: ['b'] }
    await c.request('post', '/api/v1/courses/{cid}/kp/merge', { params: { cid: 'c1' }, body: merge })
    expect(calls[0].init.method).toBe('POST')
    expect(headersOf(calls[0]).get('Content-Type')).toBe('application/json')
    expect(calls[0].init.body).toBe(JSON.stringify(merge))

    const form = new FormData()
    form.append('file', new Blob(['x']), 'a.txt')
    await c.request('post', '/api/v1/courses/{cid}/documents', { params: { cid: 'c1' }, body: form })
    expect(calls[1].init.body).toBe(form)
    expect(headersOf(calls[1]).has('Content-Type')).toBe(false)
  })

  it('204 与空体返回 undefined', async () => {
    const { fn } = fakeFetch(() => new Response(null, { status: 204 }))
    await expect(
      client(fn).request('delete', '/api/v1/courses/{cid}/members/{uid}', { params: { cid: 'c1', uid: 'u1' } }),
    ).resolves.toBeUndefined()
  })

  it('2xx 但响应体为空或不是 JSON 时抛 InvalidResponseError，不把 undefined 冒充为数据', async () => {
    for (const body of ['', '<html>ok</html>']) {
      const { fn } = fakeFetch(() => new Response(body, { status: 200 }))
      const error = await rejectionOf(client(fn).request('get', '/api/v1/courses'))
      expect(error).toBeInstanceOf(InvalidResponseError)
      expect((error as InvalidResponseError).kind).toBe('invalid_response')
      expect((error as InvalidResponseError).status).toBe(200)
    }
  })
})

describe('B15 类型化错误', () => {
  it('契约 Error 体解析为 ApiError（code/message/details/status）', async () => {
    const body = { code: 'CYCLE_DETECTED', message: '会形成环', details: { cycle: ['a', 'b', 'a'] } }
    const { fn } = fakeFetch(() => json(body, { status: 409 }))
    const error = await rejectionOf(
      client(fn).request('post', '/api/v1/courses/{cid}/relations', {
        params: { cid: 'c1' },
        body: { type: 'PREREQUISITE', from_id: 'a', to_id: 'b' },
      }),
    )
    expect(error).toBeInstanceOf(ApiError)
    expect(error).toBeInstanceOf(HttpClientError)
    const api = error as ApiError
    expect(api.kind).toBe('api')
    expect(api.status).toBe(409)
    expect(api.code).toBe('CYCLE_DETECTED')
    expect(api.message).toBe('会形成环')
    expect(api.details).toEqual({ cycle: ['a', 'b', 'a'] })
  })

  it('429 带出 Retry-After 秒数', async () => {
    const { fn } = fakeFetch(() =>
      json({ code: 'RATE_LIMITED', message: '稍后再试' }, { status: 429, headers: { 'Retry-After': '7' } }),
    )
    const error = (await rejectionOf(client(fn).request('get', '/api/v1/courses'))) as ApiError
    expect(error.code).toBe('RATE_LIMITED')
    expect(error.details).toBeUndefined()
    expect(error.retryAfterSeconds).toBe(7)
  })

  it('非 JSON 错误体（如网关 HTML）为 InvalidResponseError，保留状态码', async () => {
    const { fn } = fakeFetch(() => new Response('<html>Bad Gateway</html>', { status: 502 }))
    const error = await rejectionOf(client(fn).request('get', '/api/v1/courses'))
    expect(error).toBeInstanceOf(InvalidResponseError)
    expect(error).not.toBeInstanceOf(ApiError)
    expect((error as InvalidResponseError).status).toBe(502)
  })

  it('JSON 但不符合 Error 形状（未知码、缺 message、details 非对象）为 InvalidResponseError', async () => {
    const bodies = [
      { code: 'NOT_A_CODE', message: 'x' },
      { code: 'NOT_FOUND' },
      { code: 'NOT_FOUND', message: 'x', details: 'oops' },
      ['NOT_FOUND'],
    ]
    for (const body of bodies) {
      const { fn } = fakeFetch(() => json(body, { status: 404 }))
      const error = await rejectionOf(client(fn).request('get', '/api/v1/courses'))
      expect(error).toBeInstanceOf(InvalidResponseError)
    }
  })

  it('fetch 自身失败为 NetworkError，保留原因', async () => {
    const cause = new TypeError('Failed to fetch')
    const { fn } = fakeFetch(() => Promise.reject(cause))
    const error = await rejectionOf(client(fn).request('get', '/api/v1/courses'))
    expect(error).toBeInstanceOf(NetworkError)
    expect((error as NetworkError).kind).toBe('network')
    expect((error as NetworkError).cause).toBe(cause)
  })
})

describe('B15 认证', () => {
  it('令牌经 getter 放进 Authorization: Bearer，绝不出现在 URL', async () => {
    const { fn, calls } = fakeFetch()
    await client(fn, { getAccessToken: () => 'tok.en-123' }).request('get', '/api/v1/courses/{cid}/graph', {
      params: { cid: 'c1' },
    })
    expect(headersOf(calls[0]).get('Authorization')).toBe('Bearer tok.en-123')
    expect(calls[0].url).not.toContain('tok.en-123')
  })

  it('每次请求重新读取令牌；没有令牌时不发 Authorization 头', async () => {
    let token: string | null = null
    const { fn, calls } = fakeFetch()
    const c = client(fn, { getAccessToken: () => token })
    await c.request('get', '/api/v1/courses')
    token = 'later'
    await c.request('get', '/api/v1/courses')
    expect(headersOf(calls[0]).has('Authorization')).toBe(false)
    expect(headersOf(calls[1]).get('Authorization')).toBe('Bearer later')
  })

  it('401 调用注入的回调一次并仍然抛出 ApiError；其他状态不调用', async () => {
    const onUnauthenticated = vi.fn()
    let status = 401
    const { fn } = fakeFetch(() =>
      json({ code: status === 401 ? 'UNAUTHENTICATED' : 'COURSE_FORBIDDEN', message: 'x' }, { status }),
    )
    const c = client(fn, { getAccessToken: () => 't', onUnauthenticated })
    const error = await rejectionOf(c.request('get', '/api/v1/courses'))
    expect(error).toBeInstanceOf(ApiError)
    expect((error as ApiError).code).toBe('UNAUTHENTICATED')
    expect(onUnauthenticated).toHaveBeenCalledTimes(1)
    expect(onUnauthenticated).toHaveBeenCalledWith(error)

    status = 403
    await rejectionOf(c.request('get', '/api/v1/courses'))
    expect(onUnauthenticated).toHaveBeenCalledTimes(1)
  })

  it('401 即使错误体不是 JSON 也调用回调', async () => {
    const onUnauthenticated = vi.fn()
    const { fn } = fakeFetch(() => new Response('unauthorized', { status: 401 }))
    const error = await rejectionOf(client(fn, { onUnauthenticated }).request('get', '/api/v1/courses'))
    expect(error).toBeInstanceOf(InvalidResponseError)
    expect(onUnauthenticated).toHaveBeenCalledWith(error)
  })

  it('登录接口（契约 security: []）不带令牌，401 口令错误不触发清会话回调', async () => {
    const onUnauthenticated = vi.fn()
    const { fn, calls } = fakeFetch(() => json({ code: 'UNAUTHENTICATED', message: '用户名或口令错误' }, { status: 401 }))
    const error = await rejectionOf(
      client(fn, { getAccessToken: () => 'stale', onUnauthenticated }).request('post', '/api/v1/auth/login', {
        body: { username: 'u', password: 'p' },
      }),
    )
    expect((error as ApiError).code).toBe('UNAUTHENTICATED')
    expect(headersOf(calls[0]).has('Authorization')).toBe(false)
    expect(onUnauthenticated).not.toHaveBeenCalled()
  })
})

describe('B15 取消与超时', () => {
  afterEach(() => {
    vi.useRealTimers()
  })

  it('外部 signal 真正传给 fetch：外部中止时 fetch 收到的 signal 也中止，抛 AbortedError', async () => {
    const { fn, calls } = fakeFetch(hangingUntilAbort)
    const external = new AbortController()
    const pending = client(fn).request('get', '/api/v1/courses', { signal: external.signal })
    await vi.waitFor(() => expect(calls).toHaveLength(1))
    const passed = calls[0].init.signal
    expect(passed).toBeInstanceOf(AbortSignal)
    expect(passed?.aborted).toBe(false)
    external.abort()
    const error = await rejectionOf(pending)
    expect(passed?.aborted).toBe(true)
    expect(error).toBeInstanceOf(AbortedError)
    expect(error).not.toBeInstanceOf(TimeoutError)
    expect((error as AbortedError).kind).toBe('aborted')
  })

  it('已中止的 signal 不发请求，直接抛 AbortedError', async () => {
    const { fn } = fakeFetch()
    const error = await rejectionOf(client(fn).request('get', '/api/v1/courses', { signal: AbortSignal.abort() }))
    expect(error).toBeInstanceOf(AbortedError)
    expect(fn).not.toHaveBeenCalled()
  })

  it('超时中止 fetch 并抛 TimeoutError，与用户取消可区分', async () => {
    vi.useFakeTimers()
    const { fn, calls } = fakeFetch(hangingUntilAbort)
    const external = new AbortController()
    const pending = rejectionOf(
      client(fn, { timeoutMs: 1000 }).request('get', '/api/v1/courses', { signal: external.signal }),
    )
    await vi.advanceTimersByTimeAsync(999)
    expect(calls[0].init.signal?.aborted).toBe(false)
    await vi.advanceTimersByTimeAsync(1)
    const error = await pending
    expect(error).toBeInstanceOf(TimeoutError)
    expect(error).not.toBeInstanceOf(AbortedError)
    expect((error as TimeoutError).kind).toBe('timeout')
    expect((error as TimeoutError).timeoutMs).toBe(1000)
    expect(calls[0].init.signal?.aborted).toBe(true)
    expect(external.signal.aborted).toBe(false)
  })

  it('单次请求可覆盖超时；成功后不留计时器', async () => {
    vi.useFakeTimers()
    const { fn } = fakeFetch(hangingUntilAbort)
    const pending = rejectionOf(client(fn, { timeoutMs: 60_000 }).request('get', '/api/v1/courses', { timeoutMs: 50 }))
    await vi.advanceTimersByTimeAsync(50)
    expect(await pending).toBeInstanceOf(TimeoutError)

    const ok = fakeFetch()
    await client(ok.fn, { timeoutMs: 60_000 }).request('get', '/api/v1/courses')
    expect(vi.getTimerCount()).toBe(0)
  })

  it('读取响应体阶段超时同样抛 TimeoutError', async () => {
    vi.useFakeTimers()
    const neverEnds = new ReadableStream<Uint8Array>({ start() {} })
    const { fn } = fakeFetch(() => new Response(neverEnds, { status: 200 }))
    const pending = rejectionOf(client(fn, { timeoutMs: 100 }).request('get', '/api/v1/courses'))
    await vi.advanceTimersByTimeAsync(100)
    expect(await pending).toBeInstanceOf(TimeoutError)
  })

  describe('与 B04 课程作用域联动', () => {
    beforeEach(() => {
      setActivePinia(createPinia())
    })

    it('切课中止 scope.signal，在途请求在网络层被取消', async () => {
      const store = useCourseStore()
      store.selectCourse('A')
      const scope = store.beginRequest()
      const { fn, calls } = fakeFetch(hangingUntilAbort)
      const pending = rejectionOf(
        client(fn).request('get', '/api/v1/courses/{cid}/graph', {
          params: { cid: scope.courseId },
          signal: scope.signal,
        }),
      )
      await vi.waitFor(() => expect(calls).toHaveLength(1))
      store.selectCourse('B')
      expect(calls[0].init.signal?.aborted).toBe(true)
      expect(await pending).toBeInstanceOf(AbortedError)
    })
  })
})
