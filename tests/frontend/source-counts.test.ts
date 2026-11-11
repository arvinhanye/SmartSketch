import { flushPromises } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'
import { effectScope, ref } from 'vue'
import type { KnowledgeDetailApi } from '../../src/frontend/src/api/knowledgeDetail'
import { useSourceCounts } from '../../src/frontend/src/composables/useSourceCounts'

/**
 * DEDUP-FIX F2：知识点来源数量的按需读取与缓存（草稿图谱的节点不带 `source_refs`）。
 */
function deferred<T>() {
  let resolve!: (value: T) => void
  let reject!: (reason: unknown) => void
  const promise = new Promise<T>((res, rej) => {
    resolve = res
    reject = rej
  })
  return { promise, resolve, reject }
}
const detail = (count: number) => ({ source_refs: Array.from({ length: count }, (_, i) => ({ chunk_id: `c${i}` })) }) as never

function setup(get: KnowledgeDetailApi['get'], course = 'c1') {
  const courseId = ref<string | null>(course)
  const scope = effectScope()
  const api = { get: vi.fn(get) }
  const counts = scope.run(() => useSourceCounts({ api, courseId }))!
  return { counts, api, courseId, scope }
}

describe('useSourceCounts', () => {
  it('要求时才读；读取中、数量（含 0）与失败分开；失败不冒充 0', async () => {
    const pending = deferred<never>()
    const { counts, api } = setup(async (_cid, kid) => (kid === 'a' ? detail(2) : kid === 'b' ? detail(0) : pending.promise))
    expect(counts.of({ id: 'a', revision: 1 })).toBeUndefined()
    expect(api.get).not.toHaveBeenCalled()

    counts.ensure([{ id: 'a', revision: 1 }, { id: 'b', revision: 1 }, { id: 'c', revision: 1 }])
    expect(counts.of({ id: 'a', revision: 1 })).toEqual({ state: 'loading' })
    await flushPromises()
    expect(counts.of({ id: 'a', revision: 1 })).toEqual({ state: 'ready', count: 2 })
    expect(counts.of({ id: 'b', revision: 1 })).toEqual({ state: 'ready', count: 0 })
    expect(counts.of({ id: 'c', revision: 1 })).toEqual({ state: 'loading' })
    pending.reject(new Error('boom'))
    await flushPromises()
    expect(counts.of({ id: 'c', revision: 1 })).toEqual({ state: 'error' })
    expect(api.get.mock.calls.map((call) => call.slice(0, 2))).toEqual([['c1', 'a'], ['c1', 'b'], ['c1', 'c']])
  })

  it('同一修订重复要求不重复请求；失败的会重试；修订号变了重新读', async () => {
    let fail = true
    const { counts, api } = setup(async (_cid, kid) => {
      if (kid === 'x' && fail) throw new Error('once')
      return detail(1)
    })
    counts.ensure([{ id: 'a', revision: 1 }])
    counts.ensure([{ id: 'a', revision: 1 }])
    await flushPromises()
    counts.ensure([{ id: 'a', revision: 1 }])
    expect(api.get).toHaveBeenCalledTimes(1)

    counts.ensure([{ id: 'x', revision: 1 }])
    await flushPromises()
    expect(counts.of({ id: 'x', revision: 1 })).toEqual({ state: 'error' })
    fail = false
    counts.ensure([{ id: 'x', revision: 1 }])
    await flushPromises()
    expect(counts.of({ id: 'x', revision: 1 })).toEqual({ state: 'ready', count: 1 })

    counts.ensure([{ id: 'a', revision: 2 }])
    await flushPromises()
    expect(api.get).toHaveBeenCalledTimes(4)
    expect(counts.of({ id: 'a', revision: 2 })).toEqual({ state: 'ready', count: 1 })
  })

  it('invalidate 丢弃该知识点各修订的缓存，下次要求时重新读', async () => {
    const { counts, api } = setup(async () => detail(3))
    counts.ensure([{ id: 'a', revision: 1 }, { id: 'ab', revision: 1 }])
    await flushPromises()
    counts.invalidate(['a'])
    expect(counts.of({ id: 'a', revision: 1 })).toBeUndefined()
    // 前缀相同的另一个知识点不受影响
    expect(counts.of({ id: 'ab', revision: 1 })).toEqual({ state: 'ready', count: 3 })
    counts.ensure([{ id: 'a', revision: 1 }])
    await flushPromises()
    expect(api.get).toHaveBeenCalledTimes(3)
  })

  it('换课程：清空缓存，上一门课迟到的响应不写进来；在途请求被中止', async () => {
    const slow = deferred<never>()
    const signals: AbortSignal[] = []
    const { counts, courseId } = setup(async (cid, _kid, control) => {
      if (control?.signal) signals.push(control.signal)
      return cid === 'c1' ? slow.promise : detail(5)
    })
    counts.ensure([{ id: 'a', revision: 1 }])
    courseId.value = 'c2'
    await flushPromises()
    expect(signals[0]!.aborted).toBe(true)
    expect(counts.of({ id: 'a', revision: 1 })).toBeUndefined()
    slow.resolve(detail(9))
    await flushPromises()
    expect(counts.of({ id: 'a', revision: 1 })).toBeUndefined()
    counts.ensure([{ id: 'a', revision: 1 }])
    await flushPromises()
    expect(counts.of({ id: 'a', revision: 1 })).toEqual({ state: 'ready', count: 5 })
  })

  it('没有详情接口或没有课程时什么都不做；响应里没有来源数组按失败处理', async () => {
    const none = effectScope().run(() => useSourceCounts({ api: null, courseId: 'c1' }))!
    none.ensure([{ id: 'a', revision: 1 }])
    expect(none.of({ id: 'a', revision: 1 })).toBeUndefined()

    const { counts } = setup(async () => ({}) as never)
    counts.ensure([{ id: 'a', revision: 1 }])
    await flushPromises()
    expect(counts.of({ id: 'a', revision: 1 })).toEqual({ state: 'error' })
  })
})
