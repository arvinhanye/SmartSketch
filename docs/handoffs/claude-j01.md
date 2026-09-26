# Claude 交接：J01 发布来源向量检索

- review_status: ready_for_review
- task_id: J01
- 分支：`claude/project-thread-sqwla4`；base：`main@5ff441b`
- 状态：DONE（待 PR 审查/合并）

## 交付物

| 文件 | 内容 |
| --- | --- |
| `src/backend/app/repositories/vector_search.py` | `search_chunks`、`ChunkHit`、`DEFAULT_FETCH_FACTOR`、`DEFAULT_MAX_FETCH` |
| `tests/integration/test_j01.py` | 16 个用例，连真实 Neo4j |
| ADR-046、`docs/tasks.md` | 决定与看板 |

## 用法（给 J04）

```python
bound = resolve_published(sqlite_url, course_id)               # G07，请求内只解析一次
query = embedder.embed([question])[0]                          # 当前空间
hits = search_chunks(repo, bound.graph_scope(), bound.revision_ids, query, space=current_space(), limit=k)
# hits: ChunkHit(chunk_id, revision_id, document_id, score)，score ∈ [0, 1]，按相似度降序
# 阈值、可定位（page / section_path）和原文由 J04 结合 SQLite chunks 判断
```

## 验收对照

| 条目 | 用例 |
| --- | --- |
| 跨课 / 旧版本结果不进入候选 | `test_other_courses_and_revisions_outside_the_version_never_come_back` |
| 多取再过滤并补足召回 | `test_recall_is_topped_up_past_nearer_foreign_chunks` |
| 封顶告警、索引取尽不告警 | `test_fetch_cap_returns_what_it_has_and_warns` |
| 排序、条数、相似度口径 | `test_hits_are_ranked_limited_and_carry_their_revision` |
| 无命中 / 修订列表为空 | `test_no_match_or_empty_revision_list_is_empty` |
| 无本空间向量的块 | `test_chunks_without_a_vector_in_this_space_are_skipped` |
| V12 查询向量校验 | `test_bad_query_vectors_are_rejected_before_querying[...]` |
| 参数与作用域 | `test_bad_bounds_are_rejected[...]`、`test_draft_scope_is_refused`、`test_missing_index_for_the_space_is_a_repository_error` |

## 命令与实际结果

`S=<scratchpad>`，`$S/pt.sh` 同 `claude-e12.md`；真实 Neo4j 用 `claude-f04.md` 记录的 Maven harness（`SMARTSKETCH_TEST_NEO4J_URI=bolt://127.0.0.1:7687`、`USER=neo4j`、`PASSWORD=x`）。

| 命令 | 结果 |
| --- | --- |
| `$S/pt.sh tests/integration/test_j01.py -q`（实现前） | 收集错误：模块不存在 |
| `$S/pt.sh tests/integration/test_j01.py -q`（带 Neo4j 环境变量） | 16 passed |
| `$S/pt.sh tests/backend -q` | 3096 passed |
| `$S/pt.sh tests/integration -q`（带 Neo4j 环境变量） | 211 passed、6 skipped |
| `PATH=$S/venv/bin:$S/tools/node_modules/.bin:$PATH ./scripts/verify.sh` | exit 0 |
| `git diff --check` | exit 0 |

反向篡改（改 `vector_search.py` 后跑 `test_j01.py`，每次恢复）：去掉课程过滤（7 failed）；去掉修订过滤（2 failed）；不扩大取数（2 failed）；封顶不告警（1 failed）；不校验查询向量（3 failed）；不按 `limit` 截断（1 failed）；索引取尽仍继续扩大（1 failed）。存活 2 处，均为冗余防护：草稿作用域检查（仓储 `reader="student"` 同样拒绝草稿）；修订列表为空时提前返回（`IN []` 同样无结果，只省一次查询）。

## 接口 / 数据变更

- 无契约、无迁移、无依赖变更。新增仓储函数，暂无调用方（J04 接入）。

## 风险

- CI 只跑 `tests/backend`，本任务用例全部在 `tests/integration`，依赖本地真实 Neo4j。
- 向量索引为近似检索，相似度与精确余弦有约 1e-3 的误差。
- 他课文本块很多时每次问答可能多查几轮，最多 `max_fetch` 条；课程规模上来后需按实测调整占位值。

## 下一步 / 待决

- **运行时文本块没有向量**：F04/F13 持久化只建 `Chunk` 节点（仅被知识点引用的块），G03 只为知识点算向量，只有 F14 迁移会写文本块向量。J04 接上问答之前，需要在持久化时为全部文本块建节点并写当前空间向量，否则检索永远为空。建议单列任务，归属待定。
- `fetch_factor`、`max_fetch` 占位值由 J04 实测召回后确认（ADR-046）。
