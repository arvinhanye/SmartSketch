import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { computed, defineComponent, h, ref } from 'vue'
import { expect, test, vi } from 'vitest'
import { useCourses } from '../../src/frontend/src/composables/useCourses'
import { useSessionStore } from '../../src/frontend/src/stores/session'

function deferred<T>() { let resolve!: (v:T)=>void;const promise=new Promise<T>(r=>resolve=r);return {promise,resolve} }
const detail = {id:'private-course-a',name:'A 私有待建课',status:'draft' as const,my_role:'teacher' as const,created_at:'2026-10-03T00:00:00Z'}
function signIn(session:ReturnType<typeof useSessionStore>,id:string) { session.signIn({ access_token:'token-'+id,token_type:'bearer',expires_in:3600,user:{id,username:id,role:'teacher'} }) }

test('same mounted course list account change ignores old creation result', async()=>{
 sessionStorage.clear();const pinia=createPinia();setActivePinia(pinia);const session=useSessionStore(pinia);signIn(session,'a')
 const pending=deferred<typeof detail>(); const api={list:vi.fn(async()=>[]),get:vi.fn(),create:vi.fn(()=>pending.promise)}
 let state!:ReturnType<typeof useCourses>
 const wrapper=mount(defineComponent({setup(){state=useCourses({api,courseId:ref(null),sessionKey:computed(()=>session.accessToken),canCreate:computed(()=>session.role==='teacher'),onCourseForbidden:vi.fn()});return()=>h('div')}}),{global:{plugins:[pinia]}})
 await flushPromises(); state.form.value.name='A 私有待建课'; const creating=state.createCourse(); signIn(session,'b');await flushPromises();expect(state.courses.value).toEqual([])
 pending.resolve(detail);await creating;await flushPromises()
 expect(state.courses.value).toEqual([]);expect(state.createdName.value).toBeNull();wrapper.unmount()
})


test('旧创建 finally 与失败不解锁或报错到新会话的新创建', async () => {
  sessionStorage.clear()
  const pinia = createPinia(); setActivePinia(pinia)
  const session = useSessionStore(pinia); signIn(session, 'a')
  let rejectOld!: (reason: unknown) => void
  const old = new Promise<typeof detail>((_, reject) => { rejectOld = reject })
  const next = deferred<typeof detail>()
  const api = {list: vi.fn(async () => []), get: vi.fn(), create: vi.fn().mockReturnValueOnce(old).mockReturnValueOnce(next.promise)}
  let state!: ReturnType<typeof useCourses>
  const wrapper = mount(defineComponent({setup() {
    state = useCourses({api, courseId: ref(null), sessionKey: computed(() => session.accessToken), canCreate: computed(() => session.role === 'teacher'), onCourseForbidden: vi.fn()})
    return () => h('div')
  }}), {global: {plugins: [pinia]}})
  await flushPromises()
  state.form.value.name = 'old'; const first = state.createCourse()
  signIn(session, 'b'); await flushPromises()
  expect(state.form.value.name).toBe('')
  state.form.value.name = 'new'; const second = state.createCourse()
  rejectOld(new Error('old failure')); await first
  expect(state.creating.value).toBe(true)
  expect(state.createError.value).toBeNull()
  expect(state.form.value.name).toBe('new')
  next.resolve({...detail, id:'b-course', name:'new'}); await second
  expect(state.courses.value.map(c => c.id)).toEqual(['b-course'])
  expect(state.creating.value).toBe(false)
  wrapper.unmount()
})


import { useChat } from '../../src/frontend/src/composables/useChat'
import { useCourseStore } from '../../src/frontend/src/stores/course'
import type { ChatStreamClient } from '../../src/frontend/src/api/chatStream'

test('SPA 切课后旧问答 delta/done 不污染新课正文、引用和历史', async () => {
  const pinia = createPinia(); setActivePinia(pinia)
  const cid = ref<string | null>('course-a')
  const pending = deferred<Awaited<ReturnType<ChatStreamClient['send']>>>()
  let oldEvents: Parameters<ChatStreamClient['send']>[2]
  const client: ChatStreamClient = {
    send: vi.fn((_cid, _body, control) => { oldEvents = control; return pending.promise }),
  }
  let chat!: ReturnType<typeof useChat>
  const wrapper = mount(defineComponent({setup() {chat = useChat(client, cid); return () => h('div')}}), {global: {plugins: [pinia]}})
  const oldRequest = chat.ask('A 的问题')
  cid.value = 'course-b'; await flushPromises()
  expect(oldEvents?.signal?.aborted).toBe(true)
  oldEvents?.onEvent?.({kind:'delta', data:{event:'delta', delta:'A 的秘密'}})
  pending.resolve({kind:'done', final:{status:'answered', answer:'A 的秘密[1]', graph_version:1, request_id:'a', related_kp_ids:['kp-a'], citations:[{index:1,chunk_id:'k-a',document_id:'m-a',document_name:'A.pdf',page:1,text:'A 原文'}]}})
  await oldRequest
  expect(chat.entries.value).toEqual([])
  expect(useCourseStore(pinia).courseId).toBe('course-b')
  expect(useCourseStore(pinia).chatHistory).toEqual([])
  expect(chat.sending.value).toBe(false)
  wrapper.unmount()
})
