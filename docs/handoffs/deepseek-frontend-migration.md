# 交接：27bff16 前端设计迁移到 68762e8（frontend-backend-refactor）

日期：2026-10-04（北京时间）
分支：`frontend-backend-refactor`（基于目标基线 `68762e8`，**未推送、未合并、未部署**）
界面来源：`frontend-ui-revision@27bff16a67fa4e9b96416d3529069832b05e88ac`
审查报告：`.review-artifacts/a770278-ui-review.md`（本轮视觉复刻审查）、`.review-artifacts/055d914-complete-review.md`（功能迁移审查）、`.review-artifacts/ccf5602-review.md`（第 1 批）
执行方案：[`docs/superpowers/plans/2026-10-04-frontend-ui-exact-replica.md`](../superpowers/plans/2026-10-04-frontend-ui-exact-replica.md)

> **本文件的定位**：主人要求「前端完全复刻 `frontend-ui-revision`，重点检查 UI 效果」。
> 因此第 1 节之后先记录**视觉复刻**结果（U1–U7），再记录此前功能迁移的批次状态。
> 「展示范围已覆盖」不等于「视觉完全复刻」，两者分别验收、不互相替代。

## 0. 本轮视觉复刻（U1–U7）结果

| 编号 | 问题 | 状态 | 改动 | 证据 |
| --- | --- | --- | --- | --- |
| U1 | 登录/注册仍是另一套设计 | 已修复 | `AuthLayout.vue` 恢复来源模板与样式（58/42 浅色分栏、品牌标识、单张暖色示意图、独立圆角表单卡、卡上方绝对定位通知、页脚、900px 隐藏品牌、720px 矮窗压缩）；`App.vue` 的外壳提示标记 `is-auth-owned`；`styles.css` 恢复来源认证页外壳并精确隐藏重复提示 | 1280×720 实测列宽 `742.391px 537.609px`、品牌底 `rgb(243,239,231)`、卡边框 `1px`/圆角 `20px` 与来源逐项相同；800×800 品牌 `display:none` |
| U2 | 审核页多一层大白卡与 20px 内边距 | 已修复 | `styles.css` 把 `.app-main > section:not(.page)` 的 padding/背景/边框/圆角/阴影兜底还原为来源的 `min-width: 0` | `section.version-panel` 实测 `padding 0px`、背景透明、`border 0px`、`box-shadow none`；标题/发布栏/队列/历史各自成卡 |
| U3 | API 设置与结果弹窗经过重新设计 | 已修复 | `ModelSettingsView.vue` 恢复来源接口卡骨架：`.page` 外层 + `.surface-card` 接口卡、卡头带分隔线与状态同排、字段成组、卡底 `test-actions` 分隔区、卡外 `save-row` 页尾、弹窗顶部 ×、双列 `dl` 摘要、成败强调；新增只读「查看测试结果」 | 标题「API 设置」、`max-width 1160px`、卡头 `border-bottom 1px`、页尾 `border-top 1px`；13 个地址预设 |
| U4 | 成员断点与导航顺序偏离 | 已修复 | `MembersView.vue` 堆叠断点由 480px 恢复 760px；`App.vue` 把「API 设置」入口移回「我的课程」之后、课程导航之前并恢复来源文字 | 1280px 输入与按钮同行；600px 纵向堆叠且两者等宽（各 377px→满宽）；侧栏顺序「我的课程 → API 设置 → 当前课程…」 |
| U5 | 来源遗留的按钮覆盖导致文字不可见 | 已局部纠错 | 知识点卡片加 `data-variant="secondary"`；引用按钮用局部选择器写清普通/悬停/焦点三态；`NodeEditor` 两个删除按钮加 `data-variant="secondary"`；Auth 核心圆显式 `fill: var(--color-primary)` | 引用按钮实测普通 `rgb(156,74,52)`/透明、悬停 `rgb(127,58,39)`/`rgb(246,236,231)`；删除按钮 `rgb(138,59,38)`/`rgb(255,253,250)`；核心圆 `rgb(156,74,52)` + 白字 |
| U6 | 测试后清除/保存残留「表单已修改」提示 | 已修复 | `ModelSettingsView.vue` 增加 `watch([testResult, busy])`，在结果被清空且非测试中时复位 `resultObsolete`/`testDisplayContext`；换号与卸载一并清理 | 新增 2 项顺序回归测试，**未修复时 2 项失败**，修复后通过；`l10` 16 项通过 |
| U7 | CONTAINS/EXAMPLE_OF 也显示「前置 → 后继」 | 已修复 | `ReviewView.vue` 该说明只对 `relation.type === 'PREREQUISITE'` 显示；箭头方向函数与关系算法未动 | `h09` 新增 `it.each` 覆盖 PREREQUISITE/CONTAINS/EXAMPLE_OF/RELATED_TO 四类 |

