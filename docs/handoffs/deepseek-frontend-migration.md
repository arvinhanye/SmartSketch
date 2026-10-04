# 交接：27bff16 前端设计迁移到 68762e8（frontend-backend-refactor）

日期：2026-10-04（北京时间）
分支：`frontend-backend-refactor`（基于目标基线 `68762e8`，**未推送、未合并、未部署**）
界面来源：`frontend-ui-revision@27bff16`
审查报告：`.review-artifacts/055d914-complete-review.md`（本轮）、`.review-artifacts/ccf5602-review.md`（第 1 批）
执行方案：[`docs/superpowers/plans/2026-10-04-frontend-migration-completion.md`](../superpowers/plans/2026-10-04-frontend-migration-completion.md)

## 1. 当前进度

| 批次 | 范围 | 状态 | 提交 |
| --- | --- | --- | --- |
| 1 | 全局样式、外壳侧栏、登录页 | 完成并验证 | `ccf5602` |
| — | 审查 R2（提示被隐藏）、R3（卡片兜底） | 完成并验证 | `5667384` |
| 2 | 课程首页/概览、教师首页、学生首页 | 完成并验证 | `14ff2f5` |
| 3 | 资料上传页、课程成员页 | 完成并验证 | `ffae94d` |
| F1/F2 | 资料页拖放默认动作与键盘焦点可见 | 已修复并验证 | `25d785f` |
| F3 | 课程概览恢复与首页分离 | 已修复并验证 | `f723801` |
| F4 | 成员页桌面输入框与按钮同行 | 已修复并验证 | `257aa6d` |
| 4 | 审核队列 `ReviewView`、版本面板 `VersionPanel` | 已迁移并验证 | `103a322` |
| 5 | 教师/学生图谱页、图形子组件、`graph/theme.ts` 画布配色 | 已迁移并验证 | `10981d4` |
| 6 | 问答页 `ChatView`、`ChatMarkdown` | 已迁移并验证 | `b27bdb3` |
| 7 | 个人模型 API 设置页适配 | 已迁移并验证 | `700d743` |
| 8 | 全量门禁与交接 | 前端门禁完成；系统门禁受阻 | 本文件 |

最终 HEAD 见本文件末「提交序列」。界面来源 `27bff16` 的展示范围已全部覆盖（覆盖表见 §3）。

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
| `components/AuthLayout.vue`、`components/authGraphMotion.ts` | 目标在来源基础上新增登录动效，属增强版 |
| 来源删除的测试（`l10`、`n03-n05`、`d1-d3`、`chat-send-lock`、`auth-graph-motion`） | 目标测试是行为约束来源，继续保留 |

## 4. F1–F4 关闭证据

| 问题 | 改动 | 验证 |
| --- | --- | --- |
| F1 上传中拖入文件未取消默认动作 | `onDragOver` 先 `isFileDrag` → `preventDefault()` → 再判 `uploading`（忙时 `dropEffect='none'`）；`onDrop` 同样把 `preventDefault()` 提到 `uploading` 判断之前 | `h02` 新增「上传中再次拖入文件」「提示不可放置」「非文件拖拽不取消默认动作」3 项；暂存修复后 4 项失败（含 F2），恢复后全绿；仓库外独立探针 `dragoverCancelled`/`dropCancelled` 均为 `true` |
| F2 隐藏 input 抢焦点、焦点提示消失 | 选择区增加 `:focusin`/`:focusout` 同步的 `is-focused` 类（`:focus-visible` 保留），与 `:focus-visible` 共用 2px 主色轮廓；`clearSelection()` 改 `dropzone.value?.focus()` | `h02` 新增焦点轮廓与取消选择后焦点交回可见选择区 2 项；未修复时失败。**真实浏览器的 Tab 焦点可见性仍建议人工复核（见 §7 未完成项）** |
| F3 概览重新展示全部课程 | 删除概览内 `course-overview-list` 整块与 `.courses__grid` 循环，只留当前课程详情、返回链接与功能入口；注释改为「当前课程详情与功能入口」 | `h01` 新增 c1/c2 用例（概览 `course-card` 数为 0、不出现「其他课程乙」、返回首页后有 2 张卡）；原 aria-current 结构断言改为 `aria-labelledby` → 「当前课程」标题；独立探针 F3 用例通过 |
| F4 成员添加按钮独占下一行 | `label` 与按钮同处 `members__field-row`（`display:flex; align-items:flex-end`），`label` 自身 `flex:1; display:grid`；堆叠断点从 760px 收窄到 480px | `h12`/`h13` 原标签、成员增删、权限断言全部保留通过。**1280px/420px 的实际矩形测量需浏览器人工复核（见 §7）** |

