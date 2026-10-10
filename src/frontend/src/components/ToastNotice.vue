<script setup lang="ts">
// 右下角弹窗提示：固定定位，不占文档流，出现和消失都不会把页面内容顶得上下跳动。
// 错误用 role=alert（立即朗读），成功/信息用 role=status。样式见 styles/ui.css 的 .ui-toast。
// 外面包一层不带样式的容器：页面里有 `.ui-sheet__inner > [role=status]` 这类「直接子元素」通用规则（灰底、内边距），
// 弹窗不是直接子元素就不会被它们命中。attrs（如 data-test）落在弹窗本身上。
defineOptions({ inheritAttrs: false })
defineProps<{ tone: 'success' | 'info' | 'error'; text: string }>()
defineEmits<{ dismiss: [] }>()
</script>

<template>
  <div class="ui-toast-host">
    <div v-bind="$attrs" class="ui-toast" :data-tone="tone" :role="tone === 'error' ? 'alert' : 'status'">
      <span class="ui-toast__text">{{ text }}</span>
      <button type="button" class="ui-toast__close" aria-label="关闭提示" @click="$emit('dismiss')">×</button>
    </div>
  </div>
</template>
