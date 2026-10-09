# 教师端与学生端前端复审
review_status: ready_for_review
task_id: CLAUDE-UI-REVIEW-20261008
日期：2026-10-08；负责人：Claude；worktree 分支 `claude/smartsketch-frontend-review-4670f1`；基线 PR #323 head `f76020f`。

## 复审方式（可复现）
隔离环境，不依赖原开发者机器：Python 3.11 venv（`pip install -e './src/backend[test]'`）、`npm ci`（根目录 + `src/frontend`）、一次性 `neo4j:5.26-community` 容器（端口 17690，APOC）、全新 SQLite、`LLM_MODE=demo` / `EMBEDDING_MODE=demo`（无付费调用）。步骤：
```bash
python -m app.repositories.sqlite && python -m app.repositories.graph_migrations   # 在 src/backend，应用到 019
SEED_DEMO_PASSWORD=<本地口令> python scripts/seed-demo-accounts.py                # demo_teacher / demo_student / demo_student2
python -m app &  python -m app.workers &                                          # API(18321) 与 worker
python scripts/import-demo.py                                                     # 示例课程（64 知识点、71 关系），已发布 v1
SMARTSKETCH_API_TARGET=http://127.0.0.1:18321 npx vite --port 15322              # 在 src/frontend
```
教师 `demo_teacher`、学生 `demo_student2`（口令为上面设置的本地口令，仅用于该一次性环境）。Playwright 截图脚本放在会话临时目录，不入库；可检查的运行方式即上面环境 + `tests/frontend/teacher-viewport.browser.cjs`（`E2E_BASE_URL=… PLAYWRIGHT_MODULE=…`）。

## 问题清单（按严重度；均已复现）
### 功能阻塞 / 明显缺陷（已修）
1. **切换布局后小地图消失**（教师与学生）：G6 小地图插件销毁时会把传入容器从 DOM 摘掉，画布重建沿用旧容器 → 小地图不再出现，但开关仍显示“收起小地图”。修：`GraphCanvas.vue` 每次 `stop()` 换用新容器（`key`），重建前等新容器挂上（仅在组件根节点已连接时等待、最多 3 次，避免 KeepAlive 下空转）。验收：浏览器层次→力导向→层次三次均有小地图；单测 RED（还原修复失败）/GREEN。
2. **教师下拉选择知识点不带动画布**：详情切换了，画布仍停在原处（选中节点常不在视口）。修：`TeacherGraphView.vue` 的下拉与详情关联链接选择后聚焦画布，与搜索定位一致；有未保存修改时先确认，取消则画布不动。验收：3 条新增 H14 用例 + 浏览器确认被选中节点居中高亮。
3. **窄屏学生图谱页下方出现约 800px 空白滚动区**：收起的覆盖面板虽 `visibility:hidden`，仍按自身 1568px 内容撑高页面。修：`graph-workspace.css` 收起时 `max-height:100%; overflow:hidden; min-height:0`，打开时恢复。验收：390×844 页面高度 1669→885，抽屉仍可打开；CSS 策略测试。
4. **演示模式下学生图谱底部控件落在视口外**：舞台高度按“无横幅”计算，演示横幅把舞台顶下推 45px，小地图/缩放/计数条被切掉 17–33px。修：`--gw-banner` 变量扣除横幅占位。验收：1440×900 / 1366×768 / 1920×1080 舞台底部 888 / 756 / 1068，均在视口内。

### 明显体验问题（已修）
5. 发布历史显示原始 ISO 时间 `2026-10-08T17:00:08.854000Z`，与成员页本地化时间不一致 → 本地时区 `YYYY/MM/DD HH:mm` + `<time datetime>`。
6. 课程概览页的列表标题“其他课程”却包含当前课程 → “全部课程”。
7. 学生模型设置页出现教师措辞（“图谱生成”“上传资料”）；学生只能提问 → 页面副标题/卡片/状态按角色显示。
8. 关系编辑页起点永远是“请选择”，即使已选中节点 → 进入“编辑关系”时已选中节点自动作为起点（图上第一次点击即为终点；H14 一条依赖旧点击序列的用例随之更新并注明）。
9. 教师编辑页标题行、“返回课程”独占一行，画布上方提示与“选择知识点”各占一行，共多占约 55–70px 竖向空间 → “返回课程”并入标题行；提示与键盘选择器合为一行。1440×900 下图谱绘图区由约 390px 增至约 510px（按截图估算），仍无长表单撑高图谱，视口回归脚本 5 个宽度通过。

