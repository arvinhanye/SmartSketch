# Claude 交接：J02 图结构检索

- review_status: ready_for_review
- task_id: J02
- 分支：`task/j02`（本地，未 push）；base：`main@0b8aa73`
- 状态：DONE（待协调者汇总 / PR 审查）

## 交付物

| 文件 | 内容 |
| --- | --- |
| `src/backend/app/repositories/graph_search.py` | `search_subgraph`、`GraphSubgraph`、`SubgraphNode`、`SubgraphEdge`、`GraphEvidence` 与各上限常量 |
| `tests/integration/test_j02.py` | 24 个测试函数（参数化后 38 个用例），连真实 Neo4j；图用 G01 `build_snapshot` + G03 `materialize` 建成真实版本副本 |
| `docs/decisions.md`（扩围） | 末尾追加 ADR-050 |

未改 `docs/tasks.md`（由协调者汇总），也未改 J01 文件。

## 用法（给 J04）

入参风格与 J01 `search_chunks` 一致，都是 `(repo, scope, revision_ids, 查询, *, 上限…)`：

```python
bound = resolve_published(sqlite_url, course_id)               # G07，请求内只解析一次
graph = search_subgraph(repo, bound.graph_scope(), bound.revision_ids, [rewrite.query],
                        seed_kp_ids=[kp_id] if kp_id else ())   # H4
# graph.nodes: SubgraphNode(kp_id, name, aliases, type, definition, chapter_id, hops, matched)
#   种子在前，其余按跳数、kp_id；graph.seed_kp_ids 为实际种子
# graph.edges: SubgraphEdge(rel_id, type, from_id, to_id)，结果节点之间的四类关系
# graph.evidence: GraphEvidence(kp_id, chunk_id, revision_id, document_id)，已按修订列表过滤
# graph.truncated：任一上限截掉了内容；graph.empty：无匹配
```

J04 合并时，`graph.evidence` 的 `chunk_id` 可以与 J01 `ChunkHit.chunk_id` 去重后并入候选集合 H（Q1）。子图本身作为无编号的结构上下文；`graph.kp_ids` 可作为 `related_kp_ids` 的图检索部分。

## 规则（ADR-050）

- **种子**：名称或别名（去首尾空白、小写）与术语相等、包含在术语中，或包含某个至少 2 个字的术语，都算命中。排序为：显式种子 > 相等 > 名称在术语中 > 术语在名称中；同级按名称长者优先，再按 `kp_id`。不在本版本的 `seed_kp_ids` 忽略，并记 INFO 日志。
- **扩展**：无向逐跳扩展，缺省只沿 `CONTAINS`、`PREREQUISITE`、`RELATED_TO`（规格「前置/包含/相关」）；`EXAMPLE_OF` 须传 `relation_types` 开启。
- **上限**（占位值）：`max_hops` 2（硬上限 3），`max_nodes` 30（硬上限 200），`max_seeds` 为 `min(10, max_nodes)`，`max_evidence` 60（硬上限 500）。上限写在 Cypher `LIMIT` 中，多取 1 条用来判断是否截断。
- **作用域**：草稿作用域直接拒绝（`GraphScopeError`）。节点与关系都按 `(course_id, version_id)` 匹配。证据块另按修订列表过滤。

## 验收对照

| 条目 | 用例 |
| --- | --- |
| 跳数有上限 | `test_hop_limit_is_respected`、`test_bad_bounds_are_rejected[max_hops…]` |
| 节点数有上限 | `test_node_limit_truncates_deterministically`、`test_hub_expansion_stays_within_the_node_limit`、`test_limits_are_applied_in_the_query_not_after_fetching`、`test_seed_limit_truncates`、`test_evidence_limit_truncates` |
| 只返回同课程发布版 | `test_draft_other_versions_and_other_courses_never_come_back`、`test_draft_scope_is_refused`、`test_seed_kp_ids_outside_the_version_are_ignored`、`test_isolation_holds_with_many_terms_matching_foreign_names`、`test_evidence_is_filtered_by_the_version_revision_list`、`test_published_version_bound_by_g07_is_used_as_is` |
| 无匹配返回空 | `test_no_match_returns_an_empty_subgraph[…]`、`test_unpublished_version_id_returns_empty` |
| 匹配与结构 | `test_term_in_question_seeds_and_expands_within_two_hops`、`test_edges_are_the_induced_edges_of_the_returned_nodes`、`test_example_of_is_not_expanded_by_default_but_can_be_requested`、`test_aliases_match_case_insensitively`、`test_exact_term_beats_containment_and_short_terms_match_inside_names`、`test_shorter_names_rank_after_longer_ones`、`test_single_character_terms_do_not_match_inside_names` |

