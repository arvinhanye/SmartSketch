import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia, type Pinia } from 'pinia'
import { createMemoryHistory } from 'vue-router'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { components } from '../../src/contracts/v1/generated/typescript/openapi'
import App from '../../src/frontend/src/App.vue'
import { COURSES_API_KEY, type CoursesApi } from '../../src/frontend/src/api/courses'
import { ApiError, createHttpClient, NetworkError, type FetchLike } from '../../src/frontend/src/api/http'
import { createMembersApi, MEMBERS_API_KEY, type MembersApi } from '../../src/frontend/src/api/members'
import { toMemberRow } from '../../src/frontend/src/composables/useMembers'
import {
  COURSE_MEMBERS_ROUTE,
  createAppRouter,
  NOTICE_COURSE_FORBIDDEN,
  NOTICE_WRONG_ROLE,
} from '../../src/frontend/src/router/index.ts'
import { useSessionStore } from '../../src/frontend/src/stores/session'
import CoursesView from '../../src/frontend/src/views/CoursesView.vue'
import MembersView from '../../src/frontend/src/views/MembersView.vue'

type Course = components['schemas']['Course']
type CourseMember = components['schemas']['CourseMember']
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

function member(userId: string, username: string, role: Role = 'student'): CourseMember {
  return { user_id: userId, username, role, created_at: '2026-09-25T08:00:00Z' }
}

const TEACHER = member('u_teacher', 'teacher', 'teacher')
const ALICE = member('u_alice', 'alice')

function apiError(status: number, code: ErrorCode): ApiError {
  return new ApiError(status, { code, message: '服务端原文不应被展示' })
}

function deferred<T>() {
  let resolve!: (value: T) => void
  let reject!: (reason: unknown) => void
  const promise = new Promise<T>((res, rej) => {
    resolve = res
    reject = rej
  })
  return { promise, resolve, reject }
}

function fakeMembersApi(overrides: Partial<MembersApi> = {}) {
  return {
    list: vi.fn<MembersApi['list']>(overrides.list ?? (async () => [TEACHER, ALICE])),
    add: vi.fn<MembersApi['add']>(overrides.add ?? (async (_cid, body) => member(`u_${body.username}`, body.username))),
    remove: vi.fn<MembersApi['remove']>(overrides.remove ?? (async () => undefined)),
  }
}

function fakeCoursesApi(overrides: Partial<CoursesApi> = {}): CoursesApi {
  return {
    list: overrides.list ?? (async () => [course('c1')]),
    create: overrides.create ?? (async (body) => course('c_new', { name: body.name })),
    get: overrides.get ?? (async (cid) => course(cid)),
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
  api = fakeMembersApi(),
  courses = fakeCoursesApi(),
  path = '/courses/c1/members',
  withMembers = true,
}: {
  role?: Role | null
  api?: ReturnType<typeof fakeMembersApi>
  courses?: CoursesApi
  path?: string
  withMembers?: boolean
} = {}) {
  const session = useSessionStore(pinia)
  if (role !== null) {
    session.signIn({ access_token: 'tok', token_type: 'bearer', expires_in: 3600, user: { id: `u_${role}`, username: role, role } })
  }
  const router = createAppRouter({
    history: createMemoryHistory(),
    getAccountRole: () => session.role,
    coursesComponent: CoursesView,
    ...(withMembers ? { membersComponent: MembersView } : {}),
  })
  await router.push(path)
  await router.isReady()
  const wrapper = mount(App, {
    global: {
      plugins: [pinia, router],
      provide: { [COURSES_API_KEY as symbol]: courses, [MEMBERS_API_KEY as symbol]: api },
    },
  })
  await flushPromises()
  return { wrapper, router, api }
}

const rows = (wrapper: Awaited<ReturnType<typeof mountApp>>['wrapper']) => wrapper.findAll('[data-test="member-row"]')

async function submitAdd(wrapper: Awaited<ReturnType<typeof mountApp>>['wrapper'], username: string) {
  await wrapper.get('[data-test="member-add"] input[name="username"]').setValue(username)
  await wrapper.get('[data-test="member-add"]').trigger('submit')
}

// ---------------------------------------------------------------- API 封装

