import { describe, expect, it } from 'vitest'
import { planLabels, type Box, type LabelCandidate, type LabelPlanInput } from '../../src/frontend/src/graph/labelPlan'

/** 每个字符占 fontPx（全角近似）；测试用，不依赖真实字体 */
const measure = (text: string, fontPx: number) => text.length * fontPx

function candidate(id: string, x: number, y: number, over: Partial<LabelCandidate> = {}): LabelCandidate {
  return { id, x, y, text: '知识点', score: 0, forced: false, ...over }
}

function input(candidates: LabelCandidate[], over: Partial<LabelPlanInput> = {}): LabelPlanInput {
  return {
    candidates,
    viewport: { width: 800, height: 600 },
    zoom: 1,
    labelK: 1,
    nodeK: 1,
    obstacles: [],
    measure,
    ...over,
  }
}

describe('标签排布 planLabels', () => {
  it('互不重叠的标签都显示', () => {
    const shown = planLabels(input([candidate('a', 100, 100), candidate('b', 400, 100), candidate('c', 100, 400)]))
    expect([...shown].sort()).toEqual(['a', 'b', 'c'])
  })

  it('重叠时分数高的保留、低的隐藏，与输入顺序无关', () => {
    const near = [candidate('low', 100, 100, { score: 1 }), candidate('high', 110, 100, { score: 9 })]
    expect([...planLabels(input(near))]).toEqual(['high'])
    expect([...planLabels(input([...near].reverse()))]).toEqual(['high'])
  })

  it('分数相同按 id 决定，结果稳定', () => {
    const tie = [candidate('b', 100, 100), candidate('a', 105, 100)]
    expect([...planLabels(input(tie))]).toEqual(['a'])
    expect([...planLabels(input([...tie].reverse()))]).toEqual(['a'])
  })

  it('forced（被预览/选中的节点）即使重叠也显示，且不会因为分数低而被挤掉', () => {
    const shown = planLabels(
      input([candidate('a', 100, 100, { score: 500 }), candidate('picked', 105, 100, { score: 0, forced: true })]),
    )
    expect(shown.has('picked')).toBe(true)
    // 高分的先排：picked 作为 forced 后排但仍放入
    expect(shown.has('a')).toBe(true)
  })

  it('高分（如章节成员 950 + 推荐项 300）不是强制：仍然要避让', () => {
    const shown = planLabels(
      input([candidate('chapter-a', 100, 100, { score: 1250 }), candidate('chapter-b', 105, 100, { score: 950 })]),
    )
    expect([...shown]).toEqual(['chapter-a'])
  })

  it('视口外（超出边距）的标签不参与排布', () => {
    const shown = planLabels(input([candidate('in', 10, 10), candidate('out', 900, 100), candidate('above', 100, -80)]))
    expect([...shown]).toEqual(['in'])
  })

  it('落在浮层（工具栏、图例、小地图…）下面的标签不显示，forced 也一样', () => {
    const obstacles: Box[] = [[0, 0, 300, 200]]
    const shown = planLabels(
      input([candidate('under', 100, 100), candidate('picked', 120, 90, { forced: true }), candidate('free', 500, 400)], {
        obstacles,
      }),
    )
    expect([...shown]).toEqual(['free'])
  })

  it('按真实宽度判断重叠：长文字挡住邻居，短文字不挡', () => {
    const wide = planLabels(
      input(
        [
          candidate('long', 100, 100, { text: '基于哈希函数的冲突处理策略', score: 5 }),
          candidate('near', 150, 100, { text: '堆', score: 1 }), // 长标签换行宽度 112，右缘约 164
        ],
        { measure },
      ),
    )
    expect(wide.has('near')).toBe(false)
    const narrow = planLabels(
      input([candidate('s1', 100, 100, { text: '栈', score: 5 }), candidate('s2', 180, 100, { text: '堆', score: 1 })]),
    )
    expect(narrow.has('s2')).toBe(true)
  })

  it('标签放大系数与缩放共同决定屏幕占位：缩小后放大字号，同样距离的两个标签更容易重叠', () => {
    const pair = [candidate('a', 100, 100, { score: 2 }), candidate('b', 170, 100, { score: 1 })]
    // zoom 1、k 1：字号 13，宽 ≈ 39+10，间距 70 → 不重叠
    expect(planLabels(input(pair)).size).toBe(2)
    // zoom 0.5、k 2：屏幕字号仍是 13，但节点放大系数不影响水平宽度；换成更宽的文字才会重叠
    const wideText = pair.map((c) => ({ ...c, text: '较长的知识点名称' }))
    expect(planLabels(input(wideText, { zoom: 0.5, labelK: 2 })).size).toBe(1)
  })

  it('节点放大系数把标签向下推（标签画在放大后的节点下面）', () => {
    // b 在 a 的正下方：节点不放大时标签刚好错开，节点放大后标签下移 → 与 b 的标签区域重叠
    const stack = [candidate('a', 100, 100, { score: 2 }), candidate('b', 100, 150, { score: 1 })]
    const plain = planLabels(input(stack, { nodeK: 1 }))
    const bigger = planLabels(input(stack, { nodeK: 3 }))
    expect(plain.size).toBeGreaterThanOrEqual(bigger.size)
  })

  it('空输入、缩放无效时返回空集合', () => {
    expect(planLabels(input([])).size).toBe(0)
    expect(planLabels(input([candidate('a', 10, 10)], { zoom: 0 })).size).toBe(0)
    expect(planLabels(input([candidate('a', 10, 10)], { zoom: Number.NaN })).size).toBe(0)
  })

  it('不修改输入', () => {
    const list = [candidate('b', 100, 100, { score: 1 }), candidate('a', 105, 100, { score: 2 })]
    const snapshot = JSON.stringify(list)
    planLabels(input(list))
    expect(JSON.stringify(list)).toBe(snapshot)
  })
})
