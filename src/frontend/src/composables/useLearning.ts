import { computed, onScopeDispose, ref, shallowRef, toValue, watch, type MaybeRefOrGetter } from 'vue'
import type { ProgressApi, ProgressEntry, ProgressResponse, MasteryStatus } from '../api/progress'
import type { Recommendation, RecommendApi, RecommendResponse } from '../api/recommend'
import { AbortedError, ApiError, NetworkError, TimeoutError } from '../api/http'
import { buildLearningPath, pathInputFromCanvas, type LearningPath, type PathRole } from '../graph/learningPath'
import type { CanvasElementState, GraphCanvasData } from '../graph/lifecycle'
import { useCourseStore, type CourseRequestScope } from '../stores/course'

/**
 * 掌握标记与下一步推荐的学生页状态（I06，ADR-075）。
 *
 * - 只读、只写**当前显示的已发布版本**：`graphVersion` 为 null（草稿页、未发布、教师视图）时
 *   既不读进度也打印记；进度与推荐响应的 `graph_version` 与显示版本不一致时一律丢弃并请求重载图谱
 *   （`specs/learning-path.md` §5：读请求一旦绑定版本就不混算）。
 * - **乐观标记 + 失败完整回滚**：点击先本地写入新状态，`PUT` 成功后以服务端重新投影的
 *   `ProgressResponse.entries` 为准；网络/超时/4xx/5xx 一律回滚到写前的服务端已知状态，只给按错误码
 *   固定的文案，绝不回显服务端 `message`。422 `not_in_published_version`（草稿独有/已删除/他课、
 *   或写入期间发布指针变化）撤销乐观状态后重新读进度与推荐。
 * - **同一时刻最多一个在途写入**：连点第二次起直接返回，页面按 `busyKpId` 禁用按钮。
 * - **切课隔离**：沿用 `CourseRequestScope` + 请求序号，迟到的课程 A 响应不写入课程 B 的界面。
 * - 推荐理由只展示服务端 `reason` 与 `reason_facts`/`weighted` 字段，前端不自行计算分量、不把权重乘出分数
 *   （`Recommendations.vue` 与 `reasonFactRows`）。
 * - 未注入学习接口（`progressApi`/`recommendApi` 为 null）时本组合式完全不发请求，页面保持 H11 原状。
 */

export type LearningStatus = 'idle' | 'loading' | 'not_student' | 'unpublished' | 'ready' | 'error'

export interface LearningNotice {
  tone: 'success' | 'info' | 'error'
  text: string
}

export interface ReasonFactRow {
  key: string
  label: string
  value: string
  /** L14：该值是缺失属性时的中性值 0.5（ADR-014 修订 1 决定 5），展示为「未标注」而不是测量值 */
  labelledDefault?: boolean
}

export const MASTERY_LABELS: Readonly<Record<MasteryStatus, string>> = Object.freeze({
  unknown: '未学习',
  learning: '学习中',
  mastered: '已掌握',
})

/** 服务端 `reason_facts.primary_factor` 的中文名；前端只做展示映射，不据此重算贡献 */
export const PRIMARY_FACTOR_LABELS: Readonly<Record<Recommendation['reason_facts']['primary_factor'], string>> = Object.freeze({
  unlock: '解锁后继',
  importance: '重要度',
  chapter_order: '章节顺序',
  ease: '易学度',
})

const FORBIDDEN_MESSAGE = '你无权访问该课程。'
const SESSION_EXPIRED_MESSAGE = '登录已失效，请重新登录。'
const NETWORK_MESSAGE = '无法连接服务器，请检查网络后重试。'
const INVALID_MESSAGE = '服务器返回的学习进度数据异常，请稍后重试。'
const GENERIC_MESSAGE = '学习进度加载失败，请稍后重试。'
const INTEGRITY_MESSAGE = '课程图谱数据完整性异常，暂时无法显示进度与推荐。'
const RECOMMEND_FAILED_MESSAGE = '推荐加载失败，请稍后重试。'
const RECOMMEND_NETWORK_MESSAGE = '无法连接服务器，推荐加载失败请稍后重试。'
const RECOMMEND_INVALID_MESSAGE = '服务器返回的推荐数据异常，请稍后重试。'
const WRITE_FAILED_MESSAGE = '标记保存失败，已撤销本次标记，请稍后重试。'
const WRITE_INVALID_MESSAGE = '服务器返回的进度数据异常，已撤销本次标记，请稍后重试。'
const NOT_IN_VERSION_MESSAGE = '该知识点已不在当前发布版本中，已撤销标记并刷新进度。'
const VERSION_STALE_MESSAGE = '课程图谱已发布新版本，请重新加载后再继续。'

