# Claude 交接：PR #264（G05+G06）独立审查四项遗留修复

- review_status: ready_for_review
- task_id: #264-R1～R4
- 分支：`claude/leftovers264-0927`；base：`main@ac21e5d`
- 状态：DONE（待 PR 审查/合并）；未 push、未 merge
- 决策：ADR-072；看板：`docs/tasks.md`「2026-09-27 PR #264（G05+G06）独立审查四项遗留修复」

## 交付物（四项各自独立 commit，可单独 revert）

| Commit | 遗留 | 改动 |
| --- | --- | --- |
| `9c5d753` | R1 sweep 调度 | `src/backend/app/workers/runner.py`（`PublishSweep`、`build_maintenance`、`run_loop` 默认接线）、`src/backend/app/config.py`（`PUBLISH_SWEEP_INTERVAL_SECONDS`）、`.env.example`、`docs/integrations.md`、`tests/backend/test_g05_sweep_schedule.py`（5 用例） |
| `b318172` | R2 空清理解锁 | `src/backend/app/repositories/graph_relations.py`（`task_has_contributions` + 查询）、`src/backend/app/workers/persist_graph.py`（`cleanup_failed_task` 前置判断）、`tests/backend/test_264_cleanup_lock.py`（4 用例） |
| `38b3dbd` | R3 重跑状态保护 | `src/backend/app/repositories/graph_nodes.py`（`_WRITE_BATCH` 状态列）、`tests/integration/test_f13.py`（3 用例 + `_BrokenRepo.read`） |
| `03ab66b` | R4 无来源手工节点 | `src/contracts/api.v1.yaml`、`src/contracts/v1/generated/*`（重新生成）、`src/backend/app/services/graph/read.py`、`src/backend/app/api/graph.py`、`src/backend/app/schemas/contracts.py`、`tests/backend/test_f07.py`（4 用例）、`tests/contracts/test_264_leftovers.py`（4 用例） |

## 逐项：根因 → 修复 → 验收

### R1 `sweep` 未接入 worker 周期回收（A06 §8.6；ADR-036 第 5 条待决）

- 根因：`reconcile.sweep` 已实现，但 `runner.run_loop` 的 `maintenance` 挂点（ADR-039 第 3 条预留）默认空，`_child_main` 不传任何 hook —— 仓库里没有任何调度。
- 修复：`PublishSweep` 接在挂点，每轮后按 `time.monotonic` 判断是否到点；`run_loop` 在未注入 `step` 的生产路径上默认 `build_maintenance`。周期/开关只从环境变量读（`PUBLISH_SWEEP_INTERVAL_SECONDS`，整数 ≥ 0，缺省 `3600`，`0` 关闭）。`sweep` 逐课程隔离，`PublishSweep` 再兜一层 `except Exception` 只记日志；下次时间在调用前排定（故障按周期重试，不每轮打 Neo4j）。
- 红灯：实现前 `test_g05_sweep_schedule.py` 与基线（未修）对照 4 failed（旧 `runner` 没有 `PublishSweep`/`build_maintenance`，且生产路径无清扫）。见「反向篡改矩阵」T1a/T1b/T1c。
- 绿灯：`tests/backend/test_g05_sweep_schedule.py` **5 passed**。
- 验收对照：到点调用 `test_sweep_runs_only_when_the_interval_has_elapsed`；抛错不打断主循环 `test_failed_sweep_is_logged_and_does_not_break_the_worker_loop`；0 关闭与缺省值 `test_interval_zero_disables_the_hook_and_defaults_to_hourly`；配置校验 `test_interval_must_be_a_non_negative_integer`；生产装配 `test_production_loop_wires_the_publish_sweep_by_default`。

### R2 无实际工作时清理空等课程锁（§8.4 第 4 步）