describe('H12 成员 API 封装', () => {
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

  it('list 走契约 GET /api/v1/courses/{cid}/members 并编码 cid', async () => {
    const { calls, fetch } = recordingFetch(() => json([TEACHER]))
    const api = createMembersApi(createHttpClient({ fetch, getAccessToken: () => 'tok' }))
    await expect(api.list('a/b')).resolves.toEqual([TEACHER])
    expect(calls[0]!.url).toBe('/api/v1/courses/a%2Fb/members')
    expect(calls[0]!.init?.method).toBe('GET')
    expect(new Headers(calls[0]!.init?.headers).get('Authorization')).toBe('Bearer tok')
  })

  it('add 走 POST，请求体只有 MemberAdd.username；201 与 200（已是成员）都返回成员行', async () => {
    let status = 201
    const { calls, fetch } = recordingFetch(() => json(ALICE, status))
    const api = createMembersApi(createHttpClient({ fetch }))
    await expect(api.add('c1', { username: 'alice' })).resolves.toEqual(ALICE)
    status = 200
    await expect(api.add('c1', { username: 'alice' })).resolves.toEqual(ALICE)
    expect(calls[0]!.url).toBe('/api/v1/courses/c1/members')
    expect(calls[0]!.init?.method).toBe('POST')
    expect(JSON.parse(String(calls[0]!.init?.body))).toEqual({ username: 'alice' })
  })

  it('remove 走 DELETE /members/{uid}，204 返回 undefined', async () => {
    const { calls, fetch } = recordingFetch(() => new Response(null, { status: 204 }))
    const api = createMembersApi(createHttpClient({ fetch }))
    await expect(api.remove('c1', 'u/1')).resolves.toBeUndefined()
    expect(calls[0]!.url).toBe('/api/v1/courses/c1/members/u%2F1')
    expect(calls[0]!.init?.method).toBe('DELETE')
  })

  it('成员行视图模型与后端字段解耦：只有学生成员可移除', () => {
    expect(toMemberRow(ALICE)).toMatchObject({ userId: 'u_alice', username: 'alice', roleLabel: '学生', removable: true })
    expect(toMemberRow(TEACHER)).toMatchObject({ roleLabel: '教师', removable: false })
  })
})

// ---------------------------------------------------------------- 入口与守卫

describe('H12 入口与路由守卫', () => {
  it('教师成员在课程页看到「管理成员」入口，链接到成员路由', async () => {
    const { wrapper, router } = await mountApp({ path: '/courses/c1' })
    const link = wrapper.get('[data-test="members-link"]')
    expect(link.attributes('href')).toBe(router.resolve({ name: COURSE_MEMBERS_ROUTE, params: { cid: 'c1' } }).href)
  })

  it('学生账号的课程页没有入口', async () => {
    const { wrapper } = await mountApp({
      role: 'student',
      path: '/courses/c1',
      courses: fakeCoursesApi({ get: async (cid) => course(cid, { my_role: 'student', status: 'published' }) }),
    })
    expect(wrapper.find('[data-test="current-course"]').text()).toContain('学生视图')
    expect(wrapper.find('[data-test="members-link"]').exists()).toBe(false)
  })

  it('教师账号但在本课是学生成员：也没有入口', async () => {
    const { wrapper } = await mountApp({
      path: '/courses/c1',
      courses: fakeCoursesApi({ get: async (cid) => course(cid, { my_role: 'student' }) }),
    })
    expect(wrapper.find('[data-test="current-course"]').text()).toContain('学生视图')
    expect(wrapper.find('[data-test="members-link"]').exists()).toBe(false)
  })

  it('学生账号直接打开成员路由被守卫送回学生首页，不发成员请求', async () => {
    const api = fakeMembersApi()
    const { router, wrapper } = await mountApp({ role: 'student', api })
    expect(router.currentRoute.value.name).toBe('student-home')
    expect(router.currentRoute.value.query.notice).toBe(NOTICE_WRONG_ROLE)
    expect(api.list).not.toHaveBeenCalled()
    expect(wrapper.find('[data-test="members"]').exists()).toBe(false)
  })

  it('未注入成员页时不注册成员路由，课程页也不显示入口', async () => {
    const { wrapper, router } = await mountApp({ path: '/courses/c1', withMembers: false })
    expect(router.hasRoute(COURSE_MEMBERS_ROUTE)).toBe(false)
    expect(wrapper.find('[data-test="current-course"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="members-link"]').exists()).toBe(false)
  })
})

// ---------------------------------------------------------------- 列表状态

