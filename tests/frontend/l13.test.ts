import { flushPromises } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import { edgeElementId, nodeElementId, RELATION_STYLES, type G6Edge, type G6Node, type RelationType } from '../../src/frontend/src/graph/adapter'
import {
  createGraphLifecycle,
  READABLE_ZOOM,
  type CanvasGraph,
  type CanvasGraphInit,
  type GraphCanvasData,
} from '../../src/frontend/src/graph/lifecycle'

// L13-1（R06）：节点多时整图适配会把图缩成一条不可读的细线（L11 走查截图：129 个节点）。
// 初始视口不低于可读缩放并聚焦到入口节点；页面可按知识点聚焦（搜索、问答跳转用）。

class ZoomGraph implements CanvasGraph {
  destroyed = false
  calls: string[] = []
  zoom: number
  constructor(readonly init: CanvasGraphInit, zoomAfterFit: number) {
    this.zoom = zoomAfterFit
  }
  async render() { this.calls.push('render') }
  setData() { this.calls.push('setData') }
  setSize() { this.calls.push('setSize') }
  async fitView() { this.calls.push('fitView') }
  on() { return undefined }
  destroy() { this.destroyed = true }
  getZoom() { return this.zoom }
  async zoomTo(zoom: number) { this.calls.push(`zoomTo ${zoom}`); this.zoom = zoom }
  async focusElement(id: string) { this.calls.push(`focus ${id}`) }
}

/** 不实现可选视口方法的旧替身（H04 同款），确保兼容 */
class PlainGraph implements CanvasGraph {
  destroyed = false
  async render() {}
  setData() {}
  setSize() {}
  async fitView() {}
  on() { return undefined }
  destroy() { this.destroyed = true }
}

function container(): HTMLElement {
  const el = document.createElement('div')
  Object.defineProperty(el, 'clientWidth', { value: 800 })
  Object.defineProperty(el, 'clientHeight', { value: 600 })
  return el
}

function node(id: string): G6Node {
  return {
    id: nodeElementId(id),
    data: { kpId: id, name: id.toUpperCase(), type: 'concept', level: 0, chapterId: 'ch', status: 'approved',
            confidence: 0.9, source: 'ai', locked: false },
  } as G6Node
}

function edge(id: string, type: RelationType, from: string, to: string): G6Edge {
  const s = RELATION_STYLES[type]
  return {
    id: edgeElementId(id), source: nodeElementId(from), target: nodeElementId(to),
    data: { relationId: id, type, directed: s.directed, status: 'approved', confidence: 0.8, source: 'ai', downgraded: false },
    style: { stroke: s.stroke, lineWidth: s.lineWidth, lineDash: [...s.lineDash], endArrow: s.directed, labelText: s.label },
  } as G6Edge
}

// b 在数据里排第一，但 a 才是没有前置（入度为 0）的入口节点
const DATA: GraphCanvasData = {
  nodes: [node('b'), node('a'), node('c')],
  edges: [edge('r1', 'PREREQUISITE', 'a', 'b'), edge('r2', 'PREREQUISITE', 'b', 'c')],
}

function start(zoomAfterFit: number, onZoom?: (zoom: number) => void) {
  let graph!: ZoomGraph
  const life = createGraphLifecycle(container(), {
    data: DATA,
    factory: (init) => (graph = new ZoomGraph(init, zoomAfterFit)),
    onZoom,
  })
  return { life, graph: () => graph }
}

describe('L13-1 可读的初始视口', () => {
  it('整图适配后缩放低于可读值：放大到可读缩放并聚焦到第一个没有前置的节点', async () => {
    const zooms: number[] = []
    const { graph } = start(0.2, (z) => zooms.push(z))
    await flushPromises()
    expect(graph().calls).toEqual(['render', `zoomTo ${READABLE_ZOOM}`, `focus ${nodeElementId('a')}`])
    expect(zooms.at(-1)).toBe(READABLE_ZOOM)
  })

  it('本来就可读时不改缩放、不移动视口', async () => {
    const zooms: number[] = []
    const { graph } = start(1.2, (z) => zooms.push(z))
    await flushPromises()
    expect(graph().calls).toEqual(['render'])
    expect(zooms.at(-1)).toBe(1.2)
  })

  it('focus(kpId) 聚焦到对应节点；未知节点不动', async () => {
    const { life, graph } = start(1.2)
    await flushPromises()
    life.focus('c')
    life.focus('not-here')
    await flushPromises()
    expect(graph().calls).toEqual(['render', `focus ${nodeElementId('c')}`])
  })

  it('建图前请求的聚焦在首次渲染后落到该节点（取代入口节点）', async () => {
    let graph!: ZoomGraph
    const el = document.createElement('div')
    Object.defineProperty(el, 'clientWidth', { value: 0, configurable: true })
    Object.defineProperty(el, 'clientHeight', { value: 0, configurable: true })
    const life = createGraphLifecycle(el, { data: DATA, factory: (init) => (graph = new ZoomGraph(init, 0.2)) })
    life.focus('c')
    Object.defineProperty(el, 'clientWidth', { value: 800 })
    Object.defineProperty(el, 'clientHeight', { value: 600 })
    life.refreshSize()
    await new Promise((resolve) => setTimeout(resolve, 30))
    await flushPromises()
    expect(graph.calls).toEqual(['render', `zoomTo ${READABLE_ZOOM}`, `focus ${nodeElementId('c')}`])
  })

  it('替身不实现视口方法时照常渲染，不报错', async () => {
    const statuses: string[] = []
    const life = createGraphLifecycle(container(), {
      data: DATA, factory: () => new PlainGraph(), onStatus: (s) => statuses.push(s),
    })
    life.focus('a')
    await flushPromises()
    expect(statuses.at(-1)).toBe('ready')
  })
})
