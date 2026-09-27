# Claude 交接：H08 教师连边编辑交互

- `task_id`: H08（`docs/atomic-task-plan.md`「H08 实现教师连边编辑交互」）
- `review_status`: ready_for_review
- 分支：本地 `task/h08`（未 push），base `ddae1ed`（第九批认领提交，其父为 `main@0b8aa73`）
- 依赖：H04（`GraphCanvas.vue`、`graph/lifecycle.ts`）、F06（关系事务写入与 `CycleDetectedError.cycle`）
- 决策：ADR-053（预分配）

## 交付物

| 文件 | 内容 |
| --- | --- |
| `src/frontend/src/composables/useRelationEditor.ts` | 编辑状态：`graph`（store 草稿图 + 叠加层）、`canvasData`（适配图，临时边虚线加「（保存中）」，冲突边 `#ff4d4f`/线宽 3）、`status`（loading/empty/ready）、`nodeOptions`、`relationRows`（与起点相连的关系）、`saving`/`error`/`notice`/`conflict`/`stale`、`highlightedNodeIds`/`highlightedRelationIds`；方法 `pickNode`、`swapDraft`、`createRelation`、`changeType`、`reverseRelation`、`deleteRelation`、`dismissConflict` |
| `src/frontend/src/components/RelationEditor.vue` | props `editor`（组合式返回值）。加载/空态 `role="status"`；起点/终点/类型三个带 `label` 的下拉、交换按钮、提交；成环时 `role="alert"` 的有序冲突路径，可关闭；其他错误 `role="alert"`；保存中 `aria-busy` 且控件禁用；起点关系列表可改类型、反转（`RELATED_TO` 禁用）、删除 |
| `tests/frontend/h08.test.ts` | 35 项：API 层 3、状态与选点 4、乐观更新与回滚 20（含经 `createGraphLifecycle` 验证冲突色传到 G6）、组件 6、分层源码检查 2 |
| `src/frontend/src/api/relations.ts`（扩围，新文件） | `createRelationsApi(client)`：`create`/`update`/`remove`，`RELATIONS_API_KEY` |
| `docs/decisions.md`（扩围） | 末尾追加 ADR-053 |

页面接法（本任务未接入路由，规格未要求）：

```ts
const editor = useRelationEditor({ api: inject(RELATIONS_API_KEY)!, onRefreshNeeded: reloadDraftGraph, onCourseForbidden: toCourses })
// <GraphCanvas :graph="editor.canvasData.value" @node-click="editor.pickNode" />
// <RelationEditor :editor="editor" />
```

## 行为要点

1. **乐观更新**：请求期间叠加一条临时改动，不写 store；成功后把响应合并进 store **当时**的图（期间图被重新加载也不丢），失败丢弃叠加层即撤销临时边。一次只允许一个写请求。
2. **成环**：`details.cycle`（F06：`(source, *back)`，沿边方向、首尾相同）→ 名称路径；环上相邻两点间未拒绝的 `PREREQUISITE` 边与本次被修改的关系标为冲突。`details` 不合规时只提示。
3. **修订冲突**：关系接口无 `expected_revision`，按通用 409 `REVISION_CONFLICT` 兜底：撤销、`stale = true`、调用 `onRefreshNeeded`；`NOT_FOUND`、`DANGLING_ENDPOINT` 同样处理。图谱重新加载后 `stale` 复位。
4. 其他：`DUPLICATE_RELATION` 标出 `existing_id`；`COURSE_BUSY` 提示稍后重试；`COURSE_FORBIDDEN` 清当前课程并回调；`ROLE_FORBIDDEN`/401/网络/超时固定文案，不回显服务端 `message`。切课时取消在途请求、丢弃晚到结果（含晚到的失败），清空叠加层、选点与提示。
5. 组件不 import `api/` 与 `stores/`，无 `fetch`/`request`、无 Cypher（测试读源码断言）。

## 验证（worktree 根目录）

