import { mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi, type MockInstance } from 'vitest'
import { defineComponent, h, KeepAlive, nextTick, ref, type Ref } from 'vue'
import { createMemoryHistory, createRouter, RouterView } from 'vue-router'
import GraphCanvas from '../../src/frontend/src/components/GraphCanvas.vue'
import {
  edgeElementId,
  nodeElementId,
  RELATION_STYLES,
  type G6Edge,
  type G6Node,
  type RelationType,
} from '../../src/frontend/src/graph/adapter'
import {
  buildGraphOptions,
  createGraphLifecycle,
  GRAPH_FACTORY_KEY,
  type CanvasGraph,
  type CanvasGraphFactory,
  type CanvasGraphInit,
  type GraphCanvasData,
  type LifecycleStatus,
} from '../../src/frontend/src/graph/lifecycle'

// ---------- 测试替身 ----------

interface Deferred {
  promise: Promise<void>
  resolve: () => void
  reject: (error: unknown) => void
}

function deferred(): Deferred {
  let resolve!: () => void
  let reject!: (error: unknown) => void
  const promise = new Promise<void>((res, rej) => {
    resolve = res
    reject = rej
  })
  return { promise, resolve, reject }
}

type Handler = (event: { target?: { id?: string } }) => void

/** 只实现生命周期用到的 G6 Graph 子集，记录每次调用 */
class FakeGraph implements CanvasGraph {
  destroyed = false
  calls: string[] = []
  data: GraphCanvasData
  size: [number, number]
  handlers = new Map<string, Handler[]>()
  /** 为真时 render 挂起，直到测试手动放行 */
  holdRender = false
  pendingRenders: Deferred[] = []
  renderError: unknown = null

  constructor(readonly init: CanvasGraphInit) {
    this.data = init.data
    this.size = [init.width, init.height]
  }

  render(): Promise<void> {
    this.calls.push('render')
    if (this.renderError !== null) return Promise.reject(this.renderError)
    if (!this.holdRender) return Promise.resolve()
    const d = deferred()
    this.pendingRenders.push(d)
    return d.promise
  }

  setData(data: GraphCanvasData): void {
    this.calls.push('setData')
    this.data = data
  }

  setSize(width: number, height: number): void {
    this.calls.push(`setSize ${width}x${height}`)
    this.size = [width, height]
  }

  fitView(): Promise<void> {
    this.calls.push('fitView')
    return Promise.resolve()
  }

  on(event: string, handler: Handler): this {
    this.handlers.set(event, [...(this.handlers.get(event) ?? []), handler])
    return this
  }

  destroy(): void {
    this.calls.push('destroy')
    this.destroyed = true
    this.handlers.clear()
  }

  emit(event: string, payload: { target?: { id?: string } }): void {
    for (const handler of this.handlers.get(event) ?? []) handler(payload)
  }
}

interface FactoryControl {
  factory: CanvasGraphFactory
  graphs: FakeGraph[]
  /** 为真时工厂挂起（模拟 G6 按需加载），直到 release() */
  hold: boolean
  release(): void
  error: unknown
  configure: ((graph: FakeGraph) => void) | null
}

function fakeFactory(): FactoryControl {
  const waiting: Array<() => void> = []
  const control: FactoryControl = {
    graphs: [],
    hold: false,
    error: null,
    configure: null,
    release() {
      while (waiting.length > 0) waiting.shift()!()
    },
    factory: (init) => {
      if (control.error !== null) return Promise.reject(control.error)
      const make = () => {
        const graph = new FakeGraph(init)
        control.configure?.(graph)
        control.graphs.push(graph)
        return graph
      }
      if (!control.hold) return make()
      return new Promise<CanvasGraph>((resolve) => waiting.push(() => resolve(make())))
    },
  }
  return control
}

class FakeResizeObserver {
  static instances: FakeResizeObserver[] = []
  observed: Element[] = []
  disconnected = false
  constructor(readonly callback: ResizeObserverCallback) {
    FakeResizeObserver.instances.push(this)
  }
  observe(target: Element): void {
    this.observed.push(target)
  }
  unobserve(): void {}
  disconnect(): void {
    this.disconnected = true
    this.observed = []
  }
  trigger(): void {
    this.callback([], this as unknown as ResizeObserver)
  }
}

