# Claude 交接：G07 统一发布版本解析器

- review_status: ready_for_review
- task_id: G07
- 分支：`claude/project-thread-8wzxew`；base：`main@95d5c9a`
- 状态：DONE（待 PR 审查/合并）

## 交付物

| 文件 | 内容 |
| --- | --- |
| `src/backend/app/services/versions/resolver.py` | `resolve_published`、`PublishedVersion`、`VersionIntegrityError`、`clear_cache` |
| `tests/backend/test_g07.py` | 32 个用例，连迁移后的真实 SQLite，快照由 G01 `build_snapshot` 生成、版本由 G02 仓储提交 |
| `docs/decisions.md` ADR-037、`docs/tasks.md` | 决定与看板 |

## 用法（给 F07 / I 组推荐 / J 组问答）

```python
bound = resolve_published(sqlite_url, access.course.id, version=version)  # 请求开始时只调一次
reader.read(bound.graph_scope())            # Neo4j 读版本副本
chunks = [c for c in hits if bound.covers_revision(c.revision_id)]  # 问答：按修订过滤，不按 material_id
response.graph_version = bound.graph_version
# AccessDenied(404 GRAPH_NOT_PUBLISHED / NOT_FOUND) 照常映射；VersionIntegrityError → 500 INTERNAL_ERROR
```

## 验收对照

| 条目 | 用例 |
| --- | --- |
| 无发布版明确状态 | `test_never_published_course_is_graph_not_published`、`test_never_published_wins_over_an_explicit_version`、`test_in_progress_or_failed_attempts_do_not_count_as_published` |
| PUB-13 请求内不混读 | `test_pub13_a_request_bound_to_v1_keeps_v1_after_v2_commits`、`test_the_pointer_is_re_read_on_every_call_even_when_cached` |
| PUB-14（解析部分） | `test_pub14_explicit_committed_version_is_readable_while_pointer_is_elsewhere`、`test_pub14_missing_version_numbers_are_not_found[...]`、`test_another_courses_version_number_is_not_readable` |
| 图/问答/路径复用 | `test_one_result_serves_graph_path_and_qa`、`test_revision_list_is_cached_per_committed_version` |
| 课程隔离 | `test_courses_are_isolated`、`test_pointer_to_another_courses_cached_version_is_still_an_integrity_error` |
| V9 第 5 条不回退 | `test_pointer_to_a_non_committed_row_...`、`..._number_disagreeing_...`、`test_corrupt_snapshot_is_an_integrity_error[...]`、`test_snapshot_of_another_course_...`、`test_integrity_errors_are_not_cached` |

## 命令与实际结果（Linux，Python 3.11 venv）

```bash
python3 -m venv .venv && .venv/bin/pip install -e './src/backend[test]'
.venv/bin/python -m pytest tests/backend/test_g07.py -q     # 实现前：收集失败（模块不存在）；实现后 32 passed
.venv/bin/python -m pytest tests/backend -q                  # 2994 passed
# verify.sh 需要契约生成器：venv 内装 datamodel-code-generator==0.26.3、jsonschema、openapi-spec-validator，
# 另用 npm 装 openapi-typescript@7.4.4、typescript@5.9.3，均经 PATH 暴露
PATH=$PWD/.venv/bin:<tools>/node_modules/.bin:$PATH ./scripts/verify.sh   # exit 0
```

反向篡改 13 处：去掉摘要复核、快照课程复核、指针号复核、`BY_NUMBER` 的课程条件、未发布先判、缓存命中/写入、`covers_revision`、`graph_scope`、课程不存在分支，均被检出；去掉「版本行属于本课程」起初存活（快照课程复核兜住），补「他课版本已在缓存中」用例后检出。仍存活 2 处，均为冗余防护：指针行的 `state != 'committed'`（版本号为 NULL 与读快照时的 `state='committed'` 条件同样拦住）与 `BY_NUMBER` 的 `state='committed'`（G02 的 CHECK 保证非提交行版本号为 NULL）。

## 接口 / 数据变更

无契约、无迁移、无依赖变更。新增服务层函数，暂无调用方。

## 风险与待决

1. F07 `services/graph/read.py` 的 `resolve_target` 仍按访问层课程行判断，只能读当前发布版；改为调用本解析器即可读历史版本（PUB-14 的 F07 部分）。该文件不在 G07 范围内，建议由 F07 后续或路由任务接入。
2. 推荐（I 组）与问答（J 组）接入时须保证每个请求只解析一次，并把同一个 `PublishedVersion` 传到底层。
3. 修订列表缓存上限 256 为占位值；进程内缓存，多进程各自缓存（版本不可变，无一致性问题）。
4. `VersionIntegrityError` 目前没有全局异常映射，接入的路由需映射为 500 并记诊断信息。

## 下一步

G05（清扫）、G06（版本 API / 回滚 / `POST /publish`）由主线线程负责；本任务未触碰 `repositories/versions.py` 与 `publish.py`。
