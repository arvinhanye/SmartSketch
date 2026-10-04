# SmartSketch 完整前端迁移与缺陷修复 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task; superpowers:subagent-driven-development is an alternative only when delegation is explicitly authorized. 使用下列复选框跟踪执行。

**Goal:** 修复当前 F1–F4，完成审核、图谱、问答及个人 API 设置的页面设计和交互迁移，并交付可复核的本地提交与验收记录。

**Architecture:** 以 68762e8 的后端、契约、前端业务逻辑为基础，把 27bff16 的展示结构、样式与局部交互适配到当前分支。数据请求继续经过当前 API/composable/store；新增状态仅用于分类、证据展开、服务商地址预设和结果弹窗。图谱主题通过 theme → GraphCanvas → lifecycle 传递，关系样式仍由 adapter 定义。

**Tech Stack:** Vue 3、TypeScript、Vite、Pinia、Vue Router、AntV G6、Vitest、Vue Test Utils；现有 FastAPI、SQLite、Neo4j 后端保持不变。

**Spec:** 本计划对应 2026-10-04 的 055d914 审查报告与本仓库 docs/handoffs/deepseek-frontend-migration.md；同时遵守 AGENTS.md、docs/architecture.md、specs/identity-access.md、specs/teacher-review-publish.md、specs/course-knowledge-graph.md、specs/grounded-qa.md 和 ADR-080。原始审查及截图位于仓库外 ../.review-artifacts/055d914-review.md；完整报告位于 ../.review-artifacts/055d914-complete-review.md。

## Global Constraints

- 当前审查基线：frontend-backend-refactor@055d91495bef79a7ca0dc492620553e1c3c6af87。
- 后端与业务基线：68762e8ab9efdfc20552a94668d7e26deb2e34c5。
- 界面来源：frontend-ui-revision@27bff16a67fa4e9b96416d3529069832b05e88ac。
- 执行前重新核对 HEAD 与工作区；如果基线之后有新提交，先检查它们是否已经修复本计划中的问题，保护其他人的改动。
- 后端、契约/生成物、数据库迁移、启动脚本、环境配置、前端 API、composable、store、router、main.ts 不属于本次修改范围。
- 基础设施与系统级配置只能从环境变量读取；个人模型凭据经现有个人配置接口写入、服务端加密存储。
- 不恢复 /api/v1/api-settings、全局 LLM 设置、JSON 覆盖环境变量、保存后重启、向量设置、向量测试或模型发现接口。
- 不持久化、回显、恢复或记录个人 API Key；来源 ApiSettings.vue 的 smartsketch.apiKeys/localStorage 逻辑禁止迁入。
- 关系类型仅限 CONTAINS、PREREQUISITE、RELATED_TO、EXAMPLE_OF；方向、线型、DAG 检查、课程权限与版本语义保持不变。
- 保留个人模型配置引导、发送锁、请求取消、会话隔离、晚到结果保护、操作互斥、演示标识和原有错误分类。
- 使用现有依赖，不升级包或引入新的 UI 框架；package.json 的 Node 范围为 ^22.22.2 || ^24.15.0 || >=26.0.0。
- 分批仅为验证和提交，执行范围是全部任务。完成某一批后继续下一批，不得把部分批次交付写成完整迁移。
- 必要检查后必须创建本地 Git 提交；仅暂存任务文件，不自动推送、不部署。交付分支、完整提交哈希、提交说明、检查结果；提交受阻必须如实说明。
- 本计划中的代码块是明确的改动或测试示例；合并时保留所在文件其他现有实现。来源参考是完整文件，不是授权整文件覆盖目标。

## Review Focus

1. 上传请求悬而未决时再次拖入文件：默认动作必须取消，不能替换已选文件或发起第二次上传；任务 1 用可取消真实 DOM 事件验证。
2. Tab 聚焦隐藏文件控件、取消文件选择：可见选择区必须有焦点反馈；任务 1 用真实浏览器检查 CSS 与焦点，而非仅靠 jsdom。
3. 用户同时拥有多门课并进入一门课程概览：其他课程卡片不应出现；任务 2 使用 c1/c2 夹具验证。
4. 审核页版本请求加载中或失败、随后切换课程：审核区域独立显示，展示状态正确重置，晚到响应不污染新课；任务 4 覆盖插槽和原有切课测试。
5. 模型测试未返回时改表单、退出或换号：旧结果不能标成当前配置已成功，新会话不接收旧结果；任务 7 保留 N03–N05 并增加弹窗与过期提示检查。

## 执行前的定位与参考

以下路径均相对实际 Git 仓库 SmartSketch_src，不是外层展示目录。

~~~powershell
# 在实际仓库根目录执行。
$migrationRepo = (Resolve-Path .).Path
git -c safe.directory="$migrationRepo" branch --show-current
git -c safe.directory="$migrationRepo" rev-parse HEAD
git -c safe.directory="$migrationRepo" status --short
git -c safe.directory="$migrationRepo" show 27bff16:src/frontend/src/views/ReviewView.vue
git -c safe.directory="$migrationRepo" diff 68762e8 27bff16 -- src/frontend/src/graph/lifecycle.ts src/frontend/src/graph/adapter.ts
~~~

来源提交的 18 个完整参考文件已经导出到仓库外 ../.review-artifacts/055d914-source-27bff16/src/frontend/src/，可直接阅读；Git 中的原提交仍是最终依据。参考包含旧 ApiSettings.vue，只用于识别卡片、排版和弹窗设计，不能复制其请求、持久化或向量代码。

阅读 docs/tasks.md 后，记录本次迁移任务、负责人、完整验收范围；已有任务被占用时，不改他人条目。每批提交更新 docs/handoffs/deepseek-frontend-migration.md，写清“已完成 / 未完成 / 验证受阻”，直到所有范围完成。

