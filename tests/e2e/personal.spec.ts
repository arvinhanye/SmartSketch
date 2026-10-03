import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import type { Page } from '@playwright/test'
import { addStudent, apiLogin, call, createCourse, draftNodes, publish, registerStudent, uploadAndWait } from './api'
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

/** 点开详情里的第一条来源：文件名是本课资料，位置与格式相符；可收起 */
async function expectSourceViewer(page: Page): Promise<void> {
  await page.locator('[data-test=kd-source-locate]').first().click()
  const viewer = page.locator('[data-test=source-viewer]')
  await expect(viewer.locator('[data-test=sv-document]')).toHaveText(/^ch3-stack-queue\.(pdf|md)$/)
  const name = (await viewer.locator('[data-test=sv-document]').textContent()) ?? ''
  await expect(viewer.locator('[data-test=sv-location]')).toHaveText(name.endsWith('.pdf') ? /第 \d+ 页/ : /\S/)
  await viewer.locator('[data-test=sv-close]').click()
  await expect(viewer).toHaveCount(0)
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
    const names = (await page.locator('[data-test=tg-node-picker] option:not([value=""])').allTextContents())
      .map((name) => name.trim())
    expect(names.length).toBeGreaterThanOrEqual(3)
    // 同一章 PDF 与 Markdown 各抽取一遍，AI 节点多为同名（跨任务融合不在本期，R05）；
    // 修改定义与「发布后改草稿」都用教师新建的节点（名称唯一），删除按同名数量减 1 断言。
    const edited = 'L11 教师新增知识点'
    const removed = names[names.length - 1]!

    // L12：教师图谱的来源可点开，显示资料文件名与对应格式的位置（PDF 页码 / Markdown 章节）
    await selectDraftNode(page, names[0]!)
    await page.locator('[data-test=tg-tab-detail]').click()
    await expectSourceViewer(page)

    // 以选中节点的来源新建知识点，再修改它的定义
    await page.locator('[data-test=tg-create-open]').click()
    await page.locator('[data-test=tg-create-name]').fill(edited)
    await page.locator('[data-test=tg-create-definition]').fill('教师根据资料补充的知识点。')
    await page.locator('[data-test=tg-create-submit]').click()
    await expect(page.locator('[data-test=tg-create-success]')).toContainText(edited)
    await selectDraftNode(page, edited)
    await page.locator('[data-test=tg-tab-edit]').click()
    await page.locator('[data-test=ne-definition]').fill('L11 教师修改后的定义')
    await page.locator('[data-test=ne-save]').click()
    await expect(page.locator('[data-test=ne-notice]')).toContainText('已保存')

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
      await expect(await studentCards(student, edited)).toHaveCount(1)
      await expect(await studentCards(student, removed)).toHaveCount(before - 1)

      await student.goto(`${appUrl}/courses/${courseId}/chat`)
      await student.locator('textarea').fill('什么是栈？')
      await student.locator('[data-test=chat-send]').click()
      await expect(student.locator('.source-list__item').first()).toBeVisible({ timeout: 60_000 })
      // L12：问答引用带文件名，位置与格式相符
      for (const text of await student.locator('.source-list__item').allTextContents()) {
        expect(text).toMatch(/ch3-stack-queue\.(pdf · 第 \d+ 页|md · \S)/)
      }

      // L13：从问答点知识点跳到图谱并选中同一节点；刷新直达仍选中
      const chip = student.locator('[data-test=chat-kp]').first()
      await expect(chip).not.toHaveText(/^kp_/)        // 问答页读完已发布图谱后，按钮显示知识点名称
      const chipName = ((await chip.textContent()) ?? '').trim()
      await chip.click()
      await expect(student).toHaveURL(new RegExp(`/courses/${courseId}/graph\\?kp=`))
      await expect(student.locator('[data-test=kd-title]')).toHaveText(chipName)
      await student.reload()
      await expect(student.locator('[data-test=kd-title]')).toHaveText(chipName)

      // L13：20+ 节点时初始视口不低于可读缩放；搜索回车定位并选中
      const canvas = student.locator('[data-test=graph-canvas]')
      await expect(canvas).toHaveAttribute('data-zoom', /\d/)
      expect(Number(await canvas.getAttribute('data-zoom'))).toBeGreaterThanOrEqual(0.7)
      const label = (await student.locator('.graph-canvas__stage').getAttribute('aria-label')) ?? ''
      expect(Number(/(\d+) 个知识点/.exec(label)?.[1] ?? 0)).toBeGreaterThanOrEqual(20)
      await student.getByPlaceholder('搜索知识点').fill(edited)
      await student.getByPlaceholder('搜索知识点').press('Enter')
      await expect(student.locator('[data-test=kd-title]')).toHaveText(edited)

      // L14：把推荐第 1 项标为已掌握 → 推荐与路径行更新、刷新保留；另一个学生不受影响；取消后恢复
      await student.goto(`${appUrl}/courses/${courseId}/graph`)
      const items = student.locator('[data-test=recommendations] [data-test=rc-item]')
      const pathLine = student.locator('[data-test=rc-path-line]')
      await expect(pathLine).toContainText('下一步：')
      const firstId = (await items.first().getAttribute('data-kp-id'))!
      const firstLine = ((await pathLine.textContent()) ?? '').trim()
      await expect(items.first().locator('[data-test=rc-order]')).toHaveText('1.')
      await student.locator(`[data-test="rc-select-${firstId}"]`).click()
      await student.locator('[data-test=sg-mastery-mastered]').click()
      await expect(student.locator('[data-test=sg-learning-notice]')).toContainText('已标记为已掌握')
      await expect(student.locator(`[data-test="rc-select-${firstId}"]`)).toHaveCount(0)
      await expect(pathLine).not.toHaveText(firstLine)
      await student.reload()
      await expect(items.first()).toBeVisible()
      await expect(student.locator(`[data-test="rc-select-${firstId}"]`)).toHaveCount(0)

      const otherName = `l14_s2_${stamp}`
      await registerStudent(request, otherName, studentPassword)
      await addStudent(teacher, courseId, otherName)
      const otherContext = await browser.newContext()
      try {
        const other = await otherContext.newPage()
        await login(other, otherName, studentPassword)
        await other.goto(`${appUrl}/courses/${courseId}/graph?kp=${firstId}`)
        await expect(other.locator('[data-test=sg-mastery-target]')).toContainText('当前：未开始')
        await expect(other.locator('[data-test=recommendations] [data-test=rc-item]').first()).toHaveAttribute('data-kp-id', firstId)
      } finally {
        await otherContext.close()
      }

      await student.goto(`${appUrl}/courses/${courseId}/graph?kp=${firstId}`)
      await expect(student.locator('[data-test=sg-mastery-target]')).toContainText('当前：已掌握')
      await student.locator('[data-test=sg-mastery-unknown]').click()
      await expect(student.locator('[data-test=sg-learning-notice]')).toContainText('已标记为未开始')
      await expect(items.first()).toHaveAttribute('data-kp-id', firstId)
      await expect(pathLine).toHaveText(firstLine)

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
      await expectSourceViewer(student)   // L12：学生图谱同样能查看来源
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
  test('L15 两门课：成员权限、图谱、进度、推荐和问答出处互不串课', async ({page, browser, request}) => {
    test.setTimeout(480_000)
    await login(page, teacherUsername, teacherPassword)
    await configureModel(page, 'sk-fake-good', true)
    const teacher = await apiLogin(request, teacherUsername, teacherPassword)
    const first = await createCourse(teacher, `L15 数据结构 ${Date.now()}`)
    const second = await createCourse(teacher, `L15 操作系统 ${Date.now()}`)
    for (const [cid, relative] of [[first, `${course1}/ch3-stack-queue.md`], [second, 'datasets/contest/course2-os-ch2/ch2-process-thread.md']]) {
      const upload = file(relative, 'text/markdown')
      await uploadAndWait(teacher, cid, upload.name, upload.mimeType, upload.buffer)
      await publish(teacher, cid)
    }
    const username = `l15_student_${Date.now()}`
    await registerStudent(request, username, studentPassword)
    await addStudent(teacher, first, username)
    const studentApi = await apiLogin(request, username, studentPassword)
    const firstNode = (await draftNodes(teacher, first))[0]!
    for (const suffix of ['/graph', '/progress', '/recommend', `/kp/${firstNode.id}`]) {
      const forbidden = await call(studentApi, 'GET', `/api/v1/courses/${second}${suffix}`)
      expect(forbidden.status()).toBe(403)
      expect(await forbidden.text()).not.toContain('ch2-process-thread')
    }
    await addStudent(teacher, second, username)
    const context = await browser.newContext()
    try {
      const student = await context.newPage()
      await login(student, username, studentPassword)
      await configureModel(student, 'sk-fake-good', true)
      await student.goto(`${appUrl}/courses/${first}/graph`)
      const masteredId = (await student.locator('[data-test=recommendations] [data-test=rc-item]').first().getAttribute('data-kp-id'))!
      await student.locator(`[data-test="rc-select-${masteredId}"]`).click()
      await student.locator('[data-test=sg-mastery-mastered]').click()
      await expect(student.locator('[data-test=sg-learning-notice]')).toContainText('已标记为已掌握')
      for (const [cid, question, filename] of [[first, '什么是栈？', 'ch3-stack-queue.md'], [second, '什么是进程？', 'ch2-process-thread.md']]) {
        await student.goto(`${appUrl}/courses/${cid}/graph`)
        await expect(student.locator('[data-test=sg-version]')).toContainText('v1')
        const graph = await (await call(studentApi, 'GET', `/api/v1/courses/${cid}/graph`)).json()
        expect(graph.course_id).toBe(cid)
        const ids = new Set(graph.nodes.map((n: {id: string}) => n.id))
        const recommendations = await (await call(studentApi, 'GET', `/api/v1/courses/${cid}/recommend`)).json()
        for (const item of recommendations.recommendations) expect(ids.has(item.kp_id)).toBe(true)
        const progress = await (await call(studentApi, 'GET', `/api/v1/courses/${cid}/progress`)).json()
        expect(progress.entries.every((entry: {kp_id: string}) => ids.has(entry.kp_id))).toBe(true)
        if (cid === second) expect(progress.entries.every((entry: {status: string}) => entry.status === 'unknown')).toBe(true)
        await student.goto(`${appUrl}/courses/${cid}/chat`)
        expect(await student.locator('.conversation .exchange').count()).toBe(0)
        await student.locator('textarea').fill(question)
        await student.locator('[data-test=chat-send]').click()
        await expect(student.locator('.source-list__item').first()).toBeVisible({timeout: 60_000})
        for (const text of await student.locator('.source-list__item').allTextContents()) expect(text).toContain(filename)
        const foreign = cid === first ? 'ch2-process-thread.md' : 'ch3-stack-queue.md'
        expect(await student.locator('.source-list').textContent()).not.toContain(foreign)
      }
      const persisted = await (await call(studentApi, 'GET', `/api/v1/courses/${first}/progress`)).json()
      expect(persisted.entries.find((e: {kp_id: string}) => e.kp_id === masteredId).status).toBe('mastered')
    } finally { await context.close() }
  })

})
