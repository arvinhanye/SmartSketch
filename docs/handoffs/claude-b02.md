# Claude 交接：B02 前端测试配置

- `task_id`: B02
- `review_status`: ready_for_review
- `worktree`: `/Users/arvinhan/Desktop/SmartSketch/.claude/worktrees/a09-dev-environment-check-8e5e93`（分支 `claude/frontend-dev-04eee7`）
- `base_commit`: `dddafb3`（PR #15 合入后的 main）
- `head_commit`: 见本分支提交
- 父任务：M0-02 仍为 IN PROGRESS（B03、B04、B15 待做）

## 交付物

| 文件 | 内容 |
| --- | --- |
| `src/frontend/vitest.config.ts` | 用 `mergeConfig` 继承 `vite.config.ts`；`dir` 指向仓库外层 `tests/frontend`，收集 `**/*.test.ts`，排除点开头目录；jsdom 环境；setup 文件；`server.fs.allow` 放行 tests 目录；小插件把 `tests/frontend` 中的裸模块导入改为从 `src/frontend` 解析 |
| `tests/frontend/setup.ts` | `enableAutoUnmount(afterEach)`，每个用例后卸载挂载的组件 |
| `tests/frontend/b02.test.ts` | 5 个用例：从外层挂载 `App.vue`；setup 生效（挂载可见 → 下一用例已卸载）；用项目 `npm test` 脚本在临时探针目录上嵌套运行，断言「断言失败 → 非 0 且失败原因是断言」「零用例 → 非 0」 |
| `src/frontend/tsconfig.node.json`（新增） | Node 侧类型检查：`vite.config.ts`、`vitest.config.ts`、`tests/frontend/**/*.ts`，`types: ["node"]`；`paths` 先查 `@types/*` 再查包本身，让外层测试找到 `src/frontend/node_modules` |
| `src/frontend/tsconfig.json` | include 去掉 `vite.config.ts`，只含应用代码（处理 B01-R01） |
| `src/frontend/package.json` / `package-lock.json` | `test: vitest`；`type-check` 依次检查两个 tsconfig；新增精确版本 `vitest@5.0.1`、`@vue/test-utils@2.5.1`、`jsdom@30.1.1`、`@types/node@22.20.4`；`engines.node` 收紧为 `^22.22.2 \|\| ^24.15.0 \|\| >=26.0.0` |
| `src/frontend/README.md`、`docs/architecture.md`、`docs/tasks.md` | 测试命令与约定、架构入口一节、任务状态 |

## 决定与理由

- **jsdom 而非 happy-dom**：规范符合度更高，后续可访问性断言更可靠；代价是 Node 下限抬高（见风险）。
- **resolve 插件而非 `resolve.dedupe` 列包名**：外层测试的所有裸导入统一从前端包解析，B04 引入 pinia 等依赖时不用再改配置。插件只作用于 importer 位于 `tests/frontend` 的导入，应用代码的解析不变。
- **退出码用例放进常驻测试**：不是只在本轮手工验证一次，今后有人给脚本加 `|| true` 或打开 `passWithNoTests` 都会被 B02 用例检出（K11 把前端测试接入 CI 后自动执行）。探针目录以 `.b02-probe-` 开头，配置排除点目录，外层收集不会误跑；用例结束时删除。

## 实际验证（Node 26.4.0 / npm 11.17.0）

| 命令/方法 | 结果 |
| --- | --- |
| 配置前运行 `npm --prefix src/frontend run test -- --run ../../tests/frontend/b02.test.ts`（RED） | exit 1，`Missing script: "test"` |
| `npm ci --prefix src/frontend --no-audit --no-fund` | exit 0；149 项 `resolved` 全部来自 `registry.npmjs.org`；npm 提示 `fsevents` 安装脚本未批准（可选依赖，不影响） |
| 计划验收命令 `npm --prefix src/frontend run type-check && npm --prefix src/frontend run test -- --run ../../tests/frontend/b02.test.ts` | exit 0，5 passed |
| `npm --prefix src/frontend run test -- --run`（全量） | exit 0，1 file / 5 passed |
| `npm --prefix src/frontend run build` | exit 0 |
| `./scripts/verify.sh` | exit 0 |
| `git diff --check` | exit 0 |

反向篡改（逐项改坏后运行，随即恢复，恢复后重新全绿）：

| 篡改 | 被哪条用例/命令检出 |
| --- | --- |
| 删除 `setupFiles` | 「下一个用例开始前已被自动卸载」失败 |
| 打开 `passWithNoTests: true` | 「一个用例都没收集到时命令非 0」失败 |
| 脚本改为 `vitest \|\| true` | 两条退出码用例失败（`--run` 被接到 `true` 之后，嵌套运行进入 watch 模式，30s 超时） |
| 未加 resolve 插件 | 整个文件报 `Failed to resolve import "@vue/test-utils"` |
| 遗留一个含失败用例的点目录后全量运行 | 被跳过，1 file / 5 passed；`--dir` 直接指向该目录则收集并失败 |
| 测试里调用不存在的方法；`vitest.config.ts` 中类型错误；`src/main.ts` 使用 `process` | `type-check` 分别报 TS2339、TS2322、TS2591，exit 2 |

## 接口、配置与风险

- 无 REST/SSE、契约、数据模型或环境变量变化。
- **Node 下限抬高**：原 `^20.19.0 || >=22.12.0`，现 `^22.22.2 || ^24.15.0 || >=26.0.0`。Codex 本机 24.16.0、CI `node-version: '24'` 均满足；Node 20 已停止维护。
- `paths` 通配在 Node 侧 tsconfig 中对所有裸导入生效（含 node_modules 内部）。已用「先 `@types` 后包本身」避免把 `chai` 解析到无类型的 JS；若日后出现某包自带类型却被过时 `@types` 覆盖，改为逐包列出。
- CI 仍只运行 `scripts/verify.sh`，前端 type-check/test/build 未进门禁（K11 范围）。
- 嵌套运行每次约 1 秒，`b02.test.ts` 整体约 4 秒。

## 未验证

- Windows：嵌套运行已改为优先用 npm 注入的 `npm_execpath` 由当前 node 执行（不依赖 `npm.cmd` 查找），不经 npm 启动时在 win32 上退回 `shell: true`。本轮只在 macOS 验证（经 `npm run test` 与直接 `npx vitest` 两条路径均 5 passed），Windows 上请 Codex 实跑一次。

## 下一步

- 请 Codex 审查本范围；修复另开一轮。
- 之后可并行：B03（路由壳与角色入口，依赖 A05 已签收）、B04（Pinia 课程上下文，需新增 `pinia` 依赖）。B15 等 B14（契约 B09～B13）。

## 回滚

- 撤销本分支提交即可；无数据库迁移或外部状态。依赖回退后执行 `npm ci --prefix src/frontend` 同步 `node_modules`。
