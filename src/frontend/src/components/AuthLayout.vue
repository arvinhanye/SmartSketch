<script setup lang="ts">
/**
 * 登录与注册页共用的左右分栏（前端改版方向 A「工作台」，ADR-079）。
 * 左栏是产品说明与示意图谱（纯装饰，读屏跳过），右栏放表单插槽；窄屏只留右栏。
 */
type GraphNode = { x: number; y: number; label: string; shape: 'circle' | 'pill'; width?: number }
type GraphArt = {
  id: string
  nodes: GraphNode[]
  edges: Array<[number, number, boolean]>
}

// 各组采用不同连接关系，位置在下方独立绘图区中随机散开。
const graphDefinitions: GraphArt[] = [
  {
    id: 'materials',
    nodes: [
      { x: 85, y: 74, label: '课程', shape: 'circle' },
      { x: 28, y: 24, label: '讲义', shape: 'circle' },
      { x: 185, y: 25, label: '章节', shape: 'pill', width: 72 },
      { x: 203, y: 113, label: '知识点', shape: 'pill', width: 84 },
      { x: 28, y: 148, label: '材料', shape: 'circle' },
    ],
    edges: [[0, 1, false], [0, 2, false], [0, 3, true], [0, 4, false]],
  },
  {
    id: 'prerequisites',
    nodes: [
      { x: 32, y: 35, label: '基础', shape: 'circle' },
      { x: 125, y: 71, label: '线性表', shape: 'pill', width: 84 },
      { x: 227, y: 22, label: '栈', shape: 'circle' },
      { x: 224, y: 118, label: '队列', shape: 'circle' },
      { x: 303, y: 72, label: '算法', shape: 'circle' },
    ],
    edges: [[0, 1, true], [1, 2, true], [1, 3, true], [2, 4, false], [3, 4, false]],
  },
  {
    id: 'questions',
    nodes: [
      { x: 25, y: 69, label: '提问', shape: 'circle' },
      { x: 111, y: 20, label: '检索', shape: 'circle' },
      { x: 113, y: 124, label: '片段', shape: 'circle' },
      { x: 198, y: 70, label: '回答', shape: 'circle' },
    ],
    edges: [[0, 1, false], [0, 2, false], [1, 3, true], [2, 3, false], [1, 2, false]],
  },
  {
    id: 'progress',
    nodes: [
      { x: 95, y: 20, label: '发布', shape: 'circle' },
      { x: 20, y: 100, label: '浏览', shape: 'circle' },
      { x: 174, y: 97, label: '掌握', shape: 'circle' },
      { x: 96, y: 175, label: '复习', shape: 'circle' },
    ],
    edges: [[0, 1, false], [0, 2, false], [1, 3, false], [2, 3, true], [3, 0, false]],
  },
  {
    id: 'learning-path',
    nodes: [
      { x: 116, y: 20, label: '学习路径', shape: 'pill', width: 96 },
      { x: 28, y: 97, label: '先修', shape: 'circle' },
      { x: 208, y: 94, label: '目标', shape: 'circle' },
      { x: 62, y: 183, label: '进度', shape: 'circle' },
      { x: 186, y: 184, label: '下一步', shape: 'pill', width: 82 },
      { x: 120, y: 105, label: '导航', shape: 'circle' },
    ],
    edges: [[0, 1, true], [0, 2, false], [1, 3, false], [2, 4, true], [3, 5, false], [4, 5, false], [0, 5, false]],
  },
  {
    id: 'concepts',
    nodes: [
      { x: 35, y: 35, label: '概念', shape: 'circle' },
      { x: 129, y: 18, label: '关联', shape: 'circle' },
      { x: 223, y: 65, label: '例子', shape: 'circle' },
      { x: 72, y: 152, label: '理解', shape: 'circle' },
      { x: 182, y: 161, label: '应用', shape: 'circle' },
    ],
    edges: [[0, 1, false], [1, 2, false], [0, 3, true], [1, 3, false], [2, 4, false], [3, 4, true], [1, 4, false]],
  },
  {
    id: 'sources',
    nodes: [
      { x: 22, y: 28, label: '文档', shape: 'circle' },
      { x: 104, y: 55, label: '片段', shape: 'circle' },
      { x: 35, y: 125, label: '页码', shape: 'circle' },
      { x: 176, y: 122, label: '来源', shape: 'circle' },
    ],
    edges: [[0, 1, false], [1, 2, false], [1, 3, true]],
  },
  {
    id: 'review',
    nodes: [
      { x: 20, y: 34, label: '抽取', shape: 'circle' },
      { x: 107, y: 18, label: '候选', shape: 'circle' },
      { x: 82, y: 118, label: '审核', shape: 'circle' },
      { x: 183, y: 90, label: '发布', shape: 'circle' },
    ],
    edges: [[0, 1, false], [1, 2, false], [2, 3, true], [1, 3, false]],
  },
]

