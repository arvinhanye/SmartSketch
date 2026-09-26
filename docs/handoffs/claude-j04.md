# Claude 交接：J04 检索合并与上下文预算

- review_status: ready_for_review
- task_id: J04（issue #133）
- 分支：`claude/project-thread-ohmwyv`；base：`main@a7d8075`
- 状态：DONE（待 PR 审查/合并）

## 交付物

| 文件 | 内容 |
| --- | --- |
| `src/backend/app/services/qa/context.py` | `build_context`、`ContextBudget`、`EvidenceContext`、`EvidenceChunk`、`GraphContext`、`ContextStats`、`ContextStatus`、`ContextReason`、`utf8_token_estimate` |
| `tests/backend/test_j04.py` | 44 个用例，fake 检索结果、fake 文本块、fake 阈值与预算；不连数据库、不调模型 |
| ADR-065、`docs/tasks.md` | 决定与看板 |

## 用法（给 J05 / J06 / J07）

```python
bound = resolve_published(sqlite_url, course_id)                     # G07
hits = search_chunks(repo, bound.graph_scope(), bound.revision_ids, qvec, space=space, limit=k)   # J01
sub = search_subgraph(repo, bound.graph_scope(), bound.revision_ids, terms, seed_kp_ids=kp_ids)  # J02
ctx = build_context(
    course_id=course_id, revision_ids=bound.revision_ids, vector_hits=hits, subgraph=sub,
    load_chunks=lambda ids: get_chunks(sqlite_url, course_id=course_id, chunk_ids=ids),
    threshold=THRESHOLD, budget=ContextBudget(chunk_tokens=..., graph_tokens=..., max_chunks=...),
)
if not ctx.covered:        # meta(not_covered, retrieved=0) → done(ctx.reason)；不调用生成
    ...
prompt_evidence = ctx.render_evidence()   # "[n]（第p页；章节）\n原文\n\n" 逐块
prompt_graph = ctx.graph.text             # 无编号结构上下文
ctx.by_index(n)                            # J06 引用校验：n ∈ A 时返回块（chunk_id、document_id、page、section_path、text）
```

## 验收对照

| 条目 | 用例 |
| --- | --- |
| 去重保留出处 | `test_duplicates_merge_into_one_numbered_block_keeping_every_origin` |
| 空上下文 → `no_retrieval_hit`，不读块 | `test_no_candidates_is_no_retrieval_hit_without_reading_chunks`、`test_candidates_that_fail_q31_leave_h_empty_so_the_reason_is_no_retrieval_hit` |
| 低分 → `below_similarity_threshold`，阈值用 fake | `test_all_below_the_fake_threshold_is_below_similarity_threshold`、`test_threshold_is_inclusive_and_comes_from_the_caller` |
| 图证据不能单独打开闸门 | `test_graph_evidence_alone_cannot_pass_the_relevance_gate`、`test_graph_evidence_with_a_low_vector_score_stays_out` |
| Q3.1 三项条件以库为准（QA-17） | `test_q31_uses_the_stored_chunk_not_the_hit`、`test_foreign_outside_and_unlocatable_chunks_never_get_a_number` |
| 编号连续、排序确定 | `test_numbering_is_contiguous_from_one_in_context_order`、`test_ties_are_broken_by_chunk_id_and_graph_evidence_keeps_subgraph_order` |
| token 预算不截断定位（主验收第 8 条） | `test_budget_drops_whole_blocks_and_never_cuts_text_or_locator`、`test_token_count_covers_the_rendered_block`、`test_nothing_fitting_the_budget_is_not_covered_and_logged`、`test_max_chunks_caps_the_context` |
| 图谱上下文无编号、按行预算 | `test_graph_context_is_unnumbered_and_names_relations`、`test_graph_budget_drops_whole_lines_seeds_first`、`test_edges_to_dropped_nodes_are_not_rendered` |

## 命令与实际结果

`S=<scratchpad>`；`$S/venv` 为 `pip install -e './src/backend[test]'` 加 CI 的契约工具；`$S/tools` 为 `openapi-typescript@7.4.4`。

