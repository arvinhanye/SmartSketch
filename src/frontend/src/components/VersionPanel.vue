<script setup lang="ts">
import { computed, inject, useSlots } from 'vue'
import { HTTP_CLIENT_KEY } from '../api/client'
import { COURSES_API_KEY } from '../api/courses'
import { createVersionsApi, VERSIONS_API_KEY } from '../api/versions'
import { useVersions } from '../composables/useVersions'

/**
 * H10: 已提交版本以课程详情为准，发布/回滚响应不做乐观替换。
 *
 * 组件由上到下渲染：`review-header` 插槽（导航与标题）、紧凑发布状态栏、`review-content` 插槽（审核区）、
 * 底部默认折叠的版本历史。标题必须排在发布栏之前，因此审核页把导航与标题交给 `review-header`，
 * 审核内容交给 `review-content`：两个插槽都留在版本条件之外，版本加载中或加载失败时它们仍独立显示。
 * 版本状态只有这一份（`useVersions`），审核页不再单独挂载第二个版本面板。
 * 不传插槽时组件仍可独立用作「发布与版本历史」面板。
 */
const props = defineProps<{ courseId: string }>()
const emit = defineEmits<{ forbidden: [] }>()
const slots = useSlots()
const hasReviewContent = computed(() => slots['review-header'] !== undefined || slots['review-content'] !== undefined)
const coursesApi = inject(COURSES_API_KEY, null)
if (coursesApi === null) throw new Error('VersionPanel 需要注入 COURSES_API_KEY')
const client = inject(HTTP_CLIENT_KEY, null)
const api = inject(VERSIONS_API_KEY, null) ?? (client === null ? null : createVersionsApi(client))
if (api === null) throw new Error('VersionPanel 需要注入 VERSIONS_API_KEY 或 HTTP_CLIENT_KEY')
const state = useVersions({ courseId: computed(() => props.courseId), coursesApi, versionsApi: api, onCourseForbidden: () => emit('forbidden') })

const publishLabel = computed(() =>
  state.busy.value === 'publish' ? '正在发布…' : state.busy.value === 'rollback' ? '回滚中…' : '发布当前草稿',
)

/**
 * 发布时间格式化为中文日期时间，固定 Asia/Shanghai（与课程数据一致），并显式带出时区说明。
 * 时间戳缺失或非法时退回固定文案，绝不渲染 Invalid Date 或原始 ISO / 毫秒值。
 */
function formatPublishedAt(value: string | undefined): string {
  if (typeof value !== 'string' || value === '') return '发布时间未知'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return '发布时间未知'
  const body = new Intl.DateTimeFormat('zh-CN', {
    timeZone: 'Asia/Shanghai',
    year: 'numeric',
    month: 'long',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  }).format(date)
  return `${body} UTC+8`
}
</script>

