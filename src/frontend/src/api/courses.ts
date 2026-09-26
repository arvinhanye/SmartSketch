import type { InjectionKey } from 'vue'
import type { components } from '../../../contracts/v1/generated/typescript/openapi'
import type { HttpClient, RequestControl } from './http'

/**
 * 课程接口（H01）：只封装契约 `GET/POST /api/v1/courses` 与 `GET /api/v1/courses/{cid}`。
 * 不做状态、不做错误文案；错误按 B15 的错误类型原样抛出，由 composable 处理。
 */

export type Course = components['schemas']['Course']
export type CourseCreate = components['schemas']['CourseCreate']

export interface CoursesApi {
  /** 当前用户可见的课程（`specs/identity-access.md` §4.4） */
  list(control?: RequestControl): Promise<Course[]>
  /** 新建课程（仅教师账号，否则 403 `ROLE_FORBIDDEN`） */
  create(body: CourseCreate, control?: RequestControl): Promise<Course>
  /** 课程详情；非成员或课程不存在为 403 `COURSE_FORBIDDEN` */
  get(cid: string, control?: RequestControl): Promise<Course>
}

/** 视图经 inject 取得课程接口，测试可注入假实现 */
export const COURSES_API_KEY: InjectionKey<CoursesApi> = Symbol('smartsketch.courses-api')

export function createCoursesApi(client: HttpClient): CoursesApi {
  return {
    list: (control = {}) => client.request('get', '/api/v1/courses', control),
    create: (body, control = {}) => client.request('post', '/api/v1/courses', { ...control, body }),
    get: (cid, control = {}) => client.request('get', '/api/v1/courses/{cid}', { ...control, params: { cid } }),
  }
}
