---
review_status: ready_for_review
task_id: H12
branch: worktree-agent-a2e507ac1651f2076
base: 5072a48（main，Merge PR #250）
---

# H12 交接：课程成员管理页面

## 交付物

| 文件 | 内容 |
| --- | --- |
| `src/frontend/src/api/members.ts` | 新增。`createMembersApi(client)`：`list` → `GET /api/v1/courses/{cid}/members`，`add` → `POST …/members`（体为 `MemberAdd`），`remove` → `DELETE …/members/{uid}`（204 → `undefined`）；`MEMBERS_API_KEY` 注入键。类型取自 `src/contracts/v1/generated` 的 `CourseMember`、`MemberAdd`，只封装 HTTP，错误原样抛出 |
| `src/frontend/src/composables/useMembers.ts` | 新增。`toMemberRow`（`CourseMember` → 视图模型，`removable` 只对学生成员为真）；`useMembers`：列表四态（`loading`/`ready`（含「无学生」空态）/`error`/`forbidden`）与重试；添加（同步标志防重入 + `adding` 禁用、空用户名不发请求、按 `user_id` 去重）；移除（按 `uid` 的同步防重入 + 行内 `removing` 禁用）；请求都在 `useCourseStore().beginRequest()` 作用域内发出、经 `commit` 提交 |
| `src/frontend/src/views/MembersView.vue` | 新增。成员表（`caption`、`th scope="col"`、用户名为行头、`<time datetime>`）、学生行「移除」按钮（`aria-label="移除学生 <用户名>"`、进行中 `disabled` + `aria-busy`）、添加表单（控件包在 `label` 内，`fieldset` 提交中禁用）、返回课程链接；错误 `role="alert"`，加载/成功 `role="status"`，列表区 `aria-busy` |
| `src/frontend/src/router/index.ts` | `AppRouterOptions.membersComponent`（可选）：注入后注册 `/courses/:cid/members`（名 `course-members`，导出 `COURSE_MEMBERS_ROUTE`），`meta.accountRole: 'teacher'`；未注入时路由与原来完全相同 |
| `src/frontend/src/views/CoursesView.vue` | 当前课程面板加「管理成员」链接：仅当成员路由已注册且 `Course.my_role === 'teacher'` 时显示 |
| `src/frontend/src/main.ts` | 注入 `membersComponent: MembersView`，提供 `MEMBERS_API_KEY`（与其他 API 共用同一会话客户端，401 统一回登录页） |
| `tests/frontend/h12.test.ts` | 33 个用例 |

## 验收对照

| 验收 | 实现与用例 |
| --- | --- |
| 教师可添加和移除 | 添加成功新行出现、输入清空、`role=status` 提示；移除成功调用 `DELETE`（`cid`、`uid` 正确）、行消失并提示 |
| 学生无入口 | 学生账号课程页无链接；教师账号但在本课是学生成员（`my_role=student`）也无链接；学生账号直接打开 `/courses/c1/members` 被守卫送回 `student-home`（`notice=wrong-role`），不发成员请求 |
| 权限失败明确提示 | 列表 403 `ROLE_FORBIDDEN` → 「无权管理成员：只有本课程的教师成员…」，隐藏添加表单与重试；添加 403 同文案；移除 403 → 「无权移除该成员…」且行保留；任一操作 403 `COURSE_FORBIDDEN` → 清当前课程、回本账号课程列表并带 `notice=course-forbidden`（课程页已有的 `role=alert` 提示）。均不回显服务端 message |
| 重复提交不重复成员 | 添加：连续三次 `submit` 只发一次请求，提交中按钮/`fieldset` 禁用、表单 `aria-busy`；接口对已是成员幂等返回原行（200），按 `user_id` 替换而不新增，提示「已是课程成员（…），未重复添加」，已是教师成员时身份不被改为学生。移除：连续点击（含禁用渲染之前的两次）只发一次 |
| 空、加载、错误态与可访问性 | 见上；网络错误可重试；404 用户名不存在、422、网络失败各有固定文案；移除 404 视为已不是成员并从列表去掉；切课时旧课程晚到的列表被丢弃、旧请求被取消 |

## 关键决定

