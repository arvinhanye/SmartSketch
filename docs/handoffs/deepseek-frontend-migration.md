# 交接：27bff16 前端设计迁移到 68762e8（frontend-backend-refactor）

日期：2026-10-04（北京时间）
分支：`frontend-backend-refactor`（基于目标基线 `68762e8`，**未推送、未合并、未部署**）
界面来源：`frontend-ui-revision@27bff16`
审查报告：`.review-artifacts/ccf5602-review.md`

## 1. 当前进度

| 批次 | 范围 | 状态 | 提交 |
| --- | --- | --- | --- |
| 1 | 全局样式、外壳侧栏、登录页 | 完成并验证 | `ccf5602` |
| — | 审查 R2（提示被隐藏）、R3（卡片兜底） | 完成并验证 | `5667384` |
| 2 | 课程首页/概览、教师首页、学生首页 | 完成并验证 | `14ff2f5` |
| 3 | 资料上传页、课程成员页 | 完成并验证 | `ffae94d` |
| 4 | 审核队列 `ReviewView`（−868）、`VersionPanel`（−393） | **未开始** | — |
| 5 | 教师图谱页、学生图谱页、`graph/theme.ts` 画布配色、图谱子组件 | **未开始** | — |
| 6 | 问答页 `ChatView`（+18/−7）、`ChatMarkdown` | **未开始** | — |
| 7 | API 设置页适配个人模型配置体系 | **未开始** | — |

已完成 4 个提交、共 9 个文件（含 `vitest.config.ts` 的环境修复）。剩余约 10 个文件。

## 2. 已确立的迁移方法（后续批次照此办理）

每个文件按同一套流程，已验证三轮有效：

1. **量化差异**：`git diff --numstat 68762e8 27bff16 -- <file>`。
2. **核对能力差集**（关键，避免覆盖时丢目标能力）：
   - 目标相对来源新增的 `data-test`（用正则提取两侧 `data-test="..."` 求差集）；
   - 目标是否使用 `useRuntimeStore` / `needsConfig` / `model-config-*` / `SETTINGS_ROUTE`（L10 个人模型配置能力）；
   - 目标相对来源新增的**可访问性绑定**（如 `:aria-current`）。
3. **判定形态**：
   - 目标 = 来源的**精简版**（绝大多数页面如此）→ 采用来源的模板与样式，再按第 2 步把目标独有能力嫁接回去；
   - 目标 = 来源的**增强版**（例：`AuthLayout.vue` 在来源基础上新增了 `authGraphMotion` 动效）→ **保留目标版本**，不要覆盖。这是本任务踩过的坑，务必先判定。
4. **composable / API / store 一律不动**：`git diff 68762e8 27bff16 -- src/frontend/src/composables/<x>.ts` 若为「一致」则可放心覆盖对应页面；若不一致，说明目标改了逻辑，必须逐段嫁接而不是覆盖。
5. **跑相关测试 → 按失败信息判断是「补能力」还是「改结构」**，禁止改弱断言。已有两例：
   - `h01` 要求卡片链接有 `aria-current="page"` → 目标有、来源无 → **补进来源版**；
   - `h12` 要求 `input.closest('label')` 含「学生用户名」→ 与来源的无障碍改法冲突 → 改成「label 只包 input + `aria-label`」两者兼得。

## 3. 剩余批次的已知要点

### 第 4 批：审核队列与版本面板
- `ReviewView.vue` 目标比来源少 868 行；来源版本是「紧凑发布状态栏 + 分类 tab + 宽松单列审核列表 + 默认折叠版本历史」，并使用两个插槽 `review-header` / `review-content` 与 `VersionPanel` 组合（**来源的 `VersionPanel` 有 `review-header` 插槽，目标没有**）。
- 目标分支的 `h09.test.ts` 与来源分支的版本**不是同一份**（目标版含 `rv-all-empty` 期待、来源版含空态互斥断言）。迁移后必须跑 `h09`，按失败信息决定是补能力还是调整；`specs/teacher-review-publish.md` 是行为约束来源。
- 空态互斥规则（来源版）：三类全空只显示一条总提示 `rv-all-empty`；只有当前分类为空才显示 `rv-empty-<kind>`；判断用服务端 `totals` 而非已加载数组长度。
- `h10.test.ts` 覆盖版本面板与审核页集成，注意来源版的 `review-header` 插槽迁移后 `h10` 里针对 `version-panel` 的断言。

### 第 5 批：图谱
- 目标**删除了** `src/frontend/src/graph/theme.ts`，来源的 `GraphCanvas.vue` 依赖它读取 CSS 变量着色。迁移画布配色时需要一并恢复 `graph/theme.ts` 并接回 `GraphCanvas`，否则画布会失去暖纸配色。
- 目标 `GraphCanvas.vue` 只差 4 行，其余图谱子组件差异都很小（`GraphToolbar` +7/−7、`KnowledgeCards` +6/−6、`NodeEditor` +5/−5、`Recommendations` +13/−13 等），可逐个小改。
- `h14.test.ts`（教师图谱）、`h11.test.ts` 与 `i06.test.ts`（学生图谱/学习路径）是回归重点。