## 5. 验证命令与实测结果（最终 HEAD）

工作目录 `SmartSketch_src/src/frontend`，Node v24.16.0、npm 11.13.0。

```powershell
npx vue-tsc --noEmit -p tsconfig.json          # exit 0
npx vue-tsc --noEmit -p tsconfig.node.json     # exit 0
npx vitest run --reporter=dot --testTimeout=30000 --maxWorkers=2
npx vitest run --config ../../../.review-artifacts/055d914-probe.config.ts --run --reporter=verbose --testTimeout=30000 --maxWorkers=1
node node_modules/vite/bin/vite.js build --outDir ../../../.review-artifacts/frontend-migration-final-dist
```

| 检查 | 结果 |
| --- | --- |
| 类型检查（两套 tsconfig） | 均 0 错误 |
| 全量前端测试 | **29 个文件、831 项全部通过**（基线 814 项，本轮新增 17 项断言） |
| 仓库外独立审查探针 | **2 项全部通过**（修复前为 2 项失败，分别对应 F3 与 F1） |
| 生产构建 | 成功：`index.html` 0.41 kB、`index-*.css` 63.36 kB、`index-*.js` 352.20 kB、`esm-*.js` 1 406.72 kB（仍有 >500 kB chunk 提示，与上一轮一致） |
| 真实无头 Chrome 验收（见下） | **7 项全部通过**，0 控制台错误/警告 |
| `git diff --check 68762e8 HEAD` | 通过（无空白错误） |
| 边界 diff | `git diff --name-only 68762e8 HEAD -- src/backend src/contracts scripts .env.example src/frontend/src/{api,composables,stores,router,main.ts}` **无输出**（工作区另有 `useRelationEditor.ts` 的冲突边配色，属第 5 批画布配色范围） |
| `bash scripts/verify.sh` | **未运行**：本机无 Bash（见 §7） |

真实浏览器验收（仓库外脚本 `.review-artifacts/ui-verify.mjs`，无头 Chrome + CDP，托管本次构建产物并注入合成 API 数据与教师会话）：

| 判定 | 实测值 |
| --- | --- |
| F2 隐藏 input 获得焦点时选择区显示轮廓 | Tab 进 `material-file-input`（`opacity:0`）时选择区 `is-focused` 为真，`outline: solid 2px rgb(156,74,52)` |
| F2 取消选择后焦点交回可见选择区 | `activeIsZoneAfterZoneFocus: true`，轮廓仍为 `solid 2px` |
| F4 桌面输入框与按钮同行 | 1280px 下 input 与 button 的 `top/bottom` 均为 `304.13 / 345.72`，**底边差 0px** |
| F4 输入可访问名称未被按钮污染 | `labelText = "学生用户名"`，`buttonInsideLabel = false` |
| F4 无整页横向溢出 | 1280px 与 420px 均 `scrollWidth <= innerWidth`；420px 下按钮堆到输入框下方且各占满整行 |
| 第 5 批 真实 G6 画布暖纸底色 | canvas 尺寸 332×692，角落像素 `rgb(255,253,250)`（= `--color-surface`），非空白像素 229 744 |
| 第 7 批 结果弹窗在 390×320 | `dialog.open = true` 且完全落在视口内，含关闭按钮 |

