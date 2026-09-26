import { describe, expect, it } from 'vitest'
import type { components } from '../../src/contracts/v1/generated/typescript/openapi'
import {
  edgeElementId,
  nodeElementId,
  RELATION_STYLES,
  toG6Data,
} from '../../src/frontend/src/graph/adapter'

type GraphExchange = components['schemas']['GraphExchange']
type KnowledgePoint = components['schemas']['KnowledgePoint']
type Relation = components['schemas']['Relation']
type RelationStandard = components['schemas']['RelationStandard']
type RelationType = components['schemas']['RelationType']

const CID = 'c_ds'
const ALL_TYPES: RelationType[] = ['CONTAINS', 'PREREQUISITE', 'RELATED_TO', 'EXAMPLE_OF']

function kp(id: string, overrides: Partial<KnowledgePoint> = {}): KnowledgePoint {
  return {
    id,
    course_id: CID,
    chapter_id: 'ch3',
    name: `知识点 ${id}`,
    aliases: [`别名 ${id}`],
    type: 'concept',
    definition: `定义 ${id}`,
    level: 0,
    confidence: 0.9,
    status: 'draft',
    source: 'ai',
    locked: false,
    revision: 1,
    source_refs: [{ chunk_id: 'k1', document_id: 'd1', page: 3 }],
    ...overrides,
  }
}

function rel(id: string, type: RelationType, from: string, to: string, overrides: Partial<RelationStandard> = {}): RelationStandard {
  return {
    id,
    course_id: CID,
    type,
    from_id: from,
    to_id: to,
    confidence: 0.8,
    status: 'draft',
    source: 'ai',
    source_refs: [{ chunk_id: 'k1', document_id: 'd1', section_path: '第3章 > 3.1 栈' }],
    ...overrides,
  }
}

function graph(nodes: KnowledgePoint[], edges: Relation[], overrides: Partial<GraphExchange> = {}): GraphExchange {
  return {
    format_version: '1.0',
    course_id: CID,
    graph_version: null,
    generated_at: '2026-09-26T00:00:00Z',
    chapters: [{ id: 'ch3', title: '第3章 栈与队列', order: 3 }],
    nodes,
    edges,
    ...overrides,
  }
}

function deepFreeze<T>(value: T): T {
  if (value && typeof value === 'object' && !Object.isFrozen(value)) {
    Object.freeze(value)
    for (const child of Object.values(value)) deepFreeze(child)
  }
  return value
}

/** 四类边各一条，端点齐全 */
function fourKinds(): GraphExchange {
  return graph(
    [kp('stack'), kp('push', { type: 'method', level: 1 }), kp('queue'), kp('bracket', { type: 'example' })],
    [
      rel('r_contains', 'CONTAINS', 'stack', 'push'),
      rel('r_pre', 'PREREQUISITE', 'stack', 'queue'),
      rel('r_rel', 'RELATED_TO', 'stack', 'queue'),
      rel('r_ex', 'EXAMPLE_OF', 'bracket', 'stack'),
    ],
  )
}

