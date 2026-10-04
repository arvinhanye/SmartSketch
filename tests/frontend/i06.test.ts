import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { createPinia, setActivePinia, type Pinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { defineComponent, h, ref } from 'vue'
import { createMemoryHistory, RouterView } from 'vue-router'
import type { components } from '../../src/contracts/v1/generated/typescript/openapi'
import { COURSES_API_KEY, type CoursesApi } from '../../src/frontend/src/api/courses'
import { createPublishedGraphApi, PUBLISHED_GRAPH_API_KEY, type PublishedGraphApi } from '../../src/frontend/src/api/graph'
import { ApiError, createHttpClient, NetworkError, type FetchLike } from '../../src/frontend/src/api/http'
import { KNOWLEDGE_DETAIL_API_KEY, type KnowledgeDetailApi } from '../../src/frontend/src/api/knowledgeDetail'
import { createProgressApi, PROGRESS_API_KEY, type ProgressApi } from '../../src/frontend/src/api/progress'
import { createRecommendApi, RECOMMEND_API_KEY, type RecommendApi } from '../../src/frontend/src/api/recommend'
import Recommendations from '../../src/frontend/src/components/Recommendations.vue'
import GraphCanvas from '../../src/frontend/src/components/GraphCanvas.vue'
import {
  applyLearningStates,
  MASTERY_LABELS,
  masteryElementStates,
  PRIMARY_FACTOR_LABELS,
  reasonFactRows,
  useLearning,
  weightedFactRows,
} from '../../src/frontend/src/composables/useLearning'
import { toG6Data } from '../../src/frontend/src/graph/adapter'
import { buildGraphOptions, GRAPH_FACTORY_KEY, type CanvasGraph, type CanvasGraphFactory, type GraphCanvasData } from '../../src/frontend/src/graph/lifecycle'
import { createAppRouter } from '../../src/frontend/src/router/index.ts'
import { useCourseStore } from '../../src/frontend/src/stores/course'
import { useSessionStore } from '../../src/frontend/src/stores/session'
import CoursesView from '../../src/frontend/src/views/CoursesView.vue'
import StudentGraphView from '../../src/frontend/src/views/StudentGraphView.vue'

type Course = components['schemas']['Course']
type GraphExchange = components['schemas']['GraphExchange']
type KnowledgePoint = components['schemas']['KnowledgePoint']
type KnowledgePointDetail = components['schemas']['KnowledgePointDetail']
type MasteryStatus = components['schemas']['MasteryStatus']
type ProgressEntry = components['schemas']['ProgressEntry']
type ProgressResponse = components['schemas']['ProgressResponse']
type Recommendation = components['schemas']['Recommendation']
type RecommendResponse = components['schemas']['RecommendResponse']
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
  } as Course
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

