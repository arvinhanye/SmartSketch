# 课程列表与模型设置 UI 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox syntax. 主人已批准并要求执行；不自动提交、推送或开 PR。

**Goal:** 按 PR #322 已确认的 R2/R3 默认设计，升级课程列表、课程主页与模型设置，提供可实际登录查看的页面。

**Architecture:** 沿用 Vue 路由、useCourses/useModelConfig 和现有 API。复用 AppTopbar/AppIcon；暗色外壳仅推广到课程列表、课程主页与模型设置，保留既有学生图谱样板页。新增有作用域的浅色页面组件与 CSS，不修改其他页面的业务或外观。

**Tech Stack:** Vue 3、TypeScript、Vite、Pinia、Vue Router、Vitest；不新增依赖。

**Spec:** GitHub PR #322 `docs/frontend-ui-handoff.md` §4.4、§5，以及 `docs/superpowers/plans/2026-10-07-ui-rollout-batch2.md` §3/§4/R2/R3；`specs/identity-access.md`、ADR-080/ADR-090。

## 输入与边界

- 起点：独立本地克隆 `_pr-preview-321`，`claude/smartsketch-frontend-init-0d2af9@ab601831791da40345f74d515652a7315dd63429`。
- 设计文档在 `origin/claude/ui-rollout-batch2-plan@55b19d0`，实现前基于该提交切本地分支 `codex/courses-model-settings-ui`；保留 `.local-run/` 和预览日志。
- 当前前端 http://127.0.0.1:5322，后端 http://127.0.0.1:8321。启动配置与课程数据库沿用；本任务不导入、发布或修改课程数据。
- 原有全部 `data-test` 钩子、权限判断、接口、会话取消/晚到响应保护不变。
- 样式仅使用 `--ss-*`、`--gw-*`；`.graph-workspace, .light-surface` 共用相同浅色 token 数值；不改全局 `--color-*`。
- 不改登录、注册、问答、教师图谱、资料、成员和审核页；这些路由沿用当前外壳。
- UI 文案变化限交接文档已确认的标题、字段说明、创建/取消、状态与复制用户名提示；原课程入口链接文案保持不变。
- 不在日志、存储、URL、测试证据或截图写入真实密钥；截图只用未配置状态或明显的假值。

## Review Focus

1. 教师账号在某门课内为学生时，只显示学生入口；不把账号角色用于课程权限判断。
2. 390px 宽和 200% 缩放时，长课程名称/服务地址不撑破页面，按钮可换行，长内容整页可达。
3. 保存失败时密钥处理仍遵循既有 composable；保存成功不回显；只复制用户名不复制令牌。
4. 创建请求未完成时不能取消或重复提交；失败留在面板，成功关闭面板并保留成功提示。
5. 设置保存/测试/清除互斥，清除必须二次确认，错误不回显服务端原文。

## 任务 1：页面基础与限定外壳

**Files:** `src/frontend/src/App.vue`、`styles/tokens.css`；新增 `styles/ui.css`、`components/PageSheet.vue`、`components/PageHeader.vue`；测试 `tests/frontend/app-graph-shell.test.ts`、`ui-rollout-shell.test.ts`、`graph-theme.test.ts`。

**Interfaces:** PageSheet 接收 `labelledby: string`、`compact?: boolean` 和 default slot；PageHeader 接收 `id: string`、`title: string`、`description?: string`，提供 actions slot。外壳仍使用原 graphShell 分支及 AppTopbar props，扩充路由选择与面包屑。

- [x] 写失败测试：课程主页使用顶栏、图标栏且没有旧侧栏；设置页最后面包屑是“模型 API 设置”；不误标“知识图谱”；其他尚未升级路由仍保留原行为。

```ts
expect(wrapper.find('.app-topbar').exists()).toBe(true)
expect(wrapper.find('.app-sidebar').exists()).toBe(false)
expect(wrapper.get('nav[aria-label="当前位置"] [aria-current="page"]').text()).toBe('课程概览')
```

