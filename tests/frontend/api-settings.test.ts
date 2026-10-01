import { afterEach, describe, expect, it, vi } from 'vitest'
import { mount, flushPromises, type VueWrapper } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { createRouter, createMemoryHistory } from 'vue-router'
import ApiSettings from '../../src/frontend/src/views/ApiSettings.vue'

let wrapper: VueWrapper | undefined
const calls: { method: string; path: string; body: Record<string, unknown> }[] = []

const saved = {
  LLM_MODE: 'demo', LLM_BASE_URL: 'https://saved.invalid/v1', LLM_CHAT_MODEL: 'deepseek-flash', LLM_EXTRACTION_MODEL: 'deepseek-flash',
  LLM_PROVIDER_LABEL: '', EMBEDDING_MODE: 'demo', EMBEDDING_BASE_URL: '', EMBEDDING_MODEL: '', EMBEDDING_DIMENSIONS: 1024,
  EMBEDDING_PROVIDER_LABEL: '', LLM_API_KEY_configured: true, EMBEDDING_API_KEY_configured: false,
  active: { LLM_MODE: 'live', EMBEDDING_MODE: 'demo', EMBEDDING_MODEL: '' },
}

/** 接口返回：两个带展示名的模型 + 一个只有 ID 的模型，用于验证「ID 与名称分开」 */
const MODEL_OPTIONS = [
  { id: 'deepseek-flash', name: 'DeepSeek-V4.1-Flash' },
  { id: 'deepseek-pro', name: 'DeepSeek-V4-Pro' },
  { id: 'deepseek-plain', name: '' },
]

/** 向量模型候选与能力：一个多档可选、一个固定维度、一个能力未知 */
const EMBEDDING_OPTIONS = [
  { id: 'text-embedding-v4', name: '通义 text-embedding-v4' },
  { id: 'text-embedding-v3', name: '通义 text-embedding-v3' },
  { id: 'my-private-embedding', name: '' },
]

const CAPABILITIES: Record<string, Record<string, unknown>> = {
  'text-embedding-v4': { known: true, model: 'text-embedding-v4', dimensions: [64, 256, 768, 1024, 1536, 2048], default: 1024, flexible: 'flexible', label: '通义 text-embedding-v4', source: 'https://www.alibabacloud.com/help/en/model-studio/embedding-rerank-model/' },
  'text-embedding-v3': { known: true, model: 'text-embedding-v3', dimensions: [1024], default: 1024, flexible: 'fixed', label: '通义 text-embedding-v3', source: 'https://www.alibabacloud.com/help/en/model-studio/embedding-rerank-model/' },
  'my-private-embedding': { known: false, model: 'my-private-embedding', dimensions: [], default: null, flexible: 'unknown', label: '', source: '' },
}

async function setup(failure = false) {
  calls.length = 0
  vi.stubGlobal('fetch', vi.fn(async (path: string, options: RequestInit = {}) => {
    const body = options.body ? JSON.parse(options.body as string) : {}
    calls.push({ method: options.method ?? 'GET', path, body })
    if (path.endsWith('/models')) {
      const options = body.kind === 'embedding' ? EMBEDDING_OPTIONS : MODEL_OPTIONS
      return { ok: true, status: 200, json: async () => ({ kind: body.kind, ok: true, models: options.map(o => o.id), model_options: options, count: options.length, latency_ms: 12, provider: 'https://saved.invalid/v1', error: null }) }
    }
    if (path.endsWith('/capability')) {
      const model = String(body.EMBEDDING_TARGET_MODEL ?? '')
      return { ok: true, status: 200, json: async () => CAPABILITIES[model] ?? CAPABILITIES['my-private-embedding'] }
    }
    if (path.endsWith('/test')) {
      return { ok: true, status: 200, json: async () => ({ kind: body.kind, ok: !failure, latency_ms: 37, http_status: failure ? 401 : 200, detail: { model: body.LLM_CHAT_MODEL ?? 'x' }, provider: 'https://saved.invalid/v1', error: failure ? '服务商返回 HTTP 401，请核对密钥、地区、模型与额度' : null }) }
    }
    if (options.method === 'PUT') return { ok: true, status: 200, json: async () => ({ ...saved, ...body, message: '已保存' }) }
    return { ok: true, status: 200, json: async () => saved }
  }))
  const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/', component: { template: '<div />' } }] })
  await router.push('/')
  wrapper = mount(ApiSettings, { attachTo: document.body, global: { plugins: [createPinia(), router] } })
  await flushPromises()
  return wrapper
}

