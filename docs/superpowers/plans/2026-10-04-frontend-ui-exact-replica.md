# frontend-ui-revision 精确视觉复刻 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. If the user explicitly chooses delegation, use superpowers:subagent-driven-development. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 以本地 `frontend-ui-revision@27bff16` 为唯一页面设计来源，修正当前前端的视觉差异，保留 `68762e8` 个人模型体系及现有业务保护。

**Architecture:** 复用来源模板/样式，按页面修正展示层，不整分支合并，不整目录覆盖。API 设置复用来源视觉结构，调用当前个人配置接口；来源已有的可读性/语义缺陷仅做局部纠错并记录。

**Tech Stack:** 现有 Vue 3、TypeScript、Vue Router、Pinia、G6、Vite、Vitest；遵守当前 package.json 的 Node engines，不新增 UI 框架、不升级依赖。

**Spec:** [本轮完整审查报告与截图](<C:/Users/asus/Desktop/32401139蒋韩烨+32401141孔绍诚+32401140金鸣远+32401142兰家旺 (1)/32401139蒋韩烨+32401141孔绍诚+32401140金鸣远+32401142兰家旺/S4A原型展示/SmartSketch/.review-artifacts/a770278-ui-review.md>)。读取本计划前先读报告 U1–U7；原“迁移完成计划”只作为历史交接，遇到视觉要求冲突以本计划和主人最新要求为准。

## Global Constraints

- 主人明确要求：“我的要求是前端完全复刻我之前的分支，着重检查前端ui制作效果”；随后指定 `frontend-ui-revision` 且要求查找本地提交。
- 已核实 UI 来源完整 SHA：`27bff16a67fa4e9b96416d3529069832b05e88ac`。当前被审查分支 `frontend-backend-refactor`、HEAD `a770278e3a0fe72d24b939110841186e8e590e4a`。实施前重新核实，若 HEAD 后来有变化先检查新增差异，不回滚别人的修改。
- 不修改 `src/backend`、`src/contracts`、数据库迁移、启动脚本、运行配置及 .env.example；不改前端 API、router、stores、main.ts、composable 的请求与算法。
- 保留个人模型接口 `/api/v1/me/model-config`，保留加密存密钥、不回显/不落浏览器存储、保存/测试/清除、demo/personal 提示、会话隔离、迟到结果保护和操作互斥。
- 不恢复旧全局 API/向量配置、模型发现、本地 Ollama/私网能力；不显示无法工作的按钮或假的向量设置卡。
- 保留 F1/F2 文件拖放和焦点修复、F3 概览分离、F4 桌面同行；保留聊天发送/取消锁与未配置引导。
- 已匹配的首页、图谱、问答主体不重新设计；不新增暗色模式、主题切换、随机图示或其他新功能。
- 来源已有的名称/引用/删除按钮可读性和关系文案问题按本计划小范围纠错。该例外必须写入交接，不能扩展成风格重做。
- 仅暂存任务文件，完成检查后必须产生本地 Git 提交；不自动推送、合并或部署。交付当前分支、完整提交哈希、提交说明、检查结果；提交受阻须如实说明。

## Review Focus

1. 认证页未登录通知关闭后表单卡位置应稳定；wrong-role/course-forbidden 等原因仍可见。任务 1 的真实浏览器检查覆盖。
2. 原生测试弹窗在 pending/完成/失败、Esc/关闭/重看结果、切页/换号时不显示旧结果、不重复请求、不把键盘焦点丢到页面开头。任务 3/6 覆盖。
3. 成员输入与按钮在 760/761、480/481、600px 边界符合来源，长用户名与表格在窄屏可以滚动。任务 4 覆盖。
4. 普通/悬停/焦点/选中/禁用状态下，卡片名称、引用编号、删除按钮和来源 SVG 核心文字可读。任务 1/5 覆盖。
5. 测试后清除、测试后保存、修改表单作废旧结果；CONTAINS/EXAMPLE_OF 不误标前置；分页 totals 的可见数字与可访问名称正确。任务 6 覆盖。

## 工作目录与文件边界

