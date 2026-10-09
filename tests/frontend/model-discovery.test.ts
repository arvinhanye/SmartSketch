import { mount, flushPromises } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { afterEach, expect, it, vi } from 'vitest'
import { MODEL_CONFIG_API_KEY, type ModelConfigApi } from '../../src/frontend/src/api/modelConfig'
import ModelSettingsView from '../../src/frontend/src/views/ModelSettingsView.vue'
let wrapper: ReturnType<typeof mount>
afterEach(()=>{wrapper?.unmount();vi.useRealTimers()})
async function setup(discover: any) {
 const api:ModelConfigApi={get:async()=>({runtime_mode:'personal',configured:false}),save:vi.fn(),clear:async()=>{},test:async()=>({ok:true,latency_ms:1}),discover}
 wrapper=mount(ModelSettingsView,{global:{plugins:[createPinia()],provide:{[MODEL_CONFIG_API_KEY as symbol]:api}}});await flushPromises();return api
}
it('provider presets, debounced discovery, selection and free input',async()=>{
 vi.useFakeTimers();const discover=vi.fn().mockResolvedValue({ok:true,models:['model-a','model-b']});await setup(discover)
 await wrapper.get('[data-test="mc-provider"]').setValue('deepseek')
 expect((wrapper.get('[data-test="mc-base-url"]').element as HTMLInputElement).value).toBe('https://api.deepseek.com')
 await wrapper.get('[data-test="mc-api-key"]').setValue('fake-key');await vi.advanceTimersByTimeAsync(800);await flushPromises()
 expect(discover).toHaveBeenCalledTimes(1);expect(discover.mock.calls[0][0]).toEqual({base_url:'https://api.deepseek.com',api_key:'fake-key'})
 await wrapper.get('[data-test="mc-model-toggle"]').trigger('click');await wrapper.findAll('[role=option]')[1]!.trigger('click');expect((wrapper.get('[data-test="mc-model"]').element as HTMLInputElement).value).toBe('model-b')
 await wrapper.get('[data-test="mc-model"]').setValue('custom-model');expect((wrapper.get('[data-test="mc-model"]').element as HTMLInputElement).value).toBe('custom-model')
})
it('switching provider clears keys and discards late results',async()=>{
 let finish!:(v:any)=>void;const discover=vi.fn(()=>new Promise(r=>{finish=r}));await setup(discover)
 await wrapper.get('[data-test="mc-provider"]').setValue('deepseek');await wrapper.get('[data-test="mc-api-key"]').setValue('fake-key');await wrapper.get('[data-test="mc-refresh-models"]').trigger('click')
 await wrapper.get('[data-test="mc-provider"]').setValue('openai');finish({ok:true,models:['old-model']});await flushPromises()
 expect((wrapper.get('[data-test="mc-api-key"]').element as HTMLInputElement).value).toBe('');expect(wrapper.find('[data-test="mc-model-select"]').exists()).toBe(false)
})
it('unavailable directory keeps manual input and hides provider error text',async()=>{
 const discover=vi.fn().mockRejectedValue(new Error('SECRET-UPSTREAM'));await setup(discover)
 await wrapper.get('[data-test="mc-provider"]').setValue('deepseek');await wrapper.get('[data-test="mc-api-key"]').setValue('fake-key');await wrapper.get('[data-test="mc-refresh-models"]').trigger('click');await flushPromises()
 expect(wrapper.text()).toContain('手动');expect(wrapper.text()).not.toContain('SECRET-UPSTREAM');await wrapper.get('[data-test="mc-model"]').setValue('manual-model')
})
import { useRuntimeStore } from '../../src/frontend/src/stores/runtime'
it('a session change aborts the directory and ignores its response',async()=>{
 let finish!:(v:any)=>void;let signal:AbortSignal|undefined
 await setup((_:any,control:any)=>{signal=control.signal;return new Promise(r=>{finish=r})})
 await wrapper.get('[data-test="mc-provider"]').setValue('deepseek');await wrapper.get('[data-test="mc-api-key"]').setValue('fake-key');await wrapper.get('[data-test="mc-refresh-models"]').trigger('click')
 useRuntimeStore().startSession('different-user');expect(signal?.aborted).toBe(true);finish({ok:true,models:['old-user-model']});await flushPromises()
 expect(wrapper.find('[data-test="mc-model-select"]').exists()).toBe(false)
})
it('free-form model names remain the value sent when saving',async()=>{
 const api=await setup(vi.fn().mockResolvedValue({ok:true,models:['listed-model']}))
 vi.mocked(api.save).mockResolvedValue({runtime_mode:'personal',configured:true,base_url:'https://api.deepseek.com',model:'manual-model',key_hint:'fake',version:1,updated_at:'2026-10-08T00:00:00Z'})
 await wrapper.get('[data-test="mc-provider"]').setValue('deepseek');await wrapper.get('[data-test="mc-api-key"]').setValue('fake-key');await wrapper.get('[data-test="mc-model"]').setValue('manual-model');await wrapper.get('form').trigger('submit');await flushPromises()
 expect(api.save).toHaveBeenCalledWith(expect.objectContaining({model:'manual-model',api_key:'fake-key'}),expect.anything())
})
it('discovery preserves key validation used by save and test',async()=>{
 const discover=vi.fn().mockResolvedValue({ok:false,models:[],error_class:'auth'});await setup(discover)
 await wrapper.get('[data-test="mc-provider"]').setValue('deepseek');await wrapper.get('[data-test="mc-api-key"]').setValue(' fake-key ');await wrapper.get('[data-test="mc-refresh-models"]').trigger('click');await flushPromises()
 expect(discover.mock.calls[0][0].api_key).toBe(' fake-key ')
})

