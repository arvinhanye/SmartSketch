# Codex 交接：B01 前端构建与单页挂载

- 任务与状态：B01 DONE；父任务 M0-02 仍为 IN PROGRESS（B02～B04、B15 待做）。
- 分支与基线：`codex/b01-vue-scaffold`，base `50a15c9`；本交接随 B01 分支提交，提交范围以该分支 HEAD 相对基线为准。
- 范围：`src/frontend/package.json`、`package-lock.json`、`tsconfig.json`、`vite.config.ts`、`index.html`、`src/main.ts`、`src/App.vue`；同步 `src/frontend/README.md`、`docs/architecture.md` 和 `docs/tasks.md`。

## 交付与决定

- 建立 Vue 3 + TypeScript + Vite 的单页应用；`index.html` 提供 `#app`，`main.ts` 挂载 `App.vue`。页面只显示应用名称和基础就绪文案，无路由、业务请求或 DTO。
- 依赖在 `package.json` 精确固定，并提交 `package-lock.json`。Vite 8.3.0、Vue 3.5.43、`@vitejs/plugin-vue` 6.0.9、`vue-tsc` 3.3.11、TypeScript 5.9.3。首次试用 TypeScript 7.0.2 时，`vue-tsc` 因包导出路径不兼容而失败，已改为实际验证通过的 5.9.3。
- 构建产物 `dist/` 与安装目录 `node_modules/` 均在仓库现有 `.gitignore` 中，不入库。

## 实际验证

| 命令或方法 | 结果 |
| --- | --- |
| `npm ci --prefix src/frontend --no-audit --no-fund` | exit 0；45 个包由锁文件重新安装 |
| `npm --prefix src/frontend run type-check` | exit 0；`vue-tsc --noEmit` |
| `npm --prefix src/frontend run build` | exit 0；Vite 8.3.0，13 个模块，产物写入被忽略的 `dist/` |
| `npm --prefix src/frontend run dev -- --host 127.0.0.1`；浏览器打开 `http://127.0.0.1:5173/` | 页面标题为“智绘学途 · SmartSketch”，页面可见“智绘学途”与“前端基础应用已就绪。”；随后关闭临时标签和服务 |
| Git Bash 临时提供 `python3` 函数后运行 `./scripts/verify.sh` | `block-dangerous hook tests passed.`、`Scaffold verification passed.`，exit 0 |
| `git diff --check` | exit 0 |

本机 Node.js 24.16.0、npm 11.13.0。浏览器烟测验证了开发服务器的实际 Vue 挂载；B02 尚未建立正式前端测试脚本。

## 接口、配置与风险

- 无 REST/SSE、数据模型或环境变量变更。新增 npm 脚本：`dev`、`type-check`、`build`、`preview`。
- B01 不声明 M0-02 完成；B02 需建立可发现仓库外层 `tests/frontend` 的测试配置，B03 才引入角色路由。
- 首次依赖安装需要 npm 包索引；后续应使用 `npm ci` 复现锁文件。Node 版本要求见 `package.json`。

## 下一步与回滚

- 首个后续动作：B02 建立 Vitest 配置及实际可运行的前端测试命令，不把零用例当作通过。
- 回滚只撤销 B01 分支新增的前端骨架与本轮文档；无数据库迁移或外部状态。