实际仓库根：
`C:/Users/asus/Desktop/32401139蒋韩烨+32401141孔绍诚+32401140金鸣远+32401142兰家旺 (1)/32401139蒋韩烨+32401141孔绍诚+32401140金鸣远+32401142兰家旺/S4A原型展示/SmartSketch/SmartSketch_src`

任务文件：

| 文件 | 职责 |
| --- | --- |
| [AuthLayout.vue](<C:/Users/asus/Desktop/32401139蒋韩烨+32401141孔绍诚+32401140金鸣远+32401142兰家旺 (1)/32401139蒋韩烨+32401141孔绍诚+32401140金鸣远+32401142兰家旺/S4A原型展示/SmartSketch/SmartSketch_src/src/frontend/src/components/AuthLayout.vue>) | 来源品牌、图示、登录/注册卡片、局部通知及响应式 |
| [App.vue](<C:/Users/asus/Desktop/32401139蒋韩烨+32401141孔绍诚+32401140金鸣远+32401142兰家旺 (1)/32401139蒋韩烨+32401141孔绍诚+32401140金鸣远+32401142兰家旺/S4A原型展示/SmartSketch/SmartSketch_src/src/frontend/src/App.vue>) | 通知展示归属、设置导航位置/文案，保留 runtime/session 逻辑 |
| [styles.css](<C:/Users/asus/Desktop/32401139蒋韩烨+32401141孔绍诚+32401140金鸣远+32401142兰家旺 (1)/32401139蒋韩烨+32401141孔绍诚+32401140金鸣远+32401142兰家旺/S4A原型展示/SmartSketch/SmartSketch_src/src/frontend/src/styles.css>) | 来源认证页外壳、根 section/form 布局兜底 |
| [ModelSettingsView.vue](<C:/Users/asus/Desktop/32401139蒋韩烨+32401141孔绍诚+32401140金鸣远+32401142兰家旺 (1)/32401139蒋韩烨+32401141孔绍诚+32401140金鸣远+32401142兰家旺/S4A原型展示/SmartSketch/SmartSketch_src/src/frontend/src/views/ModelSettingsView.vue>) | 个人 API 卡片、字段、按钮区、弹窗与局部展示状态 |
| [MembersView.vue](<C:/Users/asus/Desktop/32401139蒋韩烨+32401141孔绍诚+32401140金鸣远+32401142兰家旺 (1)/32401139蒋韩烨+32401141孔绍诚+32401140金鸣远+32401142兰家旺/S4A原型展示/SmartSketch/SmartSketch_src/src/frontend/src/views/MembersView.vue>) | 来源 760px 输入/按钮堆叠断点 |
| [KnowledgeCards.vue](<C:/Users/asus/Desktop/32401139蒋韩烨+32401141孔绍诚+32401140金鸣远+32401142兰家旺 (1)/32401139蒋韩烨+32401141孔绍诚+32401140金鸣远+32401142兰家旺/S4A原型展示/SmartSketch/SmartSketch_src/src/frontend/src/components/KnowledgeCards.vue>) | 卡片文字/悬停可读性 |
| [ChatMarkdown.vue](<C:/Users/asus/Desktop/32401139蒋韩烨+32401141孔绍诚+32401140金鸣远+32401142兰家旺 (1)/32401139蒋韩烨+32401141孔绍诚+32401140金鸣远+32401142兰家旺/S4A原型展示/SmartSketch/SmartSketch_src/src/frontend/src/components/ChatMarkdown.vue>) | 引用按钮的普通/悬停/焦点可读性 |
| [NodeEditor.vue](<C:/Users/asus/Desktop/32401139蒋韩烨+32401141孔绍诚+32401140金鸣远+32401142兰家旺 (1)/32401139蒋韩烨+32401141孔绍诚+32401140金鸣远+32401142兰家旺/S4A原型展示/SmartSketch/SmartSketch_src/src/frontend/src/components/NodeEditor.vue>) | 两个删除按钮的可读性，确认逻辑保留 |
| [ReviewView.vue](<C:/Users/asus/Desktop/32401139蒋韩烨+32401141孔绍诚+32401140金鸣远+32401142兰家旺 (1)/32401139蒋韩烨+32401141孔绍诚+32401140金鸣远+32401142兰家旺/S4A原型展示/SmartSketch/SmartSketch_src/src/frontend/src/views/ReviewView.vue>) | 前置关系说明的类型条件 |
| [l10.test.ts](<C:/Users/asus/Desktop/32401139蒋韩烨+32401141孔绍诚+32401140金鸣远+32401142兰家旺 (1)/32401139蒋韩烨+32401141孔绍诚+32401140金鸣远+32401142兰家旺/S4A原型展示/SmartSketch/SmartSketch_src/tests/frontend/l10.test.ts>) | 展示状态顺序、重看结果不重发请求 |
| [h09.test.ts](<C:/Users/asus/Desktop/32401139蒋韩烨+32401141孔绍诚+32401140金鸣远+32401142兰家旺 (1)/32401139蒋韩烨+32401141孔绍诚+32401140金鸣远+32401142兰家旺/S4A原型展示/SmartSketch/SmartSketch_src/tests/frontend/h09.test.ts>) | 关系文案、可见 totals/aria-label |
| [交接文档](<C:/Users/asus/Desktop/32401139蒋韩烨+32401141孔绍诚+32401140金鸣远+32401142兰家旺 (1)/32401139蒋韩烨+32401141孔绍诚+32401140金鸣远+32401142兰家旺/S4A原型展示/SmartSketch/SmartSketch_src/docs/handoffs/deepseek-frontend-migration.md>) | 实际来源、差异例外、截图、门禁、本地提交记录 |

