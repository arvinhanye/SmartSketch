import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { test, expect } from 'vitest'
import KnowledgeDetail from '../../src/frontend/src/components/KnowledgeDetail.vue'
import { KNOWLEDGE_DETAIL_API_KEY } from '../../src/frontend/src/api/knowledgeDetail'
import { useCourseStore } from '../../src/frontend/src/stores/course'

test('长来源只在展开后显示全文，收起恢复短预览', async () => {
  const pinia = createPinia(); setActivePinia(pinia); useCourseStore(pinia).selectCourse('c1')
  const excerpt = '栈的来源原文'.repeat(300)
  const wrapper = mount(KnowledgeDetail, { props: { kpId: 'k1' }, global: { plugins: [pinia], provide: { [KNOWLEDGE_DETAIL_API_KEY as symbol]: { get: async () => ({ id:'k1', course_id:'c1',name:'栈',type:'concept',definition:'定义',level:0,aliases:[],status:'approved',source:'ai',locked:false,revision:1,prerequisites:[],successors:[],related:[],source_refs:[{chunk_id:'k-a',document_id:'m1',page:2,text:excerpt,document_name:'ch3.pdf'}] }) } } } })
  await flushPromises()
  expect(wrapper.get('[data-test=kd-source-excerpt]').text().length).toBeLessThanOrEqual(601)
  await wrapper.get('[data-test=kd-source-locate]').trigger('click')
  expect(wrapper.get('[data-test=sv-excerpt]').text().length).toBeLessThan(excerpt.length)
  expect(wrapper.find('[data-test=kd-source-excerpt]').exists()).toBe(false)
  await wrapper.get('[data-test=sv-expand]').trigger('click')
  expect(wrapper.get('[data-test=sv-excerpt]').text()).toBe(excerpt)
  expect(wrapper.findAll('blockquote')).toHaveLength(1)
  await wrapper.get('[data-test=sv-close]').trigger('click')
  expect(wrapper.get('[data-test=kd-source-excerpt]').text().length).toBeLessThanOrEqual(601)
  wrapper.unmount()
})

import { reasonFactRows } from '../../src/frontend/src/composables/useLearning'
import type { Recommendation } from '../../src/frontend/src/api/recommend'
test('显式 0.5 与旧接口数值不能被猜测为缺失', () => {
  const item = { unlock_count: 0, reason_facts: {primary_factor:'ease',chapter_id:null,chapter_name:null,chapter_rank:null,importance:0.5,centrality:0,difficulty:0.5} } as Recommendation
  expect(reasonFactRows(item).find(r => r.key === 'difficulty')).toMatchObject({value:'0.5000',labelledDefault:false})
})
