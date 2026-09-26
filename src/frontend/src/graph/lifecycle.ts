import type { GraphData, GraphOptions } from '@antv/g6'
import type { InjectionKey } from 'vue'
import type { AdaptedGraph, G6Edge, G6Node } from './adapter'

/**
 * G6 画布生命周期（H04）。
 *
 * 把一张适配图（H03 `toG6Data` 的节点与边）画进容器，并负责：
 * - 挂载：量出容器尺寸再建图；尺寸为 0（隐藏页签、未排版）时推迟到出现尺寸再建。
 * - 更新：`setData` + `render` 串行执行；渲染进行中的多次更新合并为一次，落在最后一次数据。
 * - resize：容器尺寸变化在下一帧合并处理，`setSize` 后重新适应视口；尺寸为 0 或未变时不动。
 * - 销毁：销毁图实例、断开观察、取消待执行帧；之后迟到的建图、渲染结果都被丢弃。
 *
 * 交给 G6 的数据是副本（G6 布局会往数据里写坐标），调用方的对象不被改写。
 * G6 通过工厂创建，默认按需加载 `@antv/g6`，测试可换成替身。
 */

export type GraphCanvasData = Pick<AdaptedGraph, 'nodes' | 'edges'>

export interface NodeClickEvent {
  target?: { id?: string }
}

/** 生命周期用到的 G6 `Graph` 子集 */
export interface CanvasGraph {
  readonly destroyed: boolean
  render(): Promise<void>
  setData(data: GraphCanvasData): void
  setSize(width: number, height: number): void
  fitView(): Promise<void>
  on(event: 'node:click', handler: (event: NodeClickEvent) => void): unknown
  destroy(): void
}

export interface CanvasGraphInit {
  container: HTMLElement
  width: number
  height: number
  data: GraphCanvasData
}

export type CanvasGraphFactory = (init: CanvasGraphInit) => CanvasGraph | Promise<CanvasGraph>

/**
 * - `waiting`：容器尚无尺寸，未建图
 * - `rendering`：正在加载 G6、渲染或应用更新
 * - `ready`：最近一次数据已画完
 * - `error`：建图或渲染失败，需销毁后重建
 * - `destroyed`：已销毁
 */
export type LifecycleStatus = 'waiting' | 'rendering' | 'ready' | 'error' | 'destroyed'

export interface GraphLifecycleOptions {
  data: GraphCanvasData
  factory?: CanvasGraphFactory
  /** 参数是知识点 ID（契约 ID，不带 `kp:` 前缀） */
  onNodeClick?: (kpId: string) => void
  onStatus?: (status: LifecycleStatus, error?: unknown) => void
}

export interface GraphLifecycle {
  readonly status: LifecycleStatus
  update(data: GraphCanvasData): void
  /** 容器可能变了尺寸但观察器不会通知时（如 KeepAlive 重新激活）主动复查 */
  refreshSize(): void
  destroy(): void
}

/** 画布组件取 G6 工厂的注入键；不提供时用 `loadG6Graph` */
export const GRAPH_FACTORY_KEY: InjectionKey<CanvasGraphFactory> = Symbol('graph-factory')

/** 默认建图参数：层次布局，缩放、拖拽画布、拖拽节点，平行边分开画；边样式由适配层逐条给出 */
export function buildGraphOptions(init: CanvasGraphInit): GraphOptions {
  return {
    container: init.container,
    width: init.width,
    height: init.height,
    data: init.data as unknown as GraphData,
    autoFit: 'view',
    padding: 32,
    animation: false,
    zoomRange: [0.2, 4],
    node: {
      type: 'circle',
      style: {
        size: 28,
        fill: '#ffffff',
        stroke: '#1677ff',
        lineWidth: 1.5,
        labelText: (datum: unknown) => (datum as G6Node).data.name,
        labelPlacement: 'bottom',
        labelFontSize: 12,
      },
    },
    edge: {
      // 不指定 type：平行边转换会把成组的边改为曲线
      style: { labelFontSize: 10, labelBackground: true },
    },
    layout: { type: 'antv-dagre', rankdir: 'TB', nodesep: 40, ranksep: 70 },
    behaviors: ['zoom-canvas', 'drag-canvas', 'drag-element'],
    // 同一对知识点间可同时有前置与相关等多条关系，分开画避免重叠
    transforms: ['process-parallel-edges'],
  }
}

/** 按需加载 G6，让未打开图谱的页面不下载它 */
export const loadG6Graph: CanvasGraphFactory = async (init) => {
  const { Graph } = await import('@antv/g6')
  return new Graph(buildGraphOptions(init)) as unknown as CanvasGraph
}

