import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia, type Pinia } from 'pinia'
import { createMemoryHistory } from 'vue-router'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { components } from '../../src/contracts/v1/generated/typescript/openapi'
import App from '../../src/frontend/src/App.vue'
import {
  AUTH_API_KEY,
  createAuthApi,
  createSessionHttpClient,
  type AuthApi,
} from '../../src/frontend/src/api/auth'
import { ApiError, NetworkError, TimeoutError, type FetchLike } from '../../src/frontend/src/api/http'
import { createAppRouter, NOTICE_UNAUTHENTICATED, ROOT_ROUTE } from '../../src/frontend/src/router/index.ts'
import { useCourseStore } from '../../src/frontend/src/stores/course'
import { SESSION_STORAGE_KEY, useSessionStore } from '../../src/frontend/src/stores/session'
import LoginView from '../../src/frontend/src/views/LoginView.vue'

type LoginResponse = components['schemas']['LoginResponse']
type Role = components['schemas']['Role']

const PASSWORD = 'PASSWORD-SECRET-h13'
// 故意不是 JWT：前端不得解析令牌，只看 LoginResponse.user.role
const TOKEN = 'opaque-token-not-a-jwt'

function loginResponse(role: Role, id = `u_${role}`): LoginResponse {
  return { access_token: `${TOKEN}-${id}`, token_type: 'bearer', expires_in: 3600, user: { id, username: `${role}1`, role } }
}

function apiError(status: number, code: components['schemas']['ErrorCode'], retryAfter?: number): ApiError {
  return new ApiError(status, { code, message: 'x' }, retryAfter)
}

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })
}

let pinia: Pinia

beforeEach(() => {
  sessionStorage.clear()
  localStorage.clear()
  pinia = createPinia()
  setActivePinia(pinia)
})

afterEach(() => {
  vi.restoreAllMocks()
})

// ---------------------------------------------------------------- 会话存储

describe('H13 会话存储', () => {
  it('登录后令牌与用户只写 sessionStorage，不写 localStorage 与 Cookie', () => {
    const session = useSessionStore()
    session.signIn(loginResponse('teacher'))
    expect(session.accessToken).toBe(`${TOKEN}-u_teacher`)
    expect(session.role).toBe('teacher')
    const stored = JSON.parse(sessionStorage.getItem(SESSION_STORAGE_KEY) ?? 'null')
    expect(stored).toEqual({
      access_token: `${TOKEN}-u_teacher`,
      user: { id: 'u_teacher', username: 'teacher1', role: 'teacher' },
    })
    expect(localStorage.length).toBe(0)
    expect(document.cookie).toBe('')
  })

  it('刷新页面（新的 store）从 sessionStorage 恢复会话', () => {
    useSessionStore().signIn(loginResponse('student'))
    setActivePinia(createPinia())
    const restored = useSessionStore()
    expect(restored.role).toBe('student')
    expect(restored.accessToken).toBe(`${TOKEN}-u_student`)
  })

  it.each([
    ['非 JSON', '{not json'],
    ['缺令牌', JSON.stringify({ user: { id: 'u', username: 'a', role: 'teacher' } })],
    ['空令牌', JSON.stringify({ access_token: '', user: { id: 'u', username: 'a', role: 'teacher' } })],
    ['未知角色', JSON.stringify({ access_token: 't', user: { id: 'u', username: 'a', role: 'admin' } })],
    ['缺用户', JSON.stringify({ access_token: 't' })],
  ])('存储内容无效（%s）视为未登录并清除', (_, raw) => {
    sessionStorage.setItem(SESSION_STORAGE_KEY, raw)
    const session = useSessionStore()
    expect(session.accessToken).toBeNull()
    expect(session.role).toBeNull()
    expect(sessionStorage.getItem(SESSION_STORAGE_KEY)).toBeNull()
  })

  it('sessionStorage 不可用时会话仍在内存中生效', () => {
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new DOMException('quota', 'QuotaExceededError')
    })
    const session = useSessionStore()
    expect(() => session.signIn(loginResponse('teacher'))).not.toThrow()
    expect(session.role).toBe('teacher')
  })

  it('退出清会话并清空课程上下文，旧作用域失效（B04-R01）', () => {
    const session = useSessionStore()
    const course = useCourseStore()
    session.signIn(loginResponse('teacher'))
    course.selectCourse('c1')
    const scope = course.beginRequest()
    course.appendChatTurns(scope, { role: 'user', content: '什么是栈？' })

    session.signOut()

    expect(session.accessToken).toBeNull()
    expect(session.role).toBeNull()
    expect(sessionStorage.getItem(SESSION_STORAGE_KEY)).toBeNull()
    expect(course.courseId).toBeNull()
    expect(course.chatHistory).toEqual([])
    expect(scope.signal.aborted).toBe(true)
    expect(scope.isCurrent()).toBe(false)
  })

  it('同一标签页换账号登录时清空上一账号的课程上下文（B04-R01）', () => {
    const session = useSessionStore()
    const course = useCourseStore()
    session.signIn(loginResponse('teacher', 'u1'))
    course.selectCourse('c1')
    const scope = course.beginRequest()

    session.signIn(loginResponse('student', 'u2'))

    expect(course.courseId).toBeNull()
    expect(scope.isCurrent()).toBe(false)
    // 再选同一课程也会开启新的作用域，不沿用上一账号的状态
    course.selectCourse('c1')
    expect(course.beginRequest().isCurrent()).toBe(true)
    expect(scope.isCurrent()).toBe(false)
  })
})

