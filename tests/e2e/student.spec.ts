import { addStudent, apiLogin, call, createCourse, draftNodes, publish, uploadAndWait } from './api'
import { appUrl, expect, login, studentPassword, studentUsername, teacherPassword, teacherUsername, test } from './fixtures'

// K06 学生主线：浏览已发布图谱 → 标记掌握 → 推荐更新 → 有出处问答；
// 负例：跨课程拒绝、草稿修改不可见（旧发布版稳定）、无来源答案不以完成态显示。
// 需要能抽取中文定义句的模型：scripts/e2e.sh 缺省用演示模型（LLM_MODE=demo）。

const notes = [
  '# 第3章 栈与队列',
  '',
  '## 3.1 栈',
  '',
  '栈是一种只允许在一端进行插入和删除的线性表，这一端称为栈顶。栈的特点是后进先出。',
  '',
  '## 3.2 队列',
  '',
  '队列是一种只允许在一端插入、在另一端删除的线性表，特点是先进先出。学习队列之前需要先掌握栈。',
  '',
  '循环队列是用数组实现队列的一种方式，队满时尾指针的下一个位置是头指针。',
  '',
].join('\n')

test.afterEach(async ({ page }, info) => {
  if (info.status === info.expectedStatus) return
  await info.attach('failure.png', { body: await page.screenshot({ fullPage: true }), contentType: 'image/png' })
  await info.attach('failure.html', { body: await page.content(), contentType: 'text/html' })
})

test('学生浏览已发布图谱、标记掌握、获得推荐并得到带出处的回答；看不到草稿与他课', async ({ page, request }) => {
  test.setTimeout(240_000)
  const stamp = Date.now()

  // 准备：教师建两门课，只把学生加入 A；A 上传资料并发布 v1，B 不含该学生。
  const teacher = await apiLogin(request, teacherUsername, teacherPassword)
  const courseA = await createCourse(teacher, `K06 栈与队列 ${stamp}`)
  const courseB = await createCourse(teacher, `K06 他课 ${stamp}`)
  await addStudent(teacher, courseA, studentUsername)
  await uploadAndWait(teacher, courseA, 'stack-queue.md', 'text/markdown', Buffer.from(notes))
  expect(await publish(teacher, courseA)).toBe(1)
  const publishedNames = (await draftNodes(teacher, courseA)).map((node) => node.name)
  expect(publishedNames.length).toBeGreaterThanOrEqual(2)

  // 1. 课程列表只含 A；图谱页显示已发布 v1
  await login(page, studentUsername, studentPassword)
  await expect(page.getByRole('link', { name: `K06 栈与队列 ${stamp}` })).toBeVisible()
  await expect(page.getByRole('link', { name: `K06 他课 ${stamp}` })).toHaveCount(0)
  await page.goto(`${appUrl}/courses/${courseA}/graph`)
  await expect(page.locator('[data-test=student-graph-page]')).toBeVisible()
  await expect(page.locator('[data-test=sg-version]')).toContainText('v1')
  await expect(page.locator('[data-test=sg-graph]')).toBeVisible()

  // 2. 推荐列表给出可学知识点和服务端理由；选中第一项并标记为已掌握
  const recommendations = page.locator('[data-test=recommendations]')
  await expect(recommendations.locator('[data-test=rc-item]').first()).toBeVisible()
  await expect(recommendations.locator('[data-test=rc-reason]').first()).not.toBeEmpty()
  const firstSelect = recommendations.locator('[data-test^=rc-select-]').first()
  const selectTestId = (await firstSelect.getAttribute('data-test'))!
  const firstName = (await firstSelect.innerText()).trim()
  await firstSelect.click()
  await expect(page.locator('[data-test=sg-mastery-target]')).toContainText(firstName.split(/\s/)[0])
  const mastered = page.locator('[data-test=sg-mastery-mastered]')
  await mastered.click()
  await expect(mastered).toHaveAttribute('aria-pressed', 'true')
  // 已掌握的知识点不再作为推荐出现（推荐按服务端结果刷新）
  await expect(recommendations.locator(`[data-test="${selectTestId}"]`)).toHaveCount(0)

  // 刷新后掌握状态由服务端恢复，而非前端残留
  await page.reload()
  await expect(page.locator('[data-test=sg-version]')).toContainText('v1')
  const progress = await call(await apiLogin(request, studentUsername, studentPassword), 'GET', `/api/v1/courses/${courseA}/progress`)
  expect(progress.status()).toBe(200)
  expect(JSON.stringify(await progress.json())).toContain('mastered')

  // 3. 草稿不可见、旧发布版稳定：教师改名一个节点（草稿修订），学生仍只看到 v1 的名称
  const [target] = await draftNodes(teacher, courseA)
  const draftName = `草稿改名${stamp}`
  const edit = await call(teacher, 'PATCH', `/api/v1/courses/${courseA}/kp/${target.id}`, { name: draftName, expected_revision: target.revision })
  expect(edit.status(), await edit.text()).toBe(200)
  await page.reload()
  await expect(page.locator('[data-test=sg-version]')).toContainText('v1')
  await page.locator('[data-test=sg-mode-cards]').click()
  await expect(page.locator('[data-test=knowledge-cards]')).toBeVisible()
  await expect(page.locator('[data-test=knowledge-cards]')).toContainText(target.name)
  await expect(page.locator('body')).not.toContainText(draftName)

  // 4. 跨课程拒绝：直接访问 B 的图谱页被拒，接口同样 403
  await page.goto(`${appUrl}/courses/${courseB}/graph`)
  await expect(page.locator('[data-test=student-graph-page]')).toHaveCount(0)
  await expect(page.getByText(/无权|没有权限|不是.*成员|无法访问/).first()).toBeVisible()
  const student = await apiLogin(request, studentUsername, studentPassword)
  expect((await call(student, 'GET', `/api/v1/courses/${courseB}/graph?version=1`)).status()).toBe(403)

  // 5. 有出处问答：覆盖问题得到带可点击引用的回答，点开能看到原文
  await page.goto(`${appUrl}/courses/${courseA}/chat`)
  const input = page.getByLabel('向课程助教提问')
  await input.fill('什么是栈')
  await page.getByRole('button', { name: '发送' }).click()
  const answered = page.locator('.exchange').nth(0)
  const citation = answered.locator('button.citation').first()
  await expect(citation).toBeVisible({ timeout: 30_000 })
  await expect(answered.locator('.answer')).toContainText('栈')
  await citation.click()
  const source = page.getByRole('complementary', { name: '引用原文' })
  await expect(source).toBeVisible()
  await expect(source.locator('blockquote')).toContainText('栈')

  // 6. 资料未覆盖：不显示为完成的回答，也没有引用
  await input.fill('今天天气怎么样')
  await page.getByRole('button', { name: '发送' }).click()
  const uncovered = page.locator('.exchange').nth(1)
  await expect(uncovered.getByText('资料未覆盖')).toBeVisible({ timeout: 30_000 })
  await expect(uncovered.locator('button.citation')).toHaveCount(0)
})
