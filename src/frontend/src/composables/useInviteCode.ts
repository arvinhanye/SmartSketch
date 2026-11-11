import { computed, nextTick, onScopeDispose, ref, watch, type Ref } from 'vue'
import type { InviteCodeApi } from '../api/inviteCode'
import { AbortedError, ApiError, NetworkError, TimeoutError } from '../api/http'

function requestError(cause: unknown, action: '加载' | '重置'): string {
  if (cause instanceof ApiError) {
    if (cause.status === 401) return '登录已失效，请重新登录。'
    if (cause.status === 403) return '只有本课程的教师成员可以查看和重置邀请码。'
    if (cause.code === 'RATE_LIMITED') return '请求过于频繁，请稍后再试。'
  }
  if (cause instanceof NetworkError || cause instanceof TimeoutError) return '无法连接服务器，请检查网络后重试。'
  return `邀请码${action}失败，请稍后重试。`
}

/** 教师邀请码只驻留当前页面；读取、重置、剪贴板回执都受课程与会话代次约束。 */
export function useInviteCode(options: {
  api: InviteCodeApi | null
  courseId: Ref<string | null>
  sessionKey: Ref<string | null>
  enabled: Ref<boolean>
  onCourseForbidden: () => void
}) {
  const code = ref<string | null>(null)
  const loading = ref(false)
  const rotating = ref(false)
  const confirming = ref(false)
  const error = ref<string | null>(null)
  const notice = ref<string | null>(null)
  const copying = ref(false)
  const copyStatus = ref<string | null>(null)
  const busy = computed(() => loading.value || rotating.value)
  let generation = 0
  let controller: AbortController | null = null
  let inFlight = false
  let copySequence = 0
  let disposed = false

  function reset(): void {
    generation += 1
    copySequence += 1
    controller?.abort()
    controller = null
    inFlight = false
    code.value = null
    loading.value = false
    rotating.value = false
    confirming.value = false
    error.value = null
    notice.value = null
    copying.value = false
    copyStatus.value = null
  }

  async function request(rotate: boolean): Promise<void> {
    const { api } = options
    const cid = options.courseId.value
    const key = options.sessionKey.value
    if (disposed || inFlight || !options.enabled.value || api === null || cid === null || key === null) return
    if (rotate && (!confirming.value || code.value === null || copying.value)) return
    const owner = generation
    const currentRequest = new AbortController()
    controller = currentRequest
    const current = () => !disposed && owner === generation && controller === currentRequest && !currentRequest.signal.aborted && options.enabled.value && options.courseId.value === cid && options.sessionKey.value === key
    inFlight = true
    loading.value = !rotate
    rotating.value = rotate
    error.value = null
    notice.value = null
    copyStatus.value = null
    try {
      const result = await (rotate ? api.rotate(cid, { signal: currentRequest.signal }) : api.get(cid, { signal: currentRequest.signal }))
      if (!current()) return
      code.value = result.code
      confirming.value = false
      if (rotate) notice.value = '邀请码已重置，旧码已失效。'
    } catch (cause) {
      if (!current() || cause instanceof AbortedError) return
      if (rotate && !(cause instanceof ApiError)) {
        // 传输或响应失败时服务端可能已经提交，旧码不能再作为有效码展示或复制。
        code.value = null
        confirming.value = false
        error.value = '无法确认邀请码是否已重置，请重新获取当前邀请码。'
      } else {
        if (cause instanceof ApiError && cause.status === 403) code.value = null
        error.value = requestError(cause, rotate ? '重置' : '加载')
      }
      if (cause instanceof ApiError && cause.code === 'COURSE_FORBIDDEN') options.onCourseForbidden()
    } finally {
      if (current()) {
        controller = null
        inFlight = false
        loading.value = false
        rotating.value = false
      }
    }
  }

  watch([options.courseId, options.sessionKey, options.enabled], () => {
    reset()
    const owner = generation
    // 先同步取消旧请求，再等成员页的课程切换/加载状态落地，避免沿用旧课 ready 发请求。
    void nextTick(() => {
      if (!disposed && owner === generation && options.enabled.value) void request(false)
    })
  }, { immediate: true, flush: 'sync' })
  onScopeDispose(() => { disposed = true; reset() })

  async function copy(): Promise<void> {
    const value = code.value
    if (disposed || !options.enabled.value || busy.value || copying.value || value === null) return
    const owner = generation
    const sequence = ++copySequence
    const current = () => !disposed && owner === generation && sequence === copySequence && options.enabled.value && code.value === value
    copying.value = true
    copyStatus.value = null
    try {
      await navigator.clipboard.writeText(value)
      if (current()) copyStatus.value = '邀请码已复制。'
    } catch {
      if (current()) copyStatus.value = '复制失败，请手动选中并复制邀请码。'
    } finally {
      if (current()) copying.value = false
    }
  }

  function askReset(): void {
    if (!busy.value && !copying.value && code.value !== null && options.enabled.value) {
      confirming.value = true
      error.value = null
      notice.value = null
    }
  }
  function cancelReset(): void {
    if (!rotating.value) confirming.value = false
  }

  return { code, loading, rotating, busy, confirming, error, notice, copying, copyStatus, load: () => request(false), rotate: () => request(true), copy, askReset, cancelReset }
}
