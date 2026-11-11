# Claude 交接：UI-PINE-01 青松明黄界面改版（进行中，2026-11-04～05）

## 范围

按设计预览 v3（https://claude.ai/artifact/Vg9yqHzdfAgEVvu1bAKnRV）改前端配色、Logo、外壳、登录/注册与页面外围。计划：`docs/superpowers/plans/2026-11-04-ui-pine-redesign.md`。分支 `claude/ui-pine-redesign`（本地，未提交、未推送）。

## 工作区说明

`~/Desktop/SmartSketch-main` 原是 main 的压缩包副本（非 git）。本次 `git init` 后从本机 `~/SmartSketch` 取 `origin/main`（`3f26766`，与压缩包一致）并 `reset --mixed`，未改动任何工作区文件；`origin` 指向 GitHub。之后在 `claude/ui-pine-redesign` 上工作。

## 已完成（P1–P4 的样式部分）

- **tokens**（`styles/tokens.css`）：`--ss-*` 换成深松外壳（`#0f3d36` 等）；新增 `--ui-*` 页面色板（浅松灰底、白色面板、青松 `#0e6b5c`、明黄 `#f5b82e`、控件边界 `--ui-edge #788c86`）。`--gw-*` 与 `graph/theme.ts` 未动，图谱画布样式不变。
- **Logo**：新增 `components/BrandMark.vue`（阶梯路线标志，`color` / `onDark` / `mono` 三种）。
- **外壳**：顶栏去掉「智」字标志；演示模式横幅改为顶栏标签（保留 `data-test="mode-demo"`）；当前导航项明黄底；主区浅松灰底；未登录页顶部旧页眉与标语在登录/注册页不再显示；旧侧栏的「智」字删除。
- **登录 / 注册**：`LoginLayout.vue` 改为分栏封面（左白色表单栏 + 右青松品牌面板、几何装饰、右下角对勾徽标）；登录表单去掉「开始你的学途 / 欢迎回来 / 说明」三行，改下划线输入框与胶囊按钮；注册表单同风格，去掉提交按钮箭头。
- **页面**（`styles/ui.css`）：`PageSheet` 页面内把 `--gw-accent/selected/hover/line/panel/edge` 换成青松明黄；课程列表改为白色卡片；卡片加柔和阴影。
- **图谱页外围**（`styles/ui.css` 末尾）：`.app--graph .graph-workspace` 内的强调色换青松；侧栏白底；浮层（章节菜单、预览卡、概览条、图例）与右上工具组、缩放组、小地图改白色圆角卡片加阴影；布局切换钮深松；第一条推荐明黄高亮；按下态与主按钮青松。

- **继续学习主卡**（第二轮）：`composables/resumeLearning.ts`（纯函数 + `useResumeLearning`）、`components/courses/ResumeCard.vue`，接入学生课程列表页。候选为本人以学生身份加入且有发布版的课程（前 5 门），按自身进度行 `updated_at` 选最近学过的一门，无记录时取第一门并写「开始学习」；只读第一条推荐，理由为短语（「学完可解锁 N 个知识点」/「前置知识已掌握」/「本课程知识点已全部掌握」）；主按钮跳 `?kp=&v=` 直达该知识点。任一请求失败时主卡不出现，不影响列表。教师端不显示。
- **模型 API 三步式**（第二轮）：服务商由下拉框改为卡片式单选组（原生 radio，`data-test="mc-provider-<id>"`）→ API Key（旁边放「测试连接」与模型目录状态）→ 模型；服务地址与「关闭模型思考」收进「高级选项」，选「自定义」时服务地址直接放在第 1 步；「去配置」改为聚焦当前选中的服务商；去掉三段说明文字与底部「密钥安全与接口说明」。

## 验证（已跑）

- 基线（改动前）：type-check 通过；vitest 77 文件 / 1302 条全过。
- 改动后：type-check 通过；vitest 全量 77 文件 / 1302 条通过；`vite build` 通过；`./scripts/verify.sh`（basic）exit 0。
- 环境补充：`.venv` 原只有运行依赖，按 `src/backend/pyproject.toml` 的 `[test]` 额外依赖补装后门禁才能跑；Docker Desktop 更新后 `docker` 不在 PATH，用 `PATH="$HOME/.docker/bin:$PATH"` 启动演示环境。
- 测试改动：`tests/frontend/register-layout.test.ts` 品牌标题断言由「把知识连起来」改为「智绘学途」（设计按 v3 变更）。
- 第二轮：vitest 78 文件 / 1311 条通过（新增 `tests/frontend/resume-learning.test.ts` 8 条，先红后绿；`model-settings-ui` 新增三步结构 1 条），type-check、build、`verify.sh` basic exit 0。测试改动：`model-discovery.test.ts` 9 处选择服务商由 `select.setValue` 改为点选对应单选卡；`model-settings-ui.test.ts`「去配置」的聚焦目标由服务地址改为当前服务商。
- 第二轮浏览器：学生课程页主卡（真实数据：下一步「后缀表达式求值算法」，1/64）并点「继续学习」直达该知识点详情；学生与教师的模型 API 页（教师页两列）。修正：fieldset 与旧规则 `.ui-field:has(#mc-base-url) { grid-column: 2 }` 造成的两列错位。
- 浏览器（演示环境，1440×900）：登录、注册（另看 1280×720）、学生课程列表、学生图谱页（含节点预览）、课程问答、模型 API 设置均已截图走查；修正了布局切换钮被工具组底色覆盖、图标不可见的问题。未测：教师端各页、窄屏、Safari。

## 未完成

1. 教师端「向量模型 API」卡片仍是原来的下拉表单，未改为三步式。
2. 课程卡片上的逐门进度（每门需一次进度请求，暂未加）。
3. 图谱页工具轨合并为单列（目前仅换样式，结构未变）。
4. 邀请码（P6：规格、ADR、契约、迁移、前后端）。
5. 教师端页面（资料、审核、成员、教师图谱）与窄屏的截图走查。
6. 提交：改动尚未提交，等用户确认。

## 风险

- 对比度已按 WCAG 核对：外壳文字、链接、主按钮、三级文字均 ≥4.5:1，控件边界 ≥3:1；`graph-theme.test.ts` 通过。
- `tests/frontend` 全量并发时有 3 条 5 秒超时（`h14` / `l14` / `student-graph-workbench`），单独重跑通过，属负载问题。
