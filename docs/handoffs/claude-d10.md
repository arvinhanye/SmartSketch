# Claude 交接：D10 实现来源块持久化

- task_id: D10
- review_status: ready_for_review
- worktree: `/home/user/wt-d10-chunk-store`，分支 `claude/d10-chunk-store`
- base: `f0814cc`（第五批认领提交）
- 状态：实现与验证完成，待 PR 审查/合并（未 push、未开 PR、未改 issue）

## 改动文件

| 文件 | 说明 |
| --- | --- |
| `src/backend/migrations/007_chunks.sql` | 新表 `material_revisions`、`task_revisions`、`chunks`，索引、不可变与课程作用域触发器；文件头写明回滚步骤 |
| `src/backend/app/repositories/chunks.py` | 修订登记、块写入（幂等 + 不可变检查）、按课程隔离的读取、带删除保护的回收 |
| `tests/backend/test_d10.py` | 36 条测试 |
| `docs/handoffs/claude-d10.md` | 本文件 |
| `docs/tasks.md` | 仅「2026-09-25 第五批并行」D10 行的状态与证据列 |

无范围扩展；未新增依赖；未改其他文件。

## 数据模型（迁移 007）

| 表 | 主键 / 唯一 | 说明 |
| --- | --- | --- |
| `material_revisions` | PK `revision_id`；`UNIQUE(material_id, content_hash, parser_version)`；`UNIQUE(revision_id, course_id, material_id)` | 资料修订三元组 → `revision_id`（D09 派生）。FK `(course_id, material_id)` → `materials(course_id, id)`，`ON DELETE RESTRICT`。`parser_version` 须含 `+chunk/`（ADR-018 复合版本） |
| `task_revisions` | PK `(task_id, revision_id)` | 哪个任务产生了哪个修订；V3 发布集合第 1 条与 V2 删除保护都读它。FK `task_id` → `processing_tasks`；FK `(revision_id, course_id, material_id)` → `material_revisions`；插入触发器要求任务与修订同课程、同资料 |
| `chunks` | PK `chunk_id`；`CHECK (chunk_id = revision_id \|\| '-' \|\| ordinal)` | 原文 `text`、`text_sha256`、`section_titles`（JSON 数组）、`sources`（非空 JSON 数组：`block_ordinal/start/end/locator{page?, section_titles, paragraph?, line_start?, line_end?}`）。FK `(revision_id, course_id, material_id)` → `material_revisions` |

三表都有 `BEFORE UPDATE … RAISE(ABORT, '… immutable')` 触发器：库层也不允许改写已写入的块或修订。删除只经本仓储的回收函数。

## 接口（`app.repositories.chunks`）

| 函数 | 说明 |
| --- | --- |
| `record_revision(database, *, course_id, task_id, key: RevisionKey) -> RevisionRecord` | 在调用方事务内登记修订并关联任务，幂等。任务须属于该课程且 `document_id == key.document_id`，否则 `ChunkScopeError`；`parser_version` 非复合版本时 D09 抛 `ChunkIdentityError` |
| `put_chunks(database, *, course_id, revision_id, chunks: Sequence[SemanticChunk]) -> ChunkWriteResult` | 在调用方事务内按 D09 块 ID 写入 D08 块（`INSERT … ON CONFLICT DO NOTHING`）。修订须已在本课程登记（否则 `ChunkScopeError`）；序号须从 0 连续（否则 `ChunkIdentityError`）。已存在 ID：文本哈希不同 → `ChunkImmutableError`（PUB-30），哈希相同但定位（`section_titles`/`sources`）不同 → 同样拒绝；相同即计入 `existing` |
| `persist_revision_chunks(sqlite_url, *, course_id, task_id, key, chunks) -> (RevisionRecord, ChunkWriteResult)` | 上两者在一个 `BEGIN IMMEDIATE` 事务内完成；任一失败整批回滚 |
| `get_revision` / `list_material_revisions` / `list_task_revisions` | 按 `course_id` 限定的修订查询 |
| `get_chunk` / `get_chunks(chunk_ids)` / `list_chunks(material_id=?, revision_id=?)` | 按 `course_id` 限定的块查询；`get_chunks` 按请求顺序返回、去重、略去不存在或外课程 ID；`list_chunks` 至少给资料或修订之一，按 `(revision_id, ordinal)` 排序 |
| `delete_task_chunks(sqlite_url, *, course_id, task_id, committed_revision_ids) -> ChunkCleanupResult` | 回收 `failed`/`cancelled` 任务的来源块（§8.6 + V2 删除保护），见下 |

