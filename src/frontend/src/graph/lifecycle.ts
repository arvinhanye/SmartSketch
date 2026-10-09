import type { GraphData, GraphOptions } from '@antv/g6'
import type { InjectionKey } from 'vue'
import { nodeElementId, type G6Edge, type G6EdgeData, type G6Node, type G6NodeData } from './adapter'
import type { Positions } from './chapterLayout'
import { createEnhancer, type EnhanceOptions, type Enhancer } from './enhancer'
import { badgesFor, nodeLabel } from './presentation'
import { NODE_BASE_PX, READABLE_ZOOM } from './scale'
import { GRAPH_COLORS, GRAPH_FONT, NODE_TYPE_FILL, NODE_TYPE_GLYPH } from './theme'

/** 可读缩放见 `graph/scale.ts`（0.9：新标签 13px，0.7 时只有约 9px）；这里再导出，保持既有导入路径有效 */
export { READABLE_ZOOM }

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

/**
 * 画布元素状态（H05）：筛选层据审核状态与选中项给元素打标，样式见 `buildGraphOptions` 的 `state`。
 * 状态随数据交给 G6，所以重新布局、重设数据都不会丢选中高亮。
 *
 * I06 追加学习状态：学生页按服务端投影的 `MasteryStatus`（`mastered`/`learning`/`notStarted`）
 * 与推荐项（`recommended`）给节点打标；元素只携带状态名，颜色只在 `buildGraphOptions` 定义一处。
 */
export type CanvasElementState =
  | 'selected'
  | 'rejected'
  | 'lowConfidence'
  | 'mastered'
  | 'learning'
  | 'notStarted'
  | 'recommended'
  // L14 学习路径：未满足的前置、之后解锁、与当前路径无关（淡化）；边：路径上的先修边
  | 'pathPrereq'
  | 'pathUnlock'
  | 'dimmed'
  | 'pathEdge'
  // UI-GRAPH-PILOT-01 聚焦与悬停状态（`graph/focusStates.ts` 计算；颜色只在 `buildGraphOptions` 定义一处）
  | 'neighbor'
  | 'match'
  | 'faded'
  | 'hovered'
  | 'hoverRelated'
  | 'hoverFaded'
  | 'active'
  | 'scoped'

export { nodeLabel }

export type CanvasNode = G6Node & { states?: CanvasElementState[]; style?: { x: number; y: number } }
export type CanvasEdge = G6Edge & { states?: CanvasElementState[] }

/** 适配图（H03 `AdaptedGraph` 的节点与边）可直接传入；筛选层可附加 `states` */
export interface GraphCanvasData {
  nodes: CanvasNode[]
  edges: CanvasEdge[]
}

/** 画布布局（H05）：层次（自上而下）或力导向 */
export type GraphLayoutName = 'hierarchical' | 'force'

export interface NodeClickEvent {
  target?: { id?: string }
}

/** 画布事件的公共子集（点击、悬停；`client` 是页面坐标） */
export interface GraphEvent extends NodeClickEvent {
  pointerType?: string
  client?: { x: number; y: number }
}

/** 画布坐标 / 视口坐标（G6 的 `Point` 可带第三维，这里只用前两维） */
export type Point2 = readonly number[]

/** 生命周期用到的 G6 `Graph` 子集 */
export interface CanvasGraph {
  readonly destroyed: boolean
  render(): Promise<void>
  setData(data: GraphCanvasData): void
  setSize(width: number, height: number): void
  fitView(): Promise<void>
  on(event: string, handler: (event: GraphEvent) => void): unknown
  destroy(): void
  /** G6 `Graph` 均有；测试替身可不实现，此时布局切换不生效（H05） */
  setLayout?(layout: NonNullable<GraphOptions['layout']>): void
  layout?(): Promise<void>
  /** 视口（L13）：G6 `Graph` 均有；测试替身可不实现，此时保持整图适配、不做聚焦 */
  getZoom?(): number
  zoomTo?(zoom: number, animation?: unknown): Promise<void>
  focusElement?(id: string, animation?: unknown): Promise<void>
  /**
   * L14：G6 5.x 的 `render()` 每次都按 `autoFit` 重新整图适配，掌握状态、选中、路径高亮引起的数据更新
   * 因此会把视口拉回整图。首次渲染后用它关掉 `autoFit`；之后的适配只在尺寸变化与切换布局时显式 `fitView`。
   */
  setOptions?(options: Partial<GraphOptions>): void
  /**
   * 增强模式（UI-GRAPH-PILOT-01）用到的视口、数据与插件接口：G6 `Graph` 均有；测试替身可不实现，
   * 此时对应能力静默跳过。
   */
  getElementPosition?(id: string): Point2
  getViewportByCanvas?(point: Point2): Point2
  translateBy?(offset: Point2, animation?: unknown): Promise<void>
  zoomBy?(ratio: number, animation?: unknown): Promise<void>
  updateNodeData?(data: ReadonlyArray<Record<string, unknown>>): void
  updateEdgeData?(data: ReadonlyArray<Record<string, unknown>>): void
  draw?(): Promise<void>
  setElementState?(state: Record<string, string[]>, animation?: boolean): Promise<void>
  setPlugins?(update: (plugins: unknown[]) => unknown[]): void
  updatePlugin?(option: Record<string, unknown>): void
  getPluginInstance?(key: string): unknown
}

