import { MASTERY_LABELS } from '../../src/frontend/src/composables/useLearning'
import { describe, expect, it } from 'vitest'
import type { G6EdgeData, G6EdgeStyle, G6NodeData } from '../../src/frontend/src/graph/adapter'
import {
  badgesFor,
  chapterOfNodes,
  decorateEdge,
  decorateNodeData,
  INITIAL_VIEW,
  masteryOfStates,
  MASTERY_TEXT,
  nodeLabel,
  type ViewState,
} from '../../src/frontend/src/graph/presentation'
import { scaleFloors } from '../../src/frontend/src/graph/scale'

const data: G6NodeData = {
  kpId: 'a', name: '线性表', type: 'concept', level: 1, chapterId: 'c1',
  status: 'approved', confidence: 1, source: 'ai', locked: false,
}
const edgeData: G6EdgeData = {
  relationId: 'r1', type: 'PREREQUISITE', directed: true, status: 'approved', confidence: 1, source: 'ai', downgraded: false,
}
const edgeStyle: G6EdgeStyle = { stroke: '#5145CD', lineWidth: 2, lineDash: [], endArrow: true, labelText: '前置' }
const zoomedOut: ViewState = { labelK: 5, floors: scaleFloors(0.2, true), labelShown: new Set(['kp:a']) }

describe('decorateNodeData', () => {
  it('把标签放大系数、节点放大系数、线宽下限与标签开关写进 data，不改原对象', () => {
    const out = decorateNodeData('kp:a', data, ['mastered'], zoomedOut)
    expect(out).toMatchObject({ k: 5, nk: zoomedOut.floors.nodeK, lw: zoomedOut.floors.lwMin, labelOn: true, mastery: 'mastered' })
    expect(data).not.toHaveProperty('k')
  })
  it('不在显示集合里的节点关闭标签；尚未排布时全部显示', () => {
    expect(decorateNodeData('kp:b', { ...data, kpId: 'b' }, [], zoomedOut).labelOn).toBe(false)
    expect(decorateNodeData('kp:b', { ...data, kpId: 'b' }, [], INITIAL_VIEW).labelOn).toBe(true)
  })
})

describe('masteryOfStates', () => {
  it('掌握状态取自 states：mastered > learning > unknown', () => {
    expect(masteryOfStates(['mastered', 'recommended'])).toBe('mastered')
    expect(masteryOfStates(['learning'])).toBe('learning')
    expect(masteryOfStates(['notStarted'])).toBe('unknown')
    expect(masteryOfStates(undefined)).toBe('unknown')
  })
})

describe('badgesFor', () => {
  it('已掌握 ✓、学习中 ◐，未学习没有角标；字号与内边距随节点放大', () => {
    expect(badgesFor('unknown', 1)).toEqual([])
    expect(badgesFor(undefined, 1)).toEqual([])
    expect(badgesFor('mastered', 1)[0]).toMatchObject({ text: '✓', fontSize: 11 })
    expect(badgesFor('learning', 2)[0]).toMatchObject({ text: '◐', fontSize: 22 })
  })
})

describe('decorateEdge', () => {
  it('关系名标签只在 active 边上显示', () => {
    expect(decorateEdge({ data: edgeData, style: edgeStyle, states: ['active'] }, false, INITIAL_VIEW).style.labelText).toBe('前置')
    expect(decorateEdge({ data: edgeData, style: edgeStyle, states: [] }, false, INITIAL_VIEW).style.labelText).toBe('')
  })
  it('跨章边未被强调时画 1px，被强调（active/scoped）时恢复关系线宽', () => {
    expect(decorateEdge({ data: edgeData, style: edgeStyle, states: [] }, true, INITIAL_VIEW).style.lineWidth).toBe(1)
    expect(decorateEdge({ data: edgeData, style: edgeStyle, states: ['active'] }, true, INITIAL_VIEW).style.lineWidth).toBe(2)
    expect(decorateEdge({ data: edgeData, style: edgeStyle, states: ['scoped'] }, true, INITIAL_VIEW).style.lineWidth).toBe(2)
    expect(decorateEdge({ data: edgeData, style: edgeStyle, states: [] }, false, INITIAL_VIEW).style.lineWidth).toBe(2)
  })
  it('缩小时线宽不低于屏幕下限，箭头系数写进 data', () => {
    const out = decorateEdge({ data: edgeData, style: edgeStyle, states: [] }, true, zoomedOut)
    expect(out.style.lineWidth).toBe(Math.max(1, zoomedOut.floors.lwMin))
    expect(out.data).toMatchObject({ lw: zoomedOut.floors.lwMin, ak: zoomedOut.floors.arrowK, cross: true, emph: false, showLabel: false })
  })
  it('不修改输入（style.lineDash 是副本）', () => {
    const out = decorateEdge({ data: edgeData, style: { ...edgeStyle, lineDash: [6, 4] }, states: [] }, false, INITIAL_VIEW)
    expect(out.style.lineDash).toEqual([6, 4])
    expect(out.style.lineDash).not.toBe(edgeStyle.lineDash)
    expect(edgeData).not.toHaveProperty('cross')
  })
})

describe('chapterOfNodes', () => {
  it('元素 id → 章节 id，缺章节为 null', () => {
    const map = chapterOfNodes([
      { id: 'kp:a', data: { chapterId: 'c1' } },
      { id: 'kp:b', data: { chapterId: null } },
    ])
    expect(map.get('kp:a')).toBe('c1')
    expect(map.get('kp:b')).toBeNull()
  })
})

describe('nodeLabel', () => {
  it('推荐项前加序号「1. 」（L14），其余为名称', () => {
    expect(nodeLabel({ name: '栈', pathOrder: 2 })).toBe('2. 栈')
    expect(nodeLabel({ name: '栈' })).toBe('栈')
  })
})

describe('MASTERY_TEXT', () => {
  it('与 useLearning 的 MASTERY_LABELS 一致（预览卡、tooltip、列表、详情用同一套文字，不会漂移）', () => {
    expect(MASTERY_TEXT).toEqual(MASTERY_LABELS)
  })
})
