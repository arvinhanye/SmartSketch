/**
 * 图谱布局（设计规格 §4.1，用户确认采用「章节分区 + 紧凑间距」）。纯函数，不渲染。
 *
 * 现状的问题：四类关系全部参与布局，跨章长线和「例题挂在远处」把画布拉成 5:1 的长条
 * （96 节点 9042×1792，适应一屏缩放 0.10，没有一章能放进一屏）。
 *
 * 三种模式：
 * - all：四类关系全部参与（现状基线，只用于对比测量）
 * - hier：只有 PREREQUISITE 与 CONTAINS 决定层级；RELATED_TO / EXAMPLE_OF 照常画，但不再拉扯位置，
 *         没有层级边的节点作为「卫星」放到所关联节点旁边，无关联的孤立节点排成网格
 * - chapter（默认）：在 hier 的基础上每章单独布局，各章按课程顺序排成分区
 *
 * 任何模式都不删除、不隐藏任何关系。缺章节信息的节点归入「未归章」分区。
 */
import type { RelationType } from './adapter'

export type LayoutMode = 'all' | 'hier' | 'chapter'

export interface LayoutNode {
  id: string
  /** 所属章节 id；null 表示未归章 */
  chapter: string | null
}

export interface LayoutEdge {
  id: string
  source: string
  target: string
  type: RelationType
}

export type Positions = Map<string, { x: number; y: number }>

export interface LayoutOptions {
  nodesep: number
  ranksep: number
  /** 卫星/孤立节点占位格子的宽高（含标签） */
  cellW: number
  cellH: number
  /** 章节分区之间的间距 */
  laneGap: number
  /** 排版时参照的视口（画布像素）：在多种列数里选「适应该视口时缩放最大」的一种 */
  viewport: readonly [number, number]
}

/**
 * 紧凑间距。注意 G6 `antv-dagre` 的实际间距是「节点尺寸 + 3×nodesep」「节点尺寸 + 2×ranksep」，
 * 原来的 56 / 110 实际是 204 / 256，比设定值宽松很多；这里的 28 / 57 实际约 120 / 150。
 */
export const COMPACT_OPTIONS: Readonly<LayoutOptions> = Object.freeze({
  nodesep: 28,
  ranksep: 57,
  cellW: 120,
  cellH: 100,
  laneGap: 100,
  viewport: [884, 732] as const,
})

/** 层级布局引擎：给一组节点和它们之间的层级边，返回每个节点的位置。可替换，便于测试 */
export type DagreEngine = (
  ids: string[],
  edges: Array<{ source: string; target: string }>,
  options: LayoutOptions,
) => Promise<Positions>

/** 默认引擎：G6 自带的 antv-dagre（按需加载，不新增依赖） */
export const g6DagreEngine: DagreEngine = async (ids, edges, o) => {
  const pos: Positions = new Map()
  if (ids.length === 0) return pos
  const { AntVDagreLayout } = await import('@antv/g6')
  const layout = new AntVDagreLayout({ rankdir: 'TB', nodesep: o.nodesep, ranksep: o.ranksep, nodeSize: [36, 36] } as never)
  await layout.execute({
    nodes: ids.map((id) => ({ id })),
    edges: edges.map((e, i) => ({ id: `e${i}`, source: e.source, target: e.target })),
  } as never)
  layout.forEachNode((node) => {
    // G6 的节点 id 类型是 string | number，位置字段在布局后一定存在
    pos.set(String(node.id), { x: Number(node.x), y: Number(node.y) })
  })
  return pos
}

/**
 * 径向布局引擎（可替换 {@link g6DagreEngine}）：先修/包含关系按最长路径分层，每个节点取「上一层」的一个父节点形成生成树，
 * 根在圆心（多个根时排在第一圈），子树按叶子数占据连续扇区。适合单章里一棵大树被层次布局拉成 10:1 长条的情形。
 * 不属于生成树的边照常画，只是不参与摆位。同输入同输出。
 */
