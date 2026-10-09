import type { InjectionKey } from 'vue'
import type { components } from '../../../contracts/v1/generated/typescript/openapi'
import type { HttpClient, RequestControl } from './http'
export type EmbeddingConfig = components['schemas']['EmbeddingConfig']
export type EmbeddingConfigUpdate = components['schemas']['EmbeddingConfigUpdate']
export interface EmbeddingConfigApi {
 get(control?:RequestControl):Promise<EmbeddingConfig>
 save(body:EmbeddingConfigUpdate,control?:RequestControl):Promise<EmbeddingConfig>
 test(body:EmbeddingConfigUpdate,control?:RequestControl):Promise<components['schemas']['ModelConfigTestResult']>
 discover(body?:components['schemas']['ModelDiscoveryRequest'],control?:RequestControl):Promise<components['schemas']['ModelDiscoveryResult']>
}
export const EMBEDDING_CONFIG_API_KEY:InjectionKey<EmbeddingConfigApi>=Symbol('smartsketch.embedding-config-api')
export function createEmbeddingConfigApi(client:HttpClient):EmbeddingConfigApi {
 return {
  get:(control={})=>client.request('get','/api/v1/me/embedding-config',control),
  save:(body,control={})=>client.request('put','/api/v1/me/embedding-config',{timeoutMs:300000,...control,body}),
  test:(body,control={})=>client.request('post','/api/v1/me/embedding-config/test',{...control,body}),
  discover:(body,control={})=>client.request('post','/api/v1/me/embedding-config/models',{...control,body:body??{}}),
 }
}