**两类必须单独说明的视觉例外（不是复刻遗漏）：**

1. **个人模型体系的真实差异**：来源是「大模型 + 向量」两张全局接口卡；目标按 ADR-080 保留**一张真实的个人大模型卡**，因此右侧不补假的向量卡、卡标题为「我的模型 API」。来源的模型发现按钮、本地 Ollama/私网地址、向量维度与「保存后重启」语义都**没有恢复**（属于后端边界，见 §6）。弹窗只显示本次测试真实存在的字段（状态、接口地址、使用模型、结果文本），不编造 HTTP 状态或向量维度。
2. **来源已有缺陷的局部纠错**（U5，以及 U1 中 Auth 核心圆）：这些缺陷在 `27bff16` 上同样存在，实测已核实。本轮只加最小局部规则修正可读性，**没有借机重做页面设计**；不能据此宣称来源分支没有缺陷。

上表全部指标来自**同一份合成数据、同一视窗尺寸**下的真实浏览器对照（来源构建 `.review-artifacts/ui-source-27bff16-dist` 与本轮构建 `.review-artifacts/ui-replica-fixed-dist`，对照脚本 `.review-artifacts/ui-replica-compare.mjs`，15 项判定全部 PASS）。截图前缀：`replica-source-*` / `replica-fixed-*`。

**仍未闭合的视觉验收项**：本轮只覆盖登录、注册、审核、成员、个人设置与 U5 的可读性场景；教师/学生首页、课程概览、资料、教师/学生图谱、问答的逐页同尺寸对照沿用审查轮结论（这些页面此前已判定基本一致，本轮未再改动其展示层），没有重新出图。真实后端数据下的长文本、失败态、空态与写链路仍未验收。

## 1. 功能迁移批次状态

| 批次 | 范围 | 状态 | 提交 |
| --- | --- | --- | --- |
| 1 | 全局样式、外壳侧栏、登录页 | 完成并验证（认证页已被本轮 U1 按来源重做） | `ccf5602` |
| — | 审查 R2（提示被隐藏）、R3（卡片兜底） | 完成并验证（R3 的兜底已被本轮 U2 移除，见下方说明） | `5667384` |
| 2 | 课程首页/概览、教师首页、学生首页 | 完成并验证 | `14ff2f5` |
| 3 | 资料上传页、课程成员页 | 完成并验证 | `ffae94d` |
| F1/F2 | 资料页拖放默认动作与键盘焦点可见 | 已修复并验证 | `25d785f` |
| F3 | 课程概览恢复与首页分离 | 已修复并验证 | `f723801` |
| F4 | 成员页桌面输入框与按钮同行 | 已修复并验证（断点已按 U4 回到 760px） | `257aa6d` |
| 4 | 审核队列 `ReviewView`、版本面板 `VersionPanel` | 已迁移；外层容器问题已由 U2 闭合 | `103a322` |
| 5 | 教师/学生图谱页、图形子组件、`graph/theme.ts` 画布配色 | 已迁移并验证 | `10981d4` |
| 6 | 问答页 `ChatView`、`ChatMarkdown` | 已迁移；引用按钮可读性已由 U5 闭合 | `b27bdb3` |
| 7 | 个人模型 API 设置页适配 | 已适配；视觉已由 U3 按来源重做 | `700d743` |
| U1–U7 | 视觉复刻修正 | 见 §0 | 本轮提交 |

**R3 兜底规则的处置说明**：`5667384` 曾给 `.app-main > section` 加卡片外观，用于「尚未迁移的页面保持卡片与留白」。到本轮为止所有页面都已迁移并自带 `.page`/`.surface-card` 外观，该兜底只剩副作用（正是 U2 的成因），因此已还原为来源的 `min-width: 0`。`h13` 中对应的结构断言已改为「页面根容器不再叠加卡片外观」。

