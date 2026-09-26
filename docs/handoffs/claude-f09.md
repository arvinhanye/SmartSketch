# Claude 交接：F09 删除知识点与关系清理

- **任务**：F09（依赖 F08），第九批并行；在 F10 之后于同一分支顺序完成
- **分支**：本地 `task/f10-f09`，F10 提交 `f720dd5` 之上；未 push
- **决策**：ADR-048（待 ArvinHan 审阅）

## 1. 交付物

| 文件 | 内容 |
| --- | --- |
| `src/backend/app/services/graph/delete_node.py` | `delete_node(ctx, course_id, kp_id, expected_revision=None) -> DeletedNode(kp_id, relations)`：输入校验 → 课程写锁 → 一个 Neo4j 写事务（守卫锁 → 读 → 核对 → `draft_revision + 1` → 条件删除） |
| `tests/integration/test_f09.py` | 5 个无服务器用例 + 12 个真实 Neo4j + 真实 SQLite 用例（含并发删除、删除与合并并发、1 个经 API） |
| 扩围 `src/backend/app/repositories/graph_edit.py` | `_TX_DELETE_NODE` 与 `delete_draft_node`（复用 F10 的 `DraftNodeStore.transaction`、`read_nodes`） |
| 扩围 `src/backend/app/api/graph_nodes.py` | `DELETE /kp/{kid}`（`deleteKnowledgePoint`，204）；`_run` 支持无响应体 |
| 扩围契约 | `deleteKnowledgePoint` 新增可选查询参数 `expected_revision`（≥ 1）、422 响应与描述；`errors.v1.md` `REVISION_CONFLICT` 措辞；重新生成 `openapi.json` 与 `openapi.d.ts`（Python 模型无变化） |
| 扩围文档 | `docs/decisions.md` ADR-048；`docs/architecture.md` 第 155 行续一句；`specs/teacher-review-publish.md`「审核队列」一段 F09 落实 |

## 2. 行为要点

1. 只删草稿：节点、与它相连的全部草稿关系（含对 V 不可见的）及其 `RelationIdentity`、来源关联、`merged_from`。其他版本的副本（同 `kp_id`/`rel_id`）、同 ID 的他版本关系身份、SQLite 版本行与快照、发布指针、共享文本块都不动。
2. 不存在、不可见、他课、只在已发布版本中存在、空白 ID → 404 `NOT_FOUND`；`expected_revision` 过期 → 409 `REVISION_CONFLICT`；非法 → 422；课程写锁被占 → 409 `COURSE_BUSY`。以上都不写任何数据、不加 `draft_revision`。
3. 并发：删除经课程写锁 + 守卫串行，同一节点恰有一次成功，其余 404；与 F10 合并并发时结果二选一且一致。

## 3. 验证

命令约定同 `claude-f10.md` §3（`$S`、`$N`、`pt-f10.sh`、`vf-f10.sh`、`gen-f10.sh`）。

| 步骤 | 命令 | 结果 |
| --- | --- | --- |
| 红灯 | `$N $S/pt.sh tests/integration/test_f09.py -q`（实现前） | 收集错误：`No module named 'app.services.graph.delete_node'`；服务实现后路由未加时 1 failed（`test_api_delete_results`） |
| 绿灯 | `$N $S/pt.sh tests/integration/test_f09.py -q` | 17 passed；并发两用例连跑 5 次均通过 |
| 无真库 | `$S/pt.sh tests/integration/test_f09.py -q` | 5 passed, 12 skipped |
| F10 回归 | `$N $S/pt.sh tests/integration/test_f09.py tests/integration/test_f10.py -q` | 44 passed |
| 后端 + 契约 | `$S/pt-f10.sh tests/backend tests/contracts -q` | 3387 passed（后端 3096 与基线一致 + 契约 291） |
| 集成全量 | `$N $S/pt-f10.sh tests/integration -q` | 263 passed, 3 skipped, 1 failed：`test_k08.py::test_images_build`（本机 docker 构建镜像时 `pip install` 失败，与本任务无关，F10 时同样失败） |
| 前端 | `npm --prefix src/frontend run type-check` | 通过 |
| 门禁 | `$S/vf-f10.sh`（`./scripts/verify.sh`）；`git diff --check` | exit 0；无输出 |

### 反向篡改（`$S/tamper-f09.py`，连真库跑 `test_f09.py`，每处跑完原样还原）

| # | 篡改 | 结果 |
| --- | --- | --- |
| T1 | 按 `kp_id` 删所有版本的节点 | 1 failed |
| T2 | 不删关系身份 | 1 failed |
| T3 | 删关系身份不限版本 | 起初 0 failed；已发布用例补一个同 ID 的他版本身份后 1 failed |
| T4 | 不可见节点也删 | 1 failed |
| T5 | 不核对 `expected_revision` | 2 failed |
| T6 | 校验前加草稿修订号 | 6 failed |
| T7 | 不存在时静默成功 | 6 failed |
| T8 | 不取课程写锁 | 1 failed |
| T9 | API 不透传 `expected_revision` | 1 failed |

9 处全部检出（T3 在补强用例后检出）。

## 4. 接口与数据变更

- REST：`deleteKnowledgePoint` 实现；新增可选查询参数 `expected_revision`，新增 422 响应。原有无参数调用不变。
- Neo4j：无 DDL；只删除草稿数据。
- SQLite：无迁移；成功删除 `draft_revision + 1`。

## 5. 风险

1. 教师删除不留墓碑：后续抽取任务再次写出同一 `kp_id` 时 F04 会重建该节点。
2. 失败任务留下的不可见关系随节点删除，之后的撤销对其无操作（预期）。
3. 前端尚未接入 `expected_revision`，不带参数的删除不做乐观并发核对（最后写入者生效，但结果明确：已删则 404）。

## 6. 待决

- ADR-048 待 ArvinHan 签收（尤其「只存在于已发布版本 → 404」「`expected_revision` 可选」）。
- 是否需要墓碑阻止 F04 重建被删节点（与 ADR-047 风险 1 同一问题）。
- 审计日志归 F12。

## 7. 下一步

F12 审计日志记录删除与合并；前端（H 组）删除确认与 `expected_revision` 接入。

## 8. 回滚

`git revert <F09 提交>`（F10 不受影响），或按 ADR-048「回滚」逐项撤销后运行 `./scripts/gen-contracts.sh`；无 SQLite 迁移与 Neo4j DDL。已删除的草稿数据只能从备份恢复。
