import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it } from 'vitest'
import type { components } from '../../src/contracts/v1/generated/typescript/openapi'
import { useCourseStore } from '../../src/frontend/src/stores/course'

type GraphExchange = components['schemas']['GraphExchange']
type ChatTurn = components['schemas']['ChatTurn']

function graphOf(courseId: string): GraphExchange {
  return {
    format_version: '1.0',
    course_id: courseId,
    graph_version: 1,
    generated_at: '2026-09-24T00:00:00Z',
    nodes: [],
    edges: [],
  }
}

const turns: ChatTurn[] = [
  { role: 'user', content: '什么是栈？' },
  { role: 'assistant', content: '栈是后进先出的线性表。' },
]

// 可手动 resolve 的 promise，用来模拟响应在切课之后才到达
function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>((r) => {
    resolve = r
  })
  return { promise, resolve }
}

// 模拟以后 composable 的写法：在作用域内发起、等待、再经作用域提交
async function loadGraph(pending: Promise<GraphExchange>) {
  const store = useCourseStore()
  const scope = store.beginRequest()
  return store.setGraph(scope, await pending)
}

describe('B04 课程上下文 store', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('初始没有课程，且无课程时不能开启请求作用域', () => {
    const store = useCourseStore()
    expect(store.courseId).toBeNull()
    expect(store.graph).toBeNull()
    expect(store.chatHistory).toEqual([])
    expect(() => store.beginRequest()).toThrow()
  })

  it('当前作用域内的响应正常写入图谱与问答槽位', () => {
    const store = useCourseStore()
    store.selectCourse('A')
    const scope = store.beginRequest()
    expect(scope.courseId).toBe('A')
    expect(scope.signal.aborted).toBe(false)
    expect(scope.isCurrent()).toBe(true)

    expect(store.setGraph(scope, graphOf('A'))).toBe(true)
    expect(store.appendChatTurns(scope, ...turns)).toBe(true)
    expect(store.graph?.course_id).toBe('A')
    expect(store.chatHistory).toEqual(turns)
  })

  it('切到另一门课时清空图谱与问答', () => {
    const store = useCourseStore()
    store.selectCourse('A')
    const scope = store.beginRequest()
    store.setGraph(scope, graphOf('A'))
    store.appendChatTurns(scope, ...turns)

    store.selectCourse('B')
    expect(store.courseId).toBe('B')
    expect(store.graph).toBeNull()
    expect(store.chatHistory).toEqual([])
  })

  it('切课时中止旧作用域的 signal，新作用域不受影响', () => {
    const store = useCourseStore()
    store.selectCourse('A')
    const scopeA = store.beginRequest()
    store.selectCourse('B')
    const scopeB = store.beginRequest()

    expect(scopeA.signal.aborted).toBe(true)
    expect(scopeA.isCurrent()).toBe(false)
    expect(scopeB.signal.aborted).toBe(false)
    expect(scopeB.isCurrent()).toBe(true)
  })

  it('A 的晚到响应在切到 B 后被丢弃，B 的数据不受影响', async () => {
    const store = useCourseStore()
    store.selectCourse('A')
    const slowA = deferred<GraphExchange>()
    const loadingA = loadGraph(slowA.promise)

    store.selectCourse('B')
    const scopeB = store.beginRequest()
    store.setGraph(scopeB, graphOf('B'))
    store.appendChatTurns(scopeB, ...turns)

    slowA.resolve(graphOf('A'))
    expect(await loadingA).toBe(false)
    expect(store.graph?.course_id).toBe('B')
    expect(store.chatHistory).toEqual(turns)
  })

  it('A→B→A 时第一次 A 的晚到响应不写入第二次 A', async () => {
    const store = useCourseStore()
    store.selectCourse('A')
    const firstA = store.beginRequest()
    const slowGraph = deferred<GraphExchange>()
    const loadingA = loadGraph(slowGraph.promise)

    store.selectCourse('B')
    store.selectCourse('A')
    const secondA = store.beginRequest()
    expect(firstA.courseId).toBe(secondA.courseId)
    expect(firstA.isCurrent()).toBe(false)
    expect(firstA.signal.aborted).toBe(true)

    slowGraph.resolve(graphOf('A'))
    expect(await loadingA).toBe(false)
    expect(store.appendChatTurns(firstA, ...turns)).toBe(false)
    expect(store.graph).toBeNull()
    expect(store.chatHistory).toEqual([])
    expect(secondA.isCurrent()).toBe(true)
  })

  it('重复选择同一课程是幂等的：不清空、不中止', () => {
    const store = useCourseStore()
    store.selectCourse('A')
    const scope = store.beginRequest()
    store.setGraph(scope, graphOf('A'))
    store.appendChatTurns(scope, ...turns)

    store.selectCourse('A')
    expect(scope.signal.aborted).toBe(false)
    expect(scope.isCurrent()).toBe(true)
    expect(store.graph?.course_id).toBe('A')
    expect(store.chatHistory).toEqual(turns)
  })

  it('选择 null（离开课程）清空状态并中止作用域', () => {
    const store = useCourseStore()
    store.selectCourse('A')
    const scope = store.beginRequest()
    store.setGraph(scope, graphOf('A'))
    store.appendChatTurns(scope, ...turns)

    store.selectCourse(null)
    expect(store.courseId).toBeNull()
    expect(store.graph).toBeNull()
    expect(store.chatHistory).toEqual([])
    expect(scope.signal.aborted).toBe(true)
    expect(store.setGraph(scope, graphOf('A'))).toBe(false)
    expect(() => store.beginRequest()).toThrow()
  })

  it('同一作用域内的多个请求共享同一个 signal，切课时一起中止', () => {
    const store = useCourseStore()
    store.selectCourse('A')
    const first = store.beginRequest()
    const second = store.beginRequest()
    expect(second.signal).toBe(first.signal)
    store.selectCourse('B')
    expect(first.signal.aborted && second.signal.aborted).toBe(true)
  })

  it('课程 ID 与作用域不符的图谱被拒收', () => {
    const store = useCourseStore()
    store.selectCourse('A')
    const scope = store.beginRequest()
    expect(store.setGraph(scope, graphOf('B'))).toBe(false)
    expect(store.graph).toBeNull()
  })

  it('commit 只在作用域有效时执行写入回调', () => {
    const store = useCourseStore()
    store.selectCourse('A')
    const scope = store.beginRequest()
    let runs = 0
    expect(store.commit(scope, () => runs++)).toBe(true)
    store.selectCourse('B')
    expect(store.commit(scope, () => runs++)).toBe(false)
    expect(runs).toBe(1)
  })

  it('非 store 签发的作用域对象不能写入', () => {
    const store = useCourseStore()
    store.selectCourse('A')
    const forged = { courseId: 'A', signal: new AbortController().signal, isCurrent: () => true }
    expect(store.setGraph(forged, graphOf('A'))).toBe(false)
    expect(store.appendChatTurns(forged, ...turns)).toBe(false)
    expect(store.graph).toBeNull()
    expect(store.chatHistory).toEqual([])
  })
})
