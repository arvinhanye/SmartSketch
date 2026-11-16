<script setup lang="ts">
import { computed, onMounted, onScopeDispose, ref } from 'vue'
import type { TaskActivity } from '../api/materials'
import type { TaskStatusKind } from '../composables/materials/types'
import { ACTIVITY_LABEL, formatDuration } from '../composables/materials/activity'

const props = defineProps<{
  activity: TaskActivity
  receivedAt: number
  unavailable: boolean
  status: TaskStatusKind
}>()
const now = ref(Date.now())
let timer: ReturnType<typeof setInterval> | undefined
onMounted(() => { timer = setInterval(() => { now.value = Date.now() }, 1000) })
onScopeDispose(() => { if (timer !== undefined) clearInterval(timer) })

const active = computed(() => props.status === 'processing' || props.status === 'cancelling')
const elapsedClock = computed(() => Date.parse(props.activity.observed_at) +
  (active.value && !props.unavailable ? Math.max(0, now.value - props.receivedAt) : 0))
const phaseLabel = computed(() => {
  if (props.status === 'cancelling') return ACTIVITY_LABEL.cancelling
  if (props.status !== 'processing') return ACTIVITY_LABEL[props.status]
  if (['cancelled', 'failed', 'completed', 'awaiting_review'].includes(props.activity.stage)) return ACTIVITY_LABEL.waiting
  if (props.activity.phase === 'disambiguating') return props.activity.stage === 'merging' ? '正在进行全局消歧' : '正在进行小节消歧'
  return ACTIVITY_LABEL[props.activity.phase]
})
const requests = computed(() => active.value && props.activity.worker_active ? props.activity.active_requests : [])
const globalProgress = computed(() => props.activity.global_disambiguation)
const globalPhaseLabel = computed(() => {
  if (globalProgress.value?.phase === 'complete') return '本批检查已结束'
  if (!active.value) return '进度已保存'
  return globalProgress.value?.phase === 'planning' ? '正在准备候选计划' : '本批检查进行中'
})
const PURPOSE_LABEL: Readonly<Record<string, string>> = {
  extract_entities: '知识点抽取', extract_entities_gleaning: '补充知识点',
  resolve_duplicate: '知识点消歧', judge_duplicate: '融合复核',
  extract_relations: '关系抽取', extract_normalized_relations: '关系抽取',
  repair: '输出修复', summarize_definition: '整理定义',
}
function purposeLabel(purpose: string): string {
  if (purpose === 'resolve_duplicate') return props.activity.stage === 'merging' ? '全局消歧' : '小节消歧'
  return PURPOSE_LABEL[purpose] ?? '模型处理'
}
const waiting = (started: string) => formatDuration(elapsedClock.value - Date.parse(started))
const retryWait = computed(() => props.activity.retry_at === null ? null :
  formatDuration(Math.max(0, Date.parse(props.activity.retry_at) - elapsedClock.value)))
</script>

<template>
  <div class="task-activity" data-test="task-activity">
    <p class="task-activity-phase" data-test="task-current-phase">当前：{{ phaseLabel }}</p>
    <ul class="task-activity-counts" aria-label="已完成的处理结果">
      <li>资料块 {{ activity.chunks.completed }} / {{ activity.chunks.total }}<span v-if="activity.chunks.failed">（{{ activity.chunks.failed }} 块未完成）</span></li>
      <li>关系小节 {{ activity.sections.completed }} / {{ activity.sections.total }}<span v-if="activity.sections.failed">（{{ activity.sections.failed }} 节未完成）</span></li>
      <li>小节消歧已保存 {{ activity.disambiguation.completed }} 对</li>
    </ul>
    <section v-if="globalProgress" class="global-disambiguation" data-test="global-disambiguation" aria-label="全局消歧进度">
      <p class="global-disambiguation-title"><strong>全局消歧</strong><span>{{ globalPhaseLabel }}</span></p>
      <p v-if="globalProgress.phase !== 'planning' || globalProgress.total > 0" data-test="global-completed">本批已完成 {{ globalProgress.completed }} / {{ globalProgress.total }} 对</p>
      <ul class="task-activity-counts" aria-label="全局消歧处理结果">
        <li>其中已复用 {{ globalProgress.reused }} 对</li>
        <li>{{ active ? '处理中' : '上次记录处理中' }} {{ globalProgress.inflight }} 对</li>
        <li>待处理 {{ globalProgress.pending }} 对</li>
        <li>失败 {{ globalProgress.failed }} 对</li>
        <li>技术未检查 {{ globalProgress.deferred }} 对</li>
      </ul>
      <p v-if="globalProgress.total_possible > globalProgress.total" class="task-activity-note">另有 {{ globalProgress.total_possible - globalProgress.total }} 对未纳入本批候选计划。</p>
    </section>
    <p v-else class="task-activity-note" data-test="global-progress-unavailable">全局消歧暂无已保存的进度。</p>
    <p v-for="request in requests" :key="request.purpose" class="task-activity-wait" data-test="task-request-wait">
      {{ purposeLabel(request.purpose) }}：<template v-if="unavailable">上次记录 {{ request.count }} 个请求未结束 · 当时已等待</template><template v-else>{{ request.count }} 个请求进行中 · 本次已等待</template> {{ waiting(request.started_at) }}
    </p>
    <p v-if="active && activity.phase === 'retrying' && retryWait !== null" class="task-activity-wait">
      约 {{ retryWait }}后自动重试，已完成结果会保留。
    </p>
    <p v-else-if="active && requests.length === 0 && !unavailable" class="task-activity-wait">
      <template v-if="!activity.worker_active">等待处理继续 · 已等待 {{ waiting(activity.last_activity_at) }}</template>
      <template v-else>最近一次处理进展距今 {{ waiting(activity.last_activity_at) }}</template>
    </p>
    <p v-if="status === 'cancelling'" class="task-activity-note"><template v-if="requests.length">正在等待当前请求结束，</template>完成的处理结果会保留。</p>
    <p v-if="unavailable" class="task-activity-note" role="status">详情更新暂不可用，以上为最后一次记录。</p>
  </div>
</template>

<style scoped>
.task-activity { grid-column: 1 / -1; display: grid; gap: 8px; padding: 12px 14px; border: 1px solid var(--gw-line); border-radius: 8px; background: var(--gw-hover); min-width: 0; }
.task-activity-phase { font-weight: 600; font-size: 13px; }
.task-activity-counts { display: flex; flex-wrap: wrap; gap: 6px 18px; list-style: none; margin: 0; padding: 0; font-size: 12px; }
.global-disambiguation { display: grid; gap: 6px; padding-block: 10px; border-block: 1px solid var(--gw-line); font-size: 12px; }
.global-disambiguation-title { display: flex; flex-wrap: wrap; gap: 6px 16px; }
.global-disambiguation-title span { color: var(--gw-text-3); }
.task-activity-wait, .task-activity-note { font-size: 12px; line-height: 1.6; color: var(--gw-text-3); overflow-wrap: anywhere; }
</style>
