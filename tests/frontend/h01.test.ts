import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia, type Pinia } from 'pinia'
import { createMemoryHistory } from 'vue-router'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { components } from '../../src/contracts/v1/generated/typescript/openapi'
import App from '../../src/frontend/src/App.vue'
import { HTTP_CLIENT_KEY } from '../../src/frontend/src/api/client'
import { COURSES_API_KEY, createCoursesApi, type CoursesApi } from '../../src/frontend/src/api/courses'
import { ApiError, createHttpClient, NetworkError, type FetchLike } from '../../src/frontend/src/api/http'
import { toCourseCard } from '../../src/frontend/src/composables/useCourses'
import {
  COURSE_ROUTE,
  createAppRouter,
  NOTICE_COURSE_FORBIDDEN,
  NOTICE_UNAUTHENTICATED,
} from '../../src/frontend/src/router/index.ts'
import { useCourseStore } from '../../src/frontend/src/stores/course'
import { useSessionStore } from '../../src/frontend/src/stores/session'
import CoursesView from '../../src/frontend/src/views/CoursesView.vue'

type Course = components['schemas']['Course']
type Role = components['schemas']['Role']
type ErrorCode = components['schemas']['ErrorCode']

/** 课程内页面的占位组件：只为让路由存在，供课程页判断入口 */
const Stub = { template: '<div />' }

function course(id: string, overrides: Partial<Course> = {}): Course {
  return {
    id,
    name: `课程 ${id}`,
    description: null,
    status: 'draft',
    my_role: 'teacher',
    teacher_id: 'u_teacher',
    kp_count: 0,
    published_version: null,
    created_at: '2026-09-25T00:00:00Z',
    ...overrides,
  }
}

function apiError(status: number, code: ErrorCode): ApiError {
  return new ApiError(status, { code, message: '服务端原文不应被展示' })
}

/** 可手动完成的 Promise，用于制造「请求进行中」与晚到响应 */
function deferred<T>() {
  let resolve!: (value: T) => void
  let reject!: (reason: unknown) => void
  const promise = new Promise<T>((res, rej) => {
    resolve = res
    reject = rej
  })
  return { promise, resolve, reject }
}

function fakeApi(overrides: Partial<CoursesApi> = {}) {
  return {
    list: vi.fn<CoursesApi['list']>(overrides.list ?? (async () => [])),
    create: vi.fn<CoursesApi['create']>(overrides.create ?? (async (body) => course('c_new', { name: body.name }))),
    get: vi.fn<CoursesApi['get']>(overrides.get ?? (async (cid) => course(cid))),
  }
}

let pinia: Pinia

beforeEach(() => {
  sessionStorage.clear()
  pinia = createPinia()
  setActivePinia(pinia)
})

afterEach(() => {
  vi.restoreAllMocks()
})

async function mountApp({
  role = 'teacher',
  api = fakeApi(),
  path,
  attachTo,
}: {
  role?: Role | null
  api?: ReturnType<typeof fakeApi>
  path?: string
  /** 需要断言 document.activeElement 时把组件挂到真实 DOM 上 */
  attachTo?: HTMLElement
} = {}) {
  // 与 main.ts 一致：守卫与课程页都从会话读账号类型
  const session = useSessionStore(pinia)
  if (role !== null) {
    session.signIn({ access_token: 'tok', token_type: 'bearer', expires_in: 3600, user: { id: `u_${role}`, username: role, role } })
  }
  const router = createAppRouter({
    history: createMemoryHistory(),
    getAccountRole: () => session.role,
    coursesComponent: CoursesView,
    // 与 main.ts 一样注册课程内页面；课程页按“路由是否存在”决定入口是否显示
    membersComponent: Stub,
    materialsComponent: Stub,
    teacherGraphComponent: Stub,
    studentGraphComponent: Stub,
    reviewComponent: Stub,
    chatComponent: Stub,
  })
  await router.push(path ?? (role === 'student' ? '/student' : '/teacher'))
  await router.isReady()
  const wrapper = mount(App, {
    global: { plugins: [pinia, router], provide: { [COURSES_API_KEY as symbol]: api } },
    ...(attachTo ? { attachTo } : {}),
  })
  await flushPromises()
  return { wrapper, router, api, store: useCourseStore(pinia) }
}

