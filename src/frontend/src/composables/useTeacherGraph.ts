import { computed, onScopeDispose, ref, shallowRef, watch, type Ref } from 'vue'
import type { CoursesApi } from '../api/courses'
import type { DraftGraphApi, GraphExchange } from '../api/graph'
import { AbortedError, ApiError, NetworkError, TimeoutError } from '../api/http'
import { useCourseStore, type CourseRequestScope } from '../stores/course'
import type { Chapter } from './useGraphFilters'

/**
 * 教师图谱编辑页状态（H14，ADR-067）。
 *
 * - 只在课程内角色为教师时读图，且只读草稿（`getGraph` 不带版本号）；响应的 `course_id` 必须与请求一致、
 *   `graph_version` 必须为 null（草稿），否则按数据异常丢弃，不会把某个发布版本当草稿编辑。
 * - 草稿写入课程 store（`setGraph`）：H07 节点编辑与 H08 连边编辑都以 store 里的图为基准并在成功后写回，
 *   画布从同一份图派生，因此保存/删除/连边成功后画布自动同步，失败时 store 不变、画布不变。
 * - `refresh` 供编辑器在修订冲突后重新拉草稿：保留当前画布，失败只给提示，不清空已显示的图。
 *
 * 迟到隔离沿用课程作用域：路由换课、重载、刷新、卸载都会作废旧请求，旧响应不写入。
 */

export type TeacherGraphStatus = 'idle' | 'loading' | 'not_teacher' | 'ready' | 'error'

const FORBIDDEN_MESSAGE = '你无权访问该课程。'
const SESSION_EXPIRED_MESSAGE = '登录已失效，请重新登录。'
const NETWORK_MESSAGE = '无法连接服务器，请检查网络后重试。'
const INVALID_MESSAGE = '服务器返回的草稿图谱数据异常，请稍后重试。'
const GENERIC_MESSAGE = '草稿图谱加载失败，请稍后重试。'
const CONTEXT_LOST_MESSAGE = '课程上下文已失效，请重新加载或返回课程列表。'
const REFRESH_FAILED_MESSAGE = '刷新草稿图谱失败，画布仍显示刷新前的内容，请稍后重试。'

export interface UseTeacherGraphOptions {
  coursesApi: Pick<CoursesApi, 'get'>
  graphApi: DraftGraphApi
  /** 路由里的课程 ID；null 表示不在教师图谱页 */
  courseId: Ref<string | null>
  onCourseForbidden?: () => void
}

/** 草稿校验：同课程、`graph_version` 为 null、节点与边为数组 */
export function isDraftOf(result: GraphExchange | null | undefined, cid: string): result is GraphExchange {
  if (typeof result !== 'object' || result === null) return false
  if (result.course_id !== cid) return false
  if (result.graph_version !== null && result.graph_version !== undefined) return false
  return Array.isArray(result.nodes) && Array.isArray(result.edges)
}