export interface CanvasGraphInit {
  container: HTMLElement
  width: number
  height: number
  data: GraphCanvasData
  /** 缺省为层次布局 */
  layout?: GraphLayoutName
  /** 预先算好的位置（章节分区布局）：给了就不再让 G6 布局，边画成竖向曲线；只对层次布局生效 */
  positions?: Positions | null
  /** 给了位置时边的画法：竖向曲线（层次/章节布局，缺省）或直线（径向布局） */
  edgeStyle?: 'vertical' | 'straight'
  /** 小地图（增强模式）：外部容器与节点点的着色回调 */
  minimap?: { container: HTMLElement; color: (elementId: string) => string }
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
  /** 缺省为层次布局 */
  layout?: GraphLayoutName
  /**
   * 章节分区布局算好的位置（知识点 ID → 画布坐标），建图时一次性给定；缺省沿用 G6 布局。
   * 力导向布局下忽略。位置变了（换图、换布局）由调用方重建生命周期。
   */
  positions?: Positions | null
  /** 给了位置时边的画法（径向布局用直线）；缺省竖向曲线 */
  edgeStyle?: 'vertical' | 'straight'
  /**
   * 首屏视图：`readable`（缺省）按可读缩放聚焦入口节点；`overview` 先把整张图适应进视口（增强模式）。
   * 已有待聚焦目标（搜索/跳转）时仍聚焦目标。换布局与窗口缩放后的重新适配沿用同一策略。
   */
  initialView?: 'readable' | 'overview'
  /**
   * 增强模式（语义缩放、标签排布、悬停强淡化、章节外框、小地图、整组适应）。缺省关闭，行为与 H04 完全一致。
   * 开启后容器尺寸变化（面板开合）只 `setSize`、保持镜头；窗口缩放与 `refreshSize()` 仍整图重新适配。
   */
  enhance?: EnhanceOptions
  factory?: CanvasGraphFactory
  /** 参数是知识点 ID（契约 ID，不带 `kp:` 前缀） */
  onNodeClick?: (kpId: string) => void
  onStatus?: (status: LifecycleStatus, error?: unknown) => void
  /** 视口调整后的缩放值（L13，页面写到 `data-zoom` 供验收） */
  onZoom?: (zoom: number) => void
}

export interface GraphLifecycle {
  readonly status: LifecycleStatus
  update(data: GraphCanvasData): void
  /** 在原图上换布局并适应视口，不重建、不重设数据；尚未建图时建图即用新布局 */
  setLayout(layout: GraphLayoutName): void
  /** 容器可能变了尺寸但观察器不会通知时（如 KeepAlive 重新激活）主动复查 */
  refreshSize(): void
  /** 把视口移到该知识点（搜索定位、问答跳转）；尚未建图时在首次渲染后执行；不在图中的知识点忽略 */
  focus(kpId: string): void
  /** 增强模式：把一组知识点（缺省为当前全部）整体放进视口；未开启增强或尚未建图时忽略 */
  fitTo(kpIds?: readonly string[]): void
  /** 增强模式：章节外框的成员（知识点 ID）；null 隐藏外框 */
  setScope(kpIds: readonly string[] | null): void
  /** 增强模式：按比例缩放（工具栏的放大、缩小） */
  zoomBy(ratio: number): void
  /** 增强模式：节点在视口外时才把镜头移过去（面板里的显式选择） */
  ensureVisible(kpId: string): void
  /** 增强模式：浮层出现、消失、展开收起后重新排布标签 */
  relayoutLabels(): void
  /** 增强模式：指针离开整个画布容器时结束悬停淡化 */
  leaveHover(): void
  destroy(): void
}