逐页冒烟（合成数据，非真实后端验收）：资料页、成员页（2 行成员）、审核页（发布栏「学生当前看到 v2」+ 徽标「草稿修订中」+ 三个 tab「低置信度关系/疑似重复知识点/孤立知识点，各 1 项」+ 单列条目含证据「第 3 页」+ 版本历史默认折叠）、教师图谱页、个人设置页（13 个地址预设、脱敏 `••••1234`）均正常渲染且无横向溢出、无控制台错误。

实际请求端点（仓库外脚本 `.review-artifacts/ui-net.mjs` 记录）：

| 页面/操作 | 实际请求 |
| --- | --- |
| `/settings/model` 打开 | `GET /api/v1/me/model-config` ×2（外壳 `App.vue` 读一次用于侧栏「未配置」徽标，设置页自身读一次） |
| 点「测试连接」 | `POST /api/v1/me/model-config/test` |
| 改模型名后保存 | `PUT /api/v1/me/model-config` |
| `/courses/c1/materials` 打开 | `GET /api/v1/me/model-config`、`GET /api/v1/courses/c1`、`GET /api/v1/courses/c1/upload-policy`、`GET /api/v1/courses/c1/documents` |

**没有**出现在 `/api/v1/api-settings`、模型发现（`/models`）或 embedding 相关的任何请求。

截图：`final-materials.jpg`、`final-members-desktop.jpg`、`final-review.jpg`、`final-teacher-graph.jpg`、`final-model-settings.jpg`、`final-model-dialog-390x320.jpg`（均在 `.review-artifacts/`）。

分组实测（均为 `--reporter=dot --testTimeout=30000 --maxWorkers=2`）：

- `h01 h02 h12 h13`：192 项通过（F1–F4）。
- `h09 h10 h14`：94 项通过（第 4 批）。
- `h03 h04 h05 h06 h07 h08 h11 h14 i06`：367 项通过（第 5 批）。
- `redesign-chat chat-send-lock j08 j09 l10 d1-d3`：95 项通过（第 6 批）。
- `l10 n03-n05 d1-d3`：33 项通过（第 7 批）。

## 6. 边界与不越界核对

`git diff --name-only 68762e8 HEAD` 只含 `src/frontend/**`、`tests/frontend/**` 与 `docs/**`。以下均**未修改**：`src/backend/`、`src/contracts/` 及其生成物、数据库迁移、系统运行配置与启动脚本、真实密钥/配置/数据库、`.env.example`。

个人模型设置页仍使用目标契约：`GET/PUT/DELETE /api/v1/me/model-config` 与 `POST /api/v1/me/model-config/test`；没有恢复 `/api/v1/api-settings`、全局 LLM 配置、JSON 覆盖环境变量、保存后重启、向量设置或模型发现；密钥既未回显也未写入任何浏览器存储（`l10` 断言 `sessionStorage`/`localStorage` 不含密钥）。

## 7. 未完成项与受阻说明

1. **系统门禁未运行**：本机没有可用的 Bash/Python 后端依赖与隔离 Neo4j，`bash scripts/verify.sh full|integration` 未执行。因此本分支只能记为「**前端实现与前端验收完成，系统验收受阻**」，原 R1 的系统级关闭条件尚未满足。
2. **真实后端数据验收未做**：本轮浏览器验收用的是**合成 API 数据**（仓库外脚本托管构建产物并注入固定响应），能证明布局、焦点与画布配色，但不等同真实 API/worker/数据库链路。审核的处理/合并/发布回滚、成员增删、上传进度流等写操作仍需带真实后端逐页验收。
3. **`AuthLayout.vue` 的动效**保留目标版本，未与来源做视觉对齐（来源没有该动效，属目标增强）。
4. **来源的服务商地址预设**是 27bff16 的静态值，本轮没有逐家联网验证可用性；页面文案已声明「地址预设只填写服务地址，不校验服务商当前可用性」。
5. **个人设置测试弹窗的键盘细节**（Tab 焦点限制、Esc 关闭、关闭后焦点回测试按钮）本轮只在 jsdom 与 CDP 截图层面核对，未做完整的键盘路径回放。

