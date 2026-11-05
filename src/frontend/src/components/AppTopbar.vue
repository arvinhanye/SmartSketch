<script setup lang="ts">
import { RouterLink, type RouteLocationRaw } from 'vue-router'
import AppIcon from './AppIcon.vue'

/**
 * 深色外壳顶栏（规格 §5.1）：面包屑、运行模式标签、用户与退出。窄屏（<1024）多一个打开导航抽屉的按钮。
 * 面包屑最后一项是当前页（`aria-current="page"`），不是链接。品牌标志只在登录封面出现，顶栏不放。
 */
export interface Crumb {
  label: string
  to?: RouteLocationRaw
}

withDefaults(defineProps<{ crumbs: readonly Crumb[]; user: string; showMenu: boolean; mode?: string }>(), { mode: '' })
const emit = defineEmits<{ menu: []; signOut: [] }>()
</script>

<template>
  <header class="app-topbar">
    <button v-if="showMenu" type="button" class="app-iconbtn" aria-label="打开导航" data-test="app-menu" @click="emit('menu')">
      <AppIcon name="menu" />
    </button>
    <nav class="app-topbar__crumb" aria-label="当前位置">
      <template v-for="(crumb, index) in crumbs" :key="index">
        <span v-if="index > 0" aria-hidden="true">/</span>
        <RouterLink v-if="crumb.to && index < crumbs.length - 1" :to="crumb.to">{{ crumb.label }}</RouterLink>
        <span v-else :aria-current="index === crumbs.length - 1 ? 'page' : undefined">{{ crumb.label }}</span>
      </template>
    </nav>
    <div class="app-topbar__user">
      <span v-if="mode" class="app-topbar__mode" data-test="mode-demo" role="status">{{ mode }}</span>
      <span class="app-topbar__name" data-test="app-user">{{ user }}</span>
      <button type="button" class="app-topbar__out" data-test="app-sign-out" @click="emit('signOut')">退出登录</button>
    </div>
  </header>
</template>
