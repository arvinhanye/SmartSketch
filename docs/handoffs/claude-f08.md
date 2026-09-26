# Claude 交接：F08 教师节点编辑与人工编辑锁

- **分支**：`claude/project-thread-z0m8yg`，base `main@ebb0f42`
- **决策**：ADR-035（待 ArvinHan 签收）

## 1. 交付物

| 文件 | 内容 |
| --- | --- |
| `src/backend/app/api/graph_nodes.py` | `createKnowledgePoint`（201）、`updateKnowledgePoint`（PATCH）、`unlockKnowledgePoint`；只做协议转换，PATCH 体逐字段校验（生成模型不拒绝多余字段与 `null`） |
| `src/backend/app/services/graph/edit_node.py` | 课程写锁（持有方 `edit`）→ 读 V → 校验 → `draft_revision + 1` → Neo4j 条件写入；`CourseBusy`、`RevisionConflict`、`InvalidEdit` |
| `src/backend/app/repositories/graph_edit.py` | `DraftNodeStore`（读节点、条件更新/解锁、新建人工节点与来源、章节可见性）；SQLite：加草稿修订号、锁持有方、可用来源块 |
| `tests/backend/test_f08.py` | 62 个用例：API + 真实 SQLite，Neo4j 用内存假存储 |
| `tests/integration/test_f08.py` | 3 个无服务器用例 + 5 个真实 Neo4j 用例（条件更新、可见性、F04 守锁与解锁后恢复、人工来源、章节） |
| 契约 | `KnowledgePointCreate.sources`（必填，≥1）、`KnowledgePointSourceInput`、`KnowledgePointUnlock`、`POST /kp/{kid}/unlock`、`ErrorCode.REVISION_CONFLICT`；`errors.v1.md` 一行；生成物由 `gen-contracts.sh` 重新生成 |

## 2. 验证

`S=<scratchpad>`；`$S/pt.sh` = `PYTHONPATH=src/backend PYTHONPYCACHEPREFIX=$S/pyc-$RANDOM $S/venv/bin/python -m pytest -p no:cacheprovider`，venv 按 `pip install -e "src/backend[test]" 'datamodel-code-generator==0.26.3'`；真实 Neo4j 用 `claude-f04.md` 记录的 Maven `neo4j-harness:5.26.0`。

| 步骤 | 命令 | 结果 |
| --- | --- | --- |
| 红灯 | 移走三个实现文件与路由注册后 `$S/pt.sh tests/backend/test_f08.py -q` | 61 failed, 1 passed |
| 绿灯 | `$S/pt.sh tests/backend/test_f08.py -q` | 62 passed |
| 集成 | `SMARTSKETCH_TEST_NEO4J_URI=bolt://127.0.0.1:7687 SMARTSKETCH_TEST_NEO4J_USER=neo4j SMARTSKETCH_TEST_NEO4J_PASSWORD=x $S/pt.sh tests/integration/test_f08.py -q` | 8 passed |
| 集成全量 | 同上，`tests/integration -q` | 123 passed, 4 skipped |
| 后端全量 | `$S/pt.sh tests/backend -q` | 3021 passed |
| 前端 | `npm --prefix src/frontend run type-check`；`npm --prefix src/frontend run test -- --run` | 通过；263 passed |
| 门禁 | `PATH=<openapi-typescript>:$S/venv/bin:$PATH ./scripts/verify.sh`（含 `gen-contracts.sh --check`） | exit 0 |

## 3. 接口与数据变更

- REST：新增 `unlockKnowledgePoint`；`createKnowledgePoint` 请求体新增必填 `sources`；新增错误码 `REVISION_CONFLICT`（409）。
- Neo4j：无 DDL。人工节点 `source = manual`、`contrib_manual = true`、`contrib_tasks = []`；其 `EVIDENCED_BY` 不带 `task_id`。教师修改与解锁都置 `contrib_manual = true`。
- SQLite：无迁移；每次成功写入 `courses.draft_revision + 1`，使用迁移 009 的 `course_locks`。

## 4. 风险与未完成

1. 前端需要为新建知识点选择来源块；目前只能用已知的 `chunk_id`（来自图谱 `source_refs` 或问答引用），没有按资料列块的接口。
2. 人工新建节点状态定为 `approved`、置信度 1.0，属 Claude 选择，待签收。
3. `REVISION_CONFLICT` 的 `details.current` 不含 `chapter_id` 与来源。
4. 与 PR #261（G04）都会追加 `docs/decisions.md` 与 `docs/tasks.md` 末尾，后合并的一方需解决该处冲突；G04 另给 `course_locks.py` 加了 `current_holder`，本任务在 `graph_edit.py` 里写了同样的查询以免改同一文件，两者合并后可收敛为一个。
5. 审计日志归 F12；删除（F09）与合并（F10）另行实现。

## 5. 下一步

F09 删除节点与关系清理、F10 合并与审核，然后 F12 审计日志。