不创建新的全局模型客户端，不恢复 ApiSettings.ts；不重新覆盖 useChat/useMaterials/useModelConfig/useRelationEditor。冲突边当前 `#8a3b26` 与来源相同，无需再改。

## Task 1: 恢复来源认证页视觉（U1）

**Files:** AuthLayout.vue、App.vue、styles.css。
**Interfaces:** 继续接收现有默认 slot；不新增登录参数，不改 Root/Register View 的请求。通知只读取现有 route/query。

- [ ] **Step 1：查看并使用准确来源。** 在仓库根执行：

```powershell
$uiReplicaRepo = (Get-Location).Path
git -c safe.directory="$uiReplicaRepo" show 27bff16:src/frontend/src/components/AuthLayout.vue
git -c safe.directory="$uiReplicaRepo" show 27bff16:src/frontend/src/styles.css
```

恢复来源 AuthLayout 的品牌标识、58/42 分栏、暖色单张示意图、独立圆角卡、绝对定位通知、页脚、900px 品牌隐藏断点及 720px 高度规则。去掉当前运动图在该页面的使用；无需删除其他任务的 motion 文件/测试。

- [ ] **Step 2：对来源通知脚本做最小安全适配。** 避免无 Router 的组件挂载读取 undefined；保留来源 nodes/edges 和其余模板样式：

```ts
import { computed, inject, ref } from 'vue'
import { routeLocationKey } from 'vue-router'
import { NOTICE_UNAUTHENTICATED, ROOT_ROUTE } from '../router'

const route = inject(routeLocationKey, null)
const noticeDismissed = ref(false)
const showLoginNotice = computed(() =>
  !noticeDismissed.value
  && route !== null
  && route.name === ROOT_ROUTE
  && route.query.notice === NOTICE_UNAUTHENTICATED,
)
function dismissNotice(): void {
  noticeDismissed.value = true
}
```

App 保留当前 notice 逻辑和 `v-if="notice"`，增加展示归属标记，不删除守卫通知：

```ts
const authHandlesNotice = computed(() =>
  route?.name === ROOT_ROUTE && route.query.notice === NOTICE_UNAUTHENTICATED,
)
```

给现有 App notice 容器增加 `:class="{ 'is-auth-owned': authHandlesNotice }"`。styles.css 中认证页 main 采用来源 display:block/position:relative；只在实际包含 AuthLayout 时隐藏由它承载的重复提示：

```css
.app.app--auth .app-main {
  display: block;
  position: relative;
}
.app.app--auth .app-main:has(> .auth-layout) > .app-notice.is-auth-owned {
  display: none;
}
```

