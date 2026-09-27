# Claude 交接：H09 审核队列与节点合并 UI

- `task_id`: H09（`docs/atomic-tasks.json`「实现审核队列和节点合并 UI」），issue #121
- `review_status`: 待 PR 审查
- 分支：`claude/project-thread-eo5fzo`；`base_commit`: `ac21e5d`（origin/main）
- 依赖：F10（合并，ADR-047）、F11（审核队列 API，ADR-060）、H07（节点编辑的错误处理约定）
- 决策：ADR-070
- 断点：issue 挂着旧的 `status:in-progress`，远端无分支/PR、三个允许文件都不存在；本轮从零实现。

## 交付物

| 文件 | 内容 |
| --- | --- |
| `src/frontend/src/views/ReviewView.vue`（文件锁） | 路由页 `/courses/:cid/review`：加载 / 非教师 / 错误（可重试）/ 就绪；三栏（低置信度关系、疑似重复、孤立知识点）带服务端数量、各自空态、全空提示「可以直接发布」；每条通过/拒绝、不是重复、确认保留；合并先选主知识点再确认；条目下显示错误与成环名称路径；加载更多 |
| `src/frontend/src/composables/useReview.ts`（文件锁） | `useReview`：课程教师校验、读队列 + 草稿名称、`refresh`、`loadMore`（键集游标、去重、422 重读）、`resolve`（单写、`changed = false`、错误码映射、连带变化重读）、合并草稿状态；`isQueue`/`isCounts` 形状校验 |
| `tests/frontend/h09.test.ts`（文件锁） | 31 项：API 层 2、加载与空态 10、单项处理与重复操作 7、疑似重复与合并 5、分页 4、迟到响应 1 等 |
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
| 任务验证 | `npm --prefix src/frontend run type-check && npm --prefix src/frontend run test -- --run ../../tests/frontend/h09.test.ts` | type-check exit 0；31 passed |
| 前端全量 | `npm --prefix src/frontend run test -- --run` | 18 files，618 passed |
| 构建 | `npm --prefix src/frontend run build` | exit 0（仅既有 chunk 体积警告） |
| 门禁 | `PATH=$S/venv/bin:$S/tools/node_modules/.bin:$PATH ./scripts/verify.sh`（`$S` 为 scratchpad；venv 按 `src/contracts/toolchain.txt` 锁定版本安装并 `pip install -e src/backend`；npm 装 openapi-typescript@7.4.4、typescript@5.9.3） | `PASS contracts gate`、`Scaffold verification passed.` |
| 空白 | `git diff --check` | exit 0 |

## 风险与下一步

- **仅假 API 验证**：F11 的 `/review` 与 `/review/actions` 后端路由已在 main，但本页未与真实后端联调；假后端的分页游标是简化实现，只验证前端按契约传 `kind`/`cursor`/`limit`。
- 合并不带 `expected_revisions`（契约 `ReviewDuplicateAction` 无此字段），两名教师同时合并时以服务端 404/`changed` 为准。
- 名称来自一次草稿读取；草稿很大时这是额外开销（ADR-070 后果）。
- ADR-070 待 ArvinHan 签收。K05 教师主线 E2E 可把本页作为审核入口。
