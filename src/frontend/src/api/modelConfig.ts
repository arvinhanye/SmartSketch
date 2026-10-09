import type { InjectionKey } from 'vue'
import type { components } from '../../../contracts/v1/generated/typescript/openapi'
import type { HttpClient, RequestControl } from './http'

/**
 * 当前用户的个人模型 API 配置（L10，ADR-080）：封装配置与只读模型发现契约。
 * 响应永不含密钥；请求里的 `api_key` 仅随保存、测试或模型发现请求发送，本模块与调用方都不缓存它。
 */

export type ModelConfig = components['schemas']['ModelConfig']
export type ModelConfigUpdate = components['schemas']['ModelConfigUpdate']
export type ModelConfigTestRequest = components['schemas']['ModelConfigTestRequest']
export type ModelConfigTestResult = components['schemas']['ModelConfigTestResult']

export type ModelDiscoveryRequest = components['schemas']['ModelDiscoveryRequest']
export type ModelDiscoveryResult = components['schemas']['ModelDiscoveryResult']

export interface ModelConfigApi {
  discover?(body?: ModelDiscoveryRequest, control?: RequestControl): Promise<ModelDiscoveryResult>
  get(control?: RequestControl): Promise<ModelConfig>
  save(body: ModelConfigUpdate, control?: RequestControl): Promise<ModelConfig>
  clear(control?: RequestControl): Promise<void>
  /** 不带 `body` 测试已保存的配置；带则测试这组值而不保存 */
  test(body?: ModelConfigTestRequest, control?: RequestControl): Promise<ModelConfigTestResult>
}

export const MODEL_CONFIG_API_KEY: InjectionKey<ModelConfigApi> = Symbol('smartsketch.model-config-api')

export function createModelConfigApi(client: HttpClient): ModelConfigApi {
  return {
    discover: (body, control = {}) => client.request('post', '/api/v1/me/model-config/models', body === undefined ? { ...control } : { ...control, body }),
    get: (control = {}) => client.request('get', '/api/v1/me/model-config', { ...control }),
    save: (body, control = {}) => client.request('put', '/api/v1/me/model-config', { ...control, body }),
    clear: async (control = {}) => {
      await client.request('delete', '/api/v1/me/model-config', { ...control })
    },
    test: (body, control = {}) =>
      client.request('post', '/api/v1/me/model-config/test', body === undefined ? { ...control } : { ...control, body }),
  }
}