let frames = new Map<number, FrameRequestCallback>()
let nextFrame = 1

function flushFrames(): void {
  const current = [...frames.values()]
  frames = new Map()
  for (const callback of current) callback(0)
}

function setBox(element: HTMLElement, width: number, height: number): void {
  Object.defineProperty(element, 'clientWidth', { configurable: true, value: width })
  Object.defineProperty(element, 'clientHeight', { configurable: true, value: height })
}

/** 让挂起的 promise 链走完 */
async function settle(): Promise<void> {
  for (let i = 0; i < 10; i += 1) await Promise.resolve()
  await new Promise((resolve) => setTimeout(resolve, 0))
}

function node(id: string, name = `知识点 ${id}`): G6Node {
  return {
    id: nodeElementId(id),
    data: {
      kpId: id,
      name,
      type: 'concept',
      level: 0,
      chapterId: 'ch3',
      status: 'draft',
      confidence: 0.9,
      source: 'ai',
      locked: false,
    },
  }
}

function edge(id: string, type: RelationType, from: string, to: string): G6Edge {
  const s = RELATION_STYLES[type]
  return {
    id: edgeElementId(id),
    source: nodeElementId(from),
    target: nodeElementId(to),
    data: { relationId: id, type, directed: s.directed, status: 'draft', confidence: 0.8, source: 'ai', downgraded: false },
    style: { stroke: s.stroke, lineWidth: s.lineWidth, lineDash: [...s.lineDash], endArrow: s.directed, labelText: s.label },
  }
}

function sample(): GraphCanvasData {
  return {
    nodes: [node('push'), node('queue'), node('stack')],
    edges: [edge('r1', 'CONTAINS', 'stack', 'push'), edge('r2', 'PREREQUISITE', 'stack', 'queue')],
  }
}

function container(width = 800, height = 600): HTMLElement {
  const el = document.createElement('div')
  document.body.appendChild(el)
  setBox(el, width, height)
  return el
}

let addSpy: MockInstance<Window['addEventListener']>
let removeSpy: MockInstance<Window['removeEventListener']>

beforeEach(() => {
  FakeResizeObserver.instances = []
  frames = new Map()
  nextFrame = 1
  vi.stubGlobal('ResizeObserver', FakeResizeObserver)
  vi.stubGlobal('requestAnimationFrame', (callback: FrameRequestCallback) => {
    const id = nextFrame++
    frames.set(id, callback)
    return id
  })
  vi.stubGlobal('cancelAnimationFrame', (id: number) => {
    frames.delete(id)
  })
  addSpy = vi.spyOn(window, 'addEventListener')
  removeSpy = vi.spyOn(window, 'removeEventListener')
})

afterEach(() => {
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
  document.body.innerHTML = ''
})

// ---------- 生命周期 ----------