- 根因：`persist_graph.cleanup_failed_task`（约 315 行起）无条件 `course_locks.acquire(wait_seconds=lock_wait_seconds)`；`_after_failure`/`_release` 对每次 `persisting` 失败都置 `cleanup_pending`，即使 Neo4j 里根本没有本任务的贡献（例如成环回滚、锁等不到而退避耗尽），仍要等到锁或超时。
- 修复：新增 `graph_relations.task_has_contributions(repo, scope, task_id)`（存在性读，谓词与 `_REVOKE_RELATIONS`/`_REVOKE_NODES` 一一对应）；`cleanup_failed_task` 先读，无工作直接 `clear_cleanup_pending` 返回（不取锁、不等待），有工作完全沿用原路径（取锁 → 同一写事务 `lock_draft` + `revoke_task` → 清标记）。读失败返回 `False`、保留 `cleanup_pending`、不取锁。
- 一致性论证：只有 `persisting` 写任务贡献且仅在持有租约期间；T9 清空租约，`claim_next` 不领取 `failed` 任务，所以判断发生在 T9 之后时「没有贡献」是最终结论——判断与撤销分离不会漏掉工作。并发清理在锁上串行，`revoke_task` 幂等。ADR-025 的守卫串行与租约语义不变。
- 红灯：未修时 `test_264_cleanup_lock.py` 的鉴别用例红——旧实现取锁（`acquired == ['w']`）且返回 `False`（`assert False is True`）。
- 绿灯：`tests/backend/test_264_cleanup_lock.py` **4 passed**；`tests/integration/test_f13.py` 全量 **30 passed**（真实 Neo4j，含 LEASE-12/18 与 DAG-10 清理路径）。
- 验收对照：无工作不取锁 `test_no_pending_work_clears_the_marker_without_taking_the_course_lock`；有工作仍取锁且撤销 `test_pending_work_still_takes_the_lock_and_revokes`；读失败保留标记 `test_unreadable_graph_leaves_the_marker_and_takes_no_lock`；空 task_id 拒绝 `test_the_contribution_check_rejects_a_blank_task_id`。

### R3 任务重跑覆盖教师已裁决状态（E09/E10 → T9）

- 根因（文件:行）：`src/backend/app/repositories/graph_nodes.py` 的 `_WRITE_BATCH`（`_WRITE_BATCH` SET 段，约 213 行）对未被加锁的节点**无条件**写 `n.status = row.status`；`row.status` 恒为 `AUTO_STATUS = 'draft'`。教师裁决路径都会置 `locked = true`（F08 更新、F11 节点拒绝），但 `unlockKnowledgePoint`（ADR-035 决定 4）把 `locked` 置回 `false` 而保留 `status`，于是重跑把 `approved`/`rejected` 写回 `draft`。关系侧无此问题：`graph_relations._MERGE` 对任务写入不写 `r.status`，且 `contrib_manual` 让 `revoke_task` 保留教师处理过的关系（补回归用例）。
- 修复：先算「本次最终状态」——已有 `approved`/`rejected` 原样保留，其余沿用候选状态；`changed` 与最终状态比较，内容未变的重跑不改状态也不加 `revision`。内容、别名与来源照常更新；只保护 `approved`/`rejected`；加锁节点仍完全不动（F04/ADR-024 决定 4）。
- 红灯（真实 Neo4j）：未修时 `after[0]["status"] == 'draft'`（`assert 'draft' == 'approved'`）与 `['draft'] == ['rejected']`。
- 绿灯：`tests/integration/test_f13.py` **30 passed**（含 3 个新用例）。
- 验收对照：approve 后重跑仍 approved + 内容幂等 `test_live_rerun_keeps_an_approved_node_approved_and_updates_its_content`；reject 后重跑不复活 `test_live_rerun_does_not_resurrect_a_rejected_node`；重跑幂等（未审核仍 draft、revision 不变）`test_live_rerun_with_unchanged_candidates_is_idempotent`。
- 测试边界：只有本任务贡献的纯 AI 节点会被 `revoke_task` 删除并重建（观察上幂等但测不到 revision 的更新路径），所以幂等用例先给节点/关系加上另一个任务的贡献，让重跑走「更新已有元素」的路径。
- ADR-060「确认保留」：存在 SQLite `review_dismissals`、按 `kp_id` 记；确定性 ID 在重跑间稳定，`persisting` 不触碰它，永久性不受影响（没有为它改图数据）。

### R4 无来源人工节点详情 500（F07/F08 口径）

