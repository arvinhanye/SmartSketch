# Claude 交接：G08 遗留修复（向量索引、P9 核对、按版本补齐）

- review_status: ready_for_review
- task_id: G08-R1（关闭 #283 审查对 G08 / ADR-066 的遗留）
- 分支：`claude/project-thread-sqwla4`；base：`main@f2fbf1e`
- 状态：DONE（待 PR 审查/合并）
- 分工：补齐命令与其测试由并行子代理完成，主会话审读并纳入；其余由主会话完成。

## 交付物

| 文件 | 内容 |
| --- | --- |
| `src/backend/app/repositories/graph_migrations.py` | `ensure_current_vector_indexes(settings)`；`main()` 在约束迁移后调用 |
| `src/backend/app/services/versions/chunk_vectors.py` | `_missing` 按 SQLite 核对块身份；写入覆盖 `revision_id`/`document_id`；`verify_chunks` 要求索引 `ONLINE` |
| `scripts/backfill_chunk_vectors.py` | 按已提交版本补齐文本块向量；`--course`、`--version`、`--dry-run`；退出码 0/1/2 |
| `tests/integration/test_g08.py`（+4）、`tests/integration/test_g08_backfill.py`（15）、`tests/backend/test_g08_index.py`（4，CI 覆盖） | 用例 |
| `tests/integration/test_g04.py`、`tests/integration/test_k10.py` | 夹具按部署流程建 `fake/4` 向量索引 |
| ADR-055、规格 P9、`docs/integrations.md`、`src/backend/README.md`、`docs/tasks.md` | 决定、部署说明与看板 |

## 部署 / 运维

```bash
python -m app.repositories.sqlite && python -m app.repositories.graph_migrations   # migrate 步骤，现在也建向量索引
PYTHONPATH=src/backend python3 scripts/backfill_chunk_vectors.py --dry-run        # 统计缺向量的块
PYTHONPATH=src/backend python3 scripts/backfill_chunk_vectors.py                  # 补齐全部已提交版本；可随时重跑
```

## 命令与实际结果

`S=<scratchpad>`，`$S/pt.sh` 同 `claude-e12.md`；真实 Neo4j 用 `claude-f04.md` 记录的 Maven harness（`SMARTSKETCH_TEST_NEO4J_URI=bolt://127.0.0.1:7687`、`USER=neo4j`、`PASSWORD=x`）。

| 命令 | 结果 |
| --- | --- |
| 新用例（实现前） | 收集错误：`ensure_current_vector_indexes`、`scripts/backfill_chunk_vectors.py` 不存在 |
| `$S/pt.sh tests/integration/test_g08.py -q` | 14 passed |
| `$S/pt.sh tests/integration/test_g08_backfill.py -q` | 15 passed |
| `$S/pt.sh tests/backend/test_g08_index.py -q` | 4 passed |
| 删掉 `fake/4` 索引后跑 `test_g04.py -k first_publish` | 夹具改动前 1 failed（P9：索引缺失），改动后 1 passed |
| `$S/pt.sh tests/integration/test_k10.py -q` | 夹具改动前 12 failed（K10 清库会删索引，P9 拒绝），改动后 19 passed、1 skipped |
| `$S/pt.sh tests/backend -q` | 3223 passed、27 skipped |
| `$S/pt.sh tests/integration -q` | 370 passed、8 skipped |
| `PATH=$S/venv/bin:$S/tools/node_modules/.bin:$PATH ./scripts/verify.sh` | exit 0 |
| `ruff check`（改动文件）、`git diff --check` | 通过 |

反向篡改（每次恢复）：
- 主会话：不查索引（1 failed）；忽略索引状态（集成存活，补 `test_g08_index.py` 后 2 failed）；不查 `revision_id` 取值（1 failed）；不查 `document_id`（1 failed）；写入改回 `coalesce`（2 failed）；迁移不拒绝空间不符（1 failed）；迁移不建索引（1 failed）。
- 子代理：不按课程去重（1 failed）；不查版本空间（2 failed）；`--dry-run` 调用模型（2 failed）；忽略 `--version`（2 failed）；不查配置空间（1 failed）。

## 接口 / 数据变更

- 无契约、无 SQLite 迁移。部署的 Neo4j 迁移命令多建两个向量索引（`IF NOT EXISTS`，可重复执行）。
- 发布 P9 对缺索引的环境从「通过」变为「失败」：部署必须先跑 `graph_migrations`（docker `migrate` 已包含）。

## 风险

- 本地或其他环境若只跑过旧版迁移命令，升级后首次发布会在 P9 失败，提示重跑迁移。
- K10 用例清库时会删除所有索引；与其他集成用例并发运行时会互相干扰（本轮观察到），应串行运行。
- 补齐命令与发布的向量调用都不写 `model_calls`。

## 下一步 / 待决

- 部署后在已有数据的环境跑一次 `backfill_chunk_vectors.py`。
- 向量调用是否计入 `model_calls` 与预算（与 F14 口径对齐）待定。
