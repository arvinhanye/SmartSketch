<script setup lang="ts">
import { computed } from 'vue'
import { RouterLink, type RouteLocationRaw } from 'vue-router'
import type { ResumeState } from '../../composables/resumeLearning'

/**
 * 「继续学习」主卡（UI-PINE-01，设计预览 v3）：课程名、下一步与短理由、掌握进度环。
 * 主按钮直达图谱并打开推荐的知识点（`?kp=&v=`，与问答里的知识点链接同一机制）。
 */
const props = defineProps<{ resume: ResumeState; graphRoute: string; chatRoute: string | null }>()

const RADIUS = 78
const CIRCUMFERENCE = 2 * Math.PI * RADIUS

const goTo = computed<RouteLocationRaw>(() => {
  const { course, next, graphVersion } = props.resume
  return {
    name: props.graphRoute,
    params: { cid: course.id },
    ...(next === null ? {} : { query: { kp: next.kpId, v: String(graphVersion) } }),
  }
})
const chatTo = computed<RouteLocationRaw | null>(() => (props.chatRoute === null ? null : { name: props.chatRoute, params: { cid: props.resume.course.id } }))
const ring = computed(() => {
  const { mastered, learning, total } = props.resume.summary
  const share = (n: number) => (total === 0 ? 0 : (CIRCUMFERENCE * n) / total)
  return { mastered: share(mastered), learning: share(learning) }
})
const progressLabel = computed(() => {
  const { mastered, learning, total } = props.resume.summary
  return `${total} 个知识点中已掌握 ${mastered} 个，学习中 ${learning} 个`
})
</script>

<template>
  <section class="resume" data-test="resume-card" aria-labelledby="resume-title">
    <svg class="resume__decor" viewBox="0 0 400 260" aria-hidden="true" focusable="false">
      <circle cx="390" cy="0" r="120" fill="#127d6b" />
      <circle cx="390" cy="0" r="80" fill="none" stroke="#5fc3a8" stroke-width="2" opacity=".5" />
      <path d="M260 260 360 160" stroke="#f5b82e" stroke-width="10" stroke-linecap="round" opacity=".9" />
      <path d="M310 260 400 170" stroke="#0f3d36" stroke-width="5" stroke-linecap="round" />
    </svg>
    <div class="resume__main">
      <p class="resume__label">{{ resume.hasActivity ? '继续学习' : '开始学习' }}</p>
      <h3 id="resume-title" class="resume__title">{{ resume.course.name }}</h3>
      <div class="resume__next">
        <span v-if="resume.next" class="resume__tag">下一步</span>
        <span v-if="resume.next" class="resume__name">{{ resume.next.name }}</span>
        <span class="resume__reason">{{ resume.reason }}</span>
      </div>
      <div class="resume__actions">
        <RouterLink :to="goTo" class="resume__go" data-test="resume-go">{{ resume.hasActivity ? '继续学习' : '开始学习' }}</RouterLink>
        <RouterLink v-if="chatTo" :to="chatTo" class="resume__chat">课程问答</RouterLink>
      </div>
    </div>
    <svg class="resume__ring" width="168" height="168" viewBox="0 0 200 200" role="img" :aria-label="progressLabel" data-test="resume-progress">
      <circle cx="100" cy="100" :r="RADIUS" fill="none" stroke="rgb(255 255 255 / 18%)" stroke-width="14" />
      <circle cx="100" cy="100" :r="RADIUS" fill="none" stroke="#fff" stroke-width="14" stroke-linecap="round" :stroke-dasharray="`${ring.mastered} ${CIRCUMFERENCE}`" transform="rotate(-90 100 100)" />
      <circle cx="100" cy="100" :r="RADIUS" fill="none" stroke="#f5b82e" stroke-width="14" :stroke-dasharray="`${ring.learning} ${CIRCUMFERENCE}`" :stroke-dashoffset="-ring.mastered" transform="rotate(-90 100 100)" />
      <text x="100" y="104" text-anchor="middle" class="resume__count">{{ resume.summary.mastered }}<tspan class="resume__total">/{{ resume.summary.total }}</tspan></text>
      <text x="100" y="128" text-anchor="middle" class="resume__caption">已掌握</text>
    </svg>
  </section>
</template>

<style scoped>
.resume {
  position: relative;
  overflow: hidden;
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 24px 32px;
  margin: 0 0 28px;
  padding: 26px 28px;
  border-radius: 18px;
  background: var(--ui-primary);
  color: #fff;
  box-shadow: 0 14px 34px rgb(14 107 92 / 25%);
}
.resume__decor {
  position: absolute;
  right: 0;
  top: 0;
  width: 400px;
  height: 260px;
  pointer-events: none;
}
.resume__main {
  position: relative;
  flex: 1 1 320px;
  min-width: 0;
  display: grid;
  gap: 12px;
}
.resume__label {
  margin: 0;
  font-size: 13px;
  color: #d8efe8;
}
.resume .resume__title {
  margin: 0;
  color: #fff;
  font-size: 24px;
  line-height: 32px;
  font-weight: 500;
  overflow-wrap: anywhere;
}
.resume__next {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px 10px;
  padding: 12px 14px;
  border: 1px solid rgb(255 255 255 / 18%);
  border-radius: 12px;
  background: rgb(255 255 255 / 12%);
}
.resume__tag {
  padding: 1px 8px;
  border-radius: 6px;
  background: var(--ui-highlight);
  color: var(--ui-text);
  font-size: 12px;
  line-height: 20px;
}
.resume__name {
  font-size: 16px;
  font-weight: 500;
  overflow-wrap: anywhere;
}
.resume__reason {
  margin-left: auto;
  font-size: 12px;
  color: #d8efe8;
}
.resume__actions {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}
.resume .resume__go,
.resume .resume__chat {
  display: inline-flex;
  align-items: center;
  min-height: 44px;
  padding: 0 20px;
  border-radius: 12px;
  font-size: 15px;
  text-decoration: none;
}
.resume .resume__go {
  background: var(--ui-highlight);
  color: var(--ui-text);
  font-weight: 500;
}
.resume .resume__go:hover {
  background: #f8c552;
  color: var(--ui-text);
  text-decoration: none;
}
.resume .resume__chat {
  border: 1px solid rgb(255 255 255 / 45%);
  color: #fff;
}
.resume .resume__chat:hover {
  background: rgb(255 255 255 / 10%);
  color: #fff;
  text-decoration: none;
}
.resume :is(a):focus-visible {
  outline: 2px solid var(--ui-highlight);
  outline-offset: 3px;
}
.resume__ring {
  position: relative;
  flex: none;
}
.resume__count {
  fill: #fff;
  font-size: 40px;
  font-weight: 500;
}
.resume__total {
  fill: #d8efe8;
  font-size: 18px;
}
.resume__caption {
  fill: #d8efe8;
  font-size: 13px;
}
@media (max-width: 767px) {
  .resume { padding: 20px; }
  .resume__reason { margin-left: 0; }
}
</style>
