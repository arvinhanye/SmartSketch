import type { InjectionKey } from 'vue'
import type { components } from '../../../contracts/v1/generated/typescript/openapi'
import type { HttpClient, RequestControl } from './http'

/**
 * 教师节点编辑接口（H07）：只封装契约 `getKnowledgePoint`、`updateKnowledgePoint`、`unlockKnowledgePoint`、
 * `deleteKnowledgePoint`，以及 L11 补上的 `createKnowledgePoint`（新建必带来源，ADR-035）。不做状态、不做错误文案；错误按 B15 的错误类型原样抛出，由 `useNodeEditor` 处理。
 *
 * - `update` / `unlock` 必带节点级 `expected_revision`，不一致时 409 `REVISION_CONFLICT`（ADR-035）。
 * - `remove` 可选 `expected_revision`（ADR-048）；编辑面板总是带上读到的修订号，成功为 204，无响应体。
 */

export type KnowledgePoint = components['schemas']['KnowledgePoint']
export type KnowledgePointDetail = components['schemas']['KnowledgePointDetail']
export type KnowledgePointUpdate = components['schemas']['KnowledgePointUpdate']
export type KnowledgePointCreate = components['schemas']['KnowledgePointCreate']

export interface NodeEditApi {
  get(cid: string, kid: string, control?: RequestControl): Promise<KnowledgePointDetail>
  update(cid: string, kid: string, body: KnowledgePointUpdate, control?: RequestControl): Promise<KnowledgePoint>
  unlock(cid: string, kid: string, expectedRevision: number, control?: RequestControl): Promise<KnowledgePoint>
  remove(cid: string, kid: string, expectedRevision: number, control?: RequestControl): Promise<void>
  /** 新建知识点：201 返回新节点；来源不属于本课程或未审核通过时 422，课程写锁超时 409 `COURSE_BUSY` */
  create(cid: string, body: KnowledgePointCreate, control?: RequestControl): Promise<KnowledgePoint>
}

/** 组件经 inject 取得节点编辑接口，测试可注入假实现；未提供时组件用 `HTTP_CLIENT_KEY` 的客户端构造 */
export const NODE_EDIT_API_KEY: InjectionKey<NodeEditApi> = Symbol('smartsketch.node-edit-api')

export function createNodeEditApi(client: HttpClient): NodeEditApi {
  return {
    get: (cid, kid, control = {}) =>
      client.request('get', '/api/v1/courses/{cid}/kp/{kid}', { ...control, params: { cid, kid } }),
    update: (cid, kid, body, control = {}) =>
      client.request('patch', '/api/v1/courses/{cid}/kp/{kid}', { ...control, params: { cid, kid }, body }),
    unlock: (cid, kid, expectedRevision, control = {}) =>
      client.request('post', '/api/v1/courses/{cid}/kp/{kid}/unlock', {
        ...control,
        params: { cid, kid },
        body: { expected_revision: expectedRevision },
      }),
    remove: async (cid, kid, expectedRevision, control = {}) => {
      await client.request('delete', '/api/v1/courses/{cid}/kp/{kid}', {
        ...control,
        params: { cid, kid },
        query: { expected_revision: expectedRevision },
      })
    },
    create: (cid, body, control = {}) =>
      client.request('post', '/api/v1/courses/{cid}/kp', { ...control, params: { cid }, body }),
  }
}
