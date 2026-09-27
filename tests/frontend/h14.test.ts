import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { createPinia, setActivePinia, type Pinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { defineComponent, effectScope, h, nextTick, ref } from 'vue'
import { createMemoryHistory, RouterView } from 'vue-router'
import type { components } from '../../src/contracts/v1/generated/typescript/openapi'
import { COURSES_API_KEY, type CoursesApi } from '../../src/frontend/src/api/courses'
import { createDraftGraphApi, DRAFT_GRAPH_API_KEY, type DraftGraphApi } from '../../src/frontend/src/api/graph'
import { ApiError, createHttpClient, NetworkError, type FetchLike } from '../../src/frontend/src/api/http'
import { KNOWLEDGE_DETAIL_API_KEY, type KnowledgeDetailApi } from '../../src/frontend/src/api/knowledgeDetail'
import { NODE_EDIT_API_KEY, type NodeEditApi } from '../../src/frontend/src/api/nodeEdit'
import { RELATIONS_API_KEY, type RelationsApi } from '../../src/frontend/src/api/relations'
import GraphCanvas from '../../src/frontend/src/components/GraphCanvas.vue'
import { isDraftOf, useSelectionGuard } from '../../src/frontend/src/composables/useTeacherGraph'
import { GRAPH_FACTORY_KEY, type CanvasGraph, type CanvasGraphFactory, type GraphCanvasData } from '../../src/frontend/src/graph/lifecycle'
import { createAppRouter, NOTICE_WRONG_ROLE, TEACHER_GRAPH_ROUTE } from '../../src/frontend/src/router/index.ts'
import { useSessionStore } from '../../src/frontend/src/stores/session'
import CoursesView from '../../src/frontend/src/views/CoursesView.vue'
import TeacherGraphView from '../../src/frontend/src/views/TeacherGraphView.vue'

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
    status: 'draft',
    my_role: 'teacher',
    published_version: null,
    created_at: '2026-09-01T00:00:00Z',
    ...overrides,
  } as Course
}

function kp(id: string, overrides: Partial<KnowledgePoint> = {}, cid = 'c1'): KnowledgePoint {
  return {
    id,
    course_id: cid,
    name: `知识点 ${id}`,
    aliases: [],
    type: 'concept',
    definition: `${id} 的定义`,
    importance: 0.5,
    level: 1,
    confidence: 0.9,
    status: 'draft',
    source: 'ai',
    locked: false,
    revision: 1,
    chapter_id: 'ch1',
    ...overrides,
  } as KnowledgePoint
}

function rel(id: string, from: string, to: string, cid = 'c1'): Relation {
  return {
    id,
    course_id: cid,
    type: 'PREREQUISITE',
    from_id: from,
    to_id: to,
    confidence: 0.9,
    status: 'draft',
    source: 'ai',
    source_refs: [],
  } as unknown as Relation
}

