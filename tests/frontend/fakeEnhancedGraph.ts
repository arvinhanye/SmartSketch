import { vi } from 'vitest'
import type { CanvasGraph, CanvasGraphInit, GraphEvent } from '../../src/frontend/src/graph/lifecycle'

/**
 * G6 `Graph` 的测试替身，实现增强模式用到的全部可选方法（`CanvasGraph`）。
 * 记录调用与数据更新，`emit` 手动派发画布事件；`getViewportByCanvas` 是简单的缩放 + 平移变换。
 */
export type Update = Array<{ id: string; data: Record<string, unknown> }>

export class FakeEnhancedGraph implements CanvasGraph {
  destroyed = false
  zoom = 1
  offset: [number, number] = [0, 0]
  calls: string[] = []
  nodeUpdates: Update[] = []
  edgeUpdates: Update[] = []
  stateCalls: Array<Record<string, string[]>> = []
  pluginsAdded: unknown[][] = []
  pluginUpdates: Array<Record<string, unknown>> = []
  focusCalls: Array<[string, unknown]> = []
  drawHull = vi.fn()
  handlers = new Map<string, Array<(event: GraphEvent) => void>>()

  constructor(
    readonly pos: Record<string, [number, number]> = {},
    readonly init?: CanvasGraphInit,
  ) {
    // 带初始坐标的节点（章节布局）直接取它们的位置
    for (const node of init?.data.nodes ?? []) {
      const at = (node as { style?: { x: number; y: number } }).style
      if (at !== undefined) this.pos[node.id] = [at.x, at.y]
    }
  }

  data: unknown = null
  render(): Promise<void> {
    this.calls.push('render')
    return Promise.resolve()
  }
  setData(data: unknown): void {
    this.calls.push('setData')
    this.data = data
  }
  setSize(width: number, height: number): void {
    this.calls.push(`setSize ${width}x${height}`)
  }
  fitView(): Promise<void> {
    this.calls.push('fitView')
    return Promise.resolve()
  }
  on(event: string, handler: (event: GraphEvent) => void): this {
    this.handlers.set(event, [...(this.handlers.get(event) ?? []), handler])
    return this
  }
  emit(event: string, payload: GraphEvent = {}): void {
    for (const handler of this.handlers.get(event) ?? []) handler(payload)
  }
  destroy(): void {
    this.calls.push('destroy')
    this.destroyed = true
  }
  getZoom(): number {
    return this.zoom
  }
  zoomTo(zoom: number): Promise<void> {
    this.zoom = zoom
    this.calls.push(`zoomTo ${zoom}`)
    this.emit('aftertransform')
    return Promise.resolve()
  }
  zoomBy(ratio: number): Promise<void> {
    this.calls.push(`zoomBy ${ratio}`)
    this.zoom *= ratio
    return Promise.resolve()
  }
  getElementPosition(id: string): number[] {
    const at = this.pos[id]
    if (at === undefined) throw new Error('no such element')
    return [...at]
  }
  getViewportByCanvas(point: readonly number[]): number[] {
    return [point[0]! * this.zoom + this.offset[0], point[1]! * this.zoom + this.offset[1]]
  }
  translateBy(offset: readonly number[]): Promise<void> {
    this.offset = [this.offset[0] + offset[0]!, this.offset[1] + offset[1]!]
    this.calls.push('translateBy')
    return Promise.resolve()
  }
  focusElement(id: string, animation?: unknown): Promise<void> {
    this.focusCalls.push([id, animation])
    return Promise.resolve()
  }
  updateNodeData(data: ReadonlyArray<Record<string, unknown>>): void {
    this.nodeUpdates.push(data as Update)
  }
  updateEdgeData(data: ReadonlyArray<Record<string, unknown>>): void {
    this.edgeUpdates.push(data as Update)
  }
  draw(): Promise<void> {
    this.calls.push('draw')
    return Promise.resolve()
  }
  setElementState(state: Record<string, string[]>): Promise<void> {
    this.stateCalls.push(state)
    return Promise.resolve()
  }
  setPlugins(update: (plugins: unknown[]) => unknown[]): void {
    this.pluginsAdded.push(update([]))
  }
  updatePlugin(option: Record<string, unknown>): void {
    this.pluginUpdates.push(option)
  }
  getPluginInstance(): unknown {
    return { drawHull: this.drawHull }
  }
}