describe('H12 成员列表状态', () => {
  it('加载态：请求中 role=status 且区域 aria-busy，完成后显示成员表', async () => {
    const pending = deferred<CourseMember[]>()
    const { wrapper, api } = await mountApp({ api: fakeMembersApi({ list: () => pending.promise }) })
    expect(api.list).toHaveBeenCalledWith('c1', expect.objectContaining({ signal: expect.any(AbortSignal) }))
    expect(wrapper.get('[data-test="members-loading"]').attributes('role')).toBe('status')
    expect(wrapper.get('[data-test="members-region"]').attributes('aria-busy')).toBe('true')
    pending.resolve([TEACHER, ALICE])
    await flushPromises()
    expect(wrapper.find('[data-test="members-loading"]').exists()).toBe(false)
    expect(wrapper.get('[data-test="members-region"]').attributes('aria-busy')).toBe('false')
    expect(rows(wrapper).map((r) => r.text())).toEqual([expect.stringContaining('teacher'), expect.stringContaining('alice')])
  })

  it('成员表可访问：有 caption 与列头，教师行无移除按钮，学生行按钮带用户名', async () => {
    const { wrapper } = await mountApp()
    const table = wrapper.get('[data-test="members-table"]')
    expect(table.find('caption').exists()).toBe(true)
    expect(table.findAll('th[scope="col"]').length).toBeGreaterThanOrEqual(3)
    const [teacherRow, aliceRow] = rows(wrapper)
    expect(teacherRow!.find('[data-test="member-remove"]').exists()).toBe(false)
    expect(aliceRow!.get('[data-test="member-remove"]').attributes('aria-label')).toBe('移除学生 alice')
  })

  it('空态：没有学生成员时给出添加引导', async () => {
    const { wrapper } = await mountApp({ api: fakeMembersApi({ list: async () => [TEACHER] }) })
    expect(wrapper.get('[data-test="members-empty"]').text()).toContain('暂无学生成员')
    expect(rows(wrapper)).toHaveLength(1)
  })

  it('错误态：网络失败显示 role=alert 与重试，重试成功后显示成员', async () => {
    let attempt = 0
    const api = fakeMembersApi({
      list: async () => {
        attempt += 1
        if (attempt === 1) throw new NetworkError(new TypeError('offline'))
        return [TEACHER, ALICE]
      },
    })
    const { wrapper } = await mountApp({ api })
    const alert = wrapper.get('[data-test="members-error"]')
    expect(alert.attributes('role')).toBe('alert')
    expect(alert.text()).toContain('网络')
    await wrapper.get('[data-test="members-retry"]').trigger('click')
    await flushPromises()
    expect(api.list).toHaveBeenCalledTimes(2)
    expect(wrapper.find('[data-test="members-error"]').exists()).toBe(false)
    expect(rows(wrapper)).toHaveLength(2)
  })

  it('错误态不回显服务端 message', async () => {
    const { wrapper } = await mountApp({
      api: fakeMembersApi({ list: async () => Promise.reject(apiError(500, 'INTERNAL_ERROR')) }),
    })
    expect(wrapper.get('[data-test="members-error"]').text()).not.toContain('服务端原文')
  })

  it('ROLE_FORBIDDEN：明确提示只有本课程教师可管理成员，不显示添加表单', async () => {
    const { wrapper } = await mountApp({
      api: fakeMembersApi({ list: async () => Promise.reject(apiError(403, 'ROLE_FORBIDDEN')) }),
    })
    const alert = wrapper.get('[data-test="members-forbidden"]')
    expect(alert.attributes('role')).toBe('alert')
    expect(alert.text()).toContain('只有本课程的教师成员')
    expect(wrapper.find('[data-test="member-add"]').exists()).toBe(false)
    expect(wrapper.find('[data-test="members-retry"]').exists()).toBe(false)
  })

  it('COURSE_FORBIDDEN：回课程列表并提示无权限', async () => {
    const { router, wrapper } = await mountApp({
      api: fakeMembersApi({ list: async () => Promise.reject(apiError(403, 'COURSE_FORBIDDEN')) }),
    })
    expect(router.currentRoute.value.name).toBe('teacher-home')
    expect(router.currentRoute.value.query.notice).toBe(NOTICE_COURSE_FORBIDDEN)
    expect(wrapper.get('[data-test="course-forbidden"]').attributes('role')).toBe('alert')
  })

  it('切换课程：旧课程晚到的成员列表被丢弃，旧请求被取消', async () => {
    const slow = deferred<CourseMember[]>()
    let firstSignal: AbortSignal | undefined
    const api = fakeMembersApi({
      list: async (cid, control) => {
        if (cid === 'cA') {
          firstSignal = control?.signal
          return slow.promise
        }
        return [TEACHER, member('u_bob', 'bob')]
      },
    })
    const { wrapper, router } = await mountApp({ api, path: '/courses/cA/members' })
    await router.push('/courses/cB/members')
    await flushPromises()
    expect(firstSignal?.aborted).toBe(true)
    slow.resolve([TEACHER, ALICE])
    await flushPromises()
    expect(wrapper.text()).toContain('bob')
    expect(wrapper.text()).not.toContain('alice')
  })
})

