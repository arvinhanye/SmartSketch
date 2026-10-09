import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { keepCanvasOutOfTabOrder } from '../../src/frontend/src/graph/a11y'
import { createGraphLifecycle, type CanvasGraphFactory } from '../../src/frontend/src/graph/lifecycle'
import { FakeEnhancedGraph } from './fakeEnhancedGraph'

// UI-QA-01：G6 把每层 canvas 设成 tabindex=1，成了页面最先的 4 个 Tab 停靠点；画布不是键盘停靠点（规格：画布键盘约定）。
const tick = () => new Promise<void>((resolve) => setTimeout(resolve, 0))
function canvas(tab = '1'): HTMLCanvasElement {
  const el = document.createElement('canvas')
  el.setAttribute('tabindex', tab)
  return el
}

describe('画布不进入 Tab 顺序', () => {
  it('已有的 canvas 立即改为 tabindex=-1', () => {
    const box = document.createElement('div')
    box.append(canvas(), canvas())
    const stop = keepCanvasOutOfTabOrder(box)
    expect([...box.querySelectorAll('canvas')].map((c) => c.getAttribute('tabindex'))).toEqual(['-1', '-1'])
    stop()
  })
  it('之后加入的 canvas、被改回的 tabindex 也改为 -1', async () => {
    const box = document.createElement('div')
    const stop = keepCanvasOutOfTabOrder(box)
    const later = canvas()
    box.append(later)
    await tick()
    expect(later.getAttribute('tabindex')).toBe('-1')
    later.setAttribute('tabindex', '1')
    await tick()
    expect(later.getAttribute('tabindex')).toBe('-1')
    stop()
  })
  it('停止后不再干预', async () => {
    const box = document.createElement('div')
    keepCanvasOutOfTabOrder(box)()
    const later = canvas()
    box.append(later)
    await tick()
    expect(later.getAttribute('tabindex')).toBe('1')
  })
})

describe('生命周期接入', () => {
  beforeEach(() => {
    vi.stubGlobal('ResizeObserver', class { observe() {} unobserve() {} disconnect() {} })
    vi.stubGlobal('requestAnimationFrame', () => 1)
    vi.stubGlobal('cancelAnimationFrame', () => undefined)
  })
  afterEach(() => vi.unstubAllGlobals())
  it('图谱创建的 canvas 不进入 Tab 顺序，销毁后停止监听', async () => {
    const factory: CanvasGraphFactory = (init) => new FakeEnhancedGraph({}, init)
    const el = document.createElement('div')
    Object.defineProperty(el, 'clientWidth', { configurable: true, value: 800 })
    Object.defineProperty(el, 'clientHeight', { configurable: true, value: 600 })
    const life = createGraphLifecycle(el, { data: { nodes: [], edges: [] }, factory })
    const drawn = canvas()
    el.append(drawn)
    await tick()
    expect(drawn.getAttribute('tabindex')).toBe('-1')
    life.destroy()
    const after = canvas()
    el.append(after)
    await tick()
    expect(after.getAttribute('tabindex')).toBe('1')
  })
})
