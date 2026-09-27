<script setup lang="ts">
/**
 * 登录与注册页共用的左右分栏（前端改版方向 A「工作台」，ADR-079）。
 * 左栏是产品说明与示意图谱（纯装饰，读屏跳过），右栏放表单插槽；窄屏只留右栏。
 */
const nodes = [
  { x: 150, y: 30, label: '线性表' },
  { x: 70, y: 95, label: '栈' },
  { x: 230, y: 95, label: '队列' },
  { x: 30, y: 160, label: '顺序栈' },
  { x: 110, y: 160, label: '后进先出' },
  { x: 200, y: 160, label: '循环队列' },
  { x: 275, y: 160, label: '链队列' },
]
const edges: Array<[number, number, boolean]> = [
  [0, 1, false],
  [0, 2, false],
  [1, 3, false],
  [1, 4, true],
  [2, 5, false],
  [2, 6, false],
]
</script>

<template>
  <div class="auth-layout">
    <aside class="auth-layout__brand">
      <p class="auth-layout__eyebrow">AIGC 课程知识图谱与学习导航</p>
      <p class="auth-layout__headline">把课程资料变成可审核、可导航的知识图谱</p>
      <p class="auth-layout__lede">
        教师上传讲义，系统抽取知识点与关系；审核发布后，学生按前置关系获得学习路径，提问得到带出处的回答。
      </p>
      <svg class="auth-layout__art" viewBox="0 0 310 190" aria-hidden="true" focusable="false">
        <line
          v-for="([from, to, prereq], i) in edges"
          :key="i"
          :x1="nodes[from].x"
          :y1="nodes[from].y"
          :x2="nodes[to].x"
          :y2="nodes[to].y"
          :class="prereq ? 'edge edge--prereq' : 'edge'"
        />
        <g v-for="node in nodes" :key="node.label">
          <rect :x="node.x - 30" :y="node.y - 11" width="60" height="22" rx="5" class="node" />
          <text :x="node.x" :y="node.y + 4" text-anchor="middle" class="label">{{ node.label }}</text>
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
  margin-top: auto;
  width: 100%;
  max-width: 460px;
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
  fill: rgb(255 255 255 / 6%);
  stroke: rgb(160 210 228 / 60%);
}
.label {
  fill: #cfe6ef;
  font-size: 10px;
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