describe('H03 四类边样式', () => {
  it('每类关系都有样式与中文图例名，四类样式两两可区分', () => {
    expect(Object.keys(RELATION_STYLES).sort()).toEqual([...ALL_TYPES].sort())
    expect(ALL_TYPES.map((t) => RELATION_STYLES[t].label)).toEqual(['包含', '前置', '相关', '应用实例'])
    const signatures = ALL_TYPES.map((t) => {
      const s = RELATION_STYLES[t]
      return JSON.stringify([s.stroke, s.lineDash, s.directed])
    })
    expect(new Set(signatures).size).toBe(4)
    expect(new Set(ALL_TYPES.map((t) => RELATION_STYLES[t].stroke)).size).toBe(4)
  })

  it('边样式取自关系类型的样式表', () => {
    const { edges } = toG6Data(fourKinds())
    for (const edge of edges) {
      const s = RELATION_STYLES[edge.data.type]
      expect(edge.style.stroke).toBe(s.stroke)
      expect(edge.style.lineWidth).toBe(s.lineWidth)
      expect(edge.style.lineDash).toEqual(s.lineDash)
      expect(edge.style.labelText).toBe(s.label)
    }
    expect(edges.map((e) => e.data.type).sort()).toEqual([...ALL_TYPES].sort())
  })

  it('样式表不可被改写，边上的虚线数组不与样式表共享引用', () => {
    expect(Object.isFrozen(RELATION_STYLES)).toBe(true)
    for (const t of ALL_TYPES) {
      expect(Object.isFrozen(RELATION_STYLES[t])).toBe(true)
      expect(Object.isFrozen(RELATION_STYLES[t].lineDash)).toBe(true)
    }
    const { edges } = toG6Data(fourKinds())
    const related = edges.find((e) => e.data.type === 'RELATED_TO')!
    expect(related.style.lineDash).not.toBe(RELATION_STYLES.RELATED_TO.lineDash)
    related.style.lineDash.push(99)
    expect(RELATION_STYLES.RELATED_TO.lineDash).not.toContain(99)
  })
})

describe('H03 方向', () => {
  it('source/target 取 from_id/to_id；相关关系无箭头，其余三类有终点箭头', () => {
    const { edges } = toG6Data(fourKinds())
    const byType = new Map(edges.map((e) => [e.data.type, e]))
    expect(byType.get('CONTAINS')).toMatchObject({ source: nodeElementId('stack'), target: nodeElementId('push') })
    expect(byType.get('PREREQUISITE')).toMatchObject({ source: nodeElementId('stack'), target: nodeElementId('queue') })
    expect(byType.get('EXAMPLE_OF')).toMatchObject({ source: nodeElementId('bracket'), target: nodeElementId('stack') })
    expect(byType.get('RELATED_TO')).toMatchObject({ source: nodeElementId('stack'), target: nodeElementId('queue') })
    expect(byType.get('CONTAINS')!.style.endArrow).toBe(true)
    expect(byType.get('PREREQUISITE')!.style.endArrow).toBe(true)
    expect(byType.get('EXAMPLE_OF')!.style.endArrow).toBe(true)
    expect(byType.get('RELATED_TO')!.style.endArrow).toBe(false)
    for (const e of edges) expect(e.data.directed).toBe(e.data.type !== 'RELATED_TO')
  })

  it('同一对节点上的前置与相关两条边互不合并', () => {
    const { edges } = toG6Data(fourKinds())
    const between = edges.filter((e) => e.source === nodeElementId('stack') && e.target === nodeElementId('queue'))
    expect(between).toHaveLength(2)
  })

  it('成环降级边按相关关系画，保留降级标记与原端点方向', () => {
    const downgraded: Relation = {
      ...rel('r_down', 'RELATED_TO', 'queue', 'stack', { status: 'low_confidence' }),
      type: 'RELATED_TO',
      status: 'low_confidence',
      source: 'ai',
      downgraded_from_type: 'PREREQUISITE',
      downgrade_cycle: ['stack', 'queue', 'stack'],
    }
    const { edges } = toG6Data(graph([kp('stack'), kp('queue')], [downgraded]))
    expect(edges).toHaveLength(1)
    expect(edges[0]).toMatchObject({
      source: nodeElementId('queue'),
      target: nodeElementId('stack'),
      data: { type: 'RELATED_TO', downgraded: true, status: 'low_confidence' },
      style: { endArrow: false, stroke: RELATION_STYLES.RELATED_TO.stroke },
    })
    const { edges: plain } = toG6Data(fourKinds())
    for (const e of plain) expect(e.data.downgraded).toBe(false)
  })
})