describe('H04 挂载', () => {
  it('按容器尺寸建图、交入数据并渲染，状态经 rendering 到 ready', async () => {
    const f = fakeFactory()
    const statuses: LifecycleStatus[] = []
    const el = container(800, 600)
    const life = createGraphLifecycle(el, { data: sample(), factory: f.factory, onStatus: (s) => statuses.push(s) })
    await settle()

    expect(f.graphs).toHaveLength(1)
    const g = f.graphs[0]!
    expect(g.init.container).toBe(el)
    expect(g.size).toEqual([800, 600])
    expect(g.data).toEqual(sample())
    expect(g.calls).toEqual(['render'])
    expect(life.status).toBe('ready')
    expect(statuses).toEqual(['rendering', 'ready'])
    expect(FakeResizeObserver.instances).toHaveLength(1)
    expect(FakeResizeObserver.instances[0]!.observed).toEqual([el])
    life.destroy()
  })

  it('交给 G6 的是副本：G6 改写数据（如布局写坐标）不影响调用方', async () => {
    const f = fakeFactory()
    const input = sample()
    const snapshot = JSON.parse(JSON.stringify(input)) as GraphCanvasData
    const life = createGraphLifecycle(container(), { data: input, factory: f.factory })
    await settle()

    const given = f.graphs[0]!.data
    expect(given).not.toBe(input)
    expect(given.nodes[0]).not.toBe(input.nodes[0])
    expect(given.nodes[0]!.data).not.toBe(input.nodes[0]!.data)
    expect(given.edges[0]!.style).not.toBe(input.edges[0]!.style)
    expect(given.edges[0]!.style.lineDash).not.toBe(input.edges[0]!.style.lineDash)
    ;(given.nodes[0] as { style?: unknown }).style = { x: 1, y: 2 }
    given.edges[0]!.style.lineDash.push(9)
    expect(input).toEqual(snapshot)

    const next = sample()
    const nextSnapshot = JSON.parse(JSON.stringify(next)) as GraphCanvasData
    life.update(next)
    await settle()
    expect(f.graphs[0]!.data).not.toBe(next)
    f.graphs[0]!.data.nodes.pop()
    expect(next).toEqual(nextSnapshot)
    life.destroy()
  })

  it('容器尺寸为 0（隐藏页签）时推迟建图，出现尺寸后再按新尺寸建图', async () => {
    const f = fakeFactory()
    const el = container(0, 0)
    const life = createGraphLifecycle(el, { data: sample(), factory: f.factory })
    await settle()
    expect(f.graphs).toHaveLength(0)
    expect(life.status).toBe('waiting')

    FakeResizeObserver.instances[0]!.trigger()
    flushFrames()
    await settle()
    expect(f.graphs).toHaveLength(0)

    setBox(el, 640, 480)
    FakeResizeObserver.instances[0]!.trigger()
    flushFrames()
    await settle()
    expect(f.graphs).toHaveLength(1)
    expect(f.graphs[0]!.size).toEqual([640, 480])
    expect(life.status).toBe('ready')
    life.destroy()
  })

  it('默认建图参数：缩放、拖拽画布、拖拽节点、适应视口、节点标签取知识点名', () => {
    const el = container()
    const data = sample()
    const options = buildGraphOptions({ container: el, width: 320, height: 240, data })
    expect(options.container).toBe(el)
    expect(options.width).toBe(320)
    expect(options.height).toBe(240)
    expect(options.data).toBe(data)
    expect(options.behaviors).toEqual(expect.arrayContaining(['zoom-canvas', 'drag-canvas', 'drag-element']))
    expect(options.autoFit).toBe('view')
    expect(options.animation).toBe(false)
    expect(options.transforms).toEqual(['process-parallel-edges'])
    const labelText = (options.node?.style as unknown as { labelText: (d: G6Node) => string }).labelText
    expect(labelText(node('stack', '栈'))).toBe('栈')
  })
})

describe('H04 更新', () => {
  it('update 调 setData 后重渲染，传入最新数据', async () => {
    const f = fakeFactory()
    const life = createGraphLifecycle(container(), { data: sample(), factory: f.factory })
    await settle()
    const next: GraphCanvasData = { nodes: [node('stack')], edges: [] }
    life.update(next)
    await settle()
    expect(f.graphs).toHaveLength(1)
    expect(f.graphs[0]!.calls).toEqual(['render', 'setData', 'render'])
    expect(f.graphs[0]!.data).toEqual(next)
    expect(life.status).toBe('ready')
    life.destroy()
  })

  it('渲染进行中连续更新只合并为一次，且落在最后一次数据', async () => {
    const f = fakeFactory()
    f.configure = (g) => {
      g.holdRender = true
    }
    const life = createGraphLifecycle(container(), { data: sample(), factory: f.factory })
    await settle()
    const g = f.graphs[0]!
    expect(g.calls).toEqual(['render'])

    life.update({ nodes: [node('a')], edges: [] })
    life.update({ nodes: [node('b')], edges: [] })
    const last: GraphCanvasData = { nodes: [node('c')], edges: [] }
    life.update(last)
    await settle()
    expect(g.calls).toEqual(['render'])
    expect(life.status).toBe('rendering')

    g.pendingRenders.shift()!.resolve()
    await settle()
    expect(g.calls).toEqual(['render', 'setData', 'render'])
    expect(g.data).toEqual(last)
    g.pendingRenders.shift()!.resolve()
    await settle()
    expect(g.calls).toEqual(['render', 'setData', 'render'])
    expect(life.status).toBe('ready')
    life.destroy()
  })

  it('G6 尚在加载时的更新不丢：建图后画的是最新数据', async () => {
    const f = fakeFactory()
    f.hold = true
    const life = createGraphLifecycle(container(), { data: sample(), factory: f.factory })
    await settle()
    expect(f.graphs).toHaveLength(0)
    const last: GraphCanvasData = { nodes: [node('z')], edges: [] }
    life.update(last)
    f.release()
    await settle()
    expect(f.graphs).toHaveLength(1)
    expect(f.graphs[0]!.data).toEqual(last)
    life.destroy()
  })
})

