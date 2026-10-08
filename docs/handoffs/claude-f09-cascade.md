# F09 扩展：删除知识点支持「连带删除会变成孤儿的后代」

- **task_id**：F09-CASCADE（`docs/tasks.md` 2026-10-08 条目）
- **agent**：Claude
- **base / head**：`pr-321@ab60183`（PR #321 图谱工作台）／工作区未提交
- **review_status**：`ready_for_review`（待独立复审）
- **决策记录**：ADR-092

## 任务与状态

用户在会话中提出「添加功能：可以删除单个知识点，并自动删除后续节点及关系」。两处取舍由用户逐项选择：

1. **级联与否每次由教师在确认弹窗里选择**（不做默认整批删除）；
2. **只跟随有向向下关系**——进一步限定为**只跟 `CONTAINS`**。`PREREQUISITE` 表示学习顺序而非归属，删掉一个前置知识不应连带删除依赖它的后续知识点，否则删「递归」会带走「二叉树遍历」等整条学习路径。

状态：**后端与前端功能均已完成并端到端验证**；门禁与集成测试未跑（见「未完成项」）。

## 改动文件

| 文件 | 变更 |
| --- | --- |
| `src/contracts/api.v1.yaml` | `deleteKnowledgePoint` 增 `cascade` 查询参数与 200 报告响应；新增 `GET /kp/{kid}/delete-impact`（`getKnowledgePointDeleteImpact`）；新增 schema `KnowledgePointDeletion`、`KnowledgePointDeletionNode` |
| `src/contracts/v1/generated/{openapi.json,python/models.py,typescript/openapi.d.ts}` | 重新生成（含 33 条路径） |
| `src/backend/app/repositories/graph_edit.py` | 新增 5 条 Cypher 与 6 个函数：`read_contains_reachable`、`read_contains_parents`、`read_draft_nodes_by_id`、`delete_draft_nodes`、`count_draft_relations_among`、`count_draft_relations_to_outside`；新增 `CASCADE_MAX_DEPTH = 12`、`CascadeNode`、`CascadePlan` |
| `src/backend/app/services/graph/delete_node_cascade.py` | **新增**：孤儿安全闭包、影响报告、`preview_deletion`、`delete_node_cascade` |
| `src/backend/app/api/graph_nodes.py` | `delete` 路由分流（`cascade=false` 仍走原 204 路径）；新增 `get_knowledge_point_delete_impact`；`_deletion_payload` |
| `src/backend/app/schemas/contracts.py` | 再导出两个新 DTO |
| `src/frontend/src/api/knowledgeDetail.ts` | `deleteImpact` / `remove`（`cascade` 走 `query`） |
| `src/frontend/src/composables/useNodeDeletion.ts` | **新增**：两步删除流程（先预览、再确认） |
| `src/frontend/src/components/NodeDeletionConfirm.vue` | **新增**：确认弹窗（影响预览 + 两个删除选项 + 保留原因） |
| `src/frontend/src/components/KnowledgeDetail.vue` | `allowDelete` 开关 + `delete` 事件（学生端不渲染） |
| `src/frontend/src/views/TeacherGraphView.vue` | 接线：详情面板入口 → 弹窗 → 刷新草稿图；删除成功文案区分是否级联 |
| `tests/backend/test_f09_cascade.py` | **新增**：14 个用例 |
| `docs/decisions.md` | ADR-092 |
| `docs/tasks.md` | F09-CASCADE 条目 |

## 关键决定

1. **只沿 `CONTAINS` 递归**，`PREREQUISITE` 不参与孤儿判定。用真实演示课程测量得出：`CONTAINS` 65 条、`PREREQUISITE` 1 条；若把后者算作父子，删一个基础概念会连带删掉大段后续课程。
2. **孤儿安全**：节点被删当且仅当它原有的 `CONTAINS` 父节点**全部**在待删集合里。实测「栈」的可达后代 19 个，其中「采」同时挂在「链队列」下（全局另有 2 个多父节点），因此「采」**保留**，并在报告的 `retained_parents` 里说明原因。若按「可达即删」，「采」会从「链队列」分支上消失。
3. **预览与删除共用同一个计划函数 `_plan`**，报告里的数量就是实际删除的数量，不会出现「说删 3 个、实际删 30 个」。
4. **缺省行为零变化**：`cascade` 缺省 `false` 时仍返回 204 无响应体，既有客户端与 ADR-048 的约定不受影响。
5. **预览也走课程写锁**（不写数据、不加草稿修订号），使其与随后的删除处于同一锁序；契约描述里写明「只读」。
6. **级联范围内不可见的节点同样删除**，否则会留下悬空边（与 ADR-048 第 2 条一致）。

## 已运行命令与**实际结果**