// ---------------------------------------------------------------- 添加

describe('H12 添加学生成员', () => {
  it('表单控件有 label；添加成功后新行出现、输入清空并以 role=status 提示', async () => {
    const { wrapper, api } = await mountApp()
    const input = wrapper.get('[data-test="member-add"] input[name="username"]')
    expect(input.element.closest('label')?.textContent).toContain('学生用户名')
    expect(input.attributes('autocomplete')).toBe('off')
    await submitAdd(wrapper, '  bob  ')
    await flushPromises()
    expect(api.add).toHaveBeenCalledTimes(1)
    expect(api.add.mock.calls[0]![0]).toBe('c1')
    expect(api.add.mock.calls[0]![1]).toEqual({ username: 'bob' })
    expect(rows(wrapper)).toHaveLength(3)
    expect((input.element as HTMLInputElement).value).toBe('')
    const status = wrapper.get('[data-test="member-add-success"]')
    expect(status.attributes('role')).toBe('status')
    expect(status.text()).toContain('bob')
  })

  it('用户名为空不发请求并以 role=alert 提示', async () => {
    const { wrapper, api } = await mountApp()
    await submitAdd(wrapper, '   ')
    await flushPromises()
    expect(api.add).not.toHaveBeenCalled()
    expect(wrapper.get('[data-test="member-add-error"]').attributes('role')).toBe('alert')
  })

  it('重复提交只发一次：提交中禁用按钮与表单，完成后恢复', async () => {
    const pending = deferred<CourseMember>()
    const api = fakeMembersApi({ add: () => pending.promise })
    const { wrapper } = await mountApp({ api })
    await wrapper.get('[data-test="member-add"] input[name="username"]').setValue('bob')
    const form = wrapper.get('[data-test="member-add"]')
    await form.trigger('submit')
    await form.trigger('submit')
    await form.trigger('submit')
    expect(api.add).toHaveBeenCalledTimes(1)
    expect(form.get('button[type="submit"]').attributes('disabled')).toBeDefined()
    expect(form.get('fieldset').attributes('disabled')).toBeDefined()
    expect(form.attributes('aria-busy')).toBe('true')
    pending.resolve(member('u_bob', 'bob'))
    await flushPromises()
    expect(form.get('button[type="submit"]').attributes('disabled')).toBeUndefined()
    expect(rows(wrapper)).toHaveLength(3)
  })

  it('已是成员（接口幂等返回现有行）：不重复出现，提示未重复添加', async () => {
    // 后端按用户名小写化后命中已有成员，返回 200 与原成员行
    const api = fakeMembersApi({ add: async () => ALICE })
    const { wrapper } = await mountApp({ api })
    await submitAdd(wrapper, 'ALICE')
    await flushPromises()
    await submitAdd(wrapper, 'alice')
    await flushPromises()
    expect(api.add).toHaveBeenCalledTimes(2)
    expect(rows(wrapper)).toHaveLength(2)
    expect(rows(wrapper).filter((r) => r.text().includes('alice'))).toHaveLength(1)
    expect(wrapper.get('[data-test="member-add-success"]').text()).toContain('已是课程成员')
  })

  it('已是教师成员：返回原教师行，身份不被改成学生', async () => {
    const api = fakeMembersApi({ add: async () => TEACHER })
    const { wrapper } = await mountApp({ api })
    await submitAdd(wrapper, 'teacher')
    await flushPromises()
    expect(rows(wrapper)).toHaveLength(2)
    expect(rows(wrapper)[0]!.text()).toContain('教师')
    expect(rows(wrapper)[0]!.find('[data-test="member-remove"]').exists()).toBe(false)
  })

  it.each([
    [404, 'NOT_FOUND' as ErrorCode, '未找到该用户'],
    [403, 'ROLE_FORBIDDEN' as ErrorCode, '只有本课程的教师成员'],
    [422, 'VALIDATION_ERROR' as ErrorCode, '用户名'],
  ])('添加失败 %i %s：role=alert 固定文案，保留输入，不回显服务端 message', async (status, code, text) => {
    const api = fakeMembersApi({ add: async () => Promise.reject(apiError(status, code)) })
    const { wrapper } = await mountApp({ api })
    await submitAdd(wrapper, 'ghost')
    await flushPromises()
    const alert = wrapper.get('[data-test="member-add-error"]')
    expect(alert.attributes('role')).toBe('alert')
    expect(alert.text()).toContain(text)
    expect(alert.text()).not.toContain('服务端原文')
    expect((wrapper.get('[data-test="member-add"] input[name="username"]').element as HTMLInputElement).value).toBe('ghost')
    expect(rows(wrapper)).toHaveLength(2)
  })

  it('添加时 COURSE_FORBIDDEN（已被移出课程）：回课程列表', async () => {
    const api = fakeMembersApi({ add: async () => Promise.reject(apiError(403, 'COURSE_FORBIDDEN')) })
    const { wrapper, router } = await mountApp({ api })
    await submitAdd(wrapper, 'bob')
    await flushPromises()
    expect(router.currentRoute.value.name).toBe('teacher-home')
    expect(router.currentRoute.value.query.notice).toBe(NOTICE_COURSE_FORBIDDEN)
  })

  it('添加时网络失败提示可重试', async () => {
    const api = fakeMembersApi({ add: async () => Promise.reject(new NetworkError(new TypeError('offline'))) })
    const { wrapper } = await mountApp({ api })
    await submitAdd(wrapper, 'bob')
    await flushPromises()
    expect(wrapper.get('[data-test="member-add-error"]').text()).toContain('网络')
  })
})