export function useTeacherGraph({ coursesApi, graphApi, courseId, onCourseForbidden }: UseTeacherGraphOptions) {
  const store = useCourseStore()
  const status = ref<TeacherGraphStatus>('idle')
  const error = ref<string | null>(null)
  const retryable = ref(false)
  const courseName = ref<string | null>(null)
  const chapters = shallowRef<Chapter[]>([])
  const refreshing = ref(false)
  const refreshError = ref<string | null>(null)

  /** 编辑器共用的草稿图；只在就绪时对外可见 */
  const graph = computed<GraphExchange | null>(() => (status.value === 'ready' ? store.graph : null))

  let seq = 0
  let controller: AbortController | null = null
  let disposed = false

  function cancel(): void {
    seq += 1
    controller?.abort()
    controller = null
    refreshing.value = false
  }

  function reset(next: TeacherGraphStatus): void {
    status.value = next
    error.value = null
    retryable.value = false
    chapters.value = []
    refreshError.value = null
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
        store.selectCourse(null)
        onCourseForbidden?.()
        return
      }
      // 课程详情说是教师、读图时角色已被移除：按非教师处理，不显示草稿
      if (cause.code === 'ROLE_FORBIDDEN') return reset('not_teacher')
      if (cause.status === 401) return fail(SESSION_EXPIRED_MESSAGE, false)
      return fail(GENERIC_MESSAGE, cause.status >= 500)
    }
    if (cause instanceof NetworkError || cause instanceof TimeoutError) return fail(NETWORK_MESSAGE, true)
    fail(INVALID_MESSAGE, true)
  }

  /** 开启一次请求：作废旧请求，取课程作用域，并把作用域中止联到本次请求 */
  function begin(): { token: number; scope: CourseRequestScope; own: AbortController; release: () => void } {
    cancel()
    const token = seq
    const scope = store.beginRequest()
    const own = new AbortController()
    controller = own
    const onScopeAbort = () => own.abort(scope.signal.reason)
    if (scope.signal.aborted) own.abort(scope.signal.reason)
    else scope.signal.addEventListener('abort', onScopeAbort, { once: true })
    const release = () => {
      scope.signal.removeEventListener('abort', onScopeAbort)
      if (controller === own) controller = null
    }
    return { token, scope, own, release }
  }

  async function load(cid: string | null): Promise<void> {
    cancel()
    courseName.value = null
    if (disposed || cid === null) {
      reset('idle')
      return
    }
    store.selectCourse(cid)
    const { token, scope, own, release } = begin()
    const current = () => !disposed && token === seq && scope.isCurrent()

    reset('loading')
    try {
      const course = await coursesApi.get(cid, { signal: own.signal })
      if (!current()) return
      if (course?.id !== cid) return fail(INVALID_MESSAGE, true)
      courseName.value = course.name
      if (course.my_role !== 'teacher') return reset('not_teacher')

      const result = await graphApi.getDraft(cid, { signal: own.signal })
      if (!current()) return
      if (!isDraftOf(result, cid)) return fail(INVALID_MESSAGE, true)
      store.commit(scope, () => {
        store.setGraph(scope, result)
        chapters.value = Array.isArray(result.chapters) ? result.chapters : []
        status.value = 'ready'
      })
    } catch (cause) {
      if (!current() || cause instanceof AbortedError) return
      handle(cause)
    } finally {
      release()
    }
  }

  /**
   * 编辑器要求刷新（修订冲突、关系已不存在等）：只替换草稿，失败保留当前画布。
   * 刷新在途时编辑器若已写回 store（保存、删除、连边成功），这份响应可能早于那次写入，
   * 丢弃并重新拉取，不让旧快照盖掉刚成功的修改。
   */
  async function refresh(): Promise<void> {
    const cid = courseId.value
    if (disposed || cid === null || status.value !== 'ready' || store.courseId !== cid) return
    const { token, scope, own, release } = begin()
    const current = () => !disposed && token === seq && scope.isCurrent()
    const base = store.graph
    let again = false
    refreshing.value = true
    refreshError.value = null
    try {
      const result = await graphApi.getDraft(cid, { signal: own.signal })
      if (!current()) return
      if (store.graph !== base) {
        again = true
        return
      }
      if (!isDraftOf(result, cid)) {
        refreshError.value = REFRESH_FAILED_MESSAGE
        return
      }
      store.commit(scope, () => {
        store.setGraph(scope, result)
        chapters.value = Array.isArray(result.chapters) ? result.chapters : []
      })
    } catch (cause) {
      if (!current() || cause instanceof AbortedError) return
      if (cause instanceof ApiError && (cause.code === 'COURSE_FORBIDDEN' || cause.code === 'ROLE_FORBIDDEN')) {
        handle(cause)
        return
      }
      if (cause instanceof ApiError && cause.status === 401) {
        handle(cause)
        return
      }
      refreshError.value = REFRESH_FAILED_MESSAGE
    } finally {
      if (token === seq) refreshing.value = false
      release()
    }
    if (again) await refresh()
  }

  // 编辑器收到 COURSE_FORBIDDEN、会话过期等会清空课程上下文；若仍停在本页，给出错误态而不是空白
  watch(
    () => store.courseId,
    (id) => {
      if (id !== null || courseId.value === null || status.value !== 'ready') return
      cancel()
      fail(CONTEXT_LOST_MESSAGE, true)
    },
  )

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
    graph,
    chapters,
    refreshing,
    refreshError,
    reload: () => void load(courseId.value),
    refresh: () => void refresh(),
  }
}

export interface UseSelectionGuardOptions {
  /** 当前选中的知识点 */
  selected: Readonly<Ref<string | null>>
  /** 真正改变选中 */
  apply: (kpId: string | null) => void
  /** 节点编辑面板是否有未保存的修改 */
  isDirty: () => boolean
}

/**
 * 切换选中前的未保存确认（H14）：面板有未保存修改时，换节点或关闭面板先挂起为待确认，
 * 教师确认放弃后才切换；取消则保留当前节点与修改。选中被外部改变（删除、换课）时撤销待确认。
 */
export interface SelectionRequestOptions {
  /** C05-1：选中真正生效后才执行（如画布聚焦）；取消、或选中被外部改变（删除、换课）时丢弃 */
  then?: (kpId: string | null) => void
}

export function useSelectionGuard({ selected, apply, isDirty }: UseSelectionGuardOptions) {
  const pending = shallowRef<{ kpId: string | null } | null>(null)
  let after: SelectionRequestOptions['then'] | null = null

  function request(kpId: string | null, options: SelectionRequestOptions = {}): void {
    if (kpId === selected.value) {
      pending.value = null
      after = null
      options.then?.(kpId)
      return
    }
    if (selected.value !== null && isDirty()) {
      pending.value = { kpId }
      after = options.then ?? null
      return
    }
    pending.value = null
    after = null
    apply(kpId)
    options.then?.(kpId)
  }

  function confirm(): void {
    const target = pending.value
    const then = after
    pending.value = null
    after = null
    if (target === null) return
    apply(target.kpId)
    then?.(target.kpId)
  }

  function cancel(): void {
    pending.value = null
    after = null
  }

  watch(selected, () => {
    pending.value = null
    after = null
  })

  return { pending: pending as Readonly<Ref<{ kpId: string | null } | null>>, request, confirm, cancel }
}
