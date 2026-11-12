import { nodeElementId } from './adapter'
import { bottomPad, computeFit, DEFAULT_PADS, type FitPads } from './fit'
import { hoverStateMap, isForcedLabel, labelScore } from './focusStates'
import type { NodeAnchor } from './hitTest'
import { planLabels, type Box, type LabelCandidate } from './labelPlan'
import type { CanvasEdge, CanvasGraph, CanvasNode, GraphEvent } from './lifecycle'
import { chapterOfNodes, decorateEdge, decorateNodeData, INITIAL_VIEW, nodeLabel, type ViewState } from './presentation'
import { LABEL_BASE_PX, labelScale, NODE_BASE_PX, sameFloors, scaleFloors } from './scale'
import { GRAPH_COLORS, GRAPH_FONT } from './theme'

/**
 * 画布增强（UI-GRAPH-PILOT-01）：语义缩放、标签排布、悬停强淡化、章节外框、整组适应。
 *
 * 由 `createGraphLifecycle` 在 `enhance` 选项开启时创建；所有对 G6 的异步写操作都通过 `deps.enqueue`
 * 排进生命周期的串行队列。G6 实例的缺失方法（测试替身）一律静默跳过。
 */

export interface EnhanceOptions {
  /** 浮层的屏幕包围盒（相对画布容器）：hard 参与镜头适应与标签避让，soft（如可展开的图例）只避让标签 */
  obstacles?: () => { hard: readonly Box[]; soft: readonly Box[] }
  /** 小地图容器；缺省不画小地图 */
  minimap?: HTMLElement | null
  /** 量文字宽度（测试替身用）；缺省用真实字体在离屏 canvas 上量 */
  measure?: (text: string, fontPx: number) => number
  /** 标签排布的合并窗口（毫秒），缺省 90 */
  labelDelayMs?: number
  /** 减少动效：镜头动画一律关闭 */
  reduceMotion?: () => boolean
  /** 悬停节点（非触屏）时回调，用于 tooltip；移开时回调 null */
  onHover?: (info: { kpId: string; clientX: number; clientY: number } | null) => void
  /** 点击画布空白处（取消预览） */
  onBlankClick?: () => void
  /** 点击一条关系线（UI-GRAPH-EDIT-02）：关系的契约 ID 与指针的页面坐标 */
  onEdgeClick?: (info: { relationId: string; clientX: number; clientY: number }) => void
  /** 在节点上点右键（UI-GRAPH-EDIT-02） */
  onNodeMenu?: (info: { kpId: string; clientX: number; clientY: number }) => void
  /** 每次重排标签后回报“当前显示几个标签 / 共几个节点”，页面据此提示“放大可看到更多标签” */
  onLabels?: (shown: number, total: number) => void
  /** 整组适应时四周留白（像素），缺省按学生页的搜索栏与右侧工具；教师页没有顶部浮层，可收紧 */
  fitPads?: Partial<FitPads>
}

export interface EnhancerDeps {
  graph(): CanvasGraph | null
  /** 画布容器的当前尺寸 */
  size(): readonly [number, number]
  enqueue(task: () => Promise<void>): void
  alive(): boolean
  onZoom(zoom: number): void
  options: EnhanceOptions
}

export interface EnhancedData {
  nodes: CanvasNode[]
  edges: CanvasEdge[]
}

