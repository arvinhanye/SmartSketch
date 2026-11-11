import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { afterEach, vi } from 'vitest'
import { createMemoryHistory } from 'vue-router'
import App from '../../src/frontend/src/App.vue'
import { COURSES_API_KEY, type Course, type CoursesApi } from '../../src/frontend/src/api/courses'
import { INVITE_CODE_API_KEY, type InviteCodeApi } from '../../src/frontend/src/api/inviteCode'
import { MEMBERS_API_KEY, type MembersApi } from '../../src/frontend/src/api/members'
import { PROGRESS_API_KEY, type ProgressApi } from '../../src/frontend/src/api/progress'
import { RECOMMEND_API_KEY, type RecommendApi } from '../../src/frontend/src/api/recommend'
import { createAppRouter } from '../../src/frontend/src/router'
import { useSessionStore } from '../../src/frontend/src/stores/session'
import CoursesView from '../../src/frontend/src/views/CoursesView.vue'
import MembersView from '../../src/frontend/src/views/MembersView.vue'

export const course: Course = { id: 'joined', name: '算法课程', description: null, status: 'published', my_role: 'student', teacher_id: 'teacher', kp_count: 3, published_version: 1, created_at: '2026-11-05T00:00:00Z' }
export const invite = { code: 'ABC234', rotated_at: '2026-11-05T00:00:00Z' }
export const nextInvite = { code: 'XYZ789', rotated_at: '2026-11-05T01:00:00Z' }
export function deferred<T>() {
  let resolve!: (value: T) => void
  let reject!: (reason: unknown) => void
  const promise = new Promise<T>((res, rej) => { resolve = res; reject = rej })
  return { promise, resolve, reject }
}
export function fakeInvite(over: Partial<InviteCodeApi> = {}) {
  return {
    get: vi.fn<InviteCodeApi['get']>(over.get ?? (async () => invite)),
    rotate: vi.fn<InviteCodeApi['rotate']>(over.rotate ?? (async () => nextInvite)),
    join: vi.fn<InviteCodeApi['join']>(over.join ?? (async () => course)),
  }
}
const mounted: Array<{ unmount(): void }> = []
afterEach(() => { mounted.splice(0).forEach((w) => w.unmount()); vi.restoreAllMocks() })

export async function mountInvite(options: {
  role?: 'teacher' | 'student'
  path?: string
  inviteApi?: ReturnType<typeof fakeInvite> | null
  courses?: Partial<CoursesApi>
  members?: Partial<MembersApi>
  resume?: boolean
} = {}) {
  sessionStorage.clear()
  const pinia = createPinia()
  setActivePinia(pinia)
  const session = useSessionStore(pinia)
  const role = options.role ?? 'student'
  const signIn = (token = 'session-one', nextRole = role) => session.signIn({ access_token: token, token_type: 'bearer', expires_in: 3600, user: { id: nextRole, username: nextRole, role: nextRole } })
  signIn()
  const inviteApi = options.inviteApi === undefined ? fakeInvite() : options.inviteApi
  const courses = {
    list: vi.fn<CoursesApi['list']>(options.courses?.list ?? (async () => [])),
    get: vi.fn<CoursesApi['get']>(options.courses?.get ?? (async (cid) => ({ ...course, id: cid, my_role: role }))),
    create: vi.fn<CoursesApi['create']>(options.courses?.create ?? (async () => course)),
  }
  const members: MembersApi = {
    list: options.members?.list ?? (async () => [{ user_id: 'teacher', username: 'teacher', role: 'teacher', created_at: course.created_at }]),
    add: options.members?.add ?? (async () => { throw new Error('not used') }),
    remove: options.members?.remove ?? (async () => undefined),
  }
  const progress: ProgressApi = { get: async () => ({ graph_version: 1, entries: [] }), update: async () => ({ graph_version: 1, entries: [] }) }
  const recommend: RecommendApi = { get: async () => ({ state: 'all_mastered', graph_version: 1, total_eligible: 0, recommendations: [] }) }
  const router = createAppRouter({ history: createMemoryHistory(), getAccountRole: () => session.role, coursesComponent: CoursesView, membersComponent: MembersView, ...(options.resume ? { studentGraphComponent: { render: () => null } } : {}) })
  await router.push(options.path ?? (role === 'student' ? '/student' : '/courses/c1/members'))
  await router.isReady()
  const wrapper = mount(App, { attachTo: document.body, global: {
    plugins: [pinia, router], provide: {
      [COURSES_API_KEY as symbol]: courses, [MEMBERS_API_KEY as symbol]: members,
      ...(inviteApi === null ? {} : { [INVITE_CODE_API_KEY as symbol]: inviteApi }),
      ...(options.resume ? { [PROGRESS_API_KEY as symbol]: progress, [RECOMMEND_API_KEY as symbol]: recommend } : {}),
    },
  } })
  mounted.push(wrapper)
  await flushPromises()
  return { wrapper, router, session, signIn, api: inviteApi!, courses }
}
export async function submitCode(h: Awaited<ReturnType<typeof mountInvite>>, code = 'ABC234') {
  await h.wrapper.get('[data-test="course-join-code"]').setValue(code)
  await h.wrapper.get('[data-test="course-join"]').trigger('submit')
}