不要隐藏整类 role=alert，不删除原 B03 的访问拒绝断言。来源 SVG 核心 fill 被通用 circle 规则覆盖，局部修正为：

```css
.auth-layout__node--core circle {
  fill: var(--color-primary);
  stroke: var(--color-primary-hover);
  stroke-width: 2;
}
```

- [ ] **Step 3：在真实浏览器验收。** 登录/注册分别对照来源 1280×720、800×800、420×800；显示通知/关闭通知各一张。确认表单位置稳定、只出现一条可见通知、800px 不再保留左品牌栏、核心图示文字可见。用现有 B02/B03 检查确保独立挂载和路由守卫不回退；纯样式修改不新增实现镜像测试。

## Task 2: 恢复审核页透明外层（U2）

**Files:** styles.css。VersionPanel.vue 已与来源一致，保持其发布/历史逻辑。
**Interfaces:** VersionPanel 继续安排 header slot、发布栏、审核内容和历史区。

- [ ] **Step 1：保存修改前证据。** 进入同一 c1 审核页，记录 `section.version-panel` 的 padding/background/border/boxShadow，当前错误为 20px/暖白/边框/阴影。
- [ ] **Step 2：恢复来源根容器规则。** 将新增卡片兜底规则还原为：

```css
.app-main > section,
.app-main > form {
  min-width: 0;
}
```

移除该兜底的 display/grid gap/padding/background/border/radius/shadow；页面外观由已有 page/surface-card/组件 scoped 样式承担。不要给 VersionPanel 内部加负 margin，不重写发布/回滚方法。

- [ ] **Step 3：截图验收。** 1280×720、600×800 分别对照审核空态/有数据、证据展开、历史展开。外层 padding=0、透明、无 border/shadow；标题、发布、队列、历史的位置与来源一致。抽查教师/学生图谱、资料、成员、个人设置，避免对其他根容器造成新差异。

## Task 3: 个人 API 保留当前接口，恢复来源视觉与结果交互（U3）

**Files:** ModelSettingsView.vue。读取来源 ApiSettings.vue 与 ConnectionResultDialog.vue 的展示部分，不恢复其全局接口依赖。
**Interfaces:** 保持当前 `useModelConfig({ api })`、form/configured/keyRequired/busy/testResult/error/notice、save/test/clear；仅新增视图内测试上下文和弹窗操作。

- [ ] **Step 1：恢复来源骨架和字段顺序。** 页面标题为“API 设置”，卡片标题可使用来源“大模型接口”；说明明确是当前账号的个人配置。去掉 44rem 居中及大标题样式。桌面使用来源 2 列 grid 的第一张接口卡位置/宽度，只保留一张真实个人卡；850px 以下单列。右侧不补假的向量卡。保留 provider → URL → Key → model 顺序，删除模型发现按钮及其说明，只使用个人后端已有输入。

source 卡头与字段 CSS 按以下数值复用；fieldset 中每个 label 与其控件应作为一组，而不是将所有 label/input 打散成连续 grid 项：

```css
.interface-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 20px;
  align-items: start;
}
.card-heading {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding-bottom: 16px;
  border-bottom: 1px solid var(--color-border);
  margin-bottom: 16px;
}
fieldset { border: 0; padding: 0; margin: 0; display: grid; gap: 14px; min-width: 0; }
.field { display: grid; gap: 6px; font-size: 14px; }
input, select { width: 100%; padding: 10px 12px; min-width: 0; }
.test-actions { display: flex; flex-wrap: wrap; gap: 10px; padding-top: 12px; border-top: 1px solid var(--color-border); }
.save-row { display: flex; flex-wrap: wrap; gap: 12px; padding-top: 20px; border-top: 1px solid var(--color-border); }
@media (max-width: 850px) {
  .interface-grid { grid-template-columns: minmax(0, 1fr); }
}
```

连同来源 field/input/button 的颜色、边框、圆角与 focus 规则一起移植，避免只复制以上布局片段后继承错误默认色。配置状态徽标采用来源同排、小字体与成功色；长状态需要能换行，不溢出卡片。