describe('H03 缺端点', () => {
  it('起点或终点不在节点集时丢弃该边并逐条报告缺失的知识点 ID', () => {
    const input = graph(
      [kp('a'), kp('b')],
      [
        rel('r_ok', 'PREREQUISITE', 'a', 'b'),
        rel('r_no_from', 'PREREQUISITE', 'ghost', 'b'),
        rel('r_no_to', 'CONTAINS', 'a', 'gone'),
        rel('r_no_both', 'RELATED_TO', 'x', 'y'),
      ],
    )
    const out = toG6Data(input)
    expect(out.edges.map((e) => e.data.relationId)).toEqual(['r_ok'])
    expect(out.issues).toEqual([
      { element: 'edge', id: 'r_no_both', reason: 'missing_endpoint', missing: ['x', 'y'] },
      { element: 'edge', id: 'r_no_from', reason: 'missing_endpoint', missing: ['ghost'] },
      { element: 'edge', id: 'r_no_to', reason: 'missing_endpoint', missing: ['gone'] },
    ])
  })

  it('按章节过滤后只剩一端的边同样丢弃，节点不受影响', () => {
    const out = toG6Data(graph([kp('a')], [rel('r1', 'CONTAINS', 'a', 'b')]))
    expect(out.nodes.map((n) => n.id)).toEqual([nodeElementId('a')])
    expect(out.edges).toEqual([])
    expect(out.issues).toHaveLength(1)
  })

  it('自环两端都在时保留', () => {
    const out = toG6Data(graph([kp('a')], [rel('r_self', 'RELATED_TO', 'a', 'a')]))
    expect(out.edges).toHaveLength(1)
    expect(out.issues).toEqual([])
  })
})

describe('H03 课程隔离与重复 ID', () => {
  it('其他课程的节点与边不进入画布并报告', () => {
    const out = toG6Data(
      graph(
        [kp('a'), kp('b'), kp('alien', { course_id: 'c_other' })],
        [rel('r_ok', 'PREREQUISITE', 'a', 'b'), rel('r_alien', 'RELATED_TO', 'a', 'b', { course_id: 'c_other' })],
      ),
    )
    expect(out.nodes.map((n) => n.data.kpId)).toEqual(['a', 'b'])
    expect(out.edges.map((e) => e.data.relationId)).toEqual(['r_ok'])
    expect(out.issues).toEqual([
      { element: 'node', id: 'alien', reason: 'foreign_course' },
      { element: 'edge', id: 'r_alien', reason: 'foreign_course' },
    ])
  })

  it('指向外课节点的边按缺端点处理', () => {
    const out = toG6Data(graph([kp('a'), kp('alien', { course_id: 'c_other' })], [rel('r1', 'RELATED_TO', 'a', 'alien')]))
    expect(out.edges).toEqual([])
    expect(out.issues).toContainEqual({ element: 'edge', id: 'r1', reason: 'missing_endpoint', missing: ['alien'] })
  })

  it('重复 ID 只保留首个出现的元素并报告其余', () => {
    const out = toG6Data(
      graph(
        [kp('a', { name: '第一个' }), kp('b'), kp('a', { name: '第二个' })],
        [rel('r1', 'PREREQUISITE', 'a', 'b'), rel('r1', 'CONTAINS', 'b', 'a')],
      ),
    )
    expect(out.nodes).toHaveLength(2)
    expect(out.nodes.find((n) => n.data.kpId === 'a')!.data.name).toBe('第一个')
    expect(out.edges).toHaveLength(1)
    expect(out.edges[0].data.type).toBe('PREREQUISITE')
    expect(out.issues).toEqual([
      { element: 'node', id: 'a', reason: 'duplicate_id' },
      { element: 'edge', id: 'r1', reason: 'duplicate_id' },
    ])
  })
})

describe('H03 空图', () => {
  it('无节点无边得到空数组且无问题', () => {
    expect(toG6Data(graph([], []))).toEqual({ nodes: [], edges: [], issues: [] })
  })

  it('有节点无边时节点齐全', () => {
    const out = toG6Data(graph([kp('only')], []))
    expect(out.nodes).toHaveLength(1)
    expect(out.edges).toEqual([])
  })

  it('每次调用返回新的数组', () => {
    const input = graph([], [])
    const first = toG6Data(input)
    const second = toG6Data(input)
    expect(first.nodes).not.toBe(second.nodes)
    expect(first.edges).not.toBe(second.edges)
    expect(first.nodes).not.toBe(input.nodes)
  })
})

