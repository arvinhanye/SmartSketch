<script setup lang="ts">
import { KNOWLEDGE_POINT_TYPES, type useNodeCreator } from '../composables/useNodeCreator'

/**
 * 新建知识点表单（L11）：状态与请求在 `useNodeCreator`，本组件只渲染。来源取自页面当前选中的知识点
 * （ADR-035：新建必带来源）；来源片段按纯文本显示，不解析为 HTML。
 */
const props = defineProps<{ creator: ReturnType<typeof useNodeCreator>; sourceName: string | null }>()
const c = props.creator
</script>

<template>
  <section class="node-creator" data-test="tg-create" aria-labelledby="tg-create-title">
    <h3 id="tg-create-title">新建知识点</h3>
    <p v-if="sourceName" class="node-creator__from">来源依据：「{{ sourceName }}」引用的资料片段</p>
    <p v-if="c.hint.value" data-test="tg-create-hint" role="note">{{ c.hint.value }}</p>

    <form v-if="c.sources.value.length" class="node-creator__form" novalidate @submit.prevent="c.submit">
      <label for="tg-create-name">名称</label>
      <input id="tg-create-name" v-model="c.form.name" data-test="tg-create-name" type="text" maxlength="100" />

      <label for="tg-create-type">类型</label>
      <select id="tg-create-type" v-model="c.form.type" data-test="tg-create-type">
        <option v-for="item in KNOWLEDGE_POINT_TYPES" :key="item.value" :value="item.value">{{ item.label }}</option>
      </select>

      <label for="tg-create-definition">定义</label>
      <textarea id="tg-create-definition" v-model="c.form.definition" data-test="tg-create-definition" rows="3" />

      <fieldset class="node-creator__sources">
        <legend>来源（至少选一条）</legend>
        <label v-for="source in c.sources.value" :key="source.chunkId" class="node-creator__source">
          <input
            type="checkbox"
            data-test="tg-create-source"
            :checked="c.chosen.value.has(source.chunkId)"
            @change="c.toggleSource(source.chunkId)"
          />
          <span>{{ source.label }}</span>
          <q v-if="source.excerpt">{{ source.excerpt }}</q>
        </label>
      </fieldset>

      <p v-if="c.error.value" data-test="tg-create-error" role="alert">{{ c.error.value }}</p>
      <button type="submit" data-test="tg-create-submit" :disabled="c.busy.value">{{ c.busy.value ? '正在新建…' : '新建' }}</button>
    </form>
    <p v-else-if="c.error.value" data-test="tg-create-error" role="alert">{{ c.error.value }}</p>
    <p v-if="c.success.value" data-test="tg-create-success" role="status">{{ c.success.value }}</p>
  </section>
</template>

<style scoped>
.node-creator { display: grid; gap: 0.5rem; }
.node-creator h3 { margin: 0; }
.node-creator__from { color: var(--color-text-muted); margin: 0; }
.node-creator__form { display: grid; gap: 0.4rem; }
.node-creator__form input[type='text'],
.node-creator__form select,
.node-creator__form textarea {
  padding: 0.4rem;
  border: 1px solid var(--color-border-strong);
  border-radius: var(--radius-sm);
  font: inherit;
}
.node-creator__sources { display: grid; gap: 0.35rem; border: 1px solid var(--color-border); border-radius: var(--radius-sm); }
.node-creator__source { display: grid; grid-template-columns: auto 1fr; gap: 0.25rem 0.5rem; align-items: start; }
.node-creator__source q { grid-column: 2; color: var(--color-text-muted); font-size: 0.875rem; }
</style>
