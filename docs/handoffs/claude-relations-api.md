# Claude 交接：F06-API 后端关系编辑接口（`/relations` 三个路由）

- `task_id`: F06-API（本任务新增编号；基于交接缺口「后端尚无 `/relations` 路由」，非 `docs/atomic-tasks.json` 既有条目）
- `review_status`: ready_for_review
- 分支：`claude/relations-0927`；`base_commit`: `ac21e5d`（origin/main）
- 目标 worktree：`.claude/worktrees/relations`（未动主仓与其他 worktree）
- 决策：ADR-071
- 依赖：F06 服务层（`apply_relations`、`derive_rel_id`）、F08 课程写锁与 `EditContext`、F12 审计（ADR-061）、契约 `api.v1.yaml` 的 `createRelation`/`updateRelation`/`deleteRelation` 与 `errors.v1.md`

## 交付物

| 文件 | 内容 |
| --- | --- |
| `src/backend/app/api/relations.py`（新增，文件锁） | 三条路由：`POST /relations`（201）、`PATCH /relations/{rid}`（200）、`DELETE /relations/{rid}`（204）；`operationId` 与契约逐字一致；`course_teacher` 依赖、错误码→HTTP 映射、PATCH 请求体逐字段校验（闭合可编辑集） |
| `src/backend/app/services/graph/edit_relation.py`（新增，文件锁） | `create_relation` / `update_relation` / `delete_relation`：课程写锁 → 读 V → 单事务（守卫锁、F06 校验与环检测、写入、审计 begin、读回真实图）；改类型/方向先删旧身份再写新身份，只改 `status` 就地改（保留 `source_pairs`），无变化时空操作 |
| `src/backend/app/repositories/graph_relation_edit.py`（新增，文件锁） | Cypher：`read_relation_detail`（按 `rel_id` 读一条可见关系，形状同 `GraphReader.edges`）、`delete_relation`（删关系与 `RelationIdentity`）、`retake_relation`（同身份改状态并接管为人工）；`DraftRelationStore`（`transaction` / `relation` / `node`） |
| `tests/backend/test_relations_api.py`（新增，文件锁） | 58 项：内存草稿图（逐条镜像 Cypher，校验/环检测/加锁/审计时序都是真代码）+ 真 SQLite + 真 app；覆盖契约形状、错误映射、鉴权、写锁、503、审计时序与 `reconcile` |
| `tests/integration/test_relations_api.py`（新增，文件锁） | 11 项：真实 Neo4j 5.26.31 + 真 SQLite；覆盖身份派生、先删后写的反向、来源证据与页码、关系身份删除、跨课隔离、`COURSE_BUSY` |
| `src/backend/app/main.py`（**扩围** 2 行） | 注册 `relations_router` |
| `src/backend/app/schemas/contracts.py`（**扩围** 2 行） | 从生成物导出 `RelationCreate`（PATCH 体仍按 `graph_nodes.py` 的做法逐字段校验，不导出 `RelationUpdate`） |
| `src/backend/app/services/graph/audit.py`（**扩围**） | 关系审计摘要（`relation_create_summary` / `relation_update_summary` / `relation_delete_summary`）、`_applied_relation`、`reconcile` 按摘要 `entity = "relation"` 分派、`_Store` 协议加 `relation` |
| `docs/decisions.md`、`docs/tasks.md`、`docs/architecture.md`、`specs/course-knowledge-graph.md` | ADR-071、F06-API 小节与待决、接线一句、状态行一句 |

## 行为要点

