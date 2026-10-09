<script setup lang="ts">
import { ref } from 'vue'
import { RouterLink } from 'vue-router'
import { STATUS_LABELS } from '../../composables/chatSources'
import type { ChatEntry, Citation } from '../../composables/useChat'
import { STUDENT_GRAPH_ROUTE } from '../../router'
import AppIcon from '../AppIcon.vue'
import ChatMarkdown from '../ChatMarkdown.vue'

/**
 * 单条回答（UI-QA-01，规格 `specs/grounded-qa.md`「问答页前端呈现」F1–F4）：状态标签（图标 + 文字）、
 * 正文、资料未覆盖的下一步、涉及的知识点、复制与出处入口、失败原因（只写一次）与重试。
 * 只做展示：状态、出处与撤回语义由 `useChat` 决定。
 */
const props = defineProps<{
  entry: ChatEntry
  /** 右侧「出处」面板当前显示的就是这条回答 */
  active: boolean
  currentVersion?: number
  courseId: string | null
  graphLinkAvailable: boolean
  kpLabel: (id: string) => string
  copyState: { ok: boolean } | null
  sending: boolean
}>()
const emit = defineEmits<{
  citation: [citation: Citation]
  'show-sources': []
  copy: []
  retry: []
  'open-kp': [id: string]
}>()

const STATUS_ICON: Partial<Record<ChatEntry['status'], string>> = { answered: 'check', not_covered: 'info', error: 'warn', aborted: 'minus' }

// “涉及的知识点”一次可能有二十多个：默认只显示前 KP_COLLAPSED 个，其余按回答展开
const KP_COLLAPSED = 8
const expanded = ref(false)
function visibleKpIds(): readonly string[] {
  return expanded.value ? props.entry.relatedKpIds : props.entry.relatedKpIds.slice(0, KP_COLLAPSED)
}
function kpQuery(id: string): Record<string, string> {
  return props.entry.graphVersion === undefined ? { kp: id } : { kp: id, v: String(props.entry.graphVersion) }
}
</script>

<template>
  <div class="answer" :class="`answer--${entry.status}`" :data-status="entry.status" :aria-busy="entry.status === 'streaming'">
    <div class="answer__head">
      <strong class="answer__who">课程助教</strong>
      <span class="answer__status" data-test="answer-status" :data-status="entry.status">
        <AppIcon v-if="STATUS_ICON[entry.status]" :name="STATUS_ICON[entry.status]!" :size="14" />
        <span v-else class="answer__dots" aria-hidden="true"><i /><i /><i /></span>
        {{ STATUS_LABELS[entry.status] }}
      </span>
    </div>

    <!-- 未完成 / 已停止：原因只写一次，不走 Markdown -->
    <p
      v-if="entry.status === 'error' || entry.status === 'aborted'"
      class="answer__reason"
      data-test="answer-error-reason"
      :role="entry.status === 'error' ? 'alert' : 'status'"
    >{{ entry.answer }}</p>
    <ChatMarkdown v-else :text="entry.answer" :citations="entry.citations" :final="entry.status === 'answered'" @citation="emit('citation', $event)" />

    <p v-if="entry.status === 'not_covered'" class="answer__next" data-test="chat-nc-next">
      可以换个问法，或到知识图谱里浏览相关知识点。
      <RouterLink v-if="graphLinkAvailable && courseId" :to="{ name: STUDENT_GRAPH_ROUTE, params: { cid: courseId } }">在图谱中查看</RouterLink>
    </p>

    <p v-if="entry.graphVersion !== undefined && currentVersion !== undefined && entry.graphVersion !== currentVersion" class="answer__version">
      基于第 {{ entry.graphVersion }} 版
    </p>

    <p v-if="entry.relatedKpIds.length && (entry.status === 'answered' || entry.status === 'not_covered')" class="kps">
      <span class="kps__label">涉及的知识点：</span>
      <template v-for="id in visibleKpIds()" :key="id">
        <!-- L13-4：跳到本课程图谱并选中该知识点；带上回答所依据的图谱版本，图谱页据此提示版本差异 -->
        <RouterLink
          v-if="graphLinkAvailable && courseId"
          class="kps__chip"
          data-test="chat-kp"
          :to="{ name: STUDENT_GRAPH_ROUTE, params: { cid: courseId }, query: kpQuery(id) }"
        >
          {{ kpLabel(id) }}
        </RouterLink>
        <button v-else type="button" class="kps__chip" data-test="chat-kp" @click="emit('open-kp', id)">{{ kpLabel(id) }}</button>
      </template>
      <button
        v-if="entry.relatedKpIds.length > KP_COLLAPSED"
        type="button"
        class="kps__more"
        data-test="chat-kp-toggle"
        :aria-expanded="expanded"
        @click="expanded = !expanded"
      >
        {{ expanded ? '收起' : `展开全部 ${entry.relatedKpIds.length} 个` }}
      </button>
    </p>

    <div v-if="entry.status === 'answered'" class="answer__actions">
      <button type="button" class="answer__action" data-test="answer-sources-toggle" :aria-pressed="active ? 'true' : 'false'" @click="emit('show-sources')">
        查看 {{ entry.citations.length }} 处出处
      </button>
      <button type="button" class="answer__action" data-test="chat-copy" @click="emit('copy')">
        <AppIcon name="copy" :size="14" />复制回答
      </button>
      <span v-if="copyState" class="answer__copy-status" :class="{ 'is-failed': !copyState.ok }" data-test="chat-copy-status" role="status">
        {{ copyState.ok ? '已复制回答和出处。' : '复制失败，请手动选择文字复制。' }}
      </span>
    </div>
    <button v-if="entry.status === 'error' || entry.status === 'aborted'" type="button" class="answer__action" data-test="answer-retry" :disabled="sending" @click="emit('retry')">
      重试
    </button>
  </div>