describe('H04 resize', () => {
  it('容器变化后在下一帧 setSize 新尺寸并重新适应视口；同帧多次变化只处理一次', async () => {
    const f = fakeFactory()
    const el = container(800, 600)
    const life = createGraphLifecycle(el, { data: sample(), factory: f.factory })
    await settle()
    const g = f.graphs[0]!
    const observer = FakeResizeObserver.instances[0]!

    setBox(el, 1024, 700)
    observer.trigger()
    observer.trigger()
    observer.trigger()
    expect(g.calls).toEqual(['render'])
    flushFrames()
    await settle()
    expect(g.calls).toEqual(['render', 'setSize 1024x700', 'fitView'])
    life.destroy()
  })

  it('尺寸未变或变为 0（切到隐藏页签）时不调整，恢复可见后按新尺寸调整', async () => {
    const f = fakeFactory()
    const el = container(800, 600)
    const life = createGraphLifecycle(el, { data: sample(), factory: f.factory })
    await settle()
    const g = f.graphs[0]!
    const observer = FakeResizeObserver.instances[0]!

    observer.trigger()
    flushFrames()
    setBox(el, 0, 0)
    observer.trigger()
    flushFrames()
    await settle()
    expect(g.calls).toEqual(['render'])

    setBox(el, 500, 400)
    life.refreshSize()
    flushFrames()
    await settle()
    expect(g.calls).toEqual(['render', 'setSize 500x400', 'fitView'])
    life.destroy()
  })

  it('没有 ResizeObserver 时退回监听 window resize，销毁时移除', async () => {
    vi.stubGlobal('ResizeObserver', undefined)
    const f = fakeFactory()
    const el = container(800, 600)
    const life = createGraphLifecycle(el, { data: sample(), factory: f.factory })
    await settle()
    const added = addSpy.mock.calls.filter(([type]) => type === 'resize')
    expect(added).toHaveLength(1)

    setBox(el, 300, 200)
    window.dispatchEvent(new Event('resize'))
    flushFrames()
    await settle()
    expect(f.graphs[0]!.calls).toContain('setSize 300x200')

    life.destroy()
    const removed = removeSpy.mock.calls.filter(([type]) => type === 'resize')
    expect(removed).toHaveLength(1)
    expect(removed[0]![1]).toBe(added[0]![1])
  })
})

