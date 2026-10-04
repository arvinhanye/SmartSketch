<script setup lang="ts">
import { computed, inject, ref } from 'vue'
import { routeLocationKey } from 'vue-router'
import { NOTICE_UNAUTHENTICATED, ROOT_ROUTE } from '../router'

/**
 * 登录与注册页共用来源 frontend-ui-revision 的品牌画面（58/42 浅色分栏）。
 *
 * 左栏：品牌标识、产品说明与单张暖色示意图谱（纯装饰，读屏跳过）。
 * 右栏：绝对定位在卡片上方的可关闭通知 + 独立圆角表单卡 + 页脚。
 *
 * 跳转原因（未登录）由本组件在表单卡上方渲染，因此外壳不再重复渲染同一条提示；
 * 登录/注册的请求、账号角色与路由保护仍由各自的 View 与守卫负责。
 */
// 未安装路由时（单独挂载组件）route 为 null，不读取 undefined
const route = inject(routeLocationKey, null)
const noticeDismissed = ref(false)
const showLoginNotice = computed(
  () =>
    !noticeDismissed.value
    && route !== null
    && route.name === ROOT_ROUTE
    && route.query.notice === NOTICE_UNAUTHENTICATED,
)

function dismissNotice(): void {
  noticeDismissed.value = true
}

/** 示意图谱的固定节点与连线：只表达产品意象，不承载真实课程数据 */
const nodes = [
  { x: 350, y: 204, label: '课程知识', kind: 'core' },
  { x: 142, y: 89, label: '课程讲义', kind: 'major' },
  { x: 566, y: 91, label: '知识抽取', kind: 'major' },
  { x: 116, y: 303, label: '审核发布', kind: 'major' },
  { x: 578, y: 320, label: '学习路径', kind: 'major' },
  { x: 354, y: 385, label: '知识问答', kind: 'minor' },
  { x: 43, y: 183, label: '教学资料', kind: 'minor' },
  { x: 677, y: 194, label: '先修关系', kind: 'minor' },
] as const
const edges = [
  'M 350 204 Q 240 103 142 89',
  'M 350 204 Q 463 99 566 91',
  'M 350 204 Q 228 272 116 303',
  'M 350 204 Q 462 267 578 320',
  'M 350 204 Q 372 299 354 385',
  'M 142 89 Q 65 113 43 183',
  'M 566 91 Q 660 123 677 194',
  'M 116 303 Q 228 361 354 385',
  'M 354 385 Q 471 392 578 320',
] as const

function nodeRadius(kind: string): number {
  if (kind === 'core') return 48
  return kind === 'major' ? 35 : 29
}
</script>

