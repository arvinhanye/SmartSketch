# OPT-06D：StudentGraphView.vue 按职责拆分

- task_id：OPT-06D；负责人 Codex；状态 IN_PROGRESS（实现、前端全量与浏览器走查通过，共用门禁/最终审查待完成）。
- 本地分支 `codex/opt-06d-student-graph`；未来 PR 以 `codex/opt-06c-materials` 为 base，仅包含本项范围；暂不推送或合并远端 PR。

## 文件与边界

`StudentGraphView.vue` 从 789 行降为 635 行，保留页面路由/API 注入、模板与样式。`useStudentGraphPanel.ts` 负责面板宽度、分隔条、开关、observer/键盘生命周期和焦点；`useStudentGraphPresentation.ts` 负责画布聚焦数据、章节布局输入、预览和掌握进度。传入原 refs/computed 与回调，不增加 DOM 包装层，不更改 scoped 样式、文案或事件绑定。

## 验证

- TypeScript AST 审计：81 个原声明一致；模板/样式逐字相同，证据 `d-audit.json`。
- `npm --prefix src/frontend run test -- --run h11.test.ts i06.test.ts l13-kp-link.test.ts l14.test.ts student-graph-workbench.test.ts`：**5 文件 / 135 passed，exit 0**。
- `PATH="$PWD/.venv/bin:$PATH" scripts/verify/frontend.sh full`：**82 文件 / 1375 passed**，type-check、build exit 0；已有 jsdom/测试警告和 bundle 大小提示保留。
- 本机 Chrome，固定伪造课程数据/API，1440/1280/768/390 × 900：概览与深链接详情、宽屏分隔条拖拽/键盘、窄屏 Esc/抽屉、关闭后焦点返回、掌握状态写入与推荐刷新、列表/图谱及布局切换均通过，无 pageerror、无横向溢出。并非真实课程/后端 E2E。
- 初始截图 6/8 逐像素一致，其余两张仅缩略图异步绘制时机差异；补充等待缩略图实际绘制后，**8/8 截图逐像素一致**，布局尺寸/操作计数完全一致，证据 `visual-comparison-settled.json`。基线服务器使用经 Git 比较与整合基线 `src/frontend/` 完全相同的原工作区源码。
- 共用 `./scripts/verify.sh` 与最终独立审查待四项收尾；证据目录 `.superpowers/sdd/2026-11-10-opt-06-responsibility-split/`，含 `d-targeted.log`、`d-frontend-full.log` 及 `.exit`、`before/after` 与 `before-settled/after-settled` 截图和 results.json。

## 接口、数据与未完成项

无 API、数据、依赖或公开行为变化；架构只同步内部映射。当前未完成共用门禁与最终审查。回滚仅撤销本项代码提交，无数据迁移。
