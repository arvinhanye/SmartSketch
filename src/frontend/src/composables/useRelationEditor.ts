import { computed, onScopeDispose, ref, shallowRef, watch, type ComputedRef, type Ref } from 'vue'
import type { components } from '../../../contracts/v1/generated/typescript/openapi'
import { AbortedError, ApiError, NetworkError, TimeoutError } from '../api/http'
import type { Relation, RelationsApi, RelationUpdate } from '../api/relations'
import { RELATION_STYLES, toG6Data, type RelationType } from '../graph/adapter'
import type { GraphCanvasData } from '../graph/lifecycle'
import { useCourseStore, type CourseRequestScope } from '../stores/course'

/**
 * 教师连边编辑状态（H08）：新增关系（下拉或在画布上依次点选起点、终点）、改类型、反转方向、删除。
 *
 * - 乐观更新：请求期间在「工作图」上叠加一条临时改动（新边 / 改后的边 / 移除），不写入课程 store；
 *   成功后把服务端返回的关系合并进 store 中**当时**的图谱（`setGraph`），失败即丢弃叠加层，临时边随之撤销。
 * - 成环：409 `CYCLE_DETECTED` 的 `details.cycle`（首尾相同的知识点 ID 链，沿边方向）换成节点名称路径，
 *   并把环上相邻两点之间已有的前置边、以及本次被修改的关系标为冲突，`canvasData` 中以冲突色绘出。
 * - 修订冲突 / 关系或端点已不存在：撤销改动，标记 `stale` 并调用 `onRefreshNeeded` 让页面重新加载图谱；
 *   关系接口本身不带 `expected_revision`，这里按通用 409 `REVISION_CONFLICT` 兜底处理。
 * - 一次只允许一个写请求：课程写锁本就串行化草稿写入，单请求也让回滚只涉及一处叠加。
 * - 所有请求在 `beginRequest()` 作用域内发出；切课后在途请求随 signal 取消，晚到结果被丢弃。
 * - 错误只按错误码给固定文案，不回显服务端 message。组件只拿本组合式的返回值，不接触请求与 store。
 */

type GraphExchange = components['schemas']['GraphExchange']
type KnowledgePoint = components['schemas']['KnowledgePoint']

export const RELATION_TYPES: readonly RelationType[] = ['PREREQUISITE', 'CONTAINS', 'RELATED_TO', 'EXAMPLE_OF']

/** 冲突路径上的边在画布上的颜色 */
export const CONFLICT_EDGE_STROKE = '#ff4d4f'
export const CONFLICT_EDGE_WIDTH = 3
/** 保存中的临时边：标签后缀与虚线 */
export const PENDING_EDGE_SUFFIX = '（保存中）'
const PENDING_EDGE_DASH = [4, 4]
const TEMP_ID_PREFIX = 'pending:'

export interface ConflictPathNode {
  kpId: string
  /** 图中找不到该知识点时退回 ID */
  name: string
}

export interface CycleConflict {
  /** 首尾相同的环路，顺序同 `details.cycle` */
  path: ConflictPathNode[]
  /** 被拒绝的改动：要新增或改成的边 */
  proposed: { fromId: string; toId: string; type: RelationType }
}

export interface RelationRow {
  id: string
  type: RelationType
  typeLabel: string
  fromId: string
  fromName: string
  toId: string
  toName: string
  /** `RELATED_TO` 无方向，不能反转 */
  reversible: boolean
  pending: boolean
  highlighted: boolean
  downgraded: boolean
}

export interface NodeOption {
  id: string
  name: string
}

export type RelationEditorStatus = 'loading' | 'empty' | 'ready'

export interface UseRelationEditorOptions {
  api: RelationsApi
  /** 改动因图谱已变化被拒（修订冲突、关系或端点已不存在）：页面应重新加载草稿图谱 */
  onRefreshNeeded?: () => void
  /** `COURSE_FORBIDDEN`：当前课程已清空，调用方负责回课程列表 */
  onCourseForbidden?: () => void
}

