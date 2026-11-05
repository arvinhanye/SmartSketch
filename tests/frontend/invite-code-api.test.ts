import { describe, expect, it } from 'vitest'
import { ApiError, createHttpClient, type ErrorCode, type FetchLike } from '../../src/frontend/src/api/http'
import { createInviteCodeApi } from '../../src/frontend/src/api/inviteCode'

const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })
describe('邀请码契约客户端', () => {
  it('查看与重置按课程编码路径，入课仅发送code，全部携带令牌', async () => {
    const calls: Array<{ url: string; init?: RequestInit }> = []
    const fetch: FetchLike = async (url, init) => { calls.push({ url, init }); return json({ code: 'ABC234', rotated_at: '2026-11-05T00:00:00Z' }) }
    const api = createInviteCodeApi(createHttpClient({ fetch, getAccessToken: () => 'token' }))
    await api.get('a/b')
    await api.rotate('a/b')
    await api.join({ code: 'ABC234' })
    expect(calls.map(({ url, init }) => [url, init?.method])).toEqual([
      ['/api/v1/courses/a%2Fb/invite-code', 'GET'],
      ['/api/v1/courses/a%2Fb/invite-code:rotate', 'POST'],
      ['/api/v1/courses/join', 'POST'],
    ])
    expect(JSON.parse(String(calls[2]!.init?.body))).toEqual({ code: 'ABC234' })
    expect(calls.every(({ init }) => new Headers(init?.headers).get('Authorization') === 'Bearer token')).toBe(true)
  })
  it.each(['INVITE_CODE_INVALID', 'ALREADY_MEMBER'] as const)('HTTP运行时把%s保留为ApiError', async (code: ErrorCode) => {
    const status = code === 'ALREADY_MEMBER' ? 409 : 404
    const client = createHttpClient({ fetch: async () => json({ code, message: 'private message' }, status) })
    const result = client.request('post', '/api/v1/courses/join', { body: { code: 'ABC234' } })
    await expect(result).rejects.toBeInstanceOf(ApiError)
    await expect(result).rejects.toMatchObject({ code, status })
  })
  it('三个操作都把调用者取消传入fetch', async () => {
    const signals: AbortSignal[] = []
    const api = createInviteCodeApi(createHttpClient({ fetch: async (_url, init) => { signals.push(init!.signal!); return json({}) } }))
    for (const invoke of [api.get.bind(api, 'c1'), api.rotate.bind(api, 'c1'), api.join.bind(api, { code: 'ABC234' })]) {
      const controller = new AbortController()
      const result = invoke({ signal: controller.signal })
      controller.abort()
      await result.catch(() => undefined)
    }
    expect(signals).toHaveLength(3)
    expect(signals.every((signal) => signal.aborted)).toBe(true)
  })
})
