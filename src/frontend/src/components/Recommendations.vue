<script setup lang="ts">
import type { Recommendation } from '../api/recommend'
import { PRIMARY_FACTOR_LABELS, reasonFactRows, weightedFactRows } from '../composables/useLearning'

/**
 * 下一步推荐列表（I06，ADR-075）。
 *
 * 只做展示：`reason` 是服务端生成的一整句理由，四个加权分量与 `score` 原样展示服务端数值，
 * 事实行取自 `reason_facts`——前端不自行计算分量、不把权重乘出分数（`specs/learning-path.md` §4）。
 * `state` 是契约闭集：`recommendations`（有候选）与 `all_mastered`（全部掌握的空态）；两者都不是错误。
 * `selectedId` 命中的条目高亮，与图谱上的 `recommended` 状态色对应。
 */
const props = withDefaults(
  defineProps<{
    state: 'recommendations' | 'all_mastered' | null
    items: readonly Recommendation[]
    totalEligible: number
    version?: number | null
    loading?: boolean
    error?: string | null
    selectedId?: string | null
  }>(),
  { version: null, loading: false, error: null, selectedId: null },
)

defineEmits<{ select: [kpId: string]; retry: [] }>()

function highlighted(kpId: string): string {
  return props.selectedId === kpId ? 'true' : 'false'
}
</script>

<template>
  <section class="recommendations" data-test="recommendations" aria-labelledby="rc-title">
    <h3 id="rc-title">下一步推荐</h3>
    <p v-if="version !== null" class="recommendations__version" data-test="rc-version">绑定版本 v{{ version }}</p>

    <p v-if="loading" data-test="rc-loading" role="status">正在加载推荐…</p>

    <div v-else-if="error !== null" data-test="rc-error" role="alert">
      <p>{{ error }}</p>
      <button type="button" data-test="rc-retry" @click="$emit('retry')">重试</button>
    </div>

    <p v-else-if="state === 'all_mastered'" data-test="rc-all-mastered" role="status">
      你已掌握本课程的全部知识点，暂无下一步推荐。
    </p>

    <p v-else-if="items.length === 0" data-test="rc-empty" role="status">当前没有可学的知识点。</p>

    <template v-else>
      <p class="recommendations__total" data-test="rc-total">
        共 {{ totalEligible }} 个可学知识点，显示前 {{ items.length }} 个。
      </p>
      <ol class="recommendations__list">
        <li
          v-for="item in items"
          :key="item.kp_id"
          class="recommendations__item"
          data-test="rc-item"
          :data-kp-id="item.kp_id"
          :data-primary-factor="item.reason_facts.primary_factor"
          :data-highlighted="highlighted(item.kp_id)"
        >
          <button type="button" class="recommendations__select" :data-test="`rc-select-${item.kp_id}`" @click="$emit('select', item.kp_id)">
            {{ item.name }}
          </button>
          <p class="recommendations__reason" data-test="rc-reason">{{ item.reason }}</p>
          <details class="recommendations__details">
          <summary>评分明细</summary>
          <dl class="recommendations__facts">
            <div v-for="row in reasonFactRows(item)" :key="row.key" data-test="rc-fact" :data-fact="row.key">
              <dt>{{ row.label }}</dt>
              <dd>{{ row.value }}</dd>
            </div>
            <div v-for="row in weightedFactRows(item)" :key="row.key" data-test="rc-weighted" :data-fact="row.key">
              <dt>{{ row.label }}</dt>
              <dd>{{ row.value }}</dd>
            </div>
          </dl>
          <p class="recommendations__primary">主要理由分量：{{ PRIMARY_FACTOR_LABELS[item.reason_facts.primary_factor] }}</p>
          </details>
        </li>
      </ol>
    </template>
  </section>
</template>

<style scoped>
.recommendations {
  margin: 0;
  padding: 0.85rem;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md, 8px);
  background: var(--color-surface);
}
.recommendations h3 {
  margin: 0 0 0.25rem;
}
.recommendations__version,
.recommendations__total {
  color: var(--color-text-muted);
  font-size: 0.8rem;
  margin: 0 0 0.4rem;
}
.recommendations__list {
  list-style: none;
  padding: 0;
  margin: 0;
  display: grid;
  gap: 0.5rem;
  counter-reset: rc;
}
.recommendations__item {
  counter-increment: rc;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm, 6px);
  padding: 0.5rem 0.65rem;
}
.recommendations__item:first-child {
  border-color: var(--color-primary);
  box-shadow: inset 3px 0 0 var(--color-primary);
}
.recommendations__item[data-highlighted='true'] {
  background: var(--color-primary-soft);
  outline: 2px solid var(--color-primary);
}
.recommendations__select {
  background: none;
  color: var(--color-text, inherit);
  padding: 0;
  font-weight: 600;
  text-align: left;
}
.recommendations__select::before {
  content: counter(rc) ' · ';
  color: var(--color-text-muted);
  font-weight: 500;
}
.recommendations__select:hover:not(:disabled) {
  background: none;
  color: var(--color-primary, inherit);
  text-decoration: underline;
}
.recommendations__reason {
  margin: 0.2rem 0;
  font-size: 0.85rem;
  color: var(--color-text-muted);
}
.recommendations__details summary {
  cursor: pointer;
  font-size: 0.78rem;
  color: var(--color-text-muted);
}
.recommendations__facts {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(7rem, 1fr));
  gap: 0.25rem 1rem;
  margin: 0.4rem 0;
  font-size: 0.78rem;
}
.recommendations__facts dt {
  color: var(--color-text-muted);
}
.recommendations__facts dd {
  margin: 0;
}
.recommendations__primary {
  color: var(--color-text-muted);
  font-size: 0.78rem;
  margin: 0;
}
</style>
