<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import type { KnowledgePointDeletion } from '../api/knowledgeDetail'
import type { DeletionStatus } from '../composables/useNodeDeletion'

/**
 * 删除知识点确认弹窗（F09 扩展，ADR-092）。
 *
 * 关键点：
 * - 打开即展示**只读预览**：会删除几个知识点、几条关系，以及哪些子节点**不会**被删（仍有别的父节点）。
 * - 两种删除方式由教师每次选择：`仅删此节点` 与 `连同会变成孤儿的后代一起删`（显示将删除的数量）。
 * - `role="alertdialog"` + `aria-modal`，打开时焦点移入，Esc 取消；删除中禁用所有按钮。
 * - 所有服务端文本以插值渲染，不用 `v-html`。
 */
const props = defineProps<{
  status: DeletionStatus
  impact: KnowledgePointDeletion | null
  error: string | null
  /** 被点名节点的名称，来自详情；预览加载中也要有标题 */
  name: string
}>()

const emit = defineEmits<{
  confirm: [cascade: boolean]
  cancel: []
}>()

const box = ref<HTMLElement | null>(null)
const pending = computed(() => props.status === 'deleting')
const loading = computed(() => props.status === 'loading')
/** 预览里真正会连带删除的后代数量（不含被点名的那个） */
const descendants = computed(() => Math.max((props.impact?.deleted_count ?? 1) - 1, 0))
const retained = computed(() => props.impact?.retained ?? [])

async function focusBox(): Promise<void> {
  await nextTick()
  box.value?.focus()
}

watch(() => props.status, (value) => {
  if (value === 'loading' || value === 'ready' || value === 'deleting') void focusBox()
}, { immediate: true })
</script>

<template>
  <div
    ref="box"
    class="node-deletion"
    data-test="nd-dialog"
    role="alertdialog"
    aria-modal="true"
    tabindex="-1"
    aria-labelledby="nd-title"
    @keydown.esc.stop.prevent="!pending && emit('cancel')"
  >
    <h3 id="nd-title" data-test="nd-title">删除知识点「{{ name }}」</h3>

    <p v-if="loading" data-test="nd-loading" role="status">正在计算删除影响…</p>

    <template v-else-if="impact">
      <p data-test="nd-summary">
        会删除 <strong data-test="nd-deleted-count">{{ impact.deleted_count }}</strong> 个知识点、
        <strong data-test="nd-relation-count">{{ impact.relation_count }}</strong> 条关系。
      </p>

      <details v-if="descendants > 0" data-test="nd-descendants" open>
        <summary>连同被删除的后代（{{ descendants }}）</summary>
        <ul data-test="nd-node-list">
          <li v-for="node in impact.nodes" :key="node.id" :data-depth="node.depth">
            {{ node.name }}<span v-if="node.depth > 0" class="node-deletion__depth">（第 {{ node.depth }} 层）</span>
          </li>
        </ul>
      </details>
      <p v-else data-test="nd-no-descendants">该知识点没有下级，只会删除它自己和相连的关系。</p>

      <section v-if="retained.length" class="node-deletion__retained" data-test="nd-retained">
        <h4>以下子节点会保留（仍属于其他上层知识点）</h4>
        <ul>
          <li v-for="node in retained" :key="node.id" :data-test="`nd-retained-${node.id}`">
            {{ node.name }}
            <span v-if="node.retained_parents?.length" class="node-deletion__why">
              ← 仍挂在 {{ node.retained_parents.join('、') }} 下
            </span>
          </li>
        </ul>
      </section>

      <p class="node-deletion__hint">
        已发布版本不受影响，学生在重新发布前仍看到旧内容。
      </p>
    </template>

    <p v-if="error" class="node-deletion__error" data-test="nd-error" role="alert">{{ error }}</p>

    <div class="node-deletion__actions">
      <button
        type="button"
        class="node-deletion__danger"
        data-test="nd-confirm-cascade"
        :disabled="pending || loading || impact === null"
        @click="emit('confirm', true)"
      >
        {{ pending ? '删除中…' : descendants > 0 ? `删除并连带 ${descendants} 个后代` : '删除' }}
      </button>
      <button
        type="button"
        data-test="nd-confirm-single"
        :disabled="pending || loading || impact === null"
        @click="emit('confirm', false)"
      >
        仅删此节点
      </button>
      <button type="button" data-test="nd-cancel" :disabled="pending" @click="emit('cancel')">取消</button>
    </div>
  </div>
</template>

<style scoped>
.node-deletion {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 12px;
  border: 1px solid var(--ss-danger-border, #f0b4b4);
  border-radius: 8px;
  background: var(--ss-danger-surface, #fff7f7);
  overflow-wrap: anywhere;
}

.node-deletion h3,
.node-deletion h4 {
  margin: 0;
  font-size: 0.95rem;
}

.node-deletion__retained {
  padding: 8px;
  border-radius: 6px;
  background: var(--ss-surface-muted, #f6f7f9);
}

.node-deletion__depth,
.node-deletion__why,
.node-deletion__hint {
  color: var(--ss-text-muted, #5b6470);
  font-size: 0.85rem;
}

.node-deletion__error {
  margin: 0;
  color: var(--ss-danger, #c62828);
}

.node-deletion__actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.node-deletion__danger {
  color: var(--ss-danger, #c62828);
}
</style>
