import { flushPromises, mount } from '@vue/test-utils'
import { readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { createPinia, setActivePinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { defineComponent, effectScope, h, type EffectScope } from 'vue'
import type { components } from '../../src/contracts/v1/generated/typescript/openapi'
import {
  AbortedError,
  ApiError,
  createHttpClient,
  NetworkError,
  type FetchLike,
} from '../../src/frontend/src/api/http'
import { createRelationsApi, type RelationsApi } from '../../src/frontend/src/api/relations'
import RelationEditor from '../../src/frontend/src/components/RelationEditor.vue'
import {
  CONFLICT_EDGE_STROKE,
  PENDING_EDGE_SUFFIX,
  useRelationEditor,
  type RelationEditor as RelationEditorState,
  type UseRelationEditorOptions,
} from '../../src/frontend/src/composables/useRelationEditor'
import { edgeElementId, RELATION_STYLES } from '../../src/frontend/src/graph/adapter'
import { createGraphLifecycle, type CanvasGraph, type CanvasGraphInit } from '../../src/frontend/src/graph/lifecycle'
import { useCourseStore } from '../../src/frontend/src/stores/course'

type GraphExchange = components['schemas']['GraphExchange']
type KnowledgePoint = components['schemas']['KnowledgePoint']
type Relation = components['schemas']['Relation']
type RelationType = components['schemas']['RelationType']
type ErrorCode = components['schemas']['ErrorCode']

// ---------- 数据与替身 ----------

function kp(id: string, name: string, courseId = 'c1'): KnowledgePoint {
  return {
    id,
    course_id: courseId,
    chapter_id: null,
    name,
    type: 'concept',
    definition: `${name} 的定义`,
    level: 1,
    confidence: 0.9,
    status: 'approved',
    source: 'ai',
    locked: false,
    revision: 1,
  } as KnowledgePoint
}

function rel(id: string, type: RelationType, from: string, to: string, courseId = 'c1'): Relation {
  return {
    id,
    course_id: courseId,
    type,
    from_id: from,
    to_id: to,
    confidence: 0.8,
    status: 'approved',
    source: 'ai',
    source_refs: [],
  }
}

function graphOf(nodes: KnowledgePoint[], edges: Relation[], courseId = 'c1'): GraphExchange {
  return {
    format_version: '1.0',
    course_id: courseId,
    graph_version: null,
    generated_at: '2026-09-26T00:00:00Z',
    nodes,
    edges,
  }
}

const A = kp('kp_a', '集合')
const B = kp('kp_b', '函数')
const C = kp('kp_c', '极限')
const D = kp('kp_d', '导数')
const R_AB = rel('r_ab', 'PREREQUISITE', 'kp_a', 'kp_b')
const R_BC = rel('r_bc', 'PREREQUISITE', 'kp_b', 'kp_c')
const R_CD = rel('r_cd', 'RELATED_TO', 'kp_c', 'kp_d')
const R_CA = rel('r_ca', 'EXAMPLE_OF', 'kp_c', 'kp_a')

function baseGraph(): GraphExchange {
  return graphOf([A, B, C, D], [R_AB, R_BC, R_CD, R_CA])
}

function apiError(status: number, code: ErrorCode, details?: Record<string, unknown>): ApiError {
  return new ApiError(status, { code, message: '服务端原文不应被展示', details })
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

function fakeApi(overrides: Partial<RelationsApi> = {}) {
  let n = 0
  return {
    create: vi.fn<RelationsApi['create']>(
      overrides.create ??
        (async (cid, body) => ({ ...rel(`r_new${++n}`, body.type, body.from_id, body.to_id, cid), source: 'manual' })),
    ),
    update: vi.fn<RelationsApi['update']>(
      overrides.update ??
        (async (cid, rid, body) => {
          const old = baseGraph().edges.find((e) => e.id === rid)!
          return { ...old, ...body, source: 'manual' } as Relation
        }),
    ),
    remove: vi.fn<RelationsApi['remove']>(overrides.remove ?? (async () => undefined)),
  }
}

let scopes: EffectScope[] = []

function setup(options: Partial<UseRelationEditorOptions> & { graph?: GraphExchange | null } = {}) {
  const store = useCourseStore()
  store.selectCourse('c1')
  const graph = options.graph === undefined ? baseGraph() : options.graph
  if (graph !== null) store.setGraph(store.beginRequest(), graph)
  const api = options.api ?? fakeApi()
  const onRefreshNeeded = options.onRefreshNeeded ?? vi.fn()
  const onCourseForbidden = options.onCourseForbidden ?? vi.fn()
  const scope = effectScope()
  scopes.push(scope)
  const editor = scope.run(() => useRelationEditor({ api, onRefreshNeeded, onCourseForbidden }))!
  return { store, api: api as ReturnType<typeof fakeApi>, editor, onRefreshNeeded, onCourseForbidden }
}

function edgeIds(editor: RelationEditorState): string[] {
  return (editor.graph.value?.edges ?? []).map((e) => e.id).sort()
}

function canvasEdge(editor: RelationEditorState, relationId: string) {
  return editor.canvasData.value?.edges.find((e) => e.data.relationId === relationId)
}

beforeEach(() => {
  setActivePinia(createPinia())
})

afterEach(() => {
  for (const scope of scopes) scope.stop()
  scopes = []
})

// ---------- API 层 ----------

describe('relations API（请求只经 api/ 层）', () => {
  function recordingFetch(status: number, body: unknown) {
    const calls: { url: string; init?: RequestInit }[] = []
    const fetch: FetchLike = async (url, init) => {
      calls.push({ url, init })
      return new Response(status === 204 ? null : JSON.stringify(body), {
        status,
        headers: { 'Content-Type': 'application/json' },
      })
    }
    return { calls, fetch }
  }

  it('新增为 POST /courses/{cid}/relations，请求体只含契约字段', async () => {
    const f = recordingFetch(201, rel('r1', 'PREREQUISITE', 'kp_a', 'kp_b'))
    const api = createRelationsApi(createHttpClient({ fetch: f.fetch }))
    const created = await api.create('c 1', { type: 'PREREQUISITE', from_id: 'kp_a', to_id: 'kp_b' })
    expect(created.id).toBe('r1')
    expect(f.calls[0].url).toBe('/api/v1/courses/c%201/relations')
    expect(f.calls[0].init?.method).toBe('POST')
    expect(JSON.parse(String(f.calls[0].init?.body))).toEqual({ type: 'PREREQUISITE', from_id: 'kp_a', to_id: 'kp_b' })
  })

  it('修改为 PATCH，删除为 DELETE 且 204 返回 undefined；关系 ID 逐段编码', async () => {
    const f = recordingFetch(200, rel('r/1', 'RELATED_TO', 'kp_a', 'kp_b'))
    const api = createRelationsApi(createHttpClient({ fetch: f.fetch }))
    await api.update('c1', 'r/1', { type: 'RELATED_TO' })
    expect(f.calls[0].url).toBe('/api/v1/courses/c1/relations/r%2F1')
    expect(f.calls[0].init?.method).toBe('PATCH')
    const g = recordingFetch(204, null)
    const api2 = createRelationsApi(createHttpClient({ fetch: g.fetch }))
    await expect(api2.remove('c1', 'r1')).resolves.toBeUndefined()
    expect(g.calls[0].init?.method).toBe('DELETE')
  })

  it('成环 409 原样抛出 ApiError，details.cycle 可读', async () => {
    const f = recordingFetch(409, {
      code: 'CYCLE_DETECTED',
      message: 'x',
      details: { cycle: ['kp_c', 'kp_a', 'kp_b', 'kp_c'] },
    })
    const api = createRelationsApi(createHttpClient({ fetch: f.fetch }))
    const error = await api.create('c1', { type: 'PREREQUISITE', from_id: 'kp_c', to_id: 'kp_a' }).catch((e) => e)
    expect(error).toBeInstanceOf(ApiError)
    expect(error.code).toBe('CYCLE_DETECTED')
    expect(error.details.cycle).toEqual(['kp_c', 'kp_a', 'kp_b', 'kp_c'])
  })
})

// ---------- 组合式：状态与选点 ----------

describe('useRelationEditor 状态与选点', () => {
  it('图谱未到达为 loading，无知识点为 empty，否则 ready', () => {
    expect(setup({ graph: null }).editor.status.value).toBe('loading')
    setActivePinia(createPinia())
    expect(setup({ graph: graphOf([], []) }).editor.status.value).toBe('empty')
    setActivePinia(createPinia())
    expect(setup().editor.status.value).toBe('ready')
  })

  it('画布点选：第一次定起点、第二次定终点、点起点自身忽略、第三次重新开始', () => {
    const { editor } = setup()
    editor.pickNode('kp_a')
    expect([editor.fromId.value, editor.toId.value]).toEqual(['kp_a', null])
    editor.pickNode('kp_a')
    expect([editor.fromId.value, editor.toId.value]).toEqual(['kp_a', null])
    editor.pickNode('kp_b')
    expect([editor.fromId.value, editor.toId.value]).toEqual(['kp_a', 'kp_b'])
    editor.pickNode('kp_c')
    expect([editor.fromId.value, editor.toId.value]).toEqual(['kp_c', null])
    editor.pickNode('kp_missing')
    expect([editor.fromId.value, editor.toId.value]).toEqual(['kp_c', null])
  })

  it('交换起终点；relationRows 只列与起点相连的关系并给出名称', () => {
    const { editor } = setup()
    editor.fromId.value = 'kp_a'
    editor.toId.value = 'kp_b'
    editor.swapDraft()
    expect([editor.fromId.value, editor.toId.value]).toEqual(['kp_b', 'kp_a'])
    const rows = editor.relationRows.value
    expect(rows.map((r) => r.id).sort()).toEqual(['r_ab', 'r_bc'])
    const ab = rows.find((r) => r.id === 'r_ab')!
    expect(ab).toMatchObject({ fromName: '集合', toName: '函数', typeLabel: '前置', reversible: true })
  })

  it('本地校验：未选端点、起终点相同时不发请求', async () => {
    const { editor, api } = setup()
    expect(await editor.createRelation()).toBe(false)
    expect(editor.error.value).toContain('起点和终点')
    editor.fromId.value = 'kp_a'
    editor.toId.value = 'kp_a'
    expect(await editor.createRelation()).toBe(false)
    expect(editor.error.value).toContain('同一个知识点')
    expect(api.create).not.toHaveBeenCalled()
  })
})

// ---------- 组合式：乐观更新与回滚 ----------

describe('useRelationEditor 乐观更新', () => {
  it('新增：请求期间出现临时边（保存中样式），成功后以服务端关系写入课程图谱', async () => {
    const pending = deferred<Relation>()
    const api = fakeApi({ create: () => pending.promise })
    const { editor, store } = setup({ api })
    editor.fromId.value = 'kp_a'
    editor.toId.value = 'kp_d'
    editor.draftType.value = 'EXAMPLE_OF'
    const done = editor.createRelation()
    expect(editor.saving.value).toBe(true)
    expect(api.create).toHaveBeenCalledWith(
      'c1',
      { type: 'EXAMPLE_OF', from_id: 'kp_a', to_id: 'kp_d' },
      expect.objectContaining({ signal: expect.any(AbortSignal) }),
    )
    const temp = editor.graph.value!.edges.find((e) => e.from_id === 'kp_a' && e.to_id === 'kp_d')!
    expect(temp).toBeDefined()
    expect(canvasEdge(editor, temp.id)!.style.labelText).toContain(PENDING_EDGE_SUFFIX)
    expect(canvasEdge(editor, temp.id)!.style.lineDash.length).toBeGreaterThan(0)
    // 临时边不进入 store
    expect(store.graph!.edges).toHaveLength(4)

    pending.resolve({ ...rel('r_ad', 'EXAMPLE_OF', 'kp_a', 'kp_d'), source: 'manual' })
    expect(await done).toBe(true)
    expect(editor.saving.value).toBe(false)
    expect(store.graph!.edges.map((e) => e.id)).toContain('r_ad')
    expect(edgeIds(editor)).toEqual(['r_ab', 'r_ad', 'r_bc', 'r_ca', 'r_cd'])
    expect(canvasEdge(editor, 'r_ad')!.style.labelText).toBe(RELATION_STYLES.EXAMPLE_OF.label)
    expect(editor.notice.value).toContain('已添加')
    expect(editor.toId.value).toBeNull()
  })

  it('成环：撤销临时边，按 details.cycle 高亮冲突路径上的已有前置边与节点，提示环路名称', async () => {
    const api = fakeApi({
      create: async () => {
        throw apiError(409, 'CYCLE_DETECTED', { cycle: ['kp_c', 'kp_a', 'kp_b', 'kp_c'] })
      },
    })
    const { editor, store } = setup({ api })
    editor.fromId.value = 'kp_c'
    editor.toId.value = 'kp_a'
    editor.draftType.value = 'PREREQUISITE'
    expect(await editor.createRelation()).toBe(false)

    expect(edgeIds(editor)).toEqual(['r_ab', 'r_bc', 'r_ca', 'r_cd'])
    expect(store.graph!.edges).toHaveLength(4)
    const conflict = editor.conflict.value!
    expect(conflict.path.map((p) => p.name)).toEqual(['极限', '集合', '函数', '极限'])
    expect(conflict.proposed).toEqual({ fromId: 'kp_c', toId: 'kp_a', type: 'PREREQUISITE' })
    expect([...editor.highlightedNodeIds.value].sort()).toEqual(['kp_a', 'kp_b', 'kp_c'])
    // 只高亮沿环方向的前置边；c→a 的 EXAMPLE_OF 不属于前置环
    expect([...editor.highlightedRelationIds.value].sort()).toEqual(['r_ab', 'r_bc'])
    expect(canvasEdge(editor, 'r_ab')!.style.stroke).toBe(CONFLICT_EDGE_STROKE)
    expect(canvasEdge(editor, 'r_bc')!.style.stroke).toBe(CONFLICT_EDGE_STROKE)
    expect(canvasEdge(editor, 'r_ca')!.style.stroke).toBe(RELATION_STYLES.EXAMPLE_OF.stroke)
    expect(canvasEdge(editor, 'r_cd')!.style.stroke).toBe(RELATION_STYLES.RELATED_TO.stroke)
    expect(editor.error.value).toContain('极限 → 集合 → 函数 → 极限')
    expect(editor.error.value).not.toContain('服务端原文')
  })

  it('高亮样式经画布生命周期传给 G6（边样式不被复制丢失）', async () => {
    const api = fakeApi({
      create: async () => {
        throw apiError(409, 'CYCLE_DETECTED', { cycle: ['kp_c', 'kp_a', 'kp_b', 'kp_c'] })
      },
    })
    const { editor } = setup({ api })
    editor.fromId.value = 'kp_c'
    editor.toId.value = 'kp_a'
    editor.draftType.value = 'PREREQUISITE'
    await editor.createRelation()

    const container = document.createElement('div')
    Object.defineProperty(container, 'clientWidth', { value: 800 })
    Object.defineProperty(container, 'clientHeight', { value: 600 })
    let init: CanvasGraphInit | null = null
    const fake: CanvasGraph = {
      destroyed: false,
      render: async () => undefined,
      setData: () => undefined,
      setSize: () => undefined,
      fitView: async () => undefined,
      on: () => undefined,
      destroy: () => undefined,
    }
    const lifecycle = createGraphLifecycle(container, {
      data: editor.canvasData.value!,
      factory: (i) => {
        init = i
        return fake
      },
    })
    await flushPromises()
    const drawn = init!.data.edges.find((e) => e.id === edgeElementId('r_ab'))!
    expect(drawn.style.stroke).toBe(CONFLICT_EDGE_STROKE)
    lifecycle.destroy()
  })

  it('成环但 details 不合规：仍撤销并提示，不高亮', async () => {
    const api = fakeApi({
      create: async () => {
        throw apiError(409, 'CYCLE_DETECTED', { cycle: 'kp_a' })
      },
    })
    const { editor } = setup({ api })
    editor.fromId.value = 'kp_c'
    editor.toId.value = 'kp_a'
    editor.draftType.value = 'PREREQUISITE'
    await editor.createRelation()
    expect(edgeIds(editor)).toEqual(['r_ab', 'r_bc', 'r_ca', 'r_cd'])
    expect(editor.conflict.value).toBeNull()
    expect(editor.highlightedRelationIds.value.size).toBe(0)
    expect(editor.error.value).toContain('环路')
  })

  it('改类型为前置而成环：回滚为原类型，并把被修改的关系一起标出', async () => {
    const api = fakeApi({
      update: async () => {
        throw apiError(409, 'CYCLE_DETECTED', { cycle: ['kp_c', 'kp_a', 'kp_b', 'kp_c'] })
      },
    })
    const { editor } = setup({ api })
    const done = editor.changeType('r_ca', 'PREREQUISITE')
    expect(editor.graph.value!.edges.find((e) => e.id === 'r_ca')!.type).toBe('PREREQUISITE')
    expect(await done).toBe(false)
    expect(api.update).toHaveBeenCalledWith('c1', 'r_ca', { type: 'PREREQUISITE' }, expect.anything())
    expect(editor.graph.value!.edges.find((e) => e.id === 'r_ca')!.type).toBe('EXAMPLE_OF')
    expect([...editor.highlightedRelationIds.value].sort()).toEqual(['r_ab', 'r_bc', 'r_ca'])
  })

  it('反转方向：乐观交换端点；服务端返回新 ID 时替换旧关系', async () => {
    const pending = deferred<Relation>()
    const api = fakeApi({ update: () => pending.promise })
    const { editor, store } = setup({ api })
    const done = editor.reverseRelation('r_ab')
    const optimistic = editor.graph.value!.edges.find((e) => e.id === 'r_ab')!
    expect([optimistic.from_id, optimistic.to_id]).toEqual(['kp_b', 'kp_a'])
    expect(api.update).toHaveBeenCalledWith('c1', 'r_ab', { from_id: 'kp_b', to_id: 'kp_a' }, expect.anything())
    pending.resolve({ ...rel('r_ba', 'PREREQUISITE', 'kp_b', 'kp_a'), source: 'manual' })
    expect(await done).toBe(true)
    expect(store.graph!.edges.map((e) => e.id).sort()).toEqual(['r_ba', 'r_bc', 'r_ca', 'r_cd'])
  })

  it('无向的相关关系不能反转，不发请求', async () => {
    const { editor, api } = setup()
    expect(await editor.reverseRelation('r_cd')).toBe(false)
    expect(api.update).not.toHaveBeenCalled()
    expect(editor.error.value).toContain('无方向')
  })

  it('删除：乐观移除；课程忙时恢复原边并提示稍后重试', async () => {
    const pending = deferred<void>()
    const api = fakeApi({ remove: () => pending.promise })
    const { editor, store } = setup({ api })
    const done = editor.deleteRelation('r_bc')
    expect(edgeIds(editor)).toEqual(['r_ab', 'r_ca', 'r_cd'])
    pending.reject(apiError(409, 'COURSE_BUSY', { holder: 'publish' }))
    expect(await done).toBe(false)
    expect(edgeIds(editor)).toEqual(['r_ab', 'r_bc', 'r_ca', 'r_cd'])
    expect(store.graph!.edges).toHaveLength(4)
    expect(editor.error.value).toContain('稍后重试')
  })

  it('删除成功后从课程图谱移除', async () => {
    const { editor, store } = setup()
    expect(await editor.deleteRelation('r_bc')).toBe(true)
    expect(store.graph!.edges.map((e) => e.id)).not.toContain('r_bc')
    expect(editor.notice.value).toContain('已删除')
  })

  it('修订冲突：撤销改动、标记需刷新并通知调用方重新加载图谱', async () => {
    const api = fakeApi({
      update: async () => {
        throw apiError(409, 'REVISION_CONFLICT', { current_revision: 3 })
      },
    })
    const { editor, onRefreshNeeded } = setup({ api })
    expect(await editor.changeType('r_ab', 'RELATED_TO')).toBe(false)
    expect(editor.graph.value!.edges.find((e) => e.id === 'r_ab')!.type).toBe('PREREQUISITE')
    expect(editor.stale.value).toBe(true)
    expect(onRefreshNeeded).toHaveBeenCalledTimes(1)
    expect(editor.error.value).toContain('已被修改')
  })

  it('图谱重新加载后清除「需刷新」标记', async () => {
    const api = fakeApi({
      remove: async () => {
        throw apiError(404, 'NOT_FOUND')
      },
    })
    const { editor, store, onRefreshNeeded } = setup({ api })
    await editor.deleteRelation('r_ab')
    expect(onRefreshNeeded).toHaveBeenCalledTimes(1)
    expect(editor.stale.value).toBe(true)
    expect(edgeIds(editor)).toContain('r_ab')
    store.setGraph(store.beginRequest(), graphOf([A, B], []))
    await flushPromises()
    expect(editor.stale.value).toBe(false)
  })

  it('重复关系：撤销临时边并标出已有关系', async () => {
    const api = fakeApi({
      create: async () => {
        throw apiError(409, 'DUPLICATE_RELATION', { existing_id: 'r_ab' })
      },
    })
    const { editor } = setup({ api })
    editor.fromId.value = 'kp_a'
    editor.toId.value = 'kp_b'
    editor.draftType.value = 'PREREQUISITE'
    await editor.createRelation()
    expect(edgeIds(editor)).toEqual(['r_ab', 'r_bc', 'r_ca', 'r_cd'])
    expect([...editor.highlightedRelationIds.value]).toEqual(['r_ab'])
    expect(editor.error.value).toContain('已存在')
  })

  it('端点无效：撤销并要求刷新', async () => {
    const api = fakeApi({
      create: async () => {
        throw apiError(422, 'DANGLING_ENDPOINT', { missing: ['kp_d'] })
      },
    })
    const { editor, onRefreshNeeded } = setup({ api })
    editor.fromId.value = 'kp_a'
    editor.toId.value = 'kp_d'
    await editor.createRelation()
    expect(edgeIds(editor)).toEqual(['r_ab', 'r_bc', 'r_ca', 'r_cd'])
    expect(onRefreshNeeded).toHaveBeenCalledTimes(1)
  })

  it('无课程权限：撤销并交给调用方回课程列表', async () => {
    const api = fakeApi({
      create: async () => {
        throw apiError(403, 'COURSE_FORBIDDEN')
      },
    })
    const { editor, store, onCourseForbidden } = setup({ api })
    editor.fromId.value = 'kp_a'
    editor.toId.value = 'kp_d'
    expect(await editor.createRelation()).toBe(false)
    expect(onCourseForbidden).toHaveBeenCalledTimes(1)
    // 当前课程被清空：图谱随之清空，临时边不残留
    expect(store.courseId).toBeNull()
    expect(editor.graph.value).toBeNull()
  })

  it('角色无权、网络失败给固定文案，不回显服务端 message', async () => {
    const errors = [apiError(403, 'ROLE_FORBIDDEN'), new NetworkError(new Error('x'))]
    const api = fakeApi({
      create: async () => {
        throw errors.shift()
      },
    })
    const { editor } = setup({ api })
    editor.fromId.value = 'kp_a'
    editor.toId.value = 'kp_d'
    await editor.createRelation()
    expect(editor.error.value).toContain('无权')
    await editor.createRelation()
    expect(editor.error.value).toContain('网络')
    expect(editor.error.value).not.toContain('服务端原文')
  })

  it('保存中再次操作被拒绝，只发一次请求', async () => {
    const pending = deferred<Relation>()
    const api = fakeApi({ create: () => pending.promise })
    const { editor } = setup({ api })
    editor.fromId.value = 'kp_a'
    editor.toId.value = 'kp_d'
    const first = editor.createRelation()
    expect(await editor.createRelation()).toBe(false)
    expect(await editor.deleteRelation('r_ab')).toBe(false)
    expect(api.create).toHaveBeenCalledTimes(1)
    expect(api.remove).not.toHaveBeenCalled()
    pending.resolve(rel('r_ad', 'PREREQUISITE', 'kp_a', 'kp_d'))
    await first
  })

  it('请求期间图谱被重新加载：成功结果合并进最新图谱', async () => {
    const pending = deferred<Relation>()
    const api = fakeApi({ create: () => pending.promise })
    const { editor, store } = setup({ api })
    editor.fromId.value = 'kp_a'
    editor.toId.value = 'kp_d'
    const done = editor.createRelation()
    store.setGraph(store.beginRequest(), graphOf([A, B, C, D], [R_AB]))
    pending.resolve(rel('r_ad', 'PREREQUISITE', 'kp_a', 'kp_d'))
    await done
    expect(store.graph!.edges.map((e) => e.id).sort()).toEqual(['r_ab', 'r_ad'])
  })

  it('请求期间切换课程：取消请求、丢弃晚到结果、清空临时边与提示', async () => {
    let signal: AbortSignal | undefined
    const pending = deferred<Relation>()
    const api = fakeApi({
      create: (_cid, _body, control) => {
        signal = control?.signal
        return pending.promise
      },
    })
    const { editor, store } = setup({ api })
    editor.fromId.value = 'kp_a'
    editor.toId.value = 'kp_d'
    const done = editor.createRelation()
    store.selectCourse('c2')
    store.setGraph(store.beginRequest(), graphOf([kp('kp_x', 'X', 'c2')], [], 'c2'))
    await flushPromises()
    expect(signal?.aborted).toBe(true)
    pending.reject(new AbortedError())
    expect(await done).toBe(false)
    expect(store.graph!.course_id).toBe('c2')
    expect(store.graph!.edges).toHaveLength(0)
    expect(editor.graph.value!.edges).toHaveLength(0)
    expect(editor.error.value).toBeNull()
    expect(editor.saving.value).toBe(false)
    expect(editor.fromId.value).toBeNull()
  })

  it('切课后旧课程晚到的失败不改写新课程的提示与冲突', async () => {
    const pending = deferred<Relation>()
    const onRefreshNeeded = vi.fn()
    const api = fakeApi({ create: () => pending.promise })
    const { editor, store } = setup({ api, onRefreshNeeded })
    editor.fromId.value = 'kp_c'
    editor.toId.value = 'kp_a'
    editor.draftType.value = 'PREREQUISITE'
    const done = editor.createRelation()
    store.selectCourse('c2')
    await flushPromises()
    pending.reject(apiError(409, 'REVISION_CONFLICT'))
    expect(await done).toBe(false)
    expect(editor.error.value).toBeNull()
    expect(editor.stale.value).toBe(false)
    expect(onRefreshNeeded).not.toHaveBeenCalled()
  })

  it('新操作清除上一次的冲突高亮；dismissConflict 手动清除', async () => {
    const errors: unknown[] = [apiError(409, 'CYCLE_DETECTED', { cycle: ['kp_c', 'kp_a', 'kp_b', 'kp_c'] })]
    const api = fakeApi({
      create: async (cid, body) => {
        const e = errors.shift()
        if (e) throw e
        return rel('r_new', body.type, body.from_id, body.to_id, cid)
      },
    })
    const { editor } = setup({ api })
    editor.fromId.value = 'kp_c'
    editor.toId.value = 'kp_a'
    editor.draftType.value = 'PREREQUISITE'
    await editor.createRelation()
    expect(editor.conflict.value).not.toBeNull()
    editor.dismissConflict()
    expect(editor.conflict.value).toBeNull()
    expect(editor.highlightedRelationIds.value.size).toBe(0)

    errors.push(apiError(409, 'CYCLE_DETECTED', { cycle: ['kp_c', 'kp_a', 'kp_b', 'kp_c'] }))
    await editor.createRelation()
    expect(editor.conflict.value).not.toBeNull()
    editor.draftType.value = 'RELATED_TO'
    expect(await editor.createRelation()).toBe(true)
    expect(editor.conflict.value).toBeNull()
  })
})

// ---------- 组件 ----------

function mountEditor(options: Partial<UseRelationEditorOptions> & { graph?: GraphExchange | null } = {}) {
  const ctx = setup(options)
  const wrapper = mount(
    defineComponent({ render: () => h(RelationEditor, { editor: ctx.editor }) }),
    { attachTo: document.body },
  )
  return { ...ctx, wrapper }
}

describe('RelationEditor 组件', () => {
  it('加载态与空态', async () => {
    const loading = mountEditor({ graph: null })
    expect(loading.wrapper.get('[role="status"]').text()).toContain('加载中')
    expect(loading.wrapper.find('form').exists()).toBe(false)
    setActivePinia(createPinia())
    const empty = mountEditor({ graph: graphOf([], []) })
    expect(empty.wrapper.text()).toContain('暂无知识点')
  })

  it('表单控件有可访问名称；提交后按所选端点与类型发请求，保存中 aria-busy 且按钮禁用', async () => {
    const pending = deferred<Relation>()
    const api = fakeApi({ create: () => pending.promise })
    const { wrapper } = mountEditor({ api })
    const from = wrapper.get('select[name="from"]')
    const to = wrapper.get('select[name="to"]')
    const type = wrapper.get('select[name="type"]')
    for (const el of [from, to, type]) {
      const id = el.attributes('id')!
      expect(wrapper.find(`label[for="${id}"]`).exists()).toBe(true)
    }
    await from.setValue('kp_a')
    await to.setValue('kp_d')
    await type.setValue('EXAMPLE_OF')
    await wrapper.get('form').trigger('submit')
    expect(api.create).toHaveBeenCalledWith('c1', { type: 'EXAMPLE_OF', from_id: 'kp_a', to_id: 'kp_d' }, expect.anything())
    expect(wrapper.get('section').attributes('aria-busy')).toBe('true')
    expect(wrapper.get('button[type="submit"]').attributes('disabled')).toBeDefined()
    pending.resolve(rel('r_ad', 'EXAMPLE_OF', 'kp_a', 'kp_d'))
    await flushPromises()
    expect(wrapper.get('section').attributes('aria-busy')).toBe('false')
    expect(wrapper.get('[role="status"]').text()).toContain('已添加')
  })

  it('反转按钮交换起终点', async () => {
    const { wrapper, editor } = mountEditor()
    await wrapper.get('select[name="from"]').setValue('kp_a')
    await wrapper.get('select[name="to"]').setValue('kp_b')
    await wrapper.get('button[data-action="swap"]').trigger('click')
    expect([editor.fromId.value, editor.toId.value]).toEqual(['kp_b', 'kp_a'])
  })

  it('成环时以 alert 按顺序列出冲突路径，可关闭', async () => {
    const api = fakeApi({
      create: async () => {
        throw apiError(409, 'CYCLE_DETECTED', { cycle: ['kp_c', 'kp_a', 'kp_b', 'kp_c'] })
      },
    })
    const { wrapper } = mountEditor({ api })
    await wrapper.get('select[name="from"]').setValue('kp_c')
    await wrapper.get('select[name="to"]').setValue('kp_a')
    await wrapper.get('select[name="type"]').setValue('PREREQUISITE')
    await wrapper.get('form').trigger('submit')
    await flushPromises()
    const alert = wrapper.get('[data-testid="cycle-conflict"]')
    expect(alert.attributes('role')).toBe('alert')
    expect(alert.findAll('li').map((li) => li.text())).toEqual(['极限', '集合', '函数', '极限'])
    await alert.get('button').trigger('click')
    expect(wrapper.find('[data-testid="cycle-conflict"]').exists()).toBe(false)
  })

  it('起点的关系列表：改类型、反转、删除都经组合式发请求；相关关系不可反转', async () => {
    const { wrapper, api } = mountEditor()
    await wrapper.get('select[name="from"]').setValue('kp_c')
    const rows = wrapper.findAll('li[data-relation-id]')
    expect(rows.map((r) => r.attributes('data-relation-id')).sort()).toEqual(['r_bc', 'r_ca', 'r_cd'])
    const cd = wrapper.get('li[data-relation-id="r_cd"]')
    expect(cd.get('button[data-action="reverse"]').attributes('disabled')).toBeDefined()
    const bcType = wrapper.get('li[data-relation-id="r_bc"] select')
    expect(wrapper.find(`label[for="${bcType.attributes('id')}"]`).exists()).toBe(true)
    await bcType.setValue('RELATED_TO')
    await flushPromises()
    expect(api.update).toHaveBeenCalledWith('c1', 'r_bc', { type: 'RELATED_TO' }, expect.anything())
    await wrapper.get('li[data-relation-id="r_ca"] button[data-action="reverse"]').trigger('click')
    await flushPromises()
    expect(api.update).toHaveBeenCalledWith('c1', 'r_ca', { from_id: 'kp_a', to_id: 'kp_c' }, expect.anything())
    await wrapper.get('li[data-relation-id="r_cd"] button[data-action="delete"]').trigger('click')
    await flushPromises()
    expect(api.remove).toHaveBeenCalledWith('c1', 'r_cd', expect.anything())
  })

  it('错误以 alert 呈现', async () => {
    const api = fakeApi({
      remove: async () => {
        throw apiError(409, 'COURSE_BUSY')
      },
    })
    const { wrapper } = mountEditor({ api })
    await wrapper.get('select[name="from"]').setValue('kp_a')
    await wrapper.get('li[data-relation-id="r_ab"] button[data-action="delete"]').trigger('click')
    await flushPromises()
    expect(wrapper.get('[data-testid="relation-error"]').attributes('role')).toBe('alert')
  })
})

// ---------- 分层约束 ----------

describe('分层：组件无 Cypher、无直接请求', () => {
  const root = resolve(dirname(fileURLToPath(import.meta.url)), '../../src/frontend/src')
  const component = readFileSync(resolve(root, 'components/RelationEditor.vue'), 'utf8')
  const composable = readFileSync(resolve(root, 'composables/useRelationEditor.ts'), 'utf8')
  // Cypher 子句关键字后接模式，或关系模式 `-[r:TYPE]->`
  const CYPHER = /\b(MATCH|MERGE|UNWIND|DETACH\s+DELETE)\s+[(\w]|-\[\s*\w*\s*:\s*\w*\s*\]\s*->/

  it('组件不发请求、不引用 api 层与 store，不含 Cypher', () => {
    expect(component).not.toMatch(/\bfetch\s*\(|\.request\s*\(|XMLHttpRequest|EventSource/)
    expect(component).not.toMatch(/from\s+['"][^'"]*\/api\//)
    expect(component).not.toMatch(/from\s+['"][^'"]*\/stores\//)
    expect(component).not.toMatch(CYPHER)
  })

  it('组合式只经注入的 RelationsApi 发请求，不含 Cypher', () => {
    expect(composable).not.toMatch(/\bfetch\s*\(|\.request\s*\(|XMLHttpRequest/)
    expect(composable).not.toMatch(/from\s+['"][^'"]*\/api\/http['"][^\n]*createHttpClient/)
    expect(composable).not.toMatch(CYPHER)
  })
})
