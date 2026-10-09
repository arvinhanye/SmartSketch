import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia, type Pinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import { defineComponent, h } from 'vue'
import { createMemoryHistory } from 'vue-router'
import App from '../../src/frontend/src/App.vue'
import { COURSES_API_KEY } from '../../src/frontend/src/api/courses'
import { createAppRouter, ROOT_ROUTE } from '../../src/frontend/src/router/index.ts'
import { useSessionStore } from '../../src/frontend/src/stores/session'

const Page = (text: string) => defineComponent({ render: () => h('p', text) })

let pinia: Pinia
beforeEach(() => {
  sessionStorage.clear()
  pinia = createPinia()
  setActivePinia(pinia)
})
afterEach(() => {
  Object.defineProperty(window, 'innerWidth', { configurable: true, value: 1024 })
})

async function mountAt(path: string, width: number) {
  Object.defineProperty(window, 'innerWidth', { configurable: true, value: width })
  const session = useSessionStore(pinia)
  session.signIn({ access_token: 'tok', token_type: 'bearer', expires_in: 3600, user: { id: 'u1', username: 'li_xiaoming', role: 'student' } })
  const router = createAppRouter({
    history: createMemoryHistory(),
    getAccountRole: () => session.role,
    coursesComponent: Page('课程'),
    studentGraphComponent: Page('图谱页'),
  })
  await router.push(path)
  await router.isReady()
  // 课程内角色决定导航里有没有「知识图谱与学习路径」（L15）：读到 my_role = student 后才出现
  const courses = {
    list: async () => [],
    create: async () => {
      throw new Error('不应创建课程')
    },
    get: async (cid: string) => ({ id: cid, name: '数据结构', status: 'published', my_role: 'student', published_version: 1, created_at: '2026-09-01T00:00:00Z' }),
  }
  const wrapper = mount(App, { attachTo: document.body, global: { plugins: [pinia, router], provide: { [COURSES_API_KEY as symbol]: courses } } })
  await flushPromises()
  return { wrapper, router, session }
}

describe('图谱与已升级课程页的暗色外壳', () => {
  it('图谱页：顶栏（面包屑、用户、退出）+ 64px 图标栏，没有旧侧栏；当前页是 aria-current 的最后一项', async () => {
    const { wrapper } = await mountAt('/courses/c1/graph', 1440)
    expect(wrapper.get('.app').classes()).toContain('app--graph')
    expect(wrapper.find('.app-sidebar').exists()).toBe(false)
    const crumb = wrapper.get('nav[aria-label="当前位置"]')
    expect(crumb.text()).toContain('我的课程')
    expect(crumb.get('[aria-current="page"]').text()).toBe('知识图谱')
    expect(wrapper.get('[data-test="app-user"]').text()).toContain('li_xiaoming')
    const rail = wrapper.get('nav.app-rail')
    expect(rail.findAll('a').length).toBeGreaterThan(0)
    expect(rail.get('[aria-current="page"]').attributes('title')).toBe('知识图谱与学习路径')
    wrapper.unmount()
  })

  it('图标栏可展开显示名称，展开按钮有可访问名称与状态', async () => {
    const { wrapper } = await mountAt('/courses/c1/graph', 1440)
    const toggle = wrapper.get('.app-rail__toggle')
    expect(toggle.attributes('aria-label')).toBe('展开导航，显示名称')
    expect(toggle.attributes('aria-expanded')).toBe('false')
    await toggle.trigger('click')
    expect(wrapper.get('.app-rail').classes()).toContain('is-expanded')
    expect(wrapper.get('.app-rail').text()).toContain('知识图谱与学习路径')
    expect(wrapper.get('.app-rail__toggle').attributes('aria-expanded')).toBe('true')
    wrapper.unmount()
  })

  it('窄屏（<1024）没有图标栏，顶栏出现打开导航抽屉的按钮；抽屉可用 Esc 关闭并把焦点还给按钮', async () => {
    const { wrapper } = await mountAt('/courses/c1/graph', 800)
    expect(wrapper.find('nav.app-rail').exists()).toBe(false)
    const menu = wrapper.get('[data-test="app-menu"]')
    await menu.trigger('click')
    await flushPromises()
    const drawer = wrapper.get('nav.app-drawer')
    expect(drawer.attributes('role')).toBe('dialog')
    expect(drawer.text()).toContain('知识图谱与学习路径')
    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))
    await flushPromises()
    expect(wrapper.find('nav.app-drawer').exists()).toBe(false)
    expect(document.activeElement).toBe(menu.element)
    wrapper.unmount()
  })

  it('退出登录回到登录页', async () => {
    const { wrapper, router, session } = await mountAt('/courses/c1/graph', 1440)
    await wrapper.get('[data-test="app-sign-out"]').trigger('click')
    await flushPromises()
    expect(session.role).toBeNull()
    expect(router.currentRoute.value.name).toBe(ROOT_ROUTE)
    wrapper.unmount()
  })

  it('课程主页使用暗色外壳与正确面包屑（本次推广）', async () => {
    const { wrapper } = await mountAt('/courses/c1', 1440)
    expect(wrapper.get('.app').classes()).toContain('app--graph')
    expect(wrapper.find('.app-sidebar').exists()).toBe(false)
    expect(wrapper.find('.app-topbar').exists()).toBe(true)
    expect(wrapper.find('nav.app-rail').exists()).toBe(true)
    expect(wrapper.get('nav[aria-label="当前位置"] [aria-current="page"]').text()).toBe('课程概览')
    expect(wrapper.get('nav[aria-label="当前位置"]').text()).toContain('数据结构')
    wrapper.unmount()
  })
})
