import { computed, onScopeDispose, ref, shallowRef, watch, type Ref } from 'vue'
import type { CoursesApi } from '../api/courses'
import type { DraftGraphApi } from '../api/graph'
import { AbortedError, ApiError, NetworkError, TimeoutError } from '../api/http'
import type {
  KnowledgePointRef,
  Relation,
  ReviewAction,
  ReviewApi,
  ReviewCounts,
  ReviewItemKind,
  ReviewQueue,
  SuspectedDuplicate,
} from '../api/review'
import { useCourseStore, type CourseRequestScope } from '../stores/course'

/**
 * 教师审核队列页状态（H09，ADR-070）：三栏列表、键集分页、单项处理与疑似重复合并。
 *
 * - 只在课程内角色为教师时读队列（`Course.my_role`），同时读草稿图谱仅用于把关系两端的 ID 显示成名称；
 *   草稿读取失败不影响审核，名称退回 ID。
 * - **数量以服务端为准**：栏目标题的数量始终是服务端 `totals`（读队列或处理结果带回），不在本地加减，
 *   因此刷新页面后的数量与处理后显示的一致。
 * - **一次只处理一条**：任一写请求在途时所有处理按钮不可用，同一条连点只发一次；重复提交已生效的动作
 *   由服务端返回 `changed = false`，页面照常移除该条并提示「此前已处理」。
 * - 会影响其他栏的处理（拒绝关系、拒绝孤立知识点、合并）以及条目已不在队列（404）后，重新读取三栏第一页
 *   （条数不少于当前已加载的），不在本地猜测连带变化。
 * - 合并冲突：409 `CYCLE_DETECTED` 把 `details.cycle` 换成名称路径显示在该条下，条目保留；
 *   `COURSE_BUSY` 提示稍后重试；网络中断或超时无法确认结果时重新读取队列，以服务端为准。
 * - 错误只按错误码给固定文案，不回显服务端 message。迟到隔离沿用课程作用域 + 序号。
 */

export type ReviewStatus = 'idle' | 'loading' | 'not_teacher' | 'ready' | 'error'

export const REVIEW_KINDS: readonly ReviewItemKind[] = ['low_confidence_relation', 'suspected_duplicate', 'isolated_node']

/** 栏目 → 队列与 totals 中的字段名 */
export const KIND_FIELD = {
  low_confidence_relation: 'low_confidence_relations',
  suspected_duplicate: 'suspected_duplicates',
  isolated_node: 'isolated_nodes',
} as const satisfies Record<ReviewItemKind, keyof ReviewCounts>

export const KIND_LABELS: Readonly<Record<ReviewItemKind, string>> = {
  low_confidence_relation: '低置信度关系',
  suspected_duplicate: '疑似重复知识点',
  isolated_node: '孤立知识点',
}

export const DUPLICATE_REASON_LABELS: Readonly<Record<SuspectedDuplicate['reason'], string>> = {
  same_key: '名称归一后相同',
  alias: '名称或别名相同',
  containment: '一个名称是另一个的前缀',
}

export const PAGE_SIZE = 50
const MAX_LIMIT = 200

const FORBIDDEN_MESSAGE = '你无权访问该课程。'
const SESSION_EXPIRED_MESSAGE = '登录已失效，请重新登录。'
const NETWORK_MESSAGE = '无法连接服务器，请检查网络后重试。'
const INVALID_MESSAGE = '服务器返回的审核队列数据异常，请稍后重试。'
const GENERIC_MESSAGE = '审核队列加载失败，请稍后重试。'
const STORAGE_MESSAGE = '图数据库暂不可用，请稍后重试。'
const MORE_FAILED_MESSAGE = '加载更多失败，请重试。'
const REFRESH_FAILED_MESSAGE = '刷新审核队列失败，列表可能不是最新，请重新加载。'

export interface ReviewItems {
  low_confidence_relations: Relation[]
  suspected_duplicates: SuspectedDuplicate[]
  isolated_nodes: KnowledgePointRef[]
}

type Cursors = ReviewQueue['next_cursors']

/** 页面上可处理的一条审核项 */
export type ReviewTarget =
  | { kind: 'low_confidence_relation'; relation: Relation }
  | { kind: 'suspected_duplicate'; pair: SuspectedDuplicate }
  | { kind: 'isolated_node'; node: KnowledgePointRef }

export type ReviewVerb = 'approve' | 'reject' | 'merge'

