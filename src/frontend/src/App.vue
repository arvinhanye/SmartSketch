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
  REVIEW_ROUTE,
  ROOT_ROUTE,
  SETTINGS_ROUTE,
  STUDENT_GRAPH_ROUTE,
  TEACHER_GRAPH_ROUTE,
} from './router'
import { readCourseDetail } from './composables/courseDetailRequest'
import { COURSES_API_KEY } from './api/courses'
import { useCourseStore } from './stores/course'
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
const dismissedNotice = ref(false)
watch(
  () => route?.fullPath,
  () => { dismissedNotice.value = false },
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
// 方向 A「工作台」：登录后左侧常驻导航；未登录（登录、注册页）只留顶栏
const withSidebar = computed(() => route !== null && role.value !== null)
const onLoginPage = computed(() => route?.name === ROOT_ROUTE && role.value === null)

interface NavItem {
  label: string
  to: RouteLocationRaw
  active: boolean
}

const courseId = computed(() => {
  const cid = route?.params.cid
  return typeof cid === 'string' && cid !== '' ? cid : null
})

// L15：课程权限与账号类型分离；读取失败/未知时不猜测权限。
const courseApi = inject(COURSES_API_KEY, null)
const courseStore = getActivePinia() ? useCourseStore() : null
watch([courseId, () => session?.accessToken ?? null], async ([cid, token]) => {
  if (courseStore === null) return
  courseStore.selectCourse(token === null ? null : cid)
  if (cid === null || token === null || courseApi === null) return
  const scope = courseStore.beginRequest()
  try {
    const detail = await readCourseDetail(courseApi, cid, scope.signal)
    if (session?.accessToken === token && detail.id === cid) courseStore.setRole(scope, detail.my_role)
  } catch { /* 未知角色只提供概览，页面负责错误提示。 */ }
}, { immediate: true, flush: 'sync' })
const courseNav = computed<NavItem[]>(() => {
  const cid = courseId.value
  if (cid === null || router === null || role.value === null) return []
  const names =
    courseStore?.myRole === null || courseStore === null
      ? [[COURSE_ROUTE, '课程概览']]
      : courseStore.myRole === 'teacher'
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
    .map(([name, label]) => ({ label, to: { name, params: { cid } }, active: route?.name === name }))
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
  <div class="app" :class="{ 'app--workbench': withSidebar, 'app--login': onLoginPage }">
    <header v-if="!withSidebar" class="app-header">
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
          我的课程
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
            {{ item.label }}
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
          模型 API 设置
          <span v-if="runtime?.needsConfig" class="app-nav__badge" data-test="nav-model-settings-pending">未配置</span>
        </RouterLink>
      </nav>
      <p v-if="runtime?.isDemo" class="app-mode" data-test="mode-demo" role="status">演示模式 · 使用内置演示模型，不调用个人 API</p>
      <div class="app-sidebar__user">
        <span data-test="app-user">{{ session?.user?.username }} · {{ roleLabel }}</span>
        <button type="button" data-variant="secondary" data-test="app-sign-out" @click="signOut">退出登录</button>
      </div>
    </aside>
  </div>
</template>
