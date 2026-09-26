# Claude 交接：G01 快照序列化与摘要

- review_status: ready_for_review
- task_id: G01
- 分支：`claude/project-thread-sqwla4`（#258 合并后从 `main@608be90` 重开）
- 状态：DONE（待 PR 审查/合并）

## 交付物

| 文件 | 内容 |
| --- | --- |
| `src/backend/app/services/versions/snapshot.py` | `build_snapshot(DraftGraph) → SnapshotBuild(snapshot, excluded)`；`SnapshotBlocked(reasons)`（契约 `PublishBlockedReason`）；`canonical_bytes`、`digest_of`、`load_snapshot`；`SnapshotFormatError` |
| `src/backend/app/services/versions/__init__.py` | 新包 |
| `tests/backend/test_g01.py` | 49 个纯函数用例 |
| ADR-031、`docs/tasks.md` | 决定与看板 |

## 用法

G04 在 P4～P7 持课程写锁时读出**可见**草稿（同 F07：按 V 过滤节点、关系、章节与来源关联），加上 V 内任务的全部资料修订、本课程文本块的 `chunk_id → revision_id`，组成 `DraftGraph` 调 `build_snapshot`：

- 成功：`snapshot.canonical` 写入尝试行 `snapshot_json`，`snapshot.digest` 写 `digest`，`excluded.to_dict()` 写排除计数。
- `SnapshotBlocked`：409 `PUBLISH_BLOCKED`，`details = e.details()`。
- `SnapshotFormatError`：草稿数据损坏或实现缺陷，5xx。

G03 P8/P9 与回滚 R4 用 `load_snapshot(bytes)` 读回（只接受规范形态，读出即可复算摘要）。

## 命令与实际结果

`S=<scratchpad>`，`$S/pt.sh` 同 `claude-e12.md`。

| 步骤 | 命令 | 结果 |
| --- | --- | --- |
| 本任务 | `$S/pt.sh tests/backend/test_g01.py -q` | 49 passed |
| 后端全量 | `$S/pt.sh tests/backend -q` | 2870 passed，1 个既有 warning |
| verify | `PATH=$S/venv/bin:$S/tools/node_modules/.bin:$PATH ./scripts/verify.sh`；`git diff --check` | exit 0；通过 |

测试与实现同轮写成，以下反向篡改代替红灯（每项都有用例失败）：不排序键、转义非 ASCII、发布 `low_confidence` 节点、不连带排除、不查环、不查悬空端点、不查修订归属、不查谱系、集合数组不去重、接受非规范字节、章节不带祖先、空图不阻断（共 12 项）。

## 数据与接口变更

无契约、迁移、环境变量或依赖变更。

## 待决 / 风险

1. 装载可见草稿（Neo4j + SQLite 修订与块）归 G04。
2. 快照章节带 `parent_id`，Neo4j 章节与契约 `Chapter` 尚无此字段，目前恒为 `null`（ADR-031）。
3. 数值「原样输出」依赖 Python `repr`；跨语言复算摘要时需同样的最短浮点表示。

## 回滚

撤销本提交；无数据变更。
