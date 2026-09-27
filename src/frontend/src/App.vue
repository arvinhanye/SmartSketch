<script setup lang="ts">
import { computed, inject } from 'vue'
import { RouterView, routeLocationKey } from 'vue-router'
import { NOTICE_UNAUTHENTICATED, NOTICE_WRONG_ROLE, ROOT_ROUTE } from './router'
import './styles.css'

const appName = '智绘学途'
// 未安装路由时（如 B02 单独挂载外壳）只渲染标题，不报错
const route = inject(routeLocationKey, null)

// 提示码来自守卫写入的 query；只在与当前页面相符时显示
const notice = computed(() => {
  if (!route) return null
  const code = route.query.notice
  const role = route.meta.accountRole
  if (code === NOTICE_UNAUTHENTICATED && route.name === ROOT_ROUTE) {
    return '未登录：请先登录，再进入教师或学生首页。'
  }
  if (code === NOTICE_WRONG_ROLE && role === 'teacher') {
    return '当前账号类型为教师，无法进入学生首页，已返回教师首页。'
  }
  if (code === NOTICE_WRONG_ROLE && role === 'student') {
    return '当前账号类型为学生，无法进入教师首页，已返回学生首页。'
  }
  return null
})
</script>

<template>
  <div class="app">
    <header class="app-header">
      <div class="app-header-inner">
        <h1>{{ appName }}</h1>
        <p class="app-tagline">AIGC 课程知识图谱智能构建与学习导航</p>
      </div>
    </header>
    <main class="app-main">
      <p v-if="notice" role="alert">{{ notice }}</p>
      <RouterView v-if="route" />
    </main>
  </div>
</template>
