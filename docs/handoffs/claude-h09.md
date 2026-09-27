# Claude 交接：H09 审核队列与节点合并 UI

- `task_id`: H09（`docs/atomic-tasks.json`「实现审核队列和节点合并 UI」），issue #121
- `review_status`: 独立审查完成（2026-09-27），结论 APPROVE_WITH_NOTES；仅测试增补，无产品代码改动
- 分支：`claude/project-thread-eo5fzo`；`base_commit`: `ac21e5d`（origin/main）
- 依赖：F10（合并，ADR-047）、F11（审核队列 API，ADR-060）、H07（节点编辑的错误处理约定）
- 决策：ADR-070
- 断点：issue 挂着旧的 `status:in-progress`，远端无分支/PR、三个允许文件都不存在；本轮从零实现。

## 交付物

| 文件 | 内容 |
| --- | --- |
| `src/frontend/src/views/ReviewView.vue`（文件锁） | 路由页 `/courses/:cid/review`：加载 / 非教师 / 错误（可重试）/ 就绪；三栏（低置信度关系、疑似重复、孤立知识点）带服务端数量、各自空态、全空提示「可以直接发布」；每条通过/拒绝、不是重复、确认保留；合并先选主知识点再确认；条目下显示错误与成环名称路径；加载更多 |
| `src/frontend/src/composables/useReview.ts`（文件锁） | `useReview`：课程教师校验、读队列 + 草稿名称、`refresh`、`loadMore`（键集游标、去重、422 重读）、`resolve`（单写、`changed = false`、错误码映射、连带变化重读）、合并草稿状态；`isQueue`/`isCounts` 形状校验 |
| `tests/frontend/h09.test.ts`（文件锁） | 37 项：API 层 2、加载与空态 12、单项处理与重复操作 8、疑似重复与合并 6、分页 6、迟到响应 1、审查增补含 401 与空态文案区分、两栏游标互不串栏 |
| `src/frontend/src/api/review.ts`（**扩围，新增**） | `ReviewApi.getQueue` / `resolve`、`REVIEW_API_KEY`、`createReviewApi` |
| `router/index.ts`、`main.ts`、`views/CoursesView.vue`（**扩围**） | `REVIEW_ROUTE`（仅教师账号）；注册页面并注入审核 API；课程页只对课程内教师显示「审核队列」入口 |
| `docs/decisions.md`、`docs/architecture.md`、`specs/teacher-review-publish.md`、`docs/tasks.md` | ADR-070、前端节一行、规格「H09 落实」、H09 节 |

## 行为要点

1. **数量一致**：栏目数量只取服务端 `totals`，本地不加减；用例「通过关系后重新进入页面数量一致」覆盖。
2. **重复操作**：一次只允许一个处理（所有处理按钮禁用、条目 `aria-busy`）；`changed = false` 移除并提示此前已处理；404 移除、提示并重读。
3. **连带变化**：拒绝关系/孤立知识点、合并、404、修订冲突、422、网络中断后重读三栏第一页（条数不少于已加载的，上限 200）；通过关系、不是重复、确认保留不重读。
4. **合并冲突**：`CYCLE_DETECTED` 显示名称环路、保留条目、不重读；`COURSE_BUSY` 提示稍后重试；`REVISION_CONFLICT` 提示并重读。只按错误码给固定文案。

## 验证

仓库根目录执行（`npm --prefix src/frontend ci` 后）：

| 步骤 | 命令 | 结果 |
| --- | --- | --- |
| 任务验证 | `npm --prefix src/frontend run type-check && npm --prefix src/frontend run test -- --run ../../tests/frontend/h09.test.ts` | type-check exit 0；37 passed（审查增补 6 项后） |
| 前端全量 | `npm --prefix src/frontend run test -- --run` | 18 files，623 passed / 1 failed（`b02.test.ts` 的嵌套 `npm test` 用例 5s 超时；`origin/main@ac21e5d` 同样 1 failed / 4 passed，已对照确认是既有 flake，与本 PR 无关） |
| 构建 | `npm --prefix src/frontend run build` | exit 0（仅既有 chunk 体积警告） |
| 门禁 | `PATH=$S/venv/bin:$S/tools/node_modules/.bin:$PATH ./scripts/verify.sh`（`$S` 为 scratchpad；venv 按 `src/contracts/toolchain.txt` 锁定版本安装并 `pip install -e src/backend`；npm 装 openapi-typescript@7.4.4、typescript@5.9.3） | `PASS contracts gate`、`Scaffold verification passed.` |
| 空白 | `git diff --check` | exit 0 |

## 独立审查（2026-09-27，第二会话）

- 结论 **APPROVE_WITH_NOTES**：三条验收（三类空态 / 重复操作 / 合并冲突 / 刷新后数量一致）在实现与用例上都站得住，**未发现产品缺陷**；无 src 改动。
- 反向篡改 16 处（逐处单改、跑 h09、恢复）：14 处被现有用例判红。存活 2 处，均不可经公开输入触发，已补 6 项用例把其中 3 处原本不可检出的语义钉住
  （三栏空态文案必须互不相同；`loadMore` 以响应 `totals` 更新数量；`changed=false` 时数量取 `totals` 且不提示「已通过」），另补 401 文案、缺 `totals` 的重读回退、成环冲突后改选主节点、两栏游标互不串栏。
- 两个存活项（需人裁决，见「风险与下一步」）：`loadMore` 写回 `cursors` 时读的是该栏键（T4b：改成读别栏键后 36 项全绿）——契约要求未请求栏一律 `null`，真实后端如此，故不可观测；`resolve` 的 `busyKey` 守卫（T5a：删掉后全绿）——UI 同时禁用全部处理按钮，属冗余的第二道闸。
- 401 文案（`handleAccess` 已有 `SESSION_EXPIRED_MESSAGE` 分支）此前无用例覆盖，现补断言（篡改删掉该分支即判红）。

## 风险与下一步

- **仅假 API 验证**：F11 的 `/review` 与 `/review/actions` 后端路由已在 main，但本页未与真实后端联调；假后端的分页游标是简化实现，只验证前端按契约传 `kind`/`cursor`/`limit`。
- 合并不带 `expected_revisions`（契约 `ReviewDuplicateAction` 无此字段），两名教师同时合并时以服务端 404/`changed` 为准。
- 名称来自一次草稿读取；草稿很大时这是额外开销（ADR-070 后果）。
- **待裁决（审查留存，两项均不可经公开输入触发，故本轮未改代码）**：
  1. `loadMore` 把 `page.next_cursors[field]` 写回 `cursors`（`useReview.ts`）：`field` 取自该栏，若后端违约给未请求栏返回非 null 游标，该栏分页会被静默顶掉。契约（`ReviewQueue.next_cursors` 描述）与 F11 实现都保证未请求栏为 `null`，因此不可观测；如要加固，应显式只认请求栏、其余置 `null`。
  2. `resolve` 开头的 `busyKey.value !== null` 守卫与「所有处理按钮 `:disabled="busy"`」重复：两者任一都能挡住连点，删掉守卫后用例仍全绿（守卫只对绕过 UI 的程序化调用有意义）。
- ADR-070 待 ArvinHan 签收。K05 教师主线 E2E 可把本页作为审核入口。