function draft(cid: string, nodes: KnowledgePoint[], edges: Relation[] = [], version: number | null = null): GraphExchange {
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

function detailOf(point: KnowledgePoint): KnowledgePointDetail {
  return {
    ...point,
    source_refs: [{ chunk_id: `${point.id}-chunk`, document_id: 'doc1', page: 2 }],
    prerequisites: [],
    successors: [],
    related: [],
  } as KnowledgePointDetail
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

function fakeCanvasFactory(): CanvasGraphFactory {
  return (() =>
    ({
      render: () => Promise.resolve(),
      setData: () => {},
      setSize: () => {},
      fitView: () => Promise.resolve(),
      on() {
        return this
      },
      destroy: () => {},
    }) as unknown as CanvasGraph) as CanvasGraphFactory
}

/** 服务端草稿：假 API 的读写都作用于它，便于核对「成功才改画布」 */
function fakes(opts: { course?: CoursesApi['get']; draft?: DraftGraphApi['getDraft']; nodes?: KnowledgePoint[]; edges?: Relation[] } = {}) {
  const server = { nodes: opts.nodes ?? [kp('k1'), kp('k2'), kp('k3')], edges: opts.edges ?? [rel('r1', 'k1', 'k2')] }
  const find = (kid: string) => {
    const found = server.nodes.find((n) => n.id === kid)
    if (!found) throw apiError(404, 'NOT_FOUND')
    return found
  }
  return {
    server,
    courses: { get: vi.fn<CoursesApi['get']>(opts.course ?? (async (cid) => course(cid))) },
    draft: {
      getDraft: vi.fn<DraftGraphApi['getDraft']>(
        opts.draft ?? (async (cid) => draft(cid, server.nodes.map((n) => ({ ...n })), server.edges.map((e) => ({ ...e })))),
      ),
    },
    detail: { get: vi.fn<KnowledgeDetailApi['get']>(async (_cid, kid) => detailOf(find(kid))) },
    nodeEdit: {
      get: vi.fn<NodeEditApi['get']>(async (_cid, kid) => detailOf(find(kid))),
      update: vi.fn<NodeEditApi['update']>(async (_cid, kid, body) => {
        const old = find(kid)
        const { expected_revision: _rev, ...changes } = body
        const next = { ...old, ...changes, revision: old.revision + 1, locked: true } as KnowledgePoint
        server.nodes = server.nodes.map((n) => (n.id === kid ? next : n))
        return next
      }),
      unlock: vi.fn<NodeEditApi['unlock']>(),
      remove: vi.fn<NodeEditApi['remove']>(async (_cid, kid) => {
        find(kid)
        server.nodes = server.nodes.filter((n) => n.id !== kid)
        server.edges = server.edges.filter((e) => e.from_id !== kid && e.to_id !== kid)
      }),
    },
    relations: {
      create: vi.fn<RelationsApi['create']>(async (cid, body) => {
        const created = { ...rel(`r${server.edges.length + 10}`, body.from_id, body.to_id, cid), type: body.type, source: 'manual' } as Relation
        server.edges = [...server.edges, created]
        return created
      }),
      update: vi.fn<RelationsApi['update']>(),
      remove: vi.fn<RelationsApi['remove']>(),
    },
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

async function mountPage(f: Fakes, path = '/courses/c1/graph/edit', accountRole: 'student' | 'teacher' = 'teacher') {
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
    teacherGraphComponent: TeacherGraphView,
  })
  await router.push(path)
  await router.isReady()
  const wrapper = mount(defineComponent({ render: () => h(RouterView) }), {
    attachTo: document.body,
    global: {
      plugins: [pinia, router],
      provide: {
        [COURSES_API_KEY as symbol]: { list: async () => [course('c1')], create: vi.fn(), get: f.courses.get },
        [DRAFT_GRAPH_API_KEY as symbol]: f.draft,
        [KNOWLEDGE_DETAIL_API_KEY as symbol]: f.detail,
        [NODE_EDIT_API_KEY as symbol]: f.nodeEdit,
        [RELATIONS_API_KEY as symbol]: f.relations,
        [GRAPH_FACTORY_KEY as symbol]: fakeCanvasFactory(),
      },
    },
  })
  await flushPromises()
  return { wrapper, router }
}

function canvasGraph(wrapper: VueWrapper): GraphCanvasData | null {
  return wrapper.findComponent(GraphCanvas).props('graph') as GraphCanvasData | null
}

function canvasNodeNames(wrapper: VueWrapper): string[] {
  return (canvasGraph(wrapper)?.nodes ?? []).map((n) => n.data.name).sort()
}

function canvasEdgeIds(wrapper: VueWrapper): string[] {
  return (canvasGraph(wrapper)?.edges ?? []).map((e) => e.data.relationId).sort()
}

async function clickNode(wrapper: VueWrapper, kid: string): Promise<void> {
  wrapper.findComponent(GraphCanvas).vm.$emit('nodeClick', kid)
  await flushPromises()
}

async function openTab(wrapper: VueWrapper, tab: 'detail' | 'edit' | 'relations'): Promise<void> {
  await wrapper.find(`[data-test="tg-tab-${tab}"]`).trigger('click')
  await flushPromises()
}

async function editName(wrapper: VueWrapper, name: string): Promise<void> {
  await wrapper.find('[data-test="ne-name"]').setValue(name)
  await flushPromises()
}

// ---------------------------------------------------------------- API 层

describe('草稿图谱 API', () => {
  it('GET /graph 不带 version 查询参数（教师读草稿）', async () => {
    const urls: string[] = []
    const fetch: FetchLike = async (url) => {
      urls.push(url)
      return new Response(JSON.stringify(draft('c/1', [])), { status: 200, headers: { 'Content-Type': 'application/json' } })
    }
    const api = createDraftGraphApi(createHttpClient({ fetch, getAccessToken: () => 'tok' }))
    await api.getDraft('c/1')
    expect(urls).toEqual(['/api/v1/courses/c%2F1/graph'])
  })
})

describe('isDraftOf', () => {
  it('同课程且 graph_version 为 null 才是草稿', () => {
    expect(isDraftOf(draft('c1', []), 'c1')).toBe(true)
    expect(isDraftOf(draft('c1', [], [], 2), 'c1')).toBe(false)
    expect(isDraftOf(draft('c2', []), 'c1')).toBe(false)
    expect(isDraftOf(null, 'c1')).toBe(false)
    expect(isDraftOf({ ...draft('c1', []), nodes: 'x' } as unknown as GraphExchange, 'c1')).toBe(false)
  })
})

describe('useSelectionGuard', () => {
  function setup(dirty: boolean) {
    const scope = effectScope()
    const selected = ref<string | null>('a')
    const state = { dirty }
    const guard = scope.run(() =>
      useSelectionGuard({ selected, apply: (k) => (selected.value = k), isDirty: () => state.dirty }),
    )!
    return { scope, selected, guard, state }
  }

  it('没有未保存修改时直接切换', () => {
    const { selected, guard } = setup(false)
    guard.request('b')
    expect(selected.value).toBe('b')
    expect(guard.pending.value).toBeNull()
  })

  it('有未保存修改时挂起，确认后切换、取消则不变', async () => {
    const { selected, guard } = setup(true)
    guard.request('b')
    expect(selected.value).toBe('a')
    expect(guard.pending.value).toEqual({ kpId: 'b' })
    guard.cancel()
    expect(selected.value).toBe('a')
    guard.request(null)
    expect(guard.pending.value).toEqual({ kpId: null })
    guard.confirm()
    expect(selected.value).toBeNull()
  })

  it('选中被外部改变时撤销待确认', async () => {
    const { selected, guard } = setup(true)
    guard.request('b')
    selected.value = 'c'
    await nextTick()
    expect(guard.pending.value).toBeNull()
  })

  it('重复点当前节点不弹确认', () => {
    const { guard } = setup(true)
    guard.request('a')
    expect(guard.pending.value).toBeNull()
  })
})

// ---------------------------------------------------------------- 路由与进入权限

describe('路由与入口', () => {
  it('学生账号进不了编辑页，按账号类型送回学生首页', async () => {
    const f = fakes()
    const { router } = await mountPage(f, '/courses/c1/graph/edit', 'student')
    expect(router.currentRoute.value.name).toBe('student-home')
    expect(router.currentRoute.value.query.notice).toBe(NOTICE_WRONG_ROLE)
    expect(f.draft.getDraft).not.toHaveBeenCalled()
  })

  it('未注入页面时不注册路由', () => {
    const router = createAppRouter({ history: createMemoryHistory(), getAccountRole: () => 'teacher' })
    expect(router.hasRoute(TEACHER_GRAPH_ROUTE)).toBe(false)
  })

  it('课程页只给课程内教师显示编辑入口', async () => {
    const f = fakes()
    const { wrapper } = await mountPage(f, '/courses/c1')
    expect(wrapper.find('[data-test="teacher-graph-link"]').attributes('href')).toBe('/courses/c1/graph/edit')

    setActivePinia((pinia = createPinia()))
    const g = fakes({ course: async (cid) => course(cid, { my_role: 'student' }) })
    const other = await mountPage(g, '/courses/c1')
    expect(other.wrapper.find('[data-test="teacher-graph-link"]').exists()).toBe(false)
  })
})

// ---------------------------------------------------------------- 只取草稿、状态

describe('加载草稿与状态', () => {
  it('课程教师进入：只读草稿，画布显示全部知识点与关系', async () => {
    const f = fakes()
    const { wrapper } = await mountPage(f)
    expect(f.draft.getDraft).toHaveBeenCalledTimes(1)
    expect(f.draft.getDraft.mock.calls[0][0]).toBe('c1')
    expect(wrapper.find('[data-test="tg-draft"]').exists()).toBe(true)
    expect(canvasNodeNames(wrapper)).toEqual(['知识点 k1', '知识点 k2', '知识点 k3'])
    expect(canvasEdgeIds(wrapper)).toEqual(['r1'])
  })

  it('课程内角色是学生：不读草稿，提示仅教师可编辑', async () => {
    const f = fakes({ course: async (cid) => course(cid, { my_role: 'student' }) })
    const { wrapper } = await mountPage(f)
    expect(wrapper.find('[data-test="tg-not-teacher"]').exists()).toBe(true)
    expect(f.draft.getDraft).not.toHaveBeenCalled()
    expect(wrapper.findComponent(GraphCanvas).exists()).toBe(false)
  })

  it('响应带发布版本号（不是草稿）按数据异常丢弃', async () => {
    const f = fakes({ draft: async (cid) => draft(cid, [kp('k1')], [], 2) })
    const { wrapper } = await mountPage(f)
    expect(wrapper.find('[data-test="tg-error"]').exists()).toBe(true)
    expect(wrapper.findComponent(GraphCanvas).exists()).toBe(false)
  })

  it('响应的课程不符按数据异常丢弃', async () => {
    const f = fakes({ draft: async () => draft('c9', [kp('k1', {}, 'c9')]) })
    const { wrapper } = await mountPage(f)
    expect(wrapper.find('[data-test="tg-error"]').exists()).toBe(true)
  })

  it('加载中显示加载态', async () => {
    const pending = deferred<GraphExchange>()
    const f = fakes({ draft: () => pending.promise })
    const { wrapper } = await mountPage(f)
    expect(wrapper.find('[data-test="tg-loading"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="teacher-graph-page"]').attributes('aria-busy')).toBe('true')
    pending.resolve(draft('c1', [kp('k1')]))
    await flushPromises()
    expect(wrapper.find('[data-test="tg-loading"]').exists()).toBe(false)
  })

  it('空草稿显示空态', async () => {
    const f = fakes({ nodes: [], edges: [] })
    const { wrapper } = await mountPage(f)
    expect(wrapper.find('[data-test="tg-empty"]').exists()).toBe(true)
    expect(wrapper.findComponent(GraphCanvas).exists()).toBe(false)
  })

  it('网络错误可重试', async () => {
    let fail = true
    const f = fakes()
    const ok = f.draft.getDraft.getMockImplementation()!
    f.draft.getDraft.mockImplementation(async (...args) => {
      if (fail) throw new NetworkError(new TypeError('offline'))
      return ok(...args)
    })
    const { wrapper } = await mountPage(f)
    expect(wrapper.find('[data-test="tg-error"]').text()).toContain('无法连接服务器')
    fail = false
    await wrapper.find('[data-test="tg-retry"]').trigger('click')
    await flushPromises()
    expect(canvasNodeNames(wrapper)).toHaveLength(3)
  })

  it('读图时角色已被移除（ROLE_FORBIDDEN）按非教师处理', async () => {
    const f = fakes({ draft: async () => Promise.reject(apiError(403, 'ROLE_FORBIDDEN')) })
    const { wrapper } = await mountPage(f)
    expect(wrapper.find('[data-test="tg-not-teacher"]').exists()).toBe(true)
  })

  it('COURSE_FORBIDDEN 回首页并带提示', async () => {
    const f = fakes({ course: async () => Promise.reject(apiError(403, 'COURSE_FORBIDDEN')) })
    const { router } = await mountPage(f)
    await flushPromises()
    expect(router.currentRoute.value.name).toBe('teacher-home')
    expect(router.currentRoute.value.query.notice).toBe('course-forbidden')
  })

  it('换课后旧课程的晚到草稿不写入', async () => {
    const first = deferred<GraphExchange>()
    const f = fakes()
    const ok = f.draft.getDraft.getMockImplementation()!
    f.draft.getDraft.mockImplementation((cid, control) => (cid === 'c1' ? first.promise : ok(cid, control)))
    f.server.nodes = [kp('k1', {}, 'c2')]
    const { wrapper, router } = await mountPage(f)
    await router.push('/courses/c2/graph/edit')
    await flushPromises()
    first.resolve(draft('c1', [kp('old1'), kp('old2')]))
    await flushPromises()
    expect(canvasNodeNames(wrapper)).toEqual(['知识点 k1'])
  })
})

// ---------------------------------------------------------------- 选中联动

describe('画布选中联动详情与编辑面板', () => {
  it('点击节点显示 H06 详情，切到编辑页签是 H07 面板', async () => {
    const f = fakes()
    const { wrapper } = await mountPage(f)
    expect(wrapper.find('[data-test="tg-detail-empty"]').exists()).toBe(true)
    await clickNode(wrapper, 'k2')
    expect(f.detail.get).toHaveBeenCalledWith('c1', 'k2', expect.anything())
    await openTab(wrapper, 'edit')
    expect(wrapper.find('[data-test="ne-title"]').text()).toContain('知识点 k2')
    await clickNode(wrapper, 'k3')
    expect(wrapper.find('[data-test="ne-title"]').text()).toContain('知识点 k3')
  })

  it('保存成功后画布同步新名称', async () => {
    const f = fakes()
    const { wrapper } = await mountPage(f)
    await clickNode(wrapper, 'k1')
    await openTab(wrapper, 'edit')
    await editName(wrapper, '栈')
    await wrapper.find('[data-test="ne-form"]').trigger('submit')
    await flushPromises()
    expect(f.nodeEdit.update).toHaveBeenCalledTimes(1)
    expect(canvasNodeNames(wrapper)).toEqual(['栈', '知识点 k2', '知识点 k3'])
  })

  it('保存失败画布不变，修改保留', async () => {
    const f = fakes()
    f.nodeEdit.update.mockRejectedValue(apiError(500, 'INTERNAL_ERROR'))
    const { wrapper } = await mountPage(f)
    await clickNode(wrapper, 'k1')
    await openTab(wrapper, 'edit')
    await editName(wrapper, '栈')
    await wrapper.find('[data-test="ne-form"]').trigger('submit')
    await flushPromises()
    expect(canvasNodeNames(wrapper)).toEqual(['知识点 k1', '知识点 k2', '知识点 k3'])
    expect(wrapper.find('[data-test="ne-dirty"]').exists()).toBe(true)
  })

  it('删除成功后节点与相连关系从画布移除，选中清空', async () => {
    const f = fakes()
    const { wrapper } = await mountPage(f)
    await clickNode(wrapper, 'k1')
    await openTab(wrapper, 'edit')
    await wrapper.find('[data-test="ne-delete"]').trigger('click')
    await flushPromises()
    await wrapper.find('[data-test="ne-delete-yes"]').trigger('click')
    await flushPromises()
    expect(f.nodeEdit.remove).toHaveBeenCalledTimes(1)
    expect(canvasNodeNames(wrapper)).toEqual(['知识点 k2', '知识点 k3'])
    expect(canvasEdgeIds(wrapper)).toEqual([])
    await openTab(wrapper, 'detail')
    expect(wrapper.find('[data-test="tg-detail-empty"]').exists()).toBe(true)
  })

  it('删除失败画布不变', async () => {
    const f = fakes()
    f.nodeEdit.remove.mockRejectedValue(apiError(500, 'INTERNAL_ERROR'))
    const { wrapper } = await mountPage(f)
    await clickNode(wrapper, 'k1')
    await openTab(wrapper, 'edit')
    await wrapper.find('[data-test="ne-delete"]').trigger('click')
    await flushPromises()
    await wrapper.find('[data-test="ne-delete-yes"]').trigger('click')
    await flushPromises()
    expect(canvasNodeNames(wrapper)).toEqual(['知识点 k1', '知识点 k2', '知识点 k3'])
    expect(canvasEdgeIds(wrapper)).toEqual(['r1'])
  })
})

// ---------------------------------------------------------------- 未保存确认

describe('有未保存修改时切换节点先确认', () => {
  async function dirtyOn(kid: string) {
    const f = fakes()
    const { wrapper, router } = await mountPage(f)
    await clickNode(wrapper, kid)
    await openTab(wrapper, 'edit')
    await editName(wrapper, '未保存的名字')
    return { f, wrapper, router }
  }

  it('点别的节点：先弹确认，不切换', async () => {
    const { f, wrapper } = await dirtyOn('k1')
    await clickNode(wrapper, 'k2')
    expect(wrapper.find('[data-test="tg-discard-confirm"]').text()).toContain('知识点 k2')
    expect(f.nodeEdit.get).not.toHaveBeenCalledWith('c1', 'k2', expect.anything())
    expect((wrapper.find('[data-test="ne-name"]').element as HTMLInputElement).value).toBe('未保存的名字')
  })

  it('继续编辑：保留当前节点与修改', async () => {
    const { wrapper } = await dirtyOn('k1')
    await clickNode(wrapper, 'k2')
    await wrapper.find('[data-test="tg-discard-no"]').trigger('click')
    await flushPromises()
    expect(wrapper.find('[data-test="tg-discard-confirm"]').exists()).toBe(false)
    expect(wrapper.find('[data-test="ne-title"]').text()).toContain('知识点 k1')
    expect((wrapper.find('[data-test="ne-name"]').element as HTMLInputElement).value).toBe('未保存的名字')
  })

  it('放弃修改并切换：载入新节点', async () => {
    const { wrapper } = await dirtyOn('k1')
    await clickNode(wrapper, 'k2')
    await wrapper.find('[data-test="tg-discard-yes"]').trigger('click')
    await flushPromises()
    expect(wrapper.find('[data-test="ne-title"]').text()).toContain('知识点 k2')
    expect(wrapper.find('[data-test="ne-dirty"]').exists()).toBe(false)
  })

  it('关闭面板同样先确认', async () => {
    const { wrapper } = await dirtyOn('k1')
    await wrapper.find('[data-test="ne-close"]').trigger('click')
    await flushPromises()
    expect(wrapper.find('[data-test="tg-discard-confirm"]').text()).toContain('关闭面板')
  })

  it('切到其他页签不丢修改', async () => {
    const { wrapper } = await dirtyOn('k1')
    await openTab(wrapper, 'detail')
    await openTab(wrapper, 'edit')
    expect((wrapper.find('[data-test="ne-name"]').element as HTMLInputElement).value).toBe('未保存的名字')
  })

  it('没有修改时直接切换，不弹确认', async () => {
    const f = fakes()
    const { wrapper } = await mountPage(f)
    await clickNode(wrapper, 'k1')
    await openTab(wrapper, 'edit')
    await clickNode(wrapper, 'k2')
    expect(wrapper.find('[data-test="tg-discard-confirm"]').exists()).toBe(false)
    expect(wrapper.find('[data-test="ne-title"]').text()).toContain('知识点 k2')
  })

  it('有修改时离开页面先确认，取消则留下', async () => {
    const { wrapper, router } = await dirtyOn('k1')
    const confirm = vi.spyOn(window, 'confirm').mockReturnValue(false)
    await router.push('/courses/c1')
    await flushPromises()
    expect(confirm).toHaveBeenCalledTimes(1)
    expect(router.currentRoute.value.name).toBe(TEACHER_GRAPH_ROUTE)
    expect((wrapper.find('[data-test="ne-name"]').element as HTMLInputElement).value).toBe('未保存的名字')
  })
})

// ---------------------------------------------------------------- H08 连边

describe('连边编辑', () => {
  async function pickAndCreate(wrapper: VueWrapper, from: string, to: string): Promise<void> {
    await openTab(wrapper, 'relations')
    await clickNode(wrapper, from)
    await clickNode(wrapper, to)
    await wrapper.find('.relation-editor__form').trigger('submit')
    await flushPromises()
  }

  it('关系页签下点选起点、终点并新建，成功后画布出现新边', async () => {
    const f = fakes()
    const { wrapper } = await mountPage(f)
    await pickAndCreate(wrapper, 'k2', 'k3')
    expect(f.relations.create).toHaveBeenCalledWith('c1', expect.objectContaining({ from_id: 'k2', to_id: 'k3' }), expect.anything())
    expect(canvasEdgeIds(wrapper)).toHaveLength(2)
    // 关系页签下点击不改变知识点选中
    await openTab(wrapper, 'detail')
    expect(wrapper.find('[data-test="tg-detail-empty"]').exists()).toBe(true)
  })

  it('成环被拒绝：画布不新增边，并提示冲突', async () => {
    const f = fakes()
    f.relations.create.mockRejectedValue(apiError(409, 'CYCLE_DETECTED', { cycle: ['k2', 'k1', 'k2'] }))
    const { wrapper } = await mountPage(f)
    await pickAndCreate(wrapper, 'k2', 'k1')
    expect(canvasEdgeIds(wrapper)).toEqual(['r1'])
    expect(wrapper.find('[data-testid="cycle-conflict"]').exists()).toBe(true)
  })

  it('修订冲突时重新拉草稿；刷新失败保留当前画布并提示', async () => {
    const f = fakes()
    f.relations.create.mockRejectedValue(apiError(409, 'REVISION_CONFLICT'))
    const { wrapper } = await mountPage(f)
    const ok = f.draft.getDraft.getMockImplementation()!
    f.draft.getDraft.mockImplementationOnce(async () => Promise.reject(new NetworkError(new TypeError('offline'))))
    await pickAndCreate(wrapper, 'k2', 'k3')
    expect(f.draft.getDraft).toHaveBeenCalledTimes(2)
    expect(wrapper.find('[data-test="tg-refresh-error"]').exists()).toBe(true)
    expect(canvasEdgeIds(wrapper)).toEqual(['r1'])

    f.server.edges = [...f.server.edges, rel('r9', 'k1', 'k3')]
    f.draft.getDraft.mockImplementation(ok)
    await wrapper.find('[data-test="tg-refresh-retry"]').trigger('click')
    await flushPromises()
    expect(wrapper.find('[data-test="tg-refresh-error"]').exists()).toBe(false)
    expect(canvasEdgeIds(wrapper)).toEqual(['r1', 'r9'])
  })
})

// ---------------------------------------------------------------- 审查补充（刷新与写入交错、强制跳转、删除提示）

describe('审查补充', () => {
  it('刷新在途时保存成功：旧快照不覆盖画布', async () => {
    const f = fakes()
    const { wrapper } = await mountPage(f)
    const ok = f.draft.getDraft.getMockImplementation()!
    const stale = deferred<GraphExchange>()
    f.draft.getDraft.mockImplementationOnce(() => stale.promise)
    f.relations.create.mockRejectedValueOnce(apiError(409, 'REVISION_CONFLICT'))
    await openTab(wrapper, 'relations')
    await clickNode(wrapper, 'k2')
    await clickNode(wrapper, 'k3')
    await wrapper.find('.relation-editor__form').trigger('submit')
    await flushPromises()
    expect(f.draft.getDraft).toHaveBeenCalledTimes(2)

    f.draft.getDraft.mockImplementation(ok)
    const snapshot = draft('c1', f.server.nodes.map((n) => ({ ...n })), f.server.edges.map((e) => ({ ...e })))
    await openTab(wrapper, 'edit')
    await clickNode(wrapper, 'k1')
    await editName(wrapper, '栈')
    await wrapper.find('[data-test="ne-form"]').trigger('submit')
    await flushPromises()
    expect(canvasNodeNames(wrapper)).toContain('栈')

    stale.resolve(snapshot)
    await flushPromises()
    expect(canvasNodeNames(wrapper)).toContain('栈')
  })

  it('刷新在途时换课：晚到的旧课程草稿不写入', async () => {
    const f = fakes()
    f.relations.create.mockRejectedValueOnce(apiError(409, 'REVISION_CONFLICT'))
    const { wrapper, router } = await mountPage(f)
    const ok = f.draft.getDraft.getMockImplementation()!
    const stale = deferred<GraphExchange>()
    f.draft.getDraft.mockImplementationOnce(() => stale.promise)
    await openTab(wrapper, 'relations')
    await clickNode(wrapper, 'k2')
    await clickNode(wrapper, 'k3')
    await wrapper.find('.relation-editor__form').trigger('submit')
    await flushPromises()
    f.draft.getDraft.mockImplementation(ok)
    f.server.nodes = [kp('n1', {}, 'c2')]
    f.server.edges = []
    await router.push('/courses/c2/graph/edit')
    await flushPromises()
    stale.resolve(draft('c1', [kp('old')]))
    await flushPromises()
    expect(canvasNodeNames(wrapper)).toEqual(['知识点 n1'])
  })

  it('有未保存修改时换课先确认，取消则留在原课程', async () => {
    const f = fakes()
    const { wrapper, router } = await mountPage(f)
    await clickNode(wrapper, 'k1')
    await openTab(wrapper, 'edit')
    await editName(wrapper, '未保存的名字')
    const confirm = vi.spyOn(window, 'confirm').mockReturnValue(false)
    await router.push('/courses/c2/graph/edit')
    await flushPromises()
    expect(confirm).toHaveBeenCalledTimes(1)
    expect(router.currentRoute.value.params.cid).toBe('c1')
    expect(f.courses.get).not.toHaveBeenCalledWith('c2', expect.anything())
  })

  it('删除成功后显示已删除提示，再选节点时消失', async () => {
    const f = fakes()
    const { wrapper } = await mountPage(f)
    await clickNode(wrapper, 'k1')
    await openTab(wrapper, 'edit')
    await wrapper.find('[data-test="ne-delete"]').trigger('click')
    await flushPromises()
    await wrapper.find('[data-test="ne-delete-yes"]').trigger('click')
    await flushPromises()
    expect(wrapper.find('[data-test="tg-notice"]').text()).toContain('已删除')
    await clickNode(wrapper, 'k2')
    expect(wrapper.find('[data-test="tg-notice"]').exists()).toBe(false)
  })

  it('刷新后当前节点已不在草稿：提示未保存的修改已丢弃', async () => {
    const f = fakes()
    const { wrapper } = await mountPage(f)
    await clickNode(wrapper, 'k1')
    await openTab(wrapper, 'edit')
    await editName(wrapper, '未保存的名字')
    f.server.nodes = f.server.nodes.filter((n) => n.id !== 'k1')
    f.server.edges = []
    f.nodeEdit.update.mockRejectedValueOnce(apiError(404, 'NOT_FOUND'))
    wrapper.findComponent(TeacherGraphView).findComponent({ name: 'NodeEditor' }).vm.$emit('refreshNeeded')
    await flushPromises()
    expect(canvasNodeNames(wrapper)).toEqual(['知识点 k2', '知识点 k3'])
    expect(wrapper.find('[data-test="tg-notice"]').text()).toContain('未保存的修改')
  })

  it('有未保存修改时课程被拒：直接离开，不被确认拦住', async () => {
    const f = fakes()
    const { wrapper, router } = await mountPage(f)
    await clickNode(wrapper, 'k1')
    await openTab(wrapper, 'edit')
    await editName(wrapper, '未保存的名字')
    const confirm = vi.spyOn(window, 'confirm').mockReturnValue(false)
    f.relations.create.mockRejectedValueOnce(apiError(403, 'COURSE_FORBIDDEN'))
    await openTab(wrapper, 'relations')
    await clickNode(wrapper, 'k2')
    await clickNode(wrapper, 'k3')
    await wrapper.find('.relation-editor__form').trigger('submit')
    await flushPromises()
    expect(confirm).not.toHaveBeenCalled()
    expect(router.currentRoute.value.name).toBe('teacher-home')
  })

  it('课程上下文被清空而仍停在本页时显示错误态而非空白', async () => {
    const f = fakes()
    const { wrapper } = await mountPage(f)
    const { useCourseStore } = await import('../../src/frontend/src/stores/course')
    useCourseStore(pinia).selectCourse(null)
    await flushPromises()
    expect(wrapper.find('[data-test="tg-error"]').exists()).toBe(true)
  })

  it('确认框有说明文本并获得焦点', async () => {
    const f = fakes()
    const { wrapper } = await mountPage(f)
    await clickNode(wrapper, 'k1')
    await openTab(wrapper, 'edit')
    await editName(wrapper, 'x')
    await clickNode(wrapper, 'k2')
    const box = wrapper.find('[data-test="tg-discard-confirm"]')
    const described = box.attributes('aria-describedby')!
    expect(document.getElementById(described)?.textContent).toContain('未保存')
    expect(document.activeElement).toBe(box.element)
  })
})