export interface ItemError {
  key: string
  message: string
  /** 合并成环时的名称路径（首尾相同） */
  cycle: Array<{ kpId: string; name: string }> | null
}

export interface ReviewNotice {
  tone: 'success' | 'info' | 'error'
  text: string
}

export interface UseReviewOptions {
  coursesApi: Pick<CoursesApi, 'get'>
  reviewApi: ReviewApi
  /** 只用于显示名称；省略时关系两端显示 ID */
  graphApi?: DraftGraphApi
  /** 路由里的课程 ID；null 表示不在审核页 */
  courseId: Ref<string | null>
  onCourseForbidden?: () => void
}

// ---------------------------------------------------------------- 纯函数

export function duplicateKey(pair: Pick<SuspectedDuplicate, 'candidates'>): string {
  return `dup:${pair.candidates.map((c) => c.id).join('|')}`
}

export function itemKey(target: ReviewTarget): string {
  switch (target.kind) {
    case 'low_confidence_relation':
      return `rel:${target.relation.id}`
    case 'suspected_duplicate':
      return duplicateKey(target.pair)
    case 'isolated_node':
      return `iso:${target.node.id}`
  }
}

function isCount(value: unknown): value is number {
  return typeof value === 'number' && Number.isInteger(value) && value >= 0
}

export function isCounts(value: unknown): value is ReviewCounts {
  if (typeof value !== 'object' || value === null) return false
  const v = value as Record<string, unknown>
  return isCount(v.low_confidence_relations) && isCount(v.suspected_duplicates) && isCount(v.isolated_nodes)
}

function isRef(value: unknown): value is KnowledgePointRef {
  if (typeof value !== 'object' || value === null) return false
  const v = value as Record<string, unknown>
  return typeof v.id === 'string' && v.id !== '' && typeof v.name === 'string'
}

function isRelation(value: unknown): value is Relation {
  if (typeof value !== 'object' || value === null) return false
  const v = value as Record<string, unknown>
  return typeof v.id === 'string' && typeof v.from_id === 'string' && typeof v.to_id === 'string' && typeof v.type === 'string'
}

function isDuplicate(value: unknown): value is SuspectedDuplicate {
  if (typeof value !== 'object' || value === null) return false
  const v = value as Record<string, unknown>
  return Array.isArray(v.candidates) && v.candidates.length === 2 && v.candidates.every(isRef) && typeof v.similarity === 'number'
}

/** 队列响应的形状校验：三栏为数组、条目可识别、totals 与游标齐全 */
export function isQueue(value: unknown): value is ReviewQueue {
  if (typeof value !== 'object' || value === null) return false
  const v = value as Record<string, unknown>
  if (!Array.isArray(v.low_confidence_relations) || !v.low_confidence_relations.every(isRelation)) return false
  if (!Array.isArray(v.suspected_duplicates) || !v.suspected_duplicates.every(isDuplicate)) return false
  if (!Array.isArray(v.isolated_nodes) || !v.isolated_nodes.every(isRef)) return false
  if (!isCounts(v.totals)) return false
  const c = v.next_cursors as Record<string, unknown> | null | undefined
  if (typeof c !== 'object' || c === null) return false
  return Object.values(KIND_FIELD).every((f) => c[f] === null || (typeof c[f] === 'string' && c[f] !== ''))
}

function readCycle(details: Record<string, unknown> | undefined): string[] | null {
  const cycle = details?.cycle
  if (!Array.isArray(cycle) || cycle.length < 2) return null
  return cycle.every((id): id is string => typeof id === 'string' && id !== '') ? cycle : null
}

const EMPTY_COUNTS: ReviewCounts = { low_confidence_relations: 0, suspected_duplicates: 0, isolated_nodes: 0 }
const EMPTY_CURSORS: Cursors = { low_confidence_relations: null, suspected_duplicates: null, isolated_nodes: null }
const emptyItems = (): ReviewItems => ({ low_confidence_relations: [], suspected_duplicates: [], isolated_nodes: [] })

function successText(target: ReviewTarget, verb: ReviewVerb, changed: boolean): string {
  if (!changed) return '该条此前已处理，未重复写入。'
  switch (target.kind) {
    case 'low_confidence_relation':
      return verb === 'approve' ? '已通过该关系。' : '已拒绝该关系，发布时不会包含它。'
    case 'suspected_duplicate':
      return verb === 'merge' ? '已合并两个知识点，关系与来源已并入主知识点。' : '已标记为不是重复，这一对不再出现。'
    case 'isolated_node':
      return verb === 'approve' ? '已确认保留该知识点。' : '已拒绝该知识点，发布时不会包含它。'
  }
}