// ---------------------------------------------------------------- HTTP 接线

describe('H13 令牌注入与 401', () => {
  it('受保护请求带 Bearer 令牌；登录请求不带令牌', async () => {
    const session = useSessionStore()
    session.signIn(loginResponse('teacher'))
    const seen: Array<{ url: string; auth: string | null; body: unknown }> = []
    const fetch: FetchLike = async (url, init = {}) => {
      const headers = new Headers(init.headers)
      seen.push({ url, auth: headers.get('Authorization'), body: init.body })
      return url.endsWith('/auth/login') ? json(loginResponse('student')) : json([])
    }
    const client = createSessionHttpClient(session, () => undefined, { fetch })
    await client.request('get', '/api/v1/courses')
    await createAuthApi(client).login({ username: 'student1', password: PASSWORD })
    expect(seen[0]).toMatchObject({ url: '/api/v1/courses', auth: `Bearer ${TOKEN}-u_teacher` })
    expect(seen[1].url).toBe('/api/v1/auth/login')
    expect(seen[1].auth).toBeNull()
    expect(JSON.parse(String(seen[1].body))).toEqual({ username: 'student1', password: PASSWORD })
    // 令牌不进 URL
    expect(seen.every((call) => !call.url.includes(TOKEN))).toBe(true)
  })

  it('受保护接口 401：清会话与课程上下文，通知回登录页，仍抛出错误', async () => {
    const session = useSessionStore()
    const course = useCourseStore()
    session.signIn(loginResponse('teacher'))
    course.selectCourse('c1')
    const expired = vi.fn()
    const fetch: FetchLike = async () => json({ code: 'UNAUTHENTICATED', message: '未认证' }, 401)
    const client = createSessionHttpClient(session, expired, { fetch })

    await expect(client.request('get', '/api/v1/courses')).rejects.toBeInstanceOf(ApiError)

    expect(expired).toHaveBeenCalledTimes(1)
    expect(session.accessToken).toBeNull()
    expect(sessionStorage.getItem(SESSION_STORAGE_KEY)).toBeNull()
    expect(course.courseId).toBeNull()
  })

  it('登录接口 401 是凭据错误，不清会话、不跳转', async () => {
    const session = useSessionStore()
    session.signIn(loginResponse('teacher'))
    const expired = vi.fn()
    const fetch: FetchLike = async () => json({ code: 'UNAUTHENTICATED', message: '用户名或密码错误' }, 401)
    const auth = createAuthApi(createSessionHttpClient(session, expired, { fetch }))

    await expect(auth.login({ username: 'x', password: PASSWORD })).rejects.toBeInstanceOf(ApiError)

    expect(expired).not.toHaveBeenCalled()
    expect(session.role).toBe('teacher')
  })
})

