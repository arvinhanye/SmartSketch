import { createPinia, setActivePinia } from 'pinia'
import { mount } from '@vue/test-utils'
import { defineComponent, h, nextTick, ref } from 'vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { components } from '../../src/contracts/v1/generated/typescript/openapi'
import { ApiError } from '../../src/frontend/src/api/http'
import type { KnowledgeDetailApi } from '../../src/frontend/src/api/knowledgeDetail'
import type { NodeEditApi } from '../../src/frontend/src/api/nodeEdit'
import { nodePickerOptions, useNodeCreator } from '../../src/frontend/src/composables/useNodeCreator'
import { useCourseStore } from '../../src/frontend/src/stores/course'

// L11-3 走查发现的两个前端阻断：教师图谱页只能在画布上点选节点（键盘与自动化无法选择），
// 且后端已有的「新建知识点」（ADR-035：新建必带来源）在页面上没有入口。

type Detail = components['schemas']['KnowledgePointDetail']
type KnowledgePoint = components['schemas']['KnowledgePoint']

const DETAIL = {
  id: 'kp-stack', course_id: 'c1', name: '栈', type: 'concept', definition: '后进先出的线性表', level: 0,
  aliases: [], status: 'approved', source: 'ai', locked: false, revision: 1,
  source_refs: [
    { chunk_id: 'ch-1', document_id: 'd1', page: 2, text: '栈是只允许在一端进行插入和删除的线性表。' },
    { chunk_id: 'ch-2', document_id: 'd1', section_path: '第3章 > 3.2 栈', text: '顺序栈用数组存放元素。' },
  ],
  prerequisites: [], successors: [], related: [],
} as unknown as Detail

const CREATED = { id: 'kp-new', course_id: 'c1', name: '共享栈', type: 'concept', definition: '两个栈共享数组', revision: 1 } as unknown as KnowledgePoint

function apis(overrides: { create?: NodeEditApi['create'] } = {}) {
  const create = vi.fn<NodeEditApi['create']>(overrides.create ?? (async () => CREATED))
  const detail: KnowledgeDetailApi = { get: vi.fn(async () => DETAIL) }
  return { create, detail }
}

function mountCreator(sourceKp: string | null, overrides: { create?: NodeEditApi['create'] } = {}) {
  const { create, detail } = apis(overrides)
  const created: KnowledgePoint[] = []
  const source = ref<string | null>(sourceKp)
  let creator!: ReturnType<typeof useNodeCreator>
  const wrapper = mount(defineComponent({
    setup() {
      creator = useNodeCreator({ api: { create }, detailApi: detail, sourceKpId: source, onCreated: (kp) => created.push(kp) })
      return () => h('div')
    },
  }), { global: { plugins: [] } })
  return { creator: () => creator, create, detail, created, wrapper, source }
}

beforeEach(() => {
  setActivePinia(createPinia())
  useCourseStore().selectCourse('c1')
})

describe('L11 节点选择器选项', () => {
  it('按名称排序、去掉无名节点，值为知识点 ID', () => {
    const options = nodePickerOptions({ nodes: [
      { id: 'b', name: '队列' }, { id: 'a', name: '栈' }, { id: 'x', name: '' }, { id: 'c', name: '循环队列' },
    ] } as never)
    expect(options).toEqual([
      { value: 'c', label: '循环队列' }, { value: 'b', label: '队列' }, { value: 'a', label: '栈' },
    ].sort((p, q) => p.label.localeCompare(q.label, 'zh-Hans-CN')))
    expect(nodePickerOptions(null)).toEqual([])
  })
})

describe('L11 以选中知识点的来源新建知识点（ADR-035）', () => {
  it('没有选中知识点时提示先选择，不发请求', async () => {
    const { creator, create, wrapper } = mountCreator(null)
    await creator().open()
    expect(creator().hint.value).toContain('先在图谱或下拉框中选中一个知识点')
    await creator().submit()
    expect(create).not.toHaveBeenCalled()
    wrapper.unmount()
  })

  it('打开时载入选中知识点的来源并默认全选；提交去空白后的字段与所选文本块', async () => {
    const { creator, create, created, wrapper } = mountCreator('kp-stack')
    await creator().open()
    expect(creator().sources.value.map((s) => s.chunkId)).toEqual(['ch-1', 'ch-2'])
    creator().form.name = '  共享栈 '
    creator().form.definition = ' 两个栈共享数组 '
    creator().toggleSource('ch-2')
    await creator().submit()
    expect(create).toHaveBeenCalledWith('c1', {
      name: '共享栈', type: 'concept', definition: '两个栈共享数组', sources: [{ chunk_id: 'ch-1' }],
    }, expect.anything())
    expect(created).toEqual([CREATED])
    expect(creator().success.value).toContain('共享栈')
    wrapper.unmount()
  })

  it('名称、定义为空或一个来源都没选时不发请求', async () => {
    const { creator, create, wrapper } = mountCreator('kp-stack')
    await creator().open()
    await creator().submit()
    expect(creator().error.value).toContain('名称')
    creator().form.name = '共享栈'
    creator().form.definition = '两个栈共享数组'
    creator().toggleSource('ch-1')
    creator().toggleSource('ch-2')
    await creator().submit()
    expect(creator().error.value).toContain('来源')
    expect(create).not.toHaveBeenCalled()
    wrapper.unmount()
  })

  it.each([
    [new ApiError(422, { code: 'VALIDATION_ERROR', message: '服务端原文', details: { fields: [{ in: 'body', field: 'sources[0]', reason: 'not_committed' }] } }), '来源'],
    [new ApiError(409, { code: 'COURSE_BUSY', message: '服务端原文' }), '正在写入'],
  ])('失败按错误码给固定文案，不回显服务端 message：%#', async (failure, text) => {
    const { creator, wrapper } = mountCreator('kp-stack', { create: async () => { throw failure } })
    await creator().open()
    Object.assign(creator().form, { name: '共享栈', definition: '两个栈共享数组' })
    await creator().submit()
    expect(creator().error.value).toContain(text)
    expect(creator().error.value).not.toContain('服务端原文')
    expect(creator().busy.value).toBe(false)
    wrapper.unmount()
  })

  it('提交中不重复提交；切换到别的课程后旧结果被丢弃', async () => {
    let finish!: (kp: KnowledgePoint) => void
    const { creator, create, created, wrapper } = mountCreator('kp-stack', {
      create: () => new Promise<KnowledgePoint>((resolve) => { finish = resolve }),
    })
    await creator().open()
    Object.assign(creator().form, { name: '共享栈', definition: '两个栈共享数组' })
    const first = creator().submit()
    await creator().submit()
    expect(create).toHaveBeenCalledTimes(1)
    useCourseStore().selectCourse('c2')
    await nextTick()
    finish(CREATED)
    await first
    expect(created).toEqual([])
    wrapper.unmount()
  })
})
