<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { documentLabel, EXCERPT_FOLD_CHARS, locationLabel } from '../composables/sourceLabel'

/**
 * 来源查看器（L12，R04）：资料文件名、页码或章节、原文片段。片段与文件名都按纯文本插值渲染（不可信内容，
 * 不用 v-html）；超长片段先折叠。只显示服务端随来源返回的片段，不为展示出处读取整份资料。
 */
const props = defineProps<{
  source: { documentName?: string; page?: number; sectionPath?: string; excerpt?: string }
}>()
defineEmits<{ close: [] }>()

const expanded = ref(false)
// A parent may recreate an equal source object; reset only when its display identity changes.
watch([
  () => props.source.documentName,
  () => props.source.page,
  () => props.source.sectionPath,
  () => props.source.excerpt,
], () => { expanded.value = false })
const excerpt = computed(() => props.source.excerpt ?? '')
const folded = computed(() => !expanded.value && excerpt.value.length > EXCERPT_FOLD_CHARS)
const shown = computed(() => (folded.value ? `${excerpt.value.slice(0, EXCERPT_FOLD_CHARS)}…` : excerpt.value))
</script>

<template>
  <section class="source-viewer" data-test="source-viewer" aria-label="来源原文">
    <header class="source-viewer__head">
      <strong data-test="sv-document">{{ documentLabel(source.documentName) }}</strong>
      <span data-test="sv-location">{{ locationLabel(source) }}</span>
      <button type="button" class="source-viewer__close" data-test="sv-close" aria-label="收起来源" @click="$emit('close')">×</button>
    </header>
    <template v-if="excerpt">
      <blockquote data-test="sv-excerpt">{{ shown }}</blockquote>
      <button v-if="folded" type="button" data-test="sv-expand" @click="expanded = true">展开全文</button>
    </template>
    <p v-else data-test="sv-no-excerpt" class="source-viewer__empty">该来源没有可显示的原文片段（已发布版本只保留定位）。</p>
  </section>
</template>

<style scoped>
.source-viewer {
  display: grid;
  gap: 0.4rem;
  padding: 0.6rem 0.75rem;
  border: 1px solid var(--color-border, #d9d9d9);
  border-radius: var(--radius-sm, 6px);
  background: var(--color-surface-muted, #fafafa);
}
.source-viewer__head { display: flex; flex-wrap: wrap; gap: 0.25rem 0.75rem; align-items: baseline; }
.source-viewer__close { margin-left: auto; }
.source-viewer blockquote { margin: 0; white-space: pre-wrap; overflow-wrap: anywhere; }
.source-viewer__empty { margin: 0; color: var(--color-text-muted); }
</style>
