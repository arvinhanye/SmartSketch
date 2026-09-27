# UI-AUTH-ART-02 交接：认证页装饰知识图谱

- 交付：`AuthLayout.vue` 中的单幅固定示意图改为 8 组主题各异的 SVG 小图谱。挂载时随机生成节点轻微错位和图谱位置，以节点边界避让留出文字间距；绘图区域位于品牌说明文字下方。装饰 SVG 对读屏隐藏，禁用指针事件、文字选择和复制事件。
- 版本：改动前本地提交 `8d3d992`；本轮改动完成后另建本地提交。
- 规格与架构：`specs/identity-access.md`、`docs/architecture.md` 已同步装饰图行为。无接口、数据模型、依赖或环境变量变化。
- 验证：前端 `h13.test.ts` 30 passed、全量 767 passed；`npm run type-check` 和 `npm run build` 通过，`git diff --check` 通过。浏览器连续 3 次重新加载，8 组位置变化、37 个标签无相互重叠，图谱与说明文字之间留空，720px 视口页面无纵向溢出；拖拽图谱文字后选区为空。
- 环境限制：`./scripts/verify.sh` 已尝试，但本机契约工具链缺少 `openapi-typescript` 命令，临时子进程的 `python3` 也不可见，契约门禁失败；这不属于本轮前端变更。
- 后续：在装有项目锁定契约生成器、可访问 `python3` 的 Bash 环境中重跑 `./scripts/verify.sh`。无迁移或数据回滚步骤。