/** 画布组件取 G6 工厂的注入键；不提供时用 `loadG6Graph` */
export const GRAPH_FACTORY_KEY: InjectionKey<CanvasGraphFactory> = Symbol('graph-factory')

/** 两种布局的 G6 参数；层次布局与 H04 默认一致 */
export function layoutOptions(layout: GraphLayoutName): NonNullable<GraphOptions['layout']> {
  if (layout === 'force') {
    return { type: 'd3-force', link: { distance: 120 }, manyBody: { strength: -300 }, collide: { radius: 40 } }
  }
  return { type: 'antv-dagre', rankdir: 'TB', nodesep: 40, ranksep: 70 }
}

/**
 * 小地图：只画节点，克隆节点主形状并重新着色（已掌握绿、学习中琥珀、当前高亮靛紫、其余石板灰），
 * 缩略图同时是学习进度总览。装饰性，键盘等价路径是搜索、章节跳转与列表。
 */
function minimapPlugin(minimap: NonNullable<CanvasGraphInit['minimap']>): Record<string, unknown> {
  return {
    type: 'minimap',
    key: 'minimap',
    container: minimap.container,
    size: [180, 120],
    padding: 8,
    filter: (_id: string, kind: string) => kind === 'node',
    shape: (id: string, _kind: string, element: { getShape(name: string): { cloneNode(): { style: Record<string, unknown> } } }) => {
      const dot = element.getShape('key').cloneNode()
      dot.style.fill = minimap.color(id)
      dot.style.lineWidth = 0
      return dot
    },
    maskStyle: { border: `2px solid ${GRAPH_COLORS.accent}`, background: 'rgb(81 69 205 / 12%)' },
    delay: 100,
  }
}

const nd = (d: unknown): G6NodeData => (d as G6Node).data
const ed = (d: unknown): G6EdgeData => (d as G6Edge).data
const labelK = (d: unknown): number => nd(d).k ?? 1
const nodeK = (d: unknown): number => nd(d).nk ?? 1
const lwMin = (d: unknown): number => nd(d).lw ?? 0