<template>
  <section
    class="version-panel"
    :class="{ 'version-panel--with-review': hasReviewContent }"
    data-test="version-panel"
    aria-labelledby="version-panel-title"
  >
    <h2 id="version-panel-title" class="version-panel__sr">发布与版本历史</h2>

    <!-- 0. 导航与页面标题：排在发布状态栏之前，版本加载中或失败时照常显示 -->
    <slot name="review-header"></slot>

    <p v-if="state.status.value === 'loading'" data-test="vp-loading" role="status">正在加载版本历史…</p>
    <p v-else-if="state.status.value === 'not_teacher'" data-test="vp-not-teacher" role="status">只有本课程教师可以发布或回滚。</p>
    <template v-else-if="state.status.value === 'error' && !state.course.value">
      <p data-test="vp-error" role="alert">{{ state.error.value }}</p>
      <button type="button" data-test="vp-retry" @click="state.reload">重试</button>
    </template>

    <!-- 1. 紧凑发布状态栏：只显示学生当前可见版本、真实修订状态与发布/刷新操作 -->
    <div v-if="state.course.value" class="pub" role="group" aria-label="发布状态">
      <div class="pub__status">
        <p
          class="pub__current"
          data-test="vp-current"
          :role="state.course.value.status === 'revising' && state.currentVersion.value !== null ? undefined : 'status'"
        >
          <span class="pub__dot" aria-hidden="true"></span>
          {{ state.currentVersion.value === null ? '学生当前尚无可见的发布版本。' : `学生当前看到 v${state.currentVersion.value}` }}
        </p>
        <span
          v-if="state.course.value.status === 'revising' && state.currentVersion.value !== null"
          class="pub__badge"
          data-test="vp-revising"
          role="status"
        >
          草稿修订中
        </span>
        <p v-if="state.course.value.status === 'revising' && state.currentVersion.value !== null" class="pub__note">
          直到新版本发布成功，学生仍看到 v{{ state.currentVersion.value }}。
        </p>
      </div>
      <div class="pub__actions">
        <button
          type="button"
          class="pub__publish"
          data-test="vp-publish"
          :disabled="state.busy.value !== null || state.stale.value"
          @click="state.publish"
        >
          {{ publishLabel }}
        </button>
        <button
          type="button"
          class="pub__refresh"
          data-variant="secondary"
          data-test="vp-refresh"
          :disabled="state.busy.value !== null || state.refreshing.value"
          @click="state.reload"
        >
          刷新状态
        </button>
      </div>
    </div>

    <div v-if="state.course.value" class="pub__feedback">
      <p v-if="state.notice.value" data-test="vp-notice" role="status">{{ state.notice.value }}</p>
      <p v-if="state.error.value" data-test="vp-error" role="alert">{{ state.error.value }}</p>
      <p v-if="state.refreshing.value" data-test="vp-refreshing" role="status">正在核对发布状态…</p>
    </div>

    <!-- 2. 审核区：两个插槽都留在版本条件之外，版本加载失败不会连带隐藏标题与审核内容 -->
    <slot name="review-content"></slot>

    <!-- 3. 版本历史：默认折叠只影响展示，展开控件是原生 details/summary，键盘可直接操作 -->
    <section v-if="state.course.value" class="history" aria-labelledby="version-history-title">
      <details class="history__toggle">
        <summary class="history__summary">
          <span id="version-history-title" class="history__title">版本历史（{{ state.history.value.length }}）</span>
        </summary>
        <p v-if="state.history.value.length === 0" data-test="vp-empty" role="status">尚无历史发布版本。</p>
        <ol v-else class="history__list">
          <li v-for="item in state.history.value" :key="item.version" class="history__item" data-test="vp-version">
            <p class="history__head">
              <strong class="history__version">v{{ item.version }}</strong>
              <span class="history__kind">{{ item.kind === 'rollback' ? `回滚自 v${item.source_version}` : '发布' }}</span>
              <span v-if="item.version === state.currentVersion.value" class="history__current">当前学生可见</span>
            </p>
            <p class="history__time">
              <time :datetime="item.published_at">{{ formatPublishedAt(item.published_at) }}</time>
            </p>
            <p v-if="item.version !== state.currentVersion.value" class="history__actions">
              <button
                type="button"
                class="history__rollback"
                data-variant="secondary"
                data-test="vp-rollback"
                :data-version="item.version"
                :disabled="state.busy.value !== null || state.stale.value"
                @click="state.chooseRollback(item.version)"
              >
                回滚到 v{{ item.version }}
              </button>
            </p>
          </li>
        </ol>
      </details>

      <!-- 确认区留在折叠区之外：历史折叠不会静默隐藏待确认的回滚操作 -->
      <div v-if="state.pendingRollback.value !== null" class="history__confirm" data-test="vp-confirm" role="group" aria-label="确认回滚">
        <p class="history__confirm-text">
          目标版本：v{{ state.pendingRollback.value }}。确认后会以该版本内容创建新的发布版本；草稿不会改变，学生将看到新发布版。
        </p>
        <div class="history__confirm-actions">
          <button type="button" data-test="vp-confirm-rollback" :disabled="state.busy.value !== null" @click="state.rollback">确认回滚</button>
          <button type="button" data-variant="secondary" data-test="vp-cancel-rollback" :disabled="state.busy.value !== null" @click="state.cancelRollback">
            取消
          </button>
        </div>
      </div>
    </section>
  </section>
</template>

<style scoped>
/* 组件根只做纵向排布与间距；卡片外观交给下面的各段各自持有，避免最外层套一层大白卡。
 * 审核页把整页放进两个插槽，因此宽度上限放在组件根上：导航标题、发布栏、审核卡、版本历史四段左右对齐。 */
.version-panel {
  display: grid;
  gap: 1.25rem;
  width: 100%;
  max-width: 72.5rem; /* ≈1160px */
  margin-inline: auto;
  min-width: 0;
}

/* 有审核插槽时：导航标题、发布栏与审核卡贴合成一个整体，历史区再留出更大的间隔 */
.version-panel--with-review {
  gap: 0.75rem;
}