- [ ] **Step 2：拆分测试区和页面保存区。** 测试按钮在接口卡底部分隔区；保存按钮在卡片外页尾。现有 form 使用 `id="mc-form"`，页尾按钮使用：

```html
<button type="submit" form="mc-form" data-test="mc-save" :disabled="busy !== null">
  {{ saving ? '正在保存…' : '保存设置' }}
</button>
```

保留原表单 `@submit.prevent="save"`、字段 busy 禁用和 keyRequired 校验。“清除配置”作为个人体系的次要动作，继续使用 confirmingClear/confirmClear，不改确认文案和 clear 请求。

- [ ] **Step 3：恢复弹窗的展示结构。** 使用来源 header、顶部 ×、成败强调、dl 双列摘要、底部说明与宽度；保留当前原生 dialog。dl label 列使用来源 6rem。状态、接口地址、使用模型仅来自真实结果或这次测试的本地快照；失败原因使用当前转换后的 testResult.text/error。当前 composable 只返回 `{ok,text}`，延迟包含在 text 中，不拆字符串冒充新的结构化值，不编造 HTTP 状态，不为装饰而改 API/composable。

增加以下视图接口；函数实现只操作 dialog 和本地快照，当前 `test()` 仍只调用一次：

```ts
type TestDisplayContext = { baseUrl: string; model: string; providerLabel: string }
const testDisplayContext = ref<TestDisplayContext | null>(null)
function showTestResult(): void {
  const dialog = testDialog.value
  if (dialog !== null && !dialog.open && typeof dialog.showModal === 'function') dialog.showModal()
}
```

`runConnectionTest()` 先保留现有 busy guard，清旧展示标记，保存当前 URL/model/provider 快照，调用 showTestResult，再 await test。给“查看测试结果”按钮 `data-test="mc-view-result"`，仅在 testing 或未作废结果存在时出现，点击只调用 showTestResult；该只读按钮放在 disabled fieldset 外，pending 时仍可用。

关闭/原生 Esc 后将用户发起关闭的焦点还给可用的查看结果按钮；换号、编辑作废或卸载导致的自动关闭不抢用户焦点。完成请求不自动重开已关闭的弹窗。不要把关闭弹窗改成取消测试请求。

- [ ] **Step 4：增加只读重看的行为测试。** 在现有 l10 describe 中使用既有 fakeApi/SAVED/mountView，加入：

```ts
it('重看连接结果不重复发送测试请求', async () => {
  const api = fakeApi(SAVED)
  const wrapper = await mountView(api)
  const dialog = wrapper.get('[data-test="mc-test-dialog"]').element as HTMLDialogElement
  dialog.showModal = () => { dialog.open = true }
  dialog.close = () => { dialog.open = false }

  await wrapper.get('[data-test="mc-test"]').trigger('click')
  await flushPromises()
  await wrapper.get('[data-test="mc-dialog-close"]').trigger('click')
  await wrapper.get('[data-test="mc-view-result"]').trigger('click')
  expect(dialog.open).toBe(true)
  expect(api.test).toHaveBeenCalledTimes(1)
  wrapper.unmount()
})
```

jsdom 替身只验证请求次数/状态，不当作原生焦点验收。真实浏览器另测 pending 和完成时的 Tab/Shift+Tab/Esc/×、重看、失败与 validation error，420px 弹窗不裁切/不横向溢出。

## Task 4: 恢复成员断点和导航位置（U4）

**Files:** MembersView.vue、App.vue。
**Interfaces:** 原添加/删除调用与权限不变；settingsLink/settingsActive/needsConfig 逻辑不变。

- [ ] **Step 1：保持桌面已有 label + field-row 结构，恢复堆叠规则到 760px。**

```css
@media (max-width: 760px) {
  .members__field-row {
    flex-direction: column;
    align-items: stretch;
  }
  .members__submit {
    justify-content: center;
    width: 100%;
  }
}
```

合并现有 480px 同规则，保留 source 的 card padding、counts 换行和表格容器滚动。