### 可选美化 / 建议（未改，需要产品取舍）
- **（已由用户确认并实现，见 `claude-teacher-overview-20261008.md`）教师首屏缩放**：首屏按“可读缩放”聚焦入口节点（学生页的既定设计）；教师打开 64 个节点的层次图时看到的是根节点与出边，容易误以为图谱不完整。“适应画布”后层次布局因单章 64 个叶子被拉成约 12:1 的长条（标签靠避让策略显示），力导向更紧凑但标签重叠。成熟图谱软件（Bloom/Kumu/Obsidian）首屏通常是整体概览 + 搜索聚焦。建议：教师页首屏改“适应画布”，并为单章大树增加径向/缩进树布局。属布局算法变更，需要用户确认后再做。
- 教师页缺少“节点类型”图例/计数（学生页有）；关系筛选图例已有。
- 问答答案末尾“涉及的知识点”一次列出 25 个 chip，建议默认折叠到 8 个。
- 课程概览入口卡与侧栏用同一套图标表示不同含义（网格=概览/成员，行线=资料/课程）。
- 原生文件选择控件文案随浏览器语言（中文浏览器显示“选择文件”），不是缺陷。

## 与已确认方向的一致性
保留紫色强调色、浅色内容区与公共外壳；登录插画与浮动提示未动；上传页简洁布局、审核类别一次展示、单一模型选择控件、通用/向量并列、教师左侧可调宽详情 + 顶部新建、长表单内部滚动均未改动。没有新增依赖，没有改后端接口/数据模型/权限（后端仅迁移 019 的回滚注释，见 `claude-ci-repair-20261008.md`）。

## 改动文件
`src/frontend/src/components/GraphCanvas.vue`、`VersionPanel.vue`；`views/TeacherGraphView.vue`、`CoursesView.vue`、`ModelSettingsView.vue`；`styles/graph-workspace.css`、`styles/ui.css`；`specs/course-knowledge-graph.md`（新增“图谱工作区交互约定”）；测试 `tests/frontend/{graph-canvas-enhanced,graph-detail-layout,h14,model-settings-ui}.test.ts`。

## 验证（实际命令）
- `npx vitest run tests/frontend/{h14,h05,h07,h10,graph-detail-layout,graph-canvas-enhanced,model-settings-ui}.test.ts` 等专项通过；`scripts/verify/frontend.sh full`：type-check 通过，62 文件 / 1194 条，build 通过（G6 大 chunk 提示为既有）。
- 浏览器：1440×900 / 390×844 / 1366×768 / 1920×1080 实际登录教师与学生逐页检查；`tests/frontend/teacher-viewport.browser.cjs` 退出 0；教师/学生/个人模式 E2E 见 `claude-ci-repair-20261008.md`。
- 最终门禁：见下节。

## 最终门禁
在提交 `c8c33fb`（代码最终态）上，单独执行（无其它重任务并发）：
- `./scripts/verify.sh basic`：PASS，退出 0（实现此前已单独运行；契约 36 路径 / 133 schema）。
- `./scripts/verify.sh integration`（含 basic + full）：**PASS，退出 0**。其中后端全量 3975 passed / 27 skipped（均在 `scripts/verify/allowed-skips.txt` 登记，不计为通过的功能证明）；前端全量 62 文件 / 1194 passed，type-check 与 build 通过；集成 393 passed / 4 skipped（含此前失败的 `test_f13::test_migration_009_rolls_back`）；图库专项 44 passed；E2E 教师 + 学生 2 passed，个人模式 4 passed（演示模型/本机假供应商）。
- `./scripts/verify.sh full` 的前后端部分已包含在 integration 内（同一命令的前两步），没有单独另跑一遍；因此 full 不作为独立运行记录。
- 3 项历史“暂不补测”（浏览器可见首字、v3+ 思考开启基线、关闭思考 MD 抽取）继续标为**未测**，未恢复付费测量。
- 环境提示：评审用 Neo4j 容器中途退出过一次（`--rm` 容器，原因未查明，疑与同机 Docker 资源争用有关），已重建环境重新核对；门禁运行使用各自的一次性容器，不受影响。

## 回滚
前端改动均为独立提交，`git revert <hash>` 即可；无数据迁移、无接口变化。