| 命令 | 实际结果 |
| --- | --- |
| `python scripts/check_contracts.py` | **PASS**：OpenAPI 3.1.0，33 条路径 / 131 个 schema / 394 处 `$ref`；不变量与命名基线均通过 |
| 复现 `gen-contracts.sh --check`（重新生成到临时目录 → 统一 LF → `filecmp` 递归比对，忽略 `__pycache__`） | **✓ 生成物与真源一致**；并确认 `delete-impact`、`KnowledgePointDeletion` 已进入 openapi.json、models.py、openapi.d.ts |
| `pytest tests/backend/test_f09_cascade.py -q` | **14 passed** |
| 真实演示课程上的 `GET /kp/{kid}/delete-impact` | **HTTP 200**：删「栈」→ 19 个知识点 / 21 条关系；`retained` 含「采 ← 仍挂在 ['链队列']」 |
| 同上，不存在节点 / 无令牌 | **404 `NOT_FOUND`** / **401** |
| `vue-tsc --noEmit` | **exit 0** |
| `node build-no-config.mjs`（受限环境下的构建入口） | **成功**，1391 模块 |
| 浏览器实测（Edge 无头 + CDP） | 详情面板出现「删除此知识点」；点击后弹窗渲染：标题「中缀表达式与后缀表达式」、摘要「会删除 10 个知识点、11 条关系」、按钮 `[删除并连带 9 个后代] [仅删此节点] [取消]` |

## API / 数据 / 配置变更

- **新增查询参数**：`DELETE /api/v1/courses/{cid}/kp/{kid}?cascade=true|false`（缺省 `false`）。`cascade=true` 时响应由 204 变为 **200** 并带 `KnowledgePointDeletion`。
- **新增接口**：`GET /api/v1/courses/{cid}/kp/{kid}/delete-impact` → `KnowledgePointDeletion`（只读）。
- **新 DTO**：`KnowledgePointDeletion`（`root_id`/`root_name`/`cascade`/`deleted_count`/`relation_count`/`nodes`/`retained`）、`KnowledgePointDeletionNode`（`id`/`name`/`depth`/`retained_parents`）。
- **无数据库迁移、无 Neo4j DDL、无新依赖、无环境变量**。删除仍只作用于草稿。

## 排查中发现的仓库约定与真实缺陷

1. **每条草稿 Cypher 必须字面引用 `$effective_task_ids`**，否则 `Neo4jRepository._parameters` 抛 `GraphScopeError: Cypher is missing required scope parameters`（既有的 `_TX_DELETE_NODES` 里那句看似多余的 `WHERE $effective_task_ids IS NOT NULL` 就是为此存在）。首版 4 条新语句因此 500。
2. **按 ID 读节点必须返回 `p` 字段形状**（`_TX_NODE_FIELDS`），否则 `read_draft_nodes_by_id` 抛 `KeyError: 'p'`。
3. **关系计数语义错误（已修）**：原先「逐节点汇总相接关系再扣内部边」的写法会把**保留**节点也算进集合，于是删除集与保留节点之间的边被当作内部边扣掉一次，`relation_count` 偏小。改为两个语义明确的函数：删除集内部边（`count_draft_relations_among`）+ 删除集到外部的边（`count_draft_relations_to_outside`）。
4. `client.request` 传查询参数用独立的 `query` 选项（`params` 只放路径参数）——生成类型不接受把 `cascade` 放进 `params`。

## 未完成项 / 风险 / 下一步

1. **`scripts/verify.sh` 未跑**（`basic` 与 `full`）。本机受限环境无法执行 Git Bash（`couldn't create signal pipe, Win32 error 5`），因此 `contracts.sh`、`backend.sh`、`frontend.sh` 三个阶段都只做了 Python 层等价复现。**必须由能跑 bash 的环境补跑**，尤其 `contracts.sh` 的 `gen-contracts.sh --check`（我已用 `filecmp` 等价复现为一致，但未跑真脚本）。
2. **`tests/integration/test_f09_cascade.py` 未写**：真 Neo4j 上的 `CONTAINS` 遍历、批量删除与关系身份清理尚无集成覆盖。当前真图验证只有只读预览与 404/401 路径——**真正执行级联删除尚未在真图上跑过**（只在单元测试的假 store 上验证过）。
3. **前端单测未跑**：本机 vitest 因仓库根缺 `node_modules` 而无法解析裸模块；`git stash` 对照确认改动前后同样失败，属既有环境问题，与本次改动无关。
4. **未做实际删除的浏览器验证**：弹窗与预览已实测，但为避免破坏演示数据没有点下确认按钮。
5. **深度上限 `CASCADE_MAX_DEPTH = 12`** 是防异常数据（环）的兜底；正常课程远小于此值，但若将来有更深的合法结构需要调大。
6. **无墓碑**：被删节点若被后续抽取任务再次写出，F04 会重建（同 ADR-048 的已知限制）。
7. 建议复审重点：`_orphan_safe_closure` 的收敛条件（`own and all(parent_id in doomed ...)` 中「`own` 为空则不删」是否处处符合预期）、`cascade=false` 分支是否确实与原实现逐字节等价、预览的 `retained_parents` 是否只反映**本次删除后**仍在的父节点。

## 回滚方式

删除 `src/backend/app/services/graph/delete_node_cascade.py`、`tests/backend/test_f09_cascade.py`、
`src/frontend/src/composables/useNodeDeletion.ts`、`src/frontend/src/components/NodeDeletionConfirm.vue`；
撤销 `graph_edit.py` 的新语句与新函数、`graph_nodes.py` 的新路由与 `_deletion_payload`、
`schemas/contracts.py` 的两行再导出、前端四个文件的接线；把 `api.v1.yaml` 回退到 ADR-048 状态后重新生成四类产物；
删除 ADR-092 与 `docs/tasks.md` 的 F09-CASCADE 条目。**无 SQLite 迁移、无 Neo4j DDL**，因此不需要数据回滚；
但已删除的草稿数据只能从备份恢复或由教师重建。