describe('H03 稳定 ID', () => {
  it('节点与边的元素 ID 由契约 ID 加类别前缀得到，同名 ID 不冲突', () => {
    const out = toG6Data(graph([kp('x'), kp('y')], [rel('x', 'PREREQUISITE', 'x', 'y')]))
    expect(out.nodes.map((n) => n.id)).toEqual(['kp:x', 'kp:y'])
    expect(out.edges.map((e) => e.id)).toEqual(['rel:x'])
    expect(nodeElementId('x')).toBe('kp:x')
    expect(edgeElementId('x')).toBe('rel:x')
    const ids = [...out.nodes, ...out.edges].map((e) => e.id)
    expect(new Set(ids).size).toBe(ids.length)
  })

  it('输入顺序不同，输出逐字节相同（按契约 ID 排序）', () => {
    const base = fourKinds()
    const shuffled = graph([...base.nodes].reverse(), [base.edges[2], base.edges[0], base.edges[3], base.edges[1]])
    expect(JSON.stringify(toG6Data(shuffled))).toBe(JSON.stringify(toG6Data(base)))
    expect(toG6Data(base).nodes.map((n) => n.data.kpId)).toEqual(['bracket', 'push', 'queue', 'stack'])
    expect(toG6Data(base).edges.map((e) => e.data.relationId)).toEqual(['r_contains', 'r_ex', 'r_pre', 'r_rel'])
  })

  it('排序按码点而非本地化规则', () => {
    const out = toG6Data(graph([kp('b'), kp('B'), kp('a'), kp('栈')], []))
    expect(out.nodes.map((n) => n.data.kpId)).toEqual(['B', 'a', 'b', '栈'])
  })

  it('节点数据带展示与详情所需字段', () => {
    const out = toG6Data(graph([kp('push', { type: 'method', level: 2, chapter_id: null, locked: true })], []))
    expect(out.nodes[0]).toEqual({
      id: 'kp:push',
      data: {
        kpId: 'push',
        name: '知识点 push',
        type: 'method',
        level: 2,
        chapterId: null,
        status: 'draft',
        confidence: 0.9,
        source: 'ai',
        locked: true,
      },
    })
  })

  it('缺省的 chapter_id 视为 null', () => {
    const node = kp('n')
    delete node.chapter_id
    expect(toG6Data(graph([node], [])).nodes[0].data.chapterId).toBeNull()
  })
})

describe('H03 不修改输入对象', () => {
  it('输入深度冻结时照常转换', () => {
    const input = deepFreeze(fourKinds())
    expect(() => toG6Data(input)).not.toThrow()
  })

  it('转换前后输入序列化相同，输出不引用输入的任何对象或数组', () => {
    const input = graph(
      [kp('b'), kp('a'), kp('a'), kp('z', { course_id: 'c_other' })],
      [rel('r2', 'RELATED_TO', 'a', 'b'), rel('r1', 'PREREQUISITE', 'a', 'ghost')],
    )
    const before = JSON.stringify(input)
    const out = toG6Data(input)
    expect(JSON.stringify(input)).toBe(before)

    const inputRefs = new Set<unknown>()
    const collect = (v: unknown) => {
      if (v && typeof v === 'object') {
        inputRefs.add(v)
        Object.values(v).forEach(collect)
      }
    }
    collect(input)
    const leaked: unknown[] = []
    const walk = (v: unknown) => {
      if (v && typeof v === 'object') {
        if (inputRefs.has(v)) leaked.push(v)
        Object.values(v).forEach(walk)
      }
    }
    walk(out)
    expect(leaked).toEqual([])
  })
})