it('one model input filters matches, expands all and preserves manual names',async()=>{
 await setup(vi.fn().mockResolvedValue({ok:true,models:['alpha-chat','alpha-vector','beta-chat']}))
 await wrapper.get('[data-test=mc-provider]').setValue('deepseek')
 await wrapper.get('[data-test=mc-api-key]').setValue('fake-key')
 await wrapper.get('[data-test=mc-refresh-models]').trigger('click');await flushPromises()
 await wrapper.get('[data-test=mc-model]').setValue('alpha')
 expect(wrapper.findAll('[role=option]').map(w=>w.text())).toEqual(['alpha-chat','alpha-vector'])
 await wrapper.get('[data-test=mc-model-toggle]').trigger('click')
 expect(wrapper.findAll('[role=option]').map(w=>w.text())).toEqual(['alpha-chat','alpha-vector','beta-chat'])
 await wrapper.findAll('[role=option]')[2]!.trigger('click')
 expect((wrapper.get('[data-test=mc-model]').element as HTMLInputElement).value).toBe('beta-chat')
 expect(wrapper.find('[role=listbox]').exists()).toBe(false)
 await wrapper.get('[data-test=mc-model]').setValue('manual-unlisted')
 expect(wrapper.text()).toContain('manual-unlisted')
 expect(wrapper.findAll('input[role=combobox]')).toHaveLength(1)
})
it('model picker supports arrow selection, Enter and Escape',async()=>{
 await setup(vi.fn().mockResolvedValue({ok:true,models:['alpha','beta']}))
 await wrapper.get('[data-test=mc-provider]').setValue('deepseek');await wrapper.get('[data-test=mc-api-key]').setValue('fake-key')
 await wrapper.get('[data-test=mc-refresh-models]').trigger('click');await flushPromises()
 const input=wrapper.get('[data-test=mc-model]');await input.setValue('')
 await input.trigger('keydown',{key:'ArrowDown'});await input.trigger('keydown',{key:'ArrowDown'});await input.trigger('keydown',{key:'Enter'})
 expect((input.element as HTMLInputElement).value).toBe('beta')
 await wrapper.get('[data-test=mc-model-toggle]').trigger('click');await input.trigger('keydown',{key:'Escape'})
 expect(input.attributes('aria-expanded')).toBe('false')
})
