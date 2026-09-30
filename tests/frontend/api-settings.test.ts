import { afterEach, describe, expect, it, vi } from 'vitest'
import { mount, flushPromises, type VueWrapper } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { createRouter, createMemoryHistory } from 'vue-router'
import ApiSettings from '../../src/frontend/src/views/ApiSettings.vue'

let wrapper: VueWrapper | undefined
const calls: { path: string; body: Record<string, unknown> }[] = []
const empty = { LLM_MODE: 'demo', LLM_BASE_URL: '', LLM_CHAT_MODEL: '', LLM_EXTRACTION_MODEL: '', LLM_PROVIDER_LABEL: '', EMBEDDING_MODE: 'demo', EMBEDDING_BASE_URL: '', EMBEDDING_MODEL: '', EMBEDDING_PROVIDER_LABEL: '', EMBEDDING_DIMENSIONS: 1024, LLM_API_KEY_configured: false, EMBEDDING_API_KEY_configured: false }
async function setup(failure = false) {
  calls.length = 0
  vi.stubGlobal('fetch', vi.fn(async (path: string, options: RequestInit) => {
    const body = options.body ? JSON.parse(options.body as string) : {}
    calls.push({ path, body })
    const result = path.endsWith('/models')
      ? { kind: body.kind, ok: true, models: ['identified-model'], count: 1, latency_ms: 12, provider: 'https://test.invalid/v1', error: null }
      : path.endsWith('/test')
        ? { kind: body.kind, ok: !failure, latency_ms: 37, http_status: failure ? 401 : 200, detail: { model: 'selected-model' }, provider: 'https://test.invalid/v1', error: failure ? '服务商返回 HTTP 401，请核对密钥、地区、模型与额度' : null }
        : empty
    return { ok: true, status: 200, json: async () => result }
  }))
  const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/', component: { template: '<div />' } }] })
  await router.push('/')
  wrapper = mount(ApiSettings, { attachTo: document.body, global: { plugins: [createPinia(), router] } })
  await flushPromises()
  return wrapper
}
afterEach(() => { wrapper?.unmount(); document.body.innerHTML = ''; vi.unstubAllGlobals() })
describe('api-settings', () => {
  it('does not prefill any model', async () => {
    const page = await setup()
    expect(['chat-model', 'extraction-model', 'embedding-model'].map(name => (page.get(`[data-test="${name}"]`).element as HTMLInputElement).value)).toEqual(['', '', ''])
  })
  it('discovers each interface with its own kind', async () => {
    const page = await setup()
    for (const kind of ['llm', 'embedding']) { await page.get(`[data-kind="${kind}"] .discovery-row button`).trigger('click'); await flushPromises() }
    expect(calls.filter(call => call.path.endsWith('/models')).map(call => call.body.kind)).toEqual(['llm', 'embedding'])
  })
  it('shows one independent result dialog with latency', async () => {
    const page = await setup()
    await page.get('[data-kind="llm"] .test-actions button').trigger('click'); await flushPromises()
    const dialog = document.querySelector('.dialog')
    expect([document.querySelectorAll('.dialog').length, dialog?.textContent?.includes('37 ms'), dialog?.getAttribute('aria-label')]).toEqual([1, true, '大模型接口测试结果'])
  })
  it('shows the provider failure reason', async () => {
    const page = await setup(true)
    await page.get('[data-kind="llm"] .test-actions button').trigger('click'); await flushPromises()
    expect(document.querySelector('.dialog')?.textContent).toContain('HTTP 401')
  })
})
