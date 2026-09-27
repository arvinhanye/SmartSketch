import type { InjectionKey } from 'vue'
import type { components } from '../../../contracts/v1/generated/typescript/openapi'
import type { HttpClient, RequestControl } from './http'

/** G06 发布、版本列表和前滚式回滚；本层不缓存服务端版本指针。 */
export type GraphVersion = components['schemas']['GraphVersion']
export type PublishResult = components['schemas']['PublishResult']

export interface VersionsApi {
  list(cid: string, control?: RequestControl): Promise<GraphVersion[]>
  publish(cid: string, control?: RequestControl): Promise<PublishResult>
  rollback(cid: string, version: number, control?: RequestControl): Promise<PublishResult>
}

export const VERSIONS_API_KEY: InjectionKey<VersionsApi> = Symbol('smartsketch.versions-api')

export function createVersionsApi(client: HttpClient): VersionsApi {
  return {
    list: (cid, control = {}) => client.request('get', '/api/v1/courses/{cid}/versions', { ...control, params: { cid } }),
    publish: (cid, control = {}) => client.request('post', '/api/v1/courses/{cid}/publish', { ...control, params: { cid } }),
    rollback: (cid, version, control = {}) => {
      if (!Number.isInteger(version) || version < 1) return Promise.reject(new RangeError('版本号须为正整数'))
      return client.request('post', '/api/v1/courses/{cid}/versions/{version}/rollback', {
        ...control, params: { cid, version },
      })
    },
  }
}
