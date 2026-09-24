import { defineStore } from 'pinia'
import { ref, shallowRef } from 'vue'
import type { components } from '../../../contracts/v1/generated/typescript/openapi'

type GraphExchange = components['schemas']['GraphExchange']
type ChatTurn = components['schemas']['ChatTurn']

/**
 * 一次课程作用域：同一课程的一次选中。切课或离开课程后作用域失效，
 * 其 signal 被中止，经它提交的结果一律丢弃。
 */
export interface CourseRequestScope {
  readonly courseId: string
  readonly signal: AbortSignal
  isCurrent(): boolean
}

/**
 * 当前课程上下文与课程作用域内的状态。
 *
 * 本 store 不发请求。组件不直接发请求，也不直接写图谱/问答槽位；
 * 由 composables 先 `beginRequest()` 取得作用域，把 `scope.signal` 交给 HTTP 客户端，
 * 响应回来后经 `setGraph` / `appendChatTurns` / `commit` 提交——作用域已失效则丢弃。
 * 失效按作用域代次判断而不只比 courseId，所以 A→B→A 时第一次 A 的晚到响应也会被丢弃。
 */
export const useCourseStore = defineStore('course', () => {
  const courseId = ref<string | null>(null)
  // 图谱体量大且整体替换，不需要深层响应
  const graph = shallowRef<GraphExchange | null>(null)
  // 问答多轮历史由客户端维护并随请求提交（specs/grounded-qa.md Q8）
  const chatHistory = ref<ChatTurn[]>([])

  let generation = 0
  let controller = new AbortController()
  // 只认本 store 签发的作用域，调用方自造的对象无法绕过代次校验
  const issued = new WeakMap<CourseRequestScope, number>()

  function selectCourse(id: string | null): void {
    if (id === courseId.value) return
    controller.abort()
    controller = new AbortController()
    generation += 1
    courseId.value = id
    graph.value = null
    chatHistory.value = []
  }

  function beginRequest(): CourseRequestScope {
    const current = courseId.value
    if (current === null) throw new Error('未选择课程，不能开启课程请求作用域')
    const owner = generation
    const scope: CourseRequestScope = Object.freeze({
      courseId: current,
      signal: controller.signal,
      isCurrent: () => owner === generation,
    })
    issued.set(scope, owner)
    return scope
  }

  /** 作用域仍有效时执行写入并返回 true，否则丢弃并返回 false。 */
  function commit(scope: CourseRequestScope, apply: () => void): boolean {
    if (issued.get(scope) !== generation) return false
    apply()
    return true
  }

  function setGraph(scope: CourseRequestScope, next: GraphExchange): boolean {
    // 图谱按 course_id 隔离，不接收别的课程的数据
    if (next.course_id !== scope.courseId) return false
    return commit(scope, () => {
      graph.value = next
    })
  }

  function appendChatTurns(scope: CourseRequestScope, ...turns: ChatTurn[]): boolean {
    return commit(scope, () => {
      chatHistory.value.push(...turns)
    })
  }

  return { courseId, graph, chatHistory, selectCourse, beginRequest, commit, setGraph, appendChatTurns }
})