.version-panel--with-review > .history {
  margin-top: 0.5rem;
}

.version-panel__sr {
  position: absolute;
  width: 1px;
  height: 1px;
  margin: -1px;
  padding: 0;
  overflow: hidden;
  clip-path: inset(50%);
  white-space: nowrap;
  border: 0;
}

/* ---------------------------------------------------------------- 发布状态栏 */

.pub {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1rem 1.5rem;
  flex-wrap: wrap;
  min-width: 0;
  padding: 1rem 1.25rem;
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: 12px;
  box-shadow: var(--shadow-card);
}

.pub__status {
  display: flex;
  align-items: center;
  gap: 0.5rem 0.75rem;
  flex-wrap: wrap;
  min-width: 0;
}

.pub__current {
  display: inline-flex;
  align-items: center;
  gap: 0.5rem;
  margin: 0;
  font-size: 0.9375rem;
  font-weight: 600;
}

.pub__dot {
  flex: none;
  width: 0.5rem;
  height: 0.5rem;
  border-radius: 50%;
  background: var(--color-success-text);
}

.pub__badge {
  display: inline-flex;
  align-items: center;
  padding: 0.15rem 0.55rem;
  border-radius: 999px;
  background: var(--color-warning-bg);
  border: 1px solid var(--color-warning-border);
  color: var(--color-warning-text);
  font-size: 0.75rem;
  white-space: nowrap;
}

.pub__note {
  flex-basis: 100%;
  margin: 0;
  color: var(--color-text-muted);
  font-size: 0.8125rem;
}

.pub__actions {
  display: flex;
  align-items: center;
  gap: 0.6rem;
  flex-wrap: wrap;
}

.pub__actions button {
  min-height: 2.5rem; /* 40px */
  padding: 0.5rem 1.1rem;
  font-size: 0.9375rem;
}

.pub__publish {
  font-weight: 600;
}

.pub__feedback {
  display: grid;
  gap: 0.4rem;
}

.pub__feedback p {
  margin: 0;
  font-size: 0.875rem;
}

/* ---------------------------------------------------------------- 版本历史 */

.history {
  min-width: 0;
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: 12px;
  box-shadow: var(--shadow-card);
}

.history__toggle {
  min-width: 0;
}

.history__summary {
  display: flex;
  align-items: center;
  gap: 0.6rem;
  padding: 0.95rem 1.25rem;
  cursor: pointer;
  font-size: 1rem;
  color: var(--color-text);
  border-radius: 12px;
}

.history__summary::marker {
  color: var(--color-text-muted);
}

.history__summary:hover {
  color: var(--color-primary-hover);
}

.history__title {
  font-weight: 600;
}

.history__list {
  list-style: none;
  margin: 0;
  padding: 0 1.25rem 1.1rem;
}

.history__item {
  padding: 0.75rem 0;
  border-top: 1px solid var(--color-border);
}

.history__head {
  display: flex;
  align-items: center;
  gap: 0.5rem 0.75rem;
  flex-wrap: wrap;
  margin: 0;
}

.history__version {
  font-size: 0.9375rem;
}

.history__kind {
  color: var(--color-text-muted);
  font-size: 0.8125rem;
}

.history__current {
  padding: 0.1rem 0.5rem;
  border-radius: 999px;
  background: var(--color-success-bg);
  border: 1px solid var(--color-success-border);
  color: var(--color-success-text);
  font-size: 0.75rem;
}

.history__time {
  margin: 0.25rem 0 0;
  color: var(--color-text-muted);
  font-size: 0.8125rem;
}

.history__actions {
  margin: 0.5rem 0 0;
}

.history__rollback {
  padding: 0.3rem 0.7rem;
  font-size: 0.8125rem;
}

.history__confirm {
  display: grid;
  gap: 0.7rem;
  margin: 0 1.25rem 1.1rem;
  padding: 0.85rem 1rem;
  border: 1px solid var(--color-warning-border);
  border-radius: 10px;
  background: var(--color-warning-bg);
}

.history__confirm-text {
  margin: 0;
  color: var(--color-warning-text);
  font-size: 0.875rem;
}

.history__confirm-actions {
  display: flex;
  gap: 0.6rem;
  flex-wrap: wrap;
}

@media (max-width: 720px) {
  .pub {
    align-items: flex-start;
  }

  .pub__actions {
    width: 100%;
  }

  .pub__actions button {
    flex: 1 1 auto;
  }
}
</style>
