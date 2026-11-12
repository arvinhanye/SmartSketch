<script setup lang="ts">
import { computed, useId } from 'vue'
import { RELATION_STYLES } from '../../graph/adapter'
import type { LocalGraph, PreviewNode } from '../../graph/mergePreview'
import { NODE_TYPE_FILL, NODE_TYPE_GLYPH } from '../../graph/theme'

/**
 * 合并预览的小图（UX-REVIEW-DEDUP-01）：两个（或合并后一个）知识点居中，相邻知识点分上下两排。
 * 静态 SVG，不用 G6：只有十来个节点，位置要稳定、可测试，也不需要缩放拖拽。
 * 节点沿用图谱的类型填充色与单字标记，关系沿用四类关系的线型；改接的关系加强调底色（另有文字说明，不只靠颜色）。
 */
const props = defineProps<{ graph: LocalGraph; label: string }>()

const uid = useId()
const W = 360
const H = 216
const ROW = { top: 34, mid: 108, bottom: 178 }
const PER_ROW = 4

interface Placed extends PreviewNode {
  x: number
  y: number
  r: number
  labelY: number
  short: string
}

function shorten(name: string, max: number): string {
  const chars = [...name]
  return chars.length <= max ? name : `${chars.slice(0, max - 1).join('')}…`
}

const placed = computed<Placed[]>(() => {
  const focus = props.graph.nodes.filter((n) => n.role !== 'neighbor')
  const focusIds = new Set(focus.map((n) => n.id))
  const neighbors = props.graph.nodes.filter((n) => n.role === 'neighbor')
  // 指向这两个知识点的排在上面，其余排在下面；一排放不下的挪到另一排
  const top: PreviewNode[] = []
  const bottom: PreviewNode[] = []
  for (const node of neighbors) {
    const incoming = props.graph.edges.some((e) => e.from === node.id && focusIds.has(e.to))
    const wanted = incoming ? top : bottom
    const other = incoming ? bottom : top
    ;(wanted.length < PER_ROW || other.length >= PER_ROW ? wanted : other).push(node)
  }
  const row = (nodes: PreviewNode[], y: number, r: number, labelY: number, max: number): Placed[] =>
    nodes.map((node, index) => ({ ...node, x: ((index + 0.5) * W) / nodes.length, y, r, labelY, short: shorten(node.name, max) }))
  return [
    ...row(top, ROW.top, 14, ROW.top - 22, 6),
    ...row(focus, ROW.mid, 18, ROW.mid + 31, focus.length === 1 ? 14 : 8),
    ...row(bottom, ROW.bottom, 14, ROW.bottom + 27, 6),
  ]
})

const lines = computed(() => {
  const at = new Map(placed.value.map((n) => [n.id, n]))
  return props.graph.edges.flatMap((edge) => {
    const from = at.get(edge.from)
    const to = at.get(edge.to)
    if (from === undefined || to === undefined) return []
    const dx = to.x - from.x
    const dy = to.y - from.y
    const length = Math.hypot(dx, dy) || 1
    const style = RELATION_STYLES[edge.type]
    // 线段两端收到节点边缘，箭头不被圆盖住
    const gapEnd = to.r + (style.directed ? 5 : 2)
    return [
      {
        id: edge.id,
        moved: edge.moved,
        x1: from.x + (dx / length) * (from.r + 2),
        y1: from.y + (dy / length) * (from.r + 2),
        x2: to.x - (dx / length) * gapEnd,
        y2: to.y - (dy / length) * gapEnd,
        stroke: style.stroke,
        dash: style.lineDash.length > 0 ? style.lineDash.join(' ') : undefined,
        width: style.lineWidth,
        marker: style.directed ? `url(#${uid}-arrow-${edge.type})` : undefined,
      },
    ]
  })
})

const arrowTypes = computed(() => [...new Set(props.graph.edges.map((e) => e.type))].filter((type) => RELATION_STYLES[type].directed))

const description = computed(() => {
  const names = props.graph.nodes.filter((n) => n.role !== 'neighbor').map((n) => n.name).join(' 与 ')
  const neighbors = props.graph.nodes.filter((n) => n.role === 'neighbor').length
  return `${props.label}：${names}，画出 ${neighbors} 个相邻知识点、${props.graph.edges.length} 条关系`
})
</script>

<template>
  <figure class="rv-mini" :data-test="`rv-mini`">
    <figcaption>{{ label }}</figcaption>
    <svg :viewBox="`0 0 ${W} ${H}`" role="img" :aria-label="description">
      <defs>
        <marker v-for="type in arrowTypes" :id="`${uid}-arrow-${type}`" :key="type" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
          <path d="M1 1 L9 5 L1 9 z" :fill="RELATION_STYLES[type].stroke" />
        </marker>
      </defs>
      <g>
        <template v-for="line in lines" :key="line.id">
          <line v-if="line.moved" class="rv-mini__moved" data-test="rv-mini-moved" :x1="line.x1" :y1="line.y1" :x2="line.x2" :y2="line.y2" />
          <line data-test="rv-mini-edge" :x1="line.x1" :y1="line.y1" :x2="line.x2" :y2="line.y2" :stroke="line.stroke" :stroke-width="line.width" :stroke-dasharray="line.dash" :marker-end="line.marker" />
        </template>
      </g>
      <g v-for="node in placed" :key="node.id" class="rv-mini__node" :class="`is-${node.role}`" data-test="rv-mini-node" :data-id="node.id" :data-role="node.role">
        <title>{{ node.name }}</title>
        <circle :cx="node.x" :cy="node.y" :r="node.r" :fill="NODE_TYPE_FILL[node.type]" />
        <text class="rv-mini__glyph" :x="node.x" :y="node.y" text-anchor="middle" dominant-baseline="central">{{ NODE_TYPE_GLYPH[node.type] }}</text>
        <text class="rv-mini__name" :x="node.x" :y="node.labelY" text-anchor="middle" dominant-baseline="central">{{ node.short }}</text>
      </g>
    </svg>
    <p v-if="graph.hiddenNeighbors > 0" class="rv-mini__more" data-test="rv-mini-more">另有 {{ graph.hiddenNeighbors }} 个相邻知识点未画出</p>
  </figure>
</template>