## 文件与职责

| 任务 | 实现文件 | 测试/证据 |
| --- | --- | --- |
| 1：F1/F2 | src/frontend/src/views/MaterialsView.vue | tests/frontend/h02.test.ts、真实浏览器焦点及拖放 |
| 2：F3 | src/frontend/src/views/CoursesView.vue | tests/frontend/h01.test.ts、概览截图 |
| 3：F4 | src/frontend/src/views/MembersView.vue | tests/frontend/h12.test.ts、1280/420px 布局证据 |
| 4：审核及版本 | src/frontend/src/views/ReviewView.vue、src/frontend/src/components/VersionPanel.vue | tests/frontend/h09.test.ts、h10.test.ts、h14.test.ts |
| 5：图谱 | graph/theme.ts、graph/lifecycle.ts、graph/adapter.ts；GraphCanvas、GraphToolbar、KnowledgeCards、KnowledgeDetail、NodeEditor、RelationEditor、Recommendations；TeacherGraphView、StudentGraphView | h03–h08、h11、h14、i06 |
| 6：问答 | src/frontend/src/views/ChatView.vue、src/frontend/src/components/ChatMarkdown.vue | redesign-chat、chat-send-lock、j08、j09、l10、d1-d3 |
| 7：个人设置 | src/frontend/src/views/ModelSettingsView.vue | l10、n03-n05、d1-d3；弹窗键盘/焦点及契约 |
| 8：整体验收 | docs/tasks.md、docs/handoffs/deepseek-frontend-migration.md | 全量前端检查、系统门禁、逐页验收记录 |

除主题文件外，默认不新建产品组件；结果弹窗可直接用 ModelSettingsView 内的原生 dialog，避免引入旧弹窗依赖。

## Task 1：修复资料拖放与键盘焦点（F1/F2）

**Files:** 修改 src/frontend/src/views/MaterialsView.vue 的 onDragOver/onDrop/clearSelection 与选择区焦点样式；补充 tests/frontend/h02.test.ts。

**Interfaces:** 消费现有 useMaterials 返回的 uploading、selectFile、submitUpload 和选择版本；不修改该 composable。输出仍是原单文件上传流程，额外保证文件拖放默认动作被取消、焦点可见。

- [ ] 在 h02.test.ts 使用已有 deferred、fakeMaterialsApi、mountPage、chooseFile、submitUpload、file 夹具增加以下测试。

~~~typescript
it('上传中再次拖入文件：取消默认动作且不发起第二次上传', async () => {
  const pending = deferred<{ task_id: string; document_id: string }>()
  const materials = fakeMaterialsApi({ upload: () => pending.promise })
  const { wrapper } = await mountPage({ materials })
  await chooseFile(wrapper, file('first.txt'))
  await submitUpload(wrapper)
  const zone = wrapper.get('[data-test="material-dropzone"]').element
  const events = ['dragover', 'drop'].map((name) => {
    const event = new Event(name, { bubbles: true, cancelable: true })
    Object.defineProperty(event, 'dataTransfer', {
      value: { types: ['Files'], files: [file('second.txt')], dropEffect: 'none' },
    })
    zone.dispatchEvent(event)
    return event
  })
  const cancelled = events.map((event) => event.defaultPrevented)
  expect(materials.upload).toHaveBeenCalledTimes(1)
  expect(wrapper.get('[data-test="selected-file-name"]').text()).toContain('first.txt')
  pending.resolve({ task_id: 't_drag', document_id: 'd_drag' })
  await flushPromises()
  expect(cancelled).toEqual([true, true])
})
~~~

- [ ] 先运行新增测试，确认当前实现因 defaultPrevented 为 false 而失败。

~~~powershell
# 下列 npm/node 命令均在 src/frontend 目录执行。
npm run test -- --run h02.test.ts --reporter=verbose --testTimeout=30000 --maxWorkers=2
~~~

- [ ] 将“识别文件 → preventDefault → 判断 uploading”的顺序写入处理函数。保留其余多文件、目录提示、格式/大小校验和成功清空逻辑。

~~~typescript
function onDragOver(event: DragEvent): void {
  if (!isFileDrag(event)) return
  event.preventDefault()
  if (event.dataTransfer !== null) {
    event.dataTransfer.dropEffect = uploading.value ? 'none' : 'copy'
  }
}

function onDrop(event: DragEvent): void {
  if (!isFileDrag(event)) return
  event.preventDefault()
  if (uploading.value) {
    resetDrag()
    return
  }
  const transfer = event.dataTransfer
  resetDrag()
  if (transfer === null) return
  const files = Array.from(transfer.files ?? [])
  if (files.length > 1) {
    dropNotice.value = '一次只能选择一个文件。'
    return
  }
  const file = files[0]
  if (file === undefined) {
    dropNotice.value = '不支持拖入文件夹，请选择单个资料文件。'
    return
  }
  dropNotice.value = null
  applySelection(file)
}
~~~

onDrop 在 !isFileDrag 返回之后立即调用 event.preventDefault()，然后才执行 uploading 分支；该分支 resetDrag() 后返回。非文件事件继续不做文件选择。不要在整个页面无条件取消所有 drop。

- [ ] 增加选择区 :focus-within，与 :focus-visible 使用相同 2px 主色 outline；clearSelection 最后改为 dropzone.value?.focus()。

~~~css
.dropzone:focus-visible,
.dropzone:focus-within {
  outline: 2px solid var(--color-primary);
  outline-offset: 2px;
}
~~~

- [ ] 使用真实浏览器：Tab 到选择区及 input，均能看见选择区轮廓；选文件后取消，焦点回到可见选择区；Enter/Space 可选文件；上传中不能重新选择。检查可见区域而不是要求隐藏 input 自身显示。
- [ ] 再运行 h02、l10、n03-n05；确认上传前个人配置提示、任务取消/重连/删除和晚到结果测试保留。