- 根因（文件:行）：`src/backend/app/services/graph/read.py` 的 `read_knowledge_point`（约 356 行）在 `_evidence_refs` 为空时一律 `raise SourceUnavailable`，`api/graph.py` 映射为 500 `INTERNAL_ERROR`；但手工节点（`source = manual`）在来源块被删/不可定位时没有来源可给，AI 节点缺来源才是完整性故障。
- 契约取舍：**不采用**放宽 `KnowledgePointDetail.source_refs` 的 `minItems: 1`（选项 a）——它会推翻既有负例 `tests/contracts/test_b11.py::test_node_detail_requires_locatable_source`，而那正是要保留的「AI 节点不得缺来源」不变量；OpenAPI 3.0 也没有 `if/then` 表达条件必填。**采用**新增 `KnowledgePointDetailWithoutSource`（字段相同，`source_refs` 为 `maxItems: 0` 的显式空数组），`getKnowledgePoint` 的 200 改为两者 `oneOf`，`KnowledgePointDetail` 原样不动；按 ADR-004 重新生成并入库。
- 修复：`read_knowledge_point` 用读到的**原值** `source` 判定——`manual` 且无可定位来源 → 200 空态；其他（含发布副本缺 `source` 属性）→ 仍 500。`GET /graph` 聚合路径不带 `source_refs`，本来不 500，补回归。
- 红灯：`test_manual_node_without_any_locatable_source_is_200_with_an_explicit_empty_state` → `assert 500 == 200`。
- 绿灯：`tests/backend/test_f07.py` + `tests/contracts/test_264_leftovers.py` + R1/R2 新用例合计 **38 passed**；契约门禁 PASS。
- 验收对照：手工无来源 200 空态；`test_ai_node_without_any_locatable_source_is_still_500_not_the_empty_state`；发布副本缺 `source` 不按手工处理 `test_published_copy_without_source_property_is_not_treated_as_manual`；`GET /graph` 不 500 `test_manual_node_without_source_is_in_the_graph_read_without_error`；契约语义 `tests/contracts/test_264_leftovers.py`（4 用例，含生成模型与 TS）。

## 命令与实际结果

| 命令 | 结果 |
| --- | --- |
| `PYTHONPATH=$PWD/src/backend .venv/bin/python -m pytest tests/backend -q` | **3236 passed, 27 skipped**（基线 `ac21e5d` 为 3223 passed / 27 skipped；新增 13 个用例全绿） |
| `SMARTSKETCH_TEST_NEO4J_URI=bolt://localhost:17687 … PYTHONPATH=$PWD/src/backend .venv/bin/python -m pytest tests/integration/test_f13.py -q` | **30 passed**（真实 Neo4j 5.26.31，容器 `ss-neo4j-f11`） |
| `PYTHONPATH=$PWD/src/backend .venv/bin/python -m pytest tests/contracts/test_b11.py tests/contracts/test_264_leftovers.py -q` | **34 passed**（B11 既有负例不变 + 新契约用例 4） |
| `./scripts/gen-contracts.sh --check` | `✓ 生成物与真源一致` |
| `./scripts/verify/contracts.sh` | **PASS contracts gate**（含 B14 生成/漂移回归、门禁负向 25 项、B08/B09/B10/B12/B13） |
| `python3 -c` 打印 `app.services.versions.reconcile.__file__` 等 | 均指向本 worktree 的 `src/backend/app/...`（非主仓） |

## 接口 / 数据变更

- 契约：新增 `KnowledgePointDetailWithoutSource`；`GET /api/v1/courses/{cid}/kp/{kid}` 的 200 由 `$ref KnowledgePointDetail` 改为 `oneOf` 两种形状。`KnowledgePointDetail`（`source_refs` `minItems: 1`）不变，B11 负例仍成立。生成物（`openapi.json`、`python/models.py`、`typescript/openapi.d.ts`、`schemas/`）已重新生成入库，`--check` 一致。前端 `KnowledgeDetailApi.get` 仍按 `KnowledgePointDetail` 声明即可编译（两种形状在生成的 TS 里结构相同，联合可赋给前者），前端未改动。
- 配置：新增 `PUBLISH_SWEEP_INTERVAL_SECONDS`（整数 ≥ 0，缺省 3600，0 关闭），只从环境变量读；`.env.example` 与 `docs/integrations.md` 已同步。
- 图数据：无 DDL、无迁移。R3 只改写入时的状态选择逻辑。
- 无破坏性数据模型变更；回滚见 ADR-072「回滚」段（四项可单独 `git revert`，已写入的数据不回滚）。