// ---------------------------------------------------------------- API 封装

describe('H01 课程 API 封装', () => {
  function recordingFetch(response: () => Response) {
    const calls: { url: string; init: RequestInit | undefined }[] = []
    const fetch: FetchLike = async (url, init) => {
      calls.push({ url, init })
      return response()
    }
    return { calls, fetch }
  }
  const json = (body: unknown, status = 200) =>
    new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })

  it('list 走契约 GET /api/v1/courses 并带令牌', async () => {
    const { calls, fetch } = recordingFetch(() => json([course('c1')]))
    const api = createCoursesApi(createHttpClient({ fetch, getAccessToken: () => 'tok' }))
    await expect(api.list()).resolves.toEqual([course('c1')])
    expect(calls[0]!.url).toBe('/api/v1/courses')
    expect(calls[0]!.init?.method).toBe('GET')
    expect(new Headers(calls[0]!.init?.headers).get('Authorization')).toBe('Bearer tok')
  })

  it('create 走 POST /api/v1/courses，请求体为 CourseCreate JSON', async () => {
    const { calls, fetch } = recordingFetch(() => json(course('c9'), 201))
    const api = createCoursesApi(createHttpClient({ fetch }))
    await api.create({ name: '数据结构', description: '简介' })
    expect(calls[0]!.init?.method).toBe('POST')
    expect(JSON.parse(String(calls[0]!.init?.body))).toEqual({ name: '数据结构', description: '简介' })
  })

  it('get 按路径模板编码 cid，并把外部 signal 交给客户端', async () => {
    const { calls, fetch } = recordingFetch(() => json(course('a/b')))
    const api = createCoursesApi(createHttpClient({ fetch }))
    const controller = new AbortController()
    await api.get('a/b', { signal: controller.signal })
    expect(calls[0]!.url).toBe('/api/v1/courses/a%2Fb')
  })

  it('课程卡片视图模型与后端原始字段解耦', () => {
    const card = toCourseCard(course('c1', { status: 'published', my_role: 'student', kp_count: 7, description: '  ' }))
    expect(card).toEqual({
      id: 'c1',
      name: '课程 c1',
      description: null,
      myRole: 'student',
      roleLabel: '学生',
      statusLabel: '已发布',
      knowledgePointCount: 7,
    })
  })
})

// ---------------------------------------------------------------- 列表四态

describe('H01 课程列表状态', () => {
  it('加载态：请求未完成时显示忙碌提示', async () => {
    const pending = deferred<Course[]>()
    const { wrapper } = await mountApp({ api: fakeApi({ list: () => pending.promise }) })
    const status = wrapper.get('[data-test="courses-loading"]')
    expect(status.attributes('role')).toBe('status')
    expect(wrapper.get('[data-test="course-list-region"]').attributes('aria-busy')).toBe('true')
    pending.resolve([course('c1')])
    await flushPromises()
    expect(wrapper.find('[data-test="courses-loading"]').exists()).toBe(false)
    expect(wrapper.findAll('[data-test="course-card"]')).toHaveLength(1)
  })

  it('空态：没有可见课程时给出引导', async () => {
    const { wrapper } = await mountApp({ role: 'student', api: fakeApi({ list: async () => [] }) })
    expect(wrapper.get('[data-test="courses-empty"]').text()).toContain('暂无课程')
    expect(wrapper.findAll('[data-test="course-card"]')).toHaveLength(0)
  })

  it('错误态：网络失败显示 role=alert 与重试，重试成功后显示卡片', async () => {
    let attempt = 0
    const api = fakeApi({
      list: async () => {
        attempt += 1
        if (attempt === 1) throw new NetworkError(new TypeError('offline'))
        return [course('c1')]
      },
    })
    const { wrapper } = await mountApp({ api })
    const alert = wrapper.get('[data-test="courses-error"]')
    expect(alert.attributes('role')).toBe('alert')
    expect(alert.text()).toContain('网络')
    await wrapper.get('[data-test="courses-retry"]').trigger('click')
    await flushPromises()
    expect(api.list).toHaveBeenCalledTimes(2)
    expect(wrapper.find('[data-test="courses-error"]').exists()).toBe(false)
    expect(wrapper.findAll('[data-test="course-card"]')).toHaveLength(1)
  })

  it('错误态不回显服务端 message', async () => {
    const { wrapper } = await mountApp({ api: fakeApi({ list: async () => Promise.reject(apiError(500, 'INTERNAL_ERROR')) }) })
    expect(wrapper.get('[data-test="courses-error"]').text()).not.toContain('服务端原文')
  })

  it('禁止访问态：列表返回 403 时显示无权限提示', async () => {
    const { wrapper } = await mountApp({
      api: fakeApi({ list: async () => Promise.reject(apiError(403, 'ROLE_FORBIDDEN')) }),
    })
    const alert = wrapper.get('[data-test="courses-forbidden"]')
    expect(alert.attributes('role')).toBe('alert')
    expect(alert.text()).toContain('无权')
    expect(wrapper.find('[data-test="courses-error"]').exists()).toBe(false)
  })

  it('卡片显示课程名、课程内角色与状态，并链接到课程路由', async () => {
    const { wrapper } = await mountApp({
      api: fakeApi({
        list: async () => [
          course('c1', { name: '数据结构', my_role: 'teacher', status: 'draft', kp_count: 3 }),
          course('c2', { name: '操作系统', my_role: 'student', status: 'published', published_version: 2 }),
        ],
      }),
    })
    const cards = wrapper.findAll('[data-test="course-card"]')
    expect(cards).toHaveLength(2)
    expect(cards[0]!.text()).toContain('数据结构')
    expect(cards[0]!.text()).toContain('教师')
    expect(cards[0]!.text()).toContain('草稿')
    expect(cards[1]!.text()).toContain('学生')
    expect(cards[1]!.text()).toContain('已发布')
    expect(cards[1]!.get('a').attributes('href')).toBe('/courses/c2')
  })
})