// ---------------------------------------------------------------- 组合式

export function useReview({ coursesApi, reviewApi, graphApi, courseId, onCourseForbidden }: UseReviewOptions) {
  const store = useCourseStore()
  const status = ref<ReviewStatus>('idle')
  const error = ref<string | null>(null)
  const retryable = ref(false)
  const courseName = ref<string | null>(null)
  const items = shallowRef<ReviewItems>(emptyItems())
  const totals = shallowRef<ReviewCounts>(EMPTY_COUNTS)
  const cursors = shallowRef<Cursors>(EMPTY_CURSORS)
  const names = shallowRef<ReadonlyMap<string, string>>(new Map())
  const loadingMore = ref<ReviewItemKind | null>(null)
  const moreError = ref<{ kind: ReviewItemKind; message: string } | null>(null)
  const refreshing = ref(false)
  const refreshError = ref<string | null>(null)
  /** 在途写请求对应的条目 */
  const busyKey = ref<string | null>(null)
  const itemError = shallowRef<ItemError | null>(null)
  const notice = shallowRef<ReviewNotice | null>(null)
  /** 正在选择主知识点的疑似重复：键与所选主节点 */
  const mergeDraft = shallowRef<{ key: string; primaryId: string } | null>(null)

  const allEmpty = computed(
    () =>
      status.value === 'ready' &&
      totals.value.low_confidence_relations === 0 &&
      totals.value.suspected_duplicates === 0 &&
      totals.value.isolated_nodes === 0,
  )

  let seq = 0 // 整页加载
  let readSeq = 0 // 刷新与加载更多
  let writeSeq = 0
  const controllers = new Set<AbortController>()
  let disposed = false

  function abortAll(): void {
    for (const c of controllers) c.abort()
    controllers.clear()
  }

  /** 取课程作用域并把它的中止联到本次请求 */
  function begin(): { scope: CourseRequestScope; own: AbortController; release: () => void } {
    const scope = store.beginRequest()
    const own = new AbortController()
    controllers.add(own)
    const onScopeAbort = () => own.abort(scope.signal.reason)
    if (scope.signal.aborted) own.abort(scope.signal.reason)
    else scope.signal.addEventListener('abort', onScopeAbort, { once: true })
    const release = () => {
      scope.signal.removeEventListener('abort', onScopeAbort)
      controllers.delete(own)
    }
    return { scope, own, release }
  }

  function reset(next: ReviewStatus): void {
    status.value = next
    error.value = null
    retryable.value = false
    items.value = emptyItems()
    totals.value = EMPTY_COUNTS
    cursors.value = EMPTY_CURSORS
    names.value = new Map()
    loadingMore.value = null
    moreError.value = null
    refreshing.value = false
    refreshError.value = null
    busyKey.value = null
    itemError.value = null
    notice.value = null
    mergeDraft.value = null
  }

  function fail(message: string, canRetry: boolean): void {
    reset('error')
    error.value = message
    retryable.value = canRetry
  }

  /** 会话、课程访问类错误：整页处理；返回 true 表示已处理 */
  function handleAccess(cause: unknown): boolean {
    if (!(cause instanceof ApiError)) return false
    if (cause.code === 'COURSE_FORBIDDEN') {
      fail(FORBIDDEN_MESSAGE, false)
      store.selectCourse(null)
      onCourseForbidden?.()
      return true
    }
    if (cause.code === 'ROLE_FORBIDDEN') {
      reset('not_teacher')
      return true
    }
    if (cause.status === 401) {
      fail(SESSION_EXPIRED_MESSAGE, false)
      return true
    }
    return false
  }

  function applyQueue(queue: ReviewQueue): void {
    items.value = {
      low_confidence_relations: [...queue.low_confidence_relations],
      suspected_duplicates: [...queue.suspected_duplicates],
      isolated_nodes: [...queue.isolated_nodes],
    }
    totals.value = { ...queue.totals }
    cursors.value = { ...queue.next_cursors }
  }

  async function readNames(cid: string, signal: AbortSignal): Promise<ReadonlyMap<string, string> | null> {
    if (graphApi === undefined) return null
    try {
      const graph = await graphApi.getDraft(cid, { signal })
      if (graph?.course_id !== cid || !Array.isArray(graph.nodes)) return null
      return new Map(graph.nodes.map((n) => [n.id, n.name]))
    } catch {
      return null // 名称只是显示辅助，读不到退回 ID
    }
  }

  async function load(cid: string | null): Promise<void> {
    seq += 1
    readSeq += 1
    writeSeq += 1
    abortAll()
    courseName.value = null
    if (disposed || cid === null) {
      reset('idle')
      return
    }
    store.selectCourse(cid)
    const token = seq
    const { scope, own, release } = begin()
    const current = () => !disposed && token === seq && scope.isCurrent()

    reset('loading')
    try {
      const course = await coursesApi.get(cid, { signal: own.signal })
      if (!current()) return
      if (course?.id !== cid) return fail(INVALID_MESSAGE, true)
      courseName.value = course.name
      if (course.my_role !== 'teacher') return reset('not_teacher')

      const [queue, nameMap] = await Promise.all([
        reviewApi.getQueue(cid, { limit: PAGE_SIZE }, { signal: own.signal }),
        readNames(cid, own.signal),
      ])
      if (!current()) return
      if (!isQueue(queue)) return fail(INVALID_MESSAGE, true)
      store.commit(scope, () => {
        applyQueue(queue)
        names.value = nameMap ?? new Map()
        status.value = 'ready'
      })
    } catch (cause) {
      if (!current() || cause instanceof AbortedError) return
      if (handleAccess(cause)) return
      if (cause instanceof ApiError) return fail(cause.status === 503 ? STORAGE_MESSAGE : GENERIC_MESSAGE, cause.status >= 500)
      if (cause instanceof NetworkError || cause instanceof TimeoutError) return fail(NETWORK_MESSAGE, true)
      fail(INVALID_MESSAGE, true)
    } finally {
      release()
    }
  }

  /**
   * 重新读取三栏第一页（条数不少于当前已加载的，上限 200）与名称：处理后其他栏可能连带变化。
   * 失败保留当前列表并提示；新的刷新、加载更多或整页加载会作废本次。
   */
  async function refresh(): Promise<void> {
    const cid = courseId.value
    if (disposed || cid === null || status.value !== 'ready') return
    readSeq += 1
    const token = readSeq
    const pageToken = seq
    const loaded = Math.max(...Object.values(items.value).map((list: unknown[]) => list.length))
    const limit = Math.min(MAX_LIMIT, Math.max(PAGE_SIZE, loaded))
    const { scope, own, release } = begin()
    const current = () => !disposed && token === readSeq && pageToken === seq && scope.isCurrent()
    refreshing.value = true
    refreshError.value = null
    loadingMore.value = null
    moreError.value = null
    try {
      const [queue, nameMap] = await Promise.all([
        reviewApi.getQueue(cid, { limit }, { signal: own.signal }),
        readNames(cid, own.signal),
      ])
      if (!current()) return
      if (!isQueue(queue)) {
        refreshError.value = REFRESH_FAILED_MESSAGE
        return
      }
      store.commit(scope, () => {
        applyQueue(queue)
        if (nameMap !== null) names.value = nameMap
        if (mergeDraft.value !== null && !queue.suspected_duplicates.some((p) => duplicateKey(p) === mergeDraft.value?.key)) {
          mergeDraft.value = null
        }
      })
    } catch (cause) {
      if (!current() || cause instanceof AbortedError) return
      if (handleAccess(cause)) return
      refreshError.value = REFRESH_FAILED_MESSAGE
    } finally {
      if (token === readSeq) refreshing.value = false
      release()
    }
  }

  /** 该栏下一页：追加并去重，数量取响应的 totals */
  async function loadMore(kind: ReviewItemKind): Promise<void> {
    const cid = courseId.value
    const field = KIND_FIELD[kind]
    const cursor = cursors.value[field]
    if (disposed || cid === null || status.value !== 'ready' || cursor === null || refreshing.value) return
    readSeq += 1
    const token = readSeq
    const pageToken = seq
    const { scope, own, release } = begin()
    const current = () => !disposed && token === readSeq && pageToken === seq && scope.isCurrent()
    loadingMore.value = kind
    moreError.value = null
    try {
      const page = await reviewApi.getQueue(cid, { kind, cursor, limit: PAGE_SIZE }, { signal: own.signal })
      if (!current()) return
      if (!isQueue(page)) {
        moreError.value = { kind, message: MORE_FAILED_MESSAGE }
        return
      }
      store.commit(scope, () => {
        const next = { ...items.value }
        if (kind === 'low_confidence_relation') {
          const seen = new Set(next.low_confidence_relations.map((r) => r.id))
          next.low_confidence_relations = [...next.low_confidence_relations, ...page.low_confidence_relations.filter((r) => !seen.has(r.id))]
        } else if (kind === 'suspected_duplicate') {
          const seen = new Set(next.suspected_duplicates.map(duplicateKey))
          next.suspected_duplicates = [...next.suspected_duplicates, ...page.suspected_duplicates.filter((p) => !seen.has(duplicateKey(p)))]
        } else {
          const seen = new Set(next.isolated_nodes.map((n) => n.id))
          next.isolated_nodes = [...next.isolated_nodes, ...page.isolated_nodes.filter((n) => !seen.has(n.id))]
        }
        items.value = next
        totals.value = { ...page.totals }
        cursors.value = { ...cursors.value, [field]: page.next_cursors[field] }
      })
    } catch (cause) {
      if (!current() || cause instanceof AbortedError) return
      if (handleAccess(cause)) return
      // 游标失效（422）：从第一页重新读
      if (cause instanceof ApiError && cause.status === 422) {
        loadingMore.value = null
        void refresh()
        return
      }
      moreError.value = { kind, message: MORE_FAILED_MESSAGE }
    } finally {
      if (token === readSeq) loadingMore.value = null
      release()
    }
  }

  function removeLocally(key: string): void {
    const next = { ...items.value }
    next.low_confidence_relations = next.low_confidence_relations.filter((r) => `rel:${r.id}` !== key)
    next.suspected_duplicates = next.suspected_duplicates.filter((p) => duplicateKey(p) !== key)
    next.isolated_nodes = next.isolated_nodes.filter((n) => `iso:${n.id}` !== key)
    items.value = next
  }

  function nameOf(kpId: string): string {
    return names.value.get(kpId) ?? kpId
  }

  function toAction(target: ReviewTarget, verb: ReviewVerb, primaryId?: string): ReviewAction | null {
    switch (target.kind) {
      case 'low_confidence_relation':
        if (verb === 'merge') return null
        return { item: target.kind, rel_id: target.relation.id, action: verb }
      case 'isolated_node':
        if (verb === 'merge') return null
        return { item: target.kind, kp_id: target.node.id, action: verb }
      case 'suspected_duplicate': {
        const kpIds = target.pair.candidates.map((c) => c.id)
        if (verb === 'approve') return null
        if (verb === 'reject') return { item: target.kind, kp_ids: kpIds, action: 'reject' }
        if (primaryId === undefined || !kpIds.includes(primaryId)) return null
        return { item: target.kind, kp_ids: kpIds, action: 'merge', primary_id: primaryId }
      }
    }
  }

  /** 这次处理是否可能让其他栏连带变化 */
  function affectsOthers(target: ReviewTarget, verb: ReviewVerb): boolean {
    if (verb === 'merge') return true
    return verb === 'reject' && target.kind !== 'suspected_duplicate'
  }

  async function resolve(target: ReviewTarget, verb: ReviewVerb, primaryId?: string): Promise<void> {
    const cid = courseId.value
    if (disposed || cid === null || status.value !== 'ready' || busyKey.value !== null) return
    const action = toAction(target, verb, primaryId)
    if (action === null) return
    const key = itemKey(target)
    writeSeq += 1
    const token = writeSeq
    const pageToken = seq
    // 在途的刷新/加载更多基于处理前的队列，作废
    readSeq += 1
    refreshing.value = false
    loadingMore.value = null
    const { scope, own, release } = begin()
    const current = () => !disposed && token === writeSeq && pageToken === seq && scope.isCurrent()
    busyKey.value = key
    itemError.value = null
    notice.value = null
    let reread = false
    try {
      const result = await reviewApi.resolve(cid, action, { signal: own.signal })
      if (!current()) return
      store.commit(scope, () => {
        removeLocally(key)
        if (isCounts(result?.totals)) totals.value = { ...result.totals }
        else reread = true
        if (mergeDraft.value?.key === key) mergeDraft.value = null
        const changed = result?.changed !== false
        notice.value = { tone: changed ? 'success' : 'info', text: successText(target, verb, changed) }
        if (changed && affectsOthers(target, verb)) reread = true
      })
    } catch (cause) {
      if (!current() || cause instanceof AbortedError) return
      if (handleAccess(cause)) return
      reread = handleWriteError(cause, key)
    } finally {
      if (token === writeSeq) busyKey.value = null
      release()
    }
    if (reread && current()) await refresh()
  }

  /** 写失败：返回是否需要重新读取队列 */
  function handleWriteError(cause: unknown, key: string): boolean {
    const itemFail = (message: string, cycle: ItemError['cycle'] = null) => {
      itemError.value = { key, message, cycle }
    }
    if (cause instanceof NetworkError || cause instanceof TimeoutError) {
      notice.value = { tone: 'error', text: '网络中断，无法确认这条是否已处理，已重新读取队列，请以列表为准。' }
      return true
    }
    if (!(cause instanceof ApiError)) {
      notice.value = { tone: 'error', text: '服务器返回的处理结果异常，已重新读取队列，请以列表为准。' }
      return true
    }
    switch (cause.code) {
      case 'NOT_FOUND':
        removeLocally(key)
        if (mergeDraft.value?.key === key) mergeDraft.value = null
        notice.value = { tone: 'info', text: '该条已不在队列中（可能已被他人处理或知识点已删除），已刷新队列。' }
        return true
      case 'CYCLE_DETECTED': {
        const cycle = readCycle(cause.details)
        itemFail(
          '合并后前置关系会成环，未合并。请先在图谱编辑页调整下列前置关系，或标记为不是重复。',
          cycle === null ? null : cycle.map((kpId) => ({ kpId, name: nameOf(kpId) })),
        )
        return false
      }
      case 'REVISION_CONFLICT':
        itemFail('相关知识点刚被修改，未处理。已刷新队列，请核对后重试。')
        return true
      case 'COURSE_BUSY':
        itemFail('课程正在处理其他修改，请稍后重试。')
        return false
      case 'VALIDATION_ERROR':
        itemFail('这条审核项的数据已变化，未处理。已刷新队列，请重试。')
        return true
      default:
        itemFail(cause.status === 503 ? STORAGE_MESSAGE : '处理失败，请稍后重试。')
        return false
    }
  }

  function startMerge(pair: SuspectedDuplicate): void {
    if (busyKey.value !== null) return
    const first = pair.candidates[0]
    if (first === undefined) return
    mergeDraft.value = { key: duplicateKey(pair), primaryId: first.id }
    if (itemError.value?.key === duplicateKey(pair)) itemError.value = null
  }

  function choosePrimary(primaryId: string): void {
    if (mergeDraft.value !== null) mergeDraft.value = { ...mergeDraft.value, primaryId }
  }

  function cancelMerge(): void {
    mergeDraft.value = null
  }

  async function confirmMerge(pair: SuspectedDuplicate): Promise<void> {
    const draft = mergeDraft.value
    if (draft === null || draft.key !== duplicateKey(pair)) return
    await resolve({ kind: 'suspected_duplicate', pair }, 'merge', draft.primaryId)
  }

  // 其他页面清空了课程上下文（COURSE_FORBIDDEN、会话过期）
  watch(
    () => store.courseId,
    (id) => {
      if (id !== null || courseId.value === null || status.value !== 'ready') return
      seq += 1
      abortAll()
      fail('课程上下文已失效，请重新加载或返回课程列表。', true)
    },
  )

  watch(courseId, (cid) => void load(cid))
  void load(courseId.value)

  onScopeDispose(() => {
    disposed = true
    abortAll()
  })

  return {
    status,
    error,
    retryable,
    courseName,
    items,
    totals,
    cursors,
    allEmpty,
    loadingMore,
    moreError,
    refreshing,
    refreshError,
    busyKey,
    itemError,
    notice,
    dismissNotice: () => { notice.value = null },
    mergeDraft,
    nameOf,
    reload: () => void load(courseId.value),
    refresh: () => refresh(),
    loadMore: (kind: ReviewItemKind) => loadMore(kind),
    resolve: (target: ReviewTarget, verb: ReviewVerb, primaryId?: string) => resolve(target, verb, primaryId),
    startMerge,
    choosePrimary,
    cancelMerge,
    confirmMerge: (pair: SuspectedDuplicate) => confirmMerge(pair),
  }
}