describe('H04 销毁', () => {
  it('销毁图实例、断开观察、取消待执行帧；重复销毁无副作用，之后的更新与 resize 都不再触达 G6', async () => {
    const f = fakeFactory()
    const el = container()
    const statuses: LifecycleStatus[] = []
    const life = createGraphLifecycle(el, { data: sample(), factory: f.factory, onStatus: (s) => statuses.push(s) })
    await settle()
    const g = f.graphs[0]!
    setBox(el, 900, 900)
    FakeResizeObserver.instances[0]!.trigger()
    expect(frames.size).toBe(1)

    life.destroy()
    life.destroy()
    expect(g.calls.filter((c) => c === 'destroy')).toHaveLength(1)
    expect(FakeResizeObserver.instances[0]!.disconnected).toBe(true)
    expect(frames.size).toBe(0)
    expect(life.status).toBe('destroyed')

    life.update(sample())
    life.refreshSize()
    flushFrames()
    await settle()
    expect(g.calls).toEqual(['render', 'destroy'])
    expect(statuses.at(-1)).toBe('destroyed')
    expect(f.graphs).toHaveLength(1)
  })

  it('G6 加载完成前销毁：迟到的图立即销毁，从不渲染', async () => {
    const f = fakeFactory()
    f.hold = true
    const life = createGraphLifecycle(container(), { data: sample(), factory: f.factory })
    await settle()
    life.destroy()
    f.release()
    await settle()
    expect(f.graphs).toHaveLength(1)
    expect(f.graphs[0]!.calls).toEqual(['destroy'])
    expect(life.status).toBe('destroyed')
  })

  it('渲染途中销毁：渲染随后失败也不报错、不回到 ready', async () => {
    const f = fakeFactory()
    f.configure = (g) => {
      g.holdRender = true
    }
    const statuses: LifecycleStatus[] = []
    const life = createGraphLifecycle(container(), { data: sample(), factory: f.factory, onStatus: (s) => statuses.push(s) })
    await settle()
    life.destroy()
    f.graphs[0]!.pendingRenders[0]!.reject(new Error('canvas destroyed'))
    await settle()
    expect(life.status).toBe('destroyed')
    expect(statuses).toEqual(['rendering', 'destroyed'])
  })

  it('渲染途中销毁：渲染随后完成也不回到 ready', async () => {
    const f = fakeFactory()
    f.configure = (g) => {
      g.holdRender = true
    }
    const statuses: LifecycleStatus[] = []
    const life = createGraphLifecycle(container(), { data: sample(), factory: f.factory, onStatus: (s) => statuses.push(s) })
    await settle()
    life.destroy()
    f.graphs[0]!.pendingRenders[0]!.resolve()
    await settle()
    expect(life.status).toBe('destroyed')
    expect(statuses).toEqual(['rendering', 'destroyed'])
    expect(f.graphs[0]!.calls).toEqual(['render', 'destroy'])
  })

  it('更新的渲染途中销毁：渲染随后完成也不回到 ready', async () => {
    const f = fakeFactory()
    const statuses: LifecycleStatus[] = []
    const life = createGraphLifecycle(container(), { data: sample(), factory: f.factory, onStatus: (s) => statuses.push(s) })
    await settle()
    f.graphs[0]!.holdRender = true
    life.update({ nodes: [node('a')], edges: [] })
    await settle()
    life.destroy()
    f.graphs[0]!.pendingRenders[0]!.resolve()
    await settle()
    expect(life.status).toBe('destroyed')
    expect(statuses).toEqual(['rendering', 'ready', 'rendering', 'destroyed'])
  })
})

describe('H04 失败', () => {
  it('G6 加载失败进入 error，并把错误交给回调', async () => {
    const f = fakeFactory()
    const boom = new Error('chunk load failed')
    f.error = boom
    const onStatus = vi.fn()
    const life = createGraphLifecycle(container(), { data: sample(), factory: f.factory, onStatus })
    await settle()
    expect(life.status).toBe('error')
    expect(onStatus).toHaveBeenLastCalledWith('error', boom)
    life.destroy()
  })

  it('渲染失败进入 error，之后的更新不再触达 G6', async () => {
    const f = fakeFactory()
    f.configure = (g) => {
      g.renderError = new Error('layout failed')
    }
    const life = createGraphLifecycle(container(), { data: sample(), factory: f.factory })
    await settle()
    expect(life.status).toBe('error')
    life.update(sample())
    await settle()
    expect(f.graphs[0]!.calls).toEqual(['render'])
    life.destroy()
    expect(f.graphs[0]!.calls).toEqual(['render', 'destroy'])
  })
})

describe('H04 节点点击', () => {
  it('点击节点回传知识点 ID；点击边、画布或已移除的节点不回传', async () => {
    const f = fakeFactory()
    const onNodeClick = vi.fn()
    const life = createGraphLifecycle(container(), { data: sample(), factory: f.factory, onNodeClick })
    await settle()
    const g = f.graphs[0]!
    g.emit('node:click', { target: { id: nodeElementId('stack') } })
    expect(onNodeClick).toHaveBeenCalledWith('stack')

    g.emit('node:click', { target: { id: edgeElementId('r1') } })
    g.emit('node:click', {})
    g.emit('node:click', { target: { id: 'kp:ghost' } })
    expect(onNodeClick).toHaveBeenCalledTimes(1)

    life.update({ nodes: [node('queue')], edges: [] })
    await settle()
    g.emit('node:click', { target: { id: nodeElementId('stack') } })
    g.emit('node:click', { target: { id: nodeElementId('queue') } })
    expect(onNodeClick.mock.calls).toEqual([['stack'], ['queue']])
    life.destroy()
  })
})