const lastPut = () => calls.filter(call => call.method === 'PUT').at(-1)?.body ?? {}
const modelCalls = () => calls.filter(call => call.path.endsWith('/models'))

afterEach(() => { wrapper?.unmount(); document.body.innerHTML = ''; vi.unstubAllGlobals() })

describe('api-settings 模型选择', () => {
  it('每个接口各自的候选列表独立获取（空地址、远端缺 Key 都先提示）', async () => {
    const page = await setup()
    // 进页面自动获取的是大模型那一次
    expect(modelCalls().map(call => call.body.kind)).toEqual(['llm'])
    // 向量接口默认没有地址：先给出明确提示，不发请求
    await page.get('[data-test="embedding-discover"]').trigger('click')
    await flushPromises()
    expect(page.get('[data-test="discovery-error"]').text()).toContain('请填写 API 地址')
    expect(modelCalls()).toHaveLength(1)

    // 远端地址没有 Key：同样拦下（本机地址才允许不填 Key）
    await page.get('[data-test="embedding-base-url"]').setValue('https://saved.invalid/v1')
    await page.get('[data-test="embedding-discover"]').trigger('click')
    await flushPromises()
    expect(page.get('[data-test="discovery-error"]').text()).toContain('API Key')
    expect(modelCalls()).toHaveLength(1)

    // 本机地址无需 Key，可与大模型各自获取
    await page.get('[data-test="embedding-base-url"]').setValue('http://127.0.0.1:11434/v1')
    await page.get('[data-test="embedding-discover"]').trigger('click')
    await flushPromises()
    expect(modelCalls().map(call => call.body.kind)).toEqual(['llm', 'embedding'])
  })

  it('同一用户重新打开页面时自动带回上次填的密钥', async () => {
    window.localStorage.setItem('smartsketch.apiKeys', JSON.stringify({ llm: 'remembered-key' }))
    const page = await setup()
    expect((page.get('[data-test="llm-api-key"]').element as HTMLInputElement).value).toBe('remembered-key')
    expect(page.get('[data-test="key-restored"]').text()).toContain('已自动带回')
  })

  it('换到别的主机后不再带回旧密钥，保存成功后清除本机留存', async () => {
    window.localStorage.setItem('smartsketch.apiKeys', JSON.stringify({ llm: 'remembered-key' }))
    const page = await setup()
    await page.get('[data-test="llm-base-url"]').setValue('https://another.invalid/v1')
    await flushPromises()
    expect((page.get('[data-test="llm-api-key"]').element as HTMLInputElement).value).toBe('')
    expect(window.localStorage.getItem('smartsketch.apiKeys') ?? '').not.toContain('remembered-key')

    // 填一把新钥匙并保存：字段与本机留存都应清空（密钥已写入本机加密配置）
    await page.get('[data-test="llm-api-key"]').setValue('fresh-key')
    await page.get('form').trigger('submit')
    await flushPromises()
    expect((page.get('[data-test="llm-api-key"]').element as HTMLInputElement).value).toBe('')
    expect(window.localStorage.getItem('smartsketch.apiKeys') ?? '').not.toContain('fresh-key')
  })

  it('已选模型时仍展开全部候选，并能改选另一个模型', async () => {
    const page = await setup()
    await page.get('[data-test="llm-discover"]').trigger('click')
    await flushPromises()
    const input = page.get('[data-test="model-select-input"]')
    expect((input.element as HTMLInputElement).value).toBe('DeepSeek-V4.1-Flash')   // 旧配置优先显示 LLM_CHAT_MODEL

    await input.trigger('focus')
    await flushPromises()
    const options = page.findAll('[data-test="model-option"]')
    expect(options.map(node => node.find('.model-select__name').text())).toEqual(['DeepSeek-V4.1-Flash', 'DeepSeek-V4-Pro', 'deepseek-plain'])
    expect(options.map(node => node.find('.model-select__id').exists())).toEqual([true, true, false])  // 无展示名时只显示 ID

    await options[1].trigger('mousedown')
    await flushPromises()
    expect((input.element as HTMLInputElement).value).toBe('DeepSeek-V4-Pro')
    await page.get('form').trigger('submit')
    await flushPromises()
    expect([lastPut().LLM_CHAT_MODEL, lastPut().LLM_EXTRACTION_MODEL]).toEqual(['deepseek-pro', 'deepseek-pro'])
  })

  it('保存时写入真实模型 ID，并保留已保存的 Key（不发空 Key）', async () => {
    const page = await setup()
    await page.get('[data-test="llm-discover"]').trigger('click')
    await flushPromises()
    await page.get('[data-test="model-select-input"]').trigger('focus')
    await flushPromises()
    await page.findAll('[data-test="model-option"]')[0].trigger('mousedown')
    await flushPromises()
    await page.get('form').trigger('submit')
    await flushPromises()
    const body = lastPut()
    expect(body.LLM_CHAT_MODEL).toBe('deepseek-flash')
    expect('LLM_API_KEY' in body).toBe(false)
    expect('EMBEDDING_MODE' in body).toBe(false)   // 不提交向量模式，保留迁移门禁
  })

  it('地址变化后旧列表失效，填入新 Key 后再获取时使用新地址', async () => {
    const page = await setup()
    // 进页面已自动获取过一次，这里按「增量」判断后续请求
    const before = modelCalls().length
    expect(before).toBe(1)
    await page.get('[data-test="llm-discover"]').trigger('click')
    await flushPromises()
    expect(page.find('[data-test="model-stale"]').exists()).toBe(false)
    expect(modelCalls()).toHaveLength(before + 1)   // 「重新获取」再拉一次

    await page.get('[data-test="llm-base-url"]').setValue('https://another.invalid/v1')
    await flushPromises()
    expect(page.get('[data-test="model-stale"]').text()).toContain('已失效')

    // 换主机又没给新 Key：拦下并提示，不发请求
    const guardBaseline = modelCalls().length
    await page.get('[data-test="llm-discover"]').trigger('click')
    await flushPromises()
    expect(page.get('[data-test="discovery-error"]').text()).toContain('API 主机已更换')
    expect(modelCalls()).toHaveLength(guardBaseline)

    await page.get('[data-test="llm-api-key"]').setValue('brand-new-key')
    await page.get('[data-test="llm-discover"]').trigger('click')
    await flushPromises()
    expect(modelCalls()).toHaveLength(guardBaseline + 1)
    expect(modelCalls().at(-1)?.body.LLM_BASE_URL).toBe('https://another.invalid/v1')
  })

  it('换了主机且没有新 Key 时给出提示', async () => {
    const page = await setup()
    const before = modelCalls().length
    await page.get('[data-test="llm-base-url"]').setValue('https://another.invalid/v1')
    await page.get('[data-test="llm-discover"]').trigger('click')
    await flushPromises()
    expect(page.get('[data-test="discovery-error"]').text()).toContain('API 主机已更换')
    expect(modelCalls()).toHaveLength(before)   // 只有进页面那次自动获取
  })

  it('进页面自动获取一次，并只报接口返回的模型数量', async () => {
    const page = await setup()
    expect(modelCalls()).toHaveLength(1)        // 无需点按钮
    // 两块统一文案：只有「接口返回 N 个模型」，不带时间、延迟或其他说明
    expect(page.findAll('[data-test="discovery-count"]').map(node => node.text())).toEqual(['接口返回 3 个模型', '接口返回 0 个模型'])
    expect(page.find('[data-test="discovery-ok"]').exists()).toBe(false)
    expect(page.get('[data-test="llm-discover"]').text()).toContain('重新获取')
  })
})