type PendingEdit =
  | { kind: 'create'; relation: Relation }
  | { kind: 'update'; relationId: string; relation: Relation }
  | { kind: 'delete'; relationId: string }

const NETWORK_MESSAGE = '无法连接服务器，已撤销本次改动，请检查网络后重试。'
const STALE_MESSAGE = '图谱已被修改（其他教师或处理任务），已撤销本次改动，请刷新图谱后重试。'

function nameOf(nodes: Map<string, KnowledgePoint>, id: string): string {
  return nodes.get(id)?.name ?? id
}

function readCycle(details: Record<string, unknown> | undefined): string[] | null {
  const cycle = details?.cycle
  if (!Array.isArray(cycle) || cycle.length < 2) return null
  if (!cycle.every((id): id is string => typeof id === 'string' && id !== '')) return null
  return cycle
}

function applyPending(edges: readonly Relation[], edit: PendingEdit | null): Relation[] {
  if (edit === null) return [...edges]
  switch (edit.kind) {
    case 'create':
      return [...edges, edit.relation]
    case 'update':
      return edges.map((e) => (e.id === edit.relationId ? edit.relation : e))
    case 'delete':
      return edges.filter((e) => e.id !== edit.relationId)
  }
}

/** 乐观改动后的关系：只保留标准字段，改过的关系不再是「自动降级」形态 */
function edited(rel: Relation, patch: Partial<Pick<Relation, 'type' | 'from_id' | 'to_id'>>): Relation {
  return {
    id: rel.id,
    course_id: rel.course_id,
    type: patch.type ?? rel.type,
    from_id: patch.from_id ?? rel.from_id,
    to_id: patch.to_id ?? rel.to_id,
    confidence: rel.confidence,
    status: rel.status,
    source: rel.source,
    source_refs: rel.source_refs,
  }
}

/** 把服务端确认的结果合并进（可能已重新加载过的）图谱 */
function applyConfirmed(graph: GraphExchange, edit: PendingEdit, confirmed: Relation | null): GraphExchange {
  let edges = graph.edges
  if (edit.kind !== 'create') edges = edges.filter((e) => e.id !== edit.relationId)
  if (confirmed !== null) edges = [...edges.filter((e) => e.id !== confirmed.id), confirmed]
  return { ...graph, edges }
}