~~~powershell
npm run test -- --run h02.test.ts l10.test.ts n03-n05.test.ts --reporter=dot --testTimeout=30000 --maxWorkers=2
npm run type-check
~~~

- [ ] 更新交接并本地提交，提交说明：fix(frontend): preserve file-drop cancellation and visible upload focus。只暂存 MaterialsView.vue、h02.test.ts 和本批交接/任务文档。

## Task 2：恢复课程首页与概览的分离（F3）

**Files:** 修改 src/frontend/src/views/CoursesView.vue、tests/frontend/h01.test.ts。

**Interfaces:** 保留 useCourses、课程 store 和所有现有 route 名称；页面概览继续以 current-course 区域展示选中课程和功能入口。aria-current 不再绑定已经移除的课程卡片，改为检查实际当前课程的区域名称及路由语义。

- [ ] 使用 h01 的 fakeApi、course、mountApp 增加多课程用例。

~~~typescript
it('概览只显示当前课程，返回首页后才显示完整课程列表', async () => {
  const api = fakeApi({
    list: async () => [course('c1', { name: '当前课程甲' }), course('c2', { name: '其他课程乙' })],
    get: async (cid) => course(cid, { name: '当前课程甲' }),
  })
  const { wrapper } = await mountApp({ path: '/courses/c1', api })
  expect(wrapper.get('[data-test="current-course"]').text()).toContain('当前课程甲')
  expect(wrapper.findAll('[data-test="course-card"]')).toHaveLength(0)
  expect(wrapper.text()).not.toContain('其他课程乙')
  await wrapper.get('[data-test="back-to-courses"]').trigger('click')
  await flushPromises()
  expect(wrapper.findAll('[data-test="course-card"]')).toHaveLength(2)
})
~~~

- [ ] 运行 h01，确认上述用例失败；删除概览内 course-overview-list 整块循环，保留首页列表、详情、返回链接和功能入口。
- [ ] 保留当前课程区域已经存在的 :aria-labelledby="overviewTitleId" 与 <h3 :id="overviewTitleId">当前课程</h3>，无需再加固定 id。把 h01 旧的 course-card 链接 aria-current 结构断言替换为以下检查，继续保留原 store.courseId、API 请求参数与详情文本断言。不得删除课程权限、403 离课提示、快速切课、创建与迟到响应断言。

~~~typescript
const currentRegion = wrapper.get('[data-test="current-course"]')
const headingId = currentRegion.attributes('aria-labelledby')
expect(headingId).toBeTruthy()
expect(wrapper.get('#' + headingId).text()).toBe('当前课程')
expect(currentRegion.text()).toContain('数据结构')
~~~

更新概览上方描述“当前课程卡片”的旧注释为“当前课程详情与功能入口”，避免文档暗示仍应显示卡片。

- [ ] 运行 h01、h13、n03-n05；浏览器检查教师和学生首页、c1/c2 概览、返回首页、长课程名及 420px 宽度。

~~~powershell
npm run test -- --run h01.test.ts h13.test.ts n03-n05.test.ts --reporter=dot --testTimeout=30000 --maxWorkers=2
npm run type-check
~~~

- [ ] 更新交接并本地提交，提交说明：fix(frontend): keep the full course grid on the course home。只提交本任务页面、测试及文档。

## Task 3：修复成员页桌面同行布局（F4）

**Files:** 修改 src/frontend/src/views/MembersView.vue；使用现有 tests/frontend/h12.test.ts 回归标签及成员操作，不为 CSS 排版新增重复的结构测试。

**Interfaces:** 继续使用现有 username、adding、addMember；label 内只包含输入标签与 input，按钮在 label 外。桌面二者同行，窄屏允许按来源设计堆叠。

- [ ] 将同一个 members__field-row 同时包住现有 label 和添加按钮，不重写按钮的原内容、事件或输入控件属性。

~~~html
<div class="members__field">
  <div class="members__field-row">
    <label class="members__field-label" for="member-username">
      学生用户名
      <input
        id="member-username"
        v-model="username"
        name="username"
        type="text"
        autocomplete="off"
        placeholder="输入学生用户名"
        aria-label="学生用户名"
        required
      />
    </label>
    <button type="submit" class="members__submit" :disabled="adding">
      <svg class="members__submit-icon" viewBox="0 0 16 16" width="15" height="15" aria-hidden="true" focusable="false">
        <path d="M8 3.2v9.6M3.2 8h9.6" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" />
      </svg>
      {{ adding ? '添加中…' : '添加学生' }}
    </button>
  </div>
</div>
~~~

~~~css
.members__field-row {
  display: flex;
  align-items: flex-end;
  gap: 0.65rem;
}
.members__field-label {
  display: grid;
  flex: 1;
  min-width: 0;
  gap: 0.4rem;
}
.members__field-label input {
  width: 100%;
  min-width: 0;
}
.members__submit {
  flex: 0 0 auto;
}
@media (max-width: 480px) {
  .members__field-row { flex-direction: column; align-items: stretch; }
}
~~~

已有对应 CSS 时合并规则，避免重复覆盖。保留 target 已有 fieldset 禁用、输入可访问名称与错误反馈。

- [ ] 保留 h12 现有的 input.closest('label') 名称及操作断言；在浏览器同时核对按钮不在 label 内。以下 DOM 检查不需要新增一份通过同样结构的单元测试。

~~~javascript
const usernameInput = document.querySelector('input[name="username"]')
const usernameLabel = usernameInput.closest('label')
({
  labelText: usernameLabel.textContent.trim(),
  buttonInsideLabel: usernameLabel.querySelector('button') !== null,
})
~~~

