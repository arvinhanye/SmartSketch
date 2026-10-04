/** Test-only HTTP response surface: deliberately no application or Playwright runtime dependency. */
export interface ConfigTestResponse {
  status(): number
  headers(): Record<string, string>
  json(): Promise<{ code?: string }>
}
export async function testLocalConnection<T extends ConfigTestResponse>(
  providerUrl: string, send: () => Promise<T>, wait: (milliseconds: number) => Promise<unknown>,
): Promise<T> {
  let endpoint: URL
  try { endpoint = new URL(providerUrl) } catch { throw new Error('Expected local fake provider') }
  if (endpoint.protocol !== 'http:' || endpoint.hostname !== '127.0.0.1' || !endpoint.port ||
      endpoint.username || endpoint.password || endpoint.search || endpoint.hash) {
    throw new Error('Expected local fake provider')
  }
  const response = await send()
  if (response.status() !== 429) return response
  const body = await response.json()
  if (body?.code !== 'RATE_LIMITED') throw new Error('Expected application RATE_LIMITED')
  const value = response.headers()['retry-after']
  if (!value || !/^[1-9]\d*$/.test(value) || Number(value) > 60) {
    throw new Error('Expected bounded Retry-After (1..60 seconds)')
  }
  // Test-only pacing of the shared user limiter; never retries auth/budget/provider failures.
  await wait(Number(value) * 1000)
  return send() // at most once; the caller still requires HTTP200 and its original success/result assertions
}
