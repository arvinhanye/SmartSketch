# Claude 交接：F12 图编辑审计日志

- **任务**：F12（依赖 F08、F09、F10、C01，均已合入 main），issue #104
- **分支**：`claude/project-thread-21sjlj`，基线 `main@a7d8075`
- **决策**：ADR-061（待 ArvinHan 审阅）

## 1. 交付物

| 文件 | 内容 |
| --- | --- |
| `src/backend/migrations/012_edit_logs.sql` | `graph_edit_logs` 表（只追加；结束后冻结的触发器）、按课程与 `pending` 的索引；文件头 6 行 `ROLLBACK:` |
| `src/backend/app/repositories/edit_logs.py` | `begin`（同一事务 `draft_revision + 1` + 插入 `pending`）、`resolve`（只命中 `pending`，可重复）、`pending`、`list_logs`（按 `seq` 游标分页） |
| `src/backend/app/services/graph/audit.py` | 摘要构造（白名单 + `redact` 脱敏 + 截断）、`begin`/`commit`/`abort`（SQLite 失败退避重试，不抛错）、`reconcile`（持锁对账规则） |
| 扩围 `services/graph/edit_node.py` | `EditContext.actor_id`（可选）；`_course_write` 取锁后先 `audit.reconcile`；新建/修改/解锁以 `audit.begin` 取代 `bump_draft_revision`，经 `_write` 置 `committed`/`aborted` |
| 扩围 `services/graph/delete_node.py`、`merge_nodes.py` | 事务内的 `bump` 改为 `audit.begin`（带写前修订号与摘要）；事务抛错 `abort`，提交后 `commit`（删除补关系数，合并补重接/来源计数） |
| 扩围 `api/graph_nodes.py` | `_context`/`_run` 传入 `access.user.id` 作为 `actor_id` |
| `tests/backend/test_f12.py` | 30 个用例：经 API 的新建/修改/解锁审计、不写不记、课程隔离与分页、Neo4j 失败 `aborted`、重试成功、持续失败留 `pending` 后对账、崩溃后对账为 `aborted`、13 条对账规则、行冻结、`begin` 原子性、无 actor 不记、脱敏、迁移回滚重放 |
| `tests/integration/test_f12.py` | 8 个真实 Neo4j 用例：删除/合并审计字段、拒绝不记、合并直接父子与展平谱系、事务内失败 `aborted` 且图回滚、审计更新失败后下一次写入对账为 `committed` |
| 文档 | `docs/decisions.md` ADR-061；`docs/architecture.md` §206 一句；`specs/teacher-review-publish.md`「一致性」F12 落实；`docs/tasks.md` 本任务段 |

## 2. 接口/数据变更

- SQLite：新迁移 `012_edit_logs.sql`（编号按 D-10 取 main 最大 011 + 1；合并前若 main 已有 012 须改号，并同步改文件头的 `before-012` 与 ADR-061；测试按 `*_edit_logs.sql` 匹配，无需改）。
- REST/SSE 契约、Neo4j DDL、依赖：无变更。HTTP 行为不变（审计失败不改变响应）。

## 3. 验证

`V=/tmp/claude-0/venv/bin/python`（`pip install -e './src/backend[test]'`）；`N="SMARTSKETCH_TEST_NEO4J_URI=bolt://127.0.0.1:7687 SMARTSKETCH_TEST_NEO4J_USER=neo4j SMARTSKETCH_TEST_NEO4J_PASSWORD=x"`，Neo4j 为 Maven `org.neo4j.test:neo4j-harness:5.26.0` 在进程内起的服务（本环境无 Docker 守护进程、`dist.neo4j.org` 被代理拒绝）。`verify.sh` 需 `datamodel-codegen==0.26.3` 与 `openapi-typescript@7.4.4` 在 `PATH` 上。

| 步骤 | 命令 | 结果 |
| --- | --- | --- |
| 红灯 | 暂存实现后 `$V -m pytest tests/backend/test_f12.py -q` | 收集错误（`app.repositories.edit_logs` 不存在） |
| 绿灯 | `$V -m pytest tests/backend/test_f12.py -q` | 30 passed |
| 集成 | `$N $V -m pytest tests/integration/test_f12.py -q` | 8 passed |
| 回归 | `$V -m pytest tests/backend/test_f08.py -q`；`$N $V -m pytest tests/integration/test_f08.py tests/integration/test_f09.py tests/integration/test_f10.py -q` | 62 passed；52 passed |
| 后端全量 | `$V -m pytest tests/backend -q` | 3132 passed |
| 集成全量 | `$N $V -m pytest tests/integration -q` | 见下方补记 |
| 门禁 | `PATH=<工具>:$PATH ./scripts/verify.sh`；`git diff --check` | exit 0；无输出 |

反向篡改（逐处改实现、跑两份 `test_f12.py`、还原）16 处全部检出：去掉取锁后对账；去掉脱敏模式；`update` 对账只看修订号；`unlock` 对账恒为生效；去掉重试；删除/合并/编辑三处不 `abort`；合并 `pending` 摘要不带谱系；`resolve` 不限 `pending`；`delete` 对账恒为生效；API 不传 actor；去掉赋值脱敏；删除提交不补关系数。其中「删除不 abort」「合并 pending 摘要谱系」初次存活，已补 `test_failure_inside_the_delete_transaction_is_logged_as_aborted` 与对账用例的 `merged_from` 断言。

## 4. 风险与未完成

- 进程在 `begin` 后崩溃且之后该课程再无教师写入时，行一直是 `pending`（不影响图数据）；没有定时对账。
- 对账规则依赖「自动流程不改加锁节点」（F04/F13 的守锁）；若将来自动流程能改加锁节点，`update`/`merge` 的判定需改为在 Neo4j 写入标记。
- 脱敏是模式匹配，教师在定义里写入的其他敏感内容仍会记录；摘要字符串截断到 500 字符。
- 未覆盖：审计读接口；F06 关系编辑与 F11 审核操作的审计（对应路由/任务落地时调用 `audit.begin/commit/abort`）；发布与回滚按 ADR-034 不写本日志。

## 5. 回滚

`git revert` 本任务提交。数据库：停 API 与 worker，从 `backups/*-before-012.sqlite` 恢复，或在一个事务里执行迁移文件头部的 `ROLLBACK:` 行（丢失审计历史，先导出 `graph_edit_logs`）。无 Neo4j 数据或 DDL 变更。

## 6. 下一步

ArvinHan 签收 ADR-061；审计读接口与关系/审核操作接入审计另立任务。