// ---------------------------------------------------------------- 创建表单

describe('H01 创建课程表单', () => {
  it('只有教师账号显示创建表单，表单控件都有 label', async () => {
    const teacher = await mountApp({ role: 'teacher' })
    const form = teacher.wrapper.get('form[data-test="course-create"]')
    for (const input of form.findAll('input, textarea')) {
      expect(input.element.closest('label')).not.toBeNull()
    }
    teacher.wrapper.unmount()

    setActivePinia((pinia = createPinia()))
    const student = await mountApp({ role: 'student' })
    expect(student.wrapper.find('form[data-test="course-create"]').exists()).toBe(false)
  })

  it('重复点击提交只创建一次：提交中禁用按钮，完成后卡片加入列表并清空表单', async () => {
    const pending = deferred<Course>()
    const api = fakeApi({ list: async () => [course('c_old')], create: () => pending.promise })
    const { wrapper } = await mountApp({ api })
    await wrapper.get('input[name="name"]').setValue('编译原理')
    await wrapper.get('textarea[name="description"]').setValue('  前端与优化  ')
    const form = wrapper.get('form[data-test="course-create"]')
    await form.trigger('submit')
    await form.trigger('submit')
    await wrapper.get('button[type="submit"]').trigger('click')
    expect(api.create).toHaveBeenCalledTimes(1)
    expect(api.create.mock.calls[0]![0]).toEqual({ name: '编译原理', description: '前端与优化' })
    expect(wrapper.get('button[type="submit"]').attributes('disabled')).toBeDefined()
    expect(form.attributes('aria-busy')).toBe('true')

    pending.resolve(course('c_new', { name: '编译原理' }))
    await flushPromises()
    const names = wrapper.findAll('[data-test="course-card"]').map((c) => c.text())
    expect(names[0]).toContain('编译原理')
    expect(names).toHaveLength(2)
    expect((wrapper.get('input[name="name"]').element as HTMLInputElement).value).toBe('')
    expect(wrapper.get('button[type="submit"]').attributes('disabled')).toBeUndefined()
    expect(wrapper.get('[data-test="create-success"]').attributes('role')).toBe('status')
  })

  it('课程名为空或超长时不发请求并以 role=alert 提示', async () => {
    const api = fakeApi()
    const { wrapper } = await mountApp({ api })
    await wrapper.get('input[name="name"]').setValue('   ')
    await wrapper.get('form[data-test="course-create"]').trigger('submit')
    expect(wrapper.get('[data-test="create-error"]').attributes('role')).toBe('alert')
    await wrapper.get('input[name="name"]').setValue('长'.repeat(121))
    await wrapper.get('form[data-test="course-create"]').trigger('submit')
    expect(wrapper.get('[data-test="create-error"]').text()).toContain('120')
    expect(api.create).not.toHaveBeenCalled()
  })

  it('简介为空时不提交 description 字段', async () => {
    const api = fakeApi()
    const { wrapper } = await mountApp({ api })
    await wrapper.get('input[name="name"]').setValue('离散数学')
    await wrapper.get('form[data-test="course-create"]').trigger('submit')
    await flushPromises()
    expect(api.create.mock.calls[0]![0]).toEqual({ name: '离散数学' })
  })

  it.each([
    [apiError(403, 'ROLE_FORBIDDEN'), '无权'],
    [apiError(422, 'VALIDATION_ERROR'), '校验'],
    [new NetworkError(new TypeError('offline')), '网络'],
  ])('创建失败 %#：保留输入、提示原因、可再次提交', async (error, text) => {
    const api = fakeApi({ create: async () => Promise.reject(error) })
    const { wrapper } = await mountApp({ api })
    await wrapper.get('input[name="name"]').setValue('计算机网络')
    await wrapper.get('form[data-test="course-create"]').trigger('submit')
    await flushPromises()
    const alert = wrapper.get('[data-test="create-error"]')
    expect(alert.attributes('role')).toBe('alert')
    expect(alert.text()).toContain(text)
    expect(alert.text()).not.toContain('服务端原文')
    expect((wrapper.get('input[name="name"]').element as HTMLInputElement).value).toBe('计算机网络')
    await wrapper.get('form[data-test="course-create"]').trigger('submit')
    await flushPromises()
    expect(api.create).toHaveBeenCalledTimes(2)
  })
})

