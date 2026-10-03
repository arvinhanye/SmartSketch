import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import type { components } from '../../src/contracts/v1/generated/typescript/openapi'
import SourceViewer from '../../src/frontend/src/components/SourceViewer.vue'
import { toKnowledgeDetailView } from '../../src/frontend/src/composables/useKnowledgeDetail'
import { EXCERPT_FOLD_CHARS, formatSourceLine } from '../../src/frontend/src/composables/sourceLabel'

// L12（R04，ADR-085）：图谱节点来源与问答引用都能查看文件名、页码或章节、原文片段。
// 文件名来自后端同课资料（契约可选 document_name）；缺失时明确显示「资料不可用」，不拿资料 ID 冒充文件名。

type Detail = components['schemas']['KnowledgePointDetail']

describe('L12 来源一行文字', () => {
  it('PDF 来源：文件名 · 第 N 页', () => {
    expect(formatSourceLine({ documentName: 'ch3-stack-queue.pdf', page: 2 })).toBe('ch3-stack-queue.pdf · 第 2 页')
  })

  it('Markdown 来源没有页码：文件名 · 章节', () => {
    expect(formatSourceLine({ documentName: 'ch3.md', sectionPath: '第3章 > 3.2 栈' })).toBe('ch3.md · 第3章 > 3.2 栈')
  })

  it('页码与章节都有时都显示；缺文件名时显示「资料不可用」', () => {
    expect(formatSourceLine({ page: 3, sectionPath: '第3章' })).toBe('资料不可用 · 第 3 页 · 第3章')
    expect(formatSourceLine({ documentName: '  ', page: 1 })).toBe('资料不可用 · 第 1 页')
  })
})

describe('L12 知识点详情映射文件名', () => {
  it('source_refs 的 document_name 进入来源视图', () => {
    const view = toKnowledgeDetailView({
      id: 'a', course_id: 'c1', name: '栈', type: 'concept', definition: '定义', level: 0, aliases: [],
      status: 'approved', source: 'ai', locked: false, revision: 1, prerequisites: [], successors: [], related: [],
      source_refs: [
        { chunk_id: 'k1', document_id: 'm1', page: 2, text: '片段', document_name: 'ch3.pdf' },
        { chunk_id: 'k2', document_id: 'm2', section_path: '第3章' },
      ],
    } as unknown as Detail)
    expect(view.sources.map((s) => s.documentName)).toEqual(['ch3.pdf', undefined])
  })
})

describe('L12 来源查看器', () => {
  function viewer(source: { documentName?: string; page?: number; sectionPath?: string; excerpt?: string }) {
    return mount(SourceViewer, { props: { source } })
  }

  it('显示文件名、位置与片段，可关闭', async () => {
    const wrapper = viewer({ documentName: 'ch3.pdf', page: 2, excerpt: '栈是只允许在一端插入和删除的线性表。' })
    expect(wrapper.get('[data-test="sv-document"]').text()).toBe('ch3.pdf')
    expect(wrapper.get('[data-test="sv-location"]').text()).toBe('第 2 页')
    expect(wrapper.get('[data-test="sv-excerpt"]').text()).toBe('栈是只允许在一端插入和删除的线性表。')
    await wrapper.get('[data-test="sv-close"]').trigger('click')
    expect(wrapper.emitted('close')).toHaveLength(1)
  })

  it('缺文件名时写「资料不可用」，不显示资料 ID；没有片段时说明', () => {
    const wrapper = viewer({ sectionPath: '第3章 > 3.2 栈' })
    expect(wrapper.get('[data-test="sv-document"]').text()).toBe('资料不可用')
    expect(wrapper.get('[data-test="sv-location"]').text()).toBe('第3章 > 3.2 栈')
    expect(wrapper.get('[data-test="sv-no-excerpt"]').text()).toContain('没有可显示的原文片段')
  })

  it('超长片段先折叠，可展开', async () => {
    const long = '栈'.repeat(EXCERPT_FOLD_CHARS + 50)
    const wrapper = viewer({ documentName: 'a.pdf', page: 1, excerpt: long })
    expect(wrapper.get('[data-test="sv-excerpt"]').text().length).toBeLessThan(long.length)
    await wrapper.get('[data-test="sv-expand"]').trigger('click')
    expect(wrapper.get('[data-test="sv-excerpt"]').text()).toBe(long)
  })

  it('片段与文件名里的标签按纯文本显示，不生成可执行节点', () => {
    const wrapper = viewer({ documentName: '<img src=x onerror=alert(1)>.pdf', page: 1, excerpt: '<script>alert(1)</script>[1]' })
    expect(wrapper.find('img').exists()).toBe(false)
    expect(wrapper.find('script').exists()).toBe(false)
    expect(wrapper.get('[data-test="sv-excerpt"]').text()).toBe('<script>alert(1)</script>[1]')
  })
})

// ---------------------------------------------------------------- 详情内点开来源（教师、学生图谱共用）

import { flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { vi } from 'vitest'
import { KNOWLEDGE_DETAIL_API_KEY, type KnowledgeDetailApi } from '../../src/frontend/src/api/knowledgeDetail'
import KnowledgeDetail from '../../src/frontend/src/components/KnowledgeDetail.vue'
import { useCourseStore } from '../../src/frontend/src/stores/course'

describe('L12 知识点详情里点开来源', () => {
  function mountDetail() {
    const pinia = createPinia()
    setActivePinia(pinia)
    useCourseStore(pinia).selectCourse('c1')
    const api: KnowledgeDetailApi = {
      get: vi.fn(async () => ({
        id: 'k1', course_id: 'c1', name: '栈', type: 'concept', definition: '定义', level: 0, aliases: [],
        status: 'approved', source: 'ai', locked: false, revision: 1, prerequisites: [], successors: [], related: [],
        source_refs: [
          { chunk_id: 'k-a', document_id: 'm1', page: 2, text: '栈是只允许在一端插入和删除的线性表。', document_name: 'ch3.pdf' },
          { chunk_id: 'k-b', document_id: 'm2', section_path: '第3章 > 3.2 栈' },
        ],
      } as unknown as Detail)),
    }
    return mount(KnowledgeDetail, {
      props: { kpId: 'k1' },
      attachTo: document.body,
      global: { plugins: [pinia], provide: { [KNOWLEDGE_DETAIL_API_KEY as symbol]: api } },
    })
  }

  it('点击来源在该条下展开查看器，显示文件名、页码与片段；可收起', async () => {
    const wrapper = mountDetail()
    await flushPromises()
    expect(wrapper.find('[data-test="source-viewer"]').exists()).toBe(false)
    await wrapper.findAll('[data-test="kd-source-locate"]')[0]!.trigger('click')
    const viewer = wrapper.get('[data-test="source-viewer"]')
    expect(viewer.get('[data-test="sv-document"]').text()).toBe('ch3.pdf')
    expect(viewer.get('[data-test="sv-location"]').text()).toBe('第 2 页')
    expect(viewer.get('[data-test="sv-excerpt"]').text()).toContain('栈是只允许')
    await viewer.get('[data-test="sv-close"]').trigger('click')
    expect(wrapper.find('[data-test="source-viewer"]').exists()).toBe(false)
    wrapper.unmount()
  })

  it('Markdown 来源没有页码、文件名缺失时仍可查看位置，并写「资料不可用」', async () => {
    const wrapper = mountDetail()
    await flushPromises()
    await wrapper.findAll('[data-test="kd-source-locate"]')[1]!.trigger('click')
    const viewer = wrapper.get('[data-test="source-viewer"]')
    expect(viewer.get('[data-test="sv-document"]').text()).toBe('资料不可用')
    expect(viewer.get('[data-test="sv-location"]').text()).toBe('第3章 > 3.2 栈')
    wrapper.unmount()
  })
})

// ---------------------------------------------------------------- 问答引用

import { createMemoryHistory, createRouter } from 'vue-router'
import { CHAT_STREAM_CLIENT_KEY, type ChatStreamClient } from '../../src/frontend/src/api/chatStream'
import { CHAT_ROUTE, COURSE_ROUTE, SETTINGS_ROUTE } from '../../src/frontend/src/router/index.ts'
import { useRuntimeStore } from '../../src/frontend/src/stores/runtime'
import ChatView from '../../src/frontend/src/views/ChatView.vue'

describe('L12 问答引用显示文件名', () => {
  it('右栏出处与展开的原文都带文件名；缺文件名写「资料不可用」', async () => {
    const pinia = createPinia()
    setActivePinia(pinia)
    useRuntimeStore().apply({ runtime_mode: 'personal', configured: true })
    const client: ChatStreamClient = {
      async send() {
        return {
          kind: 'done',
          final: {
            status: 'answered', answer: '栈后进先出[1]。队列先进先出[2]。', graph_version: 1, request_id: 'r',
            citations: [
              { index: 1, chunk_id: 'k1', document_id: 'm1', page: 2, text: '栈是线性表。', document_name: 'ch3-stack-queue.pdf' },
              { index: 2, chunk_id: 'k2', document_id: 'm2', section_path: '第3章 > 3.3 队列', text: '队列是线性表。' },
            ],
          },
        } as never
      },
    }
    const stub = { render: () => null }
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [
        { path: '/courses/:cid', name: COURSE_ROUTE, component: stub },
        { path: '/courses/:cid/chat', name: CHAT_ROUTE, component: ChatView },
        { path: '/settings/model', name: SETTINGS_ROUTE, component: stub },
      ],
    })
    await router.push('/courses/c1/chat')
    await router.isReady()
    const wrapper = mount(ChatView, { global: { plugins: [pinia, router], provide: { [CHAT_STREAM_CLIENT_KEY as symbol]: client } } })
    await wrapper.get('textarea').setValue('栈和队列有什么区别？')
    await wrapper.get('form').trigger('submit')
    await flushPromises()
    const items = wrapper.findAll('.source-list__item')
    expect(items[0]!.text()).toContain('ch3-stack-queue.pdf · 第 2 页')
    expect(items[1]!.text()).toContain('资料不可用 · 第3章 > 3.3 队列')
    await items[0]!.trigger('click')
    expect(wrapper.get('.source__where').text()).toContain('ch3-stack-queue.pdf')
    wrapper.unmount()
  })
})