- [ ] 在真实浏览器 1280px 下执行以下测量：同一行的 input/button 纵向范围应相交，bottom 差不超过 2px；420px 下不要求同行，但不能有整页横向溢出。

~~~javascript
const inputRect = document.querySelector('input[name="username"]').getBoundingClientRect()
const buttonRect = document.querySelector('.members__submit').getBoundingClientRect()
({
  sameRow: inputRect.top < buttonRect.bottom && buttonRect.top < inputRect.bottom,
  bottomDelta: Math.abs(inputRect.bottom - buttonRect.bottom),
  horizontalOverflow: document.documentElement.scrollWidth > window.innerWidth,
})
~~~

- [ ] 运行 h12、h13，检查输入为空、添加中、重复/未知学生、删除确认、权限失效；已有业务测试不得删改为弱断言。

~~~powershell
npm run test -- --run h12.test.ts h13.test.ts --reporter=dot --testTimeout=30000 --maxWorkers=2
npm run type-check
~~~

- [ ] 更新交接并本地提交，提交说明：fix(frontend): align the member form controls on desktop。

## Task 4：迁移审核队列与版本面板（原第 4 批）

**Files:** 修改 src/frontend/src/views/ReviewView.vue、src/frontend/src/components/VersionPanel.vue；适配 tests/frontend/h09.test.ts、h10.test.ts，检查 h14.test.ts。

**Interfaces:** ReviewView 使用现有 useReview({ coursesApi, reviewApi, graphApi, courseId, onCourseForbidden })；VersionPanel 保留 courseId:string 属性、forbidden 事件及单一 useVersions 实例。新增 review-header/review-content 无参数插槽，仅承载展示内容。

- [ ] 阅读来源两份完整文件及目标 diff。把来源的导航/标题、紧凑发布栏、三类 tab、单列条目、证据折叠、合并确认、默认折叠历史迁到目标；两份文件必须一起改，目标目前没有 review-header。
- [ ] 采用来源的 selectedKind、autoSelected、openEvidence 展示状态；courseId 变化重置三者。使用服务端 totals 显示数量、判断全空；不得用已加载数组长度伪装总量。
- [ ] 保留 useReview/useVersions 当前调用、busy/stale 禁用、刷新失败、权限跳转、冲突处理、分页与回滚语义。发布后以重新读取的已提交课程状态为准，不做乐观版本替换。
- [ ] 使版本请求失败或加载中时，审核插槽仍可见；VersionPanel 不挂第二份状态。完整来源已包含以下顺序：

~~~html
<slot name="review-header"></slot>
<!-- 版本加载/错误及发布栏 -->
<slot name="review-content"></slot>
<!-- 原生 details/summary，默认折叠版本历史 -->
~~~

- [ ] 在 h09 中替换旧的同时显示“三栏空态+总空态”的结构测试，保留全部 API、处理、合并、分页、权限及迟到响应检查。新增的总空态断言：

~~~typescript
it('三类总数都为零时只显示全局空态', async () => {
  const { wrapper } = await mountPage(fakes({ relations: [], duplicates: [], isolated: [] }))
  expect(wrapper.get('[data-test="rv-all-empty"]').text()).toContain('可以直接发布')
  for (const kind of ['low_confidence_relation', 'suspected_duplicate', 'isolated_node']) {
    expect(wrapper.find('[data-test="rv-empty-' + kind + '"]').exists()).toBe(false)
  }
})
~~~

只有选中分类为空且其他分类有条目时，点击对应 tab 后显示该分类空态；处理最后一条导致所有 totals 为零时仅显示总空态。原三栏条目测试先切到对应 tab 再验证该类条目，不要求三类同时渲染。

- [ ] 在 h10 使用已有 mount/h/VersionPanel 和 API 注入键增加插槽隔离测试。

~~~typescript
it('版本读取失败也保留标题和审核区插槽', async () => {
  const wrapper = mount(VersionPanel, {
    props: { courseId: 'c1' },
    slots: {
      'review-header': () => h('h2', { 'data-test': 'slot-header' }, '审核队列'),
      'review-content': () => h('div', { 'data-test': 'slot-review' }, '待处理事项'),
    },
    global: { provide: {
      [COURSES_API_KEY as symbol]: { get: vi.fn(async () => { throw new Error('offline') }) },
      [VERSIONS_API_KEY as symbol]: { list: vi.fn(), publish: vi.fn(), rollback: vi.fn() },
    } },
  })
  await flushPromises()
  expect(wrapper.find('[data-test="vp-error"]').exists()).toBe(true)
  expect(wrapper.get('[data-test="slot-header"]').text()).toBe('审核队列')
  expect(wrapper.get('[data-test="slot-review"]').text()).toBe('待处理事项')
})
~~~

- [ ] tab 支持 ArrowLeft/Right/Up/Down、Home/End，更新 aria-selected 与 roving tabindex；证据仅显示真实页码/章节。旧测试定位 vp-revising 的“学生仍看到 v2”说明若被拆到相邻文字，改为验证当前版本和修订区域整体语义，不删业务断言。
- [ ] 运行相关测试与类型检查；浏览器核对版本加载/失败、三类 tab、全空/分类空、证据、合并、发布、回滚确认及窄屏。

~~~powershell
npm run test -- --run h09.test.ts h10.test.ts h14.test.ts --reporter=dot --testTimeout=30000 --maxWorkers=2
npm run type-check
~~~

- [ ] 更新交接并本地提交，提交说明：feat(frontend): migrate the review workspace and version presentation。

## Task 5：迁移图谱页面、组件与画布主题（原第 5 批）

