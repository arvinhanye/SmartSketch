---
review_status: ready_for_review
task_id: H13
branch: claude/h13-login-session
base: 85adfa7（第七批认领提交，基于 main@8985a16）
---

# H13 交接：前端登录页与会话存储

## 交付物

| 文件 | 内容 |
| --- | --- |
| `src/frontend/src/api/auth.ts` | 新增。`createAuthApi(client).login()` 走 `POST /api/v1/auth/login`；`AUTH_API_KEY` 注入键；`createSessionHttpClient(session, onExpired, options)`：每次请求读当前令牌放进 `Authorization: Bearer`，受保护接口 401 时先 `session.signOut()` 再调用 `onExpired`（登录接口是 `security: []`，401 属凭据错误，B15 不触发回调） |
| `src/frontend/src/stores/session.ts` | 新增。`useSessionStore`：`accessToken`、`user`、`role`、`signIn(LoginResponse)`、`signOut()`。只写 `sessionStorage`（键 `smartsketch.session`，值 `{access_token, user:{id,username,role}}`）；读取时严格校验，内容无效即清除并视为未登录；存储抛错时会话只留在内存。登录与退出都会 `useCourseStore().selectCourse(null)` |
| `src/frontend/src/views/LoginView.vue` | 新增。用户名与密码表单（`autocomplete` 为 `username` / `current-password`）；空值不发请求；提交中禁用、重复提交只发一次；401、429（有或无 `Retry-After`）、422、网络/超时、其他错误各有固定文案，不回显服务端 message；失败清空口令、保留用户名；成功后按 `user.role` 跳首页 |
| `src/frontend/src/router/index.ts` | `AppRouterOptions.loginComponent`（未登录时根路由显示的页面，省略时仍为空页，B03 测试不受影响）；导出 `homeRouteFor(role)` |
| `src/frontend/src/main.ts` | 真实入口接线：`getAccountRole` 取会话 `role`；401 时清会话并 `replace` 到根路由（带未登录提示）；注入 `AUTH_API_KEY` |
| `tests/frontend/h13.test.ts` | 28 个用例 |

## 关键决定

- **登录页放在根路由**：守卫已有的未登录落点就是 `/?notice=unauthenticated`，外壳会显示未登录提示。登录页挂在这里，401 回到的也是这里，不必改动 B03 的守卫与测试。登录页不用 `h2`（B03 用 `h2` 判断渲染了哪个角色首页）。
- **B03-R01′ 关闭**：真实入口 `main.ts` 不再是 `getAccountRole: () => null`，教师和学生首页在登录后可达。
- **B04-R01 关闭**：换账号、退出、会话过期都会清空课程上下文，并使旧作用域失效。未改 `stores/course.ts`，而是复用现有的 `selectCourse(null)`：它会中止旧的 signal 并递增代次。
- 未加令牌过期时间（`expires_in`）的前端判断：过期令牌会得到 401，走同一条清会话路径，结果相同。

## 实际命令与结果

| 步骤 | 命令 | 结果 |
| --- | --- | --- |
| 红灯 | `npm --prefix src/frontend run test -- --run ../../tests/frontend/h13.test.ts`（实现前） | 测试文件加载失败，`no tests`（模块不存在） |
| 绿灯 | 同上 | 28 passed |
| 前端全量 | `npm --prefix src/frontend run test -- --run` | `5 files, 81 passed`（B02/B03/B04/B15 均通过） |
| 类型检查 | `npm --prefix src/frontend run type-check` | 通过（`tsconfig.node.json` 覆盖 `tests/frontend`） |
| 构建 | `npm --prefix src/frontend run build` | 通过 |
| 门禁 | `./scripts/verify.sh` | `Scaffold verification passed.` |

未做：没有连后端在浏览器里手动登录（后端登录端点已由 C13 实现，本任务只用假接口验证）。

## 接口 / 数据变化

- 新的前端存储键 `sessionStorage['smartsketch.session']`；无后端、契约、迁移变化。
- `createAppRouter` 多了可选参数 `loginComponent`，旧调用方不受影响。

## 风险 / 待决 / 下一步

- 没有「退出登录」按钮：`signOut()` 已就绪，但外壳 `App.vue` 不在本任务文件锁内。建议由 H01（课程首页）或后续外壳任务加上。
- 其他页面的 API 调用要复用 `main.ts` 中的同一个 `http` 客户端，否则 401 不会回登录页。目前只注入了 `AUTH_API_KEY`；H01 接入课程接口时，建议在 `api/` 增加一个通用客户端注入键。
- 401 后回到登录页的提示沿用「未登录」文案，没有单独区分「会话已过期」（需要改 `App.vue`）。

## 回滚

`git revert` 本任务提交即可：删除三个新文件，恢复 `router/index.ts` 与 `main.ts`。无数据迁移。浏览器里残留的 `smartsketch.session` 键无害，关闭标签页即清除。
