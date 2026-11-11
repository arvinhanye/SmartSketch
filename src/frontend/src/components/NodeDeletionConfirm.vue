<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import type { KnowledgePointDeletion } from '../api/knowledgeDetail'
import type { DeletionStatus } from '../composables/useNodeDeletion'

const props = defineProps<{ status: DeletionStatus; impact: KnowledgePointDeletion | null; error: string | null; name: string }>()
const emit = defineEmits<{ confirm: [cascade: boolean]; cancel: []; retry: [] }>()
const box = ref<HTMLElement | null>(null)
const cascade = ref(false)
const ready = computed(() => props.status === 'ready' && props.impact !== null)
const pending = computed(() => props.status === 'deleting')
const previousFocus = typeof document === 'undefined' ? null : document.activeElement as HTMLElement | null
watch(() => props.impact?.preview_token, () => { cascade.value = false })
watch(() => props.status, async () => { await nextTick(); box.value?.focus() }, { immediate: true })
onBeforeUnmount(() => { if (previousFocus?.isConnected) previousFocus.focus() })
</script>

<template>
  <section ref="box" class="node-deletion" data-test="nd-dialog" role="region" tabindex="-1"
    aria-label="删除知识点确认" @keydown.esc.stop.prevent="!pending && emit('cancel')">
    <h3>删除知识点「{{ name }}」</h3>
    <p v-if="status === 'loading'" role="status">正在计算删除影响…</p>
    <template v-if="impact">
      <p>仅删除此节点会同时清理与它相连的关系。</p>
      <label>
        <input v-model="cascade" data-test="nd-cascade" type="checkbox" :disabled="!ready">
        同时删除失去全部上层归属的后代（共 {{ impact.deleted_count }} 个知识点、{{ impact.relation_count }} 条关系）
      </label>
      <details v-if="impact.deleted_count > 1">
        <summary>查看级联删除的知识点</summary>
        <ul><li v-for="node in impact.nodes" :key="node.id">{{ node.name }}（第 {{ node.depth }} 层）</li></ul>
      </details>
      <section v-if="impact.retained.length">
        <h4>这些知识点仍有其他上层归属，会保留</h4>
        <ul><li v-for="node in impact.retained" :key="node.id">{{ node.name }}：{{ node.retained_parents?.join('、') }}</li></ul>
      </section>
      <p>已发布版本不受影响，学生在重新发布前仍看到旧内容。</p>
    </template>
    <p v-if="error" role="alert">{{ error }}</p>
    <div class="node-deletion__actions">
      <button type="button" data-test="nd-confirm" :disabled="!ready" @click="emit('confirm', cascade)">
        {{ pending ? '删除中…' : cascade ? `删除这 ${impact?.deleted_count} 个知识点` : '仅删除此节点' }}
      </button>
      <button v-if="status === 'error'" type="button" @click="emit('retry')">重新预览</button>
      <button type="button" :disabled="pending" @click="emit('cancel')">取消</button>
    </div>
  </section>
</template>

<style scoped>
.node-deletion { display: grid; gap: 10px; padding: 12px; border: 1px solid var(--ss-danger-border, #f0b4b4); border-radius: 8px; background: var(--ss-danger-surface, #fff7f7); overflow-wrap: anywhere; }
.node-deletion h3, .node-deletion h4, .node-deletion p { margin: 0; }
.node-deletion__actions { display: flex; flex-wrap: wrap; gap: 8px; }
</style>