- **200/201 不区分**：B15 客户端只返回响应体，不暴露 2xx 状态码。契约规定两者都返回 `CourseMember`，所以「是否重复」按返回行的 `user_id` 是否已在当前列表判断。若列表已过期（别处刚加过），会显示「已添加」而不是「已是成员」，但不会产生重复行。未改 B15 或契约。
- **守卫只看账号类型**：成员路由用 `meta.accountRole: 'teacher'`，学生账号被送回学生首页（外壳沿用 B03 的 wrong-role 文案）。教师账号在本课是否为教师成员由后端 403 `ROLE_FORBIDDEN` 判定，前端对此给出明确提示（`specs/identity-access.md` §2.4：前端守卫只是界面引导）。
- **入口按 `my_role`**：课程页链接只看 `Course.my_role`，所以教师账号作为学生成员旁听的课程也没有入口。
- **不加确认弹窗**：移除是可逆操作（重新添加即恢复，§3.3 进度保留），为避免 `window.confirm` 的可访问性与测试问题，直接执行并以 `role=status` 反馈。
- **课程作用域**：成员页进入时 `selectCourse(cid)`；离开到课程页时课程页自行切换，未改 `stores/course.ts`。

## 验证（实际命令与结果，Node v22，Linux）

在 worktree 根目录执行；`S` 为本会话 scratchpad。

| 步骤 | 命令 | 结果 |
| --- | --- | --- |
| 依赖 | `npm --prefix src/frontend ci --no-audit --no-fund` | exit 0 |
| 红灯 | `npm --prefix src/frontend run test -- --run ../../tests/frontend/h12.test.ts`（实现前） | 测试文件加载失败，`Tests no tests`（模块不存在） |
| 绿灯 | 同上 | 33 passed |
| 类型检查 | `npm --prefix src/frontend run type-check` | exit 0 |
| 前端全量 | `npm --prefix src/frontend run test -- --run` | exit 0，`8 files, 183 passed` |
| 构建 | `npm --prefix src/frontend run build` | exit 0 |
| 门禁 | `env PATH="$S/oat/node_modules/.bin:$S/venv/bin:/opt/node22/bin:/usr/local/bin:/usr/bin:/bin" ./scripts/verify.sh` | exit 0，`PASS contracts gate`、`Scaffold verification passed.` |
| 空白 | `git diff --check`（新文件已暂存） | exit 0 |

`verify.sh` 说明：直接运行（系统 `python3` 无 pytest、无 `openapi-typescript`）会在契约门禁失败，与本任务无关；上表的 `$S/venv` 为已有的后端测试 venv，`$S/oat` 为临时装在仓库外的 `openapi-typescript@7.4.4`（版本同 `src/contracts/toolchain.txt`），生成物无漂移。

反向篡改（临时改源码跑 H12 测试后恢复原文件）：

| 篡改 | 结果 |
| --- | --- |
| 添加结果不按 `user_id` 去重 | 2 failed |
| 去掉添加的同步防重入 | 1 failed |
| 去掉移除的同步防重入 | 1 failed |
| 成员路由改为任一账号可进 | 1 failed |
| 列表 `ROLE_FORBIDDEN` 不进入禁止态 | 1 failed |

未做：没有连真实后端在浏览器里手动操作（只用假接口与假 fetch 验证）。

## 接口 / 数据变更

无契约、DTO、后端或数据变更。前端新增路由 `/courses/:cid/members`（名 `course-members`）、`createAppRouter` 可选参数 `membersComponent`、注入键 `MEMBERS_API_KEY`。

## 风险

- `router/index.ts` 与并行的 H02 都会各加一条路由：本任务只在课程路由之后、兜底路由之前追加一个 `if (membersComponent)` 块，合并冲突时保留两者即可。
- 学生账号被守卫送回时，外壳显示的是 B03 的「无法进入教师首页」文案，未单独区分「无法管理成员」（需改 `App.vue`，不在本任务范围）。
- 成员较多时没有分页或搜索；契约 `listMembers` 也无分页参数，MVP 规模可接受。

## 下一步

- 若需要区分 200/201（例如精确提示「已是成员」而不依赖本地列表），需要 B15 客户端暴露响应状态码，或契约给出显式字段；目前不需要。
- 教师成员（协作教师）的增删仍只能用命令行（§3.3），页面只做说明。

## 回滚

`git revert` 本任务提交即可：删除三个新源码文件与测试，恢复 `router/index.ts`、`CoursesView.vue` 与 `main.ts`。无数据迁移，无依赖变化。
