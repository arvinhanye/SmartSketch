import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia, type Pinia } from 'pinia'
import { createMemoryHistory } from 'vue-router'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { components } from '../../src/contracts/v1/generated/typescript/openapi'
import App from '../../src/frontend/src/App.vue'
import { AUTH_API_KEY, createAuthApi, type AuthApi } from '../../src/frontend/src/api/auth'
import { ApiError, createHttpClient, type FetchLike } from '../../src/frontend/src/api/http'
import { createAppRouter, REGISTER_ROUTE, ROOT_ROUTE } from '../../src/frontend/src/router/index.ts'
import { useSessionStore } from '../../src/frontend/src/stores/session'
import LoginView from '../../src/frontend/src/views/LoginView.vue'
import RegisterView from '../../src/frontend/src/views/RegisterView.vue'

type LoginResponse = components['schemas']['LoginResponse']

const PASSWORD = 'register-secret-079'

function studentResponse(username = 'li_xiaoming'): LoginResponse {
  return { access_token: 'opaque-token', token_type: 'bearer', expires_in: 3600, user: { id: 'u1', username, role: 'student' } }
}

let pinia: Pinia

beforeEach(() => {
  sessionStorage.clear()
  pinia = createPinia()
  setActivePinia(pinia)
})

async function mountApp(register: AuthApi['register'], path = '/register') {
  const session = useSessionStore(pinia)
  const router = createAppRouter({
    history: createMemoryHistory(),
    getAccountRole: () => session.role,
    loginComponent: LoginView,
    registerComponent: RegisterView,
  })
  const auth: AuthApi = { login: vi.fn<AuthApi['login']>(), register: vi.fn(register) }
  await router.push(path)
  await router.isReady()
  const wrapper = mount(App, { global: { plugins: [pinia, router], provide: { [AUTH_API_KEY]: auth } } })
  return { wrapper, router, session, auth }
}

async function fill(wrapper: Awaited<ReturnType<typeof mountApp>>['wrapper'], username: string, password: string, confirm = password) {
  await wrapper.get('input[name="username"]').setValue(username)
  await wrapper.get('input[name="password"]').setValue(password)
  await wrapper.get('input[name="confirm"]').setValue(confirm)
  await wrapper.get('form').trigger('submit')
  await flushPromises()
}

describe('ADR-079 学生自助注册页', () => {
  it('未登录可直接打开注册页，登录页有注册入口', async () => {
    const { wrapper, router } = await mountApp(async () => studentResponse(), '/')
    expect(router.currentRoute.value.name).toBe(ROOT_ROUTE)
    const link = wrapper.get('[data-test="login-register-link"]')
    expect(wrapper.text()).toContain('教师账号由管理员开通')
    await link.trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.name).toBe(REGISTER_ROUTE)
    expect(wrapper.get('input[name="password"]').attributes('autocomplete')).toBe('new-password')
  })

  it('成功：只提交用户名和口令，登录后进入学生首页，侧栏显示账号', async () => {
    const { wrapper, router, session, auth } = await mountApp(async () => studentResponse())
    await fill(wrapper, ' Li_Xiaoming ', PASSWORD)
    expect(auth.register).toHaveBeenCalledWith({ username: 'Li_Xiaoming', password: PASSWORD })
    expect(session.role).toBe('student')
    expect(router.currentRoute.value.path).toBe('/student')
    expect(wrapper.get('[data-test="app-user"]').text()).toContain('li_xiaoming')
  })

  it.each([
    ['ab', PASSWORD, PASSWORD, 'register-username-error'],
    ['有中文', PASSWORD, PASSWORD, 'register-username-error'],
    ['valid_name', 'short', 'short', 'register-password-error'],
    ['valid_name', PASSWORD, `${PASSWORD}x`, 'register-confirm-error'],
  ])('本地校验不通过时不发请求：%s', async (username, password, confirm, testId) => {
    const { wrapper, auth } = await mountApp(async () => studentResponse())
    await fill(wrapper, username, password, confirm)
    expect(auth.register).not.toHaveBeenCalled()
    expect(wrapper.find(`[data-test="${testId}"]`).exists()).toBe(true)
  })

  it('409 USERNAME_TAKEN：在用户名下提示已占用，保持未登录', async () => {
    const { wrapper, router, session } = await mountApp(async () => {
      throw new ApiError(409, { code: 'USERNAME_TAKEN', message: 'x' })
    })
    await fill(wrapper, 'taken_name', PASSWORD)
    expect(wrapper.get('[data-test="register-username-error"]').text()).toContain('已被占用')
    expect(session.accessToken).toBeNull()
    expect(router.currentRoute.value.name).toBe(REGISTER_ROUTE)
    // 换一个用户名后提示消失
    await wrapper.get('input[name="username"]').setValue('other_name')
    expect(wrapper.find('[data-test="register-username-error"]').exists()).toBe(false)
  })

  it('429：提示等待秒数，不回显服务端 message', async () => {
    const { wrapper } = await mountApp(async () => {
      throw new ApiError(429, { code: 'RATE_LIMITED', message: 'server-text' }, 42)
    })
    await fill(wrapper, 'someone', PASSWORD)
    const text = wrapper.get('[data-test="register-error"]').text()
    expect(text).toContain('42 秒')
    expect(text).not.toContain('server-text')
  })

  it('已登录访问注册页回到本账号首页', async () => {
    const session = useSessionStore(pinia)
    session.signIn(studentResponse())
    const { router } = await mountApp(async () => studentResponse())
    expect(router.currentRoute.value.path).toBe('/student')
  })

  it('退出登录清会话并回登录页', async () => {
    const session = useSessionStore(pinia)
    session.signIn(studentResponse())
    const { wrapper, router } = await mountApp(async () => studentResponse(), '/student')
    await wrapper.get('[data-test="app-sign-out"]').trigger('click')
    await flushPromises()
    expect(session.accessToken).toBeNull()
    expect(router.currentRoute.value.name).toBe(ROOT_ROUTE)
    expect(wrapper.find('[data-test="app-sign-out"]').exists()).toBe(false)
  })
})

describe('ADR-079 注册接口客户端', () => {
  it('POST /api/v1/auth/register 不带令牌，409 不清会话', async () => {
    const seen: Array<{ url: string; auth: string | null }> = []
    const onUnauthenticated = vi.fn()
    const fetchImpl: FetchLike = async (input, init) => {
      seen.push({ url: String(input), auth: new Headers(init?.headers).get('Authorization') })
      return new Response(JSON.stringify({ code: 'USERNAME_TAKEN', message: 'x' }), {
        status: 409,
        headers: { 'Content-Type': 'application/json' },
      })
    }
    const client = createHttpClient({ fetch: fetchImpl, getAccessToken: () => 'stale-token', onUnauthenticated })
    await expect(createAuthApi(client).register({ username: 'abc', password: PASSWORD })).rejects.toMatchObject({
      status: 409,
      code: 'USERNAME_TAKEN',
    })
    expect(seen).toEqual([{ url: '/api/v1/auth/register', auth: null }])
    expect(onUnauthenticated).not.toHaveBeenCalled()
  })
})
