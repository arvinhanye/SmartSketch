import type { InjectionKey } from 'vue'
import type { components } from '../../../contracts/v1/generated/typescript/openapi'
import type { HttpClient, RequestControl } from './http'

/**
 * 课程成员接口（H12）：只封装契约 `listMembers`、`addMember`、`removeMember`。
 * 不做状态、不做错误文案；错误按 B15 的错误类型原样抛出，由 composable 处理。
 *
 * - `add` 在新加入（201）与已是成员（200，幂等返回原成员行、不改角色）时都返回 `CourseMember`；
 *   客户端不区分两种状态码，调用方按 `user_id` 是否已在列表中判断是否重复。
 * - `remove` 成功为 204，无响应体。
 */

export type CourseMember = components['schemas']['CourseMember']
export type MemberAdd = components['schemas']['MemberAdd']

export interface MembersApi {
  /** 课程成员列表（教师成员；学生成员 403 `ROLE_FORBIDDEN`，非成员 403 `COURSE_FORBIDDEN`） */
  list(cid: string, control?: RequestControl): Promise<CourseMember[]>
  /** 按用户名添加学生成员；用户名不存在或账号停用 404 `NOT_FOUND` */
  add(cid: string, body: MemberAdd, control?: RequestControl): Promise<CourseMember>
  /** 移除学生成员；目标是教师成员 403 `ROLE_FORBIDDEN`，目标不是成员 404 `NOT_FOUND` */
  remove(cid: string, uid: string, control?: RequestControl): Promise<void>
}

/** 视图经 inject 取得成员接口，测试可注入假实现 */
export const MEMBERS_API_KEY: InjectionKey<MembersApi> = Symbol('smartsketch.members-api')

export function createMembersApi(client: HttpClient): MembersApi {
  return {
    list: (cid, control = {}) => client.request('get', '/api/v1/courses/{cid}/members', { ...control, params: { cid } }),
    add: (cid, body, control = {}) =>
      client.request('post', '/api/v1/courses/{cid}/members', { ...control, params: { cid }, body }),
    remove: async (cid, uid, control = {}) => {
      await client.request('delete', '/api/v1/courses/{cid}/members/{uid}', { ...control, params: { cid, uid } })
    },
  }
}