const MASTERY: ReadonlySet<string> = new Set(['unknown', 'learning', 'mastered'])

// ---------------------------------------------------------------- 纯函数

/** 掌握状态 → 画布元素状态；推荐项额外叠加 `recommended`。颜色只在 `graph/lifecycle.ts` 定义 */
export function masteryElementStates(status: MasteryStatus, recommended: boolean): CanvasElementState[] {
  const base: CanvasElementState = status === 'mastered' ? 'mastered' : status === 'learning' ? 'learning' : 'notStarted'
  return recommended ? [base, 'recommended'] : [base]
}

const PATH_NODE_STATE: Readonly<Partial<Record<PathRole, CanvasElementState>>> = Object.freeze({
  prereqMissing: 'pathPrereq',
  unlocks: 'pathUnlock',
  dimmed: 'dimmed',
})

/**
 * 纯函数：把服务端投影的掌握状态与推荐集合落到节点状态上，不修改输入。
 * 保留筛选层已有的状态（如 `selected`），输出节点是新对象。
 *
 * L14：给出 `path` 且有焦点时再叠加学习路径——推荐项带序号（`data.pathOrder`），缺失前置/之后解锁/无关节点
 * 分别带 `pathPrereq`/`pathUnlock`/`dimmed`（选中的节点不淡化），路径上的先修边 `pathEdge`、其余边 `dimmed`。
 * 没有焦点（全部掌握、无推荐）时不叠加任何路径状态，避免整图变灰。
 */
export function applyLearningStates(
  graph: GraphCanvasData,
  entries: ReadonlyMap<string, ProgressEntry>,
  recommendedIds: ReadonlySet<string>,
  path: LearningPath | null = null,
): GraphCanvasData {
  const active = path !== null && path.focus !== null
  return {
    nodes: graph.nodes.map((node) => {
      const kpId = node.data.kpId
      const status = entries.get(kpId)?.status ?? 'unknown'
      const own = node.states ?? []
      const learning = masteryElementStates(status, recommendedIds.has(kpId))
      if (!active) {
        // 学习状态是底色，筛选/选中状态叠加在后（后者优先），与 `buildGraphOptions` 的 states 顺序一致
        return { ...node, states: [...learning, ...own] }
      }
      const role = path.roles.get(kpId) ?? 'dimmed'
      const pathState = role === 'dimmed' && own.includes('selected') ? undefined : PATH_NODE_STATE[role]
      const order = path.order.get(kpId)
      return {
        ...node,
        data: order === undefined ? node.data : { ...node.data, pathOrder: order },
        states: [...learning, ...(pathState === undefined ? [] : [pathState]), ...own],
      }
    }),
    edges: active
      ? graph.edges.map((edge) => ({
          ...edge,
          states: [...(edge.states ?? []), path.edges.has(edge.data.relationId) ? 'pathEdge' : 'dimmed'],
        }))
      : graph.edges,
  }
}

/** 展示用舍入：只有前端展示时舍入，wire 的未舍入值不参与任何重算（`specs/learning-path.md` §3） */
export function formatFactor(value: number): string {
  return Number.isFinite(value) ? value.toFixed(4) : String(value)
}

/** 缺失属性标志取自服务端，不根据数值 0.5 猜测缺失（ADR-087）。 */
export const NEUTRAL_ATTRIBUTE = 0.5
const UNLABELLED_TEXT = '未标注（按中性值 0.5 排序）'

function attributeRow(key: string, label: string, value: number, defaulted?: boolean): ReasonFactRow {
  const labelledDefault = defaulted === true
  return { key, label, value: labelledDefault ? UNLABELLED_TEXT : formatFactor(value), labelledDefault }
}

