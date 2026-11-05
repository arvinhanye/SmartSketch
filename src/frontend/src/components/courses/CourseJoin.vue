<script setup lang="ts">
defineProps<{ code: string; joining: boolean; error: string | null; notice: string | null }>()
const emit = defineEmits<{ 'update:code': [value: string]; submit: [] }>()
</script>

<template>
  <form class="course-join" data-test="course-join" aria-labelledby="course-join-title" :aria-busy="joining" novalidate @submit.prevent="emit('submit')">
    <div class="course-join__heading"><h3 id="course-join-title">加入课程</h3><label for="course-join-code">六位邀请码</label></div>
    <div class="course-join__fields">
      <input id="course-join-code" :value="code" data-test="course-join-code" name="invite-code" type="text" autocomplete="off" autocapitalize="characters" :spellcheck="false" placeholder="ABC234" :disabled="joining" :aria-invalid="error !== null" :aria-describedby="error ? 'course-join-error' : undefined" @input="emit('update:code', ($event.target as HTMLInputElement).value)" />
      <button type="submit" class="ui-btn ui-btn--primary" data-test="course-join-submit" :disabled="joining">{{ joining ? '加入中…' : '加入' }}</button>
    </div>
    <p v-if="error" id="course-join-error" class="ui-notice ui-notice--danger" data-test="course-join-error" role="alert">{{ error }}</p>
    <p v-if="notice" class="ui-notice ui-notice--success" data-test="course-join-success" role="status">{{ notice }}</p>
  </form>
</template>

<style scoped>
.course-join { display: flex; flex-wrap: wrap; align-items: center; gap: 16px 24px; margin: 0 0 24px; padding: 22px 26px; border: 1px solid var(--ui-line); border-radius: 16px; background: var(--ui-surface); color: var(--ui-text); box-shadow: var(--ui-shadow); }
.course-join__heading { flex: 1 1 160px; }
.course-join h3 { margin: 0 0 4px; font-size: 18px; }
.course-join label { color: var(--ui-text-2); font-size: 13px; }
.course-join__fields { display: flex; flex-wrap: wrap; align-items: center; gap: 12px; }
.course-join input { width: 236px; max-width: 100%; min-width: 0; padding: 10px 14px; border: 1px solid var(--ui-edge); border-radius: 10px; background: var(--ui-surface-2); color: var(--ui-brand); font: 600 28px/1.3 ui-monospace, monospace; letter-spacing: .2em; text-transform: uppercase; }
.course-join input::placeholder { color: var(--ui-text-3); }
.course-join input:focus-visible { outline: 2px solid var(--ui-primary); outline-offset: 2px; }
.course-join input:disabled { opacity: .65; }
.course-join .ui-notice { flex: 1 0 100%; margin: 0; }
@media (max-width: 520px) { .course-join { padding: 18px; } .course-join__fields { width: 100%; } .course-join input { width: 100%; box-sizing: border-box; } }
</style>
