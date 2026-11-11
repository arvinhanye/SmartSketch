import { flushPromises } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'
import { ApiError, InvalidResponseError, NetworkError, TimeoutError, type ErrorCode } from '../../src/frontend/src/api/http'
import { course, deferred, fakeInvite, invite, mountInvite, nextInvite, submitCode } from './invite-code-helpers'

describe('学生输码入课', () => {
  it('加入卡位于继续学习主卡之后、课程列表之前', async () => {
    const h = await mountInvite({ resume: true, courses: { list: async () => [course] } })
    const order = h.wrapper.findAll('[data-test="resume-card"], [data-test="course-join"], [data-test="course-list-region"]').map((element) => element.attributes('data-test'))
    expect(order).toEqual(['resume-card', 'course-join', 'course-list-region'])
  })
  it('学生列表显示输入框，成功规范化代码、刷新列表并高亮新课程', async () => {
    let joined = false
    const h = await mountInvite({ inviteApi: fakeInvite({ join: async () => { joined = true; return course } }), courses: { list: async () => joined ? [course] : [] } })
    await submitCode(h, '  abc234  ')
    await flushPromises()
    expect(h.api.join).toHaveBeenCalledWith({ code: 'ABC234' }, expect.objectContaining({ signal: expect.any(AbortSignal) }))
    expect(h.courses.list).toHaveBeenCalledTimes(2)
    expect(h.wrapper.get('[data-test="course-card"]').classes()).toContain('is-new')
    expect(h.wrapper.get('[data-test="course-join-success"]').text()).toContain('算法课程')
  })
  it.each([{ role: 'teacher' as const, path: '/teacher' }, { role: 'student' as const, path: '/courses/c1' }])('$role的$path不显示加入表单', async (options) => {
    const h = await mountInvite(options)
    expect(h.wrapper.find('[data-test="course-join"]').exists()).toBe(false)
  })
  it('无API注入时不新增表单，原学生空态与复制用户名入口保留', async () => {
    const h = await mountInvite({ inviteApi: null })
    expect(h.wrapper.find('[data-test="course-join"]').exists()).toBe(false)
    expect(h.wrapper.get('[data-test="courses-empty"]').text()).toContain('告诉任课教师')
    expect(h.wrapper.find('[data-test="course-copy-username"]').exists()).toBe(true)
  })
  it('加入未发布课程只给回执，不把draft塞进可见列表', async () => {
    const h = await mountInvite({ inviteApi: fakeInvite({ join: async () => ({ ...course, status: 'draft', published_version: null }) }) })
    await submitCode(h)
    await flushPromises()
    expect(h.wrapper.get('[data-test="course-join-success"]').text()).toContain('教师发布后可见')
    expect(h.wrapper.find('[data-test="course-card"]').exists()).toBe(false)
    expect(h.wrapper.find('[data-test="course-copy-username"]').exists()).toBe(true)
  })
  it.each(['', 'ABC23', 'ABC2345', 'ABO234', 'ABI234', 'ABC014'])('格式错误%s不会调用接口', async (code) => {
    const h = await mountInvite()
    await submitCode(h, code)
    expect(h.api.join).not.toHaveBeenCalled()
    expect(h.wrapper.get('[data-test="course-join-error"]').text()).toContain('六位')
  })
  it.each([
    [404, 'INVITE_CODE_INVALID', '邀请码不存在或已失效'],
    [409, 'ALREADY_MEMBER', '你已在该课程中'],
    [429, 'RATE_LIMITED', '请求过于频繁'],
    [422, 'VALIDATION_ERROR', '六位'],
    [403, 'ROLE_FORBIDDEN', '仅学生账号可以凭码加入课程'],
    [401, 'UNAUTHENTICATED', '登录已失效'],
  ] as const)('%s/%s给固定文案', async (status, code: ErrorCode, message) => {
    const h = await mountInvite({ inviteApi: fakeInvite({ join: async () => { throw new ApiError(status, { code, message: 'private-response' }) } }) })
    await submitCode(h)
    await flushPromises()
    expect(h.wrapper.get('[data-test="course-join-error"]').text()).toContain(message)
    expect(h.wrapper.text()).not.toContain('private-response')
  })
  it('网络错误有可重试提示', async () => {
    const h = await mountInvite({ inviteApi: fakeInvite({ join: async () => { throw new NetworkError('private-response') } }) })
    await submitCode(h)
    await flushPromises()
    expect(h.wrapper.get('[data-test="course-join-error"]').text()).toContain('检查网络')
    expect(h.wrapper.text()).not.toContain('private-response')
  })
})

