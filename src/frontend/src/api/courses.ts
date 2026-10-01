import type { InjectionKey } from 'vue'
import type { components } from '../../../contracts/v1/generated/typescript/openapi'
import type { HttpClient, RequestControl } from './http'

/**
 * 课程接口（H01）：只封装契约 `GET/POST /api/v1/courses` 与 `GET /api/v1/courses/{cid}`。
 * 不做状态、不做错误文案；错误按 B15 的错误类型原样抛出，由 composable 处理。
 */

export type Course = components['schemas']['Course']
export type CourseCreate = components['schemas']['CourseCreate']

/** 课程智能功能可用状态：向量不是真实模型生成时，需要用户主动「重新处理资料」。 */
export interface CourseIntelligence {
  ready: boolean
  needs_reprocess: boolean
  message: string
  documents: number
  can_reprocess: boolean
  embedding_space: string | null
}

export interface CoursesApi {
  /** 当前用户可见的课程（`specs/identity-access.md` §4.4） */
  list(control?: RequestControl): Promise<Course[]>
  /** 新建课程（仅教师账号，否则 403 `ROLE_FORBIDDEN`） */
  create(body: CourseCreate, control?: RequestControl): Promise<Course>
  /** 课程详情；非成员或课程不存在为 403 `COURSE_FORBIDDEN` */
  get(cid: string, control?: RequestControl): Promise<Course>
  /** 课程的智能功能是否可用（教师、本课成员）；注入的假实现可以不提供 */
  intelligence?(cid: string): Promise<CourseIntelligence>
  /** 重新处理本课程资料：用原文件重新排队，保留原有资料与图谱 */
  reprocess?(cid: string): Promise<{ task_ids: string[]; count: number }>
}

/** 视图经 inject 取得课程接口，测试可注入假实现 */
export const COURSES_API_KEY: InjectionKey<CoursesApi> = Symbol('smartsketch.courses-api')

/** 课程智能状态与「重新处理资料」不在生成的契约里，直接用带令牌的 fetch 调用。 */
async function callJson<T>(path: string, method: string, token: () => string | null): Promise<T> {
  const response = await fetch(path, {
    method,
    headers: { Authorization: `Bearer ${token() ?? ''}`, 'Content-Type': 'application/json' },
    signal: AbortSignal.timeout(20000),
  })
  const payload = await response.json().catch(() => null)
  if (!response.ok) {
    const message = payload && typeof payload.message === 'string' ? payload.message : '操作失败，请稍后重试'
    throw new Error(message)
  }
  return payload as T
}

export function createCoursesApi(client: HttpClient, token: () => string | null = () => null): CoursesApi {
  return {
    list: (control = {}) => client.request('get', '/api/v1/courses', control),
    create: (body, control = {}) => client.request('post', '/api/v1/courses', { ...control, body }),
    get: (cid, control = {}) => client.request('get', '/api/v1/courses/{cid}', { ...control, params: { cid } }),
    intelligence: (cid) => callJson<CourseIntelligence>(`/api/v1/courses/${encodeURIComponent(cid)}/intelligence`, 'GET', token),
    reprocess: (cid) => callJson<{ task_ids: string[]; count: number }>(`/api/v1/courses/${encodeURIComponent(cid)}/reprocess`, 'POST', token),
  }
}
