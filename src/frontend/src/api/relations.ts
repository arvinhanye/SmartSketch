import type { InjectionKey } from 'vue'
import type { components } from '../../../contracts/v1/generated/typescript/openapi'
import type { HttpClient, RequestControl } from './http'

/**
 * 教师关系编辑接口（H08）：只封装契约 `createRelation`、`updateRelation`、`deleteRelation`。
 * 不做状态、不做错误文案；错误按 B15 的错误类型原样抛出，由 `useRelationEditor` 处理。
 *
 * - 成环时服务端返回 409 `CYCLE_DETECTED`，`details.cycle` 为首尾相同的知识点 ID 链路（errors.v1.md）。
 * - `update` 改方向时服务端可能按新端点派生新的关系 ID（F06 `derive_rel_id`），以响应体为准。
 * - `remove` 成功为 204，无响应体。
 */

export type Relation = components['schemas']['Relation']
export type RelationCreate = components['schemas']['RelationCreate']
export type RelationUpdate = components['schemas']['RelationUpdate']

export interface RelationsApi {
  create(cid: string, body: RelationCreate, control?: RequestControl): Promise<Relation>
  update(cid: string, rid: string, body: RelationUpdate, control?: RequestControl): Promise<Relation>
  remove(cid: string, rid: string, control?: RequestControl): Promise<void>
}

/** 页面经 inject 取得关系接口，测试可注入假实现 */
export const RELATIONS_API_KEY: InjectionKey<RelationsApi> = Symbol('smartsketch.relations-api')

export function createRelationsApi(client: HttpClient): RelationsApi {
  return {
    create: (cid, body, control = {}) =>
      client.request('post', '/api/v1/courses/{cid}/relations', { ...control, params: { cid }, body }),
    update: (cid, rid, body, control = {}) =>
      client.request('patch', '/api/v1/courses/{cid}/relations/{rid}', { ...control, params: { cid, rid }, body }),
    remove: async (cid, rid, control = {}) => {
      await client.request('delete', '/api/v1/courses/{cid}/relations/{rid}', { ...control, params: { cid, rid } })
    },
  }
}