function copyNode(node: G6Node): G6Node {
  return { id: node.id, data: { ...node.data } }
}

function copyEdge(edge: G6Edge): G6Edge {
  return {
    id: edge.id,
    source: edge.source,
    target: edge.target,
    data: { ...edge.data },
    style: { ...edge.style, lineDash: [...edge.style.lineDash] },
  }
}

function copyData(data: GraphCanvasData): GraphCanvasData {
  return { nodes: data.nodes.map(copyNode), edges: data.edges.map(copyEdge) }
}

function kpIndex(data: GraphCanvasData): Map<string, string> {
  return new Map(data.nodes.map((node) => [node.id, node.data.kpId]))
}

export function createGraphLifecycle(container: HTMLElement, options: GraphLifecycleOptions): GraphLifecycle {
  const factory = options.factory ?? loadG6Graph
  let status: LifecycleStatus = 'waiting'
  let graph: CanvasGraph | null = null
  let creating = false
  /** 尚未交给 G6 的最新数据；null 表示已同步 */
  let pending: GraphCanvasData | null = copyData(options.data)
  /** 当前画布上的元素 ID → 知识点 ID */
  let drawn = new Map<string, string>()
  let width = 0
  let height = 0
  let frame: number | null = null
  /** 所有对 G6 的异步操作串行执行 */
  let chain: Promise<void> = Promise.resolve()

  const alive = () => status !== 'destroyed' && status !== 'error'

  function setStatus(next: LifecycleStatus, error?: unknown): void {
    status = next
    options.onStatus?.(next, error)
  }

  function fail(error: unknown): void {
    if (!alive()) return
    setStatus('error', error)
  }

  function enqueue(task: () => Promise<void>): void {
    chain = chain.then(async () => {
      if (!alive()) return
      try {
        await task()
      } catch (error) {
        fail(error)
      }
    })
  }

  function measure(): [number, number] {
    return [container.clientWidth, container.clientHeight]
  }

  function create(): void {
    creating = true
    enqueue(async () => {
      setStatus('rendering')
      const data = pending ?? { nodes: [], edges: [] }
      pending = null
      const created = await factory({ container, width, height, data })
      if (!alive()) {
        created.destroy()
        return
      }
      graph = created
      drawn = kpIndex(data)
      graph.on('node:click', (event) => {
        const kpId = event.target?.id === undefined ? undefined : drawn.get(event.target.id)
        if (kpId !== undefined && alive()) options.onNodeClick?.(kpId)
      })
      await graph.render()
      if (!alive()) return
      if (pending !== null) flush()
      else setStatus('ready')
    })
  }

  /** 可重复调用：排到时若数据已被前一次取走即空转，连续更新因此只画最后一次 */
  function flush(): void {
    enqueue(async () => {
      if (graph === null || pending === null) return
      const data = pending
      pending = null
      setStatus('rendering')
      graph.setData(data)
      drawn = kpIndex(data)
      await graph.render()
      if (!alive()) return
      if (pending !== null) flush()
      else setStatus('ready')
    })
  }

  function applySize(): void {
    frame = null
    if (!alive()) return
    const [w, h] = measure()
    if (w <= 0 || h <= 0 || (w === width && h === height)) return
    width = w
    height = h
    if (graph === null) {
      if (!creating) create()
      return
    }
    enqueue(async () => {
      graph!.setSize(w, h)
      await graph!.fitView()
    })
  }

  function scheduleSize(): void {
    if (frame !== null || !alive()) return
    frame = requestAnimationFrame(applySize)
  }

  let stopObserving: () => void
  if (typeof ResizeObserver === 'function') {
    const observer = new ResizeObserver(scheduleSize)
    observer.observe(container)
    stopObserving = () => observer.disconnect()
  } else {
    window.addEventListener('resize', scheduleSize)
    stopObserving = () => window.removeEventListener('resize', scheduleSize)
  }

  ;[width, height] = measure()
  if (width > 0 && height > 0) create()
  else options.onStatus?.('waiting')

  return {
    get status() {
      return status
    },
    update(data) {
      if (!alive()) return
      pending = copyData(data)
      if (graph !== null) flush()
    },
    refreshSize() {
      scheduleSize()
    },
    destroy() {
      if (status === 'destroyed') return
      stopObserving()
      if (frame !== null) cancelAnimationFrame(frame)
      frame = null
      setStatus('destroyed')
      if (graph !== null && !graph.destroyed) graph.destroy()
      graph = null
      drawn = new Map()
    },
  }
}