export interface Enhancer {
  /** 当前视图状态（缩放档位、标签显示集） */
  readonly view: ViewState
  /** 记录最新数据（未装饰的副本）并返回装饰后的数据，交给 G6 */
  decorate(data: EnhancedData): EnhancedData
  /** 图创建后绑定事件 */
  attach(): void
  /** 数据画完之后（首次渲染、更新、布局、改尺寸）：同步档位、章节外框、重新排布标签 */
  afterRender(): Promise<void>
  /** 章节外框的成员（知识点 ID）；null 隐藏外框 */
  setScope(kpIds: readonly string[] | null): void
  /** 把一组知识点（缺省为全部）整体放进视口 */
  fitTo(kpIds?: readonly string[]): Promise<void>
  zoomBy(ratio: number): Promise<void>
  /** 节点在视口外时才把镜头移过去；在视口内不动 */
  ensureVisible(kpId: string): Promise<void>
  /** 浮层变化（出现、消失、展开收起）后重新排布标签 */
  relayoutLabels(): void
  /** 指针离开整个画布：结束悬停（悬停淡化的兜底之一，只依赖节点的 pointerleave 在快速移动时不可靠） */
  leaveHover(): void
  /** 当前各节点在画布容器内的屏幕位置与半径（UI-GRAPH-EDIT-02：悬停工具与连线命中）；取不到时为空数组 */
  anchors(): NodeAnchor[]
  /** 小地图里某个节点点的颜色：当前高亮靛紫、已掌握绿、学习中琥珀、其余石板灰 */
  minimapColor(elementId: string): string
  detach(): void
}

/** 安全读取缩放：G6 在初始化、销毁过程中就会发出视口事件，此时内部上下文可能没就绪，直接读会抛异步异常 */
export function zoomOf(g: CanvasGraph | null): number | null {
  if (g === null || g.getZoom === undefined) return null
  try {
    return g.getZoom()
  } catch {
    return null
  }
}

let measureContext: CanvasRenderingContext2D | null | undefined
const baseWidths = new Map<string, number>()

/** 用真实字体量文字宽度（13px 基准量一次再等比换算）：拉丁字母与全角字符宽度差很多，不能按字符数估算 */
export function measureLabel(text: string, fontPx: number): number {
  let base = baseWidths.get(text)
  if (base === undefined) {
    if (measureContext === undefined) {
      try {
        measureContext = document.createElement('canvas').getContext('2d')
      } catch {
        measureContext = null
      }
    }
    if (measureContext === null || measureContext === undefined) return text.length * fontPx
    measureContext.font = `500 ${LABEL_BASE_PX}px ${GRAPH_FONT}`
    base = measureContext.measureText(text).width
    baseWidths.set(text, base)
  }
  return (base / LABEL_BASE_PX) * fontPx
}

const round2 = (value: number): number => Math.round(value * 100) / 100