type Bounds = { left: number; top: number; right: number; bottom: number }
type PlacedGraph = GraphArt & { x: number; y: number; scale: number }
const artWidth = 910
const artHeight = 475
const gap = 12

function nodeBounds(node: GraphNode): Bounds {
  const halfWidth = node.shape === 'circle' ? 24 : (node.width ?? 72) / 2
  const halfHeight = node.shape === 'circle' ? 24 : 17
  return {
    left: node.x - halfWidth,
    right: node.x + halfWidth,
    top: node.y - halfHeight,
    bottom: node.y + halfHeight,
  }
}

function graphBounds(nodes: GraphNode[]): Bounds {
  const bounds = nodes.map(nodeBounds)
  return {
    left: Math.min(...bounds.map((box) => box.left)),
    top: Math.min(...bounds.map((box) => box.top)),
    right: Math.max(...bounds.map((box) => box.right)),
    bottom: Math.max(...bounds.map((box) => box.bottom)),
  }
}

function overlaps(a: Bounds, b: Bounds): boolean {
  return a.left < b.right + gap && a.right + gap > b.left && a.top < b.bottom + gap && a.bottom + gap > b.top
}

function placeGraphs(): PlacedGraph[] {
  const occupiedNodes: Bounds[] = []
  const centers: Array<{ x: number; y: number }> = []
  return graphDefinitions.map((graph) => {
    const nodes = graph.nodes.map((node) => ({
      ...node,
      x: node.x + (Math.random() - 0.5) * 10,
      y: node.y + (Math.random() - 0.5) * 10,
    }))
    const bounds = graphBounds(nodes)
    // 以节点避让而非矩形分格，让不同图谱能交错散开，文字之间仍保留空隙。
    for (const scale of [0.95, 0.88, 0.8, 0.72, 0.64, 0.56, 0.48, 0.4]) {
      for (let attempt = 0; attempt < 500; attempt++) {
        const x = -bounds.left * scale + Math.random() * (artWidth - (bounds.right - bounds.left) * scale)
        const y = -bounds.top * scale + Math.random() * (artHeight - (bounds.bottom - bounds.top) * scale)
        const center = {
          x: x + ((bounds.left + bounds.right) / 2) * scale,
          y: y + ((bounds.top + bounds.bottom) / 2) * scale,
        }
        const boxes = nodes.map((node) => {
          const box = nodeBounds(node)
          return {
            left: x + box.left * scale,
            top: y + box.top * scale,
            right: x + box.right * scale,
            bottom: y + box.bottom * scale,
          }
        })
        if (
          centers.every((other) => Math.hypot(center.x - other.x, center.y - other.y) > 110) &&
          boxes.every((box) => occupiedNodes.every((existing) => !overlaps(box, existing)))
        ) {
          occupiedNodes.push(...boxes)
          centers.push(center)
          return { ...graph, nodes, x, y, scale }
        }
      }
    }
    // 极端随机序列也要保持页面可用；末组缩小后放在绘图区边缘。
    return { ...graph, nodes, x: 0, y: 0, scale: 0.4 }
  })
}

