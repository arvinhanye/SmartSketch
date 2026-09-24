import { createRouter, type RouterHistory } from 'vue-router'
import type { components } from '../../../contracts/v1/generated/typescript/openapi'
import StudentHome from '../views/StudentHome.vue'
import TeacherHome from '../views/TeacherHome.vue'

export type Role = components['schemas']['Role']

declare module 'vue-router' {
  interface RouteMeta {
    /** 页面所需的账号类型（users.role），只用于界面引导 */
    accountRole?: Role
  }
}

/** 守卫重定向时写入 query.notice 的提示码，由 App 外壳渲染 */
export const NOTICE_UNAUTHENTICATED = 'unauthenticated'
export const NOTICE_WRONG_ROLE = 'wrong-role'

export const ROOT_ROUTE = 'root'
const HOME_ROUTE: Record<Role, string> = { teacher: 'teacher-home', student: 'student-home' }

export interface AppRouterOptions {
  history: RouterHistory
  /** 当前登录账号的类型；未登录返回 null */
  getAccountRole: () => Role | null
}

export function createAppRouter({ history, getAccountRole }: AppRouterOptions) {
  const router = createRouter({
    history,
    routes: [
      // 未登录时停在这里，页面本身为空，提示由外壳显示
      { path: '/', name: ROOT_ROUTE, component: { render: () => null } },
      { path: '/teacher', name: HOME_ROUTE.teacher, component: TeacherHome, meta: { accountRole: 'teacher' } },
      { path: '/student', name: HOME_ROUTE.student, component: StudentHome, meta: { accountRole: 'student' } },
      { path: '/:pathMatch(.*)*', redirect: '/' },
    ],
  })

  // 前端守卫只是界面引导，授权以后端为准（specs/identity-access.md §2.4）
  router.beforeEach((to) => {
    const role = getAccountRole()
    if (role === null) {
      if (to.name === ROOT_ROUTE && to.query.notice === NOTICE_UNAUTHENTICATED) return true
      return { name: ROOT_ROUTE, query: { notice: NOTICE_UNAUTHENTICATED } }
    }
    const required = to.meta.accountRole
    if (required === undefined) return { name: HOME_ROUTE[role] }
    if (required !== role) return { name: HOME_ROUTE[role], query: { notice: NOTICE_WRONG_ROLE } }
    return true
  })

  return router
}
