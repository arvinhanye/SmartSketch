import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { createPinia, setActivePinia, type Pinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { defineComponent, h } from 'vue'
import { createMemoryHistory, RouterView } from 'vue-router'
import type { components } from '../../src/contracts/v1/generated/typescript/openapi'
import { COURSES_API_KEY, type CoursesApi } from '../../src/frontend/src/api/courses'
import { DRAFT_GRAPH_API_KEY, type DraftGraphApi } from '../../src/frontend/src/api/graph'
import { ApiError, createHttpClient, NetworkError, type FetchLike } from '../../src/frontend/src/api/http'
import { createReviewApi, REVIEW_API_KEY, type ReviewAction, type ReviewApi } from '../../src/frontend/src/api/review'
import { duplicateKey, isQueue } from '../../src/frontend/src/composables/useReview'
import { createAppRouter, NOTICE_COURSE_FORBIDDEN, NOTICE_WRONG_ROLE, REVIEW_ROUTE } from '../../src/frontend/src/router/index.ts'
import { useSessionStore } from '../../src/frontend/src/stores/session'
import CoursesView from '../../src/frontend/src/views/CoursesView.vue'
import ReviewView from '../../src/frontend/src/views/ReviewView.vue'

type Course = components['schemas']['Course']
type GraphExchange = components['schemas']['GraphExchange']
type KnowledgePoint = components['schemas']['KnowledgePoint']
type KnowledgePointRef = components['schemas']['KnowledgePointRef']
type Relation = components['schemas']['Relation']
type ReviewQueue = components['schemas']['ReviewQueue']
type SuspectedDuplicate = components['schemas']['SuspectedDuplicate']
type ErrorCode = components['schemas']['ErrorCode']

// ---------------------------------------------------------------- 夹具

function course(id: string, overrides: Partial<Course> = {}): Course {
  return {
    id,
    name: `课程 ${id}`,
    status: 'draft',
    my_role: 'teacher',
    published_version: null,
    created_at: '2026-09-01T00:00:00Z',
    ...overrides,
  } as Course
}

const ref_ = (id: string, name = `知识点 ${id}`): KnowledgePointRef => ({ id, name, type: 'concept' })

function rel(id: string, from: string, to: string, confidence = 0.4): Relation {
  return {
    id,
    course_id: 'c1',
    type: 'PREREQUISITE',
    from_id: from,
    to_id: to,
    confidence,
    status: 'low_confidence',
    source: 'ai',
    source_refs: [{ chunk_id: `${id}-chunk`, document_id: 'doc1', page: 3 }],
  } as Relation
}

function dup(a: KnowledgePointRef, b: KnowledgePointRef, similarity = 1): SuspectedDuplicate {
  return { candidates: [a, b], similarity, reason: 'same_key' }
}

function apiError(status: number, code: ErrorCode, details?: Record<string, unknown>): ApiError {
  return new ApiError(status, { code, message: '服务端原文', details })
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

type Kind = 'low_confidence_relation' | 'suspected_duplicate' | 'isolated_node'
const FIELD = {
  low_confidence_relation: 'low_confidence_relations',
  suspected_duplicate: 'suspected_duplicates',
  isolated_node: 'isolated_nodes',
} as const

/**
 * 假后端：三栏数据在 `server` 上，读队列按下标分页（游标为 `kind:下标`），处理后从队列移除并返回完整条数。
 * 合并时删除被合并节点，并移除引用它的其他条目（模拟 ADR-060 的实时计算）。
 */
function fakes(
  opts: {
    relations?: Relation[]
    duplicates?: SuspectedDuplicate[]
    isolated?: KnowledgePointRef[]
    names?: Record<string, string>
    course?: CoursesApi['get']
  } = {},
) {
  const server = {
    relations: opts.relations ?? [rel('r1', 'k1', 'k2', 0.3), rel('r2', 'k2', 'k3', 0.5)],
    duplicates: opts.duplicates ?? [dup(ref_('k4', '栈'), ref_('k5', '堆栈'))],
    isolated: opts.isolated ?? [ref_('k5', '堆栈'), ref_('k6', '队列')],
    names: opts.names ?? { k1: '线性表', k2: '栈', k3: '括号匹配', k4: '栈', k5: '堆栈', k6: '队列' },
    handled: new Set<string>(),
  }
  const totals = () => ({
    low_confidence_relations: server.relations.length,
    suspected_duplicates: server.duplicates.length,
    isolated_nodes: server.isolated.length,
  })
  function page<T>(kind: Kind, list: T[], cursor: string | undefined, limit: number) {
    const start = cursor === undefined ? 0 : Number(cursor.split(':')[1])
    const slice = list.slice(start, start + limit)
    const next = start + limit < list.length ? `${kind}:${start + limit}` : null
    return { slice, next }
  }
  const getQueue = vi.fn<ReviewApi['getQueue']>(async (_cid, query = {}) => {
    const limit = query.limit ?? 50
    if (query.cursor !== undefined && !query.cursor.startsWith(`${query.kind}:`)) throw apiError(422, 'VALIDATION_ERROR')
    const body: ReviewQueue = {
      low_confidence_relations: [],
      suspected_duplicates: [],
      isolated_nodes: [],
      totals: totals(),
      next_cursors: { low_confidence_relations: null, suspected_duplicates: null, isolated_nodes: null },
    }
    const lists = { low_confidence_relation: server.relations, suspected_duplicate: server.duplicates, isolated_node: server.isolated }
    for (const kind of Object.keys(FIELD) as Kind[]) {
      if (query.kind !== undefined && query.kind !== kind) continue
      const { slice, next } = page(kind, lists[kind] as unknown[], query.cursor, limit)
      ;(body as unknown as Record<string, unknown>)[FIELD[kind]] = slice.map((x) => structuredClone(x))
      body.next_cursors[FIELD[kind]] = next
    }
    return body
  })
  const resolve = vi.fn<ReviewApi['resolve']>(async (_cid, action: ReviewAction) => {
    const done = (changed: boolean) => ({ item: action.item, action: action.action, changed, totals: totals() })
    if (action.item === 'low_confidence_relation') {
      const key = `rel:${action.rel_id}:${action.action}`
      if (server.handled.has(key)) return done(false)
      if (!server.relations.some((r) => r.id === action.rel_id)) throw apiError(404, 'NOT_FOUND')
      server.relations = server.relations.filter((r) => r.id !== action.rel_id)
      server.handled.add(key)
      return done(true)
    }
    if (action.item === 'isolated_node') {
      if (!server.isolated.some((n) => n.id === action.kp_id)) throw apiError(404, 'NOT_FOUND')
      server.isolated = server.isolated.filter((n) => n.id !== action.kp_id)
      return done(true)
    }
    const pairKey = action.kp_ids.join('|')
    if (!server.duplicates.some((d) => d.candidates.map((c) => c.id).join('|') === pairKey)) throw apiError(404, 'NOT_FOUND')
    server.duplicates = server.duplicates.filter((d) => d.candidates.map((c) => c.id).join('|') !== pairKey)
    if (action.action === 'merge') {
      const merged = action.kp_ids.filter((id) => id !== action.primary_id)
      server.isolated = server.isolated.filter((n) => !merged.includes(n.id))
      server.duplicates = server.duplicates.filter((d) => !d.candidates.some((c) => merged.includes(c.id)))
      for (const id of merged) delete server.names[id]
    }
    return done(true)
  })
  const draft = vi.fn<DraftGraphApi['getDraft']>(
    async (cid) =>
      ({
        format_version: '1.0',
        course_id: cid,
        graph_version: null,
        generated_at: '2026-09-27T00:00:00Z',
        nodes: Object.entries(server.names).map(([id, name]) => ({ id, name }) as KnowledgePoint),
        edges: [],
      }) as GraphExchange,
  )
  return {
    server,
    review: { getQueue, resolve },
    draft: { getDraft: draft },
    courses: { get: vi.fn<CoursesApi['get']>(opts.course ?? (async (cid) => course(cid))) },
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

async function mountPage(f: Fakes, path = '/courses/c1/review', accountRole: 'student' | 'teacher' = 'teacher') {
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
    reviewComponent: ReviewView,
  })
  await router.push(path)
  await router.isReady()
  const wrapper = mount(defineComponent({ render: () => h(RouterView) }), {
    attachTo: document.body,
    global: {
      plugins: [pinia, router],
      provide: {
        [COURSES_API_KEY as symbol]: { list: async () => [course('c1')], create: vi.fn(), get: f.courses.get },
        [REVIEW_API_KEY as symbol]: f.review,
        [DRAFT_GRAPH_API_KEY as symbol]: f.draft,
      },
    },
  })
  await flushPromises()
  return { wrapper, router }
}

function totalText(wrapper: VueWrapper, kind: Kind): string {
  return wrapper.find(`[data-test="rv-total-${kind}"]`).text()
}

function headingCounts(wrapper: VueWrapper): string[] {
  return (['low_confidence_relation', 'suspected_duplicate', 'isolated_node'] as const).map((k) => totalText(wrapper, k))
}

function rows(wrapper: VueWrapper, test: 'rv-relation' | 'rv-duplicate' | 'rv-isolated'): string[] {
  return wrapper.findAll(`[data-test="${test}"]`).map((w) => w.attributes('data-id') ?? '')
}

async function click(wrapper: VueWrapper, selector: string): Promise<void> {
  await wrapper.find(selector).trigger('click')
  await flushPromises()
}

// ---------------------------------------------------------------- API 层

describe('审核队列 API', () => {
  it('GET /review 带 kind、cursor、limit；POST /review/actions 原样提交动作', async () => {
    const calls: Array<{ url: string; method: string; body: unknown }> = []
    const fetch: FetchLike = async (url, init) => {
      calls.push({ url, method: init?.method ?? 'GET', body: init?.body === undefined ? undefined : JSON.parse(String(init.body)) })
      return new Response(JSON.stringify({}), { status: 200, headers: { 'Content-Type': 'application/json' } })
    }
    const api = createReviewApi(createHttpClient({ fetch, getAccessToken: () => 'tok' }))
    await api.getQueue('c/1', { kind: 'isolated_node', cursor: 'abc', limit: 10 })
    await api.resolve('c1', { item: 'suspected_duplicate', kp_ids: ['a', 'b'], action: 'merge', primary_id: 'b' })
    expect(calls[0]!.url).toMatch(/^\/api\/v1\/courses\/c%2F1\/review\?/)
    const query = new URLSearchParams(calls[0]!.url.split('?')[1])
    expect(Object.fromEntries(query)).toEqual({ kind: 'isolated_node', cursor: 'abc', limit: '10' })
    expect(calls[1]).toMatchObject({
      url: '/api/v1/courses/c1/review/actions',
      method: 'POST',
      body: { item: 'suspected_duplicate', kp_ids: ['a', 'b'], action: 'merge', primary_id: 'b' },
    })
  })

  it('队列形状校验：缺 totals 或游标不合法视为异常', () => {
    const good = {
      low_confidence_relations: [],
      suspected_duplicates: [],
      isolated_nodes: [],
      totals: { low_confidence_relations: 0, suspected_duplicates: 0, isolated_nodes: 0 },
      next_cursors: { low_confidence_relations: null, suspected_duplicates: null, isolated_nodes: null },
    }
    expect(isQueue(good)).toBe(true)
    expect(isQueue({ ...good, totals: undefined })).toBe(false)
    expect(isQueue({ ...good, next_cursors: { ...good.next_cursors, isolated_nodes: '' } })).toBe(false)
    expect(isQueue({ ...good, suspected_duplicates: [{ candidates: [ref_('a')], similarity: 1 }] })).toBe(false)
  })
})

// ---------------------------------------------------------------- 页面

describe('审核队列页：加载与三类空态', () => {
  it('三栏显示条目与服务端完整条数，关系两端显示名称', async () => {
    const f = fakes()
    const { wrapper } = await mountPage(f)
    expect(headingCounts(wrapper)).toEqual(['低置信度关系（2）', '疑似重复知识点（1）', '孤立知识点（2）'])
    expect(rows(wrapper, 'rv-relation')).toEqual(['r1', 'r2'])
    expect(wrapper.find('[data-test="rv-relation"]').text()).toContain('线性表')
    expect(wrapper.find('[data-test="rv-relation"]').text()).toContain('栈')
    expect(wrapper.find('[data-test="rv-relation"]').text()).toContain('置信度 30%')
    expect(wrapper.find('[data-test="rv-relation"]').text()).toContain('第 3 页')
    expect(rows(wrapper, 'rv-isolated')).toEqual(['k5', 'k6'])
    expect(f.review.getQueue).toHaveBeenCalledWith('c1', { limit: 50 }, expect.anything())
    expect(wrapper.find('[data-test="rv-all-empty"]').exists()).toBe(false)
  })

  it('三栏全空：每栏各自的空态 + 「可以直接发布」', async () => {
    const f = fakes({ relations: [], duplicates: [], isolated: [] })
    const { wrapper } = await mountPage(f)
    expect(wrapper.find('[data-test="rv-all-empty"]').text()).toContain('可以直接发布')
    for (const kind of ['low_confidence_relation', 'suspected_duplicate', 'isolated_node']) {
      expect(wrapper.find(`[data-test="rv-empty-${kind}"]`).exists()).toBe(true)
    }
  })

  it.each<[Kind, Parameters<typeof fakes>[0]]>([
    ['low_confidence_relation', { relations: [] }],
    ['suspected_duplicate', { duplicates: [] }],
    ['isolated_node', { isolated: [] }],
  ])('只有「%s」为空时只显示该栏空态', async (kind, opts) => {
    const { wrapper } = await mountPage(fakes(opts))
    const shown = ['low_confidence_relation', 'suspected_duplicate', 'isolated_node'].filter((k) =>
      wrapper.find(`[data-test="rv-empty-${k}"]`).exists(),
    )
    expect(shown).toEqual([kind])
    expect(wrapper.find('[data-test="rv-all-empty"]').exists()).toBe(false)
  })

  it('处理完最后一条后栏目进入空态；三栏都处理完显示「可以直接发布」', async () => {
    const f = fakes({ relations: [rel('r1', 'k1', 'k2')], duplicates: [], isolated: [] })
    const { wrapper } = await mountPage(f)
    await click(wrapper, '[data-test="rv-approve"]')
    expect(wrapper.find('[data-test="rv-empty-low_confidence_relation"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="rv-all-empty"]').exists()).toBe(true)
  })

  it('草稿名称读取失败不影响审核，关系两端退回显示 ID', async () => {
    const f = fakes()
    f.draft.getDraft.mockRejectedValue(new NetworkError('offline'))
    const { wrapper } = await mountPage(f)
    expect(wrapper.find('[data-test="rv-relation"]').text()).toContain('k1')
    expect(rows(wrapper, 'rv-relation')).toEqual(['r1', 'r2'])
  })

  it('课程内非教师：不读队列，显示无权说明', async () => {
    const f = fakes({ course: async (cid) => course(cid, { my_role: 'student' }) })
    const { wrapper } = await mountPage(f)
    expect(wrapper.find('[data-test="rv-not-teacher"]').exists()).toBe(true)
    expect(f.review.getQueue).not.toHaveBeenCalled()
  })

  it('读队列失败显示错误与重试，重试成功后显示队列', async () => {
    const f = fakes()
    f.review.getQueue.mockRejectedValueOnce(apiError(503, 'STORAGE_UNAVAILABLE'))
    const { wrapper } = await mountPage(f)
    expect(wrapper.find('[data-test="rv-error"]').text()).toContain('图数据库暂不可用')
    await click(wrapper, '[data-test="rv-retry"]')
    expect(rows(wrapper, 'rv-relation')).toEqual(['r1', 'r2'])
  })

  it('401：显示会话过期文案且不可重试（与 5xx 的通用文案区分）', async () => {
    const f = fakes()
    f.review.getQueue.mockRejectedValueOnce(apiError(401, 'UNAUTHENTICATED'))
    const { wrapper } = await mountPage(f)
    expect(wrapper.find('[data-test="rv-error"]').text()).toContain('登录已失效，请重新登录。')
    expect(wrapper.find('[data-test="rv-retry"]').exists()).toBe(false)
  })

  it('三栏空态文案各不相同，不是共用一句', async () => {
    const { wrapper } = await mountPage(fakes({ relations: [], duplicates: [], isolated: [] }))
    const texts = (['low_confidence_relation', 'suspected_duplicate', 'isolated_node'] as const).map((kind) =>
      wrapper.find(`[data-test="rv-empty-${kind}"]`).text().trim(),
    )
    expect(texts.every((text) => text.length > 0)).toBe(true)
    expect(new Set(texts).size).toBe(3)
  })

  it('COURSE_FORBIDDEN：回课程列表并带提示', async () => {
    const f = fakes()
    f.review.getQueue.mockRejectedValueOnce(apiError(403, 'COURSE_FORBIDDEN'))
    const { router } = await mountPage(f)
    expect(router.currentRoute.value.query.notice).toBe(NOTICE_COURSE_FORBIDDEN)
    expect(router.currentRoute.value.name).not.toBe(REVIEW_ROUTE)
  })

  it('学生账号访问审核页被守卫送回学生首页', async () => {
    const { router } = await mountPage(fakes(), '/courses/c1/review', 'student')
    expect(router.currentRoute.value.name).toBe('student-home')
    expect(router.currentRoute.value.query.notice).toBe(NOTICE_WRONG_ROLE)
  })

  it('课程页对课程教师显示审核入口', async () => {
    const { wrapper } = await mountPage(fakes(), '/courses/c1')
    expect(wrapper.find('[data-test="review-link"]').attributes('href')).toBe('/courses/c1/review')
  })
})

describe('审核队列页：单项处理与重复操作', () => {
  it('通过关系：移除该条，数量取响应 totals；重新进入页面数量一致', async () => {
    const f = fakes()
    const first = await mountPage(f)
    await click(first.wrapper, '[data-test="rv-relation"][data-id="r1"] [data-test="rv-approve"]')
    expect(f.review.resolve).toHaveBeenCalledWith('c1', { item: 'low_confidence_relation', rel_id: 'r1', action: 'approve' }, expect.anything())
    expect(rows(first.wrapper, 'rv-relation')).toEqual(['r2'])
    const before = headingCounts(first.wrapper)
    expect(before[0]).toBe('低置信度关系（1）')
    expect(first.wrapper.find('[data-test="rv-notice"]').text()).toContain('已通过')
    // 通过不影响其他栏，不重新读取
    expect(f.review.getQueue).toHaveBeenCalledTimes(1)
    first.wrapper.unmount()

    const again = await mountPage(f)
    expect(headingCounts(again.wrapper)).toEqual(before)
    expect(rows(again.wrapper, 'rv-relation')).toEqual(['r2'])
  })

  it('通过成功但响应缺少 totals：重读队列，数量与列表一致', async () => {
    const f = fakes({ relations: [rel('r1', 'k1', 'k2'), rel('r2', 'k2', 'k3')], duplicates: [], isolated: [] })
    f.review.resolve.mockImplementationOnce(async () => {
      f.server.relations = f.server.relations.filter((r) => r.id !== 'r1')
      return { item: 'low_confidence_relation', action: 'approve', changed: true } as never
    })
    const { wrapper } = await mountPage(f)
    await click(wrapper, '[data-test="rv-relation"][data-id="r1"] [data-test="rv-approve"]')
    expect(f.review.getQueue).toHaveBeenCalledTimes(2)
    expect(totalText(wrapper, 'low_confidence_relation')).toBe('低置信度关系（1）')
    expect(rows(wrapper, 'rv-relation')).toEqual(['r2'])
  })

  it('写请求在途时所有处理按钮不可用，连点只发一次', async () => {
    const f = fakes()
    const pending = deferred<Awaited<ReturnType<ReviewApi['resolve']>>>()
    f.review.resolve.mockImplementationOnce(() => pending.promise)
    const { wrapper } = await mountPage(f)
    const button = wrapper.find('[data-test="rv-relation"][data-id="r1"] [data-test="rv-approve"]')
    await button.trigger('click')
    await button.trigger('click')
    await wrapper.find('[data-test="rv-isolated"] [data-test="rv-keep"]').trigger('click')
    expect(f.review.resolve).toHaveBeenCalledTimes(1)
    expect(wrapper.findAll('button[data-test^="rv-"]').filter((b) => ['rv-approve', 'rv-reject', 'rv-keep', 'rv-merge'].includes(b.attributes('data-test')!)).every((b) => b.attributes('disabled') !== undefined)).toBe(true)
    expect(wrapper.find('[data-test="rv-relation"][data-id="r1"]').attributes('aria-busy')).toBe('true')
    pending.resolve({ item: 'low_confidence_relation', action: 'approve', changed: true, totals: { low_confidence_relations: 1, suspected_duplicates: 1, isolated_nodes: 2 } })
    await flushPromises()
    expect(rows(wrapper, 'rv-relation')).toEqual(['r2'])
    expect(wrapper.find('[data-test="rv-approve"]').attributes('disabled')).toBeUndefined()
  })

  it('同一动作已生效（changed = false）：移除该条、提示此前已处理，数量以响应 totals 为准', async () => {
    const f = fakes()
    // 这条在页面上还没被移除，但服务端记着「该动作已生效」：不写入、totals 也不再算它
    f.server.handled.add('rel:r1:approve')
    const { wrapper } = await mountPage(f)
    f.server.relations = f.server.relations.filter((r) => r.id !== 'r1')
    await click(wrapper, '[data-test="rv-relation"][data-id="r1"] [data-test="rv-approve"]')
    expect(rows(wrapper, 'rv-relation')).toEqual(['r2'])
    expect(wrapper.find('[data-test="rv-notice"]').attributes('data-tone')).toBe('info')
    expect(wrapper.find('[data-test="rv-notice"]').text()).toContain('此前已处理')
    expect(totalText(wrapper, 'low_confidence_relation')).toBe('低置信度关系（1）')
    expect(wrapper.find('[data-test="rv-notice"]').text()).not.toContain('已通过')
  })

  it('条目已不在队列（404）：移除、提示并重新读取队列，数量以服务端为准', async () => {
    const f = fakes()
    const { wrapper } = await mountPage(f)
    f.server.relations = f.server.relations.filter((r) => r.id !== 'r1') // 他人已处理
    await click(wrapper, '[data-test="rv-relation"][data-id="r1"] [data-test="rv-reject"]')
    expect(rows(wrapper, 'rv-relation')).toEqual(['r2'])
    expect(wrapper.find('[data-test="rv-notice"]').text()).toContain('已不在队列中')
    expect(f.review.getQueue).toHaveBeenCalledTimes(2)
    expect(totalText(wrapper, 'low_confidence_relation')).toBe('低置信度关系（1）')
  })

  it('拒绝关系会重新读取队列：新变成孤立的知识点出现在孤立栏', async () => {
    const f = fakes()
    const { wrapper } = await mountPage(f)
    f.review.resolve.mockImplementationOnce(async () => {
      f.server.relations = f.server.relations.filter((r) => r.id !== 'r2')
      f.server.isolated = [...f.server.isolated, ref_('k3', '括号匹配')]
      return {
        item: 'low_confidence_relation',
        action: 'reject',
        changed: true,
        totals: { low_confidence_relations: 1, suspected_duplicates: 1, isolated_nodes: 3 },
      }
    })
    await click(wrapper, '[data-test="rv-relation"][data-id="r2"] [data-test="rv-reject"]')
    expect(rows(wrapper, 'rv-isolated')).toEqual(['k5', 'k6', 'k3'])
    expect(totalText(wrapper, 'isolated_node')).toBe('孤立知识点（3）')
  })

  it('孤立知识点确认保留 / 拒绝', async () => {
    const f = fakes()
    const { wrapper } = await mountPage(f)
    await click(wrapper, '[data-test="rv-isolated"][data-id="k6"] [data-test="rv-keep"]')
    expect(f.review.resolve).toHaveBeenLastCalledWith('c1', { item: 'isolated_node', kp_id: 'k6', action: 'approve' }, expect.anything())
    await click(wrapper, '[data-test="rv-isolated"][data-id="k5"] [data-test="rv-reject-node"]')
    expect(f.review.resolve).toHaveBeenLastCalledWith('c1', { item: 'isolated_node', kp_id: 'k5', action: 'reject' }, expect.anything())
    expect(wrapper.find('[data-test="rv-empty-isolated_node"]').exists()).toBe(true)
  })

  it('网络中断无法确认结果：提示并重新读取队列，以服务端为准', async () => {
    const f = fakes()
    const { wrapper } = await mountPage(f)
    f.review.resolve.mockImplementationOnce(async () => {
      f.server.relations = f.server.relations.filter((r) => r.id !== 'r1') // 服务端其实已处理
      throw new NetworkError('reset')
    })
    await click(wrapper, '[data-test="rv-relation"][data-id="r1"] [data-test="rv-approve"]')
    expect(wrapper.find('[data-test="rv-notice"]').attributes('data-tone')).toBe('error')
    expect(wrapper.find('[data-test="rv-notice"]').text()).toContain('无法确认')
    expect(rows(wrapper, 'rv-relation')).toEqual(['r2'])
    expect(totalText(wrapper, 'low_confidence_relation')).toBe('低置信度关系（1）')
  })
})

describe('审核队列页：疑似重复与合并', () => {
  it('不是重复：提交 reject，这一对移出队列', async () => {
    const f = fakes()
    const { wrapper } = await mountPage(f)
    await click(wrapper, '[data-test="rv-not-duplicate"]')
    expect(f.review.resolve).toHaveBeenCalledWith('c1', { item: 'suspected_duplicate', kp_ids: ['k4', 'k5'], action: 'reject' }, expect.anything())
    expect(wrapper.find('[data-test="rv-empty-suspected_duplicate"]').exists()).toBe(true)
  })

  it('合并需先选主知识点再确认；合并后重新读取，引用被合并节点的条目随之消失', async () => {
    const f = fakes()
    const { wrapper } = await mountPage(f)
    await click(wrapper, '[data-test="rv-merge"]')
    expect(f.review.resolve).not.toHaveBeenCalled()
    expect(wrapper.find('[data-test="rv-merge-summary"]').text()).toContain('「堆栈」将并入「栈」')
    // 改选「堆栈」为主节点
    await wrapper.findAll('[data-test="rv-primary"]')[1]!.setValue(true)
    await flushPromises()
    expect(wrapper.find('[data-test="rv-merge-summary"]').text()).toContain('「栈」将并入「堆栈」')
    await click(wrapper, '[data-test="rv-merge-confirm"]')
    expect(f.review.resolve).toHaveBeenCalledWith(
      'c1',
      { item: 'suspected_duplicate', kp_ids: ['k4', 'k5'], action: 'merge', primary_id: 'k5' },
      expect.anything(),
    )
    expect(f.review.getQueue).toHaveBeenCalledTimes(2)
    expect(wrapper.find('[data-test="rv-merge-panel"]').exists()).toBe(false)
    expect(wrapper.find('[data-test="rv-notice"]').text()).toContain('已合并')
    expect(wrapper.find('[data-test="rv-empty-suspected_duplicate"]').exists()).toBe(true)
  })

  it('取消合并不发请求', async () => {
    const f = fakes()
    const { wrapper } = await mountPage(f)
    await click(wrapper, '[data-test="rv-merge"]')
    await click(wrapper, '[data-test="rv-merge-cancel"]')
    expect(wrapper.find('[data-test="rv-merge-panel"]').exists()).toBe(false)
    expect(f.review.resolve).not.toHaveBeenCalled()
  })

  it('合并冲突（成环）：显示名称环路，条目保留，不重新读取', async () => {
    const f = fakes()
    f.review.resolve.mockRejectedValueOnce(apiError(409, 'CYCLE_DETECTED', { cycle: ['k1', 'k2', 'k3', 'k1'] }))
    const { wrapper } = await mountPage(f)
    await click(wrapper, '[data-test="rv-merge"]')
    await click(wrapper, '[data-test="rv-merge-confirm"]')
    const error = wrapper.find('[data-test="rv-duplicate"] [data-test="rv-item-error"]')
    expect(error.text()).toContain('会成环')
    expect(wrapper.find('[data-test="rv-cycle"]').text().replace(/\s+/g, '')).toBe('环路：线性表→栈→括号匹配→线性表')
    expect(error.text()).not.toContain('服务端原文')
    expect(rows(wrapper, 'rv-duplicate')).toEqual([duplicateKey(f.server.duplicates[0]!)])
    expect(f.review.getQueue).toHaveBeenCalledTimes(1)
    // 可以改为标记不是重复
    await click(wrapper, '[data-test="rv-merge-cancel"]')
    await click(wrapper, '[data-test="rv-not-duplicate"]')
    expect(wrapper.find('[data-test="rv-empty-suspected_duplicate"]').exists()).toBe(true)
  })

  it('合并冲突（课程忙 / 修订冲突）：给出固定文案', async () => {
    const f = fakes()
    f.review.resolve.mockRejectedValueOnce(apiError(409, 'COURSE_BUSY'))
    const { wrapper } = await mountPage(f)
    await click(wrapper, '[data-test="rv-merge"]')
    await click(wrapper, '[data-test="rv-merge-confirm"]')
    expect(wrapper.find('[data-test="rv-item-error"]').text()).toContain('稍后重试')
    expect(rows(wrapper, 'rv-duplicate')).toHaveLength(1)
    expect(f.review.getQueue).toHaveBeenCalledTimes(1)

    f.review.resolve.mockRejectedValueOnce(apiError(409, 'REVISION_CONFLICT', { kp_id: 'k4' }))
    await click(wrapper, '[data-test="rv-merge-confirm"]')
    expect(wrapper.find('[data-test="rv-item-error"]').text()).toContain('刚被修改')
    expect(f.review.getQueue).toHaveBeenCalledTimes(2)
  })

  it('成环冲突后可改选另一主知识点再合并，旧错误随之清除', async () => {
    const f = fakes()
    f.review.resolve.mockRejectedValueOnce(apiError(409, 'CYCLE_DETECTED', { cycle: ['k1', 'k9', 'k1'] }))
    const { wrapper } = await mountPage(f)
    await click(wrapper, '[data-test="rv-merge"]')
    await click(wrapper, '[data-test="rv-merge-confirm"]')
    expect(wrapper.find('[data-test="rv-merge-panel"]').exists()).toBe(true)
    await wrapper.findAll('[data-test="rv-primary"]')[1]!.setValue(true)
    await flushPromises()
    await click(wrapper, '[data-test="rv-merge-confirm"]')
    expect(f.review.resolve).toHaveBeenLastCalledWith(
      'c1',
      { item: 'suspected_duplicate', kp_ids: ['k4', 'k5'], action: 'merge', primary_id: 'k5' },
      expect.anything(),
    )
    expect(wrapper.find('[data-test="rv-item-error"]').exists()).toBe(false)
  })
})

describe('审核队列页：分页', () => {
  const many = Array.from({ length: 60 }, (_, i) => ref_(`n${String(i).padStart(2, '0')}`, `孤立 ${i}`))

  it('加载更多追加下一页，数量始终是完整条数', async () => {
    const f = fakes({ isolated: [...many] })
    const { wrapper } = await mountPage(f)
    expect(rows(wrapper, 'rv-isolated')).toHaveLength(50)
    expect(totalText(wrapper, 'isolated_node')).toBe('孤立知识点（60）')
    await click(wrapper, '[data-test="rv-more-isolated_node"]')
    expect(f.review.getQueue).toHaveBeenLastCalledWith('c1', { kind: 'isolated_node', cursor: 'isolated_node:50', limit: 50 }, expect.anything())
    expect(rows(wrapper, 'rv-isolated')).toHaveLength(60)
    expect(wrapper.find('[data-test="rv-more-isolated_node"]').exists()).toBe(false)
  })

  it('加载更多后的数量取该页响应的 totals（服务端期间变多则跟着变）', async () => {
    const f = fakes({ isolated: [...many] })
    const base = f.review.getQueue.getMockImplementation()!
    f.review.getQueue.mockImplementation(async (cid, query) => {
      const page = await base(cid, query)
      if (query?.kind === 'isolated_node') page.totals = { ...page.totals, isolated_nodes: 70 }
      return page
    })
    const { wrapper } = await mountPage(f)
    expect(totalText(wrapper, 'isolated_node')).toBe('孤立知识点（60）')
    await click(wrapper, '[data-test="rv-more-isolated_node"]')
    expect(totalText(wrapper, 'isolated_node')).toBe('孤立知识点（70）')
    expect(rows(wrapper, 'rv-isolated')).toHaveLength(60)
  })

  it('处理后重新读取时条数不少于已加载的', async () => {
    const f = fakes({ isolated: [...many] })
    const { wrapper } = await mountPage(f)
    await click(wrapper, '[data-test="rv-more-isolated_node"]')
    await click(wrapper, '[data-test="rv-isolated"][data-id="n00"] [data-test="rv-reject-node"]')
    expect(f.review.getQueue).toHaveBeenLastCalledWith('c1', { limit: 59 }, expect.anything())
    expect(rows(wrapper, 'rv-isolated')).toHaveLength(59)
    expect(totalText(wrapper, 'isolated_node')).toBe('孤立知识点（59）')
  })

  it('游标失效（422）时从第一页重新读取', async () => {
    const f = fakes({ isolated: [...many] })
    const { wrapper } = await mountPage(f)
    f.review.getQueue.mockRejectedValueOnce(apiError(422, 'VALIDATION_ERROR'))
    await click(wrapper, '[data-test="rv-more-isolated_node"]')
    expect(f.review.getQueue).toHaveBeenLastCalledWith('c1', { limit: 50 }, expect.anything())
    expect(rows(wrapper, 'rv-isolated')).toHaveLength(50)
  })

  it('两栏都有下一页时各用各的游标，互不串栏', async () => {
    const f = fakes({ relations: Array.from({ length: 60 }, (_, i) => rel(`r${String(i).padStart(2, '0')}`, 'k1', 'k2')), isolated: [...many] })
    const { wrapper } = await mountPage(f)
    await click(wrapper, '[data-test="rv-more-isolated_node"]')
    expect(f.review.getQueue).toHaveBeenLastCalledWith('c1', { kind: 'isolated_node', cursor: 'isolated_node:50', limit: 50 }, expect.anything())
    await click(wrapper, '[data-test="rv-more-low_confidence_relation"]')
    expect(f.review.getQueue).toHaveBeenLastCalledWith('c1', { kind: 'low_confidence_relation', cursor: 'low_confidence_relation:50', limit: 50 }, expect.anything())
    expect(rows(wrapper, 'rv-isolated')).toHaveLength(60)
    expect(rows(wrapper, 'rv-relation')).toHaveLength(60)
  })

  it('加载更多失败给出提示，列表不变', async () => {
    const f = fakes({ isolated: [...many] })
    const { wrapper } = await mountPage(f)
    f.review.getQueue.mockRejectedValueOnce(new NetworkError('offline'))
    await click(wrapper, '[data-test="rv-more-isolated_node"]')
    expect(wrapper.find('[data-test="rv-more-error-isolated_node"]').exists()).toBe(true)
    expect(rows(wrapper, 'rv-isolated')).toHaveLength(50)
  })
})

describe('审核队列页：迟到响应', () => {
  it('换课后旧课程的队列响应被丢弃', async () => {
    const f = fakes()
    const slow = deferred<ReviewQueue>()
    f.review.getQueue.mockImplementationOnce(() => slow.promise)
    const { wrapper, router } = await mountPage(f)
    await router.push('/courses/c2/review')
    await flushPromises()
    slow.resolve({
      low_confidence_relations: [rel('old', 'x', 'y')],
      suspected_duplicates: [],
      isolated_nodes: [],
      totals: { low_confidence_relations: 99, suspected_duplicates: 0, isolated_nodes: 0 },
      next_cursors: { low_confidence_relations: null, suspected_duplicates: null, isolated_nodes: null },
    })
    await flushPromises()
    expect(rows(wrapper, 'rv-relation')).toEqual(['r1', 'r2'])
    expect(totalText(wrapper, 'low_confidence_relation')).toBe('低置信度关系（2）')
  })
})
