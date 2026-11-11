import type { InjectionKey } from 'vue'
import type { components } from '../../../contracts/v1/generated/typescript/openapi'
import type { Course } from './courses'
import type { HttpClient, RequestControl } from './http'

export type InviteCodeResponse = components['schemas']['InviteCodeResponse']
export type CourseJoinRequest = components['schemas']['CourseJoinRequest']

export interface InviteCodeApi {
  get(cid: string, control?: RequestControl): Promise<InviteCodeResponse>
  rotate(cid: string, control?: RequestControl): Promise<InviteCodeResponse>
  join(body: CourseJoinRequest, control?: RequestControl): Promise<Course>
}

export const INVITE_CODE_API_KEY: InjectionKey<InviteCodeApi> = Symbol('smartsketch.invite-code-api')

/** 仅封装契约请求，邀请码不进入浏览器持久存储。 */
export function createInviteCodeApi(client: HttpClient): InviteCodeApi {
  return {
    get: (cid, control = {}) => client.request('get', '/api/v1/courses/{cid}/invite-code', { ...control, params: { cid } }),
    rotate: (cid, control = {}) => client.request('post', '/api/v1/courses/{cid}/invite-code:rotate', { ...control, params: { cid } }),
    join: (body, control = {}) => client.request('post', '/api/v1/courses/join', { ...control, body }),
  }
}