## 命令与实际结果

`S=<scratchpad>`，`$S/pt.sh` 为共享 venv 的 pytest 包装。真实 Neo4j 5.26 使用本任务专用端口：`SMARTSKETCH_TEST_NEO4J_URI=bolt://127.0.0.1:7688`、`USER=neo4j`、`PASSWORD=x`。

| 命令 | 结果 |
| --- | --- |
| `$S/pt.sh tests/integration/test_j02.py -q`（实现前，带 Neo4j 环境变量） | 收集错误：`No module named 'app.repositories.graph_search'` |
| `$S/pt.sh tests/integration/test_j02.py -q`（带 Neo4j 环境变量） | 38 passed |
| `$S/pt.sh tests/backend -q` | 3096 passed（与基线相同） |
| `$S/pt.sh tests/integration -q`（带 Neo4j 环境变量） | 257 passed、3 skipped、1 failed：`test_k08.py::test_images_build` 因拉取 Docker Hub 基础镜像返回 429 Too Many Requests 而失败，属于环境问题，与本任务无关 |
| `./scripts/verify.sh`（PATH 加入共享 venv 与 datamodel-codegen 工具目录） | `Scaffold verification passed.`，契约门禁 PASS |
| `git diff --check` | exit 0 |

反向篡改：脚本逐项修改 `graph_search.py`，跑 `test_j02.py -x`，最后恢复并逐字比对（`restored True`）。以下 13 处均被检出：

1. 种子查询不限版本；
2. 忽略 `max_hops`；
3. 扩展查询不带 `LIMIT`（只在应用层截断）；
4. 种子查询不带 `LIMIT`；
5. 证据块不按修订过滤；
6. 证据块不封顶；
7. 单字术语也匹配名称内部；
8. 匹配改为区分大小写；
9. 默认沿 `EXAMPLE_OF` 扩展；
10. 关系只要求一端在结果中；
11. 同级不按名称长度排序；
12. 节点截断不置 `truncated`；
13. 不校验跳数硬上限。

其中第 3、4 处在首轮存活，因为应用层切片会得到相同结果。补上 `CountingRepository` 断言每次读取的行数后，两处都被检出。

另有 2 处存活，均为冗余防护：

- 去掉草稿作用域检查：仓储的 `reader="student"` 同样拒绝草稿。
- 去掉空输入提前返回：空术语在查询中本就无命中，只多一次查询。

## 接口 / 数据变更

- 无契约、无迁移、无依赖变更，也没有新增 Neo4j 索引。新增仓储函数，暂无调用方（由 J04 接入）。

## 风险

- CI 只跑 `tests/backend`；本任务的用例全部在 `tests/integration`，依赖本地真实 Neo4j。
- 种子匹配要逐个扫描版本内的知识点（按 `(course_id, version_id)` 唯一约束的索引定位），没有全文索引。课程规模在数千点以内时开销可以接受，更大时需考虑全文索引。
- 子串匹配有误命中，如问题中出现「堆」「图」这类单字名称。种子排序会把单字名称放在最后，种子上限也能压低影响，但不能完全消除。
- 同一跳内按 `kp_id` 截断，与问题的相关度无关；枢纽节点被截断时，取到的邻居是按 ID 排在前面的。

## 待决

1. 占位上限（跳数 2、节点 30、种子 10、证据 60）待 J04 按 token 预算与评测确定。规格「待细化」中的「图谱扩展跳数」一项仍未签收。
2. 缺省不沿 `EXAMPLE_OF` 扩展，这是按规格「前置/包含/相关」的字面理解。例题节点对问答可能有用，是否开启由 J04 决定。
3. J03 只产出改写后的整句问题，没有关键词。J02 目前靠「名称在问题中」匹配；若以后增加关键词抽取，可以一并传入 `terms`。

## 下一步

- J04 合并 J01、J02 两路候选：证据块去重并入 H，子图作为无编号结构上下文，并补上 `related_kp_ids`。
- 同 J01 待决：运行时文本块缺向量的问题不影响 J02，因为 J02 的证据块经 `EVIDENCED_BY` 取得，不依赖向量。

## 回滚

撤销 `src/backend/app/repositories/graph_search.py`、`tests/integration/test_j02.py`，删除 `docs/decisions.md` 末尾的 ADR-050，以及本交接文件。无数据迁移，也无持久化状态。