写函数在连接不处于事务中时抛 `RuntimeError`（与 C09 `fence` 同口径），保证拒绝时整批回滚。`StoredChunk.text` 不进 `repr`；错误信息只含 ID，不含原文。

**删除保护**：一个 `BEGIN IMMEDIATE` 事务内，对任务关联的每个修订——若有**其他**任务关联它且该任务不处于 `failed`/`cancelled`，或 `committed_revision_ids(connection, course_id)` 返回的集合含它，则整体保留、不做任何改动；否则删除其块与本任务的关联，修订行在无任何任务关联时一并删除。任务不属于该课程 → `ChunkScopeError`；任务不是 `failed`/`cancelled` → `ChunkDeleteRefused`；判定函数抛错 → 全部回滚。重复调用幂等。资料删除：`materials` 行被修订/块外键 `RESTRICT` 引用，无法删除。

## 验证（实际结果）

`<S>` = `/tmp/claude-0/-home-user-SmartSketch/f5e8fe9b-ebac-5377-b10c-8bfbef53bfde/scratchpad`，`V=<S>/venv`；每次运行前 `export PYTHONPYCACHEPREFIX=<S>/pyc-d10-$RANDOM`。

| 步骤 | 命令 | 结果 |
| --- | --- | --- |
| 红灯 | `PYTHONPATH=$PWD/src/backend $V/bin/python -m pytest tests/backend/test_d10.py -q -p no:cacheprovider`（仅有测试） | 收集错误 `ImportError: cannot import name 'chunks' from 'app.repositories'`，`1 error` |
| 绿灯 | 同上（实现后） | `36 passed` |
| 后端全量 | `... -m pytest tests/backend -q -p no:cacheprovider` | `1712 passed, 1 warning`（基线 1676 + 36；警告为既有 Starlette/httpx 弃用） |
| 契约与工具 | `PATH=$V/bin:<S>/b15-tools/node_modules/.bin:$PATH ... -m pytest tests/contracts tests/tooling -q -p no:cacheprovider` | `305 passed`（与基线相同）。不加 `b15-tools` 路径时 3 failed，均因缺 `openapi-typescript`，与本任务无关 |
| 门禁 | `PATH=$V/bin:<S>/b15-tools/node_modules/.bin:$PATH ./scripts/verify.sh` | exit 0（`PASS contracts gate`、`Scaffold verification passed.`） |
| 空白 | `git diff --check`；暂存后 `git diff --cached --check` | 无输出，exit 0 |

迁移测试只用临时目录：复制编号小于块迁移的全部迁移（及块迁移本身），按 `*_chunks.sql` 后缀定位块迁移，不写死 007、不断言真实迁移目录全集。

测试覆盖：迁移在已有数据上应用并留备份；文件头 `-- ROLLBACK:` 步骤执行后 schema 与迁移前逐项相同，且可再次迁移；库层拒绝 UPDATE、非规范块 ID、跨课程块、无出处块、跨课程任务关联；资料有修订时不可删除；修订 ID 与 D09 一致、登记幂等、跨课程/他资料任务被拒、非复合版本被拒；写函数须在事务内；原文、章节、出处往返一致且块 ID 与 `assign_chunk_identities` 相同；`repr` 不含原文；PUB-30 同任务重跑与他任务同内容再处理均不新增行（行内容逐列不变）、改文本被拒且同批新块未写入、同文本改定位被拒；PUB-29 解析器升级得新修订且旧块不变；PUB-28 换内容得新修订且旧块不变；未登记/外课程修订拒写；序号不连续拒写；按课程/资料/修订/ID 查询与课程隔离；删除保护各分支（失败/取消可删、与 `awaiting_review`/`completed`/`parsing`/`queued` 任务共享保留、仅与失败任务共享可删且修订行随最后一个关联删除、已提交版本保留且判定在同一事务内被调用、判定抛错不删、非终态任务拒删、跨课程拒删、幂等）。

### 反向篡改（先 `cp` 备份，改回后 `cmp` 均一致；每次换新 `PYTHONPYCACHEPREFIX`）

| 篡改 | 结果 |
| --- | --- |
| T1 `put_chunks` 去掉已存在 ID 的文本哈希比对 | 1 failed |
| T2 删除保护去掉「其他在用任务」判定 | 4 failed |
| T3 `get_chunk` 去掉 `course_id` 条件 | 1 failed |
| T4 删除保护忽略已提交版本判定 | 1 failed |
| T5 迁移去掉 `chunks_immutable` 触发器 | 1 failed |

## 数据变更与回滚

