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

// ---------------------------------------------------------------- UI-GRAPH-STABLE-03：只改关系时位置不动
describe('useGraphLayout：stable 模式（教师页）', () => {
  const withEdges = (ids: string[], edges: Array<[string, string]>, chapterOrder = ['c1']): LayoutSource => ({
    nodes: ids.map((id) => ({ id, chapter: 'c1' })),
    edges: edges.map(([s, t], i) => ({ id: `e${i}`, source: s, target: t, type: 'CONTAINS' })) as LayoutSource['edges'],
    chapterOrder,
  })
  async function settled(ids: string[], edges: Array<[string, string]> = []) {
    const src = ref<LayoutSource | null>(withEdges(ids, edges))
    const { engine, calls, release } = makeEngine()
    const layout = useGraphLayout(() => src.value, engine, false, { stable: true })
    await flushPromises()
    release()
    await flushPromises()
    return { src, layout, calls, release }
  }

  it('只增删关系：不重新计算，位置对象原样保留（画布因此不重建），并标记布局已过期', async () => {
    const { src, layout, calls } = await settled(['a', 'b', 'c'])
    const before = layout.positions.value
    expect(layout.stale.value).toBe(false)
    src.value = withEdges(['a', 'b', 'c'], [['a', 'b']])
    await flushPromises()
    expect(layout.positions.value).toBe(before)
    expect(calls).toHaveLength(1)
    expect(layout.stale.value).toBe(true)
    // 关系改回原样：不再算过期
    src.value = withEdges(['a', 'b', 'c'], [])
    await flushPromises()
    expect(layout.stale.value).toBe(false)
    expect(layout.positions.value).toBe(before)
  })

  it('删掉知识点：其余知识点的位置不动，不重新计算', async () => {
    const { src, layout, calls } = await settled(['a', 'b', 'c'], [['a', 'b']])
    const before = layout.positions.value
    src.value = withEdges(['a', 'c'], [])
    await flushPromises()
    expect(layout.positions.value).toBe(before)
    expect(calls).toHaveLength(1)
  })

  it('出现新知识点、知识点换了章节或章节顺序变了：重新计算', async () => {
    const { src, layout, calls, release } = await settled(['a', 'b'])
    src.value = withEdges(['a', 'b', 'n'], [])
    await flushPromises()
    expect(layout.positions.value).toBeNull()
    release()
    await flushPromises()
    expect([...layout.positions.value!.keys()].sort()).toEqual(['a', 'b', 'n'])
    expect(calls).toHaveLength(2)

    // 替身引擎按章节各调一次，所以这里不数调用次数，只看“位置先回到 null 再给出新的”
    const moved = layout.positions.value
    src.value = { ...withEdges(['a', 'b', 'n'], []), nodes: [{ id: 'a', chapter: 'c2' }, { id: 'b', chapter: 'c1' }, { id: 'n', chapter: 'c1' }] }
    await flushPromises()
    expect(layout.positions.value).toBeNull()
    // 多个章节时引擎按章节依次调用：放行几轮直到算完
    for (let round = 0; round < 4; round += 1) {
      release()
      await flushPromises()
    }
    expect(layout.positions.value).not.toBeNull()
    expect(layout.positions.value).not.toBe(moved)

    src.value = { ...src.value!, chapterOrder: ['c2', 'c1'] }
    await flushPromises()
    expect(layout.positions.value).toBeNull()
    // 多个章节时引擎按章节依次调用：放行几轮直到算完
    for (let round = 0; round < 4; round += 1) {
      release()
      await flushPromises()
    }
    expect(layout.positions.value).not.toBeNull()
    expect(layout.stale.value).toBe(false)
  })

  it('relayout()：按当前关系重新计算，过期标记清除；源为 null 后再来同一批知识点也会重新计算', async () => {
    const { src, layout, calls, release } = await settled(['a', 'b'])
    src.value = withEdges(['a', 'b'], [['a', 'b']])
    await flushPromises()
    expect(layout.stale.value).toBe(true)
    layout.relayout()
    await flushPromises()
    expect(layout.positions.value).toBeNull()
    release()
    await flushPromises()
    expect(calls).toHaveLength(2)
    expect(layout.stale.value).toBe(false)

    src.value = null
    await flushPromises()
    expect(layout.positions.value).toBeNull()
    src.value = withEdges(['a', 'b'], [['a', 'b']])
    await flushPromises()
    release()
    await flushPromises()
    expect(calls).toHaveLength(3)
  })

  it('不开 stable（学生页）时行为不变：关系一变就重新计算', async () => {
    const src = ref<LayoutSource | null>(withEdges(['a', 'b'], []))
    const { engine, calls, release } = makeEngine()
    const layout = useGraphLayout(() => src.value, engine)
    await flushPromises()
    release()
    await flushPromises()
    src.value = withEdges(['a', 'b'], [['a', 'b']])
    await flushPromises()
    expect(layout.positions.value).toBeNull()
    expect(calls).toHaveLength(2)
  })
})
