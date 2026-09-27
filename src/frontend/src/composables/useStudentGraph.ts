import { onScopeDispose, ref, shallowRef, watch, type Ref } from 'vue'
import type { CoursesApi } from '../api/courses'
import type { GraphExchange, PublishedGraphApi } from '../api/graph'
import { AbortedError, ApiError, NetworkError, TimeoutError } from '../api/http'
import { toG6Data, type AdaptedGraph } from '../graph/adapter'
import type { CanvasNode } from '../graph/lifecycle'
import { useCourseStore } from '../stores/course'
import { NODE_TYPE_LABELS, type Chapter } from './useGraphFilters'

/**
 * 学生图谱页状态（H11，ADR-063）。
 *
 * 「任何入口不取草稿」由三层保证：
 * 1. 只在课程内角色为学生时发图谱请求；教师成员（包括在本课做教师的账号）得到 `not_student`，
 *    因为契约规定教师省略版本号读草稿，详情接口也没有版本参数。
 * 2. 图谱请求总是带 `Course.published_version`；该值为 null 时不发请求，直接 `unpublished`。
 * 3. 响应的 `course_id`、`graph_version` 必须与请求一致，否则按数据异常丢弃（草稿的 `graph_version` 为 null）。
 * 卡片视图由同一份已发布图派生，不调用 `GET /kp`（该列表没有版本参数）。
 *
 * 迟到隔离沿用课程作用域：路由换课、重载、卸载都会作废旧请求，旧响应不写入。
 */

export type StudentGraphStatus = 'idle' | 'loading' | 'not_student' | 'unpublished' | 'ready' | 'error'

const FORBIDDEN_MESSAGE = '你无权访问该课程。'
const SESSION_EXPIRED_MESSAGE = '登录已失效，请重新登录。'
const NETWORK_MESSAGE = '无法连接服务器，请检查网络后重试。'
const INVALID_MESSAGE = '服务器返回的图谱数据异常，请稍后重试。'
const GENERIC_MESSAGE = '图谱加载失败，请稍后重试。'
const VERSION_GONE_MESSAGE = '课程图谱版本已更新，请重新加载。'

export interface KnowledgeCard {
  kpId: string
  name: string
  typeLabel: string
  chapterLabel: string
  level: number
}

function byCodePoint(a: string, b: string): number {
  return a < b ? -1 : a > b ? 1 : 0
}

/**
 * 可见知识点 → 卡片（纯函数，不改输入）。
 * 顺序：章节目录 `order`（目录外章节按 ID、未分章在最后）→ 层级 → 名称 → ID，与画布布局无关，翻页稳定。
 */
export function toKnowledgeCards(nodes: readonly CanvasNode[], chapters: readonly Chapter[] = []): KnowledgeCard[] {
  const catalog = new Map(chapters.map((chapter) => [chapter.id, chapter]))
  const rank = (id: string | null): [number, number, string] => {
    if (id === null) return [2, 0, '']
    const entry = catalog.get(id)
    return entry === undefined ? [1, 0, id] : [0, entry.order, id]
  }
  return nodes
    .map((node) => ({ data: node.data, rank: rank(node.data.chapterId) }))
    .sort(
      (a, b) =>
        a.rank[0] - b.rank[0] ||
        a.rank[1] - b.rank[1] ||
        byCodePoint(a.rank[2], b.rank[2]) ||
        a.data.level - b.data.level ||
        byCodePoint(a.data.name, b.data.name) ||
        byCodePoint(a.data.kpId, b.data.kpId),
    )
    .map(({ data }) => ({
      kpId: data.kpId,
      name: data.name,
      typeLabel: NODE_TYPE_LABELS[data.type] ?? data.type,
      chapterLabel: data.chapterId === null ? '未分章' : (catalog.get(data.chapterId)?.title ?? data.chapterId),
      level: data.level,
    }))
}

export interface UseStudentGraphOptions {
  coursesApi: Pick<CoursesApi, 'get'>
  graphApi: PublishedGraphApi
  /** 路由里的课程 ID；null 表示不在学生图谱页 */
  courseId: Ref<string | null>
  onCourseForbidden?: () => void
}