export function useRelationEditor({ api, onRefreshNeeded, onCourseForbidden }: UseRelationEditorOptions) {
  const store = useCourseStore()
  let disposed = false
  let tempSeq = 0
  let inFlight = false
  /** 每次写请求一个序号；切课后旧请求的收尾不得清掉新请求的保存中状态 */
  let opSeq = 0

  const pending = shallowRef<PendingEdit | null>(null)
  const saving = ref(false)
  const error = ref<string | null>(null)
  const notice = ref<string | null>(null)
  const conflict = shallowRef<CycleConflict | null>(null)
  /** 冲突时额外标出的关系（被修改的关系、重复关系的已有边） */
  const markedRelationIds = shallowRef<ReadonlySet<string>>(new Set())
  const stale = ref(false)

  const fromId = ref<string | null>(null)
  const toId = ref<string | null>(null)
  const draftType = ref<RelationType>('PREREQUISITE')

  // ------------------------------------------------------------ 派生
  const graph: ComputedRef<GraphExchange | null> = computed(() => {
    const base = store.graph
    if (base === null) return null
    return { ...base, edges: applyPending(base.edges, pending.value) }
  })

  const nodeIndex = computed(() => new Map((graph.value?.nodes ?? []).map((n) => [n.id, n])))

  const status: ComputedRef<RelationEditorStatus> = computed(() => {
    if (graph.value === null) return 'loading'
    return graph.value.nodes.length === 0 ? 'empty' : 'ready'
  })

  const nodeOptions: ComputedRef<NodeOption[]> = computed(() =>
    (graph.value?.nodes ?? []).map((n) => ({ id: n.id, name: n.name })),
  )

  const highlightedNodeIds: ComputedRef<ReadonlySet<string>> = computed(
    () => new Set(conflict.value?.path.map((p) => p.kpId) ?? []),
  )

  const highlightedRelationIds: ComputedRef<ReadonlySet<string>> = computed(() => {
    const ids = new Set(markedRelationIds.value)
    const path = conflict.value?.path
    if (path && graph.value) {
      const pairs = new Set<string>()
      for (let i = 0; i + 1 < path.length; i += 1) pairs.add(`${path[i].kpId}\u0000${path[i + 1].kpId}`)
      for (const edge of graph.value.edges) {
        if (edge.type !== 'PREREQUISITE' || edge.status === 'rejected') continue
        if (pairs.has(`${edge.from_id}\u0000${edge.to_id}`)) ids.add(edge.id)
      }
    }
    return ids
  })

  const pendingRelationId = computed(() => {
    const edit = pending.value
    if (edit === null || edit.kind === 'delete') return null
    return edit.relation.id
  })

  const canvasData: ComputedRef<GraphCanvasData | null> = computed(() => {
    if (graph.value === null) return null
    const adapted = toG6Data(graph.value)
    const highlighted = highlightedRelationIds.value
    const edges = adapted.edges.map((edge) => {
      const { relationId } = edge.data
      if (relationId === pendingRelationId.value) {
        return {
          ...edge,
          style: { ...edge.style, lineDash: [...PENDING_EDGE_DASH], labelText: `${edge.style.labelText}${PENDING_EDGE_SUFFIX}` },
        }
      }
      if (highlighted.has(relationId)) {
        return { ...edge, style: { ...edge.style, stroke: CONFLICT_EDGE_STROKE, lineWidth: CONFLICT_EDGE_WIDTH } }
      }
      return edge
    })
    return { nodes: adapted.nodes, edges }
  })

  const relationRows: ComputedRef<RelationRow[]> = computed(() => {
    const focus = fromId.value
    if (focus === null || graph.value === null) return []
    const nodes = nodeIndex.value
    return graph.value.edges
      .filter((e) => e.from_id === focus || e.to_id === focus)
      .map((e) => ({
        id: e.id,
        type: e.type,
        typeLabel: RELATION_STYLES[e.type].label,
        fromId: e.from_id,
        fromName: nameOf(nodes, e.from_id),
        toId: e.to_id,
        toName: nameOf(nodes, e.to_id),
        reversible: RELATION_STYLES[e.type].directed,
        pending: e.id === pendingRelationId.value,
        highlighted: highlightedRelationIds.value.has(e.id),
        downgraded: 'downgraded_from_type' in e,
      }))
  })

  // ------------------------------------------------------------ 选点
  function pickNode(kpId: string): void {
    if (!nodeIndex.value.has(kpId)) return
    if (fromId.value === null || toId.value !== null) {
      fromId.value = kpId
      toId.value = null
    } else if (kpId !== fromId.value) {
      toId.value = kpId
    }
  }

  function swapDraft(): void {
    const from = fromId.value
    fromId.value = toId.value
    toId.value = from
  }

  function dismissConflict(): void {
    conflict.value = null
    markedRelationIds.value = new Set()
  }

  // ------------------------------------------------------------ 错误
  function fail(message: string): false {
    error.value = message
    notice.value = null
    return false
  }

  function markStale(): void {
    stale.value = true
    onRefreshNeeded?.()
  }

  function handleError(cause: unknown, edit: PendingEdit, proposed: CycleConflict['proposed'] | null): void {
    if (cause instanceof ApiError) {
      switch (cause.code) {
        case 'CYCLE_DETECTED': {
          const cycle = readCycle(cause.details)
          if (cycle === null || proposed === null) {
            fail('该前置关系会形成学习环路，已撤销。')
            return
          }
          const nodes = nodeIndex.value
          const path = cycle.map((kpId) => ({ kpId, name: nameOf(nodes, kpId) }))
          conflict.value = { path, proposed }
          if (edit.kind === 'update') markedRelationIds.value = new Set([edit.relationId])
          fail(`该前置关系会形成学习环路，已撤销：${path.map((p) => p.name).join(' → ')}`)
          return
        }
        case 'DUPLICATE_RELATION': {
          const existing = cause.details?.existing_id
          if (typeof existing === 'string' && existing !== '') markedRelationIds.value = new Set([existing])
          fail('同类型、同方向的关系已存在，已撤销。')
          return
        }
        case 'REVISION_CONFLICT':
          markStale()
          fail(STALE_MESSAGE)
          return
        case 'NOT_FOUND':
          markStale()
          fail('该关系已不存在，已撤销本次改动，请刷新图谱。')
          return
        case 'DANGLING_ENDPOINT':
          markStale()
          fail('关系端点不存在或不属于本课程，已撤销，请刷新图谱。')
          return
        case 'COURSE_BUSY':
          fail('课程正在进行其他写入或发布，已撤销本次改动，请稍后重试。')
          return
        case 'ROLE_FORBIDDEN':
          fail('无权编辑关系：只有本课程的教师可以修改图谱。')
          return
        case 'VALIDATION_ERROR':
          fail('关系参数不符合要求，已撤销。')
          return
        case 'UNAUTHENTICATED':
          fail('登录已失效，请重新登录。')
          return
      }
    }
    if (cause instanceof NetworkError || cause instanceof TimeoutError) {
      fail(NETWORK_MESSAGE)
      return
    }
    fail('保存关系失败，已撤销本次改动，请稍后重试。')
  }

  // ------------------------------------------------------------ 提交
  async function run(
    edit: PendingEdit,
    send: (scope: CourseRequestScope) => Promise<Relation | null>,
    success: string,
    proposed: CycleConflict['proposed'] | null,
  ): Promise<boolean> {
    const scope = store.beginRequest()
    const op = ++opSeq
    inFlight = true
    saving.value = true
    error.value = null
    notice.value = null
    dismissConflict()
    pending.value = edit
    try {
      const confirmed = await send(scope)
      const committed = store.commit(scope, () => {
        if (store.graph !== null) store.setGraph(scope, applyConfirmed(store.graph, edit, confirmed))
        notice.value = success
      })
      return committed && !disposed
    } catch (cause) {
      if (disposed || !scope.isCurrent() || cause instanceof AbortedError) return false
      if (cause instanceof ApiError && cause.code === 'COURSE_FORBIDDEN') {
        store.selectCourse(null)
        onCourseForbidden?.()
        return false
      }
      handleError(cause, edit, proposed)
      return false
    } finally {
      // 成功时 store 已含确认结果，失败时丢弃即回滚；切课时叠加层也已被清空
      if (pending.value === edit) pending.value = null
      if (op === opSeq) {
        inFlight = false
        saving.value = false
      }
    }
  }

  /** 发请求前的公共检查；返回当前图谱或 null（已写入错误） */
  function ready(): GraphExchange | null {
    if (inFlight) return null
    const current = store.graph
    if (current === null || store.courseId === null) {
      fail('图谱尚未加载，无法编辑关系。')
      return null
    }
    return current
  }

  function findRelation(current: GraphExchange, relationId: string): Relation | null {
    const found = current.edges.find((e) => e.id === relationId)
    if (found === undefined) {
      fail('该关系已不存在，请刷新图谱。')
      return null
    }
    return found
  }

  async function createRelation(): Promise<boolean> {
    const from = fromId.value
    const to = toId.value
    if (from === null || to === null) return fail('请选择关系的起点和终点。')
    if (from === to) return fail('起点和终点不能是同一个知识点。')
    const current = ready()
    if (current === null) return false
    const nodes = nodeIndex.value
    if (!nodes.has(from) || !nodes.has(to)) return fail('所选知识点不在当前图谱中，请刷新图谱。')
    const type = draftType.value
    tempSeq += 1
    const temp: Relation = {
      id: `${TEMP_ID_PREFIX}${tempSeq}`,
      course_id: current.course_id,
      type,
      from_id: from,
      to_id: to,
      confidence: 1,
      status: 'draft',
      source: 'manual',
      source_refs: [],
    }
    const ok = await run(
      { kind: 'create', relation: temp },
      (scope) => api.create(scope.courseId, { type, from_id: from, to_id: to }, { signal: scope.signal }),
      `已添加关系：${nameOf(nodes, from)} → ${nameOf(nodes, to)}（${RELATION_STYLES[type].label}）。`,
      { fromId: from, toId: to, type },
    )
    if (ok) toId.value = null
    return ok
  }

  async function update(relationId: string, body: RelationUpdate, next: (old: Relation) => Relation, success: string) {
    const current = ready()
    if (current === null) return false
    const old = findRelation(current, relationId)
    if (old === null) return false
    const optimistic = next(old)
    return run(
      { kind: 'update', relationId, relation: optimistic },
      (scope) => api.update(scope.courseId, relationId, body, { signal: scope.signal }),
      success,
      { fromId: optimistic.from_id, toId: optimistic.to_id, type: optimistic.type },
    )
  }

  async function changeType(relationId: string, type: RelationType): Promise<boolean> {
    if (inFlight) return false
    const old = store.graph?.edges.find((e) => e.id === relationId)
    if (old !== undefined && old.type === type) return false
    return update(
      relationId,
      { type },
      (rel) => edited(rel, { type }),
      `已将关系类型改为「${RELATION_STYLES[type].label}」。`,
    )
  }

  async function reverseRelation(relationId: string): Promise<boolean> {
    if (inFlight) return false
    const old = store.graph?.edges.find((e) => e.id === relationId)
    if (old !== undefined && !RELATION_STYLES[old.type].directed) return fail('「相关」关系无方向，不能反转。')
    return update(
      relationId,
      old === undefined ? {} : { from_id: old.to_id, to_id: old.from_id },
      (rel) => edited(rel, { from_id: rel.to_id, to_id: rel.from_id }),
      '已反转关系方向。',
    )
  }

  async function deleteRelation(relationId: string): Promise<boolean> {
    const current = ready()
    if (current === null) return false
    if (findRelation(current, relationId) === null) return false
    return run(
      { kind: 'delete', relationId },
      async (scope) => {
        await api.remove(scope.courseId, relationId, { signal: scope.signal })
        return null
      },
      '已删除关系。',
      null,
    )
  }

  // ------------------------------------------------------------ 切课与重新加载
  watch(
    () => store.courseId,
    () => {
      pending.value = null
      saving.value = false
      inFlight = false
      error.value = null
      notice.value = null
      stale.value = false
      dismissConflict()
      fromId.value = null
      toId.value = null
    },
  )

  watch(
    () => store.graph,
    () => {
      stale.value = false
    },
  )

  onScopeDispose(() => {
    disposed = true
  })

  return {
    graph,
    canvasData,
    status,
    nodeOptions,
    relationRows,
    saving: saving as Readonly<Ref<boolean>>,
    error,
    notice,
    conflict: conflict as Readonly<Ref<CycleConflict | null>>,
    stale: stale as Readonly<Ref<boolean>>,
    highlightedNodeIds,
    highlightedRelationIds,
    fromId,
    toId,
    draftType,
    pickNode,
    swapDraft,
    dismissConflict,
    createRelation,
    changeType,
    reverseRelation,
    deleteRelation,
  }
}

export type RelationEditor = ReturnType<typeof useRelationEditor>