### 第 6 批：问答页
- `ChatView.vue` 差异小（+18/−7）；`redesign-chat.test.ts` 与 `chat-send-lock.test.ts` 是回归重点，**发送期间防重复提交的断言不得改弱**。

### 第 7 批：API 设置页（本次迁移最需要注意）
- 目标文件是 `views/ModelSettingsView.vue`（114 行）+ `composables/useModelConfig.ts`（212 行）+ `api/modelConfig.ts`（`/api/v1/me/model-config` 四操作）+ `stores/runtime.ts`（会话票据与代际）。
- 来源的 `views/ApiSettings.vue`（含卡片布局、服务商预设、测试结果弹窗）与 `components/ModelSelect.vue`、`api/apiSettings.ts` 在目标分支**已删除**。
- 要求：外观参考来源 `ApiSettings.vue`，数据与操作**继续**走 `useModelConfig` + `modelConfig` 客户端 + `runtime` store。
- 禁止：恢复 `/api/v1/api-settings` 后端、恢复 JSON 覆盖环境变量、恢复「保存后重启」语义、新增向量接口、虚构模型列表或测试结果里的耗时/用量/维度字段。
- 目标已有能力必须保留：`MODEL_CONFIG_REQUIRED`、`STORAGE_UNAVAILABLE`、地址校验（含 `private_address`）、密钥 `keyRequired`、`busy` 互斥（加载/保存/测试/清除）、测试结果属于哪份配置的标注、表单改动后作废旧结果、演示模式提示。
- 回归重点：`l10.test.ts`（配置读写/清除确认/错误分类）、`n03-n05.test.ts`（会话隔离与操作互斥）、`d1-d3.test.ts`。
- 参考规格：`docs/superpowers/plans/2026-10-02-contest-sprint-a-personal-model-api.md`、ADR-080（`docs/decisions.md`）。

## 4. 环境与验证命令（实测可用）

工作目录：`SmartSketch_src/src/frontend`；Node 用 `D:\node`（把 `D:\node` 前置到 PATH）。

```powershell
$env:PATH = 'D:\node;' + $env:PATH; $env:CI='1'
npx vitest run <file...>          # 或全量 npx vitest run
npx vue-tsc --noEmit -p tsconfig.json
npx vue-tsc --noEmit -p tsconfig.node.json
npx vite build
npx vite preview --port 4173 --strictPort   # 浏览器验收用，配合 Chrome CDP
```

- **`vitest.config.ts` 的 `resolve.alias` 是本分支新增的必需项**：`tests/frontend/setup.ts` 在前端包之外，目标基线缺少这层解析时 **29 个测试文件全部加载失败**。不要删掉。
- 部分改动需要浏览器验证可见性（例如 `.app-notice`），**不能只断言 DOM 含文本**——审查报告 R2 就是这么被抓出来的。可用 Chrome CDP（`--headless=new --remote-debugging-port`）+ `Runtime.evaluate` 读 `getBoundingClientRect()`、`getComputedStyle()` 与 `Accessibility.getPartialAXTree`。
- 后端未启动时，`vite preview` 的 `/api` 代理会失败，页面进入错误态；这只能验证容器、配色、溢出与崩溃，**带数据的验收需要先启动后端**。

## 5. 不可越界的边界（已逐次核对）

`git diff --name-only 68762e8 HEAD` 目前只含 `src/frontend/**` 与 `tests/frontend/**`。以下均**不得修改**：`src/backend/`、`src/contracts/` 及其生成物、数据库迁移、系统运行配置与启动脚本、真实密钥/配置/数据库。

## 6. 当前验证状态（截至 `ffae94d`）

- `vue-tsc` 两套 tsconfig：0 错误。
- `vitest run`：29/29 测试文件通过（第 1 批后基线全绿）。
- 第 2 批相关：`h01 h02 h09 h11 h12 h14` 274 项通过。
- 第 3 批相关：`h02 h11 h12` 164 项通过。
- `vite build`：成功（CSS 32.64 → 40.01 kB）。
- 浏览器：`/teacher`、`/courses/c1`、`/settings/model` 零控制台错误、零页面异常，暖纸令牌生效，窄屏 420px 无横向溢出。

## 7. 下一步建议顺序

1. 第 4 批（审核队列 + 版本面板），跑 `h09`、`h10`。
2. 第 5 批（图谱 + 画布配色），跑 `h11`、`h14`、`i06`。
3. 第 6 批（问答页），跑 `redesign-chat`、`chat-send-lock`。
4. 第 7 批（API 设置页），跑 `l10`、`n03-n05`、`d1-d3`。
5. 全量回归 + 构建 + 启动后端做带数据的浏览器逐页验收。
6. 补齐审查建议的验收：提示可见性、卡片容器、审核分类、设置弹窗。