- [ ] **Step 2：将当前个人设置 RouterLink 块移到“我的课程”后、courseNav template 前。** 保留 `:to="settingsLink"`、个人设置的所有已登录角色可见、active/aria-current/data-test 和未配置徽标；导航文字恢复“API 设置”。不复制来源的教师专用全局接口路由。
- [ ] **Step 3：实际检查 1280、761、760、600、481、480、420px。** >760 同行，≤760 纵向满宽；两版导航位置一致，长用户名不会撑破卡片，表格仍可横向滚动。提交按钮和关联 label 可用。

## Task 5: 局部修复来源已有的可读性问题（U5）

**Files:** KnowledgeCards.vue、ChatMarkdown.vue、NodeEditor.vue。Auth 核心 fill 已在任务 1 修正。
**Interfaces:** 不改变 emit、漫游 tabindex、选中状态、删除确认和引用识别规则。

- [ ] **Step 1：KnowledgeCards 的卡片 button 增加 `data-variant="secondary"`。** 复用已有 secondary 的深色文字、浅色 hover，保留当前选中边框/shadow。不要仅补文字色却保留主按钮 hover。
- [ ] **Step 2：ChatMarkdown 明确引用按钮普通/hover/focus 的背景，使用足以覆盖全局 hover 的局部选择器。**

```css
.chat-markdown button.citation {
  padding: 0;
  min-height: 0;
  background: transparent;
  color: var(--color-primary);
  border: 0;
  text-decoration: underline;
}
.chat-markdown button.citation:hover:not(:disabled) {
  background: var(--color-primary-soft);
  color: var(--color-primary-hover);
}
.chat-markdown button.citation:focus-visible {
  outline: 2px solid var(--color-primary);
  outline-offset: 2px;
}
```

不改 Markdown 解析、不引入 v-html，不新增表格/加粗渲染能力；这不是本次功能扩展。

- [ ] **Step 3：NodeEditor 的 `node-editor__danger` 两个删除按钮增加 secondary 外观。** 保留 scoped 危险文字色及确认动作，让危险文字位于浅色背景，不改变删除流程或默认确认态。
- [ ] **Step 4：浏览器对照普通/hover/Tab 焦点/选中/disabled。** 知识点名称、引用编号和删除文字都可读。只增加必要的局部规则，不修改全局主按钮默认色。截图记录这些是来源缺陷修复而非风格差异。

## Task 6: 修正展示状态、关系文案与数量验证（U6/U7）

**Files:** ModelSettingsView.vue、ReviewView.vue、tests/frontend/l10.test.ts、tests/frontend/h09.test.ts。
**Interfaces:** 不改变 save/clear/test 的请求和结果生命周期；只复位视图局部状态，关系类型只用于展示。

- [ ] **Step 1：先加入当前会失败的顺序测试。**

```ts
it('测试完成后清除配置不残留表单已修改提示', async () => {
  const api = fakeApi(SAVED)
  const wrapper = await mountView(api)
  await wrapper.get('[data-test="mc-test"]').trigger('click')
  await flushPromises()
  await wrapper.get('[data-test="mc-dialog-close"]').trigger('click')
  await wrapper.get('[data-test="mc-clear"]').trigger('click')
  await wrapper.get('[data-test="mc-clear-confirm"]').trigger('click')
  await flushPromises()
  expect(api.clear).toHaveBeenCalledTimes(1)
  expect(wrapper.get('[data-test="mc-status"]').text()).toContain('尚未配置')
  expect(wrapper.find('[data-test="mc-test-stale"]').exists()).toBe(false)
  wrapper.unmount()
})
```

加入同类“测试后保存”检查，仍需保留现有“修改模型会作废旧结果”断言。先运行 l10 确认新顺序测试确实失败。

- [ ] **Step 2：在视图内复位完成操作后的展示状态。** 与任务 3 的快照协同处理：

```ts
watch(
  [testResult, busy],
  ([result, operation]) => {
    if (result === null && operation !== 'testing') {
      resultObsolete.value = false
      testDisplayContext.value = null
    }
  },
  { flush: 'post' },
)
```

保留同步表单变更作废逻辑；runtime.owner 改变时关闭弹窗并清 resultObsolete/testDisplayContext。卸载只清本地展示。测试 pending 时不要因结果暂为 null 清掉这次上下文；不得让新 watch 恢复已被用户作废的旧结果。