</template>

<style scoped>
.answer { display: grid; gap: 10px; padding: 16px 20px; border: 1px solid var(--gw-line, #d2d5de); border-radius: 10px; background: var(--gw-panel, #f8f9fb); color: var(--gw-text, #20232a); }
.answer--not_covered { background: var(--gw-warn-bg, #fdf4e3); border-color: var(--gw-warn, #8a5a10); }
.answer--error { background: var(--gw-danger-bg, #fdecec); border-color: var(--gw-danger, #8f2323); }
.answer__head { display: flex; align-items: center; gap: 10px; }
.answer__who { font-size: 13px; font-weight: 500; color: var(--gw-text-2, #545967); }
.answer__status { display: inline-flex; align-items: center; gap: 6px; min-height: 24px; padding: 2px 8px; border-radius: 5px; font-size: 12px; line-height: 18px; font-weight: 500; color: var(--gw-text-2, #545967); background: var(--gw-hover, #eaecf1); }
.answer__status[data-status='answered'] { color: var(--gw-ok, #1f6b3a); background: var(--gw-ok-bg, #eaf6ee); }
.answer__status[data-status='not_covered'] { color: var(--gw-warn, #8a5a10); background: #fff; border: 1px solid var(--gw-warn, #8a5a10); }
.answer__status[data-status='error'] { color: var(--gw-danger, #8f2323); background: #fff; border: 1px solid var(--gw-danger, #8f2323); }
.answer__dots { display: inline-flex; gap: 3px; }
.answer__dots i { width: 5px; height: 5px; border-radius: 50%; background: currentColor; animation: answer-dot 900ms ease-in-out infinite alternate; }
.answer__dots i:nth-child(2) { animation-delay: 150ms; }
.answer__dots i:nth-child(3) { animation-delay: 300ms; }
@keyframes answer-dot { from { opacity: 0.25; } to { opacity: 1; } }
@media (prefers-reduced-motion: reduce) { .answer__dots i { animation: none; } }
.answer__reason { margin: 0; color: var(--gw-danger, #8f2323); font-size: 14px; line-height: 24px; }
.answer__next, .answer__version { margin: 0; font-size: 13px; line-height: 22px; color: var(--gw-text-2, #545967); }
.answer__next a { margin-left: 4px; }
.kps { display: flex; flex-wrap: wrap; align-items: center; gap: 6px; margin: 0; }
.kps__label { color: var(--gw-text-2, #545967); font-size: 12px; }
.kps__chip { min-height: 28px; padding: 2px 12px; border: 1px solid transparent; border-radius: 999px; background: var(--gw-selected, #e9e6fa); color: var(--gw-accent, #5145cd); font-size: 13px; font-weight: 500; text-decoration: none; cursor: pointer; }
.kps__chip:hover { border-color: var(--gw-accent, #5145cd); }
.kps__more { min-height: 28px; padding: 2px 8px; border: 0; background: transparent; color: var(--gw-accent, #5145cd); font-size: 13px; font-weight: 500; text-decoration: underline; cursor: pointer; }
.answer__actions { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; padding-top: 4px; }
.answer__action { display: inline-flex; align-items: center; gap: 6px; min-height: 32px; padding: 4px 10px; border: 1px solid var(--gw-edge, #747a87); border-radius: 6px; background: #fff; color: var(--gw-text, #20232a); font-size: 13px; cursor: pointer; }
.answer__action:hover:not(:disabled) { background: var(--gw-hover, #eaecf1); }
.answer__action[aria-pressed='true'] { background: var(--gw-selected, #e9e6fa); border-color: var(--gw-accent, #5145cd); color: var(--gw-accent, #5145cd); }
.answer__action:disabled { cursor: default; background: var(--gw-hover, #eaecf1); color: var(--gw-text-3, #626876); }
.answer__action:focus-visible, .kps__chip:focus-visible, .kps__more:focus-visible { outline: 2px solid var(--gw-accent, #5145cd); outline-offset: 2px; }
.answer__copy-status { font-size: 13px; color: var(--gw-ok, #1f6b3a); }
.answer__copy-status.is-failed { color: var(--gw-danger, #8f2323); }
</style>