/** 默认建图参数：新主题（浅色画布、类型填充 + 单字标记、掌握角标）；布局、缩放、拖拽与平行边处理沿用 H04/H05 */
export function buildGraphOptions(init: CanvasGraphInit): GraphOptions {
  const C = GRAPH_COLORS
  const withPositions = init.positions != null && (init.layout ?? 'hierarchical') === 'hierarchical'
  return {
    container: init.container,
    width: init.width,
    height: init.height,
    data: init.data as unknown as GraphData,
    autoFit: 'view',
    padding: 40,
    animation: false,
    zoomRange: [0.2, 4],
    node: {
      type: 'circle',
      style: {
        size: (d: unknown) => NODE_BASE_PX * nodeK(d),
        fill: (d: unknown) => NODE_TYPE_FILL[nd(d).type],
        stroke: C.nodeStroke,
        lineWidth: (d: unknown) => Math.max(1.5, lwMin(d)),
        iconText: (d: unknown) => NODE_TYPE_GLYPH[nd(d).type],
        iconFontSize: (d: unknown) => 14 * nodeK(d),
        iconFontWeight: 500,
        iconFill: C.text,
        iconFontFamily: GRAPH_FONT,
        labelText: (d: unknown) => nodeLabel(nd(d)),
        labelPlacement: 'bottom',
        // G6 节点的 label 是布尔开关：false 时整个标签不绘制（`labelVisibility` 无效）
        label: (d: unknown) => nd(d).labelOn !== false,
        labelFontSize: (d: unknown) => 13 * labelK(d),
        // 字号随缩放放大时行高必须同步，否则多行标签的两行会叠在一起
        labelLineHeight: (d: unknown) => Math.round(13 * labelK(d) * 1.3),
        labelFontWeight: 500,
        labelFill: C.text,
        labelFontFamily: GRAPH_FONT,
        labelWordWrap: true,
        labelWordWrapWidth: (d: unknown) => 112 * labelK(d),
        labelMaxLines: 2,
        labelTextOverflow: 'ellipsis',
        labelOffsetY: (d: unknown) => 4 * labelK(d),
        // 关系线从标签下方穿过时不应像删除线：标签带与画布同色的不透明底
        labelBackground: true,
        labelBackgroundFill: C.canvas,
        labelBackgroundOpacity: 0.94,
        labelPadding: [1, 3],
        badges: (d: unknown) => badgesFor(nd(d).mastery, nodeK(d)),
      },
      // 多个状态按 states 数组顺序叠加：审核/学习状态在前，聚焦状态居中，选中在后，悬停瞬时状态最后
      state: {
        rejected: { opacity: 0.4, stroke: '#7F8695', lineDash: [4, 3] },
        lowConfidence: { stroke: C.warn, lineDash: [4, 3] },
        // I06：掌握状态色只在这里定义；元素只带状态名，角标由 `badgesFor` 画（颜色之外还有 ✓/◐ 与文字）
        mastered: { stroke: C.ok, lineWidth: 2 },
        learning: { stroke: C.warn, lineWidth: 2 },
        notStarted: { stroke: C.nodeStroke },
        recommended: { stroke: C.accent, lineWidth: 3 },
        // L14 学习路径：未满足的前置（虚线）、之后解锁（点线）；与当前路径无关用 dimmed（标准淡化）
        pathPrereq: { stroke: C.warn, lineWidth: 2.5, lineDash: [4, 3] },
        pathUnlock: { stroke: C.accent, lineWidth: 2, lineDash: [2, 3] },
        // 标准淡化：降填充饱和度，边框 ≥3:1、标签保留（不使用整体 opacity）
        dimmed: { fill: C.dimmedFill, stroke: C.dimmedStroke, labelFill: '#545967', iconFill: '#545967' },
        // 强淡化（Obsidian 式，仅供对比）：近底色小点；标签由排布函数直接隐藏
        faded: { fill: C.fadedFill, stroke: C.fadedStroke, lineWidth: 1, iconFill: C.fadedIcon, halo: false },
        neighbor: { stroke: C.accent, lineWidth: (d: unknown) => Math.max(2, lwMin(d) * 1.5) },
        selected: {
          stroke: C.accent,
          lineWidth: (d: unknown) => Math.max(2.5, lwMin(d) * 2),
          halo: true,
          haloStroke: C.accent,
          haloLineWidth: (d: unknown) => Math.max(5, lwMin(d) * 3),
          haloStrokeOpacity: 0.22,
          labelFontWeight: 700,
        },
        // 搜索命中 / 章节定位：靛紫外环 + 标签加粗改靛紫，不用淡紫色底块
        match: { stroke: C.accent, lineWidth: (d: unknown) => Math.max(2.5, lwMin(d) * 2), labelFill: C.accent, labelFontWeight: 700 },
        // 悬停（瞬时，强淡化）：悬停节点与其直接相邻保持清楚，其余退成近底色小点并隐去标签与角标
        hovered: { stroke: C.accent, lineWidth: (d: unknown) => Math.max(2.5, lwMin(d) * 2), labelFontWeight: 700 },
        hoverRelated: { stroke: C.accent, lineWidth: (d: unknown) => Math.max(2, lwMin(d) * 1.5) },
        hoverFaded: { fill: C.fadedFill, stroke: C.fadedStroke, lineWidth: 1, iconFill: C.fadedIcon, halo: false, label: false, badge: false },
      },
    },
    edge: {
      // 章节分区布局下画竖向曲线；其余不指定 type（平行边转换会把成组的边改为曲线）
      ...(withPositions ? { type: init.edgeStyle === 'straight' ? 'line' : 'cubic-vertical' } : {}),
      style: {
        endArrowSize: (d: unknown) => 9 * (ed(d).ak ?? 1),
        labelFontSize: 12,
        labelFill: C.text,
        labelFontFamily: GRAPH_FONT,
        labelBackground: true,
        labelBackgroundFill: C.panel,
        labelBackgroundOpacity: 1,
        labelPadding: [1, 5],
      },
      state: {
        rejected: { opacity: 0.3 },
        lowConfidence: { opacity: 0.6 },
        pathEdge: { stroke: C.accent, lineWidth: 3.5, halo: false },
        // 与关系线重合的状态不再用 opacity；G6 内置 active 状态自带灰色光晕，必须显式关闭
        active: { lineWidth: (d: unknown) => Math.max(3, (ed(d).lw ?? 0) * 2.5), halo: false },
        scoped: { lineWidth: (d: unknown) => Math.max(2, ed(d).lw ?? 0), halo: false },
        dimmed: { stroke: C.fadedEdge, lineWidth: 1, halo: false },
        faded: { stroke: C.fadedEdge, lineWidth: 1, halo: false },
        hoverFaded: { stroke: C.fadedEdge, lineWidth: 1, halo: false, label: false },
      },
    },
    // 有预先算好的位置时不再让 G6 布局（位置稳定，且可以按章节聚拢）
    ...(withPositions ? {} : { layout: layoutOptions(init.layout ?? 'hierarchical') }),
    behaviors: ['zoom-canvas', 'drag-canvas', 'drag-element'],
    // 同一对知识点间可同时有前置与相关等多条关系，分开画避免重叠
    transforms: ['process-parallel-edges'],
    ...(init.minimap === undefined ? {} : { plugins: [minimapPlugin(init.minimap)] as unknown as GraphOptions['plugins'] }),
  }
}


