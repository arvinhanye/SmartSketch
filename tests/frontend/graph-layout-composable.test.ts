import { flushPromises } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import { ref } from 'vue'
import type { DagreEngine } from '../../src/frontend/src/graph/chapterLayout'
import { useGraphLayout, type LayoutSource } from '../../src/frontend/src/composables/useGraphLayout'

/** 替身引擎：每个节点按序号排成一行，可手动放行 */
function makeEngine() {
  const waiting: Array<() => void> = []
  const calls: string[][] = []
  const engine: DagreEngine = (ids) => {
    calls.push(ids)
    return new Promise((resolve) => {
      waiting.push(() => resolve(new Map(ids.map((id, i) => [id, { x: i * 100, y: 0 }]))))
    })
  }
  return { engine, calls, release: () => waiting.splice(0).forEach((fn) => fn()) }
}

const source = (ids: string[]): LayoutSource => ({
  nodes: ids.map((id) => ({ id, chapter: 'c1' })),
  edges: [],
  chapterOrder: ['c1'],
})

describe('useGraphLayout', () => {
  it('源为 null 时没有位置；源到达后异步算出位置', async () => {
    const src = ref<LayoutSource | null>(null)
    const { engine, release } = makeEngine()
    const { positions } = useGraphLayout(() => src.value, engine)
    expect(positions.value).toBeNull()
    src.value = source(['a', 'b'])
    await flushPromises()
    expect(positions.value).toBeNull() // 引擎还没放行
    release()
    await flushPromises()
    expect([...positions.value!.keys()].sort()).toEqual(['a', 'b'])
  })
  it('期间源又变化时丢弃过期结果', async () => {
    const src = ref<LayoutSource | null>(source(['a']))
    const { engine, release } = makeEngine()
    const { positions } = useGraphLayout(() => src.value, engine)
    await flushPromises()
    src.value = source(['x', 'y'])
    await flushPromises()
    release() // 两次计算同时放行：旧的先完成也不能覆盖新的
    await flushPromises()
    expect([...positions.value!.keys()].sort()).toEqual(['x', 'y'])
  })
  it('源重新计算期间位置回到 null（画布据此等待，而不是用旧位置画新图）', async () => {
    const src = ref<LayoutSource | null>(source(['a']))
    const { engine, release } = makeEngine()
    const { positions } = useGraphLayout(() => src.value, engine)
    await flushPromises()
    release()
    await flushPromises()
    expect(positions.value).not.toBeNull()
    src.value = source(['b'])
    await flushPromises()
    expect(positions.value).toBeNull()
  })
  it('引擎失败时记录错误、位置保持 null', async () => {
    const src = ref<LayoutSource | null>(source(['a']))
    const failing: DagreEngine = () => Promise.reject(new Error('layout failed'))
    const { positions, error } = useGraphLayout(() => src.value, failing)
    await flushPromises()
    expect(positions.value).toBeNull()
    expect(error.value).toBeInstanceOf(Error)
  })
})
