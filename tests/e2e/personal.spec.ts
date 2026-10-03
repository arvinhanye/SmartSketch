import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import type { Page } from '@playwright/test'
import { addStudent, apiLogin, createCourse } from './api'
import { appUrl, expect, login, studentPassword, studentUsername, teacherPassword, teacherUsername, test } from './fixtures'

// L11（计划 B）个人模式端到端：LLM_MODE=personal，教师和学生在设置页填写本机假供应商
// （scripts/fake_provider.py，包装演示模型，证明接线而不是模型质量）。资料为 datasets/contest 的自编一章
// （文本型 PDF + Markdown）。经 `E2E_LLM_MODE=personal scripts/e2e.sh tests/e2e/personal.spec.ts` 运行。

const personal = process.env.LLM_MODE === 'personal'
const providerUrl = process.env.E2E_PROVIDER_URL ?? ''
const course1 = 'datasets/contest/course1-ds-ch3'

function file(relative: string, mimeType: string) {
  const path = join(process.cwd(), relative)
  return { name: relative.split('/').at(-1)!, mimeType, buffer: readFileSync(path) }
}

async function configureModel(page: Page, key: string, expectOk: boolean): Promise<void> {
  await page.goto(`${appUrl}/settings/model`)
  await expect(page.locator('[data-test=mc-form]')).toBeVisible()
  await page.locator('[data-test=mc-base-url]').fill(providerUrl)
  await page.locator('[data-test=mc-model]').fill('fake-model')
  await page.locator('[data-test=mc-api-key]').fill(key)
  await page.locator('[data-test=mc-test]').click()
  await expect(page.locator('[data-test=mc-test-result]')).toContainText(expectOk ? '连接成功' : '密钥被拒绝')
  await page.locator('[data-test=mc-save]').click()
  await expect(page.locator('[data-test=mc-status]')).toContainText('已配置')
}

async function uploadThroughPage(page: Page, courseId: string, upload: ReturnType<typeof file>): Promise<void> {
  await page.goto(`${appUrl}/courses/${courseId}/materials`)
  await expect(page.locator('[data-test=materials-page]')).toBeVisible()
  await page.locator('[data-test=material-file-input]').setInputFiles(upload)
  await page.locator('[data-test=upload-submit]').click()
  await expect(page.locator('[data-test=upload-success]')).toContainText(upload.name)
}

function materialRow(page: Page, name: string) {
  return page.locator('[data-test=material-row]').filter({ hasText: name })
}

function escapeRegExp(text: string): string {
  return text.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
}

/** 学生图谱：切到「卡片」视图（键盘可用的视图），用搜索框按名称过滤（卡片分页），返回名称完全相同的卡片 */
async function studentCards(page: Page, name: string) {
  await page.locator('[data-test=sg-mode-cards]').click()
  await page.getByPlaceholder('搜索知识点').fill(name)
  return page.locator('[data-test=kc-card]').filter({
    has: page.locator('.knowledge-cards__name', { hasText: new RegExp(`^${escapeRegExp(name)}$`) }),
  })
}

async function selectDraftNode(page: Page, name: string): Promise<void> {
  // 画布之外的可访问选择方式（键盘与自动化都可用）
  await page.locator('[data-test=tg-node-picker]').selectOption({ label: name })
}

test.afterEach(async ({ page }, info) => {
  if (info.status === info.expectedStatus) return
  await info.attach('failure.png', { body: await page.screenshot({ fullPage: true }), contentType: 'image/png' })
  await info.attach('failure.html', { body: await page.content(), contentType: 'text/html' })
})