export const radialEngine: DagreEngine = async (ids, edges) => {
  const pos: Positions = new Map()
  if (ids.length === 0) return pos
  const known = new Set(ids)
  const typed = edges.filter((e) => known.has(e.source) && known.has(e.target) && e.source !== e.target) as Array<{
    source: string
    target: string
    type?: string
  }>
  // 最长路径深度；迭代次数封顶，坏数据（环）不会死循环
  const depth = new Map(ids.map((id) => [id, 0]))
  for (let round = 0; round < ids.length; round += 1) {
    let changed = false
    for (const e of typed) {
      const next = depth.get(e.source)! + 1
      if (next > depth.get(e.target)! && next < ids.length) {
        depth.set(e.target, next)
        changed = true
      }
    }
    if (!changed) break
  }
  // 父节点：深度恰好少 1 的入边来源，包含关系优先，其次按 id 排序；找不到就当根
  const parent = new Map<string, string>()
  for (const id of [...ids].sort()) {
    const d = depth.get(id)!
    if (d === 0) continue
    const candidates = typed
      .filter((e) => e.target === id && depth.get(e.source) === d - 1)
      .sort((a, b) => Number(b.type === 'CONTAINS') - Number(a.type === 'CONTAINS') || a.source.localeCompare(b.source))
    if (candidates[0] !== undefined) parent.set(id, candidates[0].source)
  }
  const children = new Map<string, string[]>()
  const roots: string[] = []
  for (const id of [...ids].sort()) {
    const p = parent.get(id)
    if (p === undefined) roots.push(id)
    else children.set(p, [...(children.get(p) ?? []), id])
  }
  // 树内的真实层数（根为 0）
  const level = new Map<string, number>()
  const order: string[] = []
  const walk = [...roots]
  for (const r of roots) level.set(r, 0)
  while (walk.length > 0) {
    const id = walk.shift()!
    order.push(id)
    for (const c of children.get(id) ?? []) {
      level.set(c, level.get(id)! + 1)
      walk.push(c)
    }
  }
  const weight = new Map<string, number>()
  for (const id of [...order].reverse()) {
    const kids = children.get(id) ?? []
    weight.set(id, kids.length === 0 ? 1 : kids.reduce((sum, k) => sum + weight.get(k)!, 0))
  }
  const single = roots.length === 1
  const ring = (id: string) => level.get(id)! + (single ? 0 : 1)
  // 角度：子树按权重平分父节点的扇区
  const angle = new Map<string, number>()
  const assign = (id: string, from: number, to: number) => {
    angle.set(id, (from + to) / 2)
    let cursor = from
    const total = weight.get(id)!
    for (const c of children.get(id) ?? []) {
      const span = ((to - from) * weight.get(c)!) / total
      assign(c, cursor, cursor + span)
      cursor += span
    }
  }
  const totalWeight = roots.reduce((sum, r) => sum + weight.get(r)!, 0)
  let cursor = -Math.PI / 2
  for (const r of roots) {
    const span = (2 * Math.PI * weight.get(r)!) / totalWeight
    assign(r, cursor, cursor + span)
    cursor += span
  }
  // 半径：每圈至少比上一圈远一个间距，并且该圈上相邻节点的弧长不小于最小间距
  const SPACING = 66
  const RING_GAP = 96
  // 教师画布是宽画布（约 1.8:1）：横向拉伸成椭圆，适应视口时缩放更大；只拉伸 x，节点间距不会变小
  const STRETCH_X = 1.5
  const rings = new Map<number, string[]>()
  for (const id of order) rings.set(ring(id), [...(rings.get(ring(id)) ?? []), id])
  const radius = new Map<number, number>()
  let previous = single ? 0 : -RING_GAP + 0
  for (const k of [...rings.keys()].sort((a, b) => a - b)) {
    if (single && k === 0) {
      radius.set(0, 0)
      previous = 0
      continue
    }
    const onRing = rings.get(k)!.map((id) => angle.get(id)!).sort((a, b) => a - b)
    let minGap = 2 * Math.PI
    for (let i = 0; i < onRing.length; i += 1) {
      const next = i === onRing.length - 1 ? onRing[0]! + 2 * Math.PI : onRing[i + 1]!
      minGap = Math.min(minGap, next - onRing[i]!)
    }
    const needed = onRing.length > 1 ? SPACING / Math.max(minGap, 0.001) : 0
    const r = Math.min(8000, Math.max(previous + RING_GAP, needed, single ? 0 : RING_GAP))
    radius.set(k, r)
    previous = r
  }
  for (const id of order) {
    const r = radius.get(ring(id))!
    const a = angle.get(id)!
    pos.set(id, r === 0 ? { x: 0, y: 0 } : { x: Math.round(r * Math.cos(a) * STRETCH_X * 100) / 100, y: Math.round(r * Math.sin(a) * 100) / 100 })
  }
  return pos
}

