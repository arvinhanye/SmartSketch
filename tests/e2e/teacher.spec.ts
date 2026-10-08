import { appUrl, expect, fourFormats, login, studentPassword, studentUsername, teacherPassword, teacherUsername, test } from './fixtures'

test.afterEach(async ({ page }, info) => {
  if (info.status === info.expectedStatus) return
  await info.attach('failure.png', { body: await page.screenshot({ fullPage: true }), contentType: 'image/png' })
  await info.attach('failure.html', { body: await page.content(), contentType: 'text/html' })
})

test('教师上传四格式资料、编辑并审核图谱、拒绝成环关系，发布后学生可见', async ({ page, browser }) => {
  test.setTimeout(240_000)
  const courseName = `K05 栈与队列 ${Date.now()}`

  await login(page, teacherUsername, teacherPassword)
  // 新版课程页把创建表单收进弹层：先点「新建课程」再填写
  await page.locator('[data-test=course-create-open]').click()
  await page.locator('[data-test=course-create] input[name=name]').fill(courseName)
  await page.locator('[data-test=course-create] button[type=submit]').click()
  await expect(page.locator('[data-test=create-success]')).toContainText(courseName)
  await page.locator('[data-test=course-card]').filter({ hasText: courseName }).getByRole('link').click()
  const courseId = new URL(page.url()).pathname.split('/').at(-1)!

  await page.locator('[data-test=members-link]').click()
  await page.locator('[data-test=member-add] input[name=username]').fill(studentUsername)
  await page.locator('[data-test=member-add] button[type=submit]').click()
  await expect(page.locator('[data-test=member-add-success]')).toBeVisible()

  await page.goto(`${appUrl}/courses/${courseId}/materials`)
  await expect(page.locator('[data-test=materials-page]')).toBeVisible()

  // The first request fails at the transport boundary; retry sends the same file to the real API.
  let failOnce = true
  const uploadPattern = `**/api/v1/courses/${courseId}/documents`
  await page.route(uploadPattern, async route => {
    if (failOnce && route.request().method() === 'POST') {
      failOnce = false
      await route.abort('failed')
    } else {
      await route.continue()
    }
  })
  const first = fourFormats[0]
  await page.locator('[data-test=material-file-input]').setInputFiles(first)
  await page.locator('[data-test=upload-submit]').click()
  await expect(page.locator('[data-test=upload-error]')).toBeVisible()
  await page.unroute(uploadPattern)
  await page.locator('[data-test=upload-retry]').click()
  await expect(page.locator('[data-test=upload-success]')).toContainText(first.name)

  for (const file of fourFormats.slice(1)) {
    await page.locator('[data-test=material-file-input]').setInputFiles(file)
    await page.locator('[data-test=upload-submit]').click()
    await expect(page.locator('[data-test=upload-success]')).toContainText(file.name)
  }
  for (const file of fourFormats) {
    const row = page.locator('[data-test=material-row]').filter({ hasText: file.name })
    await expect(row.locator('[data-test=material-status]')).toHaveText('待审核', { timeout: 120_000 })
  }

  await page.goto(`${appUrl}/courses/${courseId}/graph/edit`)
  await expect(page.locator('[data-test=teacher-graph-page]')).toBeVisible()
  await expect(page.locator('[data-test=tg-graph]')).toBeVisible()
  await page.locator('[data-test=tg-tab-relations]').click()
  const form = page.locator('.relation-editor__form')
  const options = await form.locator('select[name=from] option:not([disabled])').evaluateAll(elements =>
    elements.map(element => ({ id: (element as HTMLOptionElement).value, name: element.textContent?.trim() ?? '' })),
  )
  expect(options.length).toBeGreaterThanOrEqual(2)
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

  await page.goto(`${appUrl}/courses/${courseId}/review`)
  await expect(page.locator('[data-test=review-page]')).toBeVisible()
  await expect(page.locator('[data-test=version-panel]')).toBeVisible()
  await page.locator('[data-test=vp-publish]').click()
  await expect(page.locator('[data-test=vp-current]')).toContainText('学生当前看到 v1', { timeout: 120_000 })
  await expect(page.locator('[data-test=vp-version]')).toContainText('v1')

  const student = await browser.newContext()
  try {
    const studentPage = await student.newPage()
    await login(studentPage, studentUsername, studentPassword)
    await studentPage.goto(`${appUrl}/courses/${courseId}/graph`)
    await expect(studentPage.locator('[data-test=sg-version]')).toContainText('v1')
    await expect(studentPage.locator('[data-test=sg-graph]')).toBeVisible()
  } finally {
    await student.close()
  }
})