// ---------------------------------------------------------------- 移除

describe('H12 移除学生成员', () => {
  it('移除成功：调用 DELETE、行消失、以 role=status 提示', async () => {
    const { wrapper, api } = await mountApp()
    await rows(wrapper)[1]!.get('[data-test="member-remove"]').trigger('click')
    await flushPromises()
    expect(api.remove).toHaveBeenCalledTimes(1)
    expect(api.remove.mock.calls[0]![0]).toBe('c1')
    expect(api.remove.mock.calls[0]![1]).toBe('u_alice')
    expect(rows(wrapper)).toHaveLength(1)
    const status = wrapper.get('[data-test="member-remove-status"]')
    expect(status.attributes('role')).toBe('status')
    expect(status.text()).toContain('alice')
    expect(wrapper.find('[data-test="members-empty"]').exists()).toBe(true)
  })

  it('重复点击移除只发一次：进行中按钮禁用', async () => {
    const pending = deferred<undefined>()
    const api = fakeMembersApi({ remove: () => pending.promise })
    const { wrapper } = await mountApp({ api })
    const button = rows(wrapper)[1]!.get('[data-test="member-remove"]')
    // 两次点击在按钮禁用渲染之前连续到达：只能靠同步防重入
    void button.trigger('click')
    await button.trigger('click')
    await button.trigger('click')
    expect(api.remove).toHaveBeenCalledTimes(1)
    expect(button.attributes('disabled')).toBeDefined()
    expect(button.attributes('aria-busy')).toBe('true')
    pending.resolve(undefined)
    await flushPromises()
    expect(rows(wrapper)).toHaveLength(1)
  })

  it('移除 403 ROLE_FORBIDDEN：明确提示无权限，行保留', async () => {
    const api = fakeMembersApi({ remove: async () => Promise.reject(apiError(403, 'ROLE_FORBIDDEN')) })
    const { wrapper } = await mountApp({ api })
    await rows(wrapper)[1]!.get('[data-test="member-remove"]').trigger('click')
    await flushPromises()
    const alert = wrapper.get('[data-test="member-remove-error"]')
    expect(alert.attributes('role')).toBe('alert')
    expect(alert.text()).toContain('无权移除')
    expect(alert.text()).not.toContain('服务端原文')
    expect(rows(wrapper)).toHaveLength(2)
    expect(rows(wrapper)[1]!.get('[data-test="member-remove"]').attributes('disabled')).toBeUndefined()
  })

  it('移除 404（已不是成员）：从列表去掉并说明', async () => {
    const api = fakeMembersApi({ remove: async () => Promise.reject(apiError(404, 'NOT_FOUND')) })
    const { wrapper } = await mountApp({ api })
    await rows(wrapper)[1]!.get('[data-test="member-remove"]').trigger('click')
    await flushPromises()
    expect(rows(wrapper)).toHaveLength(1)
    expect(wrapper.get('[data-test="member-remove-status"]').text()).toContain('已不是课程成员')
  })

  it('移除时 COURSE_FORBIDDEN：回课程列表', async () => {
    const api = fakeMembersApi({ remove: async () => Promise.reject(apiError(403, 'COURSE_FORBIDDEN')) })
    const { wrapper, router } = await mountApp({ api })
    await rows(wrapper)[1]!.get('[data-test="member-remove"]').trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.name).toBe('teacher-home')
    expect(router.currentRoute.value.query.notice).toBe(NOTICE_COURSE_FORBIDDEN)
  })

  it('成员页有返回课程页的链接', async () => {
    const { wrapper } = await mountApp()
    expect(wrapper.get('[data-test="members-back"]').attributes('href')).toBe('/courses/c1')
  })
})