// ---------- 组件 ----------

function mountCanvas(f: FactoryControl, graph: Ref<GraphCanvasData | null>) {
  const Host = defineComponent({
    setup() {
      return () =>
        h('div', [
          h(GraphCanvas, {
            graph: graph.value,
            onNodeClick: (kpId: string) => clicked.push(kpId),
          }),
        ])
    },
  })
  const clicked: string[] = []
  const wrapper = mount(Host, {
    attachTo: document.body,
    global: { provide: { [GRAPH_FACTORY_KEY as symbol]: f.factory } },
  })
  return { wrapper, clicked }
}

/** jsdom 不排版：画布容器默认给 800×600，其他元素仍为 0；单个元素可用 setBox 覆盖 */
function sizeStagesByDefault(width = 800, height = 600): () => void {
  for (const [key, value] of [['clientWidth', width], ['clientHeight', height]] as const) {
    Object.defineProperty(HTMLElement.prototype, key, {
      configurable: true,
      get(this: HTMLElement) {
        return this.classList.contains('graph-canvas__stage') ? value : 0
      },
    })
  }
  return () => {
    // 删掉 HTMLElement 上的覆盖，回落到 Element.prototype 的原生实现
    for (const key of ['clientWidth', 'clientHeight']) delete (HTMLElement.prototype as unknown as Record<string, unknown>)[key]
  }
}