## 反向篡改矩阵（10 处，全部检出，无存活项）

| 篡改 | 位置 | 判别用例（红） |
| --- | --- | --- |
| T1a 到点判断失效（永不触发） | `runner.PublishSweep.__call__` | `test_sweep_runs_only_when_the_interval_has_elapsed`、`test_failed_sweep_...`（2 failed） |
| T1b 错误隔离失效（`except Exception` → `except ValueError`） | `runner.PublishSweep.__call__` | `test_failed_sweep_is_logged_and_does_not_break_the_worker_loop`（1 failed） |
| T1c 生产路径不再接清扫 | `runner.run_loop` | `test_production_loop_wires_the_publish_sweep_by_default`（1 failed） |
| T2a 缺来源一律空态（吞掉 AI 故障） | `read.read_knowledge_point` | `test_ai_node_...`、`test_published_copy_...`、`test_detail_without_any_locatable_source_is_internal_error`（3 failed） |
| T2b 放宽 `minItems: 1 → 0` | `src/contracts/api.v1.yaml` | `test_b11.py::test_node_detail_requires_locatable_source` + `test_264_leftovers`（2 failed） |
| T3a 无工作也取锁 | `cleanup_failed_task` | `test_no_pending_work_clears_the_marker_without_taking_the_course_lock`（1 failed） |
| T3b 永远当成有工作 | `task_has_contributions` | 同上（1 failed） |
| T3c 有工作时跳过课程写锁 | `cleanup_failed_task` | `test_pending_work_still_takes_the_lock_and_revokes`（1 failed） |
| T4a 重跑覆盖已裁决状态 | `_WRITE_BATCH` 状态列 | `rerun_keeps_an_approved...`、`rerun_does_not_resurrect...`（2 failed） |
| T4b 重跑不再幂等（每次加 revision） | `_WRITE_BATCH` revision 列 | `rerun_keeps_an_approved...`（revision 3 ≠ 2）、`rerun_with_unchanged_candidates_is_idempotent`（revision 2 ≠ 1）（2 failed） |

每处篡改都是单独应用、跑测试、`git checkout --` 恢复；矩阵跑完后 `git status` 只剩文档改动。

## 风险 / 需 ArvinHan 签收

1. **R1 清扫缺省启用**：`sweep` 缺省每小时运行一次，`PUBLISH_SWEEP_INTERVAL_SECONDS=0` 才关闭。`sweep` 不删已提交版本与租约内尝试、可重复执行、逐课程隔离，故判定默认启用是安全的；若希望生产默认关闭，需要改缺省值。
2. **R4 契约新增响应形状**：一个操作两种成功对象。若产品更希望手工无来源节点走 404/其他语义、或坚持单一形状，需要另立决定；现状下「只有手工节点可以为空」写在服务端与测试里（契约 3.0 表达不了条件必填）。
3. **R4 详情对已发布副本的判定**：发布副本缺 `source` 属性时按 AI 口径处理（缺来源仍 500）。若认为发布副本应一律显示为空态，需要显式区分发布路径。
4. **R3 产品取舍**：重跑**会**改写「已裁决但已解锁」节点的内容与来源，只冻结 `approved`/`rejected` 状态。理由是 `unlock` 就是为了让自动流程重新更新内容（ADR-035 决定 4）；若要连内容一起冻结，需要新增「教师已裁决内容」图标记，本 ADR 未选。
5. 集成测试只用真实 Neo4j 5.26.31 与 fake 模型；`sweep` 的真实「每小时触发」未做端到端长跑，用可注入时钟 + 同一 `run_loop` 挂点验证（测试边界已写入 ADR-072 与本文）。

## 下一步

- 待 PR 审查/合并；四项可分别 revert。
- 未纳入本轮（保持原待决）：孤儿副本与「已提交版本缺副本」仍只告警（人工处理归 K10）；§8.6 的块检查点与失败任务来源块保留期清理仍未接入同一调度。
- `docs/tasks.md`「G05 待决」那一行的三项现已由 R1/R3 与本 PR 处理（无来源人工节点归 R4），合并后可在后续任务里更新该行。
