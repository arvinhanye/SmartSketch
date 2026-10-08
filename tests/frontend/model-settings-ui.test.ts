import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it } from 'vitest'
import { MODEL_CONFIG_API_KEY, type ModelConfigApi, type ModelConfig } from '../../src/frontend/src/api/modelConfig'
import ModelSettingsView from '../../src/frontend/src/views/ModelSettingsView.vue'
import { useSessionStore } from '../../src/frontend/src/stores/session'
const SAVED:ModelConfig={runtime_mode:'personal',configured:true,base_url:'https://api.example.com',model:'test-model',key_hint:'FAKE',version:1,updated_at:'2026-10-01T00:00:00Z',last_test:{ok:true,tested_at:'2026-10-01T00:00:00Z'}}
beforeEach(()=>{sessionStorage.clear();localStorage.clear();setActivePinia(createPinia());useSessionStore().signIn({access_token:'test-token',token_type:'bearer',expires_in:3600,user:{id:'u1',username:'student',role:'student'}})})
async function view(initial:ModelConfig,overrides:Partial<ModelConfigApi>={}) {
 const api:ModelConfigApi={get:async()=>initial,save:async()=>SAVED,clear:async()=>undefined,test:async()=>({ok:true,latency_ms:1}),...overrides}
 const wrapper=mount(ModelSettingsView,{attachTo:document.body,global:{plugins:[createPinia()],provide:{[MODEL_CONFIG_API_KEY as symbol]:api}}});await flushPromises();return wrapper
}
describe('模型设置分区与可访问性',()=>{
 it('去配置聚焦服务地址，密钥保留密码框安全属性',async()=>{
  const wrapper=await view({runtime_mode:'personal',configured:false})
  await wrapper.get('[data-test="mc-configure"]').trigger('click')
  expect(document.activeElement).toBe(wrapper.get('[data-test="mc-base-url"]').element)
  const key=wrapper.get('[data-test="mc-api-key"]')
  expect(key.attributes('type')).toBe('password');expect(key.attributes('autocomplete')).toBe('off');expect(key.attributes('spellcheck')).toBe('false')
 })
 it('思考开关表达状态且继续控制同一表单值',async()=>{
  const wrapper=await view({runtime_mode:'personal',configured:false})
  const toggle=wrapper.get('[data-test="mc-disable-thinking"]')
  expect(toggle.attributes('role')).toBe('switch')
  expect(toggle.attributes('aria-checked')).toBe('false')
  await toggle.setValue(true);expect(toggle.attributes('aria-checked')).toBe('true')
 })
 it('状态卡展示脱敏密钥与真实测试日期，保存值不回填密码',async()=>{
  const wrapper=await view(SAVED)
  expect(wrapper.get('[data-test="mc-status"]').text()).toContain('••••FAKE')
  expect(wrapper.get('[data-test="mc-last-tested"] time').attributes('datetime')).toBe('2026-10-01T00:00:00Z')
  expect((wrapper.get('[data-test="mc-api-key"]').element as HTMLInputElement).value).toBe('')
 })
 it('清除取消不删除；确认期间其他操作禁用',async()=>{
  let deletes=0;let resolve!:()=>void
  const wrapper=await view(SAVED,{clear:()=>{deletes++;return new Promise(r=>{resolve=r})}})
  await wrapper.get('[data-test="mc-clear"]').trigger('click');await wrapper.get('[data-test="mc-clear-cancel"]').trigger('click')
  expect(deletes).toBe(0);expect(wrapper.find('[data-test="mc-clear-confirm"]').exists()).toBe(false)
  await wrapper.get('[data-test="mc-clear"]').trigger('click');await wrapper.get('[data-test="mc-clear-confirm"]').trigger('click')
  expect(deletes).toBe(1);expect(wrapper.get('[data-test="mc-save"]').attributes('disabled')).toBeDefined();expect(wrapper.get('[data-test="mc-test"]').attributes('disabled')).toBeDefined()
  resolve();await flushPromises();expect(wrapper.get('[data-test="mc-status"]').text()).toContain('尚未配置')
 })
})

describe('模型设置文案随角色变化（学生不能上传资料，也没有向量设置）',()=>{
 async function viewAs(role:'student'|'teacher'){
  const pinia=createPinia();setActivePinia(pinia)
  useSessionStore(pinia).signIn({access_token:'test-token',token_type:'bearer',expires_in:3600,user:{id:'u1',username:role,role}})
  const api:ModelConfigApi={get:async()=>({runtime_mode:'personal',configured:false}),save:async()=>SAVED,clear:async()=>undefined,test:async()=>({ok:true,latency_ms:1})}
  const wrapper=mount(ModelSettingsView,{global:{plugins:[pinia],provide:{[MODEL_CONFIG_API_KEY as symbol]:api}}});await flushPromises();return wrapper
 }
 it('学生只看到课程问答用途，没有上传/图谱生成措辞',async()=>{
  const wrapper=await viewAs('student')
  const text=wrapper.text()
  expect(text).toContain('用于课程问答')
  expect(wrapper.get('[data-test="mc-status"]').text()).toContain('向课程助教提问')
  expect(text).not.toContain('上传资料')
  expect(text).not.toContain('图谱生成')
 })
 it('教师保留图谱生成与问答用途',async()=>{
  const wrapper=await viewAs('teacher')
  expect(wrapper.text()).toContain('用于知识图谱生成与课程问答')
  expect(wrapper.get('[data-test="mc-status"]').text()).toContain('上传资料生成图谱或提问')
 })
})
