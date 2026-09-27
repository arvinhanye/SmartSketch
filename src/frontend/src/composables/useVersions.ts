import { computed, onScopeDispose, ref, shallowRef, watch, type Ref } from 'vue'
import type { Course, CoursesApi } from '../api/courses'
import { AbortedError, ApiError, NetworkError, TimeoutError } from '../api/http'
import type { GraphVersion, VersionsApi } from '../api/versions'

export type VersionsStatus = 'idle' | 'loading' | 'ready' | 'error' | 'not_teacher'

export interface UseVersionsOptions {
  courseId: Ref<string | null>
  coursesApi: Pick<CoursesApi, 'get'>
  versionsApi: VersionsApi
  onCourseForbidden?: () => void
}

function validVersion(value: unknown): value is GraphVersion {
  if (typeof value !== 'object' || value === null) return false
  const row = value as Record<string, unknown>
  if (!Number.isInteger(row.version) || (row.version as number) < 1 || typeof row.published_at !== 'string') return false
  return row.kind === 'publish' || (row.kind === 'rollback' && Number.isInteger(row.source_version) && (row.source_version as number) > 0)
}

function message(cause: unknown, operation: 'load' | 'publish' | 'rollback'): string {
  if (cause instanceof ApiError) {
    if (cause.code === 'PUBLISH_BLOCKED') return '发布校验未通过，请检查图谱中的环路、来源和空图问题。'
    if (cause.code === 'PUBLISH_IN_PROGRESS') return '本课程已有发布或回滚进行中，请稍后重试。'
    if (cause.code === 'COURSE_BUSY') return '课程正在写入，请稍后重试。'
    if (cause.status === 404 && operation === 'rollback') return '目标版本不存在或不可用，请刷新版本历史。'
  }
  if (cause instanceof NetworkError || cause instanceof TimeoutError) return '请求结果未确认，请重新加载以核对当前发布版本。'
  return operation === 'load' ? '加载版本历史失败，请重试。' : '操作结果未确认，请重新加载以核对当前发布版本。'
}

