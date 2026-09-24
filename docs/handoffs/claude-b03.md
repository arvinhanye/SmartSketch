# Claude 交接：B03 路由壳与角色入口

- `task_id`: B03
- `review_status`: ready_for_review
- `worktree`: `/Users/arvinhan/Desktop/SmartSketch/.claude/worktrees/agent-acb88d2bd608b82fd`（分支 `claude/b03-router-shell`）
- `base_commit`: `9dddcb4`（B03/B04 准备：已装 `vue-router@5.3.1`、`pinia@4.0.3`，`main.ts` 已接 Pinia）
- `head_commit`: 见本分支提交
- 并行：B04（Pinia 课程上下文）由另一代理实现，文件互不重叠；`docs/tasks.md`、`docs/architecture.md` 由协调方在集成时更新

## 交付物

| 文件 | 内容 |
| --- | --- |
| `src/frontend/src/router/index.ts` | 工厂 `createAppRouter({ history, getAccountRole })`；`Role` 从生成契约 type-only 导入；`RouteMeta.accountRole` 类型扩展；路由 `/`、`/teacher`、`/student`、未知路径重定向到 `/`；全局前置守卫 |
| `src/frontend/src/views/TeacherHome.vue`、`StudentHome.vue` | 只有 `h2` 标题与占位说明，无业务请求 |
| `src/frontend/src/App.vue` | 外壳：保留 `<h1>智绘学途</h1>`，按 `query.notice` 显示 `role="alert"` 中文提示，渲染 `<RouterView />` |
| `src/frontend/src/main.ts` | 接入路由（`createWebHistory()`），账号类型 getter 暂返回 `null`，注释说明登录与会话存储待补；Pinia 保留 |
| `tests/frontend/b03.test.ts` | 13 个用例，见下 |

## 决定与理由

- **账号类型由调用方注入**：原子清单没有登录页与会话存储任务，B03 不自创 `sessionStorage` 键名或格式。工厂接收 `getAccountRole: () => Role | null`，每次导航时读取，将来接入会话后只改 `main.ts` 一处。
- **守卫规则**（前端守卫只是界面引导，授权以后端为准，`specs/identity-access.md` §2.4）：
  - `getAccountRole()` 为 `null`：一律回到 `/?notice=unauthenticated`；`/` 页面本身为空，外壳显示「未登录」提示，不渲染任何角色首页，也不跳转到不存在的登录页。
  - `/` 或无 `meta.accountRole` 的页面：重定向到本人首页。
  - `meta.accountRole` 与账号类型不符：回到本人首页并带 `?notice=wrong-role`，外壳显示「当前账号类型为学生，无法进入教师首页，已返回学生首页。」（教师反之）。
  - 未知路径先重定向到 `/`，再按上面规则处理。
- **提示用 query 传递**：状态简单可测，刷新后仍在；离开该页（换 query）提示即消失。外壳只在提示码与当前页面相符时显示（`unauthenticated` 只在 `/`，`wrong-role` 只在带 `accountRole` 的页面），手工拼的 query 最多多显示一句提示，不影响任何授权。
- **外壳在未安装路由时也能挂载**：`App.vue` 用 `inject(routeLocationKey, null)` 取当前路由，没有路由时只渲染标题、不渲染 `RouterView`。原因：B02 有两个用例（首个用例和「挂载到 document.body」）直接 `mount(App)` 且不装路由，改用 `useRoute()` 后两者都会抛错；任务只允许改 B02 首个用例，所以改为让外壳容忍无路由，**B02 测试文件未改动**。生产入口始终装路由，这个分支只在单独挂载外壳时走到。若审查方更希望外壳直接用 `useRoute()`，需要同时给 B02 的两个挂载用例加 `global.plugins`/`stubs`，请在审查中决定。
- 本任务不涉及 `Course.my_role` 与课程视图（H01/H11，契约字段由 B09 添加）。

## 测试用例（`tests/frontend/b03.test.ts`）

用 `createMemoryHistory` 建路由、导航后装进 App 挂载。角色首页以 `h2` 判断（提示文字本身会提到页面名，不能按全文判断）。

