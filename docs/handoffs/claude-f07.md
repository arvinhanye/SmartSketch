# Claude 交接：F07 草稿图读取与详情服务

- review_status: ready_for_review
- task_id: F07
- 分支：`claude/project-thread-sqwla4`（#256 合并后从 `main@fa00164` 重开）
- 状态：DONE（待 PR 审查/合并）

## 交付物

| 文件 | 内容 |
| --- | --- |
| `src/backend/app/api/graph.py` | `GET /api/v1/courses/{cid}/graph`（`getGraph`）、`GET /api/v1/courses/{cid}/kp/{kid}`（`getKnowledgePoint`）；`graph_reader` 依赖首次使用时建 `Neo4jRepository` 并缓存在 `app.state` |
| `src/backend/app/services/graph/read.py` | `resolve_target`（读入口）、`read_graph`、`read_knowledge_point`、来源定位、层级计算 |
| `src/backend/app/repositories/graph_read.py`（扩围） | `GraphReader`：草稿按 V 过滤、已发布版本整读的节点/关系/来源关联/章节查询 |
| `src/backend/app/schemas/contracts.py`（扩围） | 导出 `GraphExchange`、`KnowledgePoint(Detail)`、`Relation`、`SourceRef` 等生成模型 |
| `src/backend/app/main.py`（扩围） | 注册路由 |
| `tests/backend/test_f07.py` | 20 个接口级用例（真实 SQLite + 假 `GraphReader`，响应按契约 JSON Schema 校验） |
| `tests/integration/test_f07_live.py` | 4 个真实 Neo4j 用例（草稿可见性、来源关联按任务过滤、发布副本与课程隔离、学生不可读草稿）；文件名加 `_live` 以免与后端同名模块冲突 |
| ADR-030、`docs/tasks.md` | 决定与看板 |

## 行为要点（ADR-030）

1. 教师不带 `version` → 草稿，V 从 SQLite 读一次；学生或教师带 `version` → 当前发布版本副本。
2. 空图 200；没有发布版本 404 `GRAPH_NOT_PUBLISHED`；`version` 不是当前发布版本号 404 `NOT_FOUND`；`version < 1`、非法 `type`/`relation_types` 422。
3. `level` 读取时按非 `rejected` 的 `PREREQUISITE` 最长路径计算，按整图而非过滤后的视图。
4. 过滤：先按 `chapter_id`/`type` 留节点，再留两端都在的关系，最后按 `relation_types` 过滤；`stats` 按返回内容统计。
5. 来源：知识点证据区间按 E05 的块文本拼接规则（复用 `services/ai/entities._layout/_sources_for`）找到解析块，取其 `page`/`section_path` 并带原文片段；关系按 `source_pairs` 中可见贡献方的块取第一个出处；不能定位的丢弃并记日志。知识点一条可定位来源都没有 → 500 `INTERNAL_ERROR`。
6. Neo4j 不可达 → 503 `STORAGE_UNAVAILABLE`。

## 命令与实际结果

`S=<scratchpad>`，`$S/pt.sh` 同 `claude-e12.md`；真实 Neo4j 用 `claude-f04.md` 记录的 Maven harness。

| 步骤 | 命令 | 结果 |
| --- | --- | --- |
| 接口级 | `$S/pt.sh tests/backend/test_f07.py -q` | 20 passed |
| 真实 Neo4j | `SMARTSKETCH_TEST_NEO4J_URI=bolt://127.0.0.1:7687 SMARTSKETCH_TEST_NEO4J_USER=neo4j SMARTSKETCH_TEST_NEO4J_PASSWORD=x $S/pt.sh tests/integration/test_f07_live.py -q` | 4 passed |
| 集成全量（真库） | 同上环境，`$S/pt.sh tests/integration -q` | 103 passed、4 skipped |
| 后端全量 | `$S/pt.sh tests/backend -q` | 2821 passed，1 个既有 warning |
| 契约与工具 | `$S/pt.sh tests/contracts tests/tooling -q` | 320 passed、3 failed；同样 3 个在未改动的 `main@fa00164` 上也失败（本机生成器环境问题，CI 不跑） |
| verify | `PATH=$S/venv/bin:$S/tools/node_modules/.bin:$PATH ./scripts/verify.sh`；`git diff --check` | exit 0；通过 |

测试与实现同轮写成，未单独留红灯记录；以下反向篡改代替红灯证明用例有效（每项都有用例失败）：

| # | 篡改 | 结果 |
| --- | --- | --- |
| T1 | 草稿节点查询不按 V 过滤 | 1 failed（live） |
| T2 | 草稿关系不要求两端可见 | 1 failed（live） |
| T3 | 来源关联不按 `task_id ∈ V` 过滤 | 1 failed（live） |
| T4 | 教师也读发布版本 | 11 failed |
| T5 | 定位忽略证据区间 | 1 failed |
| T6 | 关系来源不按 V 过滤 | 1 failed |
| T7 | 不校验 `version` | 1 failed |
| T8 | 层级计入 `rejected` 边 | 1 failed |
| T9 | 草稿不返回 `graph_version: null` | 4 failed |
| T10 | 详情邻居计入 `rejected` 边 | 1 failed |

## 数据与接口变更

- 新增两个已在契约中的操作的实现；无契约、迁移、环境变量或依赖变更。

## 待决 / 风险

1. 历史版本读取：G02 建版本表后，`version` 可读非当前版本。
2. 人工添加且无来源的知识点，详情接口会 500；F08 需保证新建知识点至少带一条来源，否则改契约。
3. `getKnowledgePoint` 每次整图计算层级（课程规模下可接受，G04 可在快照时预算）。
4. 复用了 `services/ai/entities` 的两个私有函数；若 E05 改块文本拼接，需同步。

## 回滚

撤销本提交即可；无数据变更。