## 2. 已确立的迁移方法（后续批次照此办理）

每个文件按同一套流程，已验证四轮有效：

1. **量化差异**：`git diff --numstat 68762e8 27bff16 -- <file>`。
2. **核对能力差集**（关键，避免覆盖时丢目标能力）：
   - 目标相对来源新增的 `data-test`（用正则提取两侧 `data-test="..."` 求差集）；
   - 目标是否使用 `useRuntimeStore` / `needsConfig` / `model-config-*` / `SETTINGS_ROUTE`（L10 个人模型配置能力）；
   - 目标相对来源新增的**可访问性绑定**（如 `:aria-current`）。
3. **判定形态**：
   - 目标 = 来源的**精简版**（绝大多数页面如此）→ 采用来源的模板与样式，再按第 2 步把目标独有能力嫁接回去；
   - 目标 = 来源的**增强版**（例：`AuthLayout.vue` 在来源基础上新增了 `authGraphMotion` 动效）→ **保留目标版本**，不要覆盖。这是本任务踩过的坑，务必先判定。
4. **composable / API / store 一律不动**：`git diff 68762e8 27bff16 -- src/frontend/src/composables/<x>.ts` 若为「一致」则可放心覆盖对应页面；若不一致，说明目标改了逻辑，必须逐段嫁接而不是覆盖。
5. **跑相关测试 → 按失败信息判断是「补能力」还是「改结构」**，禁止改弱断言。已有多例：
   - `h01` 要求卡片链接有 `aria-current="page"` → 目标有、来源无 → 第 2 批补进来源版；**第 8 轮改为验证当前课程区域的 `aria-labelledby` 语义**（见 §4）；
   - `h12` 要求 `input.closest('label')` 含「学生用户名」→ 与来源的无障碍改法冲突 → 改成「label 只包 input + `aria-label`」两者兼得；
   - `h09`/`h10` 的**纯结构断言**（三栏同时渲染、`vp-revising` 单元素文本）→ 按来源的 tab / 发布栏语义重写，业务断言全部保留；
   - `i06` 的 `nodeState.mastered.stroke === '#52c41a'` 是**测试里的硬编码色**，第 5 批改为取主题常量，并增加自定义主题透传断言。

### 本轮补充的工具经验

- **不要用 PowerShell 的 `Set-Content` / `Get-Content -Raw` 往返改写含中文的源文件**：本机控制台代码页不是 UTF-8，会按 GBK 解码再写回，直接把中文注释与文案变成乱码，并额外加入 BOM。改文本一律用编辑工具的字符串替换；必须用脚本时用 `[System.IO.File]::ReadAllText` / `WriteAllText` + `UTF8Encoding($false)`。
- 只读诊断时 `Get-Content -Encoding UTF8` 可用；但判断文件是否损坏要以编辑工具读取的结果为准。

## 3. 来源设计覆盖表（第 4–7 批逐文件）