<template>
  <div class="auth-layout">
    <section class="auth-layout__brand" aria-label="智绘学途产品介绍">
      <div class="auth-layout__identity">
        <span class="auth-layout__logo" aria-hidden="true">
          <svg viewBox="0 0 40 40" focusable="false">
            <path d="M9 13 20 7l11 6v14l-11 6-11-6Z" />
            <path d="m9 13 11 7 11-7M20 20v13M14 25l6-5 6 5" />
          </svg>
        </span>
        <div>
          <h1 data-test="auth-brand-name">智绘学途</h1>
          <p>AIGC 课程知识图谱智能构建与学习导航</p>
        </div>
      </div>

      <div class="auth-layout__story">
        <span class="auth-layout__eyebrow">从课程资料，到清晰的学习脉络</span>
        <p class="auth-layout__headline">把课程资料变成可审核、可导航的知识图谱</p>
        <p class="auth-layout__lede">
          教师上传讲义，系统抽取知识点与关系；审核发布后，学生按前置关系获得学习路径，并获得带出处的知识点问答。
        </p>
      </div>

      <div class="auth-layout__visual">
        <svg class="auth-layout__art" data-test="auth-graph" viewBox="0 0 720 425" aria-hidden="true" focusable="false">
          <circle cx="350" cy="204" r="166" class="auth-layout__glow" />
          <circle cx="350" cy="204" r="104" class="auth-layout__orbit" />
          <circle cx="350" cy="204" r="174" class="auth-layout__orbit auth-layout__orbit--outer" />
          <path v-for="edge in edges" :key="edge" :d="edge" class="auth-layout__edge" />
          <g v-for="node in nodes" :key="node.label" :class="['auth-layout__node', `auth-layout__node--${node.kind}`]">
            <circle
              :cx="node.x"
              :cy="node.y"
              :r="nodeRadius(node.kind)"
              :fill="node.kind === 'core' ? 'var(--color-primary)' : undefined"
            />
            <text :x="node.x" :y="node.y + 4" text-anchor="middle">{{ node.label }}</text>
          </g>
        </svg>
        <p class="auth-layout__visual-caption">知识有脉络，学习有方向</p>
      </div>
    </section>

    <section class="auth-layout__form-area" aria-label="账号访问">
      <div class="auth-layout__entry">
        <div v-if="showLoginNotice" class="auth-layout__notice" role="alert">
          <span>未登录：请先登录，再进入教师或学生首页。</span>
          <button type="button" aria-label="关闭提示" @click="dismissNotice">×</button>
        </div>
        <div class="auth-layout__card"><slot /></div>
      </div>
      <p class="auth-layout__footnote">智绘学途 · 让每一步学习都有迹可循</p>
    </section>
  </div>
</template>

<style scoped>
.auth-layout {
  display: grid;
  grid-template-columns: minmax(0, 58fr) minmax(390px, 42fr);
  min-height: 100vh;
  min-height: 100dvh;
}

.auth-layout__brand {
  position: relative;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  padding: clamp(2rem, 4vw, 4.5rem) clamp(2rem, 5.4vw, 6.5rem) 2rem;
  background: radial-gradient(circle at 84% 70%, var(--color-primary-soft), transparent 42%),
    var(--color-surface-muted);
  color: var(--color-text);
}

.auth-layout__identity,
.auth-layout__story,
.auth-layout__visual {
  position: relative;
  z-index: 1;
}

.auth-layout__identity {
  display: flex;
  align-items: center;
  gap: 0.95rem;
}

.auth-layout__logo {
  display: grid;
  place-items: center;
  flex: none;
  width: 3rem;
  height: 3rem;
  border: 1px solid var(--color-border-strong);
  border-radius: 0.9rem;
  background: var(--color-surface);
}

.auth-layout__logo svg {
  width: 2rem;
  fill: none;
  stroke: var(--color-primary);
  stroke-width: 1.55;
  stroke-linejoin: round;
}

.auth-layout__identity h1 {
  margin: 0;
  color: var(--color-text);
  font-size: 1.35rem;
  letter-spacing: 0.08em;
}

.auth-layout__identity p {
  margin: 0.15rem 0 0;
  color: var(--color-text-muted);
  font-size: 0.76rem;
  letter-spacing: 0.02em;
}

.auth-layout__story {
  margin-top: clamp(3rem, 9vh, 7rem);
  max-width: 43rem;
}

.auth-layout__eyebrow {
  display: inline-block;
  margin-bottom: 1.15rem;
  color: var(--color-primary);
  font-size: 0.8rem;
  font-weight: 600;
  letter-spacing: 0.12em;
}

.auth-layout__headline {
  color: var(--color-text);
  font-size: clamp(2rem, 2.7vw, 3.25rem);
  font-weight: 650;
  line-height: 1.34;
  letter-spacing: -0.025em;
  max-width: 18em;
  margin: 0;
}

.auth-layout__lede {
  max-width: 37rem;
  margin: 1.4rem 0 0;
  color: var(--color-text-muted);
  font-size: clamp(0.91rem, 1.1vw, 1.05rem);
  line-height: 1.9;
}