/** 选中向量模型：填地址与 Key → 获取候选 → 在向量卡片里选模型 */
async function pickEmbeddingModel(page: VueWrapper, model: string): Promise<void> {
  await page.get('[data-test="embedding-base-url"]').setValue('https://saved.invalid/v1')
  await page.get('[data-test="embedding-api-key"]').setValue('embedding-key')
  await page.get('[data-test="embedding-discover"]').trigger('click')
  await flushPromises()
  const input = page.get('[data-test="embedding-model"] [data-test="model-select-input"]')
  await input.trigger('focus')
  await flushPromises()
  const option = page.findAll('[data-test="embedding-model"] [data-test="model-option"]')
    .find(node => node.text().includes(model))
  if (!option) throw new Error(`未找到候选：${model}`)
  await option.trigger('mousedown')
  await flushPromises()
}

describe('api-settings 向量维度', () => {
  it('维度选项跟随模型能力变化', async () => {
    const page = await setup()
    await pickEmbeddingModel(page, 'text-embedding-v4')
    const select = page.get('[data-test="embedding-dimensions"]')
    expect(select.element.tagName).toBe('SELECT')
    const values = Array.from((select.element as HTMLSelectElement).options).map(option => option.value)
    expect(values).toEqual(['64', '256', '768', '1024', '1536', '2048'])
    expect(page.get('[data-test="capability-state"]').text()).toContain('推荐默认 1024 维')

    // 换成固定维度模型：变成只读输入，且只能用它自身的维度
    await pickEmbeddingModel(page, 'text-embedding-v3')
    const fixed = page.get('[data-test="embedding-dimensions"]')
    expect(fixed.element.tagName).toBe('INPUT')
    expect((fixed.element as HTMLInputElement).value).toBe('1024')
    expect(page.get('[data-test="capability-state"]').text()).toContain('维度固定')
  })

  it('能力未知的模型要求手动填写并勾选确认', async () => {
    const page = await setup()
    await pickEmbeddingModel(page, 'my-private-embedding')
    expect(page.find('[data-test="embedding-dimensions"]').exists()).toBe(false)
    expect(page.get('[data-test="capability-unknown"]').text()).toContain('维度说明我们没有收录')
    await page.get('[data-test="embedding-dimensions-manual"]').setValue('512')
    await page.get('[data-test="assume-dimensions"]').setValue(true)
    await page.get('form').trigger('submit')
    await flushPromises()
    const body = lastPut()
    expect(body.EMBEDDING_TARGET_MODEL).toBe('my-private-embedding')
    expect(body.EMBEDDING_TARGET_DIMENSIONS).toBe(512)
    expect(body.EMBEDDING_TARGET_ASSUME_DIMENSIONS).toBe(true)
  })

  it('维度说明默认收起，点「!」按钮才展开', async () => {
    const page = await setup()
    await pickEmbeddingModel(page, 'text-embedding-v4')
    // 默认不占版面：解释文字不出现，能力行也不暴露参数名
    expect(page.find('[data-test="embedding-help"]').exists()).toBe(false)
    expect(page.get('[data-test="capability-state"]').text()).not.toContain('dimensions')
    const toggle = page.get('[data-test="embedding-help-toggle"]')
    expect(toggle.attributes('aria-expanded')).toBe('false')
    await toggle.trigger('click')
    expect(page.get('[data-test="embedding-help"]').text()).toContain('维度表示每段文本生成的向量长度，需要与数据库索引保持一致。')
    expect(toggle.attributes('aria-expanded')).toBe('true')
    await toggle.trigger('click')
    expect(page.find('[data-test="embedding-help"]').exists()).toBe(false)
  })

  it('保存目标维度不改写当前向量空间，并提示需迁移', async () => {
    const page = await setup()
    await pickEmbeddingModel(page, 'text-embedding-v4')
    await page.get('[data-test="embedding-dimensions"]').setValue('1536')
    await page.get('form').trigger('submit')
    await flushPromises()
    const body = lastPut()
    expect(body.EMBEDDING_TARGET_MODEL).toBe('text-embedding-v4')
    expect(body.EMBEDDING_TARGET_DIMENSIONS).toBe(1536)
    // 运行时字段不得被改写，也不提交向量模式
    expect('EMBEDDING_MODEL' in body).toBe(false)
    expect('EMBEDDING_DIMENSIONS' in body).toBe(false)
    expect('EMBEDDING_MODE' in body).toBe(false)
    // 两个状态分开显示，且明确提示待迁移
    expect(page.get('[data-test="embedding-current"]').text()).toContain('当前使用')
    expect(page.get('[data-test="embedding-target"]').text()).toContain('1536 维')
    expect(page.get('[data-test="embedding-pending"]').text()).toContain('离线迁移')
  })
})
