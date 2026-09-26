<script setup lang="ts">
import { computed, reactive, useId } from 'vue'
import {
  RELATION_TYPES,
  type RelationEditor,
} from '../composables/useRelationEditor'
import { RELATION_STYLES, type RelationType } from '../graph/adapter'

/**
 * 教师连边编辑面板（H08）：新增关系、改类型、反转方向、删除，以及成环冲突路径与错误提示。
 *
 * 只渲染 `useRelationEditor` 的状态并调用其方法；请求、乐观更新与回滚都在组合式里。
 * 页面把 `GraphCanvas` 的 `nodeClick` 接到 `editor.pickNode`、画布数据取 `editor.canvasData`，
 * 即可在图上依次点选起点和终点连边，冲突路径在画布上以冲突色显示。
 */
const props = defineProps<{ editor: RelationEditor }>()

// 组合式返回的是一组 ref；包成 reactive 让模板直接读写（v-model 写回原 ref）
const ed = computed(() => reactive(props.editor))

const uid = useId()
const ids = { from: `${uid}-from`, to: `${uid}-to`, type: `${uid}-type`, heading: `${uid}-heading` }

const typeOptions = RELATION_TYPES.map((type) => ({ value: type, label: RELATION_STYLES[type].label }))

const fromName = computed(() => ed.value.nodeOptions.find((n) => n.id === ed.value.fromId)?.name ?? null)
const pickHint = computed(() => {
  if (ed.value.fromId === null) return '在图谱上点击一个知识点作为起点，或在下方选择。'
  if (ed.value.toId === null) return `已选起点「${fromName.value}」，请点击终点。`
  return null
})

function onTypeChange(relationId: string, event: Event): void {
  void props.editor.changeType(relationId, (event.target as HTMLSelectElement).value as RelationType)
}
</script>

<template>
  <section class="relation-editor" :aria-labelledby="ids.heading" :aria-busy="ed.saving ? 'true' : 'false'">
    <h2 :id="ids.heading">关系编辑</h2>

    <p v-if="ed.status === 'loading'" role="status">图谱加载中…</p>
    <p v-else-if="ed.status === 'empty'" role="status">暂无知识点，无法编辑关系。</p>

    <template v-else>
      <p class="relation-editor__hint">{{ pickHint }}</p>

      <form class="relation-editor__form" @submit.prevent="ed.createRelation()">
        <label :for="ids.from">起点</label>
        <select :id="ids.from" v-model="ed.fromId" name="from" :disabled="ed.saving">
          <option :value="null" disabled>请选择</option>
          <option v-for="n in ed.nodeOptions" :key="n.id" :value="n.id">{{ n.name }}</option>
        </select>

        <button type="button" data-action="swap" :disabled="ed.saving" aria-label="交换起点和终点" @click="ed.swapDraft()">
          ⇅
        </button>

        <label :for="ids.to">终点</label>
        <select :id="ids.to" v-model="ed.toId" name="to" :disabled="ed.saving">
          <option :value="null" disabled>请选择</option>
          <option v-for="n in ed.nodeOptions" :key="n.id" :value="n.id">{{ n.name }}</option>
        </select>

        <label :for="ids.type">关系类型</label>
        <select :id="ids.type" v-model="ed.draftType" name="type" :disabled="ed.saving">
          <option v-for="t in typeOptions" :key="t.value" :value="t.value">{{ t.label }}</option>
        </select>

        <button type="submit" :disabled="ed.saving">添加关系</button>
      </form>

      <div v-if="ed.conflict" class="relation-editor__conflict" role="alert" data-testid="cycle-conflict">
        <p>前置关系会形成环路，改动已撤销。冲突路径：</p>
        <ol aria-label="冲突路径">
          <li v-for="(node, i) in ed.conflict.path" :key="`${i}-${node.kpId}`">{{ node.name }}</li>
        </ol>
        <button type="button" @click="ed.dismissConflict()">关闭冲突提示</button>
      </div>
      <p v-else-if="ed.error" class="relation-editor__error" role="alert" data-testid="relation-error">
        {{ ed.error }}
      </p>

      <p class="relation-editor__status" role="status" aria-live="polite">
        {{ ed.saving ? '保存中…' : (ed.notice ?? '') }}
      </p>

      <template v-if="ed.fromId !== null">
        <h3>「{{ fromName }}」的关系</h3>
        <p v-if="ed.relationRows.length === 0">该知识点暂无关系。</p>
        <ul v-else class="relation-editor__list">
          <li
            v-for="row in ed.relationRows"
            :key="row.id"
            :data-relation-id="row.id"
            :class="{ 'is-pending': row.pending, 'is-highlighted': row.highlighted }"
          >
            <span>{{ row.fromName }} → {{ row.toName }}</span>
            <span v-if="row.pending">（保存中）</span>
            <span v-if="row.highlighted">（冲突）</span>
            <span v-if="row.downgraded">（自动降级）</span>
            <label :for="`${uid}-type-${row.id}`">类型</label>
            <select
              :id="`${uid}-type-${row.id}`"
              :value="row.type"
              :disabled="ed.saving"
              @change="onTypeChange(row.id, $event)"
            >
              <option v-for="t in typeOptions" :key="t.value" :value="t.value">{{ t.label }}</option>
            </select>
            <button
              type="button"
              data-action="reverse"
              :disabled="ed.saving || !row.reversible"
              :aria-label="`反转 ${row.fromName} → ${row.toName}`"
              :title="row.reversible ? undefined : '「相关」关系无方向'"
              @click="ed.reverseRelation(row.id)"
            >
              反转
            </button>
            <button
              type="button"
              data-action="delete"
              :disabled="ed.saving"
              :aria-label="`删除 ${row.fromName} → ${row.toName}`"
              @click="ed.deleteRelation(row.id)"
            >
              删除
            </button>
          </li>
        </ul>
      </template>
    </template>
  </section>
</template>

<style scoped>
.relation-editor__form {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
}

.relation-editor__conflict,
.relation-editor__error {
  color: #a8071a;
  border: 1px solid #ff4d4f;
  padding: 8px;
}

.relation-editor__list li.is-highlighted {
  outline: 2px solid #ff4d4f;
}

.relation-editor__list li.is-pending {
  opacity: 0.7;
}
</style>
