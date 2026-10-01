<script setup lang="ts">
import { computed, inject } from 'vue'
import { HTTP_CLIENT_KEY } from '../api/client'
import { COURSES_API_KEY } from '../api/courses'
import { createVersionsApi, VERSIONS_API_KEY } from '../api/versions'
import { useVersions } from '../composables/useVersions'

/** H10: 已提交版本以课程详情为准，发布/回滚响应不做乐观替换。 */
const props = defineProps<{ courseId: string }>()
const emit = defineEmits<{ forbidden: [] }>()
const coursesApi = inject(COURSES_API_KEY, null)
if (coursesApi === null) throw new Error('VersionPanel 需要注入 COURSES_API_KEY')
const client = inject(HTTP_CLIENT_KEY, null)
const api = inject(VERSIONS_API_KEY, null) ?? (client === null ? null : createVersionsApi(client))
if (api === null) throw new Error('VersionPanel 需要注入 VERSIONS_API_KEY 或 HTTP_CLIENT_KEY')
const state = useVersions({ courseId: computed(() => props.courseId), coursesApi, versionsApi: api, onCourseForbidden: () => emit('forbidden') })
</script>

<template>
  <section class="version-panel" data-test="version-panel" aria-labelledby="version-panel-title">
    <h3 id="version-panel-title">发布与版本历史</h3>
    <p v-if="state.status.value === 'loading'" data-test="vp-loading" role="status">正在加载版本历史…</p>
    <p v-if="state.status.value === 'not_teacher'" data-test="vp-not-teacher" role="status">只有本课程教师可以发布或回滚。</p>
    <p v-if="state.status.value === 'error' && !state.course.value" role="alert">{{ state.error.value }}</p>
    <template v-if="state.course.value">
      <p data-test="vp-current">
        {{ state.currentVersion.value === null ? '学生当前尚无可见的发布版本。' : `学生当前看到 v${state.currentVersion.value}。` }}
      </p>
      <p v-if="state.course.value.status === 'revising' && state.currentVersion.value !== null" data-test="vp-revising" role="status">
        草稿修订中，学生仍看到 v{{ state.currentVersion.value }}，直到新版本发布成功。
      </p>
      <p v-if="state.notice.value" data-test="vp-notice" role="status">{{ state.notice.value }}</p>
      <p v-if="state.error.value" data-test="vp-error" role="alert">{{ state.error.value }}</p>
      <p v-if="state.refreshing.value" role="status">正在核对发布状态…</p>
      <div class="version-panel__actions">
        <button type="button" data-test="vp-publish" :disabled="state.busy.value !== null || state.stale.value" @click="state.publish">
          {{ state.busy.value === 'publish' ? '正在发布…' : '发布当前草稿' }}
        </button>
        <button type="button" data-test="vp-refresh" :disabled="state.busy.value !== null || state.refreshing.value" @click="state.reload">刷新状态</button>
      </div>
      <p v-if="state.history.value.length === 0" data-test="vp-empty" role="status">尚无历史发布版本。</p>
      <ol v-else class="version-panel__history">
        <li v-for="item in state.history.value" :key="item.version" data-test="vp-version">
          <strong>v{{ item.version }}</strong>
          <span v-if="item.kind === 'rollback'"> · 回滚自 v{{ item.source_version }}</span>
          <span v-else> · 发布</span>
          <span> · {{ item.published_at }}</span>
          <span v-if="item.version === state.currentVersion.value"> · 当前学生可见</span>
          <button v-else type="button" data-test="vp-rollback" :data-version="item.version"
            :disabled="state.busy.value !== null || state.stale.value" @click="state.chooseRollback(item.version)">
            回滚到 v{{ item.version }}
          </button>
        </li>
      </ol>
      <div v-if="state.pendingRollback.value !== null" class="version-panel__confirm" data-test="vp-confirm" role="group" aria-label="确认回滚">
        <p>目标版本：v{{ state.pendingRollback.value }}。确认后会以该版本内容创建新的发布版本；草稿不会改变，学生将看到新发布版。</p>
        <button type="button" data-test="vp-confirm-rollback" :disabled="state.busy.value !== null" @click="state.rollback">确认回滚</button>
        <button type="button" data-test="vp-cancel-rollback" :disabled="state.busy.value !== null" @click="state.cancelRollback">取消</button>
      </div>
    </template>
    <button v-if="state.status.value === 'error' && !state.course.value" type="button" data-test="vp-retry" @click="state.reload">重试</button>
  </section>
</template>

<style scoped>
.version-panel { border: 1px solid var(--color-border); border-radius: 6px; padding: 0.75rem; margin: 1rem 0; }
.version-panel__actions { display: flex; gap: 0.5rem; }
.version-panel__history { padding-left: 1.5rem; }
.version-panel__history li { margin: 0.5rem 0; }
.version-panel__confirm { border: 1px solid var(--color-warning-border); border-radius: 4px; padding: 0.5rem; }
</style>