export function useVersions({ courseId, coursesApi, versionsApi, onCourseForbidden }: UseVersionsOptions) {
  const status = ref<VersionsStatus>('idle')
  const course = shallowRef<Course | null>(null)
  const versions = shallowRef<GraphVersion[]>([])
  const error = ref<string | null>(null)
  const notice = ref<string | null>(null)
  const busy = ref<'publish' | 'rollback' | null>(null)
  const pendingRollback = ref<number | null>(null)
  const refreshing = ref(false)
  const stale = ref(false)
  const currentVersion = computed(() => course.value?.published_version ?? null)
  const history = computed(() => [...versions.value].sort((a, b) => b.version - a.version))
  let epoch = 0
  let readSeq = 0
  let disposed = false
  let readController: AbortController | null = null
  let writeController: AbortController | null = null

  const current = (cid: string, token: number) => !disposed && token === epoch && courseId.value === cid

  function handleForbidden(cause: unknown): boolean {
    if (!(cause instanceof ApiError)) return false
    if (cause.code === 'COURSE_FORBIDDEN') {
      onCourseForbidden?.()
      return true
    }
    if (cause.code === 'ROLE_FORBIDDEN') {
      course.value = null
      versions.value = []
      pendingRollback.value = null
      status.value = 'not_teacher'
      return true
    }
    return false
  }

  async function reload(): Promise<boolean> {
    const cid = courseId.value
    if (cid === null || disposed) return false
    const token = epoch
    const readToken = ++readSeq
    readController?.abort()
    const controller = new AbortController()
    readController = controller
    if (course.value === null) status.value = 'loading'
    else refreshing.value = true
    error.value = null
    try {
      const nextCourse = await coursesApi.get(cid, { signal: controller.signal })
      if (!current(cid, token) || readToken !== readSeq || controller.signal.aborted) return false
      if (nextCourse?.id !== cid) {
        status.value = 'error'
        error.value = '服务器返回的课程数据异常，请重试。'
        return false
      }
      if (nextCourse.my_role !== 'teacher') {
        course.value = null
        versions.value = []
        pendingRollback.value = null
        status.value = 'not_teacher'
        return false
      }
      const nextVersions = await versionsApi.list(cid, { signal: controller.signal })
      if (!current(cid, token) || readToken !== readSeq || controller.signal.aborted) return false
      if (!Array.isArray(nextVersions) || !nextVersions.every(validVersion)) {
        status.value = 'error'
        error.value = '服务器返回的版本数据异常，请重试。'
        return false
      }
      if (nextCourse.published_version !== null && !nextVersions.some((item) => item.version === nextCourse.published_version)) {
        stale.value = true
        if (course.value === null) status.value = 'error'
        error.value = '课程发布指针与版本历史不一致，请刷新状态后核对。'
        return false
      }
      course.value = nextCourse
      versions.value = nextVersions
      stale.value = false
      status.value = 'ready'
      return true
    } catch (cause) {
      if (!current(cid, token) || readToken !== readSeq || controller.signal.aborted || cause instanceof AbortedError) return false
      if (!handleForbidden(cause)) {
        if (course.value === null) status.value = 'error'
        error.value = message(cause, 'load')
      }
      return false
    } finally {
      if (readController === controller) readController = null
      if (current(cid, token) && readToken === readSeq) refreshing.value = false
    }
  }

  function chooseRollback(version: number): void {
    if (status.value !== 'ready' || busy.value !== null || stale.value || !history.value.some((item) => item.version === version)) return
    if (version === currentVersion.value) return
    pendingRollback.value = version
    error.value = null
  }

  function cancelRollback(): void { pendingRollback.value = null }

  async function operate(kind: 'publish' | 'rollback'): Promise<void> {
    const cid = courseId.value
    const target = pendingRollback.value
    if (cid === null || status.value !== 'ready' || busy.value !== null || stale.value) return
    if (kind === 'rollback' && (target === null || target === currentVersion.value)) return
    const token = epoch
    const controller = new AbortController()
    writeController = controller
    busy.value = kind
    error.value = null
    notice.value = null
    try {
      const result = kind === 'publish'
        ? await versionsApi.publish(cid, { signal: controller.signal })
        : await versionsApi.rollback(cid, target!, { signal: controller.signal })
      if (!current(cid, token) || controller.signal.aborted) return
      pendingRollback.value = null
      stale.value = true // 成功响应不替代课程发布指针；只采纳新的课程详情与版本列表
      const refreshed = await reload()
      if (!current(cid, token)) return
      if (refreshed && currentVersion.value === result.version) notice.value = result.unchanged
        ? `内容未变化，仍是 v${result.version}。`
        : kind === 'rollback' ? `已从 v${target} 创建发布版本 v${result.version}。` : `已发布 v${result.version}。`
      else {
        stale.value = true
        error.value = '操作已提交，但状态刷新未确认目标版本；请重新加载后核对学生可见版本。'
      }
    } catch (cause) {
      if (!current(cid, token) || controller.signal.aborted || cause instanceof AbortedError) return
      // 超时/断网可能发生在服务端提交之后，先核对课程指针再允许重复写入。
      if (cause instanceof NetworkError || cause instanceof TimeoutError) stale.value = true
      if (!handleForbidden(cause)) error.value = message(cause, kind)
    } finally {
      if (writeController === controller) writeController = null
      if (current(cid, token)) busy.value = null
    }
  }

  function reset(cid: string | null): void {
    epoch += 1
    readSeq += 1
    readController?.abort()
    writeController?.abort()
    course.value = null
    versions.value = []
    status.value = 'idle'
    error.value = null
    notice.value = null
    busy.value = null
    pendingRollback.value = null
    refreshing.value = false
    stale.value = false
    if (cid !== null) void reload()
  }
  watch(courseId, reset, { immediate: true })
  onScopeDispose(() => { disposed = true; epoch += 1; readController?.abort(); writeController?.abort() })

  return { status, course, history, currentVersion, error, notice, busy, pendingRollback, refreshing, stale,
    reload, chooseRollback, cancelRollback, publish: () => operate('publish'), rollback: () => operate('rollback') }
}