1. 外壳保留 `h1` 标题
2. 教师访问 `/` → `/teacher`，无提示
3. 学生访问 `/` → `/student`，无提示
4. 教师直接访问 `/teacher`，无提示
5. 学生直接访问 `/teacher` → `/student`，只渲染学生首页，`role="alert"` 提示含「教师首页」「学生」
6. 教师直接访问 `/student` → `/teacher`，同理
7–10. 未登录访问 `/`、`/teacher`、`/student`、`/no-such-page` → 停在 `/`，提示含「未登录」，没有任何 `h2`
11. 未知路径（学生）→ `/student`
12. 路由 meta 标注 `accountRole`
13. 离开被拒页面后提示消失

## 实际验证（Node 26.4.0 / npm 11.17.0）

| 命令/方法 | 结果 |
| --- | --- |
| `npm ci --prefix src/frontend --no-audit --no-fund` | exit 0（npm 提示 `fsevents` 安装脚本未批准，可选依赖，不影响） |
| 实现前运行 `npm --prefix src/frontend run test -- --run ../../tests/frontend/b03.test.ts`（RED） | exit 1，无法解析 `src/frontend/src/router/index.ts`（功能缺失） |
| 计划验收命令 `npm --prefix src/frontend run type-check && npm --prefix src/frontend run test -- --run ../../tests/frontend/b03.test.ts` | exit 0，1 file / 13 passed |
| `npm --prefix src/frontend run test -- --run`（全量，含 B02） | exit 0，2 files / 18 passed（B02 5 + B03 13），无 Vue 警告 |
| `npm --prefix src/frontend run build` | exit 0 |
| `./scripts/verify.sh` | exit 0 |
| `git diff --check` | exit 0 |

反向篡改（改坏后运行 B03，随即恢复，恢复后重新全绿）：

| 篡改 | 结果 |
| --- | --- |
| 去掉整个 `beforeEach` 守卫 | 10 failed / 3 passed（除标题、本人首页、meta 外全部失败） |
| 只删「账号类型不符」分支 | 3 failed：学生访问 `/teacher`、教师访问 `/student`、提示消失 |
| 删除外壳中的 `role="alert"` 元素 | 7 failed：两条不符用例、四条未登录用例、提示消失 |

## 接口、配置与风险

- 无 REST/SSE、契约、数据模型、依赖或环境变量变化。
- **缺口：前端登录页与会话存储不在原子清单中**（G-1 只列 C13～C16 后端与 H12 成员页）。在补上之前，`main.ts` 注入的 getter 恒为 `null`，实际运行的应用只会显示「未登录」提示。需要协调方在任务板登记并决定由哪个任务实现登录页、`sessionStorage` 读写（§2.4）与 401 处理。
- 前端守卫不是鉴权：直接调用后端 API 不受其约束，授权由后端按 §4 判定。
- 路由组件为同步导入；页面变多后可改为按需加载。
- `docs/architecture.md` 第 38 行「B03 再引入教师/学生路由」、`src/frontend/README.md` 中「角色路由由后续任务加入」需在集成时由协调方更新（本任务文件锁不含这些文件）。

## 未验证

- 未在浏览器里手动打开开发服务器查看；行为由 jsdom 用例与生产构建覆盖。
- Windows 未实跑。

## 下一步

- 请 Codex 审查本范围；修复另开一轮。
- 集成时协调方更新 `docs/tasks.md`（B03 状态与证据）、`docs/architecture.md`、`src/frontend/README.md`，并登记登录页/会话存储缺口。
- H01/H11 在 B09 为 `Course` 添加 `my_role` 后，按课程内角色选课程视图。

## 回滚

- 撤销本分支提交即可；无依赖、迁移或外部状态变化。

## 同步更新后的 B02 分支（2026-09-24，PR #28）

- 基线：`claude/b03-b04` `4c4c417` 合并 `claude/frontend-dev-04eee7` `f4b3054`（B02 分支已并入 main `9d2437e`，含 PR #30 的 B08/B09）。
- 冲突只有 `docs/tasks.md` 一处：两边都在 B02 节之后追加新节。按任务编号保留两边，顺序为 B02、B03/B04、B08/B09，内容不改。
- 验证（Node 26.4.0，macOS）：`./scripts/verify.sh` exit 0；`npm ci --prefix src/frontend` 后 `type-check` exit 0、`test -- --run` 3 个文件 30 passed、`build` 成功；`git diff --cached --check` exit 0。
- PR #27 合入后，把 PR #28 的目标分支改为 `main`。