/** 理由的结构化事实行：逐条取自服务端 `reason_facts`，不做任何换算 */
export function reasonFactRows(item: Recommendation): ReasonFactRow[] {
  const facts = item.reason_facts
  return [
    { key: 'unlock_count', label: '可立即解锁', value: `${item.unlock_count} 个` },
    attributeRow('importance', '重要度', facts.importance, facts.importance_defaulted),
    { key: 'centrality', label: '中心度', value: formatFactor(facts.centrality) },
    attributeRow('difficulty', '难度', facts.difficulty, facts.difficulty_defaulted),
    { key: 'chapter', label: '章节', value: facts.chapter_name === null ? '未分章' : `${facts.chapter_name}（秩 ${facts.chapter_rank}）` },
    { key: 'primary_factor', label: '主要理由', value: PRIMARY_FACTOR_LABELS[facts.primary_factor] },
  ]
}

/** L14：「已掌握：A、B → 还需先学：X → 下一步：C → 之后解锁：D、E」；空段省略，没有下一步时为空串 */
export function pathLine(narrative: LearningPath['narrative']): string {
  if (narrative.next.length === 0) return ''
  const parts: string[] = []
  if (narrative.mastered.length > 0) parts.push(`已掌握：${narrative.mastered.join('、')}`)
  if (narrative.missing.length > 0) parts.push(`还需先学：${narrative.missing.join('、')}`)
  parts.push(`下一步：${narrative.next.join('、')}`)
  if (narrative.unlocks.length > 0) parts.push(`之后解锁：${narrative.unlocks.join('、')}`)
  return parts.join(' → ')
}