// ---------------------------------------------------------------- 视觉重构后的交互

describe('H01 课程页视觉重构', () => {
  it('创建面板默认收起：按钮带 aria-expanded，展开后聚焦课程名，取消后聚焦回按钮', async () => {
    const { wrapper } = await mountApp({
      api: fakeApi({ list: async () => [course('c1')] }),
      // 焦点断言需要组件真的挂在 document 上
      attachTo: document.body,
    })
    const toggle = wrapper.get('[data-test="create-toggle"]')
    const panel = wrapper.get('form[data-test="course-create"]')

    expect(toggle.attributes('aria-expanded')).toBe('false')
    expect(toggle.attributes('aria-controls')).toBe('course-create-panel')
    expect(panel.attributes('id')).toBe('course-create-panel')
    // 收起用 v-show：面板仍在 DOM 内，但不显示
    expect((panel.element as HTMLElement).style.display).toBe('none')

    await toggle.trigger('click')
    expect(toggle.attributes('aria-expanded')).toBe('true')
    expect((panel.element as HTMLElement).style.display).not.toBe('none')
    expect(document.activeElement).toBe(wrapper.get('input[name="name"]').element)

    await wrapper.get('[data-test="create-cancel"]').trigger('click')
    expect(toggle.attributes('aria-expanded')).toBe('false')
    expect((panel.element as HTMLElement).style.display).toBe('none')
    expect(document.activeElement).toBe(toggle.element)

    // 取消不改变业务状态：没有提交、没有错误
    expect(wrapper.find('[data-test="create-error"]').exists()).toBe(false)
  })

  it('创建成功后列表更新且面板保持可用，成功提示在表单外仍然可见', async () => {
    const { wrapper } = await mountApp({ api: fakeApi({ list: async () => [course('c1')] }) })
    await wrapper.get('[data-test="create-toggle"]').trigger('click')
    await wrapper.get('input[name="name"]').setValue('编译原理')
    await wrapper.get('form[data-test="course-create"]').trigger('submit')
    await flushPromises()

    expect(wrapper.findAll('[data-test="course-card"]')).toHaveLength(2)
    const toast = wrapper.get('[data-test="create-success-outside"]')
    expect(toast.text()).toContain('编译原理')
    expect(wrapper.get('[data-test="create-toast"]').attributes('role')).toBe('status')
    // 表单里的成功提示同样保留原有 data-test
    expect(wrapper.get('[data-test="create-success"]').text()).toContain('编译原理')
  })

  it('列表标题右侧给出课程总数，卡片展示状态徽标、身份与知识点，并链接到课程路由', async () => {
    const { wrapper } = await mountApp({
      api: fakeApi({
        list: async () => [
          course('c1', { name: '数据结构', my_role: 'teacher', status: 'draft', kp_count: 3 }),
          course('c2', { name: '操作系统', my_role: 'student', status: 'published', published_version: 2 }),
        ],
      }),
    })

    expect(wrapper.get('[data-test="courses-total"]').text()).toBe('共 2 门')
    const cards = wrapper.findAll('[data-test="course-card"]')
    expect(cards).toHaveLength(2)
    // 草稿与已发布要用不同样式，不能一律显示为绿色
    const draftBadge = cards[0]!.get('.course-card__badge')
    const publishedBadge = cards[1]!.get('.course-card__badge')
    expect(draftBadge.text()).toBe('草稿')
    expect(draftBadge.classes()).toContain('is-draft')
    expect(publishedBadge.text()).toBe('已发布')
    expect(publishedBadge.classes()).toContain('is-published')
    // 卡片文字包含课程内身份与知识点数量
    expect(cards[0]!.text()).toContain('教师')
    expect(cards[0]!.text()).toContain('3 个知识点')
    // 装饰图谱不进入无障碍树，也不拦鼠标
    const decor = cards[0]!.get('.course-card__decor')
    expect(decor.attributes('aria-hidden')).toBe('true')
    expect(decor.attributes('focusable')).toBe('false')
    // 整张卡是一个链接，没有嵌套链接
    const link = cards[1]!.get('a')
    expect(link.attributes('href')).toBe('/courses/c2')
    expect(cards[1]!.findAll('a')).toHaveLength(1)
  })

  it('课程卡只有「进入课程」是链接，其它区域不可跳转', async () => {
    const { wrapper, router } = await mountApp({
      api: fakeApi({ list: async () => [course('c1', { name: '数据结构', my_role: 'teacher', kp_count: 3 })] }),
    })
    const card = wrapper.get('[data-test="course-card"]')

    // 整卡只有一个链接，且就是右下角的入口
    expect(card.findAll('a')).toHaveLength(1)
    const entry = card.get('[data-test="course-entry"]')
    expect(entry.attributes('href')).toBe('/courses/c1')
    // 无障碍名称能区分课程
    expect(entry.attributes('aria-label')).toBe('进入课程：数据结构')

    // 卡片容器不是链接、不可聚焦，也没有点击跳转角色
    const body = card.get('.course-card__body')
    expect(body.element.tagName.toLowerCase()).toBe('div')
    expect(body.attributes('role')).toBeUndefined()
    expect(body.attributes('tabindex')).toBeUndefined()

    // 非链接区域（标题、简介、Chip、空白）不触发导航
    for (const selector of ['.course-card__name', '.course-card__badge', '.course-card__chip', '.course-card__body']) {
      await card.get(selector).trigger('click')
      await flushPromises()
      expect(router.currentRoute.value.path).toBe('/teacher')
    }

    // 只有入口链接负责跳转
    await entry.trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.path).toBe('/courses/c1')
  })

  it('列表与概览互斥：列表不再出现当前课程的 aria-current，侧栏课程入口标记为当前页', async () => {
    const api = fakeApi({ list: async () => [course('c1', { name: '数据结构' }), course('c2', { name: '操作系统' })] })
    const { wrapper, router } = await mountApp({ api, path: '/teacher' })
    expect(wrapper.findAll('[data-test="course-entry"]').every((entry) => entry.attributes('aria-current') === undefined)).toBe(true)

    await router.push('/courses/c2')
    await flushPromises()
    // 概览页本身表示“当前课程”，列表已不渲染，因此链接上没有 aria-current
    expect(wrapper.find('[data-test="course-list-region"]').exists()).toBe(false)
    expect(wrapper.find('[data-test="course-entry"]').exists()).toBe(false)
    // 侧栏的「课程概览」仍是当前页
    expect(wrapper.get('.app-nav__item.is-active').attributes('aria-current')).toBe('page')
  })

  it('键盘只聚焦入口链接，卡片容器不出现在 Tab 序列里', async () => {
    const { wrapper } = await mountApp({ api: fakeApi({ list: async () => [course('c1')] }) })
    const focusable = wrapper.get('[data-test="course-card"]').findAll('[tabindex], a, button')
    expect(focusable).toHaveLength(1)
    expect(focusable[0]!.attributes('data-test')).toBe('course-entry')
  })

  it('顶部统计只在列表就绪时给出确定数字', async () => {
    const pending = deferred<Course[]>()
    const { wrapper } = await mountApp({ api: fakeApi({ list: () => pending.promise }) })
    // 加载中不把未加载的数据说成「0 门课程」
    expect(wrapper.get('[data-test="courses-stats"]').text()).toBe('课程列表加载中')
    expect(wrapper.find('[data-test="courses-total"]').exists()).toBe(false)

    pending.resolve([course('c1', { kp_count: 5 }), course('c2', { kp_count: 7 })])
    await flushPromises()
    expect(wrapper.get('[data-test="courses-stats"]').text()).toBe('2 门课程 · 12 个知识点')
    expect(wrapper.get('[data-test="courses-total"]').text()).toBe('共 2 门')
  })

  it('学生端没有创建按钮与创建表单，说明文字按角色区分', async () => {
    setActivePinia((pinia = createPinia()))
    const { wrapper } = await mountApp({ role: 'student', api: fakeApi({ list: async () => [course('c1', { my_role: 'student' })] }) })

    expect(wrapper.find('[data-test="create-toggle"]').exists()).toBe(false)
    expect(wrapper.find('form[data-test="course-create"]').exists()).toBe(false)
    expect(wrapper.get('.courses__lede').text()).toContain('浏览课程知识图谱')
    // 侧栏账号区显示真实用户名与账号角色（不写死 demo 账号）
    expect(wrapper.get('[data-test="app-user"]').text()).toContain('student')
    expect(wrapper.get('[data-test="app-user"]').text()).toContain('学生')
  })
})