| 来源文件 | 目标处理 | 说明 |
| --- | --- | --- |
| `views/ReviewView.vue` | 已迁移 | 导航/标题进 `review-header` 插槽，紧凑发布栏与审核区、默认折叠历史；新增 `selectedKind`/`autoSelected`/`openEvidence` 三个纯展示状态与 tab 键盘行为 |
| `components/VersionPanel.vue` | 已迁移 | 新增两个无参插槽、`version-panel--with-review` 与宽度上限；发布/回滚 busy·stale·冲突·刷新核对逻辑原样保留 |
| `graph/theme.ts` | 已恢复 | 暖纸画布令牌与兜底色，`readGraphTheme` 只在建图时调用一次 |
| `graph/lifecycle.ts` | 已迁移 | `CanvasGraphInit`/`GraphLifecycleOptions` 增加可选 `theme`，工厂透传 `options.theme`，`buildGraphOptions` 全部颜色改取主题 |
| `graph/adapter.ts` | 已迁移 | 四类关系 `stroke` 与 `--graph-edge-*` 对齐；类型/方向/线型/数据转换不变 |
| `components/GraphCanvas.vue` | 已迁移 | 建图前 `readGraphTheme(stage.value)` 并传入生命周期 |
| `components/GraphToolbar.vue` | 已迁移 | 设计令牌替换字面量（含节点状态色样板） |
| `components/KnowledgeCards.vue` | 已迁移 | 设计令牌替换字面量 |
| `components/KnowledgeDetail.vue` | 已迁移 | 设计令牌替换字面量 |
| `components/NodeEditor.vue` | 已迁移 | 设计令牌替换字面量 |
| `components/RelationEditor.vue` | 已迁移 | 设计令牌替换字面量 |
| `components/Recommendations.vue` | 已迁移 | 去掉重复的 `var(..., fallback)` 写法 |
| `views/TeacherGraphView.vue`、`StudentGraphView.vue` | 已迁移 | 根容器加 `page surface-card` |
| `composables/useRelationEditor.ts` | 部分迁移 | 仅冲突边颜色 `#ff4d4f` → `#8a3b26`（暖纸危险色）；其余逻辑未动 |
| `views/ChatView.vue` | 部分迁移 | 只加 `page surface-card`；**不迁入**来源删除的 `submitQuestion`、个人配置引导、发送禁用与重试锁 |
| `components/ChatMarkdown.vue` | 已迁移 | 代码块底色与引用色改用全局变量 |
| `views/ModelSettingsView.vue` | 适配 | 采用来源的单卡片、服务商地址预设、原生 `dialog` 结果弹窗；数据与操作继续走 `useModelConfig` + `/api/v1/me/model-config` |

**有意不迁入（目标能力更强或属于其他边界）：**

| 来源文件 | 原因 |
| --- | --- |
| `api/apiSettings.ts`、`views/ApiSettings.vue` | 全局配置 + 保存后重启语义，与 ADR-080 个人配置边界冲突 |
| `components/ModelSelect.vue` | 依赖模型发现接口，目标没有该接口，不能伪造候选 |
| `components/ConnectionResultDialog.vue` | 目标改为 `ModelSettingsView` 内原生 `dialog`，避免引入旧弹窗组件 |
| `composables/useChat.ts`、`api/chatStream.ts`、`api/http.ts`、`api/taskEvents.ts` | 来源删除了目标已有的发送锁、取消与错误分类；这些是业务保护 |
| `composables/useMaterials.ts`、`stores/runtime.ts`、`api/modelConfig.ts`、`composables/useModelConfig.ts`、`main.ts`、`router/index.ts` | 目标比来源多出个人模型配置、会话隔离、晚到结果保护与路由注入 |
| `components/authGraphMotion.ts` | 该动效矩阵只服务目标原先的 AuthLayout；本轮 U1 已把 AuthLayout 换回来源的静态示意图，因此矩阵不再被页面引用，但**文件与 `auth-graph-motion.test.ts` 按计划保留**，不随本轮删除 |
| 来源删除的测试（`l10`、`n03-n05`、`d1-d3`、`chat-send-lock`、`auth-graph-motion`） | 目标测试是行为约束来源，继续保留 |

## 4. F1–F4 关闭证据

| 问题 | 改动 | 验证 |
| --- | --- | --- |
| F1 上传中拖入文件未取消默认动作 | `onDragOver` 先 `isFileDrag` → `preventDefault()` → 再判 `uploading`（忙时 `dropEffect='none'`）；`onDrop` 同样把 `preventDefault()` 提到 `uploading` 判断之前 | `h02` 新增「上传中再次拖入文件」「提示不可放置」「非文件拖拽不取消默认动作」3 项；暂存修复后 4 项失败（含 F2），恢复后全绿；仓库外独立探针 `dragoverCancelled`/`dropCancelled` 均为 `true` |
| F2 隐藏 input 抢焦点、焦点提示消失 | 选择区增加 `:focusin`/`:focusout` 同步的 `is-focused` 类（`:focus-visible` 保留），与 `:focus-visible` 共用 2px 主色轮廓；`clearSelection()` 改 `dropzone.value?.focus()` | `h02` 新增焦点轮廓与取消选择后焦点交回可见选择区 2 项；未修复时失败。真实浏览器实测：Tab 进 `opacity:0` 的 input 时选择区轮廓为 `solid 2px rgb(156,74,52)` |
| F3 概览重新展示全部课程 | 删除概览内 `course-overview-list` 整块与 `.courses__grid` 循环，只留当前课程详情、返回链接与功能入口；注释改为「当前课程详情与功能入口」 | `h01` 新增 c1/c2 用例（概览 `course-card` 数为 0、不出现「其他课程乙」、返回首页后有 2 张卡）；原 aria-current 结构断言改为 `aria-labelledby` → 「当前课程」标题；独立探针 F3 用例通过 |
| F4 成员添加按钮独占下一行 | `label` 与按钮同处 `members__field-row`（`display:flex; align-items:flex-end`），`label` 自身 `flex:1; display:grid`；堆叠断点**保持来源的 760px**（本轮 U4 已把上一轮误改的 480px 改回） | `h12`/`h13` 原标签、成员增删、权限断言全部保留通过；真实浏览器实测 1280px 下 input/button 的 `top/bottom` 均为 `304.13/345.72`（底边差 0px），600px 纵向堆叠且两者等宽 |

