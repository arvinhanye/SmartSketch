import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { createMemoryHistory } from 'vue-router'
import { describe, expect, it } from 'vitest'
import type { components } from '../../src/contracts/v1/generated/typescript/openapi'
import App from '../../src/frontend/src/App.vue'
import { createAppRouter } from '../../src/frontend/src/router/index.ts'

type Role = components['schemas']['Role']

// 按给定账号类型建路由、导航到 path，再把路由装进 App 挂载
async function visit(path: string, role: Role | null) {
  const router = createAppRouter({ history: createMemoryHistory(), getAccountRole: () => role })
  await router.push(path)
  await router.isReady()
  const wrapper = mount(App, { global: { plugins: [router] } })
  return { router, wrapper }
}

// 角色首页各有一个 h2 标题；提示文字里会提到页面名，所以只按标题判断渲染了哪个首页
function headings(wrapper: VueWrapper) {
  return wrapper.findAll('h2').map((h) => h.text())
}

const TEACHER_TITLE = '教师首页'
const STUDENT_TITLE = '学生首页'

describe('B03 路由壳与角色入口', () => {
  it('外壳保留应用标题', async () => {
    const { wrapper } = await visit('/', 'teacher')
    expect(wrapper.get('h1').text()).toBe('智绘学途')
  })

  it('教师访问 / 进入 /teacher', async () => {
    const { router, wrapper } = await visit('/', 'teacher')
    expect(router.currentRoute.value.path).toBe('/teacher')
    expect(wrapper.get('h2').text()).toBe(TEACHER_TITLE)
    expect(wrapper.find('[role="alert"]').exists()).toBe(false)
  })

  it('学生访问 / 进入 /student', async () => {
    const { router, wrapper } = await visit('/', 'student')
    expect(router.currentRoute.value.path).toBe('/student')
    expect(wrapper.get('h2').text()).toBe(STUDENT_TITLE)
    expect(wrapper.find('[role="alert"]').exists()).toBe(false)
  })

  it('本人首页可直接访问且无提示', async () => {
    const { router, wrapper } = await visit('/teacher', 'teacher')
    expect(router.currentRoute.value.path).toBe('/teacher')
    expect(wrapper.find('[role="alert"]').exists()).toBe(false)
  })

  it('学生直接访问 /teacher：回到 /student 并提示原因', async () => {
    const { router, wrapper } = await visit('/teacher', 'student')
    expect(router.currentRoute.value.path).toBe('/student')
    expect(headings(wrapper)).toEqual([STUDENT_TITLE])
    const alert = wrapper.get('[role="alert"]')
    expect(alert.text()).toContain('教师首页')
    expect(alert.text()).toContain('学生')
  })

  it('教师直接访问 /student：回到 /teacher 并提示原因', async () => {
    const { router, wrapper } = await visit('/student', 'teacher')
    expect(router.currentRoute.value.path).toBe('/teacher')
    expect(headings(wrapper)).toEqual([TEACHER_TITLE])
    const alert = wrapper.get('[role="alert"]')
    expect(alert.text()).toContain('学生首页')
    expect(alert.text()).toContain('教师')
  })

  it.each(['/', '/teacher', '/student', '/no-such-page'])(
    '未登录访问 %s：显示未登录提示，不渲染任何角色首页',
    async (path) => {
      const { router, wrapper } = await visit(path, null)
      expect(router.currentRoute.value.path).toBe('/')
      expect(wrapper.get('[role="alert"]').text()).toContain('未登录')
      expect(headings(wrapper)).toEqual([])
    },
  )

  it('未知路径回到 / 再按账号类型进入首页', async () => {
    const { router, wrapper } = await visit('/no-such-page', 'student')
    expect(router.currentRoute.value.path).toBe('/student')
    expect(wrapper.get('h2').text()).toBe(STUDENT_TITLE)
  })

  it('路由 meta 标注页面所需账号类型', async () => {
    const { router } = await visit('/', 'teacher')
    expect(router.resolve('/teacher').meta.accountRole).toBe('teacher')
    expect(router.resolve('/student').meta.accountRole).toBe('student')
    expect(router.resolve('/').meta.accountRole).toBeUndefined()
  })

  it('离开被拒页面后提示消失', async () => {
    const { router, wrapper } = await visit('/teacher', 'student')
    expect(wrapper.find('[role="alert"]').exists()).toBe(true)
    await router.push('/student')
    await flushPromises()
    expect(wrapper.find('[role="alert"]').exists()).toBe(false)
  })
})