- [x] 运行 `npm --prefix src/frontend run test -- --run app-graph-shell ui-rollout-shell graph-theme`，记录预期失败。
- [x] 路由条件用已注册名称，不按 pathname 猜测；课程首页/主页/设置增加外壳，其他旧页面保留。面包屑使用课程详情名称，读取失败回退“课程”。保留导航 `nav-model-settings`、`nav-model-settings-pending`、演示提示和退出登录。

```ts
const upgradedPage = computed(() => route?.name === COURSE_ROUTE || route?.name === SETTINGS_ROUTE || homeActive.value)
const graphShell = computed(() => withSidebar.value && (route?.name === STUDENT_GRAPH_ROUTE || upgradedPage.value))
```

- [x] PageSheet 使用 `section.light-surface.ui-sheet`，外留 12px、圆角 10px、内容最大宽 1120px；compact 最大宽 640px。PageHeader 为 h2 + 次级说明 + 操作槽。CSS 显式覆盖旧 section/button/input 规则。
- [x] 复跑上述测试，保留学生图谱窄屏导航焦点和退出测试。

## 任务 2：课程列表、主页与创建面板

**Files:** `views/CoursesView.vue`；新增 `components/courses/CourseList.vue`、`CourseOverview.vue`、`CourseCreate.vue`；`styles/ui.css`；测试 `h01.test.ts`、新增 `course-page-ui.test.ts`。

**Interfaces:** CourseList 消费 `CourseCard[]`、`selectedId: string|null`，仅展示 RouterLink；CourseOverview 消费 current CourseCard 与原入口判断/nextStep/nextLink，保持角色条件；CourseCreate 消费原 form/creating/createError，向父组件 emit submit/cancel。请求留在 CoursesView/useCourses。

- [x] 写失败测试：教师点击“新建课程”才显示页内表单；取消不发请求；成功关闭表单但成功提示仍可见；失败保留表单；学生没有创建入口；复制用户名成功/失败反馈；课程整行链接包含状态/身份/知识点信息；课程内学生无教师入口。

```ts
expect(wrapper.find('[data-test="course-create"]').exists()).toBe(false)
await wrapper.get('[data-test="course-create-open"]').trigger('click')
expect(wrapper.get('[data-test="course-create"]').exists()).toBe(true)
await wrapper.get('[data-test="course-create-cancel"]').trigger('click')
expect(api.create).not.toHaveBeenCalled()
```

- [x] `npm --prefix src/frontend run test -- --run course-page-ui` 确认 RED；列出 h01 旧断言中“表单默认展开”的变化，同步点击新入口后继续原校验断言，不删校验。
- [x] 行式列表：每个 `li[data-test=course-card]` 中一个完整 RouterLink；名称与一行简介在左，身份/状态/发布版/知识点与箭头在右。保持原 aria-current，不使用嵌套链接；hover/focus/新建成功高亮明确。
- [x] 课程主页：名称与简介标题区 → 下一步卡（原 course-stage/course-next-action）→ 按原角色条件的入口卡 → 原课程列表，保持 DOM 顺序。保留所有入口钩子和原文案。
- [x] 创建按钮设置 aria-expanded/aria-controls；面板显示时 nextTick 聚焦名称框；取消后焦点还按钮，忙碌时取消禁用。提交逻辑：

```ts
async function submitCourse(): Promise<void> {
  await createCourse()
  if (createdName.value !== null) createOpen.value = false
}
```

- [x] 创建成功提示独立于面板，列表顶部沿用 composable 已有插入行为。用户名复制只用 `session.user?.username`，捕获 clipboard 拒绝显示 status 消息。
- [x] `npm --prefix src/frontend run test -- --run h01 course-page-ui l15` GREEN；按引用搜索执行所有课程页面消费方测试。

## 任务 3：模型设置分区

**Files:** `views/ModelSettingsView.vue`、`styles/ui.css`；测试 `l10.test.ts`、`adr090.test.ts`、新增 `model-settings-ui.test.ts`。

**Interfaces:** 不改变 useModelConfig/API 返回对象。继续使用 status/saved/form/configured/keyRequired/busy/save/test/clear；只增加 UI 聚焦与日期展示函数。

