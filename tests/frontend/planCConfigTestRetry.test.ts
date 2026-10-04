import { describe, expect, it, vi } from 'vitest'
import { testLocalConnection } from '../e2e/configTestRetry'

function response(status: number, retryAfter?: string, code = 'RATE_LIMITED') {
  return { status: () => status, headers: () => retryAfter === undefined ? {} : { 'retry-after': retryAfter },
    json: async () => ({ code }) }
}
const localProvider = 'http://127.0.0.1:19590/v1'

describe('本机E2E配置测试共享限流窗口', () => {
  it('仅对应用429按Retry-After等待后再试一次；保留最终响应断言', async () => {
    const good = response(200)
    const send = vi.fn().mockResolvedValueOnce(response(429, '3')).mockResolvedValueOnce(good)
    const wait = vi.fn(async () => {})
    expect(await testLocalConnection(localProvider, send, wait)).toBe(good)
    expect(wait).toHaveBeenCalledExactlyOnceWith(3000)
    expect(send).toHaveBeenCalledTimes(2)
  })
  it.each([200, 401, 403, 500])('状态%s不重试、不等待', async (status) => {
    const final = response(status)
    const send = vi.fn(async () => final), wait = vi.fn(async () => {})
    expect(await testLocalConnection(localProvider, send, wait)).toBe(final)
    expect(send).toHaveBeenCalledTimes(1)
    expect(wait).not.toHaveBeenCalled()
  })
  it('再次429留给原成功断言失败，不循环', async () => {
    const final = response(429, '3')
    const send = vi.fn(async () => final), wait = vi.fn(async () => {})
    expect(await testLocalConnection(localProvider, send, wait)).toBe(final)
    expect(send).toHaveBeenCalledTimes(2)
    expect(wait).toHaveBeenCalledTimes(1)
  })
  it.each([undefined, 'NaN', '-1', '0', '1.5', '61'])('坏Retry-After %s立即失败', async (retryAfter) => {
    const send = vi.fn(async () => response(429, retryAfter)), wait = vi.fn(async () => {})
    await expect(testLocalConnection(localProvider, send, wait)).rejects.toThrow('Retry-After')
    expect(send).toHaveBeenCalledTimes(1)
    expect(wait).not.toHaveBeenCalled()
  })
  it('非应用RATE_LIMITED错误不重试', async () => {
    const send = vi.fn(async () => response(429, '3', 'BUDGET_EXCEEDED')), wait = vi.fn(async () => {})
    await expect(testLocalConnection(localProvider, send, wait)).rejects.toThrow('RATE_LIMITED')
    expect(send).toHaveBeenCalledTimes(1)
    expect(wait).not.toHaveBeenCalled()
  })
  it.each(['https://example.com/v1', 'http://localhost:1234/v1', 'https://127.0.0.1:1234/v1',
           'http://user:secret@127.0.0.1:1234/v1'])('非指定本机HTTP供应商%s，发请求前失败', async (url) => {
    const send = vi.fn(async () => response(200)), wait = vi.fn(async () => {})
    await expect(testLocalConnection(url, send, wait)).rejects.toThrow('local fake provider')
    expect(send).not.toHaveBeenCalled()
    expect(wait).not.toHaveBeenCalled()
  })
})