export function useStudentGraph({ coursesApi, graphApi, courseId, onCourseForbidden }: UseStudentGraphOptions) {
  const store = useCourseStore()
  const status = ref<StudentGraphStatus>('idle')
  const error = ref<string | null>(null)
  const retryable = ref(false)
  const courseName = ref<string | null>(null)
  const graphVersion = ref<number | null>(null)
  const graph = shallowRef<AdaptedGraph | null>(null)
  const chapters = shallowRef<Chapter[]>([])

  let seq = 0
  let controller: AbortController | null = null
  let disposed = false

  function cancel(): void {
    seq += 1
    controller?.abort()
    controller = null
  }

  function reset(next: StudentGraphStatus): void {
    status.value = next
    error.value = null
    retryable.value = false
    graphVersion.value = null
    graph.value = null
    chapters.value = []
  }

  function fail(message: string, canRetry: boolean): void {
    reset('error')
    error.value = message
    retryable.value = canRetry
  }

  function handle(cause: unknown): void {
    if (cause instanceof ApiError) {
      if (cause.code === 'COURSE_FORBIDDEN') {
        fail(FORBIDDEN_MESSAGE, false)
        onCourseForbidden?.()
        return
      }
      if (cause.code === 'GRAPH_NOT_PUBLISHED') return reset('unpublished')
      // 课程详情给出的版本在读图前被回滚或替换：重新加载会读到新的当前版本
      if (cause.code === 'NOT_FOUND') return fail(VERSION_GONE_MESSAGE, true)
      if (cause.status === 401) return fail(SESSION_EXPIRED_MESSAGE, false)
      return fail(GENERIC_MESSAGE, cause.status >= 500)
    }
    if (cause instanceof NetworkError || cause instanceof TimeoutError) return fail(NETWORK_MESSAGE, true)
    fail(INVALID_MESSAGE, true)
  }

  function accept(result: GraphExchange | null | undefined, cid: string, version: number): AdaptedGraph | null {
    if (typeof result !== 'object' || result === null) return null
    if (result.course_id !== cid || result.graph_version !== version) return null
    if (!Array.isArray(result.nodes) || !Array.isArray(result.edges)) return null
    return toG6Data(result)
  }

  async function load(cid: string | null): Promise<void> {
    cancel()
    const token = seq
    courseName.value = null
    if (disposed || cid === null) {
      reset('idle')
      return
    }
    store.selectCourse(cid)
    const scope = store.beginRequest()
    const own = new AbortController()
    controller = own
    const onScopeAbort = () => own.abort(scope.signal.reason)
    if (scope.signal.aborted) own.abort(scope.signal.reason)
    else scope.signal.addEventListener('abort', onScopeAbort, { once: true })
    const current = () => !disposed && token === seq && scope.isCurrent()

    reset('loading')
    try {
      const course = await coursesApi.get(cid, { signal: own.signal })
      if (!current()) return
      if (course?.id !== cid) return fail(INVALID_MESSAGE, true)
      courseName.value = course.name
      if (course.my_role !== 'student') return reset('not_student')
      const version = course.published_version
      if (version === null || version === undefined) return reset('unpublished')

      const result = await graphApi.getPublished(cid, version, { signal: own.signal })
      if (!current()) return
      const adapted = accept(result, cid, version)
      if (adapted === null) return fail(INVALID_MESSAGE, true)
      store.commit(scope, () => {
        status.value = 'ready'
        graphVersion.value = version
        chapters.value = Array.isArray(result.chapters) ? result.chapters : []
        graph.value = adapted
      })
    } catch (cause) {
      if (!current() || cause instanceof AbortedError) return
      handle(cause)
    } finally {
      scope.signal.removeEventListener('abort', onScopeAbort)
      if (controller === own) controller = null
    }
  }

  watch(courseId, (cid) => void load(cid))
  void load(courseId.value)

  onScopeDispose(() => {
    disposed = true
    cancel()
  })

  return {
    status,
    error,
    retryable,
    courseName,
    graphVersion,
    graph,
    chapters,
    reload: () => void load(courseId.value),
  }
}
