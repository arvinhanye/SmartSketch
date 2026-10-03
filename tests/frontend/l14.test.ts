import { describe, expect, it } from 'vitest'
import { buildLearningPath } from '../../src/frontend/src/graph/learningPath'

// L14（R11）：掌握标记 → 推荐更新 → 看懂学习路径。
// 路径是前端对已发布图的纯计算：只看未被拒的 PREREQUISITE 边；推荐顺序以服务端为准，前端不重排。

// 确定性 DAG：A→C、B→C、C→D、C→E、E→F，G 孤立；另有一条 RELATED_TO 与一条被拒的先修边
const NODES = ['A', 'B', 'C', 'D', 'E', 'F', 'G'].map((id) => ({ id, name: `知识点${id}` }))
const EDGES = [
  { id: 'ac', type: 'PREREQUISITE', from_id: 'A', to_id: 'C' },
  { id: 'bc', type: 'PREREQUISITE', from_id: 'B', to_id: 'C' },
  { id: 'cd', type: 'PREREQUISITE', from_id: 'C', to_id: 'D' },
  { id: 'ce', type: 'PREREQUISITE', from_id: 'C', to_id: 'E' },
  { id: 'ef', type: 'PREREQUISITE', from_id: 'E', to_id: 'F' },
  { id: 'gd', type: 'RELATED_TO', from_id: 'G', to_id: 'D' },
  { id: 'gf', type: 'PREREQUISITE', from_id: 'G', to_id: 'F', status: 'rejected' },
]

function mastery(...ids: string[]): Map<string, string> {
  return new Map(ids.map((id) => [id, 'mastered']))
}

function recs(...ids: string[]) {
  return ids.map((kp_id) => ({ kp_id }))
}

function role(path: ReturnType<typeof buildLearningPath>, id: string) {
  return path.roles.get(id) ?? 'dimmed'
}

describe('L14-1 学习路径纯函数', () => {
  it('无前置：焦点 A 是下一步；C 还需要 B，不算解锁', () => {
    const path = buildLearningPath(NODES, EDGES, mastery(), recs('A', 'B', 'G'), null)
    expect(path.focus).toBe('A')
    expect(role(path, 'A')).toBe('next')
    expect(role(path, 'C')).toBe('dimmed')
    expect(path.narrative).toEqual({ mastered: [], missing: [], next: ['知识点A'], unlocks: [] })
    expect([...path.edges]).toEqual([])
  })

  it('多前置必须全部满足：A 已掌握、焦点 B 时 C 才是解锁', () => {
    const path = buildLearningPath(NODES, EDGES, mastery('A'), recs('B', 'G'), 'B')
    expect(role(path, 'B')).toBe('next')
    expect(role(path, 'C')).toBe('unlocks')
    // A 不是 B 的前置，但它是 C 的另一个前置：已掌握的 A 加上 B 才解锁 C，所以 A 也在路径上
    expect(role(path, 'A')).toBe('mastered')
    expect([...path.edges].sort()).toEqual(['ac', 'bc'])
    expect(path.narrative).toEqual({ mastered: ['知识点A'], missing: [], next: ['知识点B'], unlocks: ['知识点C'] })
  })

  it('分支：A、B 已掌握、焦点 C 时解锁 D 与 E；F 要先学 E', () => {
    const path = buildLearningPath(NODES, EDGES, mastery('A', 'B'), recs('C', 'G'), null)
    expect(role(path, 'A')).toBe('mastered')
    expect(role(path, 'B')).toBe('mastered')
    expect(role(path, 'C')).toBe('next')
    expect(role(path, 'D')).toBe('unlocks')
    expect(role(path, 'E')).toBe('unlocks')
    expect(role(path, 'F')).toBe('dimmed')
    expect(role(path, 'G')).toBe('dimmed')
    expect([...path.edges].sort()).toEqual(['ac', 'bc', 'cd', 'ce'])
    expect(path.narrative).toEqual({
      mastered: ['知识点A', '知识点B'], missing: [], next: ['知识点C'], unlocks: ['知识点D', '知识点E'],
    })
  })

  it('全部掌握或没有推荐：没有焦点，所有节点淡化，叙述为空', () => {
    const path = buildLearningPath(NODES, EDGES, mastery('A', 'B', 'C', 'D', 'E', 'F', 'G'), [], null)
    expect(path.focus).toBe(null)
    expect(NODES.every((node) => role(path, node.id) === 'dimmed')).toBe(true)
    expect(path.narrative).toEqual({ mastered: [], missing: [], next: [], unlocks: [] })
    expect(path.edges.size).toBe(0)
    expect(path.order.size).toBe(0)
  })

  it('取消掌握后重新计算：未掌握的 A 成为缺失前置；A 未掌握时焦点 B 不再解锁 C', () => {
    const before = buildLearningPath(NODES, EDGES, mastery('A', 'B'), recs('C'), 'C')
    expect(role(before, 'D')).toBe('unlocks')
    const after = buildLearningPath(NODES, EDGES, mastery('B'), recs('C'), 'C')
    expect(role(after, 'A')).toBe('prereqMissing')
    expect(role(after, 'D')).toBe('unlocks')
    // 后继解锁只要求「已掌握 ∪ {焦点}」覆盖其全部前置；C 的前置缺失不影响 D 的判定，但叙述要说明缺口
    expect(after.narrative.missing).toEqual(['知识点A'])
    // 焦点 B、A 未掌握：C 不再解锁
    const other = buildLearningPath(NODES, EDGES, mastery(), recs('B'), 'B')
    expect(role(other, 'C')).toBe('dimmed')
  })

  it('RELATED_TO 与被拒的先修边不参与计算', () => {
    const path = buildLearningPath(NODES, EDGES, mastery('E'), recs('G'), 'G')
    // gd 是相关、gf 被拒：G 没有后继可解锁
    expect(role(path, 'D')).toBe('dimmed')
    expect(role(path, 'F')).toBe('dimmed')
    expect(path.edges.size).toBe(0)
  })

  it('推荐序号从 1 开始并保持服务端顺序；焦点不在推荐里时退回第一个推荐项', () => {
    const path = buildLearningPath(NODES, EDGES, mastery(), recs('G', 'B', 'A'), 'F')
    expect([...path.order]).toEqual([['G', 1], ['B', 2], ['A', 3]])
    expect(path.focus).toBe('G')
  })

  it('不修改输入；未知节点的掌握记录与指向未知节点的边被忽略', () => {
    const edges = [...EDGES, { id: 'cx', type: 'PREREQUISITE', from_id: 'C', to_id: 'X' }]
    const m = mastery('A', 'B', 'X')
    const snapshot = JSON.stringify({ edges, m: [...m] })
    const path = buildLearningPath(NODES, edges, m, recs('C'), null)
    expect(path.roles.has('X')).toBe(false)
    expect(path.edges.has('cx')).toBe(false)
    expect(JSON.stringify({ edges, m: [...m] })).toBe(snapshot)
  })
})
