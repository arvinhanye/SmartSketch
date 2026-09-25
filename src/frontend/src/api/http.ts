import type { components, paths } from '../../../contracts/v1/generated/typescript/openapi'

/**
 * 前端 HTTP 客户端（B15）。
 *
 * - 路径只能取契约 `paths` 中 `/api/v1` 下的模板，参数由 `apiPath` 编码替换，组件不自行拼路径。
 * - 令牌经注入的 getter 放进 `Authorization: Bearer`，绝不进 URL（`specs/identity-access.md` §2.4）。
 * - 401 调用注入的 `onUnauthenticated`（清会话、回登录页由 H13 接线）。
 * - 外部 `AbortSignal`（如课程作用域 `scope.signal`）与超时合并后真正传给 `fetch`；
 *   用户/作用域取消抛 `AbortedError`，超时抛 `TimeoutError`。
 * - 只处理 JSON 请求/响应（含 multipart 上传）；SSE 流不经本客户端。
 */

type ErrorBody = components['schemas']['Error']
export type ErrorCode = components['schemas']['ErrorCode']

/** 契约主版本前缀，全前端只在此处出现（`docs/architecture.md`：/api/v1 与 v1/ 同步） */
export const API_PREFIX = '/api/v1'

export const DEFAULT_TIMEOUT_MS = 30_000

/** 契约中 `/api/v1` 下的路径模板；`/health` 是运维探针，不经本客户端 */
export type ApiPath = Extract<keyof paths, `${typeof API_PREFIX}/${string}`>

export type HttpMethod = 'get' | 'post' | 'put' | 'patch' | 'delete'

/** 该路径在契约里声明了的方法 */
export type MethodOf<P extends ApiPath> = {
  [M in HttpMethod]: paths[P][M] extends undefined ? never : M
}[HttpMethod]

type Operation<P extends ApiPath, M extends HttpMethod> = NonNullable<paths[P][M]>

/** 模板里的 `{name}` 占位符名 */
type TemplateParamNames<T extends string> = T extends `${string}{${infer N}}${infer Rest}`
  ? N | TemplateParamNames<Rest>
  : never

type PathLevelParams<P extends ApiPath> = paths[P]['parameters'] extends { path: infer X } ? X : {}
type OperationPathParams<O> = O extends { parameters: { path: infer X } } ? X : {}
// 路径参数可能分别声明在路径级和操作级（如 members/{uid} 的 uid 只在 delete 上），两处合并
type DeclaredPathParams<P extends ApiPath, M extends MethodOf<P>> = PathLevelParams<P> &
  OperationPathParams<Operation<P, M>>

/** 路径参数：键取自模板占位符，值类型取契约声明，未声明时为 string */
export type PathParams<P extends ApiPath, M extends MethodOf<P> = MethodOf<P>> = {
  [K in TemplateParamNames<P>]: K extends keyof DeclaredPathParams<P, M> ? DeclaredPathParams<P, M>[K] : string
}

type PathParamArgs<P extends ApiPath> = [TemplateParamNames<P>] extends [never]
  ? [params?: undefined]
  : [params: PathParams<P>]

type QueryOf<O> = O extends { parameters: { query?: infer Q } } ? NonNullable<Q> : never

type BodyContent<O> =
  O extends { requestBody?: infer R }
    ? NonNullable<R> extends { content: infer C }
      ? C extends { 'application/json': infer J }
        ? J
        : C extends { 'multipart/form-data': unknown }
          ? FormData
          : never
      : never
    : never

type SuccessStatus = 200 | 201 | 202 | 204

/** 成功响应体：2xx 的 `application/json` 内容；无内容（204）为 `undefined` */
export type ResponseOf<O> = O extends { responses: infer R }
  ? {
      [K in keyof R & SuccessStatus]: R[K] extends { content: { 'application/json': infer B } } ? B : undefined
    }[keyof R & SuccessStatus]
  : never

type ParamsOption<P extends ApiPath, M extends MethodOf<P>> = [TemplateParamNames<P>] extends [never]
  ? { params?: undefined }
  : { params: PathParams<P, M> }

type QueryOption<O> = [QueryOf<O>] extends [never] ? { query?: undefined } : { query?: QueryOf<O> }

type BodyOption<O> = [BodyContent<O>] extends [never]
  ? { body?: undefined }
  : O extends { requestBody: object }
    ? { body: BodyContent<O> }
    : { body?: BodyContent<O> }

export interface RequestControl {
  /** 外部取消信号，如 `useCourseStore().beginRequest().signal` */
  signal?: AbortSignal
  /** 覆盖客户端默认超时（毫秒） */
  timeoutMs?: number
}

export type RequestOptions<P extends ApiPath, M extends MethodOf<P>> = RequestControl &
  ParamsOption<P, M> &
  QueryOption<Operation<P, M>> &
  BodyOption<Operation<P, M>>

type RequestArgs<P extends ApiPath, M extends MethodOf<P>> =
  {} extends RequestOptions<P, M> ? [options?: RequestOptions<P, M>] : [options: RequestOptions<P, M>]

