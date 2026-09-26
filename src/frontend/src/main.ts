import { createPinia } from 'pinia'
import { createApp } from 'vue'
import { createWebHistory } from 'vue-router'
import App from './App.vue'
import { AUTH_API_KEY, createAuthApi, createSessionHttpClient } from './api/auth'
import { HTTP_CLIENT_KEY } from './api/client'
import { COURSES_API_KEY, createCoursesApi } from './api/courses'
import { createMaterialsApi, MATERIALS_API_KEY, TASK_EVENTS_CLIENT_KEY } from './api/materials'
import { createTaskEventsClient } from './api/taskEvents'
import { createAppRouter, NOTICE_UNAUTHENTICATED, ROOT_ROUTE } from './router'
import { useSessionStore } from './stores/session'
import CoursesView from './views/CoursesView.vue'
import LoginView from './views/LoginView.vue'
import MaterialsView from './views/MaterialsView.vue'

const pinia = createPinia()
const session = useSessionStore(pinia)

// 路由守卫只用 LoginResponse.user.role 选首页；授权以后端为准（specs/identity-access.md §2.4）
const router = createAppRouter({
  history: createWebHistory(),
  getAccountRole: () => session.role,
  loginComponent: LoginView,
  // H01：教师/学生首页都是课程列表，并注册 /courses/:cid
  coursesComponent: CoursesView,
  // H02：/courses/:cid/materials
  materialsComponent: MaterialsView,
})

// 受保护接口 401：清会话与课程上下文后回登录页
const http = createSessionHttpClient(session, () => {
  void router.replace({ name: ROOT_ROUTE, query: { notice: NOTICE_UNAUTHENTICATED } })
})

// 所有功能 API 共用同一个会话客户端，受保护接口 401 才会统一回登录页
createApp(App)
  .use(pinia)
  .use(router)
  .provide(HTTP_CLIENT_KEY, http)
  .provide(AUTH_API_KEY, createAuthApi(http))
  .provide(COURSES_API_KEY, createCoursesApi(http))
  .provide(MATERIALS_API_KEY, createMaterialsApi(http))
  .provide(TASK_EVENTS_CLIENT_KEY, createTaskEventsClient({ client: http }))
  .mount('#app')
