import type { InjectionKey } from 'vue'
import type { components } from '../../../contracts/v1/generated/typescript/openapi'
import type { HttpClient, RequestControl } from './http'

/**
 * 知识点详情接口（H06）：只封装契约 `getKnowledgePoint`（`GET /api/v1/courses/{cid}/kp/{kid}`）。
 * 教师读草稿、学生读当前发布版本由后端按身份决定（ADR-030），前端不传版本。
 * 不做状态、不做错误文案；错误按 B15 的错误类型原样抛出，由 composable 处理。
 */

export type KnowledgePointDetail = components['schemas']['KnowledgePointDetail']
export type SourceRef = components['schemas']['SourceRef']
export type KnowledgePointRef = components['schemas']['KnowledgePointRef']
/** F09 级联删除的影响报告（ADR-092）：预览与实际删除返回同一结构。 */
export type KnowledgePointDeletion = components['schemas']['KnowledgePointDeletion']
export type KnowledgePointDeletionNode = components['schemas']['KnowledgePointDeletionNode']

export interface KnowledgeDetailApi {
  /** 知识点详情与出处；不存在 404 `NOT_FOUND`，学生读未发布课程 404 `GRAPH_NOT_PUBLISHED` */
  get(cid: string, kid: string, control?: RequestControl): Promise<KnowledgePointDetail>
  /**
   * 只读预览删除影响（`cascade=true` 时会删掉哪些知识点与多少条关系）。
   * 供确认弹窗展示，避免「说删 3 个、实际删了 30 个」（ADR-092）。
   */
  deleteImpact(cid: string, kid: string, control?: RequestControl): Promise<KnowledgePointDeletion>
  /**
   * 删除知识点。`cascade=false`（缺省）只删该节点，后端返回 204 无响应体（这里是 `null`）；
   * `cascade=true` 连带删除会变成孤儿的后代，返回删除报告。
   */
  remove(cid: string, kid: string, options?: { cascade?: boolean } & RequestControl):
    Promise<KnowledgePointDeletion | null>
}
/** 组件经 inject 取得详情接口，测试可注入假实现；未提供时组件用 `HTTP_CLIENT_KEY` 的客户端构造 */
export const KNOWLEDGE_DETAIL_API_KEY: InjectionKey<KnowledgeDetailApi> = Symbol('smartsketch.knowledge-detail-api')

export function createKnowledgeDetailApi(client: HttpClient): KnowledgeDetailApi {
  return {
    get: (cid, kid, control = {}) =>
      client.request('get', '/api/v1/courses/{cid}/kp/{kid}', { ...control, params: { cid, kid } }),
    deleteImpact: (cid, kid, control = {}) =>
      client.request('get', '/api/v1/courses/{cid}/kp/{kid}/delete-impact', {
        ...control,
        params: { cid, kid },
      }),
    remove: async (cid, kid, options = {}) =>
      (await client.request('delete', '/api/v1/courses/{cid}/kp/{kid}', {
        ...options,
        params: { cid, kid },
        // cascade 是 query 参数（契约 ADR-092）；缺省 false 保持原 204 行为
        query: { cascade: options.cascade === true },
      })) ?? null,
  }
}