/** 层次布局被拉成长条（宽高比 > 3）且节点不少时，推荐径向布局作为默认视图 */
export function prefersRadial(pos: Positions): boolean {
  if (pos.size < 24) return false
  const pts = [...pos.values()]
  const xs = pts.map((p) => p.x)
  const ys = pts.map((p) => p.y)
  const w = Math.max(...xs) - Math.min(...xs)
  const h = Math.max(...ys) - Math.min(...ys)
  return w / Math.max(h, 1) > 3
}

const isHierarchy = (type: RelationType): boolean => type === 'PREREQUISITE' || type === 'CONTAINS'

/**
 * 把没有层级边的节点放到「它所关联的节点」旁边最近的空位。
 * 用真实坐标做矩形碰撞：dagre 的坐标并不落在整齐的格子上，格子取整会让卫星压到别的层的节点上。
 * 返回找不到关联（或周围没有空位）的节点。
 */
function placeSatellites(
  pos: Positions,
  free: string[],
  edges: LayoutEdge[],
  o: LayoutOptions,
  within: ReadonlySet<string>,
): string[] {
  const taken: Array<{ x: number; y: number }> = [...pos.values()]
  const collides = (x: number, y: number) =>
    taken.some((t) => Math.abs(t.x - x) < o.cellW * 0.9 && Math.abs(t.y - y) < o.cellH * 0.9)
  const leftover: string[] = []
  const anchorOf = (id: string): string | null => {
    // 应用实例优先（例题挨着它说明的知识点），其次相关
    for (const type of ['EXAMPLE_OF', 'RELATED_TO'] as const) {
      for (const e of edges) {
        if (e.type !== type) continue
        const other = e.source === id ? e.target : e.target === id ? e.source : null
        if (other !== null && pos.has(other) && within.has(other)) return other
      }
    }
    return null
  }
  // 以锚点为中心的螺旋搜索顺序：优先右侧，再下方
  const ring: Array<[number, number]> = []
  for (let r = 1; r <= 8; r += 1) {
    for (let dy = 0; dy <= r; dy += 1) for (const dx of [r, -r]) ring.push([dx, dy])
    for (let dx = 0; dx < r; dx += 1) ring.push([dx, r])
  }
  for (const id of free) {
    const anchor = anchorOf(id)
    if (anchor === null) {
      leftover.push(id)
      continue
    }
    const base = pos.get(anchor)!
    let placed = false
    for (const [dx, dy] of ring) {
      const x = base.x + dx * o.cellW
      const y = base.y + dy * o.cellH
      if (!collides(x, y)) {
        pos.set(id, { x, y })
        taken.push({ x, y })
        placed = true
        break
      }
    }
    if (!placed) leftover.push(id)
  }
  return leftover
}

