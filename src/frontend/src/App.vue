<script setup lang="ts">
import { getActivePinia } from 'pinia'
import { computed, inject, ref, watch } from 'vue'
import { RouterLink, RouterView, routeLocationKey, routerKey, type RouteLocationRaw } from 'vue-router'
import {
  CHAT_ROUTE,
  COURSE_MEMBERS_ROUTE,
  COURSE_ROUTE,
  homeRouteFor,
  MATERIALS_ROUTE,
  NOTICE_UNAUTHENTICATED,
  NOTICE_WRONG_ROLE,
  REGISTER_ROUTE,
  REVIEW_ROUTE,
  ROOT_ROUTE,
  SETTINGS_ROUTE,
  STUDENT_GRAPH_ROUTE,
  TEACHER_GRAPH_ROUTE,
} from './router'
import { MODEL_CONFIG_API_KEY } from './api/modelConfig'
import { useRuntimeStore } from './stores/runtime'
import { useSessionStore } from './stores/session'
import './styles.css'

const appName = '智绘学途'
// 未安装路由时（如 B02 单独挂载外壳）只渲染标题，不报错
const route = inject(routeLocationKey, null)
const router = inject(routerKey, null)
// 未安装 Pinia 时（如 B03 只测路由守卫）不显示侧栏，外壳退回顶栏
const session = getActivePinia() ? useSessionStore() : null

// 提示可关闭：换页后重新显示（来源版本的提示条交互，保留目标的提示文案规则）
const dismissedNotice = ref(false)
watch(
  () => route?.fullPath,
  () => {
    dismissedNotice.value = false
  },
)