## 5. 验证命令与实测结果（最终 HEAD）

工作目录 `SmartSketch_src/src/frontend`，Node v24.16.0、npm 11.13.0。

```powershell
npx vue-tsc --noEmit -p tsconfig.json          # exit 0
npx vue-tsc --noEmit -p tsconfig.node.json     # exit 0
npx vitest run --reporter=dot --testTimeout=30000 --maxWorkers=2
npx vitest run --config ../../../.review-artifacts/055d914-probe.config.ts --run --reporter=verbose --testTimeout=30000 --maxWorkers=1
node node_modules/vite/bin/vite.js build --outDir ../../../.review-artifacts/ui-replica-fixed-dist
node ../../../.review-artifacts/ui-replica-compare.mjs   # 同数据同视窗与来源 27bff16 对照
```

| 检查 | 结果 |
| --- | --- |
| 类型检查（两套 tsconfig） | 均 0 错误 |
| 全量前端测试 | **29 个文件、839 项全部通过**（上一轮 831 项；本轮 U6/U7 新增 2+4 项断言，h13 的动效断言改为来源静态示意图语义） |
| 仓库外独立审查探针 | **2 项全部通过**（覆盖 F1/F3） |
| 生产构建 | 成功：`index-*.css` 68.14 kB、`index-*.js` 350.06 kB、`esm-*.js` 1 406.72 kB（仍有 >500 kB chunk 提示） |
| 视觉对照（vs 来源 27bff16，同数据同视窗） | **15 项判定全部 PASS**，见 §0 与下方明细 |
| `git diff --check 68762e8 HEAD` | 通过（无空白错误） |
| 边界 diff | `git diff --name-only 68762e8 HEAD -- src/backend src/contracts scripts .env.example src/frontend/src/{stores,router,main.ts}` **无输出**。`src/frontend/src/api` 与 `src/frontend/src/composables` 下**只有 `composables/useRelationEditor.ts` 的冲突边配色**（`#ff4d4f` → `#8a3b26`）与注释不同；已核实来源 `27bff16` 的色值同样是 `#8a3b26`，因此这不是视觉复刻缺口，请求/冲突处理/保存/图谱算法未改 |
| `bash scripts/verify.sh` | **未运行**：本机无 Bash/Docker 与隔离 Neo4j（见 §7） |

视觉对照明细（脚本 `.review-artifacts/ui-replica-compare.mjs`，来源构建 `ui-source-27bff16-dist` + 本轮构建 `ui-replica-fixed-dist`，同一合成数据夹具与同一视窗）：

| 判定 | 来源实测 | 本轮修复实测 |
| --- | --- | --- |
| 认证页 58/42 分栏 | `742.391px 537.609px` | 完全相同（品牌占比 0.580） |
| 认证页品牌底色 | `rgb(243,239,231)` | 相同 |
| 认证页 800px 品牌 | `display:none` | 相同 |
| 认证页表单卡边框/圆角 | `1px` / `20px` | 相同 |
| 认证页核心圆 | `rgb(255,253,250)`（来源缺陷：白字不可见） | `rgb(156,74,52)` + 白字（U5 局部纠错） |
| 审核页 `section.version-panel` | padding 0 / 透明 / border 0 / shadow none | 相同（修复前为 20px + 暖白 + 边框 + 阴影） |
| 成员页 1280px 输入与按钮 | 同行 | 同行（底边差 0px） |
| 成员页 600px | 纵向堆叠、等宽 | 纵向堆叠、等宽 |
| 设置页标题/限宽 | — | 「API 设置」/ `1160px`（修复前为 44rem 居中） |
| 设置页卡头分隔线、页尾保存区 | — | `border-bottom 1px` / `border-top 1px` |
| 引用按钮普通态 | 砖红字 + 深砖红底（缺陷，难辨认） | `rgb(156,74,52)` / 透明底 |
| 引用按钮悬停态 | 同上 | `rgb(127,58,39)` / `rgb(246,236,231)` |
| 删除按钮 | 危险文字 + 主色底（色差极小） | `rgb(138,59,38)` / `rgb(255,253,250)` |