/** 布局一个节点集合（全局或某一章）：层级节点走引擎，其余作为卫星或排成网格 */
async function layoutGroup(
  nodes: LayoutNode[],
  edges: LayoutEdge[],
  o: LayoutOptions,
  engine: DagreEngine,
): Promise<Positions> {
  const ids = new Set(nodes.map((n) => n.id))
  const inGroup = edges.filter((e) => ids.has(e.source) && ids.has(e.target))
  const hierarchy = inGroup.filter((e) => isHierarchy(e.type))
  const connected = new Set<string>()
  for (const e of hierarchy) {
    connected.add(e.source)
    connected.add(e.target)
  }
  const main = nodes.filter((n) => connected.has(n.id)).map((n) => n.id)
  const pos = await engine(main, hierarchy, o)
  const free = nodes.filter((n) => !connected.has(n.id)).map((n) => n.id)
  if (free.length === 0) return pos
  const leftover = placeSatellites(pos, free, inGroup, o, ids)
  if (leftover.length > 0) {
    let maxY = 0
    let minX = Infinity
    let maxX = -Infinity
    for (const p of pos.values()) {
      maxY = Math.max(maxY, p.y)
      minX = Math.min(minX, p.x)
      maxX = Math.max(maxX, p.x)
    }
    if (!Number.isFinite(minX)) {
      minX = 0
      maxX = o.cellW * 3
    }
    // 列数取「现有宽度能放下的列数」与「接近 1.4:1 的网格」两者较大者，避免没有层级边时排成一条长带
    const cols = Math.max(3, Math.floor((maxX - minX) / o.cellW) + 1, Math.ceil(Math.sqrt(leftover.length * 1.4)))
    const top = pos.size === 0 ? 0 : maxY + o.cellH * 1.4
    leftover.forEach((id, i) =>
      pos.set(id, { x: minX + (i % cols) * o.cellW, y: top + o.cellH * Math.floor(i / cols) }),
    )
  }
  return pos
}

const NO_CHAPTER = '__none__'

export async function computeLayout(
  nodes: readonly LayoutNode[],
  edges: readonly LayoutEdge[],
  mode: LayoutMode,
  chapterOrder: readonly string[],
  options: Partial<LayoutOptions> = {},
  engine: DagreEngine = g6DagreEngine,
): Promise<Positions> {
  const o: LayoutOptions = { ...COMPACT_OPTIONS, ...options }
  if (nodes.length === 0) return new Map()
  const known = new Set(nodes.map((n) => n.id))
  const valid = edges.filter((e) => known.has(e.source) && known.has(e.target))

  if (mode === 'all') {
    // 现状：全部关系参与；孤立节点由引擎自己放在第一行
    return engine(nodes.map((n) => n.id), valid, o)
  }
  if (mode === 'hier') return layoutGroup([...nodes], valid, o, engine)

  // chapter：每章单独布局，再按课程顺序排成分区
  const groups = new Map<string, LayoutNode[]>()
  for (const n of nodes) {
    const key = n.chapter ?? NO_CHAPTER
    groups.set(key, [...(groups.get(key) ?? []), n])
  }
  // 目录里有的章节按目录顺序；目录里没有的章节按出现顺序跟在后面；未归章最后。节点不能因为目录缺失而消失
  const listed = chapterOrder.filter((c) => groups.has(c))
  const unlisted = [...groups.keys()].filter((c) => c !== NO_CHAPTER && !chapterOrder.includes(c))
  const keys = [...listed, ...unlisted, ...(groups.has(NO_CHAPTER) ? [NO_CHAPTER] : [])]

  const blocks: Array<{ pos: Positions; w: number; h: number }> = []
  for (const key of keys) {
    const pos = await layoutGroup(groups.get(key)!, valid, o, engine)
    let minX = Infinity
    let minY = Infinity
    let maxX = -Infinity
    let maxY = -Infinity
    for (const p of pos.values()) {
      minX = Math.min(minX, p.x)
      minY = Math.min(minY, p.y)
      maxX = Math.max(maxX, p.x)
      maxY = Math.max(maxY, p.y)
    }
    const normalized: Positions = new Map([...pos].map(([id, p]) => [id, { x: p.x - minX, y: p.y - minY }]))
    blocks.push({ pos: normalized, w: maxX - minX, h: maxY - minY })
  }

  // 行式排版：按课程顺序从左到右、从上到下；试遍各种行宽，选「适应视口时缩放最大」的一种
  const pack = (targetW: number) => {
    const placed: Array<[string, { x: number; y: number }]> = []
    let x = 0
    let y = 0
    let rowH = 0
    let maxX = 0
    for (const b of blocks) {
      if (x > 0 && x + b.w > targetW) {
        x = 0
        y += rowH + o.laneGap
        rowH = 0
      }
      for (const [id, p] of b.pos) placed.push([id, { x: x + p.x, y: y + p.y }])
      maxX = Math.max(maxX, x + b.w)
      x += b.w + o.laneGap
      rowH = Math.max(rowH, b.h)
    }
    const fit = Math.min(o.viewport[0] / (maxX + 200), o.viewport[1] / (y + rowH + 200))
    return { placed, fit }
  }
  const widest = Math.max(...blocks.map((b) => b.w), 1)
  let best = pack(widest)
  for (let cols = 2; cols <= blocks.length; cols += 1) {
    const width = blocks.slice(0, cols).reduce((sum, b) => sum + b.w, 0) + (cols - 1) * o.laneGap
    const candidate = pack(Math.max(widest, width))
    if (candidate.fit > best.fit) best = candidate
  }
  return new Map(best.placed)
}