- 新增三表与索引、触发器；不改已有表。
- 回滚首选：停 API 与 worker，恢复 `backups/*-before-007.sqlite`（C01 迁移器自动生成并做 `integrity_check`）。
- 手工回滚（丢弃全部修订与块）：停 API 与 worker，在一个事务内执行迁移文件头 `-- ROLLBACK:` 四行（`DROP TABLE chunks; DROP TABLE task_revisions; DROP TABLE material_revisions; DELETE FROM schema_migrations WHERE filename LIKE '%_chunks.sql';`），已由测试验证可恢复原 schema 并可重新迁移。
- D-10：若合并前 main 已有 007，改号为新最大 + 1；测试按后缀定位，无需改测试；迁移文件头的编号说明随之更新。

## 风险

- 块原文存于 SQLite，是 Neo4j `Chunk` 节点（F03/F13 写入）的上游；两处必须用同一 `chunk_id`，Neo4j 侧的不可变检查仍需 F 组各自实现。
- 本表不做「修订块集已完整」的标记：`parsing` 从头重跑，同批写入在一个事务内，未提交即不可见；若 D11 分多个事务写同一修订，读方可能看到部分块（见待决 4）。
- 分块规则改了但忘记递增 `CHUNKER_VERSION` 时，同 ID 异文会被 `ChunkImmutableError` 拦截，任务在 `parsing` 失败（D09 交接已登记）。

## 待决

1. **已提交版本的修订列表**：版本表归 G02（表名未定），本任务以必填参数 `committed_revision_ids(connection, course_id)` 注入判定，无默认值。G02 合入后须提供实现（在同一连接上查本课程全部 `committed` 版本快照的 `revisions`）；G02 之前的调用方（C09/D11 回收）只能显式传入「空集」，须在 G02 合入时替换，否则会误删已发布引用的块。建议协调方在 G02 验收中登记此项。
2. **在途任务共享修订**：规格 V2/§8.6 只列 `awaiting_review`/`completed` 任务与已提交版本为保护条件。本实现更保守：任何**不处于 `failed`/`cancelled`** 的其他任务（含 `queued`、`parsing`、`extracting`、`merging`、`persisting`）关联该修订时也保留，否则会删掉正在处理同一修订的任务所依赖的块。请协调方确认后在规格中补注，或指示改回规格原文。
3. **修订内容哈希是否须等于 `materials.content_hash`**：架构规定 `content_hash` 唯一来源是 C05 `StoredFile.content_hash`；按 D-16，MVP 再处理即新资料，同一 `material_id` 不会换内容。本实现不强制二者相等（以便 PUB-28 在仓储层可测、并为将来的再处理端点留余地），由 D11 负责传入 `StoredFile.content_hash`。若要在仓储层强制，只需在 `record_revision` 加一次比对。
4. **修订完整性标记**：是否需要在 `material_revisions` 记录块数/完成标记，供 E/F 组判断修订块集完整，待 D11/F13 设计时决定（需新迁移）。
5. **仓储依赖服务模块**：`chunks.py` 引用 `app.services.chunk_identity`/`chunking`/`parsers.models` 的纯计算函数与数据类型（先例：C09 `task_leases` 引用 `services.task_state`）。若要严格 `services → repositories` 单向，需把这些类型下沉到 schemas，属跨任务调整。

## 下一步

- **D11**（parsing 编排）：在 C09 `leased_transaction(url, task_id, token)` 内：
  ```python
  t, o = target_chars, overlap_chars
  chunks = chunk_blocks(doc.blocks, target_chars=t, overlap_chars=o)
  key = RevisionKey(document_id=lease.document_id, content_hash=stored.content_hash,
                    parser_version=revision_parser_version(doc.parser_version, chunking_version(t, o)))
  revision = record_revision(db, course_id=lease.course_id, task_id=lease.task_id, key=key)
  put_chunks(db, course_id=lease.course_id, revision_id=revision.revision_id, chunks=chunks)
  ```
  整个修订在一个事务内写完；`ChunkImmutableError` 视为实现缺陷，任务按 §8.3 失败（错误码由 D11/C08 定）。E05 所需的 `ChunkIdentity` 由 `assign_chunk_identities(course_id, key, chunks)` 另行得到，块 ID 与本表一致（有测试）。
- **C09/D11 回收**：在删除块检查点的同一批次调用 `delete_task_chunks(..., committed_revision_ids=...)`（待决 1）。
- **G02/G 组**：发布集合第 1 条可由 `task_revisions` JOIN `processing_tasks` 取得有效任务的修订；并提供待决 1 的判定。
- **J01/问答检索**：按 `revision_id` 过滤后用 `get_chunks(course_id=…, chunk_ids=…)` 取原文与定位。