// ---------------------------------------------------------------- 错误类型

export type HttpErrorKind = 'api' | 'invalid_response' | 'network' | 'timeout' | 'aborted'

/** 本客户端抛出的全部错误的基类；按 `kind` 或 `instanceof` 分支 */
export abstract class HttpClientError extends Error {
  abstract readonly kind: HttpErrorKind
}

/** 服务端按契约返回的 `Error` 体 */
export class ApiError extends HttpClientError {
  readonly kind = 'api' as const
  readonly status: number
  readonly code: ErrorCode
  readonly details: Record<string, unknown> | undefined
  /** `Retry-After` 秒数（仅整数秒形式），无则 `undefined` */
  readonly retryAfterSeconds: number | undefined

  constructor(status: number, body: ErrorBody, retryAfterSeconds?: number) {
    super(body.message)
    this.name = 'ApiError'
    this.status = status
    this.code = body.code
    this.details = body.details
    this.retryAfterSeconds = retryAfterSeconds
  }
}

/** 有 HTTP 响应，但不符合契约：错误体不是 `Error` 形状（如网关 HTML），或成功体为空/不是 JSON */
export class InvalidResponseError extends HttpClientError {
  readonly kind = 'invalid_response' as const
  readonly status: number

  constructor(status: number, reason: string, cause?: unknown) {
    super(`响应不符合契约（HTTP ${status}）：${reason}`, { cause })
    this.name = 'InvalidResponseError'
    this.status = status
  }
}

/** 请求未得到 HTTP 响应（断网、DNS、CORS 等），或读取响应体时连接中断 */
export class NetworkError extends HttpClientError {
  readonly kind = 'network' as const

  constructor(cause: unknown) {
    super('网络请求失败', { cause })
    this.name = 'NetworkError'
  }
}

/** 超过客户端超时 */
export class TimeoutError extends HttpClientError {
  readonly kind = 'timeout' as const
  readonly timeoutMs: number

  constructor(timeoutMs: number, cause?: unknown) {
    super(`请求超时（${timeoutMs} ms）`, { cause })
    this.name = 'TimeoutError'
    this.timeoutMs = timeoutMs
  }
}

/** 调用方经外部 signal 取消（用户取消、切课使作用域失效） */
export class AbortedError extends HttpClientError {
  readonly kind = 'aborted' as const

  constructor(cause?: unknown) {
    super('请求已取消', { cause })
    this.name = 'AbortedError'
  }
}

// ---------------------------------------------------------------- 契约常量

// 契约 ErrorCode 的运行时副本，用于校验错误体；下方类型断言保证与契约双向一致
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
] as const satisfies readonly ErrorCode[]
type MissingErrorCode = Exclude<ErrorCode, (typeof ERROR_CODES)[number]>
const errorCodesComplete: [MissingErrorCode] extends [never] ? true : MissingErrorCode = true
void errorCodesComplete
const ERROR_CODE_SET: ReadonlySet<string> = new Set(ERROR_CODES)

/** 契约中 `security: []` 的路径：不带令牌，401 表示凭据错误而非会话失效，不触发清会话 */
const PUBLIC_PATHS: ReadonlySet<ApiPath> = new Set<ApiPath>(['/api/v1/auth/login'])

// ---------------------------------------------------------------- 路径

/** 按契约路径模板构造路径：参数逐段 `encodeURIComponent`，拒绝空值与 `.`/`..` */
export function apiPath<P extends ApiPath>(template: P, ...args: PathParamArgs<P>): string {
  const params = args[0] as Record<string, unknown> | undefined
  if (!template.startsWith(`${API_PREFIX}/`)) throw new TypeError(`路径不在 ${API_PREFIX} 下：${template}`)
  return template.replace(/\{([^}]+)\}/g, (_, name: string) => {
    const value = params?.[name]
    if (typeof value !== 'string' && typeof value !== 'number') {
      throw new TypeError(`缺少路径参数 ${name}`)
    }
    const text = String(value)
    if (text === '' || text === '.' || text === '..') throw new TypeError(`路径参数 ${name} 无效`)
    return encodeURIComponent(text)
  })
}

function queryString(query: object | undefined): string {
  const search = new URLSearchParams()
  for (const [key, value] of Object.entries(query ?? {})) {
    for (const item of Array.isArray(value) ? value : [value]) {
      if (item === undefined || item === null) continue
      if (typeof item !== 'string' && typeof item !== 'number' && typeof item !== 'boolean') {
        throw new TypeError(`查询参数 ${key} 只能是标量或标量数组`)
      }
      search.append(key, String(item))
    }
  }
  const text = search.toString()
  return text ? `?${text}` : ''
}

// ---------------------------------------------------------------- 客户端

export type FetchLike = (input: string, init?: RequestInit) => Promise<Response>

