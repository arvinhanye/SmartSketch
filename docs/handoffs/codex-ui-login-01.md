# UI-LOGIN-01 交接：登录页提示与视口布局

- 交付：`App.vue` 的路由提示加入可访问的关闭按钮，关闭仅隐藏当前提示，路由变化后恢复；登录页主区域使用顶栏以下的剩余视口高度，矮窗口中表单栏可独立滚动。
- 规格与架构：`specs/identity-access.md`、`docs/architecture.md` 已同步 UI 行为；接口、数据模型、环境变量均未变。
- 验证：`npm run test -- --run h13.test.ts` 29 passed；前端全量 `npm run test -- --run` 766 passed；`npm run type-check`、`npm run build`、`git diff --check` 通过。浏览器 720px 高视口中，关闭提示前后文档高度均为 720px，关闭后表单仍显示。
- 环境限制：`./scripts/verify.sh` 在 WSL 运行时被 Windows CRLF shebang 阻断（`env: bash\r: No such file or directory`），本机未安装 Git Bash。当前工作树基线 `main@62eb8c7`，比 `origin/main` 落后 6 次提交；`.git` 写权限不足，无法快进。
- 后续：具备正常 Bash 环境时重跑 `./scripts/verify.sh`；若集成到最新 `main`，先在可写 Git 元数据的环境中快进或移植本次变更。无迁移或回滚步骤。