describe('教师邀请码面板', () => {
  it('显示当前码，复制失败有反馈，重置先确认且可取消', async () => {
    Object.defineProperty(navigator, 'clipboard', { configurable: true, value: { writeText: vi.fn(async () => { throw new Error('denied') }) } })
    const h = await mountInvite({ role: 'teacher' })
    expect(h.wrapper.get('[data-test="invite-code-value"]').text()).toBe(invite.code)
    await h.wrapper.get('[data-test="invite-code-copy"]').trigger('click')
    await flushPromises()
    expect(h.wrapper.get('[data-test="invite-code-copy-status"]').text()).toContain('复制失败')
    await h.wrapper.get('[data-test="invite-code-reset"]').trigger('click')
    expect(h.api.rotate).not.toHaveBeenCalled()
    await h.wrapper.get('[data-test="invite-code-reset-cancel"]').trigger('click')
    expect(h.api.rotate).not.toHaveBeenCalled()
    await h.wrapper.get('[data-test="invite-code-reset"]').trigger('click')
    await h.wrapper.get('[data-test="invite-code-reset-confirm"]').trigger('click')
    await flushPromises()
    expect(h.api.rotate).toHaveBeenCalledTimes(1)
    expect(h.wrapper.get('[data-test="invite-code-value"]').text()).toBe(nextInvite.code)
    expect(h.wrapper.get('[data-test="invite-code-status"]').text()).toContain('旧码已失效')
    expect(h.wrapper.find('[data-test="member-add"]').exists()).toBe(true)
  })
  it('复制成功给可见回执', async () => {
    const write = vi.fn(async () => undefined)
    Object.defineProperty(navigator, 'clipboard', { configurable: true, value: { writeText: write } })
    const h = await mountInvite({ role: 'teacher' })
    await h.wrapper.get('[data-test="invite-code-copy"]').trigger('click')
    await flushPromises()
    expect(write).toHaveBeenCalledWith(invite.code)
    expect(h.wrapper.get('[data-test="invite-code-copy-status"]').text()).toContain('已复制')
  })
  it('成员列表尚未ready不请求邀请码；ready后才显示', async () => {
    const list = deferred<Awaited<ReturnType<import('../../src/frontend/src/api/members').MembersApi['list']>>>()
    const h = await mountInvite({ role: 'teacher', members: { list: () => list.promise } })
    expect(h.api.get).not.toHaveBeenCalled()
    expect(h.wrapper.find('[data-test="invite-code-panel"]').exists()).toBe(false)
    list.resolve([])
    await flushPromises()
    expect(h.api.get).toHaveBeenCalledTimes(1)
    expect(h.wrapper.find('[data-test="invite-code-panel"]').exists()).toBe(true)
  })
  it('成员接口拒绝时不请求邀请码', async () => {
    const h = await mountInvite({ role: 'teacher', members: { list: async () => { throw new ApiError(403, { code: 'ROLE_FORBIDDEN', message: 'private' }) } } })
    expect(h.api.get).not.toHaveBeenCalled()
    expect(h.wrapper.find('[data-test="invite-code-panel"]').exists()).toBe(false)
  })
  it('邀请码加载失败显示固定提示并能重试', async () => {
    const api = fakeInvite({ get: async () => { throw new Error('private-response') } })
    const h = await mountInvite({ role: 'teacher', inviteApi: api })
    expect(h.wrapper.get('[data-test="invite-code-error"]').text()).toContain('加载失败')
    expect(h.wrapper.text()).not.toContain('private-response')
    api.get.mockResolvedValue(invite)
    await h.wrapper.get('[data-test="invite-code-retry"]').trigger('click')
    await flushPromises()
    expect(h.wrapper.get('[data-test="invite-code-value"]').text()).toBe(invite.code)
  })
  it('服务端明确回滚的INTERNAL_ERROR保留现有码，显示固定提示且允许再次确认', async () => {
    // 碰撞耗尽在事务内返回 INTERNAL_ERROR，后端回滚确保旧码仍有效。
    const h = await mountInvite({ role: 'teacher', inviteApi: fakeInvite({ rotate: async () => { throw new ApiError(500, { code: 'INTERNAL_ERROR', message: 'private-response' }) } }) })
    await h.wrapper.get('[data-test="invite-code-reset"]').trigger('click')
    await h.wrapper.get('[data-test="invite-code-reset-confirm"]').trigger('click')
    await flushPromises()
    expect(h.wrapper.get('[data-test="invite-code-value"]').text()).toBe(invite.code)
    expect(h.wrapper.get('[data-test="invite-code-error"]').text()).toContain('重置失败')
    expect(h.wrapper.text()).not.toContain('private-response')
    expect(h.wrapper.get('[data-test="invite-code-reset-confirm"]').attributes('disabled')).toBeUndefined()
  })
  it.each([
    ['网络断开', new NetworkError('private-response')],
    ['请求超时', new TimeoutError(30000)],
    ['响应无效', new InvalidResponseError(200, 'private-response')],
  ])('重置后%s不能继续复制旧码，重试GET取回当前有效码', async (_label, failure) => {
    const h = await mountInvite({ role: 'teacher', inviteApi: fakeInvite({ rotate: async () => { throw failure } }) })
    await h.wrapper.get('[data-test="invite-code-reset"]').trigger('click')
    await h.wrapper.get('[data-test="invite-code-reset-confirm"]').trigger('click')
    await flushPromises()
    expect(h.wrapper.find('[data-test="invite-code-copy"]').exists()).toBe(false)
    expect(h.wrapper.find('[data-test="invite-code-value"]').exists()).toBe(false)
    expect(h.wrapper.text()).not.toContain(invite.code)
    expect(h.wrapper.get('[data-test="invite-code-error"]').text()).toContain('重新获取')
    h.api.get.mockResolvedValue(nextInvite)
    await h.wrapper.get('[data-test="invite-code-retry"]').trigger('click')
    await flushPromises()
    expect(h.api.get).toHaveBeenCalledTimes(2)
    expect(h.wrapper.get('[data-test="invite-code-value"]').text()).toBe(nextInvite.code)
    expect(h.wrapper.find('[data-test="invite-code-copy"]').exists()).toBe(true)
  })
})
