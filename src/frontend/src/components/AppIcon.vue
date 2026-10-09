<script setup lang="ts">
/** 内联图标（24 格、1.75 描边），不引入图标库；装饰用（`aria-hidden`），可访问名称由外层按钮提供 */
defineProps<{ name: string; size?: number }>()

const PATHS: Record<string, string> = {
  home: '<path d="M3.5 11 12 4l8.5 7"/><path d="M5.5 10v9.5h4.5v-5.5h4v5.5h4.5V10"/>',
  overview: '<rect x="4" y="4" width="6.5" height="6.5" rx="1.5"/><rect x="13.5" y="4" width="6.5" height="6.5" rx="1.5"/><rect x="4" y="13.5" width="6.5" height="6.5" rx="1.5"/><rect x="13.5" y="13.5" width="6.5" height="6.5" rx="1.5"/>',
  graph: '<circle cx="6" cy="6" r="2.5"/><circle cx="18" cy="8" r="2.5"/><circle cx="9" cy="18" r="2.5"/><path d="m8 7 8 .8M7.2 8.2 8.4 15.6M16.6 10l-5.8 6.4"/>',
  chat: '<path d="M5 5.5h14v10H11l-4.5 3.5v-3.5H5z"/>',
  key: '<circle cx="8" cy="15" r="3.5"/><path d="m10.5 12.5 8-8M15 8l2.5 2.5M17.5 5.5 20 8"/>',
  menu: '<path d="M4 7h16M4 12h16M4 17h16"/>',
  map: '<path d="M4 6.5 9 4l6 2.5L20 4v13.5L15 20l-6-2.5L4 20z"/><path d="M9 4v13.5M15 6.5V20"/>',
  filter: '<path d="M4 6h16M7 12h10M10 18h4"/>',
  chapters:'<path d="M5 6h14M5 11h14M5 16h9M5 21h6"/>',
  search:'<circle cx="11" cy="11" r="6"/><path d="m20 20-4.5-4.5"/>',
  plus: '<path d="M12 5v14M5 12h14"/>',
  minus: '<path d="M5 12h14"/>',
  fit: '<path d="M4 9V4h5M20 9V4h-5M4 15v5h5M20 15v5h-5"/>',
  list: '<path d="M9 6h11M9 12h11M9 18h11"/><circle cx="4.8" cy="6" r=".6"/><circle cx="4.8" cy="12" r=".6"/><circle cx="4.8" cy="18" r=".6"/>',
  back: '<path d="m14.5 6-6 6 6 6"/>',
  chevron: '<path d="m9.5 6 6 6-6 6"/>',
  chevronDown: '<path d="m6 9.5 6 6 6-6"/>',
  close: '<path d="m6 6 12 12M18 6 6 18"/>',
  panel: '<rect x="3.5" y="4.5" width="17" height="15" rx="2"/><path d="M9.5 4.5v15"/>',
  expand: '<path d="m6 7 5 5-5 5M13 7l5 5-5 5"/>',
  collapse: '<path d="m11 7-5 5 5 5M18 7l-5 5 5 5"/>',
  check: '<path d="m5 12.5 4.5 4.5L19 7.5"/>',
  half: '<circle cx="12" cy="12" r="7.5"/><path d="M12 4.5a7.5 7.5 0 0 1 0 15z" fill="currentColor"/>',
  eyeOff: '<path d="M4 4l16 16M9.5 5.6A8.8 8.8 0 0 1 12 5.3c4.4 0 7.5 4.2 8.5 6.7a12 12 0 0 1-2.4 3.4M6.3 7.7A12.4 12.4 0 0 0 3.5 12c1 2.5 4.1 6.7 8.5 6.7 1.2 0 2.2-.3 3.2-.7"/>',
  warn: '<path d="M12 4.5 21 19.5H3z"/><path d="M12 10v4.5M12 17v.2"/>',
}
</script>

<template>
  <svg
    :width="size ?? 18"
    :height="size ?? 18"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    stroke-width="1.75"
    stroke-linecap="round"
    stroke-linejoin="round"
    aria-hidden="true"
    focusable="false"
    v-html="PATHS[name] ?? ''"
  />
</template>