- [x] 写失败测试：switch 有正确语义和键盘切换；未配置“去配置”聚焦服务地址；密钥 autocomplete=off/spellcheck=false/type=password；已保存仅显示 key_hint，密码框为空；清除取消不请求；busy 禁用保存/测试/清除/确认；错误不暴露服务端原文。

```ts
expect(wrapper.get('[data-test="mc-disable-thinking"]').attributes('role')).toBe('switch')
expect(wrapper.get('[data-test="mc-api-key"]').attributes('type')).toBe('password')
await wrapper.get('[data-test="mc-configure"]').trigger('click')
expect(document.activeElement).toBe(wrapper.get('[data-test="mc-base-url"]').element)
```

- [x] `npm --prefix src/frontend run test -- --run model-settings-ui` 确认 RED。
- [x] 640px 单列 PageSheet：状态卡/连接配置/操作栏。状态卡区分未配置/已配置/测试成败，时间来自 existing saved.last_test，空值不编造时间；演示提示保留 mc-demo。
- [x] 连接配置为有标签与说明的 ui-field；关闭思考使用原 checkbox 加 role=switch/aria-checked 和可见滑块样式，保留 v-model 与 mc-disable-thinking。
- [x] 操作栏保存 primary、测试 secondary、清除 danger ghost；内联确认不换成弹窗，不变更请求行为；结果 role=status/alert；提示与字段通过 aria-describedby 关联。
- [x] 执行 `npm --prefix src/frontend run test -- --run l10 adr090 model-settings-ui`，确认 GREEN。

## 任务 4：验证、预览与交付

**Files:** `docs/tasks.md`、`docs/handoffs/codex-courses-model-settings-ui.md`、本计划；必要时补充 UI 规格的本次范围与证据。

- [x] 更新任务认领、逐项 RED/GREEN 记录、页面可见文案表。无后端/契约/数据库变化。
- [x] 类型检查、全量前端测试、构建：

```powershell
npm --prefix src/frontend run type-check
npm --prefix src/frontend run test -- --run
npm --prefix src/frontend run build
```

- [x] 运行 `./scripts/verify.sh` 基础门禁；先核对本机 bash/Python，不为门禁改产品依赖；失败如实记录原因。
- [x] 真实浏览器在 1440×900、1280×800、768×1024、390×844 查看教师列表/课程主页、学生空列表、设置未配置与错误状态。检查 documentElement.scrollWidth <= innerWidth；200% 缩放、Tab/Esc 焦点、减少动效。设置截图只用假值。
- [x] 浏览器执行创建/取消/校验使用隔离假 API 或测试环境，不向现有课程库写测试课程；不触发付费模型连接。
- [x] 自查 diff 或调用可用只读 code review；修复阻断缺陷后重新跑相关与全量检查。保留未完成项，不宣称执行了不可用的浏览器检查。
- [x] 在同一前端地址打开修改结果，交付截图/页面入口、改动概述、测试结果、分支名与未提交状态；不自动 push/deploy。

## 实施顺序与裁定

采用本会话顺序实施，共享文件 App.vue/ui.css 由单一执行者修改。R1 仅纳入本次两页所需外壳与内容表面，不执行 R1 的全站推广或学生图谱遗留验收；用户此次范围优先于路线图批次的完整范围。不新增模型列表接口、课程统计字段或新的设计风格。

计划自查：默认设计、原钩子、权限与安全约束均对应到以上任务；实施完成；基础门禁已执行但因本机缺少 datamodel-codegen 未通过，具体证据见交接文档。

执行裁定：基础门禁复跑启用 PYTHONUTF8 避免 Windows GBK 输出错误；仍缺 datamodel-codegen，未伪称门禁全绿。模型 ADR-090 验证包含在 l10 用例内，无独立 adr090 测试文件。浏览器缩放为 200% CSS zoom，非浏览器原生缩放；减少动效上下文与选定焦点操作已检查，不宣称完整人工无障碍审计。
