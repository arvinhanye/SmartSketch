# Claude 交接：B04 Pinia 课程上下文

- `task_id`: B04
- `review_status`: ready_for_review
- `worktree`: `/Users/arvinhan/Desktop/SmartSketch/.claude/worktrees/agent-af5fba1b70b95c810`（分支 `claude/b04-course-store`）
- `base_commit`: `9dddcb4`（B03/B04 准备：已装 `pinia@4.0.3`，`main.ts` 已 `app.use(createPinia())`）
- `head_commit`: 见本分支提交
- 父任务：M0-02 仍为 IN PROGRESS（B03 并行中，B15 待做）。`docs/tasks.md` 的 B04 行由协调方在集成时更新。

## 交付物

| 文件 | 内容 |
| --- | --- |
| `src/frontend/src/stores/course.ts`（新增） | Pinia setup store `useCourseStore`：当前课程、图谱槽位、问答历史槽位、课程请求作用域；不发请求 |
| `tests/frontend/b04.test.ts`（新增） | 12 个用例，见「实际验证」 |
| `docs/handoffs/claude-b04.md`（新增） | 本文件 |

## 公开 API

| 成员 | 说明 |
| --- | --- |
| `courseId: string \| null` | 当前课程；`null` 表示不在任何课程内 |
| `graph: GraphExchange \| null` | 当前课程图谱（`shallowRef`，整体替换） |
| `chatHistory: ChatTurn[]` | 当前课程的多轮问答历史 |
| `selectCourse(id \| null)` | 换课或离开：中止旧作用域的 `AbortController`、代次 +1、清空 `graph` 与 `chatHistory`。与当前相同则什么都不做 |
| `beginRequest(): CourseRequestScope` | 返回绑定当前作用域的 `{ courseId, signal, isCurrent() }`（冻结对象）；未选课程时抛错 |
| `commit(scope, apply)` | 作用域仍有效时执行 `apply` 并返回 `true`，否则丢弃并返回 `false` |
| `setGraph(scope, graph)` | 经 `commit` 写入；`graph.course_id` 与 `scope.courseId` 不符时拒收 |
| `appendChatTurns(scope, ...turns)` | 经 `commit` 追加问答回合 |

导出类型 `CourseRequestScope`。

## 决定与理由

- **契约类型**：`graph` 用 `components['schemas']['GraphExchange']`——它是 `getGraph`（`GET /api/v1/courses/{cid}/graph`）200 响应的类型，也是 G6 适配层输入（M0-04c）。问答槽位用 `ChatTurn[]`：`specs/grounded-qa.md` Q8 规定服务端不保存会话、历史由客户端维护并随 `ChatRequest.history` 提交，所以课程作用域内要保留的问答状态正是这份历史。均为 `import type`，无手写 DTO。
- **没有放 `ChatResponse`（最近一次回答/引用）**：它的展示形态（按回合挂引用、流式临时态）属于 J08/J09 的设计；需要时在本 store 加槽位并在 `selectCourse` 中一并清空，或放在 J08 自己的 composable 里、以作用域提交。
- **失效判据是作用域代次，不是 courseId**：`selectCourse` 每次真正切换都让代次 +1，A→B→A 时第一次 A 的作用域与第二次 A 代次不同，晚到响应被丢弃。
- **只认 store 签发的作用域**：`commit` 查内部 `WeakMap` 中登记的代次，不调用 `scope.isCurrent()`；调用方自造 `{ isCurrent: () => true }` 无法写入。
- **一个课程作用域一个 `AbortController`**：同一作用域内的并发请求共享一个 `signal`，切课时全部中止。单个请求的取消（如用户停止问答流）由调用方自建控制器，再用 `AbortSignal.any([scope.signal, own.signal])` 合并。
- **`setGraph` 额外校验 `course_id`**：`GraphExchange` 已按课程隔离，调用方不得跨课程合并（契约描述）；即便作用域有效，也拒收别的课程的图谱。
- **不做只读包装**：槽位保持 setup store 的普通 state 形态（devtools 可见、测试可直接断言），未验证 `readonly()` 包装在 Pinia 中的行为；「组件不直接写槽位」写在 store 注释中，由审查和 composable 约定保证。

## 实际验证（Node 26.4.0 / npm 11.17.0，macOS）

| 命令/方法 | 结果 |
| --- | --- |
| `npm ci --prefix src/frontend --no-audit --no-fund` | exit 0（`fsevents` 安装脚本未批准的提示与 B02 相同，不影响） |
| 实现前运行 `npm --prefix src/frontend run test -- --run ../../tests/frontend/b04.test.ts`（RED） | exit 1，`Failed to resolve import "../../src/frontend/src/stores/course"` |
| 计划验收命令 `npm --prefix src/frontend run type-check && npm --prefix src/frontend run test -- --run ../../tests/frontend/b04.test.ts` | exit 0，1 file / 12 passed |
| `npm --prefix src/frontend run test -- --run`（全量） | exit 0，2 files / 17 passed（B02 5 + B04 12） |
| `npm --prefix src/frontend run build` | exit 0 |
| `./scripts/verify.sh` | exit 0 |
| `git diff --check`（新文件 `git add -N` 后） | exit 0 |
| `grep -nE "fetch\|XMLHttpRequest\|axios\|EventSource" src/frontend/src/stores/course.ts` | exit 1（无匹配）；store 仅导入 `pinia`、`vue` 与契约类型（`import type`） |