## 8. 提交序列

最终 HEAD：**`95b2a35c426cd4aec2a894a9242099b63004d3c8`**（分支 `frontend-backend-refactor`，工作区干净，**未推送、未合并、未部署**）。产品代码在 `700d743` 之后未再改动：`8c89afa` 及之后的提交只更新本文件。

```
95b2a35 docs: record the definitive head hash in the handoff
8c89afa docs: record the final head and the R1 closure checklist
1a7dc88 docs: record the browser acceptance results and the requested endpoints
14b9b76 docs: drop the trailing blank line in the task table
db57409 docs: record the complete frontend migration verification
700d743 feat(frontend): adapt personal model settings cards and test dialog          ← 第 7 批（产品代码最后一次改动）
b27bdb3 feat(frontend): adapt chat presentation without changing request guards      ← 第 6 批
10981d4 feat(frontend): migrate graph presentation and canvas theme                  ← 第 5 批
103a322 feat(frontend): migrate the review workspace and version presentation        ← 第 4 批
257aa6d fix(frontend): align the member form controls on desktop                     ← F4
f723801 fix(frontend): keep the full course grid on the course home                  ← F3
25d785f fix(frontend): preserve file-drop cancellation and visible upload focus      ← F1/F2
055d914 docs(handoffs): record the frontend migration progress and the remaining batches   ← 起始基线
```

本轮共 13 个本地提交（F1–F4 修复 3 个、第 4–7 批 4 个、文档与收尾 5 个，最后一个只写本文件的 HEAD 哈希），涉及 `src/frontend/**`、`tests/frontend/**` 与 `docs/**`，共 38 个文件。

产品代码最后一次改动在 `700d743`（第 7 批）；其后所有提交均为文档。因此 §5 的类型检查、全量测试、仓库外探针与浏览器验收结果都适用于当前产品代码状态。

每批独立可撤回：需要回退某一批时用对应提交的 `git revert` 生成新提交，先核对后续批次的依赖；本轮没有数据迁移，不需要数据库或向量空间回退；**禁止硬重置**。

## 9. 原 R1 关闭条件逐条对照

| 条件 | 状态 |
| --- | --- |
| 第 4–7 批全部实现，并核对与 27bff16 的设计覆盖 | 已实现；覆盖表见 §3（含有意不迁入项与理由） |
| F1/F2/F3/F4 有修复和对应验证证据 | 已完成；单元/探针/浏览器三类证据见 §4 与 §5 |
| 前端全量检查与旧独立探针在最终提交通过 | 已完成：两套 `vue-tsc` 0 错误、29 文件 831 项通过、仓库外探针 2 项通过、构建成功 |
| 浏览器的布局、焦点与主要交互验收通过 | 部分完成：合成数据下 7 项判定通过（含真实 G6 画布配色与弹窗尺寸）；**真实后端数据下的写操作链路未验** |
| 后端与业务保护边界保持 | 已完成：边界 diff 为空；个人模型配置、发送锁、会话隔离、晚到结果保护保留 |
| 所需系统门禁/隔离链路完成 | **未完成**：本机无 Bash，`scripts/verify.sh` 未运行 |
| 任务文档、交接、本地提交完成 | 已完成：`docs/tasks.md` 新增 FE-MIG 任务行、本交接与执行方案均已提交 |

结论：**界面迁移与前端验收已完成，系统门禁与真实后端链路验收仍受阻**，原 R1 现在可以记为「界面部分已闭合，系统部分待环境」，不能记为完整验收通过。