function exchange(cid: string, version: number | null, nodes: KnowledgePoint[], edges: GraphExchange['edges'] = []): GraphExchange {
  return {
    format_version: '1.0',
    course_id: cid,
    graph_version: version,
    generated_at: '2026-09-27T00:00:00Z',
    chapters: [{ id: 'ch1', title: '第一章 线性表', order: 1 }],
    nodes,
    edges,
  }
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

function entry(kpId: string, status: MasteryStatus, overrides: Partial<ProgressEntry> = {}): ProgressEntry {
  const own = overrides.own_status === undefined ? status : overrides.own_status
  return {
    kp_id: kpId,
    status,
    own_status: own,
    inherited_from: overrides.inherited_from ?? [],
    updated_at: own === null ? null : (overrides.updated_at ?? '2026-09-27T00:00:00Z'),
  }
}

function progressResponse(version: number, entries: ProgressEntry[]): ProgressResponse {
  return { graph_version: version, entries }
}

function recommendation(kpId: string, overrides: Partial<Recommendation> = {}): Recommendation {
  return {
    kp_id: kpId,
    name: `知识点 ${kpId}`,
    graph_version: 3,
    score: 0.725,
    factors: { unlock: 0.5, importance: 1, chapter_order: 1, ease: 0.5 },
    weighted: { unlock: 0.175, importance: 0.25, chapter_order: 0.2, ease: 0.1 },
    unlock_count: 2,
    reason: `完成该点可立即解锁 2 个知识点（解锁度 1.0000）`,
    reason_facts: {
      primary_factor: 'unlock',
      chapter_id: 'ch1',
      chapter_name: '第一章 线性表',
      chapter_rank: 0,
      importance: 1,
      centrality: 1,
      difficulty: 0.5,
      importance_defaulted: false,
      difficulty_defaulted: true,
    },
    ...overrides,
  }
}

function recommendList(version: number, items: Recommendation[]): RecommendResponse {
  return { state: 'recommendations', graph_version: version, total_eligible: items.length, recommendations: items }
}

function allMastered(version: number): RecommendResponse {
  return { state: 'all_mastered', graph_version: version, total_eligible: 0, recommendations: [] }
}

function apiError(status: number, code: ErrorCode, details?: Record<string, unknown>): ApiError {
  return new ApiError(status, { code, message: '服务端原文', details })
}

function notInPublishedVersion(version: number): ApiError {
  return apiError(422, 'VALIDATION_ERROR', {
    fields: [{ in: 'body', field: '0.kp_id', reason: 'not_in_published_version' }],
    graph_version: version,
  })
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

/** 假后端：进度与推荐都在 `server` 上，写进度会真实改变掌握状态 */
function fakes(
  opts: {
    course?: CoursesApi['get']
    graph?: PublishedGraphApi['getPublished']
    progress?: ProgressApi['get']
    update?: ProgressApi['update']
    recommend?: RecommendApi['get']
  } = {},
) {
  const server = {
    version: 3,
    status: new Map<string, MasteryStatus>([['k1', 'unknown'], ['k2', 'unknown'], ['k3', 'unknown']]),
  }
  const defaultProgress: ProgressApi['get'] = async (_cid) => {
    const entries = [...server.status].map(([id, status]) => entry(id, status))
    return progressResponse(server.version, entries)
  }
  const progress = { get: vi.fn<ProgressApi['get']>(opts.progress ?? defaultProgress) }
  const update = vi.fn<ProgressApi['update']>(
    opts.update ??
      (async (_cid, updates) => {
        for (const item of updates) server.status.set(item.kp_id, item.status)
        return progressResponse(server.version, [...server.status].map(([id, status]) => entry(id, status)))
      }),
  )
  const recommend = {
    get: vi.fn<RecommendApi['get']>(opts.recommend ?? (async (_cid) => recommendList(server.version, [recommendation('k3')]))),
  }
  return {
    server,
    progress: { get: progress.get, update },
    recommend,
    courses: { get: vi.fn<CoursesApi['get']>(opts.course ?? (async (cid) => course(cid))) },
    graph: {
      getPublished: vi.fn<PublishedGraphApi['getPublished']>(
        opts.graph ?? (async (cid, version) => exchange(cid, version, [kp('k1'), kp('k2'), kp('k3')])),
      ),
    },
    detail: { get: vi.fn<KnowledgeDetailApi['get']>(async (cid, kid) => detail(cid, kid)) },
  }
}
type Fakes = ReturnType<typeof fakes>

let pinia: Pinia

beforeEach(() => {
  sessionStorage.clear()
  pinia = createPinia()
  setActivePinia(pinia)
})

afterEach(() => {
  vi.restoreAllMocks()
  document.body.innerHTML = ''
})

async function mountPage(f: Fakes, path = '/courses/c1/graph', accountRole: 'student' | 'teacher' = 'student', withLearning = true) {
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
  const provide: Record<symbol, unknown> = {
    [COURSES_API_KEY as symbol]: { list: async () => [], create: vi.fn(), get: f.courses.get },
    [PUBLISHED_GRAPH_API_KEY as symbol]: f.graph,
    [KNOWLEDGE_DETAIL_API_KEY as symbol]: f.detail,
    [GRAPH_FACTORY_KEY as symbol]: fakeCanvasFactory(),
  }
  if (withLearning) {
    provide[PROGRESS_API_KEY as symbol] = f.progress
    provide[RECOMMEND_API_KEY as symbol] = f.recommend
  }
  const wrapper = mount(defineComponent({ render: () => h(RouterView) }), {
    attachTo: document.body,
    global: { plugins: [pinia, router], provide },
  })
  await flushPromises()
  return { wrapper, router }
}

/** 选中一个知识点（图上点选），掌握标记按钮随之出现 */
async function selectNode(wrapper: VueWrapper, kpId: string): Promise<void> {
  wrapper.findComponent(GraphCanvas).vm.$emit('nodeClick', kpId)
  await flushPromises()
}

/** 掌握与推荐状态；L14 叠加的学习路径状态在 l14.test.ts 单独断言，这里滤掉 */
const PATH_STATES: ReadonlySet<string> = new Set(['dimmed', 'pathPrereq', 'pathUnlock'])
function nodeStates(wrapper: VueWrapper): Map<string, readonly string[]> {
  const graph = wrapper.findComponent(GraphCanvas).props('graph') as GraphCanvasData | null
  return new Map((graph?.nodes ?? []).map((node) => [node.data.kpId, (node.states ?? []).filter((s) => !PATH_STATES.has(s))]))
}

function masteryButtons(wrapper: VueWrapper): Array<ReturnType<VueWrapper['get']>> {
  return (['unknown', 'learning', 'mastered'] as const).map((value) => wrapper.get(`[data-test="sg-mastery-${value}"]`))
}

// ---------------------------------------------------------------- API 封装

describe('I06 进度 API 封装', () => {
  function recordingFetch(body: unknown) {
    const calls: Array<{ url: string; method: string; body: unknown }> = []
    const fetch: FetchLike = async (url, init) => {
      calls.push({
        url,
        method: init?.method ?? 'GET',
        body: init?.body === undefined ? undefined : JSON.parse(String(init.body)),
      })
      return new Response(JSON.stringify(body), { status: 200, headers: { 'Content-Type': 'application/json' } })
    }
    return { calls, fetch }
  }

  it('GET /progress 按契约路径取进度，不带多余参数', async () => {
    const { calls, fetch } = recordingFetch(progressResponse(3, [entry('k1', 'unknown')]))
    const api = createProgressApi(createHttpClient({ fetch, getAccessToken: () => 'tok' }))
    await api.get('c/1')
    expect(calls).toEqual([{ url: '/api/v1/courses/c%2F1/progress', method: 'GET', body: undefined }])
  })

  it('PUT /progress 的请求体只有 kp_id 与 status（不自造 graph_version 等字段）', async () => {
    const { calls, fetch } = recordingFetch(progressResponse(3, [entry('k1', 'mastered')]))
    const api = createProgressApi(createHttpClient({ fetch, getAccessToken: () => 'tok' }))
    await api.update('c1', [{ kp_id: 'k1', status: 'mastered' }])
    expect(calls).toEqual([
      { url: '/api/v1/courses/c1/progress', method: 'PUT', body: [{ kp_id: 'k1', status: 'mastered' }] },
    ])
  })

  it('空批次本地拒绝，不发请求（契约 minItems = 1）', async () => {
    const { calls, fetch } = recordingFetch({})
    const api = createProgressApi(createHttpClient({ fetch }))
    await expect(api.update('c1', [])).rejects.toBeInstanceOf(RangeError)
    expect(calls).toEqual([])
  })

  it('GET /recommend 带 limit 查询参数', async () => {
    const { calls, fetch } = recordingFetch(allMastered(3))
    const api = createRecommendApi(createHttpClient({ fetch, getAccessToken: () => 'tok' }))
    await api.get('c/1', { limit: 5 })
    expect(calls).toEqual([{ url: '/api/v1/courses/c%2F1/recommend?limit=5', method: 'GET', body: undefined }])
  })

  it('limit 超出 1～50 本地拒绝，不发请求', async () => {
    const { calls, fetch } = recordingFetch({})
    const api = createRecommendApi(createHttpClient({ fetch }))
    await expect(api.get('c1', { limit: 51 })).rejects.toBeInstanceOf(RangeError)
    expect(calls).toEqual([])
  })
})

// ---------------------------------------------------------------- 纯函数

describe('I06 掌握状态到节点视觉属性（纯函数）', () => {
  const graph: GraphCanvasData = toG6Data(exchange('c1', 3, [kp('k1'), kp('k2'), kp('k3')]))

  it('掌握状态映射为节点 states，推荐项叠加 recommended', () => {
    const entries = new Map([
      ['k1', entry('k1', 'mastered')],
      ['k2', entry('k2', 'learning')],
    ])
    const result = applyLearningStates(graph, entries, new Set(['k3']))
    const states = new Map(result.nodes.map((node) => [node.data.kpId, node.states]))
    expect(states.get('k1')).toEqual(['mastered'])
    expect(states.get('k2')).toEqual(['learning'])
    expect(states.get('k3')).toEqual(['notStarted', 'recommended'])
  })

  it('保留筛选层已有的状态（选中）与边，不修改输入', () => {
    const selected: GraphCanvasData = {
      nodes: graph.nodes.map((node) => (node.data.kpId === 'k1' ? { ...node, states: ['selected' as const] } : node)),
      edges: graph.edges,
    }
    const before = JSON.stringify(selected)
    const result = applyLearningStates(selected, new Map([['k1', entry('k1', 'mastered')]]), new Set())
    expect(result.nodes.find((node) => node.data.kpId === 'k1')?.states).toEqual(['mastered', 'selected'])
    expect(result.edges).toEqual(selected.edges)
    expect(JSON.stringify(selected)).toBe(before)
  })

  it('无记录的节点是 notStarted（不是硬编码的固定色）', () => {
    expect(masteryElementStates('unknown', false)).toEqual(['notStarted'])
    expect(masteryElementStates('mastered', true)).toEqual(['mastered', 'recommended'])
    expect(masteryElementStates('learning', false)).toEqual(['learning'])
    expect(MASTERY_LABELS).toEqual({ unknown: '未开始', learning: '学习中', mastered: '已掌握' })
  })

  it('画布为四个学习状态定义了样式（状态色真实接线，不是测试里的硬编码）', () => {
    const options = buildGraphOptions({ container: document.createElement('div'), width: 100, height: 100, data: graph })
    const nodeState = (options.node as { state: Record<string, unknown> }).state
    // L14 追加的学习路径状态（dimmed/pathPrereq/pathUnlock）另见 l14.test.ts
    expect(Object.keys(nodeState).sort()).toEqual(
      ['dimmed', 'learning', 'lowConfidence', 'mastered', 'notStarted', 'pathPrereq', 'pathUnlock', 'recommended', 'rejected', 'selected'],
    )
    expect(nodeState.mastered).toMatchObject({ stroke: '#52c41a' })
  })
})

describe('I06 推荐理由与服务端分量一致（纯函数）', () => {
  it('理由行逐条取自服务端结构事实与分量，不做任何换算', () => {
    const item = recommendation('k1')
    const rows = new Map(reasonFactRows(item).map((row) => [row.key, row.value]))
    expect(rows.get('unlock_count')).toBe('2 个')
    expect(rows.get('importance')).toBe('1.0000')
    expect(rows.get('centrality')).toBe('1.0000')
    // L14-3：缺失属性的中性值 0.5 不冒充测量值
    expect(rows.get('difficulty')).toBe('未标注（按中性值 0.5 排序）')
    expect(rows.get('chapter')).toBe('第一章 线性表（秩 0）')
    expect(rows.get('primary_factor')).toBe(PRIMARY_FACTOR_LABELS.unlock)
    const weighted = new Map(weightedFactRows(item).map((row) => [row.key, row.value]))
    expect(weighted.get('weighted_unlock')).toBe('0.1750')
    expect(weighted.get('weighted_importance')).toBe('0.2500')
    expect(weighted.get('weighted_chapter_order')).toBe('0.2000')
    expect(weighted.get('weighted_ease')).toBe('0.1000')
    expect(weighted.get('score')).toBe('0.7250')
  })

  it('服务端 score 与加权分量不一致时原样展示服务端值，不自行求和', () => {
    const item = recommendation('k1', { score: 9.99 })
    const weighted = new Map(weightedFactRows(item).map((row) => [row.key, row.value]))
    expect(weighted.get('score')).toBe('9.9900')
    expect([...weighted.values()]).not.toContain('0.7250')
  })

  it('无章节节点的章节事实为未分章，不编造章名', () => {
    const item = recommendation('k1', {
      reason_facts: { primary_factor: 'ease', chapter_id: null, chapter_name: null, chapter_rank: null, importance: 0.5, centrality: 0, difficulty: 0.25 },
    })
    const rows = new Map(reasonFactRows(item).map((row) => [row.key, row.value]))
    expect(rows.get('chapter')).toBe('未分章')
    expect(rows.get('primary_factor')).toBe(PRIMARY_FACTOR_LABELS.ease)
  })
})

// ---------------------------------------------------------------- Recommendations 组件

type RecommendationsProps = {
  state: 'recommendations' | 'all_mastered' | null
  items: readonly Recommendation[]
  totalEligible: number
  version?: number | null
  loading?: boolean
  error?: string | null
  selectedId?: string | null
}

function mountRecommendations(props: RecommendationsProps) {
  return mount(Recommendations, { props, attachTo: document.body })
}

describe('I06 推荐列表组件', () => {
  it('渲染服务端理由与逐条事实，不重算分量', () => {
    const item = recommendation('k1')
    const wrapper = mountRecommendations({
      state: 'recommendations',
      items: [item],
      totalEligible: 2,
      version: 3,
      selectedId: 'k1',
    })
    expect(wrapper.get('[data-test="rc-reason"]').text()).toBe(item.reason)
    const facts = new Map(wrapper.findAll('[data-test="rc-fact"]').map((row) => [row.attributes('data-fact')!, row.find('dd').text()]))
    expect(facts.get('unlock_count')).toBe('2 个')
    expect(facts.get('chapter')).toBe('第一章 线性表（秩 0）')
    expect(facts.get('importance')).toBe('1.0000')
    expect(wrapper.get('[data-test="rc-item"]').attributes('data-primary-factor')).toBe('unlock')
    expect(wrapper.get('[data-test="rc-total"]').text()).toContain('2')
    expect(wrapper.get('[data-test="rc-version"]').text()).toContain('v3')
  })

  it('推荐项高亮来自选中项，点击发出 select', async () => {
    const wrapper = mountRecommendations({
      state: 'recommendations',
      items: [recommendation('k1'), recommendation('k3')],
      totalEligible: 2,
      selectedId: 'k3',
    })
    const items = wrapper.findAll('[data-test="rc-item"]')
    expect(items.map((item) => item.attributes('data-highlighted'))).toEqual(['false', 'true'])
    await wrapper.get('[data-test="rc-select-k1"]').trigger('click')
    expect(wrapper.emitted('select')).toEqual([['k1']])
  })

  it('all_mastered 是空态而不是错误', () => {
    const wrapper = mountRecommendations({ state: 'all_mastered', items: [], totalEligible: 0, version: 3 })
    expect(wrapper.find('[data-test="rc-all-mastered"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="rc-error"]').exists()).toBe(false)
  })

  it('加载中与失败重试', async () => {
    const loading = mountRecommendations({ state: null, items: [], totalEligible: 0, loading: true })
    expect(loading.find('[data-test="rc-loading"]').exists()).toBe(true)
    const failed = mountRecommendations({ state: null, items: [], totalEligible: 0, error: '推荐加载失败，请稍后重试。' })
    expect(failed.get('[data-test="rc-error"]').text()).toContain('推荐加载失败')
    await failed.get('[data-test="rc-retry"]').trigger('click')
    expect(failed.emitted('retry')).toHaveLength(1)
  })
})

// ---------------------------------------------------------------- 组合式独立测试

function mountLearningHost(options: {
  courseId: string | null
  graphVersion: number | null
  ready: boolean
  progressApi: ProgressApi | null
  recommendApi: RecommendApi | null
  onVersionStale?: () => void
}) {
  let api: ReturnType<typeof useLearning> | null = null
  const host = defineComponent({
    setup() {
      api = useLearning({
        progressApi: options.progressApi,
        recommendApi: options.recommendApi,
        courseId: ref(options.courseId),
        graphVersion: ref(options.graphVersion),
        ready: ref(options.ready),
        onVersionStale: options.onVersionStale,
      })
      return () => h('div')
    },
  })
  // 组合式的写入需要课程作用域：store 里先选中课程，等价于页面已进入该课程
  useCourseStore(pinia).selectCourse('c1')
  const wrapper = mount(host, { global: { plugins: [pinia] } })
  return { wrapper, api: api as unknown as ReturnType<typeof useLearning> }
}

describe('I06 掌握标记的组合式行为', () => {
  it('无绑定发布版本时不读也不写（乐观标记必须带绑定版本）', async () => {
    const f = fakes()
    const { api } = mountLearningHost({
      courseId: 'c1',
      graphVersion: null,
      ready: true,
      progressApi: f.progress,
      recommendApi: f.recommend,
    })
    await flushPromises()
    expect(api.status.value).toBe('idle')
    expect(f.progress.get).not.toHaveBeenCalled()
    expect(f.recommend.get).not.toHaveBeenCalled()
    await api.setMastery('k1', 'mastered')
    expect(f.progress.update).not.toHaveBeenCalled()
  })

  it('同一节点在途写入时忽略后续调用（不依赖按钮是否禁用）', async () => {
    const pending = deferred<ProgressResponse>()
    const f = fakes({ update: () => pending.promise })
    const { api } = mountLearningHost({
      courseId: 'c1',
      graphVersion: 3,
      ready: true,
      progressApi: f.progress,
      recommendApi: f.recommend,
    })
    await flushPromises()
    expect(api.status.value).toBe('ready')
    const first = api.setMastery('k1', 'mastered')
    expect(api.busyKpId.value).toBe('k1')
    // 直接调用组合式的写入入口：绕过按钮的 disabled，单独钉住「单一在途写入」这道闸
    const second = api.setMastery('k1', 'learning')
    const third = api.setMastery('k2', 'unknown')
    expect(f.progress.update).toHaveBeenCalledTimes(1)
    pending.resolve(progressResponse(3, [entry('k1', 'mastered')]))
    await Promise.all([first, second, third])
    await flushPromises()
    expect(f.progress.update).toHaveBeenCalledTimes(1)
    expect(api.busyKpId.value).toBe(null)
  })

  it('写入响应的发布版本与显示版本不一致时不当作成功写入，并请求重载图谱', async () => {
    const f = fakes({
      update: async () => progressResponse(4, [entry('k1', 'mastered')]),
    })
    const onVersionStale = vi.fn()
    const { api } = mountLearningHost({
      courseId: 'c1',
      graphVersion: 3,
      ready: true,
      progressApi: f.progress,
      recommendApi: f.recommend,
      onVersionStale,
    })
    await flushPromises()
    await api.setMastery('k1', 'mastered')
    await flushPromises()
    expect(onVersionStale).toHaveBeenCalledTimes(1)
    expect(api.versionStale.value).toBe(true)
    expect(api.notice.value?.text).toContain('新版本')
  })
})

// ---------------------------------------------------------------- 页面：加载与空态

describe('I06 学生图谱页：进度与推荐加载', () => {
  it('读进度与推荐都绑定图谱版本；节点状态色与推荐高亮来自服务端状态', async () => {
    const f = fakes({
      progress: async () => progressResponse(3, [entry('k1', 'mastered'), entry('k2', 'learning'), entry('k3', 'unknown')]),
      recommend: async () => recommendList(3, [recommendation('k3')]),
    })
    const { wrapper } = await mountPage(f)
    expect(f.progress.get).toHaveBeenCalledWith('c1', expect.anything())
    expect(f.recommend.get).toHaveBeenCalledWith('c1', {}, expect.anything())
    const states = nodeStates(wrapper)
    expect(states.get('k1')).toEqual(['mastered'])
    expect(states.get('k2')).toEqual(['learning'])
    expect(states.get('k3')).toEqual(['notStarted', 'recommended'])
    expect(wrapper.get('[data-test="rc-item"]').attributes('data-kp-id')).toBe('k3')
  })

  it('全部掌握（200 all_mastered）是空态，不是错误', async () => {
    const f = fakes({
      progress: async () => progressResponse(3, [entry('k1', 'mastered'), entry('k2', 'mastered'), entry('k3', 'mastered')]),
      recommend: async () => allMastered(3),
    })
    const { wrapper } = await mountPage(f)
    expect(wrapper.find('[data-test="rc-all-mastered"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="sg-learning-error"]').exists()).toBe(false)
    expect(nodeStates(wrapper).get('k1')).toEqual(['mastered'])
  })

  it('未发布（404 GRAPH_NOT_PUBLISHED）：空白态、不读图、不读进度与推荐', async () => {
    const f = fakes({ course: async (cid) => course(cid, { status: 'draft', published_version: null }) })
    const { wrapper } = await mountPage(f)
    expect(wrapper.find('[data-test="sg-unpublished"]').exists()).toBe(true)
    expect(f.graph.getPublished).not.toHaveBeenCalled()
    expect(f.progress.get).not.toHaveBeenCalled()
    expect(f.recommend.get).not.toHaveBeenCalled()
    expect(wrapper.find('[data-test="sg-mastery"]').exists()).toBe(false)
    expect(wrapper.find('[data-test="recommendations"]').exists()).toBe(false)
  })

  it('学习接口返回 404 GRAPH_NOT_PUBLISHED：显示未发布且不给可点击入口', async () => {
    const f = fakes({ progress: async () => Promise.reject(apiError(404, 'GRAPH_NOT_PUBLISHED')) })
    const { wrapper } = await mountPage(f)
    expect(wrapper.find('[data-test="sg-learning-unpublished"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="sg-mastery"]').exists()).toBe(false)
    expect(wrapper.find('[data-test="recommendations"]').exists()).toBe(false)
  })

  it('教师角色（403 ROLE_FORBIDDEN）：提示且不给可点击入口', async () => {
    const f = fakes({ progress: async () => Promise.reject(apiError(403, 'ROLE_FORBIDDEN')) })
    const { wrapper } = await mountPage(f)
    expect(wrapper.get('[data-test="sg-learning-forbidden"]').text()).toContain('学生')
    expect(wrapper.find('[data-test="sg-mastery"]').exists()).toBe(false)
    expect(wrapper.find('[data-test="sg-learning-retry"]').exists()).toBe(false)
  })

  it('本课程教师账号：不读图、不读进度与推荐', async () => {
    const f = fakes({ course: async (cid) => course(cid, { my_role: 'teacher' }) })
    const { wrapper } = await mountPage(f, '/courses/c1/graph', 'teacher')
    expect(wrapper.find('[data-test="sg-not-student"]').exists()).toBe(true)
    expect(f.graph.getPublished).not.toHaveBeenCalled()
    expect(f.progress.get).not.toHaveBeenCalled()
    expect(f.recommend.get).not.toHaveBeenCalled()
  })

  it('完整性错误 500：只提示 request_id，不回显服务端 message', async () => {
    const f = fakes({
      progress: async () =>
        Promise.reject(apiError(500, 'INTERNAL_ERROR', { request_id: 'req-abc123' })),
    })
    const { wrapper } = await mountPage(f)
    const text = wrapper.get('[data-test="sg-learning-error"]').text()
    expect(text).toContain('req-abc123')
    expect(text).not.toContain('服务端原文')
    expect(text).not.toContain('节点')
  })

  it('判定顺序：完整性错误优先于 all_mastered 空态', async () => {
    const f = fakes({
      progress: async () => progressResponse(3, [entry('k1', 'mastered'), entry('k2', 'mastered'), entry('k3', 'mastered')]),
      recommend: async () => Promise.reject(apiError(500, 'INTERNAL_ERROR', { request_id: 'req-order' })),
    })
    const { wrapper } = await mountPage(f)
    expect(wrapper.find('[data-test="rc-all-mastered"]').exists()).toBe(false)
    expect(wrapper.get('[data-test="sg-learning-error"]').text()).toContain('req-order')
  })

  it('推荐单独网络失败不影响已读到的进度：只提示推荐可重试', async () => {
    const f = fakes({ recommend: async () => Promise.reject(new NetworkError(new TypeError('offline'))) })
    const { wrapper } = await mountPage(f)
    expect(nodeStates(wrapper).get('k1')).toEqual(['notStarted'])
    expect(wrapper.get('[data-test="rc-error"]').text()).toContain('推荐')
    await wrapper.get('[data-test="rc-retry"]').trigger('click')
    await flushPromises()
    expect(f.recommend.get).toHaveBeenCalledTimes(2)
  })
})

// ---------------------------------------------------------------- 页面：乐观标记与回滚

describe('I06 学生图谱页：乐观掌握标记', () => {
  it('点击立即乐观显示，成功后以服务端投影为准并重算推荐', async () => {
    const f = fakes()
    const { wrapper } = await mountPage(f)
    await selectNode(wrapper, 'k1')
    expect(wrapper.get('[data-test="sg-mastery-target"]').text()).toContain('未开始')
    await wrapper.get('[data-test="sg-mastery-mastered"]').trigger('click')
    await flushPromises()
    expect(f.progress.update).toHaveBeenCalledWith('c1', [{ kp_id: 'k1', status: 'mastered' }], expect.anything())
    expect(wrapper.get('[data-test="sg-mastery-target"]').text()).toContain('已掌握')
    expect(nodeStates(wrapper).get('k1')).toEqual(['mastered', 'selected'])
    expect(wrapper.get('[data-test="sg-learning-notice"]').attributes('data-tone')).toBe('success')
    expect(f.recommend.get).toHaveBeenCalledTimes(2)
  })

  it('乐观标记在 PUT 返回前就显示（不等服务端）', async () => {
    const pending = deferred<ProgressResponse>()
    const f = fakes({ update: () => pending.promise })
    const { wrapper } = await mountPage(f)
    await selectNode(wrapper, 'k1')
    await wrapper.get('[data-test="sg-mastery-mastered"]').trigger('click')
    expect(wrapper.get('[data-test="sg-mastery-target"]').text()).toContain('已掌握')
    expect(nodeStates(wrapper).get('k1')).toEqual(['mastered', 'selected'])
    pending.resolve(progressResponse(3, [entry('k1', 'mastered')]))
    await flushPromises()
  })

  it('网络失败：完整回滚到服务端已知状态，文案固定且不回显服务端原文', async () => {
    const f = fakes({ update: async () => Promise.reject(new NetworkError(new TypeError('offline'))) })
    const { wrapper } = await mountPage(f)
    await selectNode(wrapper, 'k1')
    await wrapper.get('[data-test="sg-mastery-mastered"]').trigger('click')
    expect(wrapper.get('[data-test="sg-mastery-target"]').text()).toContain('已掌握')
    await flushPromises()
    expect(wrapper.get('[data-test="sg-mastery-target"]').text()).toContain('未开始')
    expect(nodeStates(wrapper).get('k1')).toEqual(['notStarted', 'selected'])
    expect(wrapper.get('[data-test="sg-learning-notice"]').attributes('data-tone')).toBe('error')
    expect(wrapper.get('[data-test="sg-learning-notice"]').text()).toContain('已撤销')
    expect(wrapper.text()).not.toContain('服务端原文')
  })

  it('4xx 通用失败同样回滚，并按固定文案提示', async () => {
    const f = fakes({ update: async () => Promise.reject(apiError(422, 'VALIDATION_ERROR', { fields: [] })) })
    const { wrapper } = await mountPage(f)
    await selectNode(wrapper, 'k2')
    await wrapper.get('[data-test="sg-mastery-learning"]').trigger('click')
    await flushPromises()
    expect(wrapper.get('[data-test="sg-mastery-target"]').text()).toContain('未开始')
    expect(wrapper.get('[data-test="sg-learning-notice"]').text()).toContain('已撤销')
    expect(wrapper.text()).not.toContain('服务端原文')
  })

  it('422 not_in_published_version：撤销乐观状态并重新读进度与推荐', async () => {
    const f = fakes({ update: async () => Promise.reject(notInPublishedVersion(3)) })
    let phase = 0
    const base = f.progress.get
    f.progress.get = vi.fn<ProgressApi['get']>(async (cid, control) => {
      phase += 1
      // 第二次读（重读）时该节点已不在发布版：绑定版本仍是 v3，只是不含 k1
      if (phase >= 2) return progressResponse(3, [entry('k2', 'unknown')])
      return base(cid, control)
    })
    const { wrapper } = await mountPage(f)
    await selectNode(wrapper, 'k1')
    await wrapper.get('[data-test="sg-mastery-mastered"]').trigger('click')
    await flushPromises()
    expect(f.progress.get).toHaveBeenCalledTimes(2)
    expect(f.recommend.get).toHaveBeenCalledTimes(2)
    expect(wrapper.get('[data-test="sg-learning-notice"]').text()).toContain('已不在当前发布版本')
    expect(nodeStates(wrapper).get('k1')).toEqual(['notStarted', 'selected'])
  })

  it('同一节点在途写入时连点只发一次，且按钮禁用', async () => {
    const pending = deferred<ProgressResponse>()
    const f = fakes({ update: () => pending.promise })
    const { wrapper } = await mountPage(f)
    await selectNode(wrapper, 'k1')
    await wrapper.get('[data-test="sg-mastery-mastered"]').trigger('click')
    for (const button of masteryButtons(wrapper)) expect(button.attributes('disabled')).toBeDefined()
    await wrapper.get('[data-test="sg-mastery-mastered"]').trigger('click')
    await wrapper.get('[data-test="sg-mastery-learning"]').trigger('click')
    expect(f.progress.update).toHaveBeenCalledTimes(1)
    pending.resolve(progressResponse(3, [entry('k1', 'mastered')]))
    await flushPromises()
    expect(masteryButtons(wrapper)[2]!.attributes('aria-pressed')).toBe('true')
    expect(masteryButtons(wrapper)[2]!.attributes('disabled')).toBeUndefined()
  })

  it('写入响应的发布版本与显示版本不一致：不套用到旧图，改为重新加载图谱', async () => {
    const f = fakes({ update: async () => progressResponse(4, [entry('k1', 'mastered')]) })
    const { wrapper } = await mountPage(f)
    await selectNode(wrapper, 'k1')
    await wrapper.get('[data-test="sg-mastery-mastered"]').trigger('click')
    await flushPromises()
    // 显示中的图已过期：页面重新读图，而不是把 v4 的投影套到 v3 的图上
    expect(f.graph.getPublished).toHaveBeenCalledTimes(2)
    expect(wrapper.find('[data-test="sg-learning-error"]').exists()).toBe(false)
  })
})

// ---------------------------------------------------------------- 页面：切课隔离

describe('I06 切课后旧推荐不覆盖', () => {
  it('课程 A 的推荐迟到响应不写入课程 B 的界面', async () => {
    const slow = deferred<RecommendResponse>()
    const f = fakes({
      recommend: (cid) =>
        cid === 'c1' ? slow.promise : Promise.resolve(recommendList(3, [recommendation('b1')])),
      graph: async (cid, version) => exchange(cid, version, cid === 'c1' ? [kp('a1')] : [kp('b1', {}, cid)]),
      progress: async (cid) =>
        progressResponse(3, [entry(cid === 'c1' ? 'a1' : 'b1', 'unknown')]),
    })
    const { wrapper, router } = await mountPage(f)
    await router.push('/courses/c2/graph')
    await flushPromises()
    slow.resolve(recommendList(3, [recommendation('a1')]))
    await flushPromises()
    const items = wrapper.findAll('[data-test="rc-item"]')
    expect(items.map((item) => item.attributes('data-kp-id'))).toEqual(['b1'])
  })

  it('课程 A 的进度迟到响应不写入课程 B 的节点状态', async () => {
    const slow = deferred<ProgressResponse>()
    const f = fakes({
      progress: (cid) => (cid === 'c1' ? slow.promise : Promise.resolve(progressResponse(3, [entry('b1', 'learning')]))),
      graph: async (cid, version) => exchange(cid, version, cid === 'c1' ? [kp('a1')] : [kp('b1', {}, cid)]),
      recommend: async () => recommendList(3, []),
    })
    const { wrapper, router } = await mountPage(f)
    await router.push('/courses/c2/graph')
    await flushPromises()
    slow.resolve(progressResponse(3, [entry('a1', 'mastered')]))
    await flushPromises()
    const states = nodeStates(wrapper)
    expect(states.get('b1')).toEqual(['learning'])
    expect(states.has('a1')).toBe(false)
  })
})

// ---------------------------------------------------------------- 未注入学习接口时保持 H11 原状

describe('I06 未注入学习接口', () => {
  it('页面照常渲染图谱，不渲染掌握标记与推荐区', async () => {
    const f = fakes()
    const { wrapper } = await mountPage(f, '/courses/c1/graph', 'student', false)
    expect(wrapper.findComponent(GraphCanvas).exists()).toBe(true)
    expect(wrapper.find('[data-test="sg-mastery"]').exists()).toBe(false)
    expect(wrapper.find('[data-test="recommendations"]').exists()).toBe(false)
    expect(f.progress.get).not.toHaveBeenCalled()
  })
})

// ---------------------------------------------------------------- 契约形状校验

describe('I06 响应形状校验', () => {
  it('进度响应缺 entries 或 graph_version 视为异常，不写入界面', async () => {
    const f = fakes({ progress: async () => ({ graph_version: 3 }) as unknown as ProgressResponse })
    const { wrapper } = await mountPage(f)
    expect(wrapper.get('[data-test="sg-learning-error"]').text()).toContain('数据异常')
  })
})