用例：初始无课程且不能开作用域；当前作用域内写入图谱与问答；切课清空；切课中止旧 signal；A 的晚到响应在切到 B 后被丢弃、B 数据不变；A→B→A 第一次 A 的晚到响应被丢弃；重选同课幂等（不清空、不中止）；选 null 清空并中止、之后不能开作用域；同作用域多请求共享 signal；`course_id` 不符的图谱被拒收；`commit` 仅在有效时执行回调；自造作用域不能写入。晚到响应用可手动 resolve 的 deferred promise 模拟。

反向篡改（逐项改坏后运行 B04 测试，脚本结束时恢复原文件，恢复后重新全绿）：

| 篡改 | 结果 |
| --- | --- |
| 代次校验改为比较 courseId | exit 1；「A→B→A 时第一次 A 的晚到响应不写入第二次 A」失败 |
| 切课不清空槽位 | exit 1；「切到另一门课时清空」「选择 null…」失败 |
| 切课不 `abort()` | exit 1；4 个 signal 相关用例失败 |
| 去掉同课幂等判断 | exit 1；「重复选择同一课程是幂等的」失败 |
| 去掉 `setGraph` 的 `course_id` 校验 | exit 1；「课程 ID 与作用域不符的图谱被拒收」失败 |
| `commit` 改为信任 `scope.isCurrent()` | exit 1；「非 store 签发的作用域对象不能写入」失败 |

## 接口、配置与风险

- 无 REST/SSE、契约、数据模型、依赖或环境变量变化；未改 `package.json`、锁文件、`main.ts`、路由与视图。
- 作用域失效只保证**不写入**和**发出中止信号**；是否真正取消网络请求取决于 B15 客户端把 `signal` 传给 `fetch`。B15 未把 `signal` 透传时，晚到响应仍会被丢弃，但请求会跑完。
- 调用方若绕过 `setGraph`/`appendChatTurns` 直接赋值 `store.graph`，作用域保护失效。目前靠约定与审查，H01/J08 审查时注意。
- 作用域提交是同步检查；`apply` 回调里若再 `await`，回调后半段不受保护。回调应只做同步赋值。

## 未验证

- 与 B03 路由壳的联动（路由参数 `cid` 变化时调用 `selectCourse`）未验证，属于集成或 H01 范围。
- 浏览器实际中止网络请求未验证（B15 尚不存在）。
- Windows 未验证；本用例不启动子进程，预期无平台差异。

## 下一步（给消费方）

- **B03/H01**：在课程路由的参数变化处（如 `watch(() => route.params.cid, ...)` 或路由守卫）调用 `selectCourse(cid ?? null)`；离开课程页调用 `selectCourse(null)`。
- **B15**：客户端接受 `AbortSignal` 并透传给 `fetch`/SSE；被中止时抛出的 `AbortError` 由 composable 吞掉，不当作错误态展示。
- **图谱 composable（如 `useCourseGraph`）**：

  ```ts
  const store = useCourseStore()
  const scope = store.beginRequest()
  try {
    const graph = await api.getGraph(scope.courseId, { signal: scope.signal })
    store.setGraph(scope, graph)
  } catch (e) {
    if (!scope.isCurrent()) return // 已切课，丢弃
    throw e
  }
  ```

- **J08/J09 问答**：请求时带 `history: store.chatHistory`；收到 `done` 后按 QA-20，把提问与 `final.answer` 用 `appendChatTurns(scope, userTurn, assistantTurn)` 写入；`error`/`aborted` 的回合不写入。loading/error 等 UI 态放在 composable 内，并以 `scope.isCurrent()` 守卫。
- 请 Codex 审查本范围；修复另开一轮。

## 回滚

- 撤销本分支提交即可：删除 `stores/course.ts` 与 `b04.test.ts` 不影响其他模块（当前无消费方）。无数据库迁移或外部状态。

## 同步更新后的 B02 分支（2026-09-24，PR #28）

- 基线：`claude/b03-b04` `4c4c417` 合并 `claude/frontend-dev-04eee7` `f4b3054`（B02 分支已并入 main `9d2437e`，含 PR #30 的 B08/B09）。
- 冲突只有 `docs/tasks.md` 一处：两边都在 B02 节之后追加新节。按任务编号保留两边，顺序为 B02、B03/B04、B08/B09，内容不改。
- 验证（Node 26.4.0，macOS）：`./scripts/verify.sh` exit 0；`npm ci --prefix src/frontend` 后 `type-check` exit 0、`test -- --run` 3 个文件 30 passed、`build` 成功；`git diff --cached --check` exit 0。
- PR #27 合入后，把 PR #28 的目标分支改为 `main`。