// ------------------------------------------------------------------ 度量（验收与测试用）

export interface LayoutMetrics {
  bbox: [number, number]
  /** 宽 / 高 */
  aspect: number
  /** 适应给定视口时的缩放（不含 0.2 的下限，便于比较） */
  fitZoom: number
  /** 最近的两个节点中心距；小于节点直径（36）说明重叠 */
  minNodeDist: number
  chapters: { n: number; fitOneScreen: number }
  /** 章内先修边是否向下 */
  prereqWithinDownShare: number
}

export function layoutMetrics(
  pos: Positions,
  nodes: readonly LayoutNode[],
  edges: readonly LayoutEdge[],
  viewport: readonly [number, number] = COMPACT_OPTIONS.viewport,
  readableZoom = 0.9,
): LayoutMetrics {
  const pts = [...pos.values()]
  const xs = pts.map((p) => p.x)
  const ys = pts.map((p) => p.y)
  const W = Math.max(...xs) - Math.min(...xs)
  const H = Math.max(...ys) - Math.min(...ys)
  let minDist = Infinity
  for (let i = 0; i < pts.length; i += 1) {
    for (let j = i + 1; j < pts.length; j += 1) {
      minDist = Math.min(minDist, Math.hypot(pts[i]!.x - pts[j]!.x, pts[i]!.y - pts[j]!.y))
    }
  }
  const chapterOf = new Map(nodes.map((n) => [n.id, n.chapter]))
  const byChapter = new Map<string, string[]>()
  for (const n of nodes) byChapter.set(n.chapter ?? NO_CHAPTER, [...(byChapter.get(n.chapter ?? NO_CHAPTER) ?? []), n.id])
  const vw = viewport[0] / readableZoom
  const vh = viewport[1] / readableZoom
  let fits = 0
  for (const ids of byChapter.values()) {
    const px = ids.map((i) => pos.get(i)!.x)
    const py = ids.map((i) => pos.get(i)!.y)
    if (Math.max(...px) - Math.min(...px) <= vw && Math.max(...py) - Math.min(...py) <= vh) fits += 1
  }
  const within = edges.filter((e) => e.type === 'PREREQUISITE' && chapterOf.get(e.source) === chapterOf.get(e.target))
  const down = within.filter((e) => pos.get(e.target)!.y > pos.get(e.source)!.y).length
  return {
    bbox: [Math.round(W), Math.round(H)],
    aspect: +(W / Math.max(H, 1)).toFixed(2),
    fitZoom: Math.min(viewport[0] / (W + 200), viewport[1] / (H + 200)),
    minNodeDist: Math.round(minDist),
    chapters: { n: byChapter.size, fitOneScreen: fits },
    prereqWithinDownShare: +(down / Math.max(within.length, 1)).toFixed(2),
  }
}
