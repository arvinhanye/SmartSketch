import { onScopeDispose, ref, watch, type Ref } from 'vue'
import type { InviteCodeApi } from '../api/inviteCode'
import { AbortedError, ApiError, NetworkError, TimeoutError } from '../api/http'

const FORMAT_MESSAGE = '请输入六位邀请码（不含 0、O、1、I）。'

function joinError(cause: unknown): string {
  if (cause instanceof ApiError) {
    if (cause.code === 'INVITE_CODE_INVALID') return '邀请码不存在或已失效，请向教师获取新码。'
    if (cause.code === 'ALREADY_MEMBER') return '你已在该课程中，无需重复加入。'
    if (cause.code === 'RATE_LIMITED') return '请求过于频繁，请稍后再试。'
    if (cause.status === 422) return FORMAT_MESSAGE
    if (cause.status === 403) return '仅学生账号可以凭码加入课程。'
    if (cause.status === 401) return '登录已失效，请重新登录。'
  }
  if (cause instanceof NetworkError || cause instanceof TimeoutError) return '无法连接服务器，请检查网络后重试。'
  return '加入课程失败，请稍后重试。'
}

/** 入课与随后列表刷新共同占用提交状态；会话或页面变化后不再写回回执与高亮。 */
export function useCourseJoin(options: {
  api: InviteCodeApi | null
  enabled: Ref<boolean>
  sessionKey: Ref<string | null>
  refreshCourses: () => Promise<void>
}) {
  const code = ref('')
  const joining = ref(false)
  const error = ref<string | null>(null)
  const notice = ref<string | null>(null)
  const joinedId = ref<string | null>(null)
  let generation = 0
  let controller: AbortController | null = null
  let inFlight = false
  let disposed = false

  function reset(): void {
    generation += 1
    controller?.abort()
    controller = null
    inFlight = false
    joining.value = false
    code.value = ''
    error.value = null
    notice.value = null
    joinedId.value = null
  }
  watch([options.enabled, options.sessionKey], reset, { flush: 'sync' })
  onScopeDispose(() => { disposed = true; reset() })

  async function join(): Promise<void> {
    const api = options.api
    if (disposed || inFlight || !options.enabled.value || !options.sessionKey.value || api === null) return
    notice.value = null
    joinedId.value = null
    const normalized = code.value.trim().toUpperCase()
    code.value = normalized
    if (!/^[A-HJ-NP-Z2-9]{6}$/.test(normalized)) {
      error.value = FORMAT_MESSAGE
      return
    }
    const owner = generation
    const key = options.sessionKey.value
    const request = new AbortController()
    controller = request
    const current = () => !disposed && owner === generation && controller === request && !request.signal.aborted && options.enabled.value && options.sessionKey.value === key
    inFlight = true
    joining.value = true
    error.value = null
    try {
      const result = await api.join({ code: normalized }, { signal: request.signal })
      if (!current()) return
      await options.refreshCourses()
      if (!current()) return
      code.value = ''
      // 未发布课程只给回执，课程列表仍完全使用 listCourses 的可见数据。
      const published = result.published_version != null
      joinedId.value = published ? result.id : null
      notice.value = `已加入课程「${result.name}」。${published ? '' : '教师发布后可见。'}`
    } catch (cause) {
      if (current() && !(cause instanceof AbortedError)) error.value = joinError(cause)
    } finally {
      if (current()) {
        controller = null
        inFlight = false
        joining.value = false
      }
    }
  }

  return { code, joining, error, notice, joinedId, join }
}
