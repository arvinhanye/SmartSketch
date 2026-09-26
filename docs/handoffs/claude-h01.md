---
review_status: ready_for_review
task_id: H01
branch: claude/h01-courses-view
base: bdcf165（第八批认领提交，基于 main@d624208）
---

# H01 交接：课程首页和创建表单

## 交付物

| 文件 | 内容 |
| --- | --- |
| `src/frontend/src/api/client.ts` | 新增。`HTTP_CLIENT_KEY`：通用 HTTP 客户端注入键（按 H13 交接建议），`main.ts` 提供接好会话的同一个客户端 |
| `src/frontend/src/api/courses.ts` | 新增。`createCoursesApi(client)`：`list` → `GET /api/v1/courses`，`create` → `POST /api/v1/courses`，`get` → `GET /api/v1/courses/{cid}`；`COURSES_API_KEY` 注入键。只封装 HTTP，错误原样抛出 |
| `src/frontend/src/composables/useCourses.ts` | 新增。`toCourseCard`（`Course` → 视图模型，组件不接触原始响应）；`useCourses`：列表四态（`loading`/`ready`（含空）/`error`/`forbidden`）与重试；创建表单（同步标志防重入 + `creating` 禁用、前端长度校验、按状态码的固定文案）；按路由 `cid` 切换当前课程 |
| `src/frontend/src/views/CoursesView.vue` | 新增。课程卡片列表（`RouterLink` 到 `/courses/:cid`，当前课程 `aria-current="page"`）、当前课程面板、仅教师账号可见的创建表单；控件都包在 `label` 里，错误 `role="alert"`，加载/成功 `role="status"`，区域 `aria-busy` |
| `src/frontend/src/router/index.ts` | `AppRouterOptions.coursesComponent`（可选）：注入后教师/学生首页渲染课程页，并注册 `/courses/:cid`（名 `course`，`meta.anyAccountRole`）；导出 `COURSE_ROUTE`、`NOTICE_COURSE_FORBIDDEN`；守卫对 `anyAccountRole` 路由只要求已登录 |
| `src/frontend/src/main.ts` | 注入 `coursesComponent: CoursesView`；提供 `HTTP_CLIENT_KEY`、`COURSES_API_KEY`（与登录共用同一会话客户端） |
| `tests/frontend/h01.test.ts` | 31 个用例 |

## 关键决定

- **路由接入用注入而不是改路由结构**：沿用 H13 `loginComponent` 的做法。未注入 `coursesComponent` 时路由与 B03 完全相同（B03/H13 测试未改任何断言）；注入后 `/teacher`、`/student` 的路径、名称、`meta.accountRole` 与 `homeRouteFor` 都不变，只是组件换成课程页，所以登录后直接落在课程列表。
- **课程页对任一账号类型开放**：`/courses/:cid` 用新的 `meta.anyAccountRole`，因为课程内角色由 `Course.my_role` 决定，与账号类型无关（`specs/identity-access.md` §4.4）。课程面板按 `my_role` 标出教师视图/学生视图；具体图谱视图留给后续任务。
- **切课**：`cid` 变化 → `useCourseStore().selectCourse(cid)` → `beginRequest()` 取作用域 → `api.get(cid, { signal: scope.signal })` → `commit(scope, …)` 写入。旧课程的请求随作用域中止；晚到响应（含 A→B→A 的第一次 A）被代次校验丢弃。回到首页时 `selectCourse(null)`。
- **`COURSE_FORBIDDEN`**：清空当前课程，`router.replace` 到本账号首页并带 `notice=course-forbidden`，课程页显示 `role="alert"` 提示（`errors.v1.md`「提示无权限，返回课程列表」）。提示由课程页渲染，没有改 `App.vue`。
- **列表禁止访问态**：契约里 `GET /courses` 不会返回 403，但仍按 403 显示无权限状态，防止将来网关/策略变化时误报为一般错误。
- **创建防重入**：同步 `inFlight` 标志加 `fieldset`/按钮禁用；两次 `submit` 事件即使在重新渲染前连续到达，也只发一次请求。
- **不回显服务端 message**：所有错误只按状态码/错误类型给固定文案（同 H13）。
- 创建成功后新课程插入列表首位，不自动跳转。

## 实际命令与结果

| 步骤 | 命令 | 结果 |
| --- | --- | --- |
| 依赖 | `npm ci --prefix src/frontend` | exit 0 |
| 红灯 | `npm --prefix src/frontend run test -- --run ../../tests/frontend/h01.test.ts`（实现前） | 测试文件加载失败，`no tests`（模块不存在） |
| 绿灯 | 同上 | 31 passed |
| 类型检查 | `npm --prefix src/frontend run type-check` | exit 0 |
| 前端全量 | `npm --prefix src/frontend run test -- --run` | `6 files, 112 passed` exit 0 |
| 构建 | `npm --prefix src/frontend run build` | exit 0 |
| 门禁 | `./scripts/verify.sh` | exit 0，`Scaffold verification passed.` |
| 空白 | `git diff --check` | exit 0 |

说明：机器负载很高（load average 约 120）时，前端全量中 B02「断言失败时命令非 0」用例曾两次 5 s 超时（它会同步起一个子 vitest 进程，实测约 10 s）；加 `--testTimeout=60000` 单跑 5 passed。负载回落后按默认配置全量重跑，112 passed。该用例只跑自己的探针目录，与本任务改动无关。

未做：没有连真实后端在浏览器里手动操作（只用假接口与假 fetch 验证）。

## 接口 / 数据变更

无契约、DTO、后端或数据变更。前端新增路由 `/courses/:cid`（名 `course`）与 `RouteMeta.anyAccountRole`、提示码 `course-forbidden`。

## 风险 / 待决 / 下一步

- `TeacherHome.vue`、`StudentHome.vue` 在真实入口已不再使用（B03 测试仍用它们作未注入时的占位）；是否删除或改为课程页的一部分，留给后续整理任务决定。
- 外壳仍无「退出登录」按钮（`App.vue` 不在本任务锁内），H13 的建议仍待处理。
- 课程面板只显示课程基本信息与身份；教师编辑/审核视图与学生图谱视图由后续 H 系列任务接入 `/courses/:cid`（或其子路由）。
- 学生访问从未发布课程的 404 `GRAPH_NOT_PUBLISHED` 显示「尚未发布」；按 §4.4 学生列表不会出现这类课程，只有手输链接才会触发。

## 回滚

`git revert` 本任务提交即可：删除四个新源码文件与测试，恢复 `router/index.ts` 与 `main.ts`。无数据迁移，无依赖变化。