test.describe('个人模式（L11）', () => {
  test.skip(!personal, '只在 E2E_LLM_MODE=personal 下运行')

  test('教师 PDF+MD 闭环：配置 API → 上传 → 进度 → 草稿修正 → 发布 → 学生可见', async ({ page, browser, request }) => {
    test.setTimeout(480_000)
    const stamp = Date.now()
    const pdf = file(`${course1}/ch3-stack-queue.pdf`, 'application/pdf')
    const md = file(`${course1}/ch3-stack-queue.md`, 'text/markdown')

    // 1. 教师配置个人 API（测试连接后保存）
    await login(page, teacherUsername, teacherPassword)
    await configureModel(page, 'sk-fake-good', true)

    // 2. 建课、加入学生
    const teacher = await apiLogin(request, teacherUsername, teacherPassword)
    const courseId = await createCourse(teacher, `L11 栈与队列 ${stamp}`)
    await addStudent(teacher, courseId, studentUsername)

    // 3. 网页上传 PDF；处理中刷新页面，进度从服务端恢复；再上传 Markdown；两份都到待审核
    await uploadThroughPage(page, courseId, pdf)
    await page.reload()
    await expect(materialRow(page, pdf.name)).toBeVisible()
    await page.locator('[data-test=material-file-input]').setInputFiles(md)
    await page.locator('[data-test=upload-submit]').click()
    await expect(page.locator('[data-test=upload-success]')).toContainText(md.name)
    for (const name of [pdf.name, md.name]) {
      await expect(materialRow(page, name).locator('[data-test=material-status]')).toHaveText('待审核', { timeout: 240_000 })
    }

    // 4. 草稿修正：修改定义、删除一个节点（相连关系一并删除）、以选中节点的来源新建一个节点
    await page.goto(`${appUrl}/courses/${courseId}/graph/edit`)
    await expect(page.locator('[data-test=tg-graph]')).toBeVisible()
    await expect(page.locator('[data-test=tg-draft]')).toBeVisible()
    const names = await page.locator('[data-test=tg-node-picker] option:not([value=""])').allTextContents()
    expect(names.length).toBeGreaterThanOrEqual(3)
    // 只挑名称唯一的节点做修改与删除，学生端按名称核对时不会混到另一份资料抽出的同名节点
    const trimmed = names.map((name) => name.trim())
    const unique = trimmed.filter((name) => trimmed.indexOf(name) === trimmed.lastIndexOf(name))
    expect(unique.length).toBeGreaterThanOrEqual(2)
    const [edited, removed] = unique

    await selectDraftNode(page, edited)
    await page.locator('[data-test=tg-tab-edit]').click()
    await page.locator('[data-test=ne-definition]').fill('L11 教师修改后的定义')
    await page.locator('[data-test=ne-save]').click()
    await expect(page.locator('[data-test=ne-notice]')).toContainText('已保存')

    await page.locator('[data-test=tg-create-open]').click()
    await page.locator('[data-test=tg-create-name]').fill('L11 教师新增知识点')
    await page.locator('[data-test=tg-create-definition]').fill('教师根据资料补充的知识点。')
    await page.locator('[data-test=tg-create-submit]').click()
    await expect(page.locator('[data-test=tg-create-success]')).toContainText('L11 教师新增知识点')

    // 同一章 PDF 与 Markdown 各抽取一遍，草稿里可能有同名节点（跨任务融合不在本期，R05 如实记录）
    const sameName = page.locator('[data-test=tg-node-picker] option').filter({ hasText: new RegExp(`^${escapeRegExp(removed)}$`) })
    const before = await sameName.count()
    await selectDraftNode(page, removed)
    await page.locator('[data-test=tg-tab-edit]').click()
    await page.locator('[data-test=ne-delete]').click()
    await page.locator('[data-test=ne-delete-yes]').click()
    // 删除后面板清空选中，提示在页面级（与它相连的关系一并删除）
    await expect(page.locator('[data-test=tg-notice]')).toContainText('与它相连的关系已一并删除')
    await expect(sameName).toHaveCount(before - 1)

    // 5. 新增先修关系成环被拒
    await page.locator('[data-test=tg-tab-relations]').click()
    const form = page.locator('.relation-editor__form')
    const options = await form.locator('select[name=from] option:not([disabled])').evaluateAll((elements) =>
      elements.map((element) => ({ id: (element as HTMLOptionElement).value, name: element.textContent?.trim() ?? '' })))
    const [a, b] = options
    await form.locator('select[name=from]').selectOption(a.id)
    await form.locator('select[name=to]').selectOption(b.id)
    await form.locator('select[name=type]').selectOption('PREREQUISITE')
    await form.getByRole('button', { name: '添加关系' }).click()
    await expect(page.locator('.relation-editor__status')).toContainText(`已添加关系：${a.name} → ${b.name}`)
    await form.locator('select[name=from]').selectOption(b.id)
    await form.locator('select[name=to]').selectOption(a.id)
    await form.getByRole('button', { name: '添加关系' }).click()
    await expect(page.getByTestId('cycle-conflict')).toContainText('前置关系会形成环路')

    // 6. 发布
    await page.goto(`${appUrl}/courses/${courseId}/review`)
    await page.locator('[data-test=vp-publish]').click()
    await expect(page.locator('[data-test=vp-current]')).toContainText('学生当前看到 v1', { timeout: 180_000 })

    // 7. 学生：未配置时被引导；配置后看到发布版并得到带出处的回答
    const studentContext = await browser.newContext()
    try {
      const student = await studentContext.newPage()
      await login(student, studentUsername, studentPassword)
      await student.goto(`${appUrl}/courses/${courseId}/chat`)
      const required = student.locator('[data-test=model-config-required]')
      if (await required.isVisible()) await expect(student.locator('[data-test=chat-send]')).toBeDisabled()
      await configureModel(student, 'sk-fake-good', true)

      await student.goto(`${appUrl}/courses/${courseId}/graph`)
      await expect(student.locator('[data-test=sg-version]')).toContainText('v1')
      await expect(await studentCards(student, 'L11 教师新增知识点')).toHaveCount(1)
      await expect(await studentCards(student, removed)).toHaveCount(before - 1)

      await student.goto(`${appUrl}/courses/${courseId}/chat`)
      await student.locator('textarea').fill('什么是栈？')
      await student.locator('[data-test=chat-send]').click()
      await expect(student.locator('.source-list__item').first()).toBeVisible({ timeout: 60_000 })

      // 8. 教师发布后再改草稿：学生看到的仍是发布版的定义
      await page.goto(`${appUrl}/courses/${courseId}/graph/edit`)
      await selectDraftNode(page, edited)
      await page.locator('[data-test=tg-tab-edit]').click()
      await page.locator('[data-test=ne-definition]').fill('L11 发布之后的草稿修改')
      await page.locator('[data-test=ne-save]').click()
      await expect(page.locator('[data-test=ne-notice]')).toContainText('已保存')

      await student.goto(`${appUrl}/courses/${courseId}/graph`)
      await (await studentCards(student, edited)).first().click()
      await expect(student.locator('[data-test=kd-definition]')).toHaveText('L11 教师修改后的定义')
    } finally {
      await studentContext.close()
    }
  })

  test('处理中取消任务：转为已取消；换回正常密钥后重新选择同一文件上传成功', async ({ page, request }) => {
    test.setTimeout(300_000)
    const md = file(`${course1}/ch3-stack-queue.md`, 'text/markdown')
    await login(page, teacherUsername, teacherPassword)
    // sk-fake-slow：假供应商每次调用先等几秒，留出在处理中点「取消」的时间
    await configureModel(page, 'sk-fake-slow', true)
    const teacher = await apiLogin(request, teacherUsername, teacherPassword)
    const courseId = await createCourse(teacher, `L11 取消与重传 ${Date.now()}`)
    await uploadThroughPage(page, courseId, md)
    const row = materialRow(page, md.name).first()
    await expect(row.locator('[data-test=material-status]')).toHaveText(/排队中|解析中|抽取中/)
    await row.locator('[data-test=task-cancel]').click()
    await expect(row.locator('[data-test=material-status]')).toHaveText('已取消', { timeout: 120_000 })

    await configureModel(page, 'sk-fake-good', true)
    // 离开页面后浏览器不再持有原文件，页面提示「请重新选择文件上传」（不提供一键重传）
    await uploadThroughPage(page, courseId, md)
    const done = page.locator('[data-test=material-row]').filter({ hasText: md.name })
      .filter({ has: page.locator('[data-test=material-status]', { hasText: '待审核' }) })
    await expect(done).toHaveCount(1, { timeout: 180_000 })
  })

  test('供应商拒绝密钥：任务终止并引导检查配置', async ({ page, request }) => {
    test.setTimeout(240_000)
    const md = file(`${course1}/ch3-stack-queue.md`, 'text/markdown')
    await login(page, teacherUsername, teacherPassword)
    await configureModel(page, 'sk-fake-bad', false)
    const teacher = await apiLogin(request, teacherUsername, teacherPassword)
    const courseId = await createCourse(teacher, `L11 密钥被拒 ${Date.now()}`)
    await uploadThroughPage(page, courseId, md)
    const row = materialRow(page, md.name)
    await expect(row.locator('[data-test=material-status]')).toHaveText('处理失败', { timeout: 120_000 })
    await expect(row.locator('[data-test=task-error]')).toContainText('模型 API 设置')
    await configureModel(page, 'sk-fake-good', true)   // 复原，避免影响后续用例
  })
})