describe('H04 GraphCanvas 组件', () => {
  let restoreSize: () => void
  beforeEach(() => {
    restoreSize = sizeStagesByDefault()
  })
  afterEach(() => {
    restoreSize()
  })

  it('挂载后渲染图谱，画布区有描述规模的无障碍标签，加载提示随渲染结束消失', async () => {
    const f = fakeFactory()
    f.configure = (g) => {
      g.holdRender = true
    }
    const { wrapper } = mountCanvas(f, ref(sample()))
    await settle()
    const stage = wrapper.get('.graph-canvas__stage')
    expect(stage.attributes('role')).toBe('img')
    expect(stage.attributes('aria-label')).toBe('课程知识图谱：3 个知识点，2 条关系')
    expect(wrapper.get('[role="status"]').text()).toContain('加载中')
    expect(wrapper.get('.graph-canvas').attributes('aria-busy')).toBe('true')

    f.graphs[0]!.pendingRenders[0]!.resolve()
    await settle()
    expect(wrapper.find('[role="status"]').exists()).toBe(false)
    expect(wrapper.get('.graph-canvas').attributes('aria-busy')).toBe('false')
    expect(f.graphs[0]!.init.container).toBe(stage.element)
  })

  it('数据未到（null）时显示加载且不建图；数据到达后建图', async () => {
    const f = fakeFactory()
    const graph = ref<GraphCanvasData | null>(null)
    const { wrapper } = mountCanvas(f, graph)
    await settle()
    expect(f.graphs).toHaveLength(0)
    expect(wrapper.get('[role="status"]').text()).toContain('加载中')

    graph.value = sample()
    await settle()
    expect(f.graphs).toHaveLength(1)
    expect(wrapper.find('[role="status"]').exists()).toBe(false)
  })

  it('空图显示空态', async () => {
    const f = fakeFactory()
    const { wrapper } = mountCanvas(f, ref({ nodes: [], edges: [] }))
    await settle()
    expect(wrapper.get('[role="status"]').text()).toContain('暂无知识点')
  })

  it('数据变化转为 setData，不重建图', async () => {
    const f = fakeFactory()
    const graph = ref<GraphCanvasData | null>(sample())
    mountCanvas(f, graph)
    await settle()
    graph.value = { nodes: [node('stack')], edges: [] }
    await settle()
    expect(f.graphs).toHaveLength(1)
    expect(f.graphs[0]!.calls).toEqual(['render', 'setData', 'render'])
    expect(f.graphs[0]!.data.nodes.map((n) => n.id)).toEqual(['kp:stack'])
  })

  it('节点点击以知识点 ID 触发 node-click 事件', async () => {
    const f = fakeFactory()
    const { clicked } = mountCanvas(f, ref(sample()))
    await settle()
    f.graphs[0]!.emit('node:click', { target: { id: 'kp:queue' } })
    expect(clicked).toEqual(['queue'])
  })

  it('渲染失败显示告警与重试；重试重建图并销毁旧图', async () => {
    const f = fakeFactory()
    f.configure = (g) => {
      g.renderError = new Error('internal detail')
    }
    const { wrapper } = mountCanvas(f, ref(sample()))
    await settle()
    const alert = wrapper.get('[role="alert"]')
    expect(alert.text()).toContain('图谱渲染失败')
    expect(alert.text()).not.toContain('internal detail')

    f.configure = null
    await alert.get('button').trigger('click')
    await settle()
    expect(f.graphs).toHaveLength(2)
    expect(f.graphs[0]!.destroyed).toBe(true)
    expect(f.graphs[1]!.destroyed).toBe(false)
    expect(wrapper.find('[role="alert"]').exists()).toBe(false)
  })

  it('卸载时销毁图并断开观察', async () => {
    const f = fakeFactory()
    const { wrapper } = mountCanvas(f, ref(sample()))
    await settle()
    wrapper.unmount()
    expect(f.graphs[0]!.destroyed).toBe(true)
    expect(FakeResizeObserver.instances.every((o) => o.disconnected)).toBe(true)
  })

  it('反复切页不泄漏：每次进入新建一张图，离开即销毁，观察器、帧与 window 监听全部归零', async () => {
    const f = fakeFactory()
    const data = sample()
    const GraphPage = defineComponent({ setup: () => () => h(GraphCanvas, { graph: data }) })
    const OtherPage = defineComponent({ setup: () => () => h('p', '其他页面') })
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [
        { path: '/graph', component: GraphPage },
        { path: '/other', component: OtherPage },
      ],
    })
    await router.push('/other')
    const wrapper = mount(defineComponent({ setup: () => () => h(RouterView) }), {
      attachTo: document.body,
      global: { plugins: [router], provide: { [GRAPH_FACTORY_KEY as symbol]: f.factory } },
    })

    const rounds = 20
    for (let i = 0; i < rounds; i += 1) {
      await router.push('/graph')
      await settle()
      const observer = FakeResizeObserver.instances.at(-1)!
      observer.trigger()
      await router.push('/other')
      await settle()
    }

    expect(f.graphs).toHaveLength(rounds)
    expect(f.graphs.every((g) => g.destroyed && g.handlers.size === 0)).toBe(true)
    expect(FakeResizeObserver.instances).toHaveLength(rounds)
    expect(FakeResizeObserver.instances.every((o) => o.disconnected)).toBe(true)
    expect(frames.size).toBe(0)
    const added = addSpy.mock.calls.length
    const removed = removeSpy.mock.calls.length
    expect(added - removed).toBe(0)
    expect(wrapper.find('.graph-canvas').exists()).toBe(false)
  })

  it('KeepAlive 重新激活时按当前尺寸调整', async () => {
    const f = fakeFactory()
    const show = ref(true)
    const data = sample()
    const Host = defineComponent({
      setup: () => () => h(KeepAlive, null, [show.value ? h(GraphCanvas, { graph: data }) : h('p', '其他')]),
    })
    const wrapper = mount(Host, { attachTo: document.body, global: { provide: { [GRAPH_FACTORY_KEY as symbol]: f.factory } } })
    await settle()
    const stage = f.graphs[0]!.init.container

    show.value = false
    await nextTick()
    setBox(stage, 1200, 800)
    show.value = true
    await nextTick()
    flushFrames()
    await settle()
    expect(f.graphs).toHaveLength(1)
    expect(f.graphs[0]!.calls).toEqual(['render', 'setSize 1200x800', 'fitView'])
    wrapper.unmount()
    expect(f.graphs[0]!.destroyed).toBe(true)
  })
})
