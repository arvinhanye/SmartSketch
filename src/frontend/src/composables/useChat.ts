import { computed, onScopeDispose, ref, watch, type Ref } from 'vue'
import type { components } from '../../../contracts/v1/generated/typescript/openapi'
import { ChatStreamInterruptedError, type ChatStreamClient } from '../api/chatStream'
import { AbortedError, ApiError, TimeoutError } from '../api/http'
import { useCourseStore } from '../stores/course'

type ChatResponse = components['schemas']['ChatResponse']
export type Citation = { index: number; chunk_id: string; document_id: string; section_path?: string; page?: number; text: string }

export interface ChatEntry {
  id: number
  question: string
  answer: string
  status: 'streaming' | 'answered' | 'not_covered' | 'error' | 'aborted'
  graphVersion?: number
  citations: Citation[]
  relatedKpIds: string[]
}

function errorText(code: string, reason?: string): string {
  if (code === 'LLM_UNAVAILABLE') {
    if (reason === 'timeout') return '回答超时，请稍后重试。'
    if (reason === 'stream_interrupted') return '连接中断，回答已撤回。'
    if (reason === 'auth') return '问答服务鉴权失败，请稍后重试。'
    return '问答服务暂不可用，请稍后重试。'
  }
  if (code === 'BUDGET_EXCEEDED') return '当前问答额度不足，请稍后重试。'
  if (code === 'STORAGE_UNAVAILABLE') return '课程资料暂不可用，请稍后重试。'
  if (code === 'RATE_LIMITED') return '提问过于频繁，请稍后重试。'
  if (code === 'COURSE_FORBIDDEN' || code === 'ROLE_FORBIDDEN') return '当前无权使用这门课程的问答。'
  if (code === 'GRAPH_NOT_PUBLISHED') return '这门课程尚未发布知识图谱。'
  return '问答暂时失败，请稍后重试。'
}

/** J09：页面状态与课程作用域；只有 done 才提交历史。 */
export function useChat(client: ChatStreamClient, courseId: Ref<string | null>) {
  const course = useCourseStore()
  const entries = ref<ChatEntry[]>([])
  const question = ref('')
  const sending = ref(false)
  let active: AbortController | null = null
  let serial = 0

  function stop(): void {
    if (!active) return
    active.abort()
    active = null
    const last = entries.value.at(-1)
    if (last?.status === 'streaming') {
      last.answer = '已停止'
      last.status = 'aborted'
    }
    sending.value = false
  }

  watch(courseId, (id) => {
    stop()
    course.selectCourse(id)
    entries.value = []
  }, { immediate: true })

  async function ask(text = question.value): Promise<void> {
    const trimmed = text.trim()
    if (!trimmed || !courseId.value) return
    stop()
    const controller = new AbortController()
    active = controller
    const scope = course.beginRequest()
    entries.value.push({ id: ++serial, question: trimmed, answer: '', status: 'streaming', citations: [], relatedKpIds: [] })
    // 取回响应式代理再写：直接改原对象不会触发 computed（如 currentVersion）更新
    const entry: ChatEntry = entries.value[entries.value.length - 1]!
    question.value = ''
    sending.value = true
    const history = [...course.chatHistory]
    try {
      const outcome = await client.send(scope.courseId, { question: trimmed, history }, {
        signal: controller.signal,
        onEvent(event) {
          if (!scope.isCurrent() || active !== controller) return
          if (event.kind === 'meta') entry.graphVersion = event.data.graph_version
          else if (event.kind === 'delta') entry.answer += event.data.delta
        },
      })
      if (!scope.isCurrent() || active !== controller) return
      if (outcome.kind === 'done') {
        const final: ChatResponse = outcome.final
        entry.answer = final.answer
        entry.status = final.status
        entry.graphVersion = final.graph_version
        entry.citations = final.status === 'answered' ? final.citations as Citation[] : []
        entry.relatedKpIds = final.related_kp_ids ?? []
        course.appendChatTurns(scope,
          { role: 'user', content: trimmed },
          { role: 'assistant', content: final.answer },
        )
      } else {
        entry.answer = errorText(outcome.error.code, 'reason' in outcome.error.details ? outcome.error.details.reason as string : undefined)
        entry.status = 'error'
      }
    } catch (cause) {
      if (!scope.isCurrent() || active !== controller || cause instanceof AbortedError) return
      entry.answer = cause instanceof ApiError ? errorText(cause.code)
        : cause instanceof TimeoutError ? errorText('LLM_UNAVAILABLE', 'timeout')
        : cause instanceof ChatStreamInterruptedError ? errorText('LLM_UNAVAILABLE', 'stream_interrupted')
        : errorText('INTERNAL_ERROR')
      entry.status = 'error'
    } finally {
      if (active === controller) {
        active = null
        sending.value = false
      }
    }
  }

  const currentVersion = computed(() => [...entries.value].reverse().find((entry) => entry.status === 'answered' || entry.status === 'not_covered')?.graphVersion)
  onScopeDispose(stop)
  return { entries, question, sending, currentVersion, ask, stop }
}