| 步骤 | 命令 | 结果 |
| --- | --- | --- |
| 红灯 | `npm --prefix src/frontend run test -- --run ../../tests/frontend/h08.test.ts`（仅测试与 `api/relations.ts`） | 无法解析 `components/RelationEditor.vue`，`Tests no tests` |
| 绿灯 | 同上 | 35 passed |
| 类型检查 | `npm --prefix src/frontend run type-check` | exit 0（含 `tests/frontend`） |
| 前端全量 | `npm --prefix src/frontend run test -- --run` | 12 files，347 passed（基线 312 + 35）。第一次跑 `b02` 的嵌套 vitest 用例 5 s 超时（并行负载），单独重跑 5 passed，全量重跑 347 passed |
| 构建 | `npm --prefix src/frontend run build` | exit 0（组件未被页面引用，不进产物） |
| 门禁 | `./scripts/verify.sh`（PATH 前置共享 venv 与 openapi-typescript，同 `scratchpad/vf-f10.sh`） | exit 0，`Scaffold verification passed.` |
| 空白 | `git diff --check` | 无输出 |

绿灯前修过两处测试本身：分层检查的 Cypher 正则把 TS 参数注解 `(scope: CourseRequestScope)` 误判为节点模式，改为按子句关键字与 `-[r:T]->` 匹配；`COURSE_FORBIDDEN` 用例原断言「边恢复」，实际当前课程被清空、图为 null，改为断言后者。

### 反向篡改（脚本逐个改实现、跑 h08、还原；结束后源文件与原文一致）

| # | 篡改 | 结果 |
| --- | --- | --- |
| M1 | 失败时不丢弃叠加层（不撤销临时边） | 8 failed |
| M2 | 冲突高亮不限 `PREREQUISITE` | 1 failed |
| M3 | 修订冲突不调用 `onRefreshNeeded` | 3 failed |
| M4 | 成功结果合并进请求开始时的旧图 | 1 failed |
| M5 | 错误提示去掉 `role="alert"` | 1 failed |
| M6 | 写请求不防重入 | 1 failed |
| M7 | 画布不画冲突色 | 2 failed |
| M8 | 不记录冲突路径 | 5 failed |
| M9 | 切课后仍处理旧课程的错误 | 1 failed |
| M10 | 临时边无保存中样式 | 1 failed |
| M11 | 反转不拦无向关系 | 1 failed |

首轮 M6（只删 `createRelation` 开头的防重入）与 M9 未被检出：前者与 `ready()` 里的检查重复，已删去冗余行、改为篡改 `ready()`；后者补了「切课后晚到的失败」用例。两者复跑均检出，共 11 处全部检出。

## 接口 / 数据变更

无契约、后端、路由或依赖变更。新增前端 API 封装 `api/relations.ts`（只用契约既有的 `createRelation`/`updateRelation`/`deleteRelation`）。

## 风险

1. **后端关系路由尚未实现**：`src/backend/app/api/` 中没有 `/relations`；F06 只提供服务层。本任务按契约与 `errors.v1.md` 用假 API 验证，未与真实后端联调。
2. 关系请求体无 `expected_revision`，两名教师先后改同一关系时后写者直接生效；前端只能处理服务端给出的 409。
3. 画布上不能给节点着色：`lifecycle.ts` 的 `copyNode` 只复制 `id`/`data`。冲突节点目前只在面板路径列表与 `highlightedNodeIds` 中体现。

## 待决

1. 关系路由落地时是否为关系加 `expected_revision`（ADR-035 目前只覆盖节点）；如加，`RelationUpdate` 与本组合式需同步。
2. G6 真正的拖线（`create-edge` 行为）与节点冲突着色需改 H04 的 `lifecycle.ts`，建议另立小任务。
3. 服务端 `CYCLE_DETECTED.details` 是否附带 F06 的 `edge`（闭合环的候选）；目前前端用本地记录的 `proposed`。

## 下一步

- 后端实现关系路由（F06 服务 + 课程写锁 + 错误映射），再做前后端联调。
- 教师图谱页（H05/H07 页面）组合 `GraphCanvas` + `RelationEditor`，`onRefreshNeeded` 接草稿图重新加载；K05 E2E 覆盖「成环拒绝」。

## 回滚

`git revert` 本提交，或删除 `src/frontend/src/api/relations.ts`、`src/frontend/src/composables/useRelationEditor.ts`、`src/frontend/src/components/RelationEditor.vue`、`tests/frontend/h08.test.ts` 与本交接，并删去 `docs/decisions.md` 末尾的 ADR-053。无数据迁移。