上一轮的浏览器验收（脚本 `.review-artifacts/ui-verify.mjs`，7 项 PASS）仍然有效，覆盖 F2 焦点轮廓、F4 桌面/窄屏、真实 G6 画布暖纸底色 `rgb(255,253,250)`、390×320 结果弹窗不越界。实际请求端点（脚本 `.review-artifacts/ui-net.mjs`）只包含 `/api/v1/me/model-config`、`/api/v1/courses*` 系列；**没有** `/api/v1/api-settings`、模型发现或 embedding 请求。

截图（均在仓库外 `.review-artifacts/`）：

- 本轮对照：`replica-source-*.jpg` 与 `replica-fixed-*.jpg`（login 1280/800/420、register 1280、review 1280/600、members 1280/600/420、settings 1280/420），另 `replica-fixed-student-graph-1280x720.jpg`、`replica-fixed-teacher-graph-1280x720.jpg`、`replica-fixed-chat-answer-1280x720.jpg`。
- 上一轮功能迁移：`final-materials.jpg`、`final-members-desktop.jpg`、`final-review.jpg`、`final-teacher-graph.jpg`、`final-model-settings.jpg`、`final-model-dialog-390x320.jpg`。
- 审查轮基线：`a770278-source-*.jpg` / `a770278-current-*.jpg`（本轮修复前的对照）。

## 6. 边界与不越界核对

`git diff --name-only 68762e8 HEAD` 只含 `src/frontend/**`、`tests/frontend/**` 与 `docs/**`。以下均**未修改**：`src/backend/`、`src/contracts/` 及其生成物、数据库迁移、系统运行配置与启动脚本、真实密钥/配置/数据库、`.env.example`。

个人模型设置页仍使用目标契约：`GET/PUT/DELETE /api/v1/me/model-config` 与 `POST /api/v1/me/model-config/test`；没有恢复 `/api/v1/api-settings`、全局 LLM 配置、JSON 覆盖环境变量、保存后重启、向量设置或模型发现；密钥既未回显也未写入任何浏览器存储（`l10` 断言 `sessionStorage`/`localStorage` 不含密钥）。

## 7. 未完成项与受阻说明

1. **系统门禁未运行**：本机没有可用的 Bash/Python 后端依赖与隔离 Neo4j，`bash scripts/verify.sh full|integration` 未执行。因此本分支只能记为「**前端实现与前端/视觉验收完成，系统验收受阻**」，原 R1 的系统级关闭条件尚未满足。
2. **真实后端数据验收未做**：本轮与上一轮的浏览器验收都用**合成 API 数据**（仓库外脚本托管构建产物并注入固定响应），能证明布局、焦点、配色与可读性，但不等同真实 API/worker/数据库链路。审核的处理/合并/发布回滚、成员增删、上传进度流、真实模型问答仍需带真实后端逐页验收。
3. **视觉对照的覆盖范围**：本轮重新出图的是登录、注册、审核、成员、个人设置，以及 U5 的引用按钮/删除按钮场景；教师/学生首页、课程概览、资料、教师/学生图谱、问答页沿用审查轮「基本一致」的结论，展示层本轮未改动，但**没有重新逐页出图**。弹窗的完整键盘路径（Tab 限制、Esc 后焦点回测试按钮）也只在 jsdom 与 CDP 截图层面核对，未做完整回放。
4. **`authGraphMotion.ts` 与 `auth-graph-motion.test.ts`**：U1 把 AuthLayout 换回来源的静态示意图后，该动效矩阵不再被页面引用；按计划保留文件与单测，未删除。`h13` 中原本验证动效的三项断言已改为验证来源静态示意图（单图、9 条连线、节点不随帧位移、900px 断点），不是删除测试。
5. **来源的服务商地址预设**是 27bff16 的静态值，本轮没有逐家联网验证可用性；页面文案已声明「地址预设只填写服务地址，不校验服务商当前可用性」。

