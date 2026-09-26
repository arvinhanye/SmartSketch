import type { Component } from 'vue'
import { createRouter, type RouteRecordRaw, type RouterHistory } from 'vue-router'
import type { components } from '../../../contracts/v1/generated/typescript/openapi'
import StudentHome from '../views/StudentHome.vue'
import TeacherHome from '../views/TeacherHome.vue'

export type Role = components['schemas']['Role']

declare module 'vue-router' {
  interface RouteMeta {
    /** 页面所需的账号类型（users.role），只用于界面引导 */
    accountRole?: Role
    /** 任一已登录账号都可访问（如课程页：课程内角色由 `Course.my_role` 决定，与账号类型无关） */
    anyAccountRole?: boolean
  }
}

/** 守卫重定向时写入 query.notice 的提示码，由 App 外壳渲染 */
export const NOTICE_UNAUTHENTICATED = 'unauthenticated'
export const NOTICE_WRONG_ROLE = 'wrong-role'
/** 课程接口返回 `COURSE_FORBIDDEN` 后回课程列表时写入，由课程页渲染（`errors.v1.md`） */
export const NOTICE_COURSE_FORBIDDEN = 'course-forbidden'

export const ROOT_ROUTE = 'root'
/** 单个课程页的路由名，参数 `cid` 经 `useCourseStore().selectCourse` 成为当前课程（H01） */
export const COURSE_ROUTE = 'course'
/** 课程成员管理页的路由名（H12），参数 `cid`；仅教师账号可进入，授权以后端课程内角色为准 */
export const COURSE_MEMBERS_ROUTE = 'course-members'
/** 课程资料上传与处理进度页（H02），参数 `cid`；课程内教师才可用，由页面按 `Course.my_role` 引导 */
export const MATERIALS_ROUTE = 'course-materials'
const HOME_ROUTE: Record<Role, string> = { teacher: 'teacher-home', student: 'student-home' }

/** 该账号类型的默认首页路由名（登录成功后按 `LoginResponse.user.role` 跳转） */
export function homeRouteFor(role: Role): string {
  return HOME_ROUTE[role]
}

export interface AppRouterOptions {
  history: RouterHistory
  /** 当前登录账号的类型；未登录返回 null */
  getAccountRole: () => Role | null
  /** 未登录时在根路由显示的登录页（H13）；省略时根路由为空页，只显示外壳提示 */
  loginComponent?: Component
  /**
   * 课程首页（H01）。注入后教师/学生首页都渲染它，并注册 `/courses/:cid`；
   * 省略时保持 B03 的占位首页，不注册课程路由。
   */
  coursesComponent?: Component
  /** 课程成员管理页（H12）。注入后注册 `/courses/:cid/members`；省略时不注册 */
  membersComponent?: Component
  /** 资料上传与进度页（H02）。注入后注册 `/courses/:cid/materials` */
  materialsComponent?: Component
}

export function createAppRouter({
  history,
  getAccountRole,
  loginComponent,
  coursesComponent,
  membersComponent,
  materialsComponent,
}: AppRouterOptions) {
  const routes: RouteRecordRaw[] = [
    // 未登录时停在这里：显示登录页（未注入时为空页），提示由外壳显示；已登录则被守卫送往首页
    { path: '/', name: ROOT_ROUTE, component: loginComponent ?? { render: () => null } },
    {
      path: '/teacher',
      name: HOME_ROUTE.teacher,
      component: coursesComponent ?? TeacherHome,
      meta: { accountRole: 'teacher' },
    },
    {
      path: '/student',
      name: HOME_ROUTE.student,
      component: coursesComponent ?? StudentHome,
      meta: { accountRole: 'student' },
    },
  ]
  if (coursesComponent) {
    routes.push({ path: '/courses/:cid', name: COURSE_ROUTE, component: coursesComponent, meta: { anyAccountRole: true } })
  }
  if (membersComponent) {
    // 学生账号无入口：守卫按账号类型送回学生首页；教师账号在本课是否为教师成员由后端 403 判定
    routes.push({
      path: '/courses/:cid/members',
      name: COURSE_MEMBERS_ROUTE,
      component: membersComponent,
      meta: { accountRole: 'teacher' },
    })
  }
  if (materialsComponent) {
    // 课程内角色与账号类型无关（教师账号可在别的课做学生），故不按账号类型拦截
    routes.push({
      path: '/courses/:cid/materials',
      name: MATERIALS_ROUTE,
      component: materialsComponent,
      meta: { anyAccountRole: true },
    })
  }
  routes.push({ path: '/:pathMatch(.*)*', redirect: '/' })

  const router = createRouter({ history, routes })

  // 前端守卫只是界面引导，授权以后端为准（specs/identity-access.md §2.4）
  router.beforeEach((to) => {
    const role = getAccountRole()
    if (role === null) {
      if (to.name === ROOT_ROUTE && to.query.notice === NOTICE_UNAUTHENTICATED) return true
      return { name: ROOT_ROUTE, query: { notice: NOTICE_UNAUTHENTICATED } }
    }
    if (to.meta.anyAccountRole) return true
    const required = to.meta.accountRole
    if (required === undefined) return { name: HOME_ROUTE[role] }
    if (required !== role) return { name: HOME_ROUTE[role], query: { notice: NOTICE_WRONG_ROLE } }
    return true
  })

  return router
}
