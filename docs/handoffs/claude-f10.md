# Claude 交接：F10 合并知识点与重接边

- **任务**：F10（依赖 F08、F06），第九批并行；与 F09 同一执行者顺序完成
- **分支**：本地 `task/f10-f09`，base `ddae1ed`（`main@0b8aa73` + 第九批认领）；未 push
- **决策**：ADR-047（待 ArvinHan 审阅）

## 1. 交付物

| 文件 | 内容 |
| --- | --- |
| `src/backend/app/services/graph/merge_nodes.py` | `merge_nodes(ctx, course_id, primary_id, merged_ids, expected_revisions=None)`：输入校验 → 课程写锁 → 一个 Neo4j 写事务（守卫锁、读、校验、重接方案、F05 验环、`draft_revision + 1`、写） |
| `tests/integration/test_f10.py` | 8 个无服务器用例（输入校验在取锁/读库之前）+ 19 个真实 Neo4j + 真实 SQLite 用例（含 2 个经 API） |
| 扩围 `src/backend/app/repositories/graph_edit.py` | `DraftNodeStore.transaction`（先锁 `DraftWriteGuard`）；事务内语句 `read_nodes`、`read_incident_relations`、`read_evidence`、`update_merged_primary`、`add_evidence`、`replace_relations`、`delete_merged_nodes`；`IncidentRelation` |
| 扩围 `src/backend/app/api/graph_nodes.py` | `POST /kp/merge`（`mergeKnowledgePoints`）；`CycleDetectedError` → 409 `CYCLE_DETECTED`（`details.cycle`） |
| 扩围 `src/backend/app/schemas/contracts.py` | 导出 `MergeRequest` 一行 |
| 扩围契约 | `MergeRequest`：`additionalProperties: false`、可选 `expected_revisions`；合并接口描述；`errors.v1.md` 的 `REVISION_CONFLICT`、`CYCLE_DETECTED` 两行措辞；`gen-contracts.sh` 重新生成三份生成物 |
| 扩围文档 | `docs/decisions.md` ADR-047；`docs/architecture.md` 第 155 行一句；`specs/teacher-review-publish.md`「审核队列」一段 F10 落实 |

## 2. 行为要点

1. 顺序同 ADR-035：校验、`REVISION_CONFLICT`、`CYCLE_DETECTED`、422 `not_found` 都在加 `draft_revision` 之前抛出，事务回滚，Neo4j 与 SQLite 都不变；课程写锁总会释放。
2. 重接：被合并端换成主节点，两端都在合并集合内的关系删除；新 `rel_id` 重新派生（降级关系按 `PREREQUISITE` 派生）；ID 或「类型 + 端点」相同的关系合成一条，主节点原有的关系胜出，否则按可见 → 状态 → 人工 → 置信度 → rel_id；贡献、人工标记、来源对取并集，修订号取最大值 + 1；旧 `RelationIdentity` 删除、新的建立。
3. 验环：可见、未拒绝的 `PREREQUISITE`（去掉被改写的）+ 新形态中可见、未拒绝的候选，交给 `check_candidates`；草稿本已成环也拒绝。
4. 不可见的关系与来源照样迁移、贡献不变，迁移后仍不可见，留给失败任务清理。
5. 主节点：别名并入被合并节点的名称与别名；`merged_from` 展平；加锁、`contrib_manual = true`、修订号 + 1。来源按 `(task_id, chunk_id, start, end)` 去重迁移，保留 `task_id`。被合并节点只在草稿中删除，已发布副本与文本块不动。

## 3. 验证

`S=/tmp/claude-0/-home-user-SmartSketch/90b4bc93-30ee-572e-b7a8-24f4fe0ed242/scratchpad`；`$S/pt.sh` 为共享 venv 的 pytest；`$S/pt-f10.sh`、`$S/vf-f10.sh`、`$S/gen-f10.sh` 只是把 `$S/tools-f10`（新建的 `datamodel-code-generator==0.26.3` venv 与 `openapi-typescript@7.4.4`，版本同 `src/contracts/toolchain.txt`）加入 `PATH` 后分别调用 `pt.sh`、`./scripts/verify.sh`、`./scripts/gen-contracts.sh`。`N="SMARTSKETCH_TEST_NEO4J_URI=bolt://127.0.0.1:7687 SMARTSKETCH_TEST_NEO4J_USER=neo4j SMARTSKETCH_TEST_NEO4J_PASSWORD=x"`。

