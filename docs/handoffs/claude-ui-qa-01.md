# UI-QA-01：前端体验审计与问答链路优化

review_status: ready_for_review
task_id: UI-QA-01
日期：2026-10-09；负责人：Claude；基线：main `5398a1f`，分支 `claude/smartsketch-frontend-ux-672666`。范围：电脑端（手机端只验证无溢出，用户 2026-10-09 决定）。未提交、未推送。

## 做了什么（用户可见变化）
1. **画布不再占 Tab 停靠点**（`graph/a11y.ts`、`graph/lifecycle.ts`）：G6 给 4 层 canvas 设了 `tabindex=1`，学生图谱和教师图谱的前 4 次 Tab 都落在看不见的 canvas 上。现在移出 Tab 顺序（含画布重建）。
2. **出处属于回答**（`composables/chatSources.ts`、`ChatView.vue`）：右栏只显示“当前回答”的出处；最后一条是“资料未覆盖/未完成/已停止/生成中”时写明没有出处，不再显示上一条回答的出处。点回答下的“查看 N 处出处”或正文编号，面板切到那一条；提新问题后回到最后一条。
3. **回答卡**（`components/chat/AnswerCard.vue`）：状态标签（图标 + 文字：生成中/已回答/资料未覆盖/未完成/已停止）；资料未覆盖是信息色并给下一步（换个问法 / 在图谱中查看）；失败卡原因只写一次并带重试。
4. **复制回答（含出处）**（`composables/useCopyFeedback.ts`）：正文 + 空行 + “出处：”+ 每条 `[n] 文件 · 页/章节`；成功提示 3 秒后消失，失败提示保留。
5. **固定输入区与跟随最新**（`composables/useFollowLatest.ts`）：输入区固定在底部；用户在底部时新内容自动滚到最新，上翻阅读时不强拉并显示“回到最新”。
6. **页面统一**：问答页改用 `PageSheet` + `PageHeader`（与其他内容页一致），样式用 `--gw-*`；删除 `ui.css` 里 `.ui-chat-workspace` 整段（它把 `--ss-*` 重映射成浅色，名字与内容相反）。

## 与计划的差异 / 更正
- **更正审计结论**：审计报告里我说 ui.css 里有“没生效的暗色问答样式”，不对——那段是生效的，只是把 `--ss-*` 重映射成浅色值。本次已整体替换为 `.light-surface` + `--gw-*`。
- **推荐理由（“解锁度 1.0000”等）未改**：`reason` 是服务端整句，后端测试（`test_l14_reason.py`）与 `specs/learning-path.md` §4 要求前端原样展示；前端解析句子会脆弱。已移入待确认（需先改服务端文案和规格）。
- 来源只保留右栏列表（当前回答），每条回答下用“查看 N 处出处”切换，没有再铺一排来源条（避免重复信息，并保住既有 `.source-list__item`/`aside` 钩子）。

## 文件
- 新增：`graph/a11y.ts`；`composables/{chatSources,useCopyFeedback,useFollowLatest}.ts`；`components/chat/AnswerCard.vue`；测试 `graph-tab-stops`、`chat-sources`、`use-copy-feedback`、`use-follow-latest`、`answer-card`、`chat-ui-qa`（共 6 个文件、`tests/frontend/`）。
- 修改：`graph/lifecycle.ts`（挂/摘监听）、`views/ChatView.vue`、`components/ChatMarkdown.vue`（样式）、`components/AppIcon.vue`（`copy`/`info`）、`styles/ui.css`（删问答段）。
- 文档：`specs/grounded-qa.md`（新增「问答页前端呈现」F1–F7）、`specs/course-knowledge-graph.md`（画布键盘约定）、`docs/tasks.md`、计划 `docs/superpowers/plans/2026-10-09-ui-qa-01-chat-chain.md`；把“问答页是暗色页”的旧说法标为作废（`docs/frontend-ui-handoff.md`、批次 2 计划与 brief、图谱工作台设计规格 §3.1）。
- 既有测试**没有修改**（`redesign-chat`、`l10`、`l12`、`l13-kp-link`、`chat-send-lock` 等原样通过）。接口、契约、后端、数据、权限均无变化。

