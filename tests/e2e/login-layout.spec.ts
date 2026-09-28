import { expect, test } from '@playwright/test'

test('关闭未登录提示时登录卡片保持原位', async ({ page }) => {
  for (const width of [1400, 744]) {
    await page.setViewportSize({ width, height: 900 })
    await page.goto('/teacher')
    const notice = page.locator('.auth-layout__notice')
    const card = page.locator('.auth-layout__card')
    await expect(notice).toBeVisible()
    const before = await card.boundingBox()
    const banner = await notice.boundingBox()
    expect(before).not.toBeNull()
    expect(banner).not.toBeNull()
    expect(banner!.y + banner!.height).toBeLessThan(before!.y)

    await page.getByRole('button', { name: '关闭提示' }).click()
    await expect(notice).toBeHidden()
    const after = await card.boundingBox()
    expect(after).not.toBeNull()
    expect(Math.abs(after!.y - before!.y)).toBeLessThan(1)
  }
})