export function createEnhancer(deps: EnhancerDeps): Enhancer {
  const { options } = deps
  let view: ViewState = INITIAL_VIEW
  let nodes: CanvasNode[] = []
  let edges: CanvasEdge[] = []
  let chapterOf = new Map<string, string | null>()
  let importance = new Map<string, number>()
  let scope: readonly string[] | null = null
  /** 当前指针所在节点与已经生效的淡化节点分开，短暂划过只影响前者。 */
  let pointerId: string | null = null
  let hoverId: string | null = null
  let hoverEnter: ReturnType<typeof setTimeout> | null = null
  let hoverLeave: ReturnType<typeof setTimeout> | null = null
  /** null 表示重绘后状态未知，需要完整恢复；其余情况只提交差分。 */
  let appliedStates: Record<string, string[]> | null = null
  let dataRevision = 0
  let labelTimer: ReturnType<typeof setTimeout> | null = null
  let labelDirty = false
  let hullAdded = false
  let hullKey = ''
  let detached = false

  const live = () => !detached && deps.alive()
  const animation = (ms: number) => (options.reduceMotion?.() === true ? false : { duration: ms, easing: 'ease-out' })

  function decoratedNodes(): CanvasNode[] {
    return nodes.map((n) => ({ ...n, data: decorateNodeData(n.id, n.data, n.states, view) }))
  }
  function decoratedEdges(): CanvasEdge[] {
    return edges.map((e) => {
      const cross = (chapterOf.get(e.source) ?? null) !== (chapterOf.get(e.target) ?? null)
      const out = decorateEdge(e, cross, view)
      return { ...e, data: out.data, style: out.style }
    })
  }

  function decorate(data: EnhancedData): EnhancedData {
    nodes = data.nodes
    edges = data.edges
    dataRevision += 1
    const present = new Set(nodes.map((n) => n.id))
    if (hoverId !== null && !present.has(hoverId)) hoverId = null
    if (pointerId !== null && !present.has(pointerId)) endHover()
    if (hoverId === null && hoverLeave !== null) {
      clearTimeout(hoverLeave)
      hoverLeave = null
    }
    // 生命周期随后用这份数据 setData/render，基础状态因此成为新的比较起点。
    // afterRender 会把仍然有效的悬停叠回去，不能继续沿用上一份图的快照。
    appliedStates = hoverStateMap({ nodes, edges, hoverId: null, selectedId: selectedElement() })
    chapterOf = chapterOfNodes(nodes)
    const degree = new Map<string, number>()
    for (const e of edges) {
      degree.set(e.source, (degree.get(e.source) ?? 0) + 1)
      degree.set(e.target, (degree.get(e.target) ?? 0) + 1)
    }
    const max = Math.max(1, ...degree.values())
    importance = new Map(nodes.map((n) => [n.id, (degree.get(n.id) ?? 0) / max]))
    return { nodes: decoratedNodes(), edges: decoratedEdges() }
  }

  function selectedElement(): string | null {
    return nodes.find((n) => n.states?.includes('selected') === true)?.id ?? null
  }

  function stateMap(): Record<string, string[]> {
    return hoverStateMap({ nodes, edges, hoverId, selectedId: selectedElement() })
  }

  /** 在生命周期串行队列里调用；按状态顺序比较，因为后面的状态覆盖前面的样式。 */
  async function applyStates(g: CanvasGraph): Promise<void> {
    if (!live() || deps.graph() !== g || g.setElementState === undefined) return
    const revision = dataRevision
    const next = stateMap()
    const changed: Record<string, string[]> = {}
    for (const [id, states] of Object.entries(next)) {
      const previous = appliedStates?.[id]
      if (previous === undefined || previous.length !== states.length || states.some((state, index) => state !== previous[index])) {
        changed[id] = states
      }
    }
    if (Object.keys(changed).length === 0) return
    try {
      await g.setElementState(changed, false)
    } catch (error) {
      if (live() && deps.graph() === g && dataRevision === revision) appliedStates = null
      throw error
    }
    if (live() && deps.graph() === g && dataRevision === revision) appliedStates = next
  }

  /** 把当前视图状态写进元素数据并重绘；重绘会丢元素状态，所以随后重新写一次 */
  async function pushView(): Promise<void> {
    const g = deps.graph()
    if (!live() || g === null || g.updateNodeData === undefined || g.updateEdgeData === undefined || g.draw === undefined) return
    g.updateNodeData(decoratedNodes().map((n) => ({ id: n.id, data: n.data })))
    g.updateEdgeData(decoratedEdges().map((e) => ({ id: e.id, data: e.data, style: e.style })))
    await g.draw()
    if (!live() || deps.graph() !== g) return
    appliedStates = null
    await applyStates(g)
  }

  /** 按当前缩放重算档位；返回是否变化。档位量化，滚轮缩放时不会每帧重绘 */
  function syncView(zoom: number): boolean {
    const labelK = labelScale(zoom)
    const floors = scaleFloors(zoom, true)
    if (labelK === view.labelK && sameFloors(floors, view.floors)) return false
    view = { ...view, labelK, floors }
    return true
  }

  function planNow(): Set<string> | null {
    const g = deps.graph()
    if (g === null || g.getElementPosition === undefined || g.getViewportByCanvas === undefined) return null
    const zoom = zoomOf(g)
    const [width, height] = deps.size()
    if (zoom === null || width === 0) return null
    const o = options.obstacles?.() ?? { hard: [], soft: [] }
    const candidates: LabelCandidate[] = []
    for (const n of nodes) {
      let at: readonly number[]
      try {
        at = g.getViewportByCanvas(g.getElementPosition(n.id))
      } catch {
        continue
      }
      const states = n.states ?? []
      candidates.push({
        id: n.id,
        x: at[0]!,
        y: at[1]!,
        text: nodeLabel(n.data),
        // 强制只看是不是被预览/选中的那个节点：分数是累加的，不能用阈值判断
        forced: isForcedLabel(states),
        score: labelScore({ states, importance: importance.get(n.id), pathOrder: n.data.pathOrder }),
      })
    }
    return planLabels({
      candidates,
      viewport: { width, height },
      zoom,
      labelK: view.labelK,
      nodeK: view.floors.nodeK,
      obstacles: [...o.hard, ...o.soft],
      measure: options.measure ?? measureLabel,
    })
  }

  /**
   * 视口或数据变化后重新排布；只有显示集合变了才重绘。合并窗口内又来了新事件时，窗口结束后必须再算一次：
   * 镜头动画的最后一次视口事件常常落在窗口里，被吞掉的话排布会停在动画中途的位置上。
   */
  function scheduleLabels(): void {
    if (labelTimer !== null) {
      labelDirty = true
      return
    }
    labelTimer = setTimeout(() => {
      labelTimer = null
      if (!live()) return
      if (labelDirty) {
        labelDirty = false
        scheduleLabels()
        return
      }
      const next = planNow()
      if (next === null) return
      options.onLabels?.(next.size, nodes.length)
      const prev = view.labelShown
      if (prev !== null && prev.size === next.size && [...next].every((id) => prev.has(id))) return
      view = { ...view, labelShown: next }
      deps.enqueue(pushView)
    }, options.labelDelayMs ?? 90)
  }

  function drawHullSoon(g: CanvasGraph): void {
    requestAnimationFrame(() => {
      if (!live() || deps.graph() !== g) return
      try {
        ;(g.getPluginInstance?.('chapter-hull') as { drawHull?: () => void } | undefined)?.drawHull?.()
      } catch {
        /* 插件尚未就绪，下一次同步时再画 */
      }
    })
  }

  /**
   * 章节外框（`hull` 插件）：画在节点后面（`zIndex: -1`）。不要移除插件——G6 5.1.1 的 `Hull.destroy`
   * 读取未定义的 shape 会抛未捕获异常；首次添加后一直保留，只更新成员与可见性。
   * Hull 只在 `afterrender` 里绘制，我们是在渲染之后添加或更新的，所以要主动调 `drawHull`。
   */
  function syncHull(): void {
    const g = deps.graph()
    if (g === null || g.setPlugins === undefined || g.updatePlugin === undefined) return
    const present = new Set(nodes.map((n) => n.id))
    const ids = (scope ?? []).map(nodeElementId).filter((id) => present.has(id))
    const key = ids.join(',')
    if (key === hullKey) return
    hullKey = key
    if (!hullAdded) {
      if (ids.length === 0) return
      hullAdded = true
      g.setPlugins((prev) => [
        ...prev,
        {
          type: 'hull',
          key: 'chapter-hull',
          members: ids,
          padding: 34,
          corner: 'rounded',
          fill: GRAPH_COLORS.hullFill,
          fillOpacity: 1,
          stroke: GRAPH_COLORS.accent,
          lineWidth: 1.5,
          lineDash: [8, 5],
          zIndex: -1,
        },
      ])
    } else {
      g.updatePlugin({ key: 'chapter-hull', members: ids, visibility: ids.length === 0 ? 'hidden' : 'visible' })
    }
    drawHullSoon(g)
  }

  function applyHover(): void {
    const g = deps.graph()
    if (!live() || g === null || g.setElementState === undefined) return
    deps.enqueue(async () => {
      // 排到时再计算当前状态：快速切换只落地最新意图，不让旧悬停覆盖预览更新。
      await applyStates(g).catch(() => undefined)
    })
  }

  function endHover(): void {
    pointerId = null
    if (hoverEnter !== null) clearTimeout(hoverEnter)
    hoverEnter = null
    options.onHover?.(null)
    // 连续 canvas:pointermove 不重置截止时间，离开后最多保留 60ms。
    if (hoverId === null || hoverLeave !== null) return
    const g = deps.graph()
    // 稍等一下再恢复：从一个节点移到相邻节点时不闪（期间进入新节点会取消）
    hoverLeave = setTimeout(() => {
      hoverLeave = null
      if (!live() || deps.graph() !== g) return
      hoverId = null
      applyHover()
    }, 60)
  }

  function anchors(): NodeAnchor[] {
    const g = deps.graph()
    if (!live() || g === null || g.getElementPosition === undefined || g.getViewportByCanvas === undefined) return []
    const zoom = zoomOf(g) ?? 1
    // 节点在屏幕上的半径：基础尺寸 × 语义缩放的放大系数 × 缩放
    const r = (NODE_BASE_PX / 2) * view.floors.nodeK * zoom
    const out: NodeAnchor[] = []
    for (const node of nodes) {
      try {
        const at = g.getViewportByCanvas(g.getElementPosition(node.id))
        out.push({ kpId: node.data.kpId, x: at[0]!, y: at[1]!, r })
      } catch {
        /* 还没画出来或已移除的忽略 */
      }
    }
    return out
  }

  function attach(): void {
    const g = deps.graph()
    if (g === null) return
    // 语义缩放：缩小时标签按档位放大，屏幕上保持约 13px；节点、线、箭头按屏幕下限放大
    g.on('aftertransform', () => {
      if (!live() || deps.graph() !== g) return
      const zoom = zoomOf(g)
      if (zoom === null) return
      deps.onZoom(round2(zoom))
      if (syncView(zoom)) deps.enqueue(pushView)
      scheduleLabels()
    })
    g.on('canvas:click', () => {
      if (live() && deps.graph() === g) options.onBlankClick?.()
    })
    g.on('node:pointerenter', (event: GraphEvent) => {
      const id = event.target?.id
      // 触屏没有悬停：不做悬停淡化与 tooltip
      if (!live() || deps.graph() !== g || id === undefined || event.pointerType === 'touch') return
      const node = nodes.find((n) => n.id === id)
      if (node === undefined || pointerId === id) return
      if (hoverLeave !== null) clearTimeout(hoverLeave)
      hoverLeave = null
      if (hoverEnter !== null) clearTimeout(hoverEnter)
      hoverEnter = null
      pointerId = id
      // tooltip 自己等待 300ms；这里立即通知，避免把两个停留时间相加。
      options.onHover?.({ kpId: node.data.kpId, clientX: event.client?.x ?? 0, clientY: event.client?.y ?? 0 })
      if (hoverId === id) return
      hoverEnter = setTimeout(() => {
        hoverEnter = null
        if (!live() || deps.graph() !== g || pointerId !== id || !nodes.some((n) => n.id === id)) return
        hoverId = id
        applyHover()
      }, 120)
    })
    g.on('node:pointerleave', (event: GraphEvent) => {
      if (!live() || deps.graph() !== g) return
      // G6 快速切换时旧节点的 leave 可能晚于新节点的 enter。
      if (event.target?.id !== undefined && pointerId !== null && event.target.id !== pointerId) return
      if (pointerId !== null || hoverId !== null) endHover()
    })
    // 兜底：只依赖节点的 pointerleave 在快速移动时不可靠
    g.on('canvas:pointermove', () => {
      if (live() && deps.graph() === g && (pointerId !== null || hoverId !== null)) endHover()
    })
    g.on('edge:pointerenter', () => {
      if (live() && deps.graph() === g && (pointerId !== null || hoverId !== null)) endHover()
    })
    // UI-GRAPH-EDIT-02：关系线点击与节点右键，只转成契约 ID 交给页面，画布自己不改数据
    g.on('edge:click', (event: GraphEvent) => {
      if (!live() || deps.graph() !== g) return
      const edge = edges.find((e) => e.id === event.target?.id)
      if (edge === undefined) return
      options.onEdgeClick?.({ relationId: edge.data.relationId, clientX: event.client?.x ?? 0, clientY: event.client?.y ?? 0 })
    })
    g.on('node:contextmenu', (event: GraphEvent) => {
      if (!live() || deps.graph() !== g) return
      const node = nodes.find((n) => n.id === event.target?.id)
      if (node === undefined) return
      options.onNodeMenu?.({ kpId: node.data.kpId, clientX: event.client?.x ?? 0, clientY: event.client?.y ?? 0 })
    })
  }

  async function afterRender(): Promise<void> {
    const g = deps.graph()
    if (!live() || g === null) return
    const zoom = zoomOf(g)
    if (zoom !== null) {
      deps.onZoom(round2(zoom))
      if (syncView(zoom)) await pushView()
    }
    if (!live() || deps.graph() !== g) return
    await applyStates(g)
    if (!live() || deps.graph() !== g) return
    syncHull()
    scheduleLabels()
  }

  async function fitTo(kpIds?: readonly string[]): Promise<void> {
    const g = deps.graph()
    if (!live() || g === null || g.getElementPosition === undefined || g.getViewportByCanvas === undefined) return
    if (g.zoomTo === undefined || g.translateBy === undefined) return
    const present = new Set(nodes.map((n) => n.id))
    const ids = (kpIds === undefined ? nodes.map((n) => n.id) : kpIds.map(nodeElementId)).filter((id) => present.has(id))
    const points: Array<[number, number]> = []
    for (const id of ids) {
      try {
        const at = g.getElementPosition(id)
        points.push([at[0]!, at[1]!])
      } catch {
        /* 不在图中的忽略 */
      }
    }
    const [width, height] = deps.size()
    // 底部要避开小地图（按实际浮层高度算，软障碍不计）；上、左、右边距避开搜索栏与右侧工具
    const hard = options.obstacles?.().hard ?? []
    const fit = computeFit({
      points,
      viewport: { width, height },
      pads: { ...DEFAULT_PADS, ...options.fitPads, bottom: bottomPad(hard, height, options.fitPads?.bottom) },
      nodeRadius: 24 * view.floors.nodeK,
      bottomExtra: 48 * view.labelK * 0.4,
    })
    if (fit === null) return
    await g.zoomTo(fit.zoom, false)
    if (!live() || deps.graph() !== g) return
    const at = g.getViewportByCanvas(fit.center)
    await g.translateBy([fit.target[0] - at[0]!, fit.target[1] - at[1]!], animation(240))
    if (live()) {
      const zoom = zoomOf(g)
      if (zoom !== null) deps.onZoom(round2(zoom))
    }
  }

  return {
    get view() {
      return view
    },
    decorate,
    attach,
    afterRender,
    setScope(kpIds) {
      scope = kpIds
      syncHull()
    },
    fitTo,
    async zoomBy(ratio) {
      const g = deps.graph()
      if (!live() || g === null || g.zoomBy === undefined) return
      await g.zoomBy(ratio, animation(160))
      const zoom = zoomOf(g)
      if (live() && zoom !== null) deps.onZoom(round2(zoom))
    },
    async ensureVisible(kpId) {
      const g = deps.graph()
      if (!live() || g === null || g.getElementPosition === undefined || g.getViewportByCanvas === undefined) return
      const [width, height] = deps.size()
      try {
        const at = g.getViewportByCanvas(g.getElementPosition(nodeElementId(kpId)))
        const margin = 56
        if (at[0]! < margin || at[1]! < margin || at[0]! > width - margin || at[1]! > height - margin) {
          await g.focusElement?.(nodeElementId(kpId), animation(240))
        }
      } catch {
        await g.focusElement?.(nodeElementId(kpId), false)
      }
    },
    relayoutLabels: scheduleLabels,
    leaveHover() {
      if (live() && (pointerId !== null || hoverId !== null)) endHover()
    },
    anchors,
    minimapColor(elementId) {
      const states = nodes.find((n) => n.id === elementId)?.states ?? []
      if (states.includes('selected')) return GRAPH_COLORS.accent
      if (states.includes('mastered')) return GRAPH_COLORS.ok
      if (states.includes('learning')) return GRAPH_COLORS.warn
      return GRAPH_COLORS.nodeStroke
    },
    detach() {
      detached = true
      if (labelTimer !== null) clearTimeout(labelTimer)
      if (hoverEnter !== null) clearTimeout(hoverEnter)
      if (hoverLeave !== null) clearTimeout(hoverLeave)
      labelTimer = null
      hoverEnter = null
      hoverLeave = null
      pointerId = null
      hoverId = null
      appliedStates = null
    },
  }
}