// ---------------------------------------------------------------- 登录页

async function mountApp({ login: impl, path = '/' }: { login?: AuthApi['login']; path?: string } = {}) {
  const session = useSessionStore(pinia)
  const router = createAppRouter({
    history: createMemoryHistory(),
    getAccountRole: () => session.role,
    loginComponent: LoginView,
  })
  const login = vi.fn<AuthApi['login']>(impl ?? (async () => loginResponse('teacher')))
  const auth: AuthApi = { login }
  await router.push(path)
  await router.isReady()
  const wrapper = mount(App, { global: { plugins: [pinia, router], provide: { [AUTH_API_KEY]: auth } } })
  return { wrapper, router, session, login }
}

type Mounted = Awaited<ReturnType<typeof mountApp>>

async function fillAndSubmit(wrapper: Mounted['wrapper'], username = 'teacher1', password = PASSWORD) {
  await wrapper.get('input[name="username"]').setValue(username)
  await wrapper.get('input[name="password"]').setValue(password)
  await wrapper.get('form').trigger('submit')
  await flushPromises()
}

function failWith(error: Error): AuthApi['login'] {
  return async () => {
    throw error
  }
}

describe('H13 登录页', () => {
  it('未登录访问受保护页面：回到登录页，显示未登录提示与登录表单', async () => {
    const { wrapper, router } = await mountApp({ path: '/teacher' })
    expect(router.currentRoute.value.name).toBe(ROOT_ROUTE)
    expect(wrapper.text()).toContain('未登录')
    expect(wrapper.find('form').exists()).toBe(true)
    expect(wrapper.get('input[name="password"]').attributes('type')).toBe('password')
    expect(wrapper.get('input[name="username"]').attributes('autocomplete')).toBe('username')
    expect(wrapper.get('input[name="password"]').attributes('autocomplete')).toBe('current-password')
  })

  it.each([
    ['teacher', '/teacher', '教师首页'],
    ['student', '/student', '学生首页'],
  ] as const)('%s 登录后按 user.role 进入 %s', async (role, path, title) => {
    const { wrapper, router, session, login } = await mountApp({ login: async () => loginResponse(role) })
    await fillAndSubmit(wrapper)
    expect(login).toHaveBeenCalledWith({ username: 'teacher1', password: PASSWORD })
    expect(session.role).toBe(role)
    expect(router.currentRoute.value.path).toBe(path)
    expect(wrapper.get('h2').text()).toBe(title)
  })

  it('401：提示用户名或密码错误，保持未登录', async () => {
    const { wrapper, router, session } = await mountApp({ login: failWith(apiError(401, 'UNAUTHENTICATED')) })
    await fillAndSubmit(wrapper)
    expect(wrapper.get('[data-test="login-error"]').text()).toContain('用户名或密码错误')
    expect(session.accessToken).toBeNull()
    expect(router.currentRoute.value.name).toBe(ROOT_ROUTE)
    // 失败后清空口令输入框，用户名保留
    expect((wrapper.get('input[name="password"]').element as HTMLInputElement).value).toBe('')
    expect((wrapper.get('input[name="username"]').element as HTMLInputElement).value).toBe('teacher1')
  })

  it('429：提示尝试过于频繁并给出等待秒数', async () => {
    const { wrapper } = await mountApp({ login: failWith(apiError(429, 'RATE_LIMITED', 30)) })
    await fillAndSubmit(wrapper)
    const text = wrapper.get('[data-test="login-error"]').text()
    expect(text).toContain('过于频繁')
    expect(text).toContain('30 秒')
    expect(text).not.toContain('用户名或密码错误')
  })

  it('429 无 Retry-After：提示稍后再试', async () => {
    const { wrapper } = await mountApp({ login: failWith(apiError(429, 'RATE_LIMITED')) })
    await fillAndSubmit(wrapper)
    const text = wrapper.get('[data-test="login-error"]').text()
    expect(text).toContain('过于频繁')
    expect(text).toContain('稍后')
  })

  it.each([
    ['网络错误', new NetworkError(new TypeError('fetch failed'))],
    ['超时', new TimeoutError(30_000)],
  ])('%s：提示无法连接服务器', async (_, error) => {
    const { wrapper } = await mountApp({ login: failWith(error) })
    await fillAndSubmit(wrapper)
    expect(wrapper.get('[data-test="login-error"]').text()).toContain('无法连接服务器')
  })

  it('其他错误：给出通用失败提示，不回显服务端 message', async () => {
    const { wrapper } = await mountApp({
      login: failWith(new ApiError(500, { code: 'INTERNAL_ERROR', message: 'stack trace here' })),
    })
    await fillAndSubmit(wrapper)
    const text = wrapper.get('[data-test="login-error"]').text()
    expect(text).toContain('登录失败')
    expect(text).not.toContain('stack trace')
  })

  it.each([
    ['', PASSWORD],
    ['   ', PASSWORD],
    ['teacher1', ''],
  ])('用户名或口令为空（%j）：不发请求，提示填写', async (username, password) => {
    const { wrapper, login } = await mountApp()
    await fillAndSubmit(wrapper, username, password)
    expect(login).not.toHaveBeenCalled()
    expect(wrapper.get('[data-test="login-error"]').text()).toContain('请输入用户名和密码')
  })

  it('提交中按钮禁用，重复提交只发一次请求', async () => {
    let resolve!: (value: LoginResponse) => void
    const { wrapper, login } = await mountApp({ login: () => new Promise<LoginResponse>((r) => (resolve = r)) })
    await wrapper.get('input[name="username"]').setValue('teacher1')
    await wrapper.get('input[name="password"]').setValue(PASSWORD)
    await wrapper.get('form').trigger('submit')
    await wrapper.get('form').trigger('submit')
    expect(login).toHaveBeenCalledTimes(1)
    expect(wrapper.get('button[type="submit"]').attributes('disabled')).toBeDefined()
    resolve(loginResponse('teacher'))
    await flushPromises()
  })

  it('口令与令牌不写日志，口令不进存储', async () => {
    const spies = (['log', 'info', 'warn', 'error', 'debug'] as const).map((level) =>
      vi.spyOn(console, level).mockImplementation(() => undefined),
    )
    const ok = await mountApp()
    await fillAndSubmit(ok.wrapper)
    ok.session.signOut()
    const failing = await mountApp({ login: failWith(apiError(401, 'UNAUTHENTICATED')) })
    await fillAndSubmit(failing.wrapper)
    const logged = spies.flatMap((spy) => spy.mock.calls.flat().map((arg) => String(arg)))
    expect(logged.some((line) => line.includes(PASSWORD) || line.includes(TOKEN))).toBe(false)
    expect(JSON.stringify({ ...sessionStorage })).not.toContain(PASSWORD)
  })

  it('401 会话过期后回到登录页并显示未登录提示', async () => {
    const { wrapper, router, session } = await mountApp({ login: async () => loginResponse('teacher') })
    await fillAndSubmit(wrapper)
    expect(router.currentRoute.value.path).toBe('/teacher')

    const fetch: FetchLike = async () => json({ code: 'UNAUTHENTICATED', message: '未认证' }, 401)
    const client = createSessionHttpClient(
      session,
      () => void router.replace({ name: ROOT_ROUTE, query: { notice: NOTICE_UNAUTHENTICATED } }),
      { fetch },
    )
    await expect(client.request('get', '/api/v1/courses')).rejects.toBeInstanceOf(ApiError)
    await flushPromises()

    expect(router.currentRoute.value.name).toBe(ROOT_ROUTE)
    expect(wrapper.text()).toContain('未登录')
    expect(wrapper.find('form').exists()).toBe(true)
    expect(wrapper.findAll('h2').map((h) => h.text())).not.toContain('教师首页')
  })
})
