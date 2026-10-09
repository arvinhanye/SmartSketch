import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, afterEach, describe, expect, it, vi } from 'vitest'
import { defineComponent, h } from 'vue'
import { createMemoryHistory } from 'vue-router'
import { COURSES_API_KEY, type CoursesApi, type Course } from '../../src/frontend/src/api/courses'
import { createAppRouter } from '../../src/frontend/src/router'
import { useSessionStore } from '../../src/frontend/src/stores/session'
import CoursesView from '../../src/frontend/src/views/CoursesView.vue'
const course: Course = {id:'c1',name:'数据结构',description:'栈与队列',status:'published',my_role:'teacher',teacher_id:'u1',kp_count:24,published_version:2,created_at:'2026-10-01T00:00:00Z'}
const Page=defineComponent({render:()=>h('p','页面')})
beforeEach(()=>sessionStorage.clear())
afterEach(()=>vi.restoreAllMocks())
async function mountView(options: { role?: 'teacher'|'student'; path?: string; overrides?: Partial<CoursesApi> }={}) {
 const pinia=createPinia();setActivePinia(pinia)
 const role=options.role??'teacher'; const session=useSessionStore()
 session.signIn({access_token:'test-token',token_type:'bearer',expires_in:3600,user:{id:'u1',username:'test-user',role}})
 const api: CoursesApi={list:async()=>[course],get:async()=>course,create:async body=>({...course,id:'c2',name:body.name}),...options.overrides}
 const router=createAppRouter({history:createMemoryHistory(),getAccountRole:()=>session.role,coursesComponent:CoursesView,studentGraphComponent:Page,teacherGraphComponent:Page,materialsComponent:Page,reviewComponent:Page,membersComponent:Page,chatComponent:Page})
 await router.push(options.path??(role==='teacher'?'/teacher':'/student')); await router.isReady()
 const wrapper=mount(CoursesView,{attachTo:document.body,global:{plugins:[pinia,router],provide:{[COURSES_API_KEY as symbol]:api}}});await flushPromises()
 return {wrapper,router}
}
describe('课程页面的行列表与创建面板',()=>{
 it('教师展开与取消面板，并将焦点还给开关',async()=>{
  const {wrapper}=await mountView()
  expect(wrapper.find('[data-test="course-create"]').exists()).toBe(false)
  const open=wrapper.get('[data-test="course-create-open"]');await open.trigger('click');await flushPromises()
  expect(document.activeElement).toBe(wrapper.get('input[name="name"]').element)
  await wrapper.get('[data-test="course-create-cancel"]').trigger('click');await flushPromises()
  expect(wrapper.find('[data-test="course-create"]').exists()).toBe(false);expect(document.activeElement).toBe(open.element)
 })
 it('创建成功后收起且新增课程、提示仍可见',async()=>{
  const {wrapper}=await mountView();await wrapper.get('[data-test="course-create-open"]').trigger('click')
  await wrapper.get('input[name="name"]').setValue('算法课程');await wrapper.get('[data-test="course-create"]').trigger('submit');await flushPromises()
  expect(wrapper.find('[data-test="course-create"]').exists()).toBe(false)
  expect(wrapper.get('[data-test="create-success"]').text()).toContain('算法课程')
  expect(wrapper.findAll('[data-test="course-card"]')[0]!.text()).toContain('算法课程')
 })
 it('创建失败不关闭面板，显示固定错误',async()=>{
  const {wrapper}=await mountView({overrides:{create:async()=>{throw new Error('private-response')}}})
  await wrapper.get('[data-test="course-create-open"]').trigger('click');await wrapper.get('input[name="name"]').setValue('算法')
  await wrapper.get('[data-test="course-create"]').trigger('submit');await flushPromises()
  expect(wrapper.find('[data-test="course-create"]').exists()).toBe(true)
  expect(wrapper.get('[data-test="create-error"]').text()).toContain('创建课程失败');expect(wrapper.text()).not.toContain('private-response')
 })
 it('请求未完成时不能取消或重复提交',async()=>{
  let resolve!: (v:Course)=>void;let calls=0
  const {wrapper}=await mountView({overrides:{create:()=>{calls++;return new Promise(r=>{resolve=r})}}})
  await wrapper.get('[data-test="course-create-open"]').trigger('click');await wrapper.get('input[name="name"]').setValue('算法')
  await wrapper.get('[data-test="course-create"]').trigger('submit')
  expect(wrapper.get('[data-test="course-create-cancel"]').attributes('disabled')).toBeDefined()
  await wrapper.get('[data-test="course-create"]').trigger('submit');expect(calls).toBe(1)
  resolve({...course,id:'new',name:'算法'});await flushPromises()
 })
 it('课程整行链接包含说明和状态并可导航',async()=>{
  const {wrapper,router}=await mountView();const row=wrapper.get('[data-test="course-card"] a')
  expect(row.text()).toContain('栈与队列');expect(row.text()).toContain('已发布');expect(row.text()).toContain('v2');expect(row.text()).toContain('24')
  await row.trigger('click');await flushPromises();expect(router.currentRoute.value.path).toBe('/courses/c1')
 })
 it('教师账号在课程中作为学生时仅显示学生入口',async()=>{
  const {wrapper}=await mountView({path:'/courses/c1',overrides:{get:async()=>({...course,my_role:'student'})}})
  expect(wrapper.find('[data-test="student-graph-link"]').exists()).toBe(true)
  expect(wrapper.find('[data-test="teacher-graph-link"]').exists()).toBe(false)
  expect(wrapper.find('[data-test="materials-link"]').exists()).toBe(false)
  expect(wrapper.find('[data-test="course-next-action"]').exists()).toBe(true)
 })
 it('学生空态可复制自己的用户名，拒绝时有反馈',async()=>{
  Object.defineProperty(navigator,'clipboard',{configurable:true,value:{writeText:async(value:string)=>{expect(value).toBe('test-user');throw new Error('denied')}}})
  const {wrapper}=await mountView({role:'student',overrides:{list:async()=>[]}})
  expect(wrapper.find('[data-test="course-create-open"]').exists()).toBe(false)
  await wrapper.get('[data-test="course-copy-username"]').trigger('click');await flushPromises()
  expect(wrapper.get('[data-test="course-copy-status"]').text()).toContain('请手动复制')
 })
 it('换号后清除复制反馈且忽略旧剪贴板请求',async()=>{
  let reject!: (reason:Error)=>void
  Object.defineProperty(navigator,'clipboard',{configurable:true,value:{writeText:()=>new Promise<void>((_,r)=>{reject=r})}})
  const {wrapper}=await mountView({role:'student',overrides:{list:async()=>[]}})
  await wrapper.get('[data-test="course-copy-username"]').trigger('click')
  const session=useSessionStore()
  session.signIn({access_token:'second-token',token_type:'bearer',expires_in:3600,user:{id:'u2',username:'second-user',role:'student'}})
  await flushPromises();reject(new Error('denied'));await flushPromises()
  expect(wrapper.text()).not.toContain('test-user')
  expect(wrapper.find('[data-test="course-copy-status"]').exists()).toBe(false)
  Object.defineProperty(navigator,'clipboard',{configurable:true,value:{writeText:async()=>{throw new Error('denied')}}})
  await wrapper.get('[data-test="course-copy-username"]').trigger('click');await flushPromises()
  expect(wrapper.get('[data-test="course-copy-status"]').text()).toContain('second-user')
  session.signIn({access_token:'third-token',token_type:'bearer',expires_in:3600,user:{id:'u3',username:'third-user',role:'student'}})
  await flushPromises();expect(wrapper.find('[data-test="course-copy-status"]').exists()).toBe(false)
 })

})