// 提示码来自守卫写入的 query；只在与当前页面相符时显示
const notice = computed(() => {
  if (!route || dismissedNotice.value) return null
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

const role = computed(() => session?.role ?? null)
// 工作台保留侧栏；登录与注册页使用独立的全屏认证外壳。
const withSidebar = computed(() => route !== null && role.value !== null)
const authPage = computed(() => !withSidebar.value && (route?.name === ROOT_ROUTE || route?.name === REGISTER_ROUTE))

interface NavItem {
  label: string
  to: RouteLocationRaw
  active: boolean
  /** 图标键：route 用页面路由名，其余用固定键 */
  icon: string
}

const courseId = computed(() => {
  const cid = route?.params.cid
  return typeof cid === 'string' && cid !== '' ? cid : null
})

// 课程内导航按账号类型给入口；课程内实际权限由各页面按 `Course.my_role` 与后端判定
const courseNav = computed<NavItem[]>(() => {
  const cid = courseId.value
  if (cid === null || router === null || role.value === null) return []
  const names =
    role.value === 'teacher'
      ? [
          [COURSE_ROUTE, '课程概览'],
          [MATERIALS_ROUTE, '教学资料'],
          [TEACHER_GRAPH_ROUTE, '图谱编辑'],
          [REVIEW_ROUTE, '审核队列'],
          [COURSE_MEMBERS_ROUTE, '成员'],
        ]
      : [
          [COURSE_ROUTE, '课程概览'],
          [STUDENT_GRAPH_ROUTE, '知识图谱与学习路径'],
          [CHAT_ROUTE, '课程问答'],
        ]
  return names
    .filter(([name]) => router.hasRoute(name))
    .map(([name, label]) => ({ label, to: { name, params: { cid } }, active: route?.name === name, icon: 'route' }))
})

const homeLink = computed<RouteLocationRaw | null>(() => (role.value === null ? null : { name: homeRouteFor(role.value) }))
const homeActive = computed(() => role.value !== null && route?.name === homeRouteFor(role.value))
const roleLabel = computed(() => (role.value === 'teacher' ? '教师' : '学生'))

// L10（ADR-080）：登录后读取一次运行模式与本人配置状态，供侧栏提示与上传/问答页的引导；
// 读取失败不阻断外壳（设置页自有错误态）。未注入接口或未装 Pinia 时（单独挂载外壳的测试）跳过。
// N03：按会话身份（登录令牌）而不是账号类型监听——同角色换号、退出重登都会立即重置；
// 旧读取被中止，即便晚到也因会话或代际不符而被丢弃。
const modelConfigApi = inject(MODEL_CONFIG_API_KEY, null)
const runtime = getActivePinia() ? useRuntimeStore() : null
let runtimeRead: AbortController | null = null
watch(
  () => session?.accessToken ?? null,
  async (key) => {
    if (runtime === null) return
    runtimeRead?.abort()
    runtimeRead = null
    runtime.startSession(key)
    if (key === null || modelConfigApi === null) return
    const controller = new AbortController()
    runtimeRead = controller
    const ticket = runtime.claim()
    try {
      runtime.commitRead(ticket, await modelConfigApi.get({ signal: controller.signal }))
    } catch {
      // 忽略：设置页会显示加载错误
    } finally {
      if (runtimeRead === controller) runtimeRead = null
    }
  },
  { immediate: true },
)

// 设置入口对任一已登录账号可见（教师在课程内的角色与此无关）
const settingsLink = computed<RouteLocationRaw | null>(() =>
  router !== null && role.value !== null && router.hasRoute(SETTINGS_ROUTE) ? { name: SETTINGS_ROUTE } : null,
)
const settingsActive = computed(() => route?.name === SETTINGS_ROUTE)

function signOut(): void {
  session?.signOut()
  void router?.replace({ name: ROOT_ROUTE })
}
</script>

<template>
  <div class="app" :class="{ 'app--workbench': withSidebar, 'app--auth': authPage }">
    <header v-if="!withSidebar && !authPage" class="app-header">
      <div class="app-header-inner">
        <span class="app-logo" aria-hidden="true">智</span>
        <h1>{{ appName }}</h1>
        <p class="app-tagline">AIGC 课程知识图谱智能构建与学习导航</p>
      </div>
    </header>
    <main class="app-main">
      <div v-if="notice" class="app-notice" role="alert">
        <span>{{ notice }}</span>
        <button type="button" class="app-notice__close" aria-label="关闭提示" @click="dismissedNotice = true">×</button>
      </div>
      <RouterView v-if="route" />
    </main>
    <!-- 侧栏在 DOM 中位于主内容之后，读屏与键盘先到页面内容；视觉上由网格放在左侧 -->
    <aside v-if="withSidebar" class="app-sidebar" aria-label="导航">
      <div class="app-sidebar__brand">
        <span class="app-logo" aria-hidden="true">智</span>
        <h1>{{ appName }}</h1>
      </div>
      <nav class="app-nav" aria-label="主导航">
        <RouterLink v-if="homeLink" :to="homeLink" class="app-nav__item" :class="{ 'is-active': homeActive }">
          <svg class="app-nav__icon" viewBox="0 0 18 18" width="16" height="16" aria-hidden="true" focusable="false">
            <path d="M9 4.2C7.8 3.2 6.2 2.8 3.8 2.8v11c2.4 0 4 .4 5.2 1.4 1.2-1 2.8-1.4 5.2-1.4v-11c-2.4 0-4 .4-5.2 1.4Z" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linejoin="round" />
            <path d="M9 4.2v11" fill="none" stroke="currentColor" stroke-width="1.4" />
          </svg>
          <span>我的课程</span>
        </RouterLink>
        <template v-if="courseNav.length">
          <p class="app-nav__heading">当前课程</p>
          <RouterLink
            v-for="item in courseNav"
            :key="item.label"
            :to="item.to"
            class="app-nav__item"
            :class="{ 'is-active': item.active }"
            :aria-current="item.active ? 'page' : undefined"
          >
            <svg class="app-nav__icon" viewBox="0 0 18 18" width="16" height="16" aria-hidden="true" focusable="false">
              <circle cx="9" cy="6" r="2.6" fill="none" stroke="currentColor" stroke-width="1.4" />
              <path d="M3.4 15c0-2.6 2.4-4.2 5.6-4.2S14.6 12.4 14.6 15" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" />
            </svg>
            <span>{{ item.label }}</span>
          </RouterLink>
        </template>
        <RouterLink
          v-if="settingsLink"
          :to="settingsLink"
          class="app-nav__item"
          :class="{ 'is-active': settingsActive }"
          :aria-current="settingsActive ? 'page' : undefined"
          data-test="nav-model-settings"
        >
          <svg class="app-nav__icon" viewBox="0 0 18 18" width="16" height="16" aria-hidden="true" focusable="false">
            <circle cx="9" cy="9" r="2.4" fill="none" stroke="currentColor" stroke-width="1.4" />
            <path d="M9 2.2v2M9 13.8v2M2.2 9h2M13.8 9h2M4.2 4.2l1.4 1.4M12.4 12.4l1.4 1.4M13.8 4.2l-1.4 1.4M5.6 12.4l-1.4 1.4" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" />
          </svg>
          <span>模型 API 设置</span>
          <span v-if="runtime?.needsConfig" class="app-nav__badge" data-test="nav-model-settings-pending">未配置</span>
        </RouterLink>
      </nav>
      <p v-if="runtime?.isDemo" class="app-mode" data-test="mode-demo" role="status">
        演示模式 · 使用内置演示模型，不调用个人 API
      </p>
      <div class="app-sidebar__user">
        <span class="app-sidebar__avatar" aria-hidden="true">
          <svg viewBox="0 0 24 24" width="18" height="18" focusable="false">
            <circle cx="12" cy="8.5" r="3.6" fill="none" stroke="currentColor" stroke-width="1.6" />
            <path d="M4.8 20c0-3.4 3.1-5.6 7.2-5.6s7.2 2.2 7.2 5.6" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" />
          </svg>
        </span>
        <span class="app-sidebar__identity" data-test="app-user">
          <span class="app-sidebar__name">{{ session?.user?.username }}</span>
          <span class="app-sidebar__role">{{ roleLabel }}</span>
        </span>
        <button type="button" class="app-sidebar__signout" data-variant="secondary" data-test="app-sign-out" @click="signOut">
          <svg viewBox="0 0 18 18" width="15" height="15" aria-hidden="true" focusable="false">
            <path d="M11 5.5V3.8A1.8 1.8 0 0 0 9.2 2H4.3A1.8 1.8 0 0 0 2.5 3.8v10.4A1.8 1.8 0 0 0 4.3 16h4.9a1.8 1.8 0 0 0 1.8-1.8v-1.7" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" />
            <path d="M7.5 9h7.8M12.4 6 15.5 9l-3.1 3" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round" />
          </svg>
          <span>退出登录</span>
        </button>
      </div>
    </aside>
  </div>
</template>