1. **写入路径复用 F06**：`apply_relations`（同一事务内的守卫锁、端点校验、重复关系、`check_candidates` 环检测、`MERGE`）。本模块只组合「先删旧身份 / 就地改状态」这一步，不另写一套关系写入。
2. **身份语义**：`rel_id = derive_rel_id(course, type, from, to)`。改 `type`/`from_id`/`to_id` → 同事务先删旧关系与旧身份再写新身份（`source = manual`，保留原 `confidence`/`status`）；只改 `status` → 就地改（`source = manual`、`contrib_manual = true`、修订号 +1），`source_pairs` 与贡献记录保留；目标状态与当前一致且已是人工 → 空操作。
3. **环检测**：新建与改向由 F06 完成；把 `rejected` 的 `PREREQUISITE` 恢复为有效时服务层用同一组读者重新验环（`rejected` 不参与环检测，恢复它等于重新加边，规格 DAG-7）。`PREREQUISITE` 自环 → 409 `CYCLE_DETECTED`（`[A, A]`）；其余类型自环 → 422 `self_loop`。
4. **拒绝不写、不记**：`audit.begin` 放在同一 Neo4j 事务内、写入语句之后，所以成环/悬空/重复这类写入前拒绝不加 `draft_revision`、不留审计行；`begin` 之后的失败由 `abort`/`reconcile` 收尾；`commit` 失败只记日志、行留 `pending`，编辑不回滚（ADR-061）。
5. **响应来自真实图**：写事务内 `read_relation_detail` 读回，外加 SQLite 文本块定位（`read._chunks` + `_source_ref`）拼 `source_refs`。
6. **审计行**：复用迁移 012 的 `create`/`update`/`delete` 动作（`action` 是数据库级 CHECK 闭集，新增取值要重建表），`kp_id` 列存 `rel_id`，两个修订号列为 NULL，靠摘要的 `entity = "relation"` 区分；`reconcile` 用摘要的 `after` 与图里当前状态逐项比对判生效。

## 验证（命令与实际结果）

| 命令 | 结果 |
| --- | --- |
| `PYTHONPATH=$PWD/src/backend .venv/bin/python -m pytest tests/backend/test_relations_api.py -q`（实现前） | **红灯**：`53 failed, 3 passed`（路由不存在，多数为 404） |
| 同上（实现后） | **58 passed** |
| `PYTHONPATH=$PWD/src/backend SMARTSKETCH_TEST_NEO4J_URI=bolt://localhost:17687 SMARTSKETCH_TEST_NEO4J_USER=neo4j SMARTSKETCH_TEST_NEO4J_PASSWORD=testpassword1 .venv/bin/python -m pytest tests/integration/test_relations_api.py -q` | **11 passed**（真实 Neo4j 5.26.31，容器 `ss-neo4j-f11`） |
| `PYTHONPATH=$PWD/src/backend .venv/bin/python -m pytest tests/backend -q` | **3281 passed, 27 skipped**（243.68s） |
| `… -m pytest tests/integration/test_f06.py test_f08.py test_f09.py test_f10.py test_f12.py test_f13.py test_relations_api.py -q`（同目录） | **126 passed**（F12 审计与 F08～F13 未被共享改动破坏） |
| `.venv/bin/python -m pytest tests/contracts -q` | **291 passed**（245.60s） |
| `./scripts/gen-contracts.sh --check` | **PASS**（`✓ 生成物与真源一致`；未改 `src/contracts/`） |
| `./scripts/verify.sh` | **exit 0**（`Scaffold verification passed`） |
| `git diff --check` | 干净（见提交前的最后一条命令输出） |
| 反向篡改矩阵（9 处，逐处单独改、跑两个测试文件、恢复） | **9/9 检出，0 存活** |

> 跑法注意：`tests/backend/test_relations_api.py` 与 `tests/integration/test_relations_api.py` 同名（与 F08/F09/F10/F12/F13 的既有约定一致），混跑会触发 pytest import mismatch，必须按目录分开跑；`.venv` 是 editable 安装、`app` 指向主仓，所有 Python 命令都要带 `PYTHONPATH=$PWD/src/backend`。

## 反向篡改矩阵

