<script setup lang="ts">
import { ref } from 'vue'
import AppIcon from './AppIcon.vue'

/**
 * 工作台左面板外壳（规格 §5、§6）：未选中显示课程说明，选中后原位切换为知识点详情。
 * 并置模式（容器宽度足够）是普通侧栏，可收起；覆盖模式是左侧抽屉。关闭时整块 `inert`（不可聚焦、读屏不读；关闭时写 `true`、打开时写 `undefined`，不写 `false`：jsdom 等没有 `inert` 属性的环境会把 `false` 渲染成字符串属性）。
 * 内容由页面通过插槽提供（页面保留全部业务与 `data-test` 钩子）；焦点管理（打开进标题、关闭回开关）也在页面。
 */
defineProps<{
  open: boolean
  /** 并置（true）或覆盖抽屉（false） */
  docked: boolean
  /** 当前是否在详情态（决定头部是「返回课程」还是标签） */
  detail: boolean
  /** 详情态的无障碍标题，例如「知识点详情：线性表」 */
  label: string
  /** 内容切换的 key，变化时触发淡入 */
  contentKey: string
}>()

const emit = defineEmits<{ close: []; back: [] }>()
const panel = ref<HTMLElement | null>(null)
defineExpose({ el: panel })
</script>

<template>
  <aside
    ref="panel"
    class="gw-panel"
    :class="{ 'is-open': open }"
    data-test="gw-panel"
    :inert="open ? undefined : true"
    :role="docked ? 'complementary' : 'dialog'"
    :aria-label="detail ? label : '课程说明'"
  >
    <div class="gw-panel__head">
      <button v-if="detail" type="button" class="gw-back" data-focus-start data-test="gw-back" @click="emit('back')">
        <AppIcon name="back" /> 返回课程
      </button>
      <span v-else class="gw-panel__tag">课程说明</span>
      <button type="button" class="gw-iconbtn" aria-label="收起说明面板" data-test="gw-panel-close" @click="emit('close')"><AppIcon name="panel" /></button>
    </div>
    <div class="gw-panel__scroll">
      <div :key="contentKey" class="gw-fade">
        <slot />
      </div>
    </div>
  </aside>
</template>