| 步骤 | 命令 | 结果 |
| --- | --- | --- |
| 红灯 | `$N $S/pt.sh tests/integration/test_f10.py -q`（实现前） | 收集错误：`No module named 'app.services.graph.merge_nodes'`；服务实现后路由未加时 2 failed（405） |
| 绿灯 | `$N $S/pt.sh tests/integration/test_f10.py -q` | 27 passed |
| 无真库 | `$S/pt.sh tests/integration/test_f10.py -q` | 8 passed, 19 skipped |
| 集成全量 | `$N $S/pt-f10.sh tests/integration -q` | 246 passed, 3 skipped, 1 failed：`test_k08.py::test_images_build`（本机 docker 构建镜像时 `pip install` 失败，与本任务无关） |
| 后端 + 契约 | `$S/pt.sh tests/backend tests/contracts -q` | 3384 passed, 3 failed（B14/门禁负向用例需要生成器在 `PATH`）；`$S/pt-f10.sh tests/contracts -q` 291 passed；后端即 3096 passed，与基线一致 |
| 前端 | `npm --prefix src/frontend run type-check`；`npm --prefix src/frontend run test -- --run ../../tests/frontend/b15.test.ts` | 通过；23 passed |
| 门禁 | `$S/vf-f10.sh`（`./scripts/verify.sh`） | exit 0 |
| 空白 | `git diff --check` | 无输出 |

### 反向篡改（`$S/tamper-f10.py`，连真库跑 `test_f10.py`，每处跑完原样还原）

| # | 篡改 | 结果 |
| --- | --- | --- |
| T1 | 不验环 | 3 failed |
| T2 | rejected 边参与验环 | 1 failed |
| T3 | 不可见边参与验环 | 1 failed |
| T4 | 来源不去重 | 1 failed |
| T5 | 主节点原有关系不优先 | 起初 0 failed（用例中主节点的边恰好也是 approved）；加强用例（主节点边 draft、迁来的边 approved）后 1 failed |
| T6 | 不丢弃自环 | 1 failed |
| T7 | 校验前就加草稿修订号 | 5 failed |
| T8 | 谱系不展平 | 2 failed |
| T9 | 不核对 `expected_revisions` | 2 failed |
| T10 | 关系贡献不取并集 | 1 failed |
| T11 | 不删旧关系身份 | 3 failed |
| T12 | 降级关系按现类型派生 ID | 1 failed |
| T13 | 只迁移可见关系 | 2 failed |
| T14 | 不可见节点当作存在 | 1 failed |

14 处全部检出（T5 在补强用例后检出）。

## 4. 接口与数据变更

- REST：`mergeKnowledgePoints` 实现；`MergeRequest` 新增可选 `expected_revisions`，并禁止多余字段（`additionalProperties: false`，前端 B15 用例只发 `primary_id`、`merged_ids`，不受影响）。错误：422 `VALIDATION_ERROR`（`reason` 为 `too_short`、`blank`、`duplicate`、`contains_primary`、`not_in_merge`、`int_type`、`greater_than_equal`、`not_found`），409 `REVISION_CONFLICT` / `CYCLE_DETECTED` / `COURSE_BUSY`，503 `STORAGE_UNAVAILABLE`。
- Neo4j：无 DDL。主节点新增/更新 `merged_from`；关系重建（`rel_id` 重新派生），`RelationIdentity` 随之增删。
- SQLite：无迁移；成功合并 `draft_revision + 1`。

## 5. 风险

1. 被合并节点的 `kp_id` 若被后续抽取任务再次写出，F04 会重建该节点，与主节点 `merged_from` 冲突，发布时 `invalid_lineage` 阻断（F04 尚不查谱系）。
2. 迁移关系的 `downgrade_cycle` 保留旧节点 ID。
3. 合并数量无上限；一次读写都在一个事务里，极大合并会长时间持守卫锁。
4. 合并后的关系胜出规则（主节点原有关系优先）与状态优先级为 Claude 选定，待签收。

## 6. 待决

- ADR-047 待 ArvinHan 签收（尤其第 3 条胜出规则、第 2 条 422 `not_found` 而非 404、`expected_revisions` 可选而非必填）。
- F04 是否应拒绝写回已被合并的 `kp_id`（查 `merged_from`）。
- 审计日志（直接父子关系）归 F12。

## 7. 下一步

F09 删除节点（同一分支、下一提交）；F12 审计日志；H 组合并交互接入 `expected_revisions`。

## 8. 回滚

`git revert <F10 提交>`，或按 ADR-047「回滚」逐项撤销后运行 `./scripts/gen-contracts.sh` 重新生成契约产物；无 SQLite 迁移与 Neo4j DDL。已合并的草稿数据无法自动拆回，需按备份恢复。
