import { mount } from '@vue/test-utils'
import { effectScope, nextTick, ref, type EffectScope } from 'vue'
import { afterEach, expect, it, vi } from 'vitest'
import { createKnowledgeDetailApi } from '../../src/frontend/src/api/knowledgeDetail'
import { ApiError, createHttpClient, type FetchLike } from '../../src/frontend/src/api/http'

function impact(id: string, token = 'a'.repeat(64)) {
  return { root_id: id, root_name: id.toUpperCase(), root_revision: 1, cascade: true, deleted_count: 2, relation_count: 1,
    preview_token: token, nodes: [{ id, name: id.toUpperCase(), depth: 0 }, { id: `${id}-child`, name: 'Child', depth: 1 }], retained: [] }
}
function deferred<T>() {
  let resolve!: (value: T) => void
  let reject!: (reason: unknown) => void
  const promise = new Promise<T>((a, b) => { resolve = a; reject = b })
  return { promise, resolve, reject }
}
const scopes: EffectScope[] = []
afterEach(() => { scopes.splice(0).forEach(scope => scope.stop()) })
async function setup(overrides = {}) {
  const { useNodeDeletion } = await import('../../src/frontend/src/composables/useNodeDeletion')
  const api = { deleteImpact: vi.fn(async (_cid: string, kid: string) => impact(kid)), remove: vi.fn(async () => null), ...overrides }
  const courseId = ref<string | null>('c1')
  const identity = ref<string | null>('teacher')
  const selectedId = ref<string | null>('a')
  const onDeleted = vi.fn()
  const onCourseForbidden = vi.fn()
  const scope = effectScope(); scopes.push(scope)
  const flow = scope.run(() => useNodeDeletion({ api, courseId, identity, selectedId, onDeleted, onCourseForbidden }))!
  return { flow, api, courseId, identity, selectedId, onDeleted, onCourseForbidden, scope }
}

it('sends preview and cascade token as query parameters while default remove remains single', async () => {
  const requests: Array<{ url: string; method: string }> = []
  const fetch: FetchLike = async (url, init) => {
    requests.push({ url: String(url), method: init?.method ?? 'GET' })
    return String(url).includes('cascade=false') ? new Response(null, { status: 204 })
      : new Response(JSON.stringify(impact('a')), { status: 200 })
  }
  const api = createKnowledgeDetailApi(createHttpClient({ fetch }))
  expect((await api.deleteImpact('c1', 'a')).root_id).toBe('a')
  await api.remove('c1', 'a', { cascade: true, expectedRevision: 7, previewToken: 'a'.repeat(64) })
  expect(await api.remove('c1', 'a', { expectedRevision: 7 })).toBeNull()
  expect(await api.remove('c1', 'a')).toBeNull()
  expect(requests).toEqual([
    { url: '/api/v1/courses/c1/kp/a/delete-impact', method: 'GET' },
    { url: `/api/v1/courses/c1/kp/a?cascade=true&expected_revision=7&preview_token=${'a'.repeat(64)}`, method: 'DELETE' },
    { url: '/api/v1/courses/c1/kp/a?cascade=false&expected_revision=7', method: 'DELETE' },
    { url: '/api/v1/courses/c1/kp/a?cascade=false', method: 'DELETE' },
  ])
})

it('late preview A cannot replace newer preview B or its delete target', async () => {
  const a = deferred<ReturnType<typeof impact>>()
  const b = deferred<ReturnType<typeof impact>>()
  const x = await setup({ deleteImpact: vi.fn((_cid: string, kid: string) => kid === 'a' ? a.promise : b.promise) })
  const p1 = x.flow.open('a'); const p2 = x.flow.open('b')
  b.resolve(impact('b')); await p2
  a.resolve(impact('a')); await p1
  expect(x.flow.kpId.value).toBe('b')
  expect(x.flow.impact.value?.root_id).toBe('b')
  await x.flow.confirm(true)
  expect(x.api.remove).toHaveBeenCalledWith('c1', 'b', expect.objectContaining({ cascade: true, expectedRevision: 1, previewToken: 'a'.repeat(64) }))
})

it.each(['close', 'course', 'selection', 'identity', 'dispose'])('%s invalidates a pending preview', async (action) => {
  const pending = deferred<ReturnType<typeof impact>>()
  const x = await setup({ deleteImpact: vi.fn(() => pending.promise) })
  const loading = x.flow.open('a')
  if (action === 'close') x.flow.close()
  if (action === 'course') x.courseId.value = 'c2'
  if (action === 'selection') x.selectedId.value = 'b'
  if (action === 'identity') x.identity.value = null
  if (action === 'dispose') x.scope.stop()
  await nextTick()
  pending.resolve(impact('a')); await loading
  expect(x.flow.impact.value).toBeNull()
  expect(await x.flow.confirm(true)).toBe(false)
  expect(x.api.remove).not.toHaveBeenCalled()
})

