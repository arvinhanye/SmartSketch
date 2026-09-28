<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRoute } from 'vue-router'
import { NOTICE_UNAUTHENTICATED, ROOT_ROUTE } from '../router'

/** 登录与注册页共用品牌画面；图谱仅作产品意象，不承载真实课程数据。 */
const route = useRoute()
const noticeDismissed = ref(false)
const showLoginNotice = computed(() =>
  !noticeDismissed.value && route.name === ROOT_ROUTE && route.query.notice === NOTICE_UNAUTHENTICATED,
)

function dismissNotice(): void {
  noticeDismissed.value = true
}

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
  'M 350 204 Q 240 103 142 89', 'M 350 204 Q 463 99 566 91',
  'M 350 204 Q 228 272 116 303', 'M 350 204 Q 462 267 578 320',
  'M 350 204 Q 372 299 354 385', 'M 142 89 Q 65 113 43 183',
  'M 566 91 Q 660 123 677 194', 'M 116 303 Q 228 361 354 385',
  'M 354 385 Q 471 392 578 320',
] as const
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
          <defs>
            <radialGradient id="auth-graph-glow">
              <stop offset="0" stop-color="#6bdacb" stop-opacity=".28" />
              <stop offset="1" stop-color="#6bdacb" stop-opacity="0" />
            </radialGradient>
          </defs>
          <circle cx="350" cy="204" r="166" fill="url(#auth-graph-glow)" />
          <circle cx="350" cy="204" r="104" class="auth-layout__orbit" />
          <circle cx="350" cy="204" r="174" class="auth-layout__orbit auth-layout__orbit--outer" />
          <path v-for="edge in edges" :key="edge" :d="edge" class="auth-layout__edge" />
          <g v-for="node in nodes" :key="node.label" :class="['auth-layout__node', `auth-layout__node--${node.kind}`]">
            <circle :cx="node.x" :cy="node.y" :r="node.kind === 'core' ? 48 : node.kind === 'major' ? 35 : 29" />
            <text :x="node.x" :y="node.y + 4" text-anchor="middle">{{ node.label }}</text>
          </g>
        </svg>
        <p class="auth-layout__visual-caption">知识有脉络，学习有方向</p>
      </div>
    </section>
    <section class="auth-layout__form-area" aria-label="账号访问">
      <div v-if="showLoginNotice" class="auth-layout__notice" role="alert">
        <span>未登录：请先登录，再进入教师或学生首页。</span>
        <button type="button" aria-label="关闭提示" @click="dismissNotice">×</button>
      </div>
      <div class="auth-layout__card"><slot /></div>
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
  background: radial-gradient(circle at 84% 70%, rgb(49 146 145 / 22%), transparent 41%),
    linear-gradient(145deg, #0b2638 0%, #103747 54%, #0b3a42 100%);
  color: #d8e9ed;
}
.auth-layout__identity,
.auth-layout__story,
.auth-layout__visual { position: relative; z-index: 1; }
.auth-layout__identity { display: flex; align-items: center; gap: 0.95rem; }
.auth-layout__logo {
  display: grid;
  place-items: center;
  flex: none;
  width: 3rem;
  height: 3rem;
  border: 1px solid rgb(171 229 221 / 34%);
  border-radius: 0.9rem;
  background: rgb(175 236 222 / 9%);
}
.auth-layout__logo svg { width: 2rem; fill: none; stroke: #b6eee1; stroke-width: 1.55; stroke-linejoin: round; }
.auth-layout__identity h1 { margin: 0; color: #fff; font-size: 1.35rem; letter-spacing: 0.08em; }
.auth-layout__identity p { margin: 0.15rem 0 0; color: #a9c6cd; font-size: 0.76rem; letter-spacing: 0.02em; }
.auth-layout__story { margin-top: clamp(3rem, 9vh, 7rem); max-width: 43rem; }
.auth-layout__eyebrow { display: inline-block; margin-bottom: 1.15rem; color: #87d4c8; font-size: 0.8rem; font-weight: 600; letter-spacing: 0.12em; }
.auth-layout__headline {
  color: #f5fbfb;
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
  color: #b9d1d5;
  font-size: clamp(0.91rem, 1.1vw, 1.05rem);
  line-height: 1.9;
}
.auth-layout__visual { width: min(100%, 45rem); margin: auto auto 0; padding-top: 1.2rem; }
.auth-layout__art { display: block; width: 100%; max-height: min(42vh, 24rem); overflow: visible; }
.auth-layout__orbit { fill: none; stroke: rgb(143 214 212 / 10%); stroke-width: 1; }
.auth-layout__orbit--outer { stroke-dasharray: 4 10; }
.auth-layout__edge { fill: none; stroke: rgb(141 215 210 / 39%); stroke-width: 1.25; }
.auth-layout__node circle { fill: #164957; stroke: rgb(146 216 211 / 54%); stroke-width: 1.4; }
.auth-layout__node text { fill: #e3f3f2; font-size: 11px; font-weight: 500; }
.auth-layout__node--core circle { fill: #287a79; stroke: #9be3d5; stroke-width: 2; }
.auth-layout__node--core text { fill: #fff; font-size: 13px; font-weight: 650; }
.auth-layout__node--minor circle { fill: #123f4e; stroke: rgb(146 216 211 / 37%); }
.auth-layout__node--minor text { fill: #bcdad9; font-size: 10px; }
.auth-layout__visual-caption { margin: -0.2rem 0 0; color: #94b8bc; font-size: 0.75rem; letter-spacing: 0.12em; text-align: center; }
.auth-layout__form-area {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 2.5rem;
  min-width: 0;
  padding: 3rem clamp(1.5rem, 4vw, 4rem);
  background: radial-gradient(circle at 88% 5%, #e4f2f1, transparent 34%), #f5f9fa;
}
.auth-layout__notice {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
  width: min(100%, 27rem);
  margin-bottom: -0.75rem;
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
.auth-layout__notice button:hover:not(:disabled) { background: rgb(143 35 35 / 10%); }
.auth-layout__card {
  width: min(100%, 27rem);
  padding: clamp(1.7rem, 3vw, 2.75rem);
  border: 1px solid #e3ecee;
  border-radius: 1.25rem;
  background: rgb(255 255 255 / 95%);
  box-shadow: 0 22px 55px rgb(20 63 74 / 8%), 0 2px 8px rgb(20 63 74 / 3%);
}
.auth-layout__footnote { margin: 0; color: #829ba3; font-size: 0.77rem; letter-spacing: 0.04em; text-align: center; }
@media (max-width: 900px) {
  .auth-layout { grid-template-columns: minmax(0, 1fr); }
  .auth-layout__brand { display: none; }
  .auth-layout__form-area { min-height: 100vh; min-height: 100dvh; }
}
@media (max-height: 720px) and (min-width: 901px) {
  .auth-layout__story { margin-top: 2.5rem; }
  .auth-layout__art { max-height: 30vh; }
}
</style>