## 8. 提交序列

最终 HEAD：**`（见 git log -1，本文件最后一次 docs 提交）`**（分支 `frontend-backend-refactor`，**未推送、未合并、未部署**）。

上一轮的 13 个提交：

```
95b2a35 docs: record the definitive head hash in the handoff
8c89afa docs: record the final head and the R1 closure checklist
1a7dc88 docs: record the browser acceptance results and the requested endpoints
14b9b76 docs: drop the trailing blank line in the task table
db57409 docs: record the complete frontend migration verification
700d743 feat(frontend): adapt personal model settings cards and test dialog          ← 第 7 批
b27bdb3 feat(frontend): adapt chat presentation without changing request guards      ← 第 6 批
10981d4 feat(frontend): migrate graph presentation and canvas theme                  ← 第 5 批
103a322 feat(frontend): migrate the review workspace and version presentation        ← 第 4 批
257aa6d fix(frontend): align the member form controls on desktop                     ← F4
f723801 fix(frontend): keep the full course grid on the course home                  ← F3
25d785f fix(frontend): preserve file-drop cancellation and visible upload focus      ← F1/F2
055d914 docs(handoffs): record the frontend migration progress and the remaining batches   ← 起始基线
```

本轮（U1–U7 视觉复刻）在其之上再提交一个：

```
fix(frontend): restore frontend-ui-revision visual fidelity
  AuthLayout.vue / App.vue / styles.css / ModelSettingsView.vue / MembersView.vue
  KnowledgeCards.vue / ChatMarkdown.vue / NodeEditor.vue / ReviewView.vue
  tests/frontend/h09.test.ts / tests/frontend/l10.test.ts / tests/frontend/h13.test.ts
  docs/handoffs/deepseek-frontend-migration.md
  docs/superpowers/plans/2026-10-04-frontend-ui-exact-replica.md
```

每个批次/修正独立可撤回：需要回退时用对应提交的 `git revert` 生成新提交，先核对后续批次的依赖；本轮没有数据迁移，不需要数据库或向量空间回退；**禁止硬重置**。

## 9. 原 R1 关闭条件逐条对照

| 条件 | 状态 |
| --- | --- |
| 第 4–7 批全部实现，并核对与 27bff16 的设计覆盖 | 已实现；覆盖表见 §3（含有意不迁入项与理由） |
| F1/F2/F3/F4 有修复和对应验证证据 | 已完成；单元/探针/浏览器三类证据见 §4 与 §5 |
| 前端全量检查与旧独立探针在最终提交通过 | 已完成：两套 `vue-tsc` 0 错误、29 文件 839 项通过、仓库外探针 2 项通过、构建成功 |
| 浏览器的布局、焦点与主要交互验收通过 | 视觉复刻部分已完成：与来源同数据同视窗的 15 项对照判定全部 PASS（含认证页分栏/断点、审核页外层、成员断点、设置页骨架、引用与删除按钮可读性）；**真实后端数据下的写操作链路未验** |
| 后端与业务保护边界保持 | 已完成：`src/backend`、`src/contracts`、`scripts`、`.env.example`、`stores`、`router`、`main.ts` 无差异；`api/` 无差异；`composables/` 仅 `useRelationEditor.ts` 的冲突边配色与来源一致。个人模型配置、发送锁、会话隔离、晚到结果保护保留 |
| 所需系统门禁/隔离链路完成 | **未完成**：本机无 Bash，`scripts/verify.sh` 未运行 |
| 任务文档、交接、本地提交完成 | 已完成：本交接、执行方案与本地提交齐全；`docs/tasks.md` 已记 FE-MIG 行 |

结论：**视觉复刻与前端验收已完成，系统门禁与真实后端链路验收仍受阻**，原 R1 现在可以记为「界面部分已闭合（含视觉复刻），系统部分待环境」，不能记为完整验收通过。