export interface HttpClientOptions {
  /** 默认用全局 fetch；测试注入假实现 */
  fetch?: FetchLike
  /** API 源（协议+主机+端口），默认空串即同源 */
  baseUrl?: string
  /** 每次请求时读取当前访问令牌；无令牌返回 null/undefined */
  getAccessToken?: () => string | null | undefined
  /** 非公开接口收到 401 时调用（H13：清会话并回登录页）；随后仍抛出该错误 */
  onUnauthenticated?: (error: ApiError | InvalidResponseError) => void
  /** 默认超时（毫秒），覆盖发起到读完响应体的全过程 */
  timeoutMs?: number
}

export interface HttpClient {
  request<P extends ApiPath, M extends MethodOf<P>>(
    method: M,
    path: P,
    ...args: RequestArgs<P, M>
  ): Promise<ResponseOf<Operation<P, M>>>
}

interface RuntimeOptions extends RequestControl {
  params?: Record<string, unknown>
  query?: object
  body?: unknown
}

export function createHttpClient(options: HttpClientOptions = {}): HttpClient {
  const fetchImpl: FetchLike = options.fetch ?? ((input, init) => globalThis.fetch(input, init))
  const baseUrl = (options.baseUrl ?? '').replace(/\/+$/, '')
  const defaultTimeout = options.timeoutMs ?? DEFAULT_TIMEOUT_MS

  async function send(method: HttpMethod, path: ApiPath, opts: RuntimeOptions = {}): Promise<unknown> {
    const url =
      baseUrl + (apiPath as (t: string, p?: Record<string, unknown>) => string)(path, opts.params) + queryString(opts.query)
    const isPublic = PUBLIC_PATHS.has(path)

    const headers = new Headers({ Accept: 'application/json' })
    let body: BodyInit | undefined
    if (opts.body instanceof FormData) {
      body = opts.body // Content-Type（含 boundary）由浏览器生成
    } else if (opts.body !== undefined) {
      headers.set('Content-Type', 'application/json')
      body = JSON.stringify(opts.body)
    }
    if (!isPublic) {
      const token = options.getAccessToken?.()
      if (token) headers.set('Authorization', `Bearer ${token}`)
    }

    const external = opts.signal
    if (external?.aborted) throw new AbortedError(external.reason)

    const timeoutMs = opts.timeoutMs ?? defaultTimeout
    const controller = new AbortController()
    let timedOut = false
    const onExternalAbort = () => controller.abort(external?.reason)
    external?.addEventListener('abort', onExternalAbort, { once: true })
    const timer = setTimeout(() => {
      if (controller.signal.aborted) return
      timedOut = true
      controller.abort(new DOMException('请求超时', 'TimeoutError'))
    }, timeoutMs)
    const cancelled = (): HttpClientError =>
      timedOut ? new TimeoutError(timeoutMs, controller.signal.reason) : new AbortedError(controller.signal.reason)

    try {
      let response: Response
      let text: string
      try {
        response = await fetchImpl(url, { method: method.toUpperCase(), headers, body, signal: controller.signal })
        text = await readText(response, controller.signal)
      } catch (cause) {
        if (controller.signal.aborted) throw cancelled()
        throw new NetworkError(cause)
      }

      if (response.ok) return parseSuccess(response.status, text)

      const error = parseError(response, text)
      if (response.status === 401 && !isPublic) notifyUnauthenticated(error)
      throw error
    } finally {
      clearTimeout(timer)
      external?.removeEventListener('abort', onExternalAbort)
    }
  }

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

  return { request: send as HttpClient['request'] }
}

/** 读取响应体；signal 中止时立即拒绝，使超时/取消覆盖读体阶段 */
function readText(response: Response, signal: AbortSignal): Promise<string> {
  return new Promise((resolve, reject) => {
    const onAbort = () => {
      reject(signal.reason)
      response.body?.cancel(signal.reason).catch(() => undefined)
    }
    if (signal.aborted) return onAbort()
    signal.addEventListener('abort', onAbort, { once: true })
    response
      .text()
      .then(resolve, reject)
      .finally(() => signal.removeEventListener('abort', onAbort))
  })
}

function parseSuccess(status: number, text: string): unknown {
  if (status === 204 || status === 205) return undefined
  if (text === '') throw new InvalidResponseError(status, '成功响应体为空')
  try {
    return JSON.parse(text)
  } catch (cause) {
    throw new InvalidResponseError(status, '成功响应体不是 JSON', cause)
  }
}

function parseError(response: Response, text: string): ApiError | InvalidResponseError {
  let parsed: unknown
  try {
    parsed = JSON.parse(text)
  } catch (cause) {
    return new InvalidResponseError(response.status, '错误响应体不是 JSON', cause)
  }
  if (!isErrorBody(parsed)) return new InvalidResponseError(response.status, '错误响应体不是契约 Error')
  return new ApiError(response.status, parsed, retryAfterSeconds(response.headers.get('Retry-After')))
}

function isPlainObject(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
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

function retryAfterSeconds(header: string | null): number | undefined {
  if (header === null || !/^\d+$/.test(header.trim())) return undefined
  return Number(header.trim())
}
