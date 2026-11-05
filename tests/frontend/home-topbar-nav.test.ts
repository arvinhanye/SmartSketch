import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import { defineComponent, h } from 'vue'
import { createMemoryHistory } from 'vue-router'
import App from '../../src/frontend/src/App.vue'
import { COURSES_API_KEY } from '../../src/frontend/src/api/courses'
import { MODEL_CONFIG_API_KEY } from '../../src/frontend/src/api/modelConfig'
import { createAppRouter } from '../../src/frontend/src/router'
import { useSessionStore } from '../../src/frontend/src/stores/session'

// UI-PINE-01 后续：课程之外的页面（课程列表、模型 API 设置）侧栏只剩两项，没有存在的必要。
// 这些页面去掉左侧栏，顶栏放品牌与「模型 API」入口；进入课程后侧栏保持原样。

const Page = defineComponent({ render: () => h('p', '内容') })
const innerWidth = window.innerWidth
beforeEach(() => sessionStorage.clear())
afterEach(() => {
  Object.defineProperty(window, 'innerWidth', { configurable: true, value: innerWidth })
})

async function mountAt(path: string, width = 1440) {
  Object.defineProperty(window, 'innerWidth', { configurable: true, value: width })
  const pinia = createPinia()
  setActivePinia(pinia)
  const session = useSessionStore()
  session.signIn({ access_token: 'test-token', token_type: 'bearer', expires_in: 3600, user: { id: 'u1', username: 'teacher', role: 'teacher' } })
  const router = createAppRouter({ history: createMemoryHistory(), getAccountRole: () => session.role, coursesComponent: Page, settingsComponent: Page, materialsComponent: Page, membersComponent: Page, reviewComponent: Page, chatComponent: Page, teacherGraphComponent: Page })
  await router.push(path)
  await router.isReady()
  const courses = { list: async () => [], get: async (cid: string) => ({ id: cid, name: '数据结构', status: 'published', my_role: 'teacher', published_version: 1, created_at: '2026-09-01T00:00:00Z' }) }
  const wrapper = mount(App, {
    attachTo: document.body,
    global: { plugins: [pinia, router], provide: { [COURSES_API_KEY as symbol]: courses, [MODEL_CONFIG_API_KEY as symbol]: { get: async () => ({ runtime_mode: 'personal', configured: false }) } } },
  })
  await flushPromises()
  return wrapper
}

describe('课程之外的页面不用侧栏', () => {
  it('课程列表：没有左侧栏和抽屉按钮；顶栏有品牌与模型 API 入口（带未配置标记）', async () => {
    const wrapper = await mountAt('/teacher')
    expect(wrapper.find('nav.app-rail').exists()).toBe(false)
    expect(wrapper.find('[data-test="app-menu"]').exists()).toBe(false)
    expect(wrapper.get('.app').classes()).toContain('app--no-rail')
    expect(wrapper.get('[data-test="app-brand"]').text()).toContain('智绘学途')
    const settings = wrapper.get('.app-topbar [data-test="nav-model-settings"]')
    expect(settings.text()).toContain('模型 API')
    expect(settings.attributes('aria-current')).toBeUndefined()
    expect(wrapper.find('.app-topbar [data-test="nav-model-settings-pending"]').exists()).toBe(true)
    wrapper.unmount()
  })

  it('模型 API 设置页：入口标为当前页；窄屏同样没有抽屉按钮', async () => {
    const wrapper = await mountAt('/settings/model', 800)
    expect(wrapper.find('nav.app-rail').exists()).toBe(false)
    expect(wrapper.find('[data-test="app-menu"]').exists()).toBe(false)
    expect(wrapper.get('.app-topbar [data-test="nav-model-settings"]').attributes('aria-current')).toBe('page')
    wrapper.unmount()
  })

  it('进入课程后侧栏保持原样，顶栏不放品牌与模型 API 入口', async () => {
    const wrapper = await mountAt('/courses/c1')
    expect(wrapper.find('nav.app-rail').exists()).toBe(true)
    expect(wrapper.get('.app').classes()).not.toContain('app--no-rail')
    expect(wrapper.find('[data-test="app-brand"]').exists()).toBe(false)
    expect(wrapper.find('.app-topbar [data-test="nav-model-settings"]').exists()).toBe(false)
    wrapper.unmount()
  })
})