## 验证（实际命令与结果；测试与浏览器验收分开）
**自动化测试**
- 先 RED 后 GREEN：六个新测试文件在实现前均因模块不存在或行为缺失而失败；`chat-ui-qa` 实现前 8 条失败、1 条回归守卫通过。
- `npm --prefix src/frontend run type-check`：无错误输出。
- `npm --prefix src/frontend run test -- --run`：72 文件 / 1263 条通过（改动前 1227）。
- `npm --prefix src/frontend run build`：成功（原有的 >500 kB chunk 提示未变）。
- `scripts/verify/frontend.sh full`：exit 0，`PASS frontend gate (full)`。
- `./scripts/verify.sh`（basic，缺省）：通过。
- E2E（演示模式，一次性 Neo4j）`scripts/e2e.sh tests/e2e/teacher.spec.ts tests/e2e/student.spec.ts`：2 passed；个人模式 `E2E_LLM_MODE=personal … tests/e2e/personal.spec.ts`：4 passed（含“两门课问答出处互不串课”）。
- **未运行**：`./scripts/verify.sh full` / `integration` 的后端与集成部分（后端、契约、数据库未改动）。

**浏览器验收**（一次性演示栈 + 演示模型 + Playwright/Chromium；脚本与截图在会话临时目录，不进仓库）
- 1440×900、1280×800、768×1024、390×844 × 教师/学生 12 个页面（含问答与两个图谱页）：48 次加载，无横向溢出、无控制台错误；页面高度与改动前一致。
- Tab 顺序：学生/教师图谱页第一个停靠点由 canvas×4 变为“我的课程”链接；问答页 Tab 顺序在脚本中途出错未取到（脚本里拦截规则把页面地址一起拦了，不是应用问题），未单独复核。
- 问答实走：已回答 → 资料未覆盖（面板 0 条出处并写明原因）→ 长对话（输入区底边 820 ≤ 视口 900）→ 上翻后新回答不被拉动（scrollY 保持 0）且出现“回到最新”→ 点击后回到底部且按钮消失 → 复制（提示“已复制回答和出处。”，剪贴板内容为正文 + 出处）→ 失败卡（原因一次、有重试）。
- 对比度（逐文字节点计算样式）：问答页 0 项不达标（改动前“发送”禁用态 4.48:1 已不再出现）；图谱页 0 项。焦点指示扫描：问答页 0 项；学生图谱搜索框被标记一次，是脚本误报（该框的焦点环在外层容器上，截图可见）。
- 200%（720×450）无横向溢出。
- **未验证/未做**：`prefers-reduced-motion` 下三点静止（仅样式规则，未实测）；读屏；画布像素对比度；真实模型、真实 63 节点课程；键盘走查整条问答链路；流式中途“回到最新”的真实效果（演示模型流式极短）；用户视觉签收。

## 风险
- `useFollowLatest` 假设页面滚动在 `window`（现为整页滚动）；若以后改成内部滚动容器需调整。
- 画布 tabindex 由 MutationObserver 维持；G6 升级若改变创建方式需复测（`graph-tab-stops.test.ts` 覆盖）。
- 问答页样式现在依赖 `.light-surface` 作用域；`graph-theme.test.ts` 的 token 一致性测试仍通过。

## 回滚
各部分独立：画布（`a11y.ts` + `lifecycle.ts` 两处）、问答（`ChatView.vue`、`AnswerCard.vue`、`ChatMarkdown.vue`、`ui.css` 删除段）、文档分别 `git revert`；无数据与接口变化。

## 下一步（第二批候选，已确认可做、未排期）
成员移除行内二步确认；教师图谱未保存离开前提示（`beforeunload`）；首次访问登录页不显示“未登录”红色提示；教师图谱详情来源行排版与标题焦点框；模型设置演示模式提示与教师页重名控件；资料上传原生英文文件按钮与“可拖放”暗示；课程概览页两个主按钮。待确认：推荐理由文案（需服务端）、对话历史持久化、示例问题。