**Files:** 新建 src/frontend/src/graph/theme.ts；修改 src/frontend/src/graph/lifecycle.ts、adapter.ts；修改 components/GraphCanvas.vue、GraphToolbar.vue、KnowledgeCards.vue、KnowledgeDetail.vue、NodeEditor.vue、RelationEditor.vue、Recommendations.vue；修改 views/TeacherGraphView.vue、StudentGraphView.vue。修改 tests/frontend/h04.test.ts 的主题测试，必要时适配相关纯结构断言。

**Interfaces:** 新增 GraphTheme、FALLBACK_GRAPH_THEME、GRAPH_THEME_VARIABLES、toGraphTheme(values:ReadonlyMap<string,string>):GraphTheme、readGraphTheme(element:Element|null):GraphTheme；内容采用来源完整 theme.ts。CanvasGraphInit 与 GraphLifecycleOptions 都增加 theme?:GraphTheme；现有 createGraphLifecycle、CanvasGraphFactory、toG6Data 签名其余部分保持不变。

- [ ] 阅读来源 graph/theme.ts、lifecycle.ts、adapter.ts 和 GraphCanvas.vue 的联动 diff。不要只复制 theme.ts 和 GraphCanvas：当前 lifecycle 尚不接受或传递 theme。
- [ ] 将来源完整 theme.ts 加入目标。在 lifecycle 导入 FALLBACK_GRAPH_THEME/GraphTheme，给两处接口增加可选 theme 字段；factory 初始化传递 options.theme。

~~~typescript
import { FALLBACK_GRAPH_THEME, type GraphTheme } from './theme'

// CanvasGraphInit 和 GraphLifecycleOptions 中均加入：
// theme?: GraphTheme

// buildGraphOptions 内取得主题，随后按来源替换颜色：
const theme = init.theme ?? FALLBACK_GRAPH_THEME

// createGraphLifecycle 的现有 factory 调用替换为：
const created = await factory({ container, width, height, data, layout, theme: options.theme })
~~~

buildGraphOptions 的 background、默认节点 fill/stroke/labelFill、状态色与边 labelFill 均取 theme。状态名称/顺序、线宽、虚线、缩放、布局、并行边处理、alive/destroy/resize/retry 逻辑不变。

- [ ] 在 GraphCanvas.start 建图前读一次颜色，不在节点/边渲染回调里反复读 computedStyle。

~~~typescript
import { readGraphTheme } from '../graph/theme'

// start 中 stage 与 graph 均非 null 后：
const theme = readGraphTheme(stage.value)
// 在原 createGraphLifecycle 参数对象中增加 theme，保留其他字段。
~~~

- [ ] 更新 adapter 的 RELATION_STYLES 四种 stroke 为来源颜色，保持 label、directed、lineWidth、lineDash、ID、过滤/数据转换算法不变。

~~~typescript
// 按现有对象各项替换 stroke，不替换整套关系语义。
// CONTAINS:     '#8a8175'
// PREREQUISITE: '#9c4a34'
// RELATED_TO:   '#3f6157'
// EXAMPLE_OF:   '#b1791f'
~~~

来源的 relationStyles(theme:GraphTheme) 如果实际消费者没有使用，不必新增闲置函数。图例和默认画布关系色继续共用 RELATION_STYLES；styles.css 的对应变量已存在，本批只核对一致性，不重新迁移全局 CSS。

- [ ] 七个图谱子组件按来源迁入排版、纸面卡片、按钮/表单、状态徽标、焦点与响应式样式；TeacherGraphView/StudentGraphView 添加来源页面容器类。每个文件先看 diff，保留原 props/emits、注入、编辑保存、脏状态确认、删除确认、关系类型、冲突和权限逻辑。
- [ ] 在 h04 添加以下主题测试，并导入来源 theme 的导出；主题缺失与指定主题均应可建图。

~~~typescript
it('未传主题时使用暖纸兜底色，传入主题时使用该主题', () => {
  const base = { container: document.createElement('div'), width: 640, height: 480, data: { nodes: [], edges: [] } }
  expect(buildGraphOptions(base)).toMatchObject({
    background: FALLBACK_GRAPH_THEME.canvas,
    node: { style: { fill: FALLBACK_GRAPH_THEME.node.fill } },
  })
  const theme = {
    ...FALLBACK_GRAPH_THEME,
    canvas: '#102030',
    node: { ...FALLBACK_GRAPH_THEME.node, fill: '#203040' },
  }
  expect(buildGraphOptions({ ...base, theme })).toMatchObject({
    background: '#102030', node: { style: { fill: '#203040' } },
  })
})
~~~

- [ ] 在 h04 使用现有 FakeGraph 验证 factory.init.theme 与传入对象一致；保留延迟 render 后销毁、零尺寸等待、重试、KeepAlive、布局切换测试。浏览器确认 G6 真实画布及图例暖纸色，不能只看到外层卡片变色就验收。
- [ ] 运行全部相关测试并做浏览器走查：教师编辑保存/删除、关系环拒绝、切课；学生知识卡、掌握状态、推荐、筛选和画布；1280/420px 下不遮住操作按钮。

~~~powershell
npm run test -- --run h03.test.ts h04.test.ts h05.test.ts h06.test.ts h07.test.ts h08.test.ts h11.test.ts h14.test.ts i06.test.ts --reporter=dot --testTimeout=30000 --maxWorkers=2
npm run type-check
~~~

- [ ] 更新交接并本地提交，提交说明：feat(frontend): migrate graph presentation and canvas theme。逐个暂存本任务列出的文件，不暂存其他人的改动。

## Task 6：只迁移问答展示，保留发送与个人模型保护（原第 6 批）

**Files:** 修改 src/frontend/src/views/ChatView.vue、src/frontend/src/components/ChatMarkdown.vue。