/** 按需加载 G6，让未打开图谱的页面不下载它 */
export const loadG6Graph: CanvasGraphFactory = async (init) => {
  const { Graph } = await import('@antv/g6')
  return new Graph(buildGraphOptions(init)) as unknown as CanvasGraph
}

function copyNode(node: CanvasNode, positions: Positions | null): CanvasNode {
  const copy: CanvasNode = { id: node.id, data: { ...node.data } }
  if (node.states !== undefined) copy.states = [...node.states]
  const at = positions?.get(node.data.kpId)
  if (at !== undefined) copy.style = { x: at.x, y: at.y }
  return copy
}

function copyEdge(edge: CanvasEdge): CanvasEdge {
  const copy: CanvasEdge = {
    id: edge.id,
    source: edge.source,
    target: edge.target,
    data: { ...edge.data },
    style: { ...edge.style, lineDash: [...edge.style.lineDash] },
  }
  if (edge.states !== undefined) copy.states = [...edge.states]
  return copy
}

function copyData(data: GraphCanvasData, positions: Positions | null): GraphCanvasData {
  return { nodes: data.nodes.map((node) => copyNode(node, positions)), edges: data.edges.map(copyEdge) }
}

function kpIndex(data: GraphCanvasData): Map<string, string> {
  return new Map(data.nodes.map((node) => [node.id, node.data.kpId]))
}