| 命令 | 结果 |
| --- | --- |
| `$S/venv/bin/python -m pytest tests/backend/test_j04.py -q`（实现前） | 收集错误：模块不存在 |
| `$S/venv/bin/python -m pytest tests/backend/test_j04.py -q` | 44 passed |
| `$S/venv/bin/python -m pytest tests/backend -q` | 3146 passed |
| `PATH=$S/venv/bin:$S/tools/node_modules/.bin:$PATH ./scripts/verify.sh` | exit 0 |
| `git diff --check` | exit 0 |

反向篡改（改 `context.py` 后跑 `test_j04.py`，每次恢复）21 处全部检出：课程、修订、可定位、读不到四项过滤；阈值含等号；图证据打开闸门；低分图证据进入 A；相似度取最大；知识点去重；预算遇大块停止而非跳过；去掉预算；去掉 `max_chunks`；预算放不下时仍判为可答；图谱定义不剔除类标记；图谱预算；关系排在节点之后；未知端点的关系；同分按 `chunk_id`；阈值范围校验；前置关系方向；子图 `truncated` 传递。

## 接口 / 数据变更

- 无契约、无迁移、无依赖变更。新增服务函数，暂无调用方（J05/J07 接入）。`services/qa/__init__.py` 未改，调用方从 `app.services.qa.context` 导入。

## 风险与待决

- 运行时尚无环节为文本块写向量（J01 待决，主线线程已向 ArvinHan 提出），接上前向量检索为空，问答总会拒答；本任务未补。
- 阈值与 `ContextBudget` 无缺省值，待 K01 调参、J07 配置。
- ADR-065 第 4 条（只有向量相似度能打开闸门）与第 5 条（预算放不下任何块时按 `below_similarity_threshold` 拒答）待签收。
- 渲染格式 `[n]（第p页；章节）` 是给 J05 提示用的草案，J05 可改渲染但须保持编号与 A 一致。

## 下一步

J05 用 `render_evidence()` 与 `graph.text` 组提示；J06 用 `by_index` 复核并构造 `citations`；J07 在 P5 按 `ctx.covered` 分支、`meta.retrieved = ctx.retrieved`。

## 独立审查修复（2026-09-26，协调者）

独立只读审查（worktree `review-j04`，带 `PYTHONPATH` 自证测的是本分支代码）结论 APPROVE_WITH_NOTES，已按「合并前必须修的项」处理：

1. **M1 接线示例错误（已修）**：`context.py` 的 `build_context` docstring 原写 `functools.partial(chunks.get_chunks, sqlite_url, course_id=...)`，但 `get_chunks` 的 `chunk_ids` 是 keyword-only，而 `build_context` 以位置参数调用 `load_chunks(ids)` → `TypeError`。已改为 `lambda ids: get_chunks(sqlite_url, course_id=course_id, chunk_ids=ids)`，与本交接的接线示例一致。
2. **①② 待签收文字（已落规格）**：ADR-065 决定 4 补写「闸门打开后无相似度的图证据块会获得编号并进入 A（可被引用），相对 Q1 字面是扩大」；决定 5 补写「预算 0 块复用 `below_similarity_threshold` 属 wire 语义合并，K03/J10 须另记 `over_budget` 分流，且不映射 `BUDGET_EXCEEDED`（那是 A07 的调用计费预算）」。同步写入 `specs/grounded-qa.md` Q3.1 与「待细化」，签收行改为明确列出这两点。
3. **审查记录但未在本任务修**（已写入 ADR-065「已知遗留」）：`kp_ids` 只取 J02 子图 evidence 内的知识点，覆盖面窄于 Q4 字面；测试全用 fake loader，未覆盖真实 `get_chunks` 的 keyword-only 接线（M4）；`over_budget` 同时统计 token 装不下与 `max_chunks` 截断；`revision_ids` 误传字符串按字符集合展开。交给 J06/J07 或后续技术债任务。
4. 审查独立复跑：`PYTHONPATH=$PWD/src/backend .venv/bin/python -m pytest tests/backend/test_j04.py -q` → 44 passed；后端全量 3146 passed；4 处独立反向篡改全部检出。

## 回滚

撤销上述两个源文件与本交接、ADR-065、`docs/tasks.md` 中 J04 一节；无数据变更。