**Interfaces:** 继续消费现有 useChat(client,courseId) 返回的 entries/question/sending/ask/stop 与 runtime.needsConfig；不修改 useChat、SSE 客户端和 HTTP 客户端。ChatMarkdown 引用事件及安全文本渲染保持不变。

- [ ] 用 git diff 68762e8 27bff16 检查来源。来源删除了 submitQuestion、个人模型引导、retry 的 sending 禁用及 send 锁，禁止整文件复制。
- [ ] ChatView 本批按来源只给根 section 增加 page surface-card 类；其余展示 diff 若不存在，不额外编造新的聊天设计。

~~~html
<section class="page surface-card chat" aria-labelledby="chat-title">
~~~

- [ ] ChatMarkdown 仅迁移三个样式颜色变量。

~~~css
pre { overflow-x: auto; padding: .75rem; background: var(--color-surface-muted); }
code { background: var(--color-surface-muted); }
.citation { color: var(--color-primary); border: 0; background: none; cursor: pointer; text-decoration: underline; }
~~~

- [ ] 保留表单与 Ctrl/Command+Enter 经 submitQuestion，发送按钮禁用表达式 sending || !question.trim() || runtime.needsConfig；保留停止、重试互斥、model-config-required/link 和 data-test 标识。
- [ ] 运行现有锁、SSE、来源及个人配置测试，不额外编写只重复三个 CSS 字面量的测试。

~~~powershell
npm run test -- --run redesign-chat.test.ts chat-send-lock.test.ts j08.test.ts j09.test.ts l10.test.ts d1-d3.test.ts --reporter=dot --testTimeout=30000 --maxWorkers=2
npm run type-check
~~~

- [ ] 浏览器核对发送中不能第二次发送、停止/重试、未配置引导、无资料覆盖、引用跳转、代码块横向滚动和窄屏输入区。
- [ ] 更新交接并本地提交，提交说明：feat(frontend): adapt chat presentation without changing request guards。

## Task 7：把旧 API 设置界面适配为个人模型设置（原第 7 批）

**Files:** 修改 src/frontend/src/views/ModelSettingsView.vue、tests/frontend/l10.test.ts；运行 n03-n05、d1-d3。默认不新增组件，不修改 api/modelConfig.ts、composables/useModelConfig.ts、stores/runtime.ts。

**Interfaces:** 继续使用 useModelConfig({api}) 返回的 status/saved/form/configured/keyRequired/busy/saving/testing/error/notice/testResult/load/save/test/clear。form 为 baseUrl/model/apiKey；testResult 为 null 或 {ok:boolean,text:string}。底层 ModelConfigTestResult 只有 ok、latency_ms 和可选 error_class，现有 text 已包含真实延迟或标准错误。

- [ ] 阅读来源 ApiSettings.vue 和 ConnectionResultDialog.vue，仅取单卡片、字段布局、地址预设和弹窗的视觉设计。禁止引入 createApiSettingsClient、ModelSelect 模型发现、Kind='embedding'、EMBEDDING_TARGET_*、KEY_STORAGE/readStoredKeys/writeStoredKey/restoreKeys。
- [ ] 保留单一“我的模型 API”卡片、configured 脱敏状态、三项输入、保存/测试/清除按钮、清除确认与演示提示。改地址仍要求重新填密钥；只改模型名可按当前后端规则保留已存密钥。
- [ ] 服务商选择只填地址，模型 ID 继续手填。来源静态 HTTPS 地址可以作为预设值，但必须标注“地址预设”，不能宣称所有服务商已验证可用。排除来源 Ollama 的 HTTP/本机地址选项：目标 URL 校验不支持它，不能为此放宽后端。

以下适配代码列出来源的全部 HTTPS 地址预设，并明确 URL 修改时清掉未提交密钥；去掉 listPath（没有模型发现请求）和与目标不符的说明。自定义项保留用户手填。这些值是来源提交的地址预设，未在本次审查中验证第三方当前可用性。

~~~typescript
type ProviderPreset = { id: string; label: string; url: string }
const providerPresets: ProviderPreset[] = [
  { id: 'deepseek', label: 'DeepSeek', url: 'https://api.deepseek.com/v1' },
  { id: 'dashscope', label: '阿里云百炼（通义）', url: 'https://dashscope.aliyuncs.com/compatible-mode/v1' },
  { id: 'openai', label: 'OpenAI', url: 'https://api.openai.com/v1' },
  { id: 'moonshot', label: '月之暗面 Kimi', url: 'https://api.moonshot.cn/v1' },
  { id: 'zhipu', label: '智谱 GLM', url: 'https://open.bigmodel.cn/api/paas/v4' },
  { id: 'siliconflow', label: '硅基流动 SiliconFlow', url: 'https://api.siliconflow.cn/v1' },
  { id: 'openrouter', label: 'OpenRouter', url: 'https://openrouter.ai/api/v1' },
  { id: 'ark', label: '火山方舟', url: 'https://ark.cn-beijing.volces.com/api/v3' },
  { id: 'hunyuan', label: '腾讯混元', url: 'https://api.hunyuan.cloud.tencent.com/v1' },
  { id: 'qianfan', label: '百度千帆', url: 'https://qianfan.baidubce.com/v2' },
  { id: 'minimax-cn', label: 'MiniMax（国内）', url: 'https://api.minimax.chat/v1' },
  { id: 'minimax-intl', label: 'MiniMax（国际）', url: 'https://api.minimaxi.com/v1' },
]
const selectedProvider = computed(() =>
  providerPresets.find((preset) => preset.url === form.baseUrl.trim())?.id ?? 'custom',
)
function chooseProvider(event: Event): void {
  const id = (event.target as HTMLSelectElement).value
  const preset = providerPresets.find((item) => item.id === id)
  if (preset === undefined) return
  if (preset.url !== form.baseUrl.trim()) form.apiKey = ''
  form.baseUrl = preset.url
}
~~~

