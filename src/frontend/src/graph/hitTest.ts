/**
 * 节点命中（UI-GRAPH-EDIT-02）：连线拖动时判断指针落在哪个节点上。纯函数。
 * 坐标是画布容器内的屏幕坐标（左上角为原点），由画布在拖动开始时给出一份快照。
 */
export interface NodeAnchor {
  kpId: string
  /** 圆心（容器内屏幕坐标） */
  x: number
  y: number
  /** 屏幕上的半径 */
  r: number
}

/** 指针在半径加 `slop` 之内即命中；多个命中取圆心最近的 */
export function nodeAt(anchors: readonly NodeAnchor[], x: number, y: number, options: { slop?: number; exclude?: string } = {}): NodeAnchor | null {
  const slop = options.slop ?? 6
  let best: NodeAnchor | null = null
  let bestDistance = Infinity
  for (const anchor of anchors) {
    if (anchor.kpId === options.exclude) continue
    const distance = Math.hypot(anchor.x - x, anchor.y - y)
    if (distance <= anchor.r + slop && distance < bestDistance) {
      best = anchor
      bestDistance = distance
    }
  }
  return best
}
