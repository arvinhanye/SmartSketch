# Claude 交接：G08 发布时补齐文本块向量

- review_status: ready_for_review
- task_id: G08（新增任务，ArvinHan 2026-09-26 同意）
- 分支：`claude/project-thread-sqwla4`；base：`main@a7d8075`
- 状态：DONE（待 PR 审查/合并）

## 交付物

| 文件 | 内容 |
| --- | --- |
| `src/backend/app/services/versions/chunk_vectors.py` | `index_chunks`、`verify_chunks`、`ChunkIndexResult` |
| `src/backend/app/services/versions/publish.py`（扩围） | P8 写副本前调用 `index_chunks`，P9 调用 `verify_chunks` |
| `tests/integration/test_g08.py` | 10 个用例，连真实 Neo4j 与迁移后的 SQLite（夹具取自 `test_g04.py`） |
| `specs/teacher-review-publish.md`、`docs/architecture.md`（扩围） | P8、P9、V8 与向量版本各一句 |
| ADR-047、`docs/tasks.md` | 决定与看板 |

## 验收对照

| 条目 | 用例 |
| --- | --- |
| 版本内全部文本块（包括未被引用的块）都有节点与向量 | `test_publish_indexes_every_chunk_of_the_version` |
| 已有向量不重算 | `test_already_indexed_chunks_are_not_embedded_again`、`test_index_chunks_is_idempotent_and_batches` |
| 版本外修订不处理 | `test_revisions_outside_the_version_are_left_alone` |
| J01 端到端可检索 | `test_published_chunks_are_found_by_j01` |
| 向量调用失败时指针不变 | `test_embedding_failure_fails_the_publish_and_keeps_the_pointer` |
| P9 核对 | `test_verify_catches_a_chunk_without_a_vector`、`test_wrong_dimensions_are_repaired_and_verified`、`test_node_with_a_vector_but_no_revision_is_repaired` |
| V12 空间 | `test_embedder_in_another_space_is_refused` |

## 命令与实际结果

`S=<scratchpad>`，`$S/pt.sh` 同 `claude-e12.md`；真实 Neo4j 用 `claude-f04.md` 记录的 Maven harness。

| 命令 | 结果 |
| --- | --- |
| `$S/pt.sh tests/integration/test_g08.py -q`（实现前） | 收集错误：模块不存在 |
| `$S/pt.sh tests/integration/test_g08.py -q`（带 Neo4j 环境变量） | 10 passed |
| `$S/pt.sh tests/backend -q` | 3102 passed |
| `$S/pt.sh tests/integration -q`（带 Neo4j 环境变量） | 343 passed、8 skipped |
| `PATH=$S/venv/bin:$S/tools/node_modules/.bin:$PATH ./scripts/verify.sh` | exit 0 |
| `git diff --check` | exit 0 |

反向篡改（每次恢复）：全部块重算（3 failed）；不查维度（1 failed）；不补 `revision_id`（补用例前存活，补 `test_node_with_a_vector_but_no_revision_is_repaired` 后 1 failed）；写入时不回填 `revision_id`（7 failed）；不查嵌入器空间（1 failed）；核对不报错（2 failed）；漏写最后一批（7 failed）；发布不调用 `index_chunks`（5 failed）；发布不调用 `verify_chunks`（1 failed）。

## 接口 / 数据变更

- 无契约、无迁移。Neo4j 中 `Chunk` 节点从「仅被引用的块」变为「已发布版本修订内的全部块」，并带当前空间向量属性；F14 迁移按 Neo4j 存量枚举，自然覆盖。

## 风险

- 首次发布要为课程全部文本块算一次向量，耗时与模型调用量随资料量增长；已有块只算一次。
- 本任务之前提交的版本没有文本块向量，回滚到它们时检索结果不全；重新发布一次即可补齐。
- CI 只跑 `tests/backend`，本任务用例在 `tests/integration`，依赖本地 Neo4j。

## 下一步 / 待决

- J04 接入：`resolve_published` → 问题向量 → J01 `search_chunks`（本任务保证发布版的块都可检索）。
- 课程规模上来后实测首次发布耗时，必要时把块向量提前到抽取阶段。