select 使用 :value="selectedProvider"、@change="chooseProvider"；“自定义”选项值为 custom，其他选项来自 providerPresets；保留原 mc-base-url 手填输入。没有任何预设模型名或密钥；服务商选择不调用网络。

- [ ] 添加原生 dialog 作为连接结果展示，script 导入 computed、watch、onBeforeUnmount；不改 controller 请求和会话保护，不在 await 之后重新打开弹窗。

~~~typescript
const testDialog = ref<HTMLDialogElement | null>(null)
const resultObsolete = ref(false)
function closeTestDialog(): void {
  if (testDialog.value?.open) testDialog.value.close()
}
async function runConnectionTest(): Promise<void> {
  if (busy.value !== null) return
  resultObsolete.value = false
  if (testDialog.value !== null && !testDialog.value.open) testDialog.value.showModal()
  await test()
}
watch(
  [() => form.baseUrl, () => form.model, () => form.apiKey],
  () => {
    if (testing.value || testResult.value !== null) resultObsolete.value = true
    closeTestDialog()
  },
  { flush: 'sync' },
)
watch(() => runtime.owner, closeTestDialog, { flush: 'sync' })
onBeforeUnmount(closeTestDialog)
~~~

mc-test 按钮改为调用 runConnectionTest，busy !== null 禁用条件不变。原 inline mc-test-result 仅在 testResult && !resultObsolete 时显示；obsolete 时显示“表单已修改，请重新测试当前配置”。这样关闭弹窗后仍可见正常结果，编辑表单后不会把旧成功当成本次配置已成功。

~~~html
<dialog ref="testDialog" data-test="mc-test-dialog" aria-labelledby="mc-dialog-title">
  <h3 id="mc-dialog-title">连接测试结果</h3>
  <p v-if="testing" role="status">正在测试连接…</p>
  <p v-else-if="error" role="alert">{{ error }}</p>
  <p v-else-if="testResult && !resultObsolete" data-test="mc-dialog-result" role="status">
    {{ testResult.text }}
  </p>
  <button type="button" autofocus @click="closeTestDialog">关闭</button>
</dialog>
~~~

Esc/关闭只关闭展示，不伪装成取消后台测试；请求中的保存/测试/清除仍由现有 busy 互斥。弹窗不展示 API Key、完整请求、服务器原始 message、编造回答预览/token 消耗/向量维度。latency_ms 属于真实现有字段，可用原 text 展示。

- [ ] 在 l10 中增加弹窗测试。jsdom 如没有原生 dialog 行为，仅为本用例给实际 dialog 元素设置 showModal/close 替身，真实焦点行为随后在浏览器测试。

~~~typescript
it('连接结果弹窗复用个人测试结果且编辑后结果过期', async () => {
  const api = fakeApi(SAVED)
  const wrapper = await mountView(api)
  const dialog = wrapper.get('[data-test="mc-test-dialog"]').element as HTMLDialogElement
  dialog.showModal = () => { dialog.open = true }
  dialog.close = () => { dialog.open = false }
  await wrapper.get('[data-test="mc-test"]').trigger('click')
  await flushPromises()
  expect(api.test).toHaveBeenCalledTimes(1)
  expect(dialog.open).toBe(true)
  expect(wrapper.get('[data-test="mc-dialog-result"]').text()).toContain('321')
  expect(wrapper.html()).not.toContain(KEY)
  await wrapper.get('[data-test="mc-model"]').setValue('m2')
  expect(dialog.open).toBe(false)
  expect(wrapper.find('[data-test="mc-test-result"]').exists()).toBe(false)
  expect(wrapper.text()).toContain('请重新测试当前配置')
})
~~~

- [ ] 增加“已填密钥→选择不同服务商→密钥为空→保存要求新密钥”用例；保留现有保存后输入清空、浏览器存储无密钥、已保存/未保存配置测试区别、STORAGE_UNAVAILABLE、URL 拒绝原因与 MODEL_CONFIG_REQUIRED 用例。
- [ ] 运行以下测试；真实浏览器测 Esc、Tab 焦点限制、关闭后焦点回测试按钮、390×320px 弹窗滚动、测试中改表单、换号/离页后不重开弹窗。

~~~powershell
npm run test -- --run l10.test.ts n03-n05.test.ts d1-d3.test.ts --reporter=dot --testTimeout=30000 --maxWorkers=2
npm run type-check
~~~

- [ ] 在网络面板确认仍只有 GET/PUT/DELETE /api/v1/me/model-config、POST /api/v1/me/model-config/test；没有 api-settings、models 发现、embedding 请求。
- [ ] 更新交接并本地提交，提交说明：feat(frontend): adapt personal model settings cards and test dialog。

## Task 8：完整范围验收、门禁与最终交接

**Files:** docs/tasks.md、docs/handoffs/deepseek-frontend-migration.md；核对全部任务提交，不引入额外产品改动。

**Interfaces:** 消费任务 1–7 的提交、测试日志与页面证据；输出逐项状态表、本地提交序列、后端边界 diff 及可供独立复审的最终 HEAD。

- [ ] 在当前最终 HEAD 运行完整前端门禁，报告实际命令、数量、失败和警告，不沿用旧的“814 通过”替代新结果。

~~~powershell
# 在 src/frontend 执行。
npm run type-check
npm run test -- --run --reporter=dot --testTimeout=30000 --maxWorkers=2
node node_modules/vite/bin/vite.js build --outDir ../../../.review-artifacts/frontend-migration-final-dist

