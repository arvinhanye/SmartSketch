import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { describe, expect, it, vi } from 'vitest'
import { MODEL_CONFIG_API_KEY } from '../../src/frontend/src/api/modelConfig'
import { useSessionStore } from '../../src/frontend/src/stores/session'
import { useRuntimeStore } from '../../src/frontend/src/stores/runtime'
import ModelSettingsView from '../../src/frontend/src/views/ModelSettingsView.vue'
import { EMBEDDING_CONFIG_API_KEY, type EmbeddingConfigApi } from '../../src/frontend/src/api/embeddingConfig'
async function view(role:'teacher'|'student',embedding?:EmbeddingConfigApi) {
 sessionStorage.clear();const pinia=createPinia();setActivePinia(pinia)
 useSessionStore().signIn({access_token:'t',token_type:'bearer',expires_in:3600,user:{id:'u1',username:role,role}})
 const wrapper=mount(ModelSettingsView,{global:{plugins:[pinia],provide:{[EMBEDDING_CONFIG_API_KEY as symbol]:embedding,[MODEL_CONFIG_API_KEY as symbol]:{get:async()=>({runtime_mode:'personal',configured:false}),save:vi.fn(),test:vi.fn(),clear:vi.fn()}}}})
 await flushPromises();return wrapper
}
describe('教师向量设置可见性',()=>{
 it('教师设置页出现独立向量配置区',async()=>{const w=await view('teacher');expect(w.find('[data-test=embedding-settings]').exists()).toBe(true);w.unmount()})
 it('学生设置页不显示向量配置区',async()=>{const w=await view('student');expect(w.find('[data-test=embedding-settings]').exists()).toBe(false);w.unmount()})
})

function embeddingApi() {
 const get=vi.fn(async()=>({configured:false,base_url:'https://dashscope.aliyuncs.com/compatible-mode/v1',model:'text-embedding-v4',dimensions:1024}))
 const save=vi.fn<EmbeddingConfigApi['save']>(async body=>({configured:true,base_url:body.base_url,model:body.model,dimensions:body.dimensions,key_hint:'1234',version:1}))
 const test=vi.fn(async()=>({ok:true,latency_ms:3}))
 const discover=vi.fn(async()=>({ok:true,models:['text-embedding-v4','custom-vector']}))
 return {get,save,test,discover}
}
describe('教师向量表单',()=>{
 it('学生不加载或请求向量 API',async()=>{
  const api=embeddingApi();const w=await view('student',api)
  expect(api.get).not.toHaveBeenCalled();expect(api.save).not.toHaveBeenCalled();w.unmount()
 })
 it('所选维度随独立保存发送，保存后密码清空',async()=>{
  const api=embeddingApi();const w=await view('teacher',api)
  await w.get('[data-test=em-api-key]').setValue('test-vector-key-1234')
  await w.get('[data-test=em-dimensions]').setValue('512')
  await w.get('[data-test=em-form]').trigger('submit');await flushPromises()
  expect(api.save).toHaveBeenCalledWith(expect.objectContaining({dimensions:512,model:'text-embedding-v4',api_key:'test-vector-key-1234'}),expect.any(Object))
  expect((w.get('[data-test=em-api-key]').element as HTMLInputElement).value).toBe('')
  expect(w.get('[data-test=em-status]').text()).toContain('512 维');w.unmount()
 })
 it('自定义维度越界不能测试或保存',async()=>{
  const api=embeddingApi();const w=await view('teacher',api)
  await w.get('[data-test=em-dimensions]').setValue('custom')
  await w.get('[data-test=em-custom-dimensions]').setValue('4097')
  expect(w.get('[data-test=em-save]').attributes('disabled')).toBeDefined()
  expect(w.get('[data-test=em-test]').attributes('disabled')).toBeDefined()
  expect(api.save).not.toHaveBeenCalled();w.unmount()
 })
 it('测试维度但不保存，切供应商清除旧密钥和模型',async()=>{
  const api=embeddingApi();const w=await view('teacher',api)
  await w.get('[data-test=em-api-key]').setValue('test-vector-key-1234')
  await w.get('[data-test=em-dimensions]').setValue('2048')
  await w.get('[data-test=em-test]').trigger('click');await flushPromises()
  expect(api.test).toHaveBeenCalledWith(expect.objectContaining({dimensions:2048}),expect.any(Object));expect(api.save).not.toHaveBeenCalled()
  await w.get('[data-test=em-provider]').setValue('openai')
  expect((w.get('[data-test=em-api-key]').element as HTMLInputElement).value).toBe('')
  expect((w.get('[data-test=em-model]').element as HTMLInputElement).value).toBe('');w.unmount()
 })
 it('模型目录可选择，也能手动覆盖名称',async()=>{
  const api=embeddingApi();const w=await view('teacher',api)
  await w.get('[data-test=em-api-key]').setValue('test-vector-key-1234')
  await w.get('[data-test=em-refresh-models]').trigger('click');await flushPromises()
  await w.get('[data-test=em-model-toggle]').trigger('click');await w.findAll('[role=option]')[1]!.trigger('click')
  expect((w.get('[data-test=em-model]').element as HTMLInputElement).value).toBe('custom-vector')
  await w.get('[data-test=em-model]').setValue('manual-vector')
  expect((w.get('[data-test=em-model]').element as HTMLInputElement).value).toBe('manual-vector');w.unmount()
 })
})

it('embedding save preserves missing generation configuration',async()=>{
 const api=embeddingApi();const w=await view('teacher',api)
 expect(useRuntimeStore().needsConfig).toBe(true)
 await w.get('[data-test=em-api-key]').setValue('vector-key-1234')
 await w.get('[data-test=em-form]').trigger('submit');await flushPromises()
 expect(useRuntimeStore().needsConfig).toBe(true);w.unmount()
})

// 装包前修复：教师设置页有两组同名按钮（测试连接、刷新模型列表）；读屏与自动化需要能区分。
// 可见文字不变，可访问名称在其后加括号说明所属区块（可访问名称仍包含可见文字）。
describe('教师设置页重名按钮可区分',()=>{
 it('两个“测试连接”和两个“刷新模型列表”的可访问名称各不相同且包含可见文字',async()=>{
  const w=await view('teacher',embeddingApi())
  const label=(sel:string)=>w.get(sel).attributes('aria-label')
  expect(label('[data-test=mc-test]')).toBe('测试连接（通用模型）')
  expect(label('[data-test=em-test]')).toBe('测试连接（向量模型）')
  expect(label('[data-test=mc-refresh-models]')).toBe('刷新模型列表（通用模型）')
  expect(label('[data-test=em-refresh-models]')).toBe('刷新模型列表（向量模型）')
  expect(w.get('[data-test=mc-test]').text()).toContain('测试连接')
  expect(w.get('[data-test=em-test]').text()).toContain('测试连接')
  w.unmount()
 })
})