- [ ] **Step 3：仅 PREREQUISITE 显示“前置 → 后继”。**

```html
<span v-if="relation.type === 'PREREQUISITE'"> · 前置 → 后继</span>
```

原 relationDirected 函数继续负责箭头方向，不修改它或关系算法。h09 使用现有 rel/fakes/mountPage：

```ts
it.each([
  ['PREREQUISITE', true],
  ['CONTAINS', false],
  ['EXAMPLE_OF', false],
] as const)('%s 的前置说明正确', async (type, hasPrerequisiteLabel) => {
  const relation = { ...rel('r1', 'k1', 'k2'), type }
  const { wrapper } = await mountPage(fakes({ relations: [relation], duplicates: [], isolated: [] }))
  expect(wrapper.get('[data-test="rv-relation"]').text().includes('前置 → 后继')).toBe(hasPrerequisiteLabel)
  wrapper.unmount()
})
```

- [ ] **Step 4：同时检查真实数量展示与可访问名称。** 在 h09 原数量测试中保留服务端 totals 断言，并补：

```ts
expect(wrapper.get('[data-test="rv-count-low_confidence_relation"]').text()).toBe('2')
expect(wrapper.get('[data-test="rv-total-low_confidence_relation"]').attributes('aria-label'))
  .toBe('低置信度关系，共 2 项')
```

分页、处理后数字变化、空态互斥仍需满足原断言。不能只依赖隐藏的 data-heading。

- [ ] **Step 5：真实浏览器验收。** 测试成功/失败 → 关闭 → 修改/保存/清除；pending → Esc/换页/换号；三类有向关系；服务端 totals 大于当前分页数组长度。旧结果不冒充新配置、迟到结果不重开弹窗、清除后不出现“表单已修改”。

## Task 7: 全页视觉回归、文档和本地提交

**Files:** 上述任务文件、此计划、DeepSeek 交接文档；截图存仓库外 `.review-artifacts`。
**Interfaces:** 最终交付必须可被下一位审查者独立复现。

- [ ] **Step 1：运行必要检查，记录真实结果。** 在 frontend 目录：

```powershell
npm run type-check
npm run test -- --run --reporter=dot --testTimeout=30000 --maxWorkers=2
node node_modules/vite/bin/vite.js build --outDir ../../../.review-artifacts/ui-replica-fixed-dist
```

保留现有外部 F1/F3 探针；若文件仍存在，可执行：

```powershell
npm run test -- --config ../../../.review-artifacts/055d914-probe.config.ts --run --reporter=verbose --testTimeout=30000 --maxWorkers=1
```

计划中的新增测试必须先证明失败，再证明修复后通过；纯颜色/间距修正用浏览器截图验收，不新增镜像 CSS 测试来代替视觉检查。不要把本轮旧的 831 计数照抄为新结果。

- [ ] **Step 2：逐页同数据、同尺寸截图。** 对照 `27bff16` 与修复构建，至少覆盖登录、注册、教师/学生首页、课程概览、资料、成员、审核、教师/学生图谱、个人 API、问答。桌面 1280×720；涉及断点的页面至少 600/420px，认证页加 800px。记录实际 innerWidth/innerHeight、状态和角色。

展开节点编辑、关系编辑、知识点详情、证据、版本历史、连接结果、回答引用，补普通/焦点/hover/禁用/空态/失败态。必须使用实际构建和浏览器，不用截图模型伪造对比。没有可用浏览器就如实列为视觉验收未完成。

来源导出及初始对照产物在 [审查目录](<C:/Users/asus/Desktop/32401139蒋韩烨+32401141孔绍诚+32401140金鸣远+32401142兰家旺 (1)/32401139蒋韩烨+32401141孔绍诚+32401140金鸣远+32401142兰家旺/S4A原型展示/SmartSketch/.review-artifacts>)，来源构建为 `ui-source-27bff16-dist`。现有 a770278-visual-server.py 服务原审查构建；如复用它，明确把“当前构建”的映射换成 ui-replica-fixed-dist，避免错误验收旧 bundle。仅修改仓库外夹具，不向产品代码加假接口/假会话。