# 在仓库根目录执行。
$migrationRepo = (Resolve-Path .).Path
git -c safe.directory="$migrationRepo" diff --check 68762e8 HEAD
git -c safe.directory="$migrationRepo" diff --name-only 68762e8 HEAD -- src/backend src/contracts scripts .env.example src/frontend/src/api src/frontend/src/composables src/frontend/src/stores src/frontend/src/router src/frontend/src/main.ts
~~~

边界检查预期无输出。如果输出文件名，逐项核对原因；本计划不能授权修改这些范围来修复 UI。工作区未提交内容另用 git diff 和 git diff --cached 检查，避免只核对提交漏掉当前改动。

- [ ] 用修复后的代码重跑仓库外旧审查探针，F1/F3 两项必须通过。

~~~powershell
# 在 src/frontend 执行；该外部配置及用例已经保存在本地。
npm run test -- --config ../../../.review-artifacts/055d914-probe.config.ts --run --reporter=verbose --testTimeout=30000 --maxWorkers=1
~~~

- [ ] 在有 Bash、Python 后端依赖及 Docker/隔离 Neo4j 的环境，从仓库根目录运行系统门禁：

~~~bash
bash scripts/verify.sh full
bash scripts/verify.sh integration
~~~

integration 包含 full，若直接运行 integration 全部通过，无需机械重复 full。脚本默认使用一次性 Neo4j；不要设置 VERIFY_NEO4J_URI 指向开发库或真实课程库，相关集成测试会清库。采用已有 scripts/e2e.sh 的演示流程检查真实 API/worker/数据库链路，不调用主人的付费模型、不写真实课程资料。

本轮审查机器没有可用 Bash，因此上述门禁此前未运行。执行时若仍缺依赖，记录“前端检查已完成，系统门禁受阻”，说明缺失的具体依赖；不得修改门禁、虚报通过或自动安装/重配整个环境。继续完成不依赖该环境的迁移与本地提交。

- [ ] 用真实构建与测试课程完成以下页面矩阵。合成 API 能证明布局和交互，不等同真实后端验收；两种证据分别记录。

| 路径/流程 | 关键验收 |
| --- | --- |
| 登录、教师/学生首页 | 反馈可见、角色导航、课程卡片、长文本、键盘焦点 |
| 课程概览 | 只出现当前课、正确功能入口、无权离课、返回首页 |
| 资料 | 文件选择/拖放/取消、上传锁、任务进度/重连/取消/删除、模型配置引导 |
| 成员 | 桌面同行、窄屏布局、增删反馈、重复/未知学生、权限失效 |
| 审核/版本 | tab 与证据、全空/分类空、合并、真实总数、发布/回滚、版本失败不遮审核 |
| 教师图谱 | 暖纸画布、四种关系、编辑保存/删除、脏状态确认、冲突/环拒绝 |
| 学生图谱 | 已发布版本、筛选、详情、掌握状态、推荐、布局切换 |
| 问答 | 配置门槛、发送锁、停止/重试、SSE 状态、引用、未覆盖、代码块 |
| 个人设置 | 卡片/地址预设、手填 ID、脱敏、测试弹窗、保存/清除互斥、换号与迟到结果 |

桌面至少 1280px、窄屏 420px；结果弹窗额外测 390×320px。记录截图与控制台错误、键盘路径；没有页面容器横向溢出，图谱/代码块自身可按设计滚动。

- [ ] 更新 docs/tasks.md 和交接，把 F1–F4、批次 4–7、原 R1 分开验收。只有全部迁移范围完成且所需系统检查通过，才可称“完整验收通过”；界面完成但系统门禁受阻时保留该状态，不把整项标 DONE。
- [ ] 检查文档与代码对应最终实现；记录纯结构测试为什么改、业务断言如何保留；所有相关变更做最终本地提交，不推送、不部署。

~~~powershell
# 在仓库根目录，每批采用这种显式暂存方式；以下为最后文档提交。
$migrationRepo = (Resolve-Path .).Path
git -c safe.directory="$migrationRepo" add -- docs/tasks.md docs/handoffs/deepseek-frontend-migration.md docs/superpowers/plans/2026-10-04-frontend-migration-completion.md
git -c safe.directory="$migrationRepo" diff --cached --check
git -c safe.directory="$migrationRepo" commit -m "docs: record the complete frontend migration verification"
git -c safe.directory="$migrationRepo" branch --show-current
git -c safe.directory="$migrationRepo" log -1 --format=fuller
git -c safe.directory="$migrationRepo" status --short
~~~

若这些文档中混有他人更改，只暂存自己负责的内容；禁止 git add .、强制重置、整文件从来源 checkout 覆盖。提交受权限/钩子/身份阻止，准确报告原因和未提交文件，不能声称提交成功。

## 最终交付格式

1. 当前分支、最终完整提交哈希、每批提交说明。
2. F1/F2/F3/F4 各自修复证据；批次 1–7 实际状态；原 R1 是否满足关闭条件。
3. 修改文件及责任：展示/局部交互/前端测试/文档，明确没有后端/API 契约/系统向量配置变更。
4. 所有实际运行命令与结果，包括独立探针、浏览器、系统门禁；失败和未运行单列。
5. 真实 API 设置影响：保存用于本人后续新任务；已创建任务按原快照执行；清除沿用目标终止未结束任务的语义。
6. 剩余阻塞、精确复现条件、报告/截图路径；没有阻塞时也只报告已经核验的范围。

## 回退与后续维护

本计划只改变前端及文档，不涉及数据库迁移或向量重建。每批独立本地提交；需要撤回某一批时用对应提交的 git revert 生成新提交，先检查后续批次的依赖，不能硬重置整个工作区。

完成后由独立复审核对最终 HEAD、F1–F4、批次 4–7、业务边界和验收证据。后续若确实需要模型发现、Ollama/私网地址、向量可视化配置等新能力，应另立规格与任务分析后端接口及安全边界；不在本次页面迁移中夹带实现。