// ---------------------------------------------------------------- 切换课程

describe('H01 切换课程', () => {
  it('进入课程路由经 selectCourse 设置当前课程，并加载该课程', async () => {
    const api = fakeApi({ list: async () => [course('c1')], get: async (cid) => course(cid, { name: '数据结构' }) })
    const { wrapper, store } = await mountApp({ path: '/courses/c1', api })
    expect(store.courseId).toBe('c1')
    expect(api.get).toHaveBeenCalledWith('c1', expect.objectContaining({ signal: expect.any(AbortSignal) }))
    expect(wrapper.get('[data-test="current-course"]').text()).toContain('数据结构')
    // 概览不再渲染课程列表，因此这里不出现课程卡
    expect(wrapper.find('[data-test="course-card"]').exists()).toBe(false)
  })

  it('课程首页与课程概览互斥：首页没有概览，概览没有列表与统计', async () => {
    const api = fakeApi({
      list: async () => [course('c1', { name: '数据结构', kp_count: 5 })],
      get: async (cid) => course(cid, { name: '数据结构', description: '课程简介文本' }),
    })

    // 首页：有列表与统计，没有当前课程概览
    const home = await mountApp({ api, path: '/teacher' })
    expect(home.wrapper.find('[data-test="course-list-region"]').exists()).toBe(true)
    expect(home.wrapper.find('[data-test="courses-stats"]').exists()).toBe(true)
    expect(home.wrapper.find('[data-test="create-toggle"]').exists()).toBe(true)
    expect(home.wrapper.find('[data-test="current-course"]').exists()).toBe(false)
    expect(home.wrapper.find('[data-test="back-to-courses"]').exists()).toBe(false)
    home.wrapper.unmount()

    // 概览：只有当前课程信息与入口，没有课程列表、统计、创建入口与首页说明
    setActivePinia((pinia = createPinia()))
    const overview = await mountApp({ api, path: '/courses/c1' })
    const page = overview.wrapper
    expect(page.get('#courses-title').text()).toBe('课程概览')
    expect(page.get('[data-test="current-course"]').text()).toContain('数据结构')
    expect(page.get('[data-test="current-course"]').text()).toContain('课程简介文本')
    expect(page.find('[data-test="course-list-region"]').exists()).toBe(false)
    expect(page.find('[data-test="courses-stats"]').exists()).toBe(false)
    expect(page.find('[data-test="courses-total"]').exists()).toBe(false)
    expect(page.find('[data-test="create-toggle"]').exists()).toBe(false)
    expect(page.find('form[data-test="course-create"]').exists()).toBe(false)
    expect(page.find('.courses__lede').exists()).toBe(false)
    // 教师保留原有课程内入口
    expect(page.find('[data-test="teacher-graph-link"]').exists()).toBe(true)
    expect(page.find('[data-test="materials-link"]').exists()).toBe(true)
    expect(page.find('[data-test="review-link"]').exists()).toBe(true)
    expect(page.find('[data-test="members-link"]').exists()).toBe(true)
  })

  it('「返回我的课程」使用角色对应的首页路由，并能回到列表', async () => {
    const api = fakeApi({ list: async () => [course('c1')], get: async (cid) => course(cid) })
    const { wrapper, router } = await mountApp({ api, path: '/courses/c1' })
    const back = wrapper.get('[data-test="back-to-courses"]')
    expect(back.attributes('href')).toBe('/teacher')
    await back.trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.name).toBe('teacher-home')
    expect(wrapper.find('[data-test="course-list-region"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="current-course"]').exists()).toBe(false)
  })

  it('学生概览只保留学生入口，不出现教师操作', async () => {
    setActivePinia((pinia = createPinia()))
    const api = fakeApi({
      list: async () => [course('c1', { my_role: 'student' })],
      get: async (cid) => course(cid, { my_role: 'student', status: 'published' }),
    })
    const { wrapper } = await mountApp({ role: 'student', api, path: '/courses/c1' })
    expect(wrapper.find('[data-test="teacher-graph-link"]').exists()).toBe(false)
    expect(wrapper.find('[data-test="materials-link"]').exists()).toBe(false)
    expect(wrapper.find('[data-test="review-link"]').exists()).toBe(false)
    expect(wrapper.find('[data-test="members-link"]').exists()).toBe(false)
    expect(wrapper.find('[data-test="student-graph-link"]').exists()).toBe(true)
    expect(wrapper.get('[data-test="back-to-courses"]').attributes('href')).toBe('/student')
  })

  it('A→B 快速切换：A 晚到的响应不污染 B，A 的请求被取消', async () => {
    const pendings = new Map<string, ReturnType<typeof deferred<Course>>>()
    const signals = new Map<string, AbortSignal>()
    const api = fakeApi({
      list: async () => [course('cA'), course('cB')],
      get: (cid, control) => {
        const d = deferred<Course>()
        pendings.set(cid, d)
        signals.set(cid, control!.signal!)
        return d.promise
      },
    })
    const { wrapper, router, store } = await mountApp({ path: '/courses/cA', api })
    await router.push('/courses/cB')
    await flushPromises()
    expect(store.courseId).toBe('cB')
    expect(signals.get('cA')!.aborted).toBe(true)

    pendings.get('cA')!.resolve(course('cA', { name: '旧课程' }))
    await flushPromises()
    expect(wrapper.find('[data-test="current-course"]').text()).not.toContain('旧课程')

    pendings.get('cB')!.resolve(course('cB', { name: '新课程' }))
    await flushPromises()
    expect(wrapper.get('[data-test="current-course"]').text()).toContain('新课程')
  })

  it('A→B→A：第一次 A 的晚到响应也被丢弃', async () => {
    const pendings: { cid: string; d: ReturnType<typeof deferred<Course>> }[] = []
    const api = fakeApi({
      get: (cid) => {
        const d = deferred<Course>()
        pendings.push({ cid, d })
        return d.promise
      },
    })
    const { wrapper, router } = await mountApp({ path: '/courses/cA', api })
    await router.push('/courses/cB')
    await router.push('/courses/cA')
    await flushPromises()
    expect(pendings.map((p) => p.cid)).toEqual(['cA', 'cB', 'cA'])
    pendings[0]!.d.resolve(course('cA', { name: '第一次' }))
    await flushPromises()
    expect(wrapper.get('[data-test="current-course"]').text()).not.toContain('第一次')
    pendings[2]!.d.resolve(course('cA', { name: '第二次' }))
    await flushPromises()
    expect(wrapper.get('[data-test="current-course"]').text()).toContain('第二次')
  })

  it('COURSE_FORBIDDEN：清空当前课程，回到课程列表并提示无权限', async () => {
    const api = fakeApi({
      list: async () => [course('c1')],
      get: async () => Promise.reject(apiError(403, 'COURSE_FORBIDDEN')),
    })
    const { wrapper, router, store } = await mountApp({ path: '/courses/c_gone', api })
    await flushPromises()
    expect(store.courseId).toBeNull()
    expect(router.currentRoute.value.name).toBe('teacher-home')
    expect(router.currentRoute.value.query.notice).toBe(NOTICE_COURSE_FORBIDDEN)
    const alert = wrapper.get('[data-test="course-forbidden"]')
    expect(alert.attributes('role')).toBe('alert')
    expect(alert.text()).toContain('无权')
    expect(wrapper.findAll('[data-test="course-card"]')).toHaveLength(1)
  })

  it('学生遇到 COURSE_FORBIDDEN 回学生课程列表', async () => {
    const api = fakeApi({ get: async () => Promise.reject(apiError(403, 'COURSE_FORBIDDEN')) })
    const { router } = await mountApp({ role: 'student', path: '/courses/c_x', api })
    await flushPromises()
    expect(router.currentRoute.value.name).toBe('student-home')
  })

  it('课程加载失败（非 403）在课程面板内提示，不离开课程路由', async () => {
    const api = fakeApi({ get: async () => Promise.reject(new NetworkError(new TypeError('x'))) })
    const { wrapper, router } = await mountApp({ path: '/courses/c1', api })
    expect(router.currentRoute.value.path).toBe('/courses/c1')
    expect(wrapper.get('[data-test="current-course-error"]').attributes('role')).toBe('alert')
  })

  it('离开课程路由回到列表时清空当前课程并取消在途请求', async () => {
    let signal: AbortSignal | undefined
    const api = fakeApi({
      get: (_cid, control) => {
        signal = control?.signal
        return new Promise<Course>(() => undefined)
      },
    })
    const { wrapper, router, store } = await mountApp({ path: '/courses/c1', api })
    await router.push('/teacher')
    await flushPromises()
    expect(store.courseId).toBeNull()
    expect(signal?.aborted).toBe(true)
    expect(wrapper.find('[data-test="current-course"]').exists()).toBe(false)
  })
})

