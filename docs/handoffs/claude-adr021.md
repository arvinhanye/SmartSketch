# Claude 交接：ADR-021 资料 task_id 与删除资料接口

- task_id: ADR-021（H02 交出的两项缺口，ArvinHan 2026-09-26 在会话中决定「加上 task_id」「添加删除资料的接口」）
- review_status: ready_for_review
- 分支：`claude/project-thread-sp1d3a`（随 PR #255）
- 状态：实现与验证完成，待 PR 审查/合并

## 改动文件

| 文件 | 说明 |
| --- | --- |
| `docs/decisions.md` | 新增 ADR-021 |
| `specs/task-processing.md`、`specs/identity-access.md` | D-16 行补 `task_id` 与删除；访问矩阵加 `deleteDocument` |
| `src/contracts/api.v1.yaml`、`src/contracts/errors.v1.md`、`src/contracts/v1/generated/*` | `Document.task_id`（必填可空）、`DELETE /api/v1/courses/{cid}/documents/{did}`、错误码 `DOCUMENT_NOT_DELETABLE` 与 `DocumentNotDeletableDetails`；生成物由 `gen-contracts.sh` 重新导出 |
| `src/backend/app/repositories/materials.py` | 列表带最新任务 ID；`delete_material`（`BEGIN IMMEDIATE` 内复核并删除） |
| `src/backend/app/services/materials.py` | `delete_course_material`：提交后删存储文件，失败只记日志 |
| `src/backend/app/api/materials.py`、`src/backend/app/schemas/materials.py` | 路由 `deleteDocument`、`Document.task_id` |
| `tests/backend/test_adr021.py` | 新增 27 个用例；`tests/backend/test_c07.py` 只改 `DOCUMENT_KEYS` 并断言 `task_id` |
| `src/frontend/src/api/materials.ts`、`composables/useMaterials.ts`、`views/MaterialsView.vue` | 续订处理中资料的进度；删除（先确认） |
| `src/frontend/src/api/http.ts`、`src/frontend/src/api/taskEvents.ts` | 错误码运行时副本加 `DOCUMENT_NOT_DELETABLE`（类型断言要求与契约一致） |
| `tests/frontend/h02.test.ts` | 新增 18 个用例（共 71） |

## 行为

- **删除条件**：该资料全部任务为 `failed`/`cancelled` 且没有 `cleanup_pending`。否则 409，`reason`：`processing`（有未结束任务）> `contributed`（有任务到达 `awaiting_review`/`completed`）> `cleanup_pending`，`stage` 为该类中最新创建任务的阶段。没有任务的资料可删。他课或不存在的资料 404。
- **删除内容**：同一事务删 `chunks`、`task_revisions`、`material_revisions`、`processing_tasks`（SSE 票据级联）、`materials`；保留 `model_calls`。提交后删存储文件，失败留孤儿文件并记日志，仍 204。
- **前端**：列表中处理中且带 `task_id` 的资料自动订阅进度、可取消；失败/已取消行显示「删除资料」→「确认删除 / 不删除」。409 `processing` 按 `details.stage` 刷新行状态；`contributed` 保留行状态（最新任务仍是失败/取消）并隐藏删除；`cleanup_pending` 提示稍后再试并保留入口；404 视为已删除。

## 验证（实际结果）

| 命令 | 结果 |
| --- | --- |
| 红灯：`python -m pytest tests/backend/test_adr021.py -q`（实现前） | 25 failed, 1 passed |
| `python -m pytest tests/backend -q` | 2757 passed |
| `python -m pytest tests/contracts tests/tooling -q` | 323 passed（首次因内联 `details` 被 `test_b13` 拦下，改为命名 schema 后通过） |
| `./scripts/gen-contracts.sh --check`、`./scripts/verify.sh`、`git diff --check` | exit 0 |
| 前端红灯：`h02.test.ts`（实现前） | 11 failed |
| `npm --prefix src/frontend run type-check`、`build` | exit 0 |
| `npm --prefix src/frontend run test -- --run` | 9 files, 254 passed |

反向篡改：后端 7 处（去 processing/contributed/cleanup_pending 拦截、不删 chunks、task_id 置空、阻塞任务取最早），前端 5 处（不续订、去防重入、不隐藏删除、409 contributed 覆盖阶段、成功不移除行），均被检出；前端「删除时关闭订阅」无法在正常流程中构造（已结束行的流已关闭），未单独覆盖。

## 风险与下一步

- 已产生贡献的资料仍不能删除（需级联清理草稿图与发布版引用），留作后续任务。
- F13 落地后，失败任务写入 Neo4j 的 `Chunk` 节点若未被 §8.4 清理回收，会指向已删除的 SQLite 块（对读者不可见），由 F13/G 组一并处理。
- 前端 50 MiB 上限仍写死（未在本轮决定范围内）。

## 回滚

`git revert` 本任务提交；无数据库迁移。已删除的资料不可恢复（只可能是失败或已取消且无贡献的资料）。