it('blocks confirmation until preview succeeds and sends only one in-flight delete', async () => {
  const pending = deferred<ReturnType<typeof impact>>()
  const deleting = deferred<null>()
  const x = await setup({ deleteImpact: vi.fn(() => pending.promise), remove: vi.fn(() => deleting.promise) })
  const opening = x.flow.open('a')
  expect(await x.flow.confirm(true)).toBe(false)
  pending.resolve(impact('a')); await opening
  const first = x.flow.confirm(true)
  expect(await x.flow.confirm(true)).toBe(false)
  expect(x.api.remove).toHaveBeenCalledTimes(1)
  deleting.resolve(null); await first
  expect(x.onDeleted).toHaveBeenCalledTimes(1)
})

it('stale preview is refreshed and requires another explicit confirmation', async () => {
  const x = await setup()
  await x.flow.open('a')
  x.api.remove.mockRejectedValueOnce(new ApiError(409, { code: 'REVISION_CONFLICT', message: 'private', details: { reason: 'deletion_preview_stale' } }))
  x.api.deleteImpact.mockResolvedValueOnce(impact('a', 'b'.repeat(64)))
  expect(await x.flow.confirm(true)).toBe(false)
  expect(x.api.remove).toHaveBeenCalledTimes(1)
  expect(x.flow.impact.value?.preview_token).toBe('b'.repeat(64))
  expect(x.flow.error.value).toContain('重新确认')
  await x.flow.confirm(true)
  expect(x.api.remove).toHaveBeenLastCalledWith('c1', 'a', expect.objectContaining({ previewToken: 'b'.repeat(64) }))
})

it('single-node revision conflict refreshes the preview but requires a new confirmation', async () => {
  const x = await setup()
  await x.flow.open('a')
  x.api.remove.mockRejectedValueOnce(new ApiError(409, { code: 'REVISION_CONFLICT', message: 'changed' }))
  x.api.deleteImpact.mockResolvedValueOnce({ ...impact('a', 'b'.repeat(64)), root_revision: 2 })
  expect(await x.flow.confirm()).toBe(false)
  expect(x.api.remove).toHaveBeenCalledTimes(1)
  expect(x.api.remove).toHaveBeenLastCalledWith('c1', 'a', expect.objectContaining({ cascade: false, expectedRevision: 1 }))
  expect(x.flow.impact.value?.root_revision).toBe(2)
  expect(x.flow.error.value).toContain('重新确认')
  expect(x.onDeleted).not.toHaveBeenCalled()
  expect(await x.flow.confirm()).toBe(true)
  expect(x.api.remove).toHaveBeenCalledTimes(2)
  expect(x.api.remove).toHaveBeenLastCalledWith('c1', 'a', expect.objectContaining({ cascade: false, expectedRevision: 2 }))
  expect(x.onDeleted).toHaveBeenCalledTimes(1)
})

it('uncertain network outcome blocks another write until a fresh preview', async () => {
  const x = await setup()
  await x.flow.open('a')
  x.api.remove.mockRejectedValueOnce(new Error('network'))
  expect(await x.flow.confirm(true)).toBe(false)
  expect(x.flow.impact.value).toBeNull()
  expect(await x.flow.confirm(true)).toBe(false)
  expect(x.api.remove).toHaveBeenCalledTimes(1)
})

it('course change during deletion never applies success callback to the next course', async () => {
  const pending = deferred<null>()
  const x = await setup({ remove: vi.fn(() => pending.promise) })
  await x.flow.open('a')
  const deleting = x.flow.confirm(true)
  x.courseId.value = 'c2'; await nextTick()
  pending.resolve(null); await deleting
  expect(x.onDeleted).not.toHaveBeenCalled()
})

it('confirmation defaults to single-node deletion and needs explicit cascade choice', async () => {
  const { default: Dialog } = await import('../../src/frontend/src/components/NodeDeletionConfirm.vue')
  const wrapper = mount(Dialog, { props: { status: 'ready', impact: impact('a'), error: null, name: 'A' } })
  await wrapper.get('[data-test="nd-confirm"]').trigger('click')
  expect(wrapper.emitted('confirm')).toEqual([[false]])
  await wrapper.get('[data-test="nd-cascade"]').setValue(true)
  await wrapper.get('[data-test="nd-confirm"]').trigger('click')
  expect(wrapper.emitted('confirm')).toEqual([[false], [true]])
  await wrapper.setProps({ status: 'loading', impact: null })
  expect(wrapper.get('[data-test="nd-confirm"]').attributes('disabled')).toBeDefined()
  wrapper.unmount()
})
