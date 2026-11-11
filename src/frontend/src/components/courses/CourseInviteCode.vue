<script setup lang="ts">
import { nextTick, ref, watch } from 'vue'
const props = defineProps<{ code: string | null; loading: boolean; rotating: boolean; copying: boolean; confirming: boolean; error: string | null; notice: string | null; copyStatus: string | null }>()
const emit = defineEmits<{ load: []; copy: []; askReset: []; cancelReset: []; rotate: [] }>()
const cancelButton = ref<HTMLButtonElement | null>(null)
const resetButton = ref<HTMLButtonElement | null>(null)
watch(() => props.confirming, (open) => { void nextTick(() => (open ? cancelButton.value : resetButton.value)?.focus()) })
</script>

<template>
  <section class="course-invite" data-test="invite-code-panel" aria-labelledby="invite-code-title" :aria-busy="loading || rotating">
    <div class="course-invite__heading"><h3 id="invite-code-title">课程邀请码</h3><p>分享给学生，在课程列表输入即可加入。</p></div>
    <p v-if="loading" data-test="invite-code-loading" role="status">正在加载邀请码…</p>
    <template v-else-if="code">
      <div class="course-invite__actions">
        <strong class="course-invite__code" data-test="invite-code-value" :aria-label="`当前邀请码 ${code}`">{{ code }}</strong>
        <button type="button" class="ui-btn" data-test="invite-code-copy" :disabled="rotating || copying" @click="emit('copy')">{{ copying ? '复制中…' : '复制' }}</button>
        <button v-if="!confirming" ref="resetButton" type="button" class="ui-btn" data-test="invite-code-reset" :disabled="rotating || copying" @click="emit('askReset')">重置邀请码</button>
      </div>
      <div v-if="confirming" class="course-invite__confirm" role="group" aria-label="确认重置邀请码" @keydown.esc="emit('cancelReset')">
        <p>重置后旧码立即失效，已加入的学生不受影响。</p>
        <div class="course-invite__actions"><button type="button" class="ui-btn ui-btn--primary" data-test="invite-code-reset-confirm" :disabled="rotating" @click="emit('rotate')">{{ rotating ? '重置中…' : '确认重置' }}</button><button ref="cancelButton" type="button" class="ui-btn" data-test="invite-code-reset-cancel" :disabled="rotating" @click="emit('cancelReset')">不重置</button></div>
      </div>
    </template>
    <p v-if="copyStatus" data-test="invite-code-copy-status" role="status">{{ copyStatus }}</p>
    <p v-if="notice" class="ui-notice ui-notice--success" data-test="invite-code-status" role="status">{{ notice }}</p>
    <p v-if="error" class="ui-notice ui-notice--danger" data-test="invite-code-error" role="alert">{{ error }}</p>
    <button v-if="!loading && !code" type="button" class="ui-btn" data-test="invite-code-retry" @click="emit('load')">重试</button>
  </section>
</template>

<style scoped>
.course-invite { margin: 0 0 24px; padding: 22px 26px; border: 1px solid var(--ui-line); border-radius: 16px; background: var(--ui-surface); color: var(--ui-text); box-shadow: var(--ui-shadow); }
.course-invite__heading { display: flex; flex-wrap: wrap; align-items: baseline; gap: 8px 18px; margin-bottom: 16px; }
.course-invite h3 { margin: 0; font-size: 18px; }
.course-invite p { margin: 8px 0; }
.course-invite__heading p { margin: 0; color: var(--ui-text-2); font-size: 13px; }
.course-invite__actions { display: flex; flex-wrap: wrap; align-items: center; gap: 12px; }
.course-invite__code { margin-right: 8px; color: var(--ui-brand); font: 600 28px/1.3 ui-monospace, monospace; letter-spacing: .2em; user-select: all; }
.course-invite__confirm { margin-top: 16px; padding-top: 12px; border-top: 1px solid var(--ui-line-soft); }
.course-invite__confirm p { color: var(--ui-text-2); }
@media (max-width: 520px) { .course-invite { padding: 18px; } }
</style>
