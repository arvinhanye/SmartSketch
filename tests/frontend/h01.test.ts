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
}: { role?: Role | null; api?: ReturnType<typeof fakeApi>; path?: string } = {}) {
  // 与 main.ts 一致：守卫与课程页都从会话读账号类型
  const session = useSessionStore(pinia)
  if (role !== null) {
    session.signIn({ access_token: 'tok', token_type: 'bearer', expires_in: 3600, user: { id: `u_${role}`, username: role, role } })
  }
  const router = createAppRouter({
    history: createMemoryHistory(),
    getAccountRole: () => session.role,
    coursesComponent: CoursesView,
  })
  await router.push(path ?? (role === 'student' ? '/student' : '/teacher'))
  await router.isReady()
  const wrapper = mount(App, {
    global: { plugins: [pinia, router], provide: { [COURSES_API_KEY as symbol]: api } },
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

// ---------------------------------------------------------------- 切换课程

describe('H01 切换课程', () => {
  it('进入课程路由经 selectCourse 设置当前课程，并加载该课程', async () => {
    const api = fakeApi({ list: async () => [course('c1')], get: async (cid) => course(cid, { name: '数据结构' }) })
    const { wrapper, store } = await mountApp({ path: '/courses/c1', api })
    expect(store.courseId).toBe('c1')
    expect(api.get).toHaveBeenCalledWith('c1', expect.objectContaining({ signal: expect.any(AbortSignal) }))
    expect(wrapper.get('[data-test="current-course"]').text()).toContain('数据结构')
    expect(wrapper.get('[data-test="course-card"] a').attributes('aria-current')).toBe('page')
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