- [ ] **Step 3：核对业务边界与差异。** 在仓库根：

```powershell
$uiReplicaRepo = (Get-Location).Path
git -c safe.directory="$uiReplicaRepo" diff --check
git -c safe.directory="$uiReplicaRepo" diff --name-only a770278 -- src/backend src/contracts scripts .env.example src/frontend/src/api src/frontend/src/composables src/frontend/src/stores src/frontend/src/router src/frontend/src/main.ts
git -c safe.directory="$uiReplicaRepo" status --short
```

第二条预期无输出。本计划只修改展示层与相关测试/文档；若出现业务路径差异，逐条核查来源并消除本任务引入的越界修改，不撤销别人的既有工作。

- [ ] **Step 4：更新交接。** 逐项 U1–U7 给出完成状态、修改文件、来源/修复截图路径、实际检查命令与结果。明确两类视觉例外：个人设置的真实字段/单卡，与来源缺陷的局部纠错。订正旧交接关于 useRelationEditor 和 HEAD 的不准确表述。系统门禁和真实后端未跑就写未完成，不把合成 UI 冒烟当成真实系统验收。

如果仅本地 frontend 环境可用，交付 UI/前端结果并留下真实后端验收项目：资料上传与任务流、成员增删、审核处理/合并、发布/回滚、个人设置及真实问答。具备项目所需 Bash/数据库环境后按 scripts/verify.sh 的 full/integration 入口执行并记录；这不是恢复旧向量后端的理由。

- [ ] **Step 5：仅提交任务文件到本地。** 先人工核对 diff，确认无无关文件/密钥/数据库/产物，再在仓库根：

```powershell
$uiReplicaRepo = (Get-Location).Path
git -c safe.directory="$uiReplicaRepo" add -- src/frontend/src/components/AuthLayout.vue src/frontend/src/App.vue src/frontend/src/styles.css src/frontend/src/views/ModelSettingsView.vue src/frontend/src/views/MembersView.vue src/frontend/src/components/KnowledgeCards.vue src/frontend/src/components/ChatMarkdown.vue src/frontend/src/components/NodeEditor.vue src/frontend/src/views/ReviewView.vue tests/frontend/l10.test.ts tests/frontend/h09.test.ts docs/handoffs/deepseek-frontend-migration.md docs/superpowers/plans/2026-10-04-frontend-ui-exact-replica.md
git -c safe.directory="$uiReplicaRepo" diff --cached --check
git -c safe.directory="$uiReplicaRepo" diff --cached --stat
git -c safe.directory="$uiReplicaRepo" commit -m "fix(frontend): restore frontend-ui-revision visual fidelity"
git -c safe.directory="$uiReplicaRepo" branch --show-current
git -c safe.directory="$uiReplicaRepo" rev-parse HEAD
git -c safe.directory="$uiReplicaRepo" log -1 --format="%s"
git -c safe.directory="$uiReplicaRepo" status --short
```

不要 git add -A。若有任务文件未实际改动，add 不会造成额外内容；若前置改动来自别人，单独核对并按任务范围暂存。提交失败要说明错误、已完成检查和当前工作区状态，不编造哈希，不自动 push。

## 自检与完成标准

- [ ] U1–U4 的纯视觉差异已闭合，认证/审核/设置/成员的截图与来源结构吻合。
- [ ] U5 来源遗留缺陷已用局部规则修正，设计主体保持来源，并在交接列明例外。
- [ ] U6/U7 的顺序/语义回归测试通过，真实浏览器键盘与结果生命周期经过验证。
- [ ] 已一致的首页/图谱/问答没有新差异，F1–F4 和业务保护保留。
- [ ] 个人设置未添加向量/全局/发现/私网能力；本任务业务路径 diff 为空。
- [ ] 前端检查、视觉验收、真实后端/系统验收分别记录，不相互替代。
- [ ] 已产生可核实的本地提交，分支/哈希/提交说明/检查结果齐全。

本计划完成的是修正方案。开始实施前阅读主人的后续指令；本次审查并未修改产品代码。
