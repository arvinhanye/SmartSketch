# Claude 交接：G03 版本图与向量构建

- review_status: ready_for_review
- task_id: G03
- 分支：`claude/project-thread-sqwla4`（与 G01、G02 同一 PR #259）；base：`main@608be90`
- 状态：DONE（待 PR 审查/合并）

## 交付物

| 文件 | 内容 |
| --- | --- |
| `src/backend/app/services/versions/materialize.py` | `embed_snapshot_nodes`（E07 向量）、`materialize`（P8，一个写事务先删后建）、`verify`（P9，读回复算摘要 + 向量核对）、`drop_version`（C1 第 2 步）、`node_embedding_text` |
| `src/backend/app/services/graph/read.py`（扩围） | 版本副本关系读 `source_refs`；已发布版本补齐契约必填字段（忽略投影返回的 `null`） |
| `src/backend/app/repositories/graph_read.py`（扩围） | 节点查询改为显式投影，不回传向量属性 |
| `tests/integration/test_g03.py` | 12 个用例（11 个连真实 Neo4j），含经 F07 服务读回副本 |
| `tests/backend/test_f07.py`（扩围） | 1 个用例：版本副本按已发布读取，草稿不补默认值 |
| ADR-033、`docs/tasks.md` | 决定与看板 |

## 给 G04 的用法

```python
vectors = embed_snapshot_nodes(adapter, build.snapshot)          # P4/P7 前后皆可；按空间+文本缓存
materialize(repo, build.snapshot, attempt.version_id, vectors, sqlite_current_space(url))   # P8
verify(repo, build.snapshot, attempt.version_id, current_space)  # P9；VerificationError → C1
# C1：versions.fail_attempt(...) 成功后 drop_version(repo, cid, attempt.version_id)；失败 set_cleanup_pending
```

## 命令与实际结果

`S=<scratchpad>`，`$S/pt.sh` 同 `claude-e12.md`；真实 Neo4j 用 `claude-f04.md` 记录的 Maven harness。

| 步骤 | 命令 | 结果 |
| --- | --- | --- |
| 本任务 | `SMARTSKETCH_TEST_NEO4J_URI=bolt://127.0.0.1:7687 SMARTSKETCH_TEST_NEO4J_USER=neo4j SMARTSKETCH_TEST_NEO4J_PASSWORD=x $S/pt.sh tests/integration/test_g03.py -q` | 12 passed |
| F07 回归 | `$S/pt.sh tests/backend/test_f07.py -q` | 21 passed；新用例在去掉「忽略 null」修正时失败（端到端用例先发现：投影返回的 `null` 覆盖了默认值，所有已发布节点被丢弃） |
| 后端全量 | `$S/pt.sh tests/backend -q` | 2893 passed |
| 集成（真库） | 同上环境，`$S/pt.sh tests/integration -q` | 115 passed、4 skipped |
| verify | `PATH=$S/venv/bin:$S/tools/node_modules/.bin:$PATH ./scripts/verify.sh`；`git diff --check` | exit 0；通过 |

反向篡改：不先删旧副本、不核对向量空间、不核对写入条数、P9 不比摘要、P9 不查向量、缺向量跳过、副本带 `status`——均有用例失败；`drop_version` 去掉草稿拒绝时仍被 F02 作用域校验拦下（草稿写入必须带 V），无用例失败。

## 数据与接口变更

- Neo4j：新增版本副本（节点/关系按 `(course_id, version_id)`），无新 DDL；向量属性沿用 F03 的 `embedding_<suffix>`。
- 无 REST/SSE 契约、SQLite、环境变量或依赖变更。

## 待决 / 风险

1. 已决（ArvinHan 2026-09-26）：已发布知识点对外 `status` 恒为 `approved`、`source` 恒为 `manual`（ADR-033 第 5 条）。
2. 已发布版本的知识点详情来源没有原文片段（副本无证据区间）。
3. 向量索引由 F03 `ensure_vector_indexes` 建立，本任务不建索引。
4. 大课程时单事务写入的内存占用未压测。

## 回滚

撤销本提交；已物化的版本副本用 `drop_version` 或 `MATCH (n {course_id: $c, version_id: $v}) DETACH DELETE n` 删除。