.auth-layout__visual {
  width: min(100%, 45rem);
  margin: auto auto 0;
  padding-top: 1.2rem;
}

.auth-layout__art {
  display: block;
  width: 100%;
  max-height: min(42vh, 24rem);
  overflow: visible;
}

.auth-layout__glow {
  fill: var(--color-primary-soft);
  opacity: 0.55;
}

.auth-layout__orbit {
  fill: none;
  stroke: var(--color-border);
  stroke-width: 1;
}

.auth-layout__orbit--outer {
  stroke-dasharray: 4 10;
}

.auth-layout__edge {
  fill: none;
  stroke: var(--color-border-strong);
  stroke-width: 1.25;
}

.auth-layout__node circle {
  fill: var(--color-surface);
  stroke: var(--color-border-strong);
  stroke-width: 1.4;
}

.auth-layout__node text {
  fill: var(--color-text);
  font-size: 11px;
  font-weight: 500;
}

/* 砖红点缀只给核心节点（fill 用属性写在模板上，这里补描边与字重）。
 * 来源的核心圆会被通用 SVG fill 规则覆盖成暖白、白色文字因此不可见；
 * 这里显式锁回主色，属来源遗留可读性纠错，不改变整体图示。 */
.auth-layout__node--core circle {
  fill: var(--color-primary);
  stroke: var(--color-primary-hover);
  stroke-width: 2;
}

.auth-layout__node--core text {
  fill: #fff;
  font-size: 13px;
  font-weight: 650;
}

.auth-layout__node--minor circle {
  stroke: var(--color-border);
}

.auth-layout__node--minor text {
  fill: var(--color-text-muted);
  font-size: 10px;
}

.auth-layout__visual-caption {
  margin: -0.2rem 0 0;
  color: var(--color-text-muted);
  font-size: 0.75rem;
  letter-spacing: 0.12em;
  text-align: center;
}

.auth-layout__form-area {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 2.5rem;
  min-width: 0;
  padding: 3rem clamp(1.5rem, 4vw, 4rem);
  background: radial-gradient(circle at 88% 5%, var(--color-primary-soft), transparent 36%), var(--color-bg);
}

.auth-layout__entry {
  position: relative;
  width: min(100%, 27rem);
}

/* 通知绝对定位在卡片上方：出现与关闭都不会把表单卡推离原位 */
.auth-layout__notice {
  position: absolute;
  bottom: calc(100% + 1.75rem);
  left: 0;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
  width: 100%;
  font-size: 0.85rem;
}

.auth-layout__notice button {
  flex: none;
  padding: 0;
  width: 1.6rem;
  height: 1.6rem;
  border: 0;
  background: transparent;
  color: inherit;
  font-size: 1.25rem;
  line-height: 1;
}

.auth-layout__notice button:hover:not(:disabled) {
  background: var(--color-danger-bg);
}

.auth-layout__card {
  width: 100%;
  padding: clamp(1.7rem, 3vw, 2.75rem);
  border: 1px solid var(--color-border);
  border-radius: 1.25rem;
  background: var(--color-surface);
  box-shadow: var(--shadow-card);
}

.auth-layout__footnote {
  margin: 0;
  color: var(--color-text-muted);
  font-size: 0.77rem;
  letter-spacing: 0.04em;
  text-align: center;
}

/* 900px 以下隐藏品牌区，只留表单栏（来源断点） */
@media (max-width: 900px) {
  .auth-layout {
    grid-template-columns: minmax(0, 1fr);
  }

  .auth-layout__brand {
    display: none;
  }

  .auth-layout__form-area {
    min-height: 100vh;
    min-height: 100dvh;
  }
}

/* 矮窗口下压缩品牌区留白与示意图高度（来源规则） */
@media (max-height: 720px) and (min-width: 901px) {
  .auth-layout__story {
    margin-top: 2.5rem;
  }

  .auth-layout__art {
    max-height: 30vh;
  }
}
</style>