export function createGraphLifecycle(container: HTMLElement, options: GraphLifecycleOptions): GraphLifecycle {
  const factory = options.factory ?? loadG6Graph
  /** 章节分区布局的位置，只对层次布局生效（力导向由 G6 自己布局） */
  const positions: Positions | null = (options.layout ?? 'hierarchical') === 'hierarchical' ? (options.positions ?? null) : null
  let status: LifecycleStatus = 'waiting'
  let graph: CanvasGraph | null = null
  let creating = false
  /** 尚未交给 G6 的最新数据；null 表示已同步 */
  let pending: GraphCanvasData | null = copyData(options.data, positions)
  /** 当前画布上的元素 ID → 知识点 ID */
  let drawn = new Map<string, string>()
  /** 当前画布上的边（入口节点判定用） */
  let lastEdges: GraphCanvasData['edges'] = []
  let width = 0
  let height = 0
  /** 期望的布局，与 G6 实例当前使用的布局 */
  let layout: GraphLayoutName = options.layout ?? 'hierarchical'
  let appliedLayout: GraphLayoutName = layout
  let frame: number | null = null
  /** 所有对 G6 的异步操作串行执行 */
  let chain: Promise<void> = Promise.resolve()
  /** 建图前请求的聚焦目标（知识点 ID） */
  let pendingFocus: string | null = null
  /** 最近一次页面请求聚焦的知识点（L14）：尺寸变化重新适配后回到它，而不是入口节点 */
  let anchor: string | null = null

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

  const enhancer: Enhancer | null =
    options.enhance === undefined
      ? null
      : createEnhancer({
          graph: () => graph,
          size: () => [width, height],
          enqueue,
          alive,
          onZoom: (zoom) => options.onZoom?.(zoom),
          options: options.enhance,
        })

  /** 交给 G6 的数据：增强模式下附上缩放档位、标签开关、掌握角标等展示字段 */
  function prepare(data: GraphCanvasData): GraphCanvasData {
    return enhancer === null ? data : enhancer.decorate(data)
  }

  function measure(): [number, number] {
    return [container.clientWidth, container.clientHeight]
  }

  function reportZoom(g: CanvasGraph): void {
    if (g.getZoom !== undefined) options.onZoom?.(g.getZoom())
  }

  /** 入口节点：数据中第一个没有入边的节点；全图成环时取第一个节点 */
  function entryNode(): string | null {
    const ids = [...drawn.keys()]
    if (ids.length === 0) return null
    return ids.find((id) => !lastEdges.some((e) => e.target === id)) ?? ids[0]!
  }

  /** 整图适配之后：缩放低于可读值时放大并聚焦（有待聚焦目标时聚焦目标，否则入口节点） */
  async function ensureReadable(g: CanvasGraph): Promise<void> {
    if (g.getZoom !== undefined && g.zoomTo !== undefined && g.getZoom() < READABLE_ZOOM) {
      await g.zoomTo(READABLE_ZOOM)
      if (!alive()) return
      const wanted = pendingFocus ?? anchor
      const target = wanted !== null && drawn.has(nodeElementId(wanted)) ? nodeElementId(wanted) : entryNode()
      pendingFocus = null
      if (target !== null && drawn.has(target) && g.focusElement !== undefined) await g.focusElement(target)
    } else if (pendingFocus !== null) {
      const target = nodeElementId(pendingFocus)
      pendingFocus = null
      if (drawn.has(target) && g.focusElement !== undefined) await g.focusElement(target)
    }
    if (alive()) reportZoom(g)
  }

  /** 整图适配之后的视图：总览模式把整图放进视口，否则按可读缩放聚焦（有待聚焦目标时总是聚焦它） */
  async function settleView(g: CanvasGraph): Promise<void> {
    if (options.initialView === 'overview' && enhancer !== null && pendingFocus === null && anchor === null) {
      await enhancer.fitTo()
      if (alive()) reportZoom(g)
      return
    }
    await ensureReadable(g)
  }

  function create(): void {
    creating = true
    enqueue(async () => {
      setStatus('rendering')
      const data = prepare(pending ?? { nodes: [], edges: [] })
      pending = null
      appliedLayout = layout
      const minimap =
        enhancer !== null && options.enhance?.minimap != null
          ? { container: options.enhance.minimap, color: (id: string) => enhancer.minimapColor(id) }
          : undefined
      const created = await factory({ container, width, height, data, layout, positions, edgeStyle: options.edgeStyle, minimap })
      if (!alive()) {
        created.destroy()
        return
      }
      graph = created
      drawn = kpIndex(data)
      lastEdges = data.edges
      graph.on('node:click', (event) => {
        const kpId = event.target?.id === undefined ? undefined : drawn.get(event.target.id)
        if (kpId !== undefined && alive()) options.onNodeClick?.(kpId)
      })
      enhancer?.attach()
      await graph.render()
      if (!alive()) return
      // 之后的数据更新保持学生正在看的位置，不再回到整图适配（见 `CanvasGraph.setOptions`）
      graph.setOptions?.({ autoFit: undefined })
      await settleView(graph)
      if (!alive()) return
      await enhancer?.afterRender()
      if (!alive()) return
      if (pending !== null) flush()
      else setStatus('ready')
      // 加载 G6 期间切换过布局
      if (appliedLayout !== layout) relayout()
    })
  }

  /** 可重复调用：排到时布局已是期望值即空转，连续切换因此只落在最后一次 */
  function relayout(): void {
    enqueue(async () => {
      const g = graph
      if (g === null || appliedLayout === layout) return
      if (g.setLayout === undefined || g.layout === undefined) return
      appliedLayout = layout
      setStatus('rendering')
      g.setLayout(layoutOptions(layout))
      await g.layout()
      if (!alive()) return
      await g.fitView()
      if (!alive()) return
      await settleView(g)
      if (!alive()) return
      await enhancer?.afterRender()
      if (!alive()) return
      // 期间又有更新或切换时，已排队的 flush / relayout 负责收尾
      if (pending === null && appliedLayout === layout) setStatus('ready')
    })
  }

  /** 可重复调用：排到时若数据已被前一次取走即空转，连续更新因此只画最后一次 */
  function flush(): void {
    enqueue(async () => {
      if (graph === null || pending === null) return
      const data = prepare(pending)
      pending = null
      setStatus('rendering')
      graph.setData(data)
      drawn = kpIndex(data)
      lastEdges = data.edges
      await graph.render()
      if (!alive()) return
      await enhancer?.afterRender()
      if (!alive()) return
      if (pending !== null) flush()
      else setStatus('ready')
    })
  }

  /** 下一次尺寸变化是否整图重新适配：窗口缩放与 `refreshSize()` 为真；增强模式下的面板开合为假 */
  let refitNext = enhancer === null

  function applySize(): void {
    frame = null
    if (!alive()) return
    const refit = refitNext || enhancer === null
    refitNext = enhancer === null
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
      if (refit) {
        await graph!.fitView()
        if (alive()) await settleView(graph!)
      }
      // 画布尺寸变了：标签排布依赖视口，章节外框与小地图随之重算
      if (alive()) await enhancer?.afterRender()
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
    // 增强模式：容器尺寸变化多半是面板开合（只 setSize）；窗口缩放才整图重新适配
    const onWindowResize = () => {
      refitNext = true
    }
    if (enhancer !== null) window.addEventListener('resize', onWindowResize)
    stopObserving = () => {
      observer.disconnect()
      if (enhancer !== null) window.removeEventListener('resize', onWindowResize)
    }
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
      pending = copyData(data, positions)
      if (graph !== null) flush()
    },
    setLayout(next) {
      if (!alive() || next === layout) return
      layout = next
      if (graph !== null) relayout()
    },
    refreshSize() {
      refitNext = true
      scheduleSize()
    },
    focus(kpId) {
      if (!alive()) return
      anchor = kpId
      if (graph === null) {
        pendingFocus = kpId
        return
      }
      enqueue(async () => {
        const g = graph
        const target = nodeElementId(kpId)
        if (g === null || g.focusElement === undefined || !drawn.has(target)) return
        // 总览模式下镜头可能缩得很小：定位到某个知识点时放大到可读缩放，否则只看到一个看不清的小点
        const overview = options.initialView === 'overview' && g.getZoom !== undefined && g.zoomTo !== undefined && g.getZoom() < READABLE_ZOOM
        if (overview) await g.zoomTo!(READABLE_ZOOM)
        await g.focusElement(target)
        if (overview && alive()) {
          reportZoom(g)
          await enhancer?.afterRender()
        }
      })
    },
    fitTo(kpIds) {
      if (!alive() || enhancer === null || graph === null) return
      enqueue(() => enhancer.fitTo(kpIds))
    },
    setScope(kpIds) {
      if (!alive() || enhancer === null) return
      // 建图前先记下，渲染后由 `afterRender` 画出；建图后排在当前渲染之后
      if (graph === null) enhancer.setScope(kpIds)
      else enqueue(async () => enhancer.setScope(kpIds))
    },
    zoomBy(ratio) {
      if (!alive() || enhancer === null || graph === null) return
      enqueue(() => enhancer.zoomBy(ratio))
    },
    ensureVisible(kpId) {
      if (!alive() || enhancer === null || graph === null) return
      enqueue(() => enhancer.ensureVisible(kpId))
    },
    relayoutLabels() {
      if (alive()) enhancer?.relayoutLabels()
    },
    leaveHover() {
      if (alive()) enhancer?.leaveHover()
    },
    destroy() {
      if (status === 'destroyed') return
      stopObserving()
      if (frame !== null) cancelAnimationFrame(frame)
      frame = null
      setStatus('destroyed')
      enhancer?.detach()
      const g = graph
      if (g !== null && !g.destroyed) {
        if (enhancer === null) g.destroy()
        else {
          // 小地图、章节外框插件在视口变化后有延迟回调：立刻销毁会让它们在销毁后读取已清空的数据而抛错。
          // 延后一点再销毁；销毁本身可能返回会拒绝的 Promise，一并吞掉
          setTimeout(() => {
            try {
              void Promise.resolve(g.destroy()).catch(() => undefined)
            } catch {
              /* 已销毁 */
            }
          }, 400)
        }
      }
      graph = null
      drawn = new Map()
    },
  }
}
