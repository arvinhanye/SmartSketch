import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia, type Pinia } from 'pinia'
import { createMemoryHistory } from 'vue-router'
import { existsSync, readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import App from '../../src/frontend/src/App.vue'
import { AUTH_API_KEY, type AuthApi } from '../../src/frontend/src/api/auth'
import { createAppRouter } from '../../src/frontend/src/router/index.ts'
import { useSessionStore } from '../../src/frontend/src/stores/session'
import LoginView from '../../src/frontend/src/views/LoginView.vue'
import RegisterView from '../../src/frontend/src/views/RegisterView.vue'

// 用户反馈：学生注册页左侧（随机漂浮的图谱气泡 + 粗体大标题）不好看。
// 改为与登录页完全相同的左侧品牌区（「把知识连起来，让学习有迹可循。」+ 插画），表单也沿用登录页的版式，两页保持一致。
// 注册的校验与流程由 adr079.test.ts 覆盖，这里只守外观与结构。
const here = dirname(fileURLToPath(import.meta.url))
const src = (p: string) => resolve(here, '../../src/frontend/src', p)

let pinia: Pinia
beforeEach(() => {
  sessionStorage.clear()
  pinia = createPinia()
  setActivePinia(pinia)
})

async function mountRegister() {
  const session = useSessionStore(pinia)
  const router = createAppRouter({
    history: createMemoryHistory(),
    getAccountRole: () => session.role,
    loginComponent: LoginView,
    registerComponent: RegisterView,
  })
  const auth: AuthApi = { login: vi.fn(), register: vi.fn() }
  await router.push('/register')
  await router.isReady()
  const wrapper = mount(App, { global: { plugins: [pinia, router], provide: { [AUTH_API_KEY]: auth } } })
  await flushPromises()
  return wrapper
}

describe('注册页外观', () => {
  it('左侧品牌区与登录页相同：同一个标题、同一幅插画；不再有随机漂浮的图谱气泡', async () => {
    const wrapper = await mountRegister()
    expect(wrapper.find('.auth-layout--editorial').exists()).toBe(true)
    expect(wrapper.get('.login-brand__headline').text()).toContain('把知识连起来')
    expect(wrapper.find('[data-test="login-knowledge-art"]').exists()).toBe(true)
    expect(wrapper.find('.auth-layout__art').exists()).toBe(false)
    expect(wrapper.find('[data-test="auth-graph"]').exists()).toBe(false)
  })

  it('页面外壳与登录页一样锁在视口内（窗口矮时只有表单栏内部滚动，不出现整页滚动条）', async () => {
    const wrapper = await mountRegister()
    expect(wrapper.get('.app').classes()).toContain('app--login')
  })

  it('表单：保留注册所需的字段名与 data-test，口令可显隐，输入框有占位提示', async () => {
    const wrapper = await mountRegister()
    expect(wrapper.findAll('form')).toHaveLength(1)
    expect(wrapper.get('form').attributes('data-test')).toBe('register-form')
    const username = wrapper.get('input[name="username"]')
    const password = wrapper.get('input[name="password"]')
    const confirm = wrapper.get('input[name="confirm"]')
    for (const input of [username, password, confirm]) expect(input.attributes('placeholder')).toBeTruthy()
    expect(password.attributes('type')).toBe('password')
    expect(confirm.attributes('type')).toBe('password')

    const eye = wrapper.get('button[aria-controls]')
    expect(eye.attributes('aria-label')).toBe('显示口令')
    expect(eye.attributes('aria-pressed')).toBe('false')
    await eye.trigger('click')
    expect(password.attributes('type')).toBe('text')
    expect(confirm.attributes('type')).toBe('text')
    expect(eye.attributes('aria-label')).toBe('隐藏口令')
    expect(eye.attributes('aria-pressed')).toBe('true')
    await eye.trigger('click')
    expect(password.attributes('type')).toBe('password')
  })

  it('提交按钮、去登录的链接与「教师账号由管理员开通」的说明都在', async () => {
    const wrapper = await mountRegister()
    expect(wrapper.get('button[type="submit"]').text()).toContain('注册并登录')
    expect(wrapper.text()).toContain('已有账号？')
    expect(wrapper.text()).toContain('教师账号由管理员开通')
  })
})

describe('旧的注册页品牌区已移除', () => {
  it('AuthLayout 组件文件不再存在，注册页不再引用它', () => {
    expect(existsSync(src('components/AuthLayout.vue'))).toBe(false)
    expect(readFileSync(src('views/RegisterView.vue'), 'utf8')).not.toContain('AuthLayout')
    expect(readFileSync(src('views/RegisterView.vue'), 'utf8')).toContain('LoginLayout')
  })
})