| # | 篡改 | 后端 58 项 | 集成 11 项 | 结论 |
| --- | --- | --- | --- | --- |
| T1 | `_apply` 里忽略 `check_candidates` 结果（等于去掉环检测） | 3 failed | 2 failed | 检出 |
| T2 | 成环响应不带 `details.cycle` | 3 failed | 1 failed | 检出 |
| T3 | 去掉课程写锁（不再 `course_locks.acquire`，也不再 `audit.reconcile`） | 5 failed | 1 failed | 检出 |
| T4 | `_body` 不回图拼响应（只回显身份三字段） | 4 failed | 4 failed | 检出 |
| T5 | 三条路由的依赖由 `course_teacher` 放宽为 `course_reader` | 3 failed | 1 failed | 检出 |
| T6 | 审计 `commit` 失败让请求失败（`raise`） | 1 failed | 0 | 检出（后端用例：失败仍须 201 且编辑保留） |
| T7 | `DELETE` 不校验关系是否存在 | 3 failed | 3 failed | 检出 |
| T8 | `_patch` 额外放行 `course_id` | 1 failed | 0 | 检出（后端用例：`extra_forbidden`） |
| T9 | 改向时不先删旧关系与身份 | 1 failed | 1 failed | 检出（旧边仍在 → 误报 409 成环） |

存活项：无。T1～T9 的篡改脚本在 `/tmp/tamper_f06api.py`（会话临时文件，未入仓），每处篡改跑完立即恢复源文件，恢复后重跑为 **58 passed + 11 passed**。

## 接口 / 数据变更

- 新增 HTTP：`POST /api/v1/courses/{cid}/relations`（201 `Relation`）、`PATCH /api/v1/courses/{cid}/relations/{rid}`（200 `Relation`）、`DELETE /api/v1/courses/{cid}/relations/{rid}`（204 无体）。
- 错误：401 `UNAUTHENTICATED`；403 `ROLE_FORBIDDEN` / `COURSE_FORBIDDEN`；404 `NOT_FOUND`；409 `CYCLE_DETECTED`（`details.cycle`）/ `DUPLICATE_RELATION`（`details.existing_id`）/ `COURSE_BUSY`（`details.holder`）；422 `VALIDATION_ERROR` / `DANGLING_ENDPOINT`（`details.missing`）；**503 `STORAGE_UNAVAILABLE`（契约未声明）**。
- 数据：不新增表、不新增迁移；关系写入沿用草稿（`version_id = "draft"`）与 `RelationIdentity`；审计行写入既有 `graph_edit_logs`（复用动作词）。
- 契约：**未改** `src/contracts/`（漂移门禁 PASS）。
- 配置：无新增环境变量。

## 未完成项 / 风险 / 下一位 Agent 的首个动作

1. **契约未声明 503**：三条路由沿用既有图路由惯例返回 503，`api.v1.yaml` 未声明；本任务不改契约真源 → 需 ArvinHan 裁决「补契约」还是「并入 500」。
2. **两个未登记的领域 `reason`**：非 `PREREQUISITE` 自环用 `self_loop`、`InvalidRelationError` 兜底用 `invalid_relation`；`errors.v1.md` 要求先登记，契约真源本轮冻结。
3. **改类型/方向丢弃 `source_pairs`**：新身份 = 新的人工断言（保留 `confidence`/`status`）；若要求改向后仍带 AI 证据，需搬移块 ID 到新身份的 `source_pairs`。
4. **审计行语义**：关系行的 `action` 复用节点动作、`kp_id` 存 `rel_id`、修订号列 NULL；若审计消费者要显式 `entity` 列，需另开迁移。
5. **前后端未联调**：H14 教师页仍注入假实现，真实 `/relations` 与页面组合未在浏览器端到端验证（K05 教师主线 E2E 的依赖）；本次只是把 H14 交接里的「仅假 API 验证」从**后端缺口**一侧关闭。
6. **下一位 Agent 的首个动作**：独立审查先复核 ADR-071 的两处签收项（503 与 `reason` 登记），再按 `docs/tasks.md` 的 F06-API 小节复跑「后端 58 + 集成 11 + 后端全量 + `verify.sh`」，并按上表重放 9 处篡改确认 0 存活。

## 回滚

撤销 `src/backend/app/api/relations.py`、`src/backend/app/services/graph/edit_relation.py`、`src/backend/app/repositories/graph_relation_edit.py`、`tests/backend/test_relations_api.py`、`tests/integration/test_relations_api.py`，以及 `main.py`（2 行注册）、`schemas/contracts.py`（2 行导出）、`services/graph/audit.py`（关系摘要、`_applied_relation`、`reconcile` 分派）中的增量。无迁移、无契约变更、无依赖升级；回滚后 H14 回到「仅假 API 验证」。