// ---------------------------------------------------------------- 路由接入

describe('H01 路由接入', () => {
  it('注入课程页后，教师与学生首页渲染课程列表', async () => {
    const teacher = await mountApp({ role: 'teacher' })
    expect(teacher.wrapper.find('[data-test="course-list-region"]').exists()).toBe(true)
  })

  it.each<Role>(['teacher', 'student'])('%s 可直接访问 /courses/:cid', async (role) => {
    const { router } = await mountApp({ role, path: '/courses/c1' })
    expect(router.currentRoute.value.name).toBe(COURSE_ROUTE)
    expect(router.currentRoute.value.params.cid).toBe('c1')
  })

  it('未登录访问课程路由回登录页', async () => {
    const router = createAppRouter({
      history: createMemoryHistory(),
      getAccountRole: () => null,
      coursesComponent: CoursesView,
    })
    await router.push('/courses/c1')
    expect(router.currentRoute.value.path).toBe('/')
    expect(router.currentRoute.value.query.notice).toBe(NOTICE_UNAUTHENTICATED)
  })

  it('未注入课程页时不注册课程路由（兼容 B03 用法）', async () => {
    const router = createAppRouter({ history: createMemoryHistory(), getAccountRole: () => 'teacher' })
    await router.push('/courses/c1')
    expect(router.currentRoute.value.path).toBe('/teacher')
    expect(router.hasRoute(COURSE_ROUTE)).toBe(false)
  })

  it('未注入课程 API 时给出明确错误', () => {
    expect(() =>
      mount(CoursesView, { global: { plugins: [pinia] } }),
    ).toThrow(/COURSES_API_KEY/)
  })

  it('通用 HTTP 客户端注入键为独立 Symbol', () => {
    expect(typeof HTTP_CLIENT_KEY).toBe('symbol')
  })
})
