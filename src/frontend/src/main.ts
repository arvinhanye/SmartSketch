import { createPinia } from 'pinia'
import { createApp } from 'vue'
import { createWebHistory } from 'vue-router'
import App from './App.vue'
import { AUTH_API_KEY, createAuthApi, createSessionHttpClient } from './api/auth'
import { createAppRouter, NOTICE_UNAUTHENTICATED, ROOT_ROUTE } from './router'
import { useSessionStore } from './stores/session'
import LoginView from './views/LoginView.vue'

const pinia = createPinia()
const session = useSessionStore(pinia)

// 路由守卫只用 LoginResponse.user.role 选首页；授权以后端为准（specs/identity-access.md §2.4）
const router = createAppRouter({
  history: createWebHistory(),
  getAccountRole: () => session.role,
  loginComponent: LoginView,
})

// 受保护接口 401：清会话与课程上下文后回登录页
const http = createSessionHttpClient(session, () => {
  void router.replace({ name: ROOT_ROUTE, query: { notice: NOTICE_UNAUTHENTICATED } })
})

createApp(App).use(pinia).use(router).provide(AUTH_API_KEY, createAuthApi(http)).mount('#app')
