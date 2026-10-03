import { expect, type APIRequestContext } from '@playwright/test'

// E2E 的数据准备走真实 HTTP 接口（经前端同源反代），只用于把课程推进到被测页面需要的状态；
// 被验收的交互本身仍在浏览器里完成。

export type Api = { request: APIRequestContext; token: string }

export async function apiLogin(request: APIRequestContext, username: string, password: string): Promise<Api> {
  const response = await request.post('/api/v1/auth/login', { data: { username, password } })
  expect(response.status(), `login ${username}`).toBe(200)
  return { request, token: (await response.json()).access_token as string }
}

function headers(api: Api): Record<string, string> {
  return { Authorization: `Bearer ${api.token}` }
}

export async function call(api: Api, method: string, path: string, data?: unknown) {
  return api.request.fetch(path, { method, headers: headers(api), data })
}

export async function createCourse(api: Api, name: string): Promise<string> {
  const response = await call(api, 'POST', '/api/v1/courses', { name })
  expect(response.status()).toBe(201)
  return (await response.json()).id as string
}

/** 学生自助注册（成功即登录）：用于需要第二个学生账号的隔离证据 */
export async function registerStudent(request: APIRequestContext, username: string, password: string): Promise<void> {
  const response = await request.post('/api/v1/auth/register', { data: { username, password } })
  expect(response.status(), `register ${username}`).toBe(201)
}

export async function addStudent(api: Api, courseId: string, username: string): Promise<void> {
  const response = await call(api, 'POST', `/api/v1/courses/${courseId}/members`, { username })
  expect([200, 201]).toContain(response.status())
}

export async function uploadAndWait(api: Api, courseId: string, name: string, mimeType: string, buffer: Buffer): Promise<void> {
  const response = await api.request.post(`/api/v1/courses/${courseId}/documents`, {
    headers: headers(api), multipart: { file: { name, mimeType, buffer } },
  })
  expect(response.status()).toBe(202)
  const documentId = (await response.json()).document_id as string
  await expect.poll(async () => {
    const items: Array<{ id: string; parse_status: string }> =
      await (await call(api, 'GET', `/api/v1/courses/${courseId}/documents`)).json()
    return items.find((item) => item.id === documentId)?.parse_status
  }, { timeout: 120_000, intervals: [500, 1000, 2000] }).toBe('awaiting_review')
}

export async function publish(api: Api, courseId: string): Promise<number> {
  const response = await call(api, 'POST', `/api/v1/courses/${courseId}/publish`)
  expect(response.status(), await response.text()).toBe(200)
  return (await response.json()).version as number
}

export type DraftNode = { id: string; name: string; revision: number }

export async function draftNodes(api: Api, courseId: string): Promise<DraftNode[]> {
  const response = await call(api, 'GET', `/api/v1/courses/${courseId}/graph`)
  expect(response.status()).toBe(200)
  return (await response.json()).nodes as DraftNode[]
}