/** 服务端的四类加权分量与总分：原样展示，不用 `factors` 乘权重重算 */
export function weightedFactRows(item: Recommendation): ReasonFactRow[] {
  return [
    { key: 'weighted_unlock', label: '加权解锁度', value: formatFactor(item.weighted.unlock) },
    { key: 'weighted_importance', label: '加权重要度', value: formatFactor(item.weighted.importance) },
    { key: 'weighted_chapter_order', label: '加权章节顺序', value: formatFactor(item.weighted.chapter_order) },
    { key: 'weighted_ease', label: '加权易学度', value: formatFactor(item.weighted.ease) },
    { key: 'score', label: '得分', value: formatFactor(item.score) },
  ]
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function isPositiveInt(value: unknown): value is number {
  return typeof value === 'number' && Number.isInteger(value) && value >= 1
}

function isEntry(value: unknown): value is ProgressEntry {
  if (!isRecord(value)) return false
  if (typeof value.kp_id !== 'string' || value.kp_id === '') return false
  if (typeof value.status !== 'string' || !MASTERY.has(value.status)) return false
  return Array.isArray(value.inherited_from)
}

/** 进度响应形状校验：`graph_version` 为正整数、`entries` 为数组且每项可识别 */
export function isProgressResponse(value: unknown): value is ProgressResponse {
  if (!isRecord(value) || !isPositiveInt(value.graph_version)) return false
  return Array.isArray(value.entries) && value.entries.length > 0 && value.entries.every(isEntry)
}

function isRecommendation(value: unknown): value is Recommendation {
  if (!isRecord(value)) return false
  if (typeof value.kp_id !== 'string' || value.kp_id === '') return false
  if (typeof value.name !== 'string' || typeof value.reason !== 'string') return false
  if (typeof value.score !== 'number' || typeof value.unlock_count !== 'number') return false
  if (!isRecord(value.factors) || !isRecord(value.weighted) || !isRecord(value.reason_facts)) return false
  return typeof value.reason_facts.primary_factor === 'string' && value.reason_facts.primary_factor in PRIMARY_FACTOR_LABELS
}

/** 推荐响应形状校验：`state` 闭集只有 `recommendations` 与 `all_mastered`（不存在 `no_graph`） */
export function isRecommendResponse(value: unknown): value is RecommendResponse {
  if (!isRecord(value) || !isPositiveInt(value.graph_version)) return false
  if (typeof value.total_eligible !== 'number' || !Array.isArray(value.recommendations)) return false
  if (value.state !== 'recommendations' && value.state !== 'all_mastered') return false
  return value.recommendations.every(isRecommendation)
}

/** `PUT /progress` 的 422：目标不在请求事务所见的当前发布版（ADR-017 决定 5） */
export function hasNotInPublishedVersion(cause: ApiError): boolean {
  const fields = cause.details?.fields
  if (!Array.isArray(fields)) return false
  return fields.some((field) => isRecord(field) && field.reason === 'not_in_published_version')
}

function integrityMessage(cause: ApiError): string {
  const requestId = cause.details?.request_id
  return typeof requestId === 'string' && requestId !== ''
    ? `${INTEGRITY_MESSAGE}（请求编号 ${requestId}）`
    : INTEGRITY_MESSAGE
}

function toEntryMap(entries: readonly ProgressEntry[]): ReadonlyMap<string, ProgressEntry> {
  return new Map(entries.map((item) => [item.kp_id, item]))
}

function optimisticEntry(previous: ProgressEntry | undefined, kpId: string, status: MasteryStatus): ProgressEntry {
  return {
    kp_id: kpId,
    status,
    own_status: status,
    // 乐观状态不改继承来源：服务端成功响应会带回权威投影
    inherited_from: previous?.inherited_from ?? [],
    updated_at: new Date().toISOString(),
  }
}

function recommendFailureText(cause: unknown): string {
  if (cause instanceof NetworkError || cause instanceof TimeoutError) return RECOMMEND_NETWORK_MESSAGE
  if (cause instanceof ApiError) return RECOMMEND_FAILED_MESSAGE
  return RECOMMEND_INVALID_MESSAGE
}

function successText(status: MasteryStatus): string {
  if (status === 'mastered') return '已标记为已掌握。'
  if (status === 'learning') return '已标记为学习中。'
  return '已标记为未学习。'
}

// ---------------------------------------------------------------- 组合式

export interface UseLearningOptions {
  /** 未注入时为 null：本组合式完全不发请求，页面保持 H11 原状 */
  progressApi: ProgressApi | null
  recommendApi: RecommendApi | null
  /** 路由里的课程 ID；null 表示不在学生图谱页 */
  courseId: MaybeRefOrGetter<string | null>
  /** 当前显示的已发布版本号；null 表示尚无绑定版本（不读也不写） */
  graphVersion: MaybeRefOrGetter<number | null>
  /** 图谱是否已就绪（通常是 `useStudentGraph().status === 'ready'`） */
  ready: MaybeRefOrGetter<boolean>
  /** 交给画布的可见图（筛选层输出）；提供时组合式同时给出落好状态色的图 */
  graph?: MaybeRefOrGetter<GraphCanvasData | null>
  /** L14：计算学习路径用的完整已发布图（不受筛选影响，被筛掉的前置仍算数）；缺省用 `graph` */
  pathGraph?: MaybeRefOrGetter<GraphCanvasData | null>
  /** L14：希望解释的推荐项（通常是选中项）；不是推荐项时退回第一个推荐项 */
  focus?: MaybeRefOrGetter<string | null>
  onCourseForbidden?: () => void
  /** 显示版本与服务端绑定版本不一致：由页面重新加载图谱与进度 */
  onVersionStale?: () => void
}

export function useLearning({
  progressApi,
  recommendApi,
  courseId,
  graphVersion,
  ready,
  graph,
  pathGraph,
  focus,
  onCourseForbidden,
  onVersionStale,
}: UseLearningOptions) {
  const store = useCourseStore()
  const enabled = progressApi !== null && recommendApi !== null
  const cid = computed(() => toValue(courseId))
  const boundVersion = computed(() => toValue(graphVersion))
  const active = computed(() => enabled && toValue(ready) && cid.value !== null && boundVersion.value !== null)

  const status = ref<LearningStatus>('idle')
  const error = ref<string | null>(null)
  const retryable = ref(false)
  const entries = shallowRef<ReadonlyMap<string, ProgressEntry>>(new Map())
  const recommend = shallowRef<RecommendResponse | null>(null)
  const recommendError = ref<string | null>(null)
  const recommendLoading = ref(false)
  const busyKpId = ref<string | null>(null)
  const notice = shallowRef<LearningNotice | null>(null)
  const versionStale = ref(false)

  const recommendations = computed<Recommendation[]>(() =>
    recommend.value?.state === 'recommendations' ? recommend.value.recommendations : [],
  )
  const recommendState = computed<RecommendResponse['state'] | null>(() => recommend.value?.state ?? null)
  const totalEligible = computed(() => recommend.value?.total_eligible ?? 0)
  const recommendedIds = computed<ReadonlySet<string>>(() => new Set(recommendations.value.map((item) => item.kp_id)))

  /** L14：基于完整已发布图、服务端掌握投影与推荐顺序的学习路径；未就绪时为 null */
  const pathSource = computed(() => {
    const full = pathGraph === undefined ? null : toValue(pathGraph)
    return full ?? (graph === undefined ? null : toValue(graph))
  })
  const pathInput = computed(() => (pathSource.value === null ? null : pathInputFromCanvas(pathSource.value)))
  const learningPath = computed<LearningPath | null>(() => {
    const input = pathInput.value
    if (!enabled || input === null || status.value !== 'ready') return null
    const mastery = new Map([...entries.value].map(([id, entry]) => [id, entry.status]))
    return buildLearningPath(input.nodes, input.edges, mastery, recommendations.value, focus === undefined ? null : toValue(focus))
  })

  /** 落好掌握状态色、推荐高亮与学习路径的可见图；未启用学习功能时原样返回（保持 H11 行为与对象标识） */
  const learningGraph = computed<GraphCanvasData | null>(() => {
    const source = graph === undefined ? null : toValue(graph)
    if (source === null) return null
    if (!enabled) return source
    return applyLearningStates(source, entries.value, recommendedIds.value, learningPath.value)
  })

  let seq = 0
  let recSeq = 0
  let writeSeq = 0
  const controllers = new Set<AbortController>()
  let disposed = false
  /**
   * 是否已经请求过页面重载图谱。发布版本不一致时只重载一次，直到某次读到的版本与显示版本一致才复位，
   * 避免「服务端版本始终落后/超前」时形成重载死循环（`load` 里版本一致的分支复位）。
   */
  let stalePending = false

  function abortAll(): void {
    for (const controller of controllers) controller.abort()
    controllers.clear()
  }

  /** 取课程作用域并把它的中止联到本次请求（照抄 `useReview` 的迟到隔离） */
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

  function reset(next: LearningStatus): void {
    status.value = next
    error.value = null
    retryable.value = false
    entries.value = new Map()
    recommend.value = null
    recommendError.value = null
    recommendLoading.value = false
    busyKpId.value = null
    notice.value = null
    versionStale.value = false
  }

  function fail(message: string, canRetry: boolean): void {
    reset('error')
    error.value = message
    retryable.value = canRetry
  }

  function staleVersion(): void {
    versionStale.value = true
    notice.value = { tone: 'info', text: VERSION_STALE_MESSAGE }
    if (stalePending) return
    stalePending = true
    onVersionStale?.()
  }

  /** 会话、课程访问与空态类错误：整页处理；返回 true 表示已处理 */
  function handleAccess(cause: unknown): boolean {
    if (!(cause instanceof ApiError)) return false
    if (cause.code === 'COURSE_FORBIDDEN') {
      fail(FORBIDDEN_MESSAGE, false)
      store.selectCourse(null)
      onCourseForbidden?.()
      return true
    }
    if (cause.code === 'ROLE_FORBIDDEN') {
      // 掌握标记是学生行为：本课程教师拿不到可点击入口
      reset('not_student')
      return true
    }
    if (cause.code === 'GRAPH_NOT_PUBLISHED') {
      reset('unpublished')
      return true
    }
    if (cause.status === 401) {
      fail(SESSION_EXPIRED_MESSAGE, false)
      return true
    }
    if (cause.status >= 500) {
      // 已提交版完整性故障：只提示诊断 ID（ADR-017 决定 4），不回显细节
      fail(integrityMessage(cause), true)
      return true
    }
    return false
  }

  function statusOf(kpId: string): MasteryStatus {
    return entries.value.get(kpId)?.status ?? 'unknown'
  }

  function isSaving(kpId: string): boolean {
    return busyKpId.value === kpId
  }

  /** 读进度 + 推荐；按 §4 判定顺序区分未发布 / 完整性错误 / all_mastered / recommendations */
  async function load(): Promise<void> {
    seq += 1
    recSeq += 1
    writeSeq += 1
    abortAll()
    if (disposed || !active.value) {
      reset('idle')
      return
    }
    const course = cid.value as string
    const version = boundVersion.value as number
    store.selectCourse(course)
    const token = seq
    const { scope, own, release } = begin()
    const current = () => !disposed && token === seq && scope.isCurrent()

    reset('loading')
    try {
      const [progressResult, recommendResult] = await Promise.allSettled([
        progressApi!.get(course, { signal: own.signal }),
        recommendApi!.get(course, {}, { signal: own.signal }),
      ])
      if (!current()) return

      if (progressResult.status === 'rejected') {
        if (progressResult.reason instanceof AbortedError) return
        if (handleAccess(progressResult.reason)) return
        if (progressResult.reason instanceof NetworkError || progressResult.reason instanceof TimeoutError) {
          return fail(NETWORK_MESSAGE, true)
        }
        return fail(INVALID_MESSAGE, true)
      }
      if (!isProgressResponse(progressResult.value)) return fail(INVALID_MESSAGE, true)
      const progress = progressResult.value
      if (progress.graph_version !== version) {
        // 图与进度不同版本：不混算，要求页面重载
        return staleVersion()
      }

      if (recommendResult.status === 'rejected') {
        if (recommendResult.reason instanceof AbortedError) return
        if (handleAccess(recommendResult.reason)) return
        store.commit(scope, () => {
          entries.value = toEntryMap(progress.entries)
          status.value = 'ready'
          stalePending = false
          recommend.value = null
          recommendError.value = recommendFailureText(recommendResult.reason)
        })
        return
      }

      const result = recommendResult.value
      store.commit(scope, () => {
        entries.value = toEntryMap(progress.entries)
        status.value = 'ready'
        // 版本一致：显示与服务端重新对齐，允许下一次不一致时再次请求重载
        stalePending = false
        if (!isRecommendResponse(result)) {
          recommend.value = null
          recommendError.value = RECOMMEND_INVALID_MESSAGE
        } else if (result.graph_version !== version) {
          recommend.value = null
        } else {
          recommend.value = result
          recommendError.value = null
        }
      })
      if (isRecommendResponse(result) && result.graph_version !== version) staleVersion()
    } catch (cause) {
      if (!current() || cause instanceof AbortedError) return
      if (handleAccess(cause)) return
      if (cause instanceof NetworkError || cause instanceof TimeoutError) return fail(NETWORK_MESSAGE, true)
      fail(GENERIC_MESSAGE, true)
    } finally {
      release()
    }
  }

  /** 重新读推荐（掌握状态变化后 M 变了）；失败只影响推荐区，不推翻已读到的进度 */
  async function refreshRecommend(): Promise<void> {
    if (disposed || !enabled || status.value !== 'ready') return
    const course = cid.value
    const version = boundVersion.value
    if (course === null || version === null) return
    recSeq += 1
    const token = recSeq
    const loadToken = seq
    const { scope, own, release } = begin()
    const current = () => !disposed && token === recSeq && loadToken === seq && scope.isCurrent()
    recommendLoading.value = true
    recommendError.value = null
    try {
      const result = await recommendApi!.get(course, {}, { signal: own.signal })
      if (!current()) return
      if (!isRecommendResponse(result)) {
        recommendError.value = RECOMMEND_INVALID_MESSAGE
        return
      }
      if (result.graph_version !== version) {
        store.commit(scope, () => {
          recommend.value = null
        })
        staleVersion()
        return
      }
      store.commit(scope, () => {
        recommend.value = result
        recommendError.value = null
        stalePending = false
      })
    } catch (cause) {
      if (!current() || cause instanceof AbortedError) return
      if (handleAccess(cause)) return
      recommendError.value = recommendFailureText(cause)
    } finally {
      if (token === recSeq) recommendLoading.value = false
      release()
    }
  }

  /**
   * 乐观写入掌握状态：先本地改，失败完整回滚；成功以服务端投影为准并重算推荐。
   * `not_in_published_version` 与发布版本不一致时重新读进度与推荐（图谱由页面重载）。
   */
  async function write(kpId: string, next: MasteryStatus): Promise<void> {
    if (disposed || !enabled || status.value !== 'ready') return
    const course = cid.value
    const version = boundVersion.value
    if (course === null || version === null) return
    // 同一时刻最多一个在途写入：连点第二次起直接忽略
    if (busyKpId.value !== null) return

    const previous = entries.value
    const optimistic = new Map(previous)
    optimistic.set(kpId, optimisticEntry(previous.get(kpId), kpId, next))
    entries.value = optimistic

    writeSeq += 1
    const token = writeSeq
    const loadToken = seq
    const { scope, own, release } = begin()
    const current = () => !disposed && token === writeSeq && loadToken === seq && scope.isCurrent()
    busyKpId.value = kpId
    notice.value = null
    let after: 'none' | 'recommend' | 'reload' = 'none'
    let afterNotice: LearningNotice | null = null
    try {
      const result = await progressApi!.update(course, [{ kp_id: kpId, status: next }], { signal: own.signal })
      if (!current()) return
      if (!isProgressResponse(result)) {
        store.commit(scope, () => {
          entries.value = previous
          notice.value = { tone: 'error', text: WRITE_INVALID_MESSAGE }
        })
        return
      }
      if (result.graph_version !== version) {
        // 写入被服务端绑定到更新的发布版：显示中的图已过期，不把新投影套到旧图
        store.commit(scope, () => {
          entries.value = toEntryMap(result.entries)
        })
        staleVersion()
        return
      }
      store.commit(scope, () => {
        entries.value = toEntryMap(result.entries)
        notice.value = { tone: 'success', text: successText(next) }
      })
      after = 'recommend'
    } catch (cause) {
      if (!current() || cause instanceof AbortedError) return
      if (cause instanceof ApiError && hasNotInPublishedVersion(cause)) {
        store.commit(scope, () => {
          entries.value = previous
        })
        after = 'reload'
        afterNotice = { tone: 'error', text: NOT_IN_VERSION_MESSAGE }
      } else if (
        cause instanceof ApiError &&
        (cause.code === 'ROLE_FORBIDDEN' || cause.code === 'GRAPH_NOT_PUBLISHED' || cause.code === 'COURSE_FORBIDDEN' || cause.status === 401)
      ) {
        store.commit(scope, () => {
          entries.value = previous
        })
        handleAccess(cause)
        return
      } else {
        store.commit(scope, () => {
          entries.value = previous
          notice.value = { tone: 'error', text: WRITE_FAILED_MESSAGE }
        })
      }
    } finally {
      if (token === writeSeq) busyKpId.value = null
      release()
    }

    if (after === 'recommend' && current()) await refreshRecommend()
    else if (after === 'reload' && current()) {
      await load()
      if (!disposed) notice.value = afterNotice
    }
  }

  watch(
    () => [cid.value, boundVersion.value, active.value] as const,
    () => void load(),
  )

  // 其他页面清空了课程上下文（COURSE_FORBIDDEN、会话过期）
  watch(
    () => store.courseId,
    (id) => {
      if (id !== null || cid.value === null || status.value === 'idle') return
      seq += 1
      recSeq += 1
      abortAll()
      reset('idle')
    },
  )

  void load()

  onScopeDispose(() => {
    disposed = true
    abortAll()
  })

  return {
    status,
    error,
    retryable,
    entries,
    recommend,
    recommendState,
    recommendations,
    totalEligible,
    recommendedIds,
    learningGraph,
    learningPath,
    recommendError,
    recommendLoading,
    busyKpId,
    notice,
    versionStale,
    boundVersion,
    statusOf,
    isSaving,
    setMastery: (kpId: string, status: MasteryStatus) => write(kpId, status),
    reload: () => load(),
    refreshRecommend: () => refreshRecommend(),
  }
}