const graphs = placeGraphs()
</script>

<template>
  <div class="auth-layout">
    <aside class="auth-layout__brand">
      <p class="auth-layout__eyebrow">AIGC 课程知识图谱与学习导航</p>
      <p class="auth-layout__headline">把课程资料变成可审核、可导航的知识图谱</p>
      <p class="auth-layout__lede">
        教师上传讲义，系统抽取知识点与关系；审核发布后，学生按前置关系获得学习路径，提问得到带出处的回答。
      </p>
      <svg class="auth-layout__art" viewBox="0 0 910 475" preserveAspectRatio="xMidYMid meet" aria-hidden="true" focusable="false" draggable="false" @copy.prevent>
        <g v-for="graph in graphs" :key="`${graph.id}-edges`" :transform="`translate(${graph.x} ${graph.y}) scale(${graph.scale})`">
          <line
            v-for="([from, to, prereq], i) in graph.edges"
            :key="i"
            :x1="graph.nodes[from].x"
            :y1="graph.nodes[from].y"
            :x2="graph.nodes[to].x"
            :y2="graph.nodes[to].y"
            :class="prereq ? 'edge edge--prereq' : 'edge'"
          />
        </g>
        <g v-for="graph in graphs" :key="graph.id" data-test="auth-graph" :transform="`translate(${graph.x} ${graph.y}) scale(${graph.scale})`">
          <g v-for="node in graph.nodes" :key="node.label">
            <circle v-if="node.shape === 'circle'" :cx="node.x" :cy="node.y" r="24" class="node" />
            <rect v-else :x="node.x - (node.width ?? 72) / 2" :y="node.y - 17" :width="node.width ?? 72" height="34" rx="17" class="node" />
            <text :x="node.x" :y="node.y" text-anchor="middle" dominant-baseline="central" class="label">{{ node.label }}</text>
          </g>
        </g>
      </svg>
    </aside>
    <div class="auth-layout__form">
      <slot />
    </div>
  </div>
</template>

<style scoped>
.auth-layout {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
  min-height: calc(100vh - 3.5rem);
}
.auth-layout__brand {
  background: var(--color-brand-deep);
  color: #d7e9f0;
  padding: 3rem;
  display: flex;
  flex-direction: column;
  gap: 1rem;
}
.auth-layout__eyebrow {
  font-size: 0.8rem;
  letter-spacing: 0.08em;
  opacity: 0.8;
  margin: 0;
}
.auth-layout__headline {
  color: #fff;
  font-size: 1.75rem;
  font-weight: 700;
  line-height: 1.35;
  max-width: 16em;
  margin: 0;
}
.auth-layout__lede {
  max-width: 34em;
  margin: 0;
}
.auth-layout__art {
  flex: 1;
  min-height: 0;
  margin-top: 1.75rem;
  width: 100%;
  user-select: none;
  -webkit-user-select: none;
  pointer-events: none;
}
.edge {
  stroke: rgb(160 210 228 / 45%);
  stroke-width: 1.2;
}
.edge--prereq {
  stroke: #6fc0db;
  stroke-width: 1.8;
}
.node {
  fill: #1b4b5c;
  stroke: rgb(160 210 228 / 70%);
  stroke-width: 1.2;
}
.label {
  fill: #cfe6ef;
  font-size: 16px;
  user-select: none;
  -webkit-user-select: none;
}
.auth-layout__form {
  background: var(--color-surface);
  display: grid;
  place-items: center;
  padding: 2rem 1rem;
}
.auth-layout__form > :deep(*) {
  width: min(100%, 24rem);
}
@media (max-width: 760px) {
  .auth-layout {
    grid-template-columns: 1fr;
  }
  .auth-layout__brand {
    display: none;
  }
}
</style>
