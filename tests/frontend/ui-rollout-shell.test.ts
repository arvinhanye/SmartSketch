import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it } from 'vitest'
import { defineComponent, h } from 'vue'
import { createMemoryHistory } from 'vue-router'
import App from '../../src/frontend/src/App.vue'
import { createAppRouter } from '../../src/frontend/src/router'
import { MODEL_CONFIG_API_KEY } from '../../src/frontend/src/api/modelConfig'
import { useSessionStore } from '../../src/frontend/src/stores/session'
const Page = defineComponent({ render: () => h('p', '内容') })
beforeEach(() => sessionStorage.clear())
async function mountAt(path: string) {
  const pinia = createPinia(); setActivePinia(pinia)
  const session = useSessionStore()
  session.signIn({ access_token: 'test-token', token_type: 'bearer', expires_in: 3600, user: {id:'u1',username:'teacher',role:'teacher'} })
  const router = createAppRouter({ history:createMemoryHistory(),getAccountRole:()=>session.role,coursesComponent:Page,settingsComponent:Page,materialsComponent:Page,membersComponent:Page,reviewComponent:Page,chatComponent:Page,teacherGraphComponent:Page })
  await router.push(path); await router.isReady()
  const wrapper = mount(App, { global: {plugins:[pinia,router],provide:{[MODEL_CONFIG_API_KEY as symbol]:{get:async()=>({runtime_mode:'personal',configured:false})}}} })
  await flushPromises(); return wrapper
}
describe('限定的课程和设置外壳推广', () => {
  it('设置页正确显示当前页与未配置导航状态', async () => {
    const wrapper=await mountAt('/settings/model')
    expect(wrapper.find('.app-topbar').exists()).toBe(true)
    expect(wrapper.get('nav[aria-label="当前位置"] [aria-current="page"]').text()).toBe('模型 API 设置')
    expect(wrapper.get('[data-test="nav-model-settings"]').attributes('aria-current')).toBe('page')
    expect(wrapper.find('[data-test="nav-model-settings-pending"]').exists()).toBe(true)
  })
  it('课程列表仅有一项当前面包屑', async () => {
    const wrapper=await mountAt('/teacher')
    const crumb=wrapper.get('nav[aria-label="当前位置"]')
    expect(crumb.text()).toBe('我的课程')
    expect(crumb.findAll('[aria-current="page"]').length).toBe(1)
  })
  it.each([
    ['/courses/c1/materials','教学资料'],
    ['/courses/c1/members','成员管理'],
    ['/courses/c1/review','审核与发布'],
    ['/courses/c1/chat','课程问答'],
    ['/courses/c1/graph/edit','图谱编辑'],
  ])('其余课程页面 %s 使用统一外壳和正确面包屑',async(path,label)=>{
    const wrapper=await mountAt(path)
    expect(wrapper.find('.app-topbar').exists()).toBe(true)
    expect(wrapper.find('.app-sidebar').exists()).toBe(false)
    expect(wrapper.get('nav[aria-label="当前位置"] [aria-current="page"]').text()).toBe(label)
  })
})
