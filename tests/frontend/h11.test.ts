import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { createPinia, setActivePinia, type Pinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { defineComponent, h } from 'vue'
import { createMemoryHistory, RouterView } from 'vue-router'
import type { components } from '../../src/contracts/v1/generated/typescript/openapi'
import type { CoursesApi } from '../../src/frontend/src/api/courses'
import { COURSES_API_KEY } from '../../src/frontend/src/api/courses'
import { createPublishedGraphApi, PUBLISHED_GRAPH_API_KEY, type PublishedGraphApi } from '../../src/frontend/src/api/graph'
import { ApiError, createHttpClient, NetworkError, type FetchLike } from '../../src/frontend/src/api/http'
import { KNOWLEDGE_DETAIL_API_KEY, type KnowledgeDetailApi } from '../../src/frontend/src/api/knowledgeDetail'
import GraphCanvas from '../../src/frontend/src/components/GraphCanvas.vue'
import KnowledgeCards from '../../src/frontend/src/components/KnowledgeCards.vue'
import { toKnowledgeCards, type KnowledgeCard } from '../../src/frontend/src/composables/useStudentGraph'
import { toG6Data } from '../../src/frontend/src/graph/adapter'
import { GRAPH_FACTORY_KEY, type CanvasGraph, type CanvasGraphFactory } from '../../src/frontend/src/graph/lifecycle'
import { createAppRouter, STUDENT_GRAPH_ROUTE } from '../../src/frontend/src/router/index.ts'
import { useSessionStore } from '../../src/frontend/src/stores/session'
import CoursesView from '../../src/frontend/src/views/CoursesView.vue'
import StudentGraphView from '../../src/frontend/src/views/StudentGraphView.vue'

type Course = components['schemas']['Course']
type GraphExchange = components['schemas']['GraphExchange']
type KnowledgePoint = components['schemas']['KnowledgePoint']
type KnowledgePointDetail = components['schemas']['KnowledgePointDetail']
type Relation = components['schemas']['Relation']
type ErrorCode = components['schemas']['ErrorCode']

// ---------------------------------------------------------------- 夹具

function course(id: string, overrides: Partial<Course> = {}): Course {
  return {
    id,
    name: `课程 ${id}`,
    status: 'published',
    my_role: 'student',
    published_version: 3,
    created_at: '2026-09-01T00:00:00Z',
    ...overrides,
  }
}

function kp(id: string, overrides: Partial<KnowledgePoint> = {}, cid = 'c1'): KnowledgePoint {
  return {
    id,
    course_id: cid,
    name: `知识点 ${id}`,
    type: 'concept',
    definition: `${id} 的定义`,
    level: 1,
    confidence: 0.9,
    status: 'approved',
    source: 'ai',
    locked: false,
    revision: 1,
    chapter_id: 'ch1',
    ...overrides,
  }
}

function rel(id: string, from: string, to: string, cid = 'c1'): Relation {
  return {
    id,
    course_id: cid,
    type: 'PREREQUISITE',
    from_id: from,
    to_id: to,
    confidence: 0.9,
    status: 'approved',
    source: 'ai',
    source_refs: [],
  } as unknown as Relation
}

function exchange(cid: string, version: number | null, nodes: KnowledgePoint[], edges: Relation[] = []): GraphExchange {
  return {
    format_version: '1.0',
    course_id: cid,
    graph_version: version,
    generated_at: '2026-09-26T00:00:00Z',
    chapters: [{ id: 'ch1', title: '第一章 栈', order: 1 }],
    nodes,
    edges,
  }
}

/** n 个知识点，编号补零使名称与 ID 的码点顺序一致 */
function manyKps(n: number, cid = 'c1'): KnowledgePoint[] {
  return Array.from({ length: n }, (_, i) => kp(`k${String(i + 1).padStart(2, '0')}`, {}, cid))
}

function detail(cid: string, kid: string): KnowledgePointDetail {
  return {
    ...kp(kid, {}, cid),
    source_refs: [{ chunk_id: `${kid}-chunk`, document_id: 'doc1', page: 2 }],
    prerequisites: [],
    successors: [],
    related: [],
  } as KnowledgePointDetail
}

function apiError(status: number, code: ErrorCode): ApiError {
  return new ApiError(status, { code, message: '服务端原文' })
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

function fakeCanvasFactory(): CanvasGraphFactory {
  return (() => {
    const graph: CanvasGraph = {
      render: () => Promise.resolve(),
      setData: () => {},
      setSize: () => {},
      fitView: () => Promise.resolve(),
      on() {
        return this
      },
      destroy: () => {},
    } as unknown as CanvasGraph
    return graph
  }) as CanvasGraphFactory
}

interface Fakes {
  courses: { get: ReturnType<typeof vi.fn<CoursesApi['get']>> }
  graph: { getPublished: ReturnType<typeof vi.fn<PublishedGraphApi['getPublished']>> }
  detail: { get: ReturnType<typeof vi.fn<KnowledgeDetailApi['get']>> }
}

function fakes(
  opts: {
    course?: CoursesApi['get']
    graph?: PublishedGraphApi['getPublished']
  } = {},
): Fakes {
  return {
    courses: { get: vi.fn<CoursesApi['get']>(opts.course ?? (async (cid) => course(cid))) },
    graph: {
      getPublished: vi.fn<PublishedGraphApi['getPublished']>(
        opts.graph ?? (async (cid, version) => exchange(cid, version, manyKps(5, cid))),
      ),
    },
    detail: { get: vi.fn<KnowledgeDetailApi['get']>(async (cid, kid) => detail(cid, kid)) },
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

async function mountPage(f: Fakes, path = '/courses/c1/graph', accountRole: 'student' | 'teacher' = 'student') {
  const session = useSessionStore(pinia)
  session.signIn({
    access_token: 'tok',
    token_type: 'bearer',
    expires_in: 3600,
    user: { id: `u_${accountRole}`, username: accountRole, role: accountRole },
  })
  const router = createAppRouter({
    history: createMemoryHistory(),
    getAccountRole: () => session.role,
    coursesComponent: CoursesView,
    studentGraphComponent: StudentGraphView,
  })
  await router.push(path)
  await router.isReady()
  const wrapper = mount(defineComponent({ render: () => h(RouterView) }), {
    attachTo: document.body,
    global: {
      plugins: [pinia, router],
      provide: {
        [COURSES_API_KEY as symbol]: { list: async () => [], create: vi.fn(), get: f.courses.get },
        [PUBLISHED_GRAPH_API_KEY as symbol]: f.graph,
        [KNOWLEDGE_DETAIL_API_KEY as symbol]: f.detail,
        [GRAPH_FACTORY_KEY as symbol]: fakeCanvasFactory(),
      },
    },
  })
  await flushPromises()
  return { wrapper, router }
}

function cardIds(wrapper: VueWrapper): string[] {
  return wrapper.findAll('[data-test="kc-card"]').map((card) => card.attributes('data-kp-id')!)
}

async function toCards(wrapper: VueWrapper): Promise<void> {
  await wrapper.get('[data-test="sg-mode-cards"]').trigger('click')
}

// ---------------------------------------------------------------- 纯函数与 API 封装

describe('H11 卡片视图模型', () => {
  it('按章节目录顺序、层级、名称排序；目录外章节在后、未分章最后', () => {
    const graph = toG6Data(
      exchange('c1', 1, [
        kp('a', { name: 'B 树', chapter_id: 'ch2', level: 1 }),
        kp('b', { name: 'AVL 树', chapter_id: 'ch2', level: 1 }),
        kp('c', { name: '丙', chapter_id: 'ch2', level: 0 }),
        kp('d', { name: '丁', chapter_id: 'ch1', level: 3 }),
        kp('e', { name: '戊', chapter_id: null }),
        kp('f', { name: '己', chapter_id: 'zz-outside' }),
      ]),
    )
    const chapters = [
      { id: 'ch2', title: '第二章', order: 2 },
      { id: 'ch1', title: '第一章', order: 1 },
    ]
    const cards = toKnowledgeCards(graph.nodes, chapters)
    expect(cards.map((card) => card.kpId)).toEqual(['d', 'c', 'b', 'a', 'f', 'e'])
    expect(cards[0]).toEqual({ kpId: 'd', name: '丁', typeLabel: '概念', chapterLabel: '第一章', level: 3 })
    expect(cards.find((card) => card.kpId === 'e')?.chapterLabel).toBe('未分章')
    expect(cards.find((card) => card.kpId === 'f')?.chapterLabel).toBe('zz-outside')
  })

  it('不修改输入', () => {
    const graph = toG6Data(exchange('c1', 1, [kp('b'), kp('a')]))
    const before = JSON.stringify(graph.nodes)
    toKnowledgeCards(graph.nodes)
    expect(JSON.stringify(graph.nodes)).toBe(before)
  })
})

describe('H11 已发布图谱 API 封装', () => {
  function recordingFetch(body: unknown) {
    const urls: string[] = []
    const fetch: FetchLike = async (url) => {
      urls.push(url)
      return new Response(JSON.stringify(body), { status: 200, headers: { 'Content-Type': 'application/json' } })
    }
    return { urls, fetch }
  }

  it('总是带 version 查询参数请求 GET /graph', async () => {
    const { urls, fetch } = recordingFetch(exchange('c/1', 3, []))
    const api = createPublishedGraphApi(createHttpClient({ fetch, getAccessToken: () => 'tok' }))
    await api.getPublished('c/1', 3)
    expect(urls).toEqual(['/api/v1/courses/c%2F1/graph?version=3'])
  })

  it.each([0, -1, 1.5, Number.NaN])('版本号 %s 不发请求直接拒绝', async (version) => {
    const { urls, fetch } = recordingFetch({})
    const api = createPublishedGraphApi(createHttpClient({ fetch }))
    await expect(api.getPublished('c1', version)).rejects.toBeInstanceOf(RangeError)
    expect(urls).toEqual([])
  })
})

// ---------------------------------------------------------------- 页面：不取草稿

describe('H11 学生图谱页：任何入口不取草稿', () => {
  it('从未发布（published_version = null）：显示未发布，不请求图谱与详情', async () => {
    const f = fakes({ course: async (cid) => course(cid, { status: 'draft', published_version: null }) })
    const { wrapper } = await mountPage(f)
    expect(wrapper.find('[data-test="sg-unpublished"]').exists()).toBe(true)
    expect(f.graph.getPublished).not.toHaveBeenCalled()
    expect(f.detail.get).not.toHaveBeenCalled()
    expect(wrapper.find('[data-test="knowledge-cards"]').exists()).toBe(false)
  })

  it('课程详情本身返回 GRAPH_NOT_PUBLISHED：显示未发布，不请求图谱与详情', async () => {
    const f = fakes({ course: async () => Promise.reject(apiError(404, 'GRAPH_NOT_PUBLISHED')) })
    const { wrapper } = await mountPage(f)
    expect(wrapper.find('[data-test="sg-unpublished"]').exists()).toBe(true)
    expect(wrapper.get('[data-test="sg-unpublished"]').text()).toContain('尚未发布')
    expect(wrapper.find('[data-test="sg-error"]').exists()).toBe(false)
    expect(wrapper.text()).not.toContain('服务端原文')
    expect(f.courses.get).toHaveBeenCalledTimes(1)
    expect(f.graph.getPublished).not.toHaveBeenCalled()
    expect(f.detail.get).not.toHaveBeenCalled()
  })

  it('读图返回 GRAPH_NOT_PUBLISHED：显示未发布，不回显服务端原文', async () => {
    const f = fakes({ graph: async () => Promise.reject(apiError(404, 'GRAPH_NOT_PUBLISHED')) })
    const { wrapper } = await mountPage(f)
    expect(wrapper.find('[data-test="sg-unpublished"]').exists()).toBe(true)
    expect(wrapper.text()).not.toContain('服务端原文')
  })

  it('课程内角色是教师：不发任何图谱请求（教师省略版本会读到草稿）', async () => {
    const f = fakes({ course: async (cid) => course(cid, { my_role: 'teacher' }) })
    const { wrapper } = await mountPage(f, '/courses/c1/graph', 'teacher')
    expect(wrapper.find('[data-test="sg-not-student"]').exists()).toBe(true)
    expect(f.graph.getPublished).not.toHaveBeenCalled()
    expect(f.detail.get).not.toHaveBeenCalled()
  })

  it('图谱请求总是带课程当前发布版本号', async () => {
    const f = fakes({ course: async (cid) => course(cid, { published_version: 7, status: 'revising' }) })
    const { wrapper } = await mountPage(f)
    expect(f.graph.getPublished).toHaveBeenCalledTimes(1)
    expect(f.graph.getPublished.mock.calls[0]!.slice(0, 2)).toEqual(['c1', 7])
    expect(wrapper.get('[data-test="sg-version"]').text()).toContain('v7')
  })

  it.each([
    ['草稿（graph_version = null）', (cid: string) => exchange(cid, null, manyKps(2, cid))],
    ['版本号与请求不符', (cid: string) => exchange(cid, 2, manyKps(2, cid))],
    ['其他课程的图', () => exchange('c2', 3, manyKps(2, 'c2'))],
    ['缺少节点数组', (cid: string) => ({ ...exchange(cid, 3, []), nodes: undefined }) as unknown as GraphExchange],
  ])('响应是%s：按数据异常丢弃，不渲染画布与卡片', async (_label, make) => {
    const f = fakes({ graph: async (cid) => make(cid) })
    const { wrapper } = await mountPage(f)
    expect(wrapper.get('[data-test="sg-error"]').text()).toContain('数据异常')
    expect(wrapper.find('[data-test="sg-retry"]').exists()).toBe(true)
    expect(wrapper.findComponent(GraphCanvas).exists()).toBe(false)
    expect(wrapper.find('[data-test="knowledge-cards"]').exists()).toBe(false)
  })

  it('卡片视图由已发布图派生，切换视图不再发请求', async () => {
    const f = fakes()
    const { wrapper } = await mountPage(f)
    await toCards(wrapper)
    await wrapper.get('[data-test="sg-mode-graph"]').trigger('click')
    await toCards(wrapper)
    await flushPromises()
    expect(f.graph.getPublished).toHaveBeenCalledTimes(1)
    expect(f.courses.get).toHaveBeenCalledTimes(1)
  })

  it('课程页只给课程内学生显示图谱入口', async () => {
    const student = await mountPage(fakes(), '/courses/c1')
    expect(student.wrapper.find('[data-test="student-graph-link"]').attributes('href')).toBe('/courses/c1/graph')
    student.wrapper.unmount()

    const teacher = await mountPage(fakes({ course: async (cid) => course(cid, { my_role: 'teacher' }) }), '/courses/c1', 'teacher')
    expect(teacher.wrapper.find('[data-test="student-graph-link"]').exists()).toBe(false)
  })

  it('路由按课程内角色而非账号类型放行，页面自行拦截', async () => {
    const f = fakes({ course: async (cid) => course(cid, { my_role: 'teacher' }) })
    const { router } = await mountPage(f, '/courses/c1/graph', 'teacher')
    expect(router.currentRoute.value.name).toBe(STUDENT_GRAPH_ROUTE)
  })
})

// ---------------------------------------------------------------- 页面：状态

describe('H11 学生图谱页：加载、空图与错误', () => {
  it('加载中显示状态并 aria-busy', async () => {
    const pending = deferred<GraphExchange>()
    const f = fakes({ graph: () => pending.promise })
    const { wrapper } = await mountPage(f)
    expect(wrapper.find('[data-test="sg-loading"]').exists()).toBe(true)
    expect(wrapper.get('[data-test="student-graph-page"]').attributes('aria-busy')).toBe('true')
    pending.resolve(exchange('c1', 3, manyKps(1)))
    await flushPromises()
    expect(wrapper.find('[data-test="sg-loading"]').exists()).toBe(false)
    expect(wrapper.get('[data-test="student-graph-page"]').attributes('aria-busy')).toBe('false')
  })

  it('已发布但无知识点：显示空图，不显示视图切换', async () => {
    const f = fakes({ graph: async (cid, v) => exchange(cid, v, []) })
    const { wrapper } = await mountPage(f)
    expect(wrapper.find('[data-test="sg-empty"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="sg-mode-cards"]').exists()).toBe(false)
  })

  it('网络错误可重试，重试成功后显示图谱', async () => {
    let calls = 0
    const f = fakes({
      graph: async (cid, v) => {
        calls += 1
        if (calls === 1) throw new NetworkError(new TypeError('offline'))
        return exchange(cid, v, manyKps(2, cid))
      },
    })
    const { wrapper } = await mountPage(f)
    expect(wrapper.get('[data-test="sg-error"]').text()).toContain('无法连接服务器')
    await wrapper.get('[data-test="sg-retry"]').trigger('click')
    await flushPromises()
    expect(wrapper.find('[data-test="sg-error"]').exists()).toBe(false)
    expect(wrapper.findComponent(GraphCanvas).exists()).toBe(true)
  })

  it('读图时版本已不存在（NOT_FOUND）：提示重新加载', async () => {
    const f = fakes({ graph: async () => Promise.reject(apiError(404, 'NOT_FOUND')) })
    const { wrapper } = await mountPage(f)
    expect(wrapper.get('[data-test="sg-error"]').text()).toContain('版本已更新')
    expect(wrapper.find('[data-test="sg-retry"]').exists()).toBe(true)
  })

  it('COURSE_FORBIDDEN：离开图谱页回课程列表并提示', async () => {
    const f = fakes({ course: async () => Promise.reject(apiError(403, 'COURSE_FORBIDDEN')) })
    const { router } = await mountPage(f)
    await flushPromises()
    expect(router.currentRoute.value.name).toBe('student-home')
    expect(router.currentRoute.value.query.notice).toBe('course-forbidden')
    expect(f.graph.getPublished).not.toHaveBeenCalled()
  })

  it('切换课程时旧课程的迟到响应被丢弃', async () => {
    const slow = deferred<GraphExchange>()
    const f = fakes({
      graph: (cid, v) => (cid === 'c1' ? slow.promise : Promise.resolve(exchange(cid, v, [kp('b1', {}, cid)]))),
    })
    const { wrapper, router } = await mountPage(f)
    await router.push('/courses/c2/graph')
    await flushPromises()
    slow.resolve(exchange('c1', 3, [kp('a1')]))
    await flushPromises()
    await toCards(wrapper)
    expect(cardIds(wrapper)).toEqual(['b1'])
  })
})

// ---------------------------------------------------------------- 页面：图/卡片切换与联动

describe('H11 学生图谱页：图/卡片切换', () => {
  it('默认图谱视图；切换按钮 aria-pressed 反映当前视图', async () => {
    const { wrapper } = await mountPage(fakes())
    expect(wrapper.get('[data-test="sg-mode-graph"]').attributes('aria-pressed')).toBe('true')
    expect(wrapper.findComponent(GraphCanvas).exists()).toBe(true)
    await toCards(wrapper)
    expect(wrapper.get('[data-test="sg-mode-cards"]').attributes('aria-pressed')).toBe('true')
    expect(wrapper.get('[data-test="sg-mode-graph"]').attributes('aria-pressed')).toBe('false')
    expect(wrapper.findComponent(GraphCanvas).exists()).toBe(false)
    expect(cardIds(wrapper)).toHaveLength(5)
  })

  it('学生视图不显示审核状态筛选', async () => {
    const { wrapper } = await mountPage(fakes())
    expect(wrapper.find('[data-test="relation-legend"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="status-filter"]').exists()).toBe(false)
  })

  it('搜索同时作用于卡片', async () => {
    const f = fakes({ graph: async (cid, v) => exchange(cid, v, [kp('s', { name: '栈' }), kp('q', { name: '队列' })]) })
    const { wrapper } = await mountPage(f)
    await toCards(wrapper)
    await wrapper.get('input[type="search"]').setValue('栈')
    expect(cardIds(wrapper)).toEqual(['s'])
  })

  it('点卡片打开详情（按已发布课程取详情）', async () => {
    const f = fakes()
    const { wrapper } = await mountPage(f)
    await toCards(wrapper)
    await wrapper.findAll('[data-test="kc-card"]')[1]!.trigger('click')
    await flushPromises()
    expect(f.detail.get).toHaveBeenCalledTimes(1)
    expect(f.detail.get.mock.calls[0]!.slice(0, 2)).toEqual(['c1', 'k02'])
    expect(wrapper.get('[data-test="kd-title"]').text()).toBe('知识点 k02')
    expect(wrapper.findAll('[data-test="kc-card"]')[1]!.attributes('aria-pressed')).toBe('true')
  })

  it('图上选中后切到卡片：跳到选中项所在页并标记', async () => {
    const f = fakes({ graph: async (cid, v) => exchange(cid, v, manyKps(30, cid)) })
    const { wrapper } = await mountPage(f)
    wrapper.findComponent(GraphCanvas).vm.$emit('nodeClick', 'k27')
    await flushPromises()
    await toCards(wrapper)
    expect(wrapper.get('[data-test="kc-page"]').text()).toBe('第 3 / 3 页，共 30 个知识点')
    const pressed = wrapper.findAll('[data-test="kc-card"][aria-pressed="true"]')
    expect(pressed.map((card) => card.attributes('data-kp-id'))).toEqual(['k27'])
  })

  it('关闭详情清除选中', async () => {
    const { wrapper } = await mountPage(fakes())
    await toCards(wrapper)
    await wrapper.findAll('[data-test="kc-card"]')[0]!.trigger('click')
    await flushPromises()
    await wrapper.get('[data-test="kd-close"]').trigger('click')
    expect(wrapper.find('[data-test="knowledge-detail"]').exists()).toBe(false)
    expect(wrapper.findAll('[data-test="kc-card"][aria-pressed="true"]')).toHaveLength(0)
  })
})

// ---------------------------------------------------------------- 卡片组件：分页与键盘

function cards(n: number): KnowledgeCard[] {
  return Array.from({ length: n }, (_, i) => ({
    kpId: `k${i + 1}`,
    name: `卡片 ${i + 1}`,
    typeLabel: '概念',
    chapterLabel: '第一章',
    level: 1,
  }))
}

function mountCards(props: { cards: KnowledgeCard[]; selectedId?: string | null; pageSize?: number }) {
  return mount(KnowledgeCards, { props, attachTo: document.body })
}

function visibleIds(wrapper: VueWrapper): string[] {
  return cardIds(wrapper)
}

describe('H11 卡片分页', () => {
  it('按页大小分页，首末页禁用翻页按钮', async () => {
    const wrapper = mountCards({ cards: cards(25), pageSize: 10 })
    expect(visibleIds(wrapper)).toEqual(cards(10).map((c) => c.kpId))
    expect(wrapper.get('[data-test="kc-prev"]').attributes('disabled')).toBeDefined()
    expect(wrapper.get('[data-test="kc-page"]').text()).toBe('第 1 / 3 页，共 25 个知识点')
    await wrapper.get('[data-test="kc-next"]').trigger('click')
    await wrapper.get('[data-test="kc-next"]').trigger('click')
    expect(visibleIds(wrapper)).toEqual(['k21', 'k22', 'k23', 'k24', 'k25'])
    expect(wrapper.get('[data-test="kc-next"]').attributes('disabled')).toBeDefined()
    expect(wrapper.get('[data-test="kc-prev"]').attributes('disabled')).toBeUndefined()
  })

  it('恰好一页时两个翻页按钮都禁用', () => {
    const wrapper = mountCards({ cards: cards(10), pageSize: 10 })
    expect(wrapper.get('[data-test="kc-prev"]').attributes('disabled')).toBeDefined()
    expect(wrapper.get('[data-test="kc-next"]').attributes('disabled')).toBeDefined()
    expect(wrapper.get('[data-test="kc-page"]').text()).toBe('第 1 / 1 页，共 10 个知识点')
  })

  it('空列表显示空态，不显示分页', () => {
    const wrapper = mountCards({ cards: [] })
    expect(wrapper.find('[data-test="kc-empty"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="kc-next"]').exists()).toBe(false)
  })

  it('列表变短时页码收回到最后一页', async () => {
    const wrapper = mountCards({ cards: cards(25), pageSize: 10 })
    await wrapper.get('[data-test="kc-next"]').trigger('click')
    await wrapper.get('[data-test="kc-next"]').trigger('click')
    await wrapper.setProps({ cards: cards(12) })
    expect(wrapper.get('[data-test="kc-page"]').text()).toBe('第 2 / 2 页，共 12 个知识点')
    expect(visibleIds(wrapper)).toEqual(['k11', 'k12'])
  })

  it('选中项变化时跳到其所在页', async () => {
    const wrapper = mountCards({ cards: cards(25), pageSize: 10, selectedId: null })
    await wrapper.setProps({ selectedId: 'k15' })
    expect(wrapper.get('[data-test="kc-page"]').text()).toContain('第 2 / 3 页')
    expect(wrapper.get('[data-kp-id="k15"]').attributes('aria-pressed')).toBe('true')
  })

  it('非法页大小回退为 12', () => {
    const wrapper = mountCards({ cards: cards(30), pageSize: 0 })
    expect(visibleIds(wrapper)).toHaveLength(12)
  })

  it('点击只发 select，不自存选中', async () => {
    const wrapper = mountCards({ cards: cards(3) })
    await wrapper.findAll('[data-test="kc-card"]')[2]!.trigger('click')
    expect(wrapper.emitted('select')).toEqual([['k3']])
    expect(wrapper.findAll('[aria-pressed="true"]')).toHaveLength(0)
  })

  it('文本插值渲染，不执行 HTML', () => {
    const wrapper = mountCards({ cards: [{ ...cards(1)[0]!, name: '<img src=x onerror="window.__h11=1">' }] })
    expect(wrapper.find('img').exists()).toBe(false)
    expect(wrapper.text()).toContain('<img src=x')
  })
})

describe('H11 卡片键盘操作', () => {
  const focusedId = () => (document.activeElement as HTMLElement | null)?.getAttribute('data-kp-id')

  it('卡片组只占一个 Tab 位，落在选中项上', () => {
    const wrapper = mountCards({ cards: cards(5), selectedId: 'k3' })
    const tabbable = wrapper.findAll('[data-test="kc-card"][tabindex="0"]')
    expect(tabbable.map((card) => card.attributes('data-kp-id'))).toEqual(['k3'])
    expect(wrapper.findAll('[data-test="kc-card"][tabindex="-1"]')).toHaveLength(4)
  })

  it('方向键在卡片间移动焦点，Home/End 到首尾', async () => {
    const wrapper = mountCards({ cards: cards(5) })
    const first = wrapper.findAll('[data-test="kc-card"]')[0]!
    ;(first.element as HTMLElement).focus()
    await first.trigger('keydown', { key: 'ArrowRight' })
    await flushPromises()
    expect(focusedId()).toBe('k2')
    await wrapper.get('[data-kp-id="k2"]').trigger('keydown', { key: 'ArrowDown' })
    await flushPromises()
    expect(focusedId()).toBe('k3')
    await wrapper.get('[data-kp-id="k3"]').trigger('keydown', { key: 'ArrowLeft' })
    await flushPromises()
    expect(focusedId()).toBe('k2')
    await wrapper.get('[data-kp-id="k2"]').trigger('keydown', { key: 'End' })
    await flushPromises()
    expect(focusedId()).toBe('k5')
    await wrapper.get('[data-kp-id="k5"]').trigger('keydown', { key: 'Home' })
    await flushPromises()
    expect(focusedId()).toBe('k1')
    expect(wrapper.get('[data-kp-id="k1"]').attributes('tabindex')).toBe('0')
  })

  it('方向键越过页边自动翻页并聚焦', async () => {
    const wrapper = mountCards({ cards: cards(15), pageSize: 10 })
    await wrapper.get('[data-kp-id="k1"]').trigger('keydown', { key: 'End' })
    await flushPromises()
    await wrapper.get('[data-kp-id="k10"]').trigger('keydown', { key: 'ArrowRight' })
    await flushPromises()
    expect(wrapper.get('[data-test="kc-page"]').text()).toContain('第 2 / 2 页')
    expect(focusedId()).toBe('k11')
    await wrapper.get('[data-kp-id="k11"]').trigger('keydown', { key: 'ArrowUp' })
    await flushPromises()
    expect(wrapper.get('[data-test="kc-page"]').text()).toContain('第 1 / 2 页')
    expect(focusedId()).toBe('k10')
  })

  it('首页首卡按上、末页末卡按下不动', async () => {
    const wrapper = mountCards({ cards: cards(3) })
    ;(wrapper.get('[data-kp-id="k1"]').element as HTMLElement).focus()
    await wrapper.get('[data-kp-id="k1"]').trigger('keydown', { key: 'ArrowUp' })
    await flushPromises()
    expect(focusedId()).toBe('k1')
    ;(wrapper.get('[data-kp-id="k3"]').element as HTMLElement).focus()
    await wrapper.get('[data-kp-id="k3"]').trigger('keydown', { key: 'ArrowDown' })
    await flushPromises()
    expect(focusedId()).toBe('k3')
  })

  it('PageDown/PageUp 翻页并保持焦点在卡片上', async () => {
    const wrapper = mountCards({ cards: cards(25), pageSize: 10 })
    await wrapper.get('[data-kp-id="k1"]').trigger('keydown', { key: 'PageDown' })
    await flushPromises()
    expect(wrapper.get('[data-test="kc-page"]').text()).toContain('第 2 / 3 页')
    expect(focusedId()).toBe('k11')
    await wrapper.get('[data-kp-id="k11"]').trigger('keydown', { key: 'PageUp' })
    await flushPromises()
    expect(focusedId()).toBe('k1')
  })

  it('处理过的按键阻止默认滚动，其他按键不拦截', async () => {
    const wrapper = mountCards({ cards: cards(3) })
    const down = new KeyboardEvent('keydown', { key: 'ArrowDown', cancelable: true, bubbles: true })
    wrapper.get('[data-kp-id="k1"]').element.dispatchEvent(down)
    expect(down.defaultPrevented).toBe(true)
    const tab = new KeyboardEvent('keydown', { key: 'Tab', cancelable: true, bubbles: true })
    wrapper.get('[data-kp-id="k2"]').element.dispatchEvent(tab)
    expect(tab.defaultPrevented).toBe(false)
  })

  it('卡片是原生按钮，Enter/空格触发选择', () => {
    const wrapper = mountCards({ cards: cards(2) })
    const card = wrapper.get('[data-kp-id="k1"]')
    expect(card.element.tagName).toBe('BUTTON')
    expect(card.attributes('type')).toBe('button')
  })
})
