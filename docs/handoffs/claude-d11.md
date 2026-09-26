# Claude 交接：D11 实现解析阶段 worker 编排

- review_status: ready_for_review
- task_id: D11
- 分支：`claude/d11-parse-worker`
- base：认领提交 `6c50d2c`（main@`ddbeb82` + 第六批认领）；head：本交接所在提交
- 状态：DONE（待 PR 审查/合并）；已 push，未开 PR、未改 issue（协调方统一处理）

## 交付物

| 文件 | 内容 |
| --- | --- |
| `src/backend/app/workers/__init__.py` | 新包 `app.workers`，只有模块说明 |
| `src/backend/app/workers/parse_task.py` | `run_parse_stage(sqlite_url, lease, *, storage, max_attempts, target_chars=1500, overlap_chars=200) -> ParseOutcome`；`report_progress(sqlite_url, lease, progress) -> bool`；`parse_document(format, data)`；`LeaseHeartbeat`（心跳续约）；`run_once(settings, *, owner=None, storage=None) -> RunOnceResult`（运行一次入口）；常量 `PARSED_PROGRESS = 0.05`、`PDF_PARSER_VERSION = "pdf/1,cleanup/1,headings/1"` |
| `tests/backend/test_d11.py` | 42 个用例（参数化展开后） |

## 行为规则

输入：C09 `claim_next` 领到、处于 `parsing` 的任务（`Lease`）。输出：`ParseOutcome(status, task_id, stage, sse_event, revision_id, chunk_ids, chunks_inserted, error_code, not_before)`，`status ∈ {advanced, cancelled, failed, released, lost}`。

1. **阶段开头**：按 `id AND lease_token` 读任务行。读不到 → `lost`，不写任何数据。行的 `course_id`/`document_id` 与租约不符，或任务/租约不在 `parsing` → `ValueError`（调用方缺陷），不写。取消标志已为真 → 直接走检查点 T8，不读文件、不解析。
2. **解析**：`get_material(…, course_id=lease.course_id)` → `FileStorage.path_for(storage_name).read_bytes()` → 按 `materials.format` 分派：`txt`→D02，`markdown`→D03，`docx`→D04，`pdf`→D05 `extract_pdf` → D07 `clean_pages`（默认开启）→ D06 `to_sectioned_document`（D06/D07 交接要求的顺序）。
3. **分块与身份**：D08 `chunk_blocks(target_chars, overlap_chars)`；`RevisionKey(document_id=material.id, content_hash=materials.content_hash, parser_version=revision_parser_version(doc.parser_version, chunking_version(t, o)))`（ADR-018；内容哈希直接用 C05 落盘时的值，不重读重算，REVIEW-D01-R04）。0 块 → `DOCUMENT_UNREADABLE(no_text)`。
4. **阶段内进度**：检查点前上报 `0.05`，经 C08 `progress` 判定，低于当前值或超出 `parsing` 区间则不写（I2）；写入带令牌与 `progress <= 新值` 条件。
5. **检查点（同一事务）**：C09 `leased_transaction`（`BEGIN IMMEDIATE` + fence）内用 C08 `stage_done` 判定：
   - 标志为真 → T8：`UPDATE … SET stage='cancelled', lease_*=NULL WHERE id=? AND lease_token=? AND stage='parsing' AND cancel_requested=1`，**不写块**；`sse_event = "cancelled"`。
   - 否则 D10 `record_revision` + `put_chunks`（按块 ID 插入或忽略，已存在 ID 内容哈希/定位不一致即 `ChunkImmutableError`），再 T4：`UPDATE … SET stage='extracting', progress=max(旧值, 0.10) WHERE id=? AND lease_token=? AND stage='parsing' AND cancel_requested=0`；租约**继续持有**交给下一阶段；`sse_event = "stage"`。
   - 块与转换同一事务：未提交即全无，崩溃后接管从阶段开头重跑，得到同一批块 ID（§8.4 `parsing` 行）。
6. **失败**（写入同样在 `leased_transaction` 内、带令牌条件、清空租约，先经 C08 `fail` 判定）：
   - `DocumentUnreadableError` / 0 块 → T9 `DOCUMENT_UNREADABLE`，`details = {reason}`（`corrupted`/`encrypted`/`no_text`），固定中文消息；不重试（失败即终态，不可再领取）。
   - 存储不可用（读文件 `OSError`，SQLite `OperationalError`）→ C09 `release_after_transient_failure(code="STORAGE_UNAVAILABLE")`：未耗尽 → 释放、`not_before = 现在 + 30 s × 2^(attempt−1)`，`status = released`、`sse_event = None`；最后一次尝试 → T9 `STORAGE_UNAVAILABLE`，`details = {attempts, stage: "parsing"}`（LEASE-7）。
   - 其他异常（含 `ChunkImmutableError`、`ParseModelError`、资料缺失）→ T9 `INTERNAL_ERROR`，`details` 为空，消息固定；日志只记异常类型名，不记异常文本、堆栈或原文。
   - 取消标志已置但检查点前失败 → 照常 `failed`，`cancel_requested` 保持 1（TASK-7）。
7. **租约丢失**：任一带令牌写入（进度、检查点、失败）遇到 `LeaseLost` → 事务整体回滚，返回 `lost`，此后不再写任何数据；存储故障的释放遇到旧令牌同样返回 `lost`（LEASE-4）。
8. **心跳**：`LeaseHeartbeat` 独立线程每 `L/3` 调 C09 `renew_lease`；影响 0 行置 `lost` 并停止；SQLite 暂时报错则下个周期重试。心跳只延长租约，防旧写仍靠令牌条件。本阶段不写 Neo4j 与文件，§8.2「本地截止」无适用写入。
9. **`run_once`**：`reclaim_expired` → `claim_next`（`TASK_LEASE_SECONDS`、`TASK_MAX_ATTEMPTS` 取自 `Settings`）→ 若在 `parsing`，在心跳下跑本阶段。领到其他阶段的任务，或本阶段 `advanced` 后，用 C09 `release_on_shutdown` 交还（不计尝试次数），留给后续阶段（见风险 1）。不做守护进程。

### PDF 解析器版本（已由 ADR-018 修订 1 定稿）

ADR-018 修订 1（TD-01，#243）规定解析器段内步骤用 `,` 连接、按处理顺序排列，D06 给出 `pdf_headings.CLEANED_PARSER_VERSION = "pdf/1,cleanup/1,headings/1"`。worker 的 `PDF_PARSER_VERSION` 直接引用该常量，不再自拼（取值与原临时写法逐字相同，块 ID 不变）；修订键为 `pdf/1,cleanup/1,headings/1+chunk/1@1500-200`。清洗只用 D07 默认阈值。

## 测试覆盖（`tests/backend/test_d11.py`）

| 类别 | 用例 |
| --- | --- |
| 成功 | TXT、Markdown、DOCX、PDF 各一例（参数化）：到 `extracting`、`progress = 0.10`、仍持租约；块 ID 等于按 D08/D09 独立计算的值；修订的复合版本与内容哈希；PDF 块带页码、其余格式无页码有段落号。分块参数进入修订键（`txt/1+chunk/1@40-10`）。检查点前进度为 0.05 |
| 边界 | 提交前崩溃（`BaseException`）→ 无块无修订、仍 `parsing`；接管重跑（`attempt = 2`）得到相同块 ID。已存在同修订块时重跑不新增（`chunks_inserted = 0`，`created_at` 不变）。同资料第二个任务共享块。取消在开头生效（解析器未被调用）、在检查点生效（不写块）。低值进度不生效、超区间不生效、接管后已有 0.08 时 0.05 不生效。心跳续约与丢失检测、默认间隔 `L/3` |
| 失败 | 损坏（TXT 解码失败、坏 zip、坏 PDF）、加密（PDF `/Encrypt`、OLE 加密包）、无文本（空白 TXT/Markdown、空页 PDF）→ `DOCUMENT_UNREADABLE` + 对应 reason，不可再领取、回收不改写（TASK-14）。0 块 → `no_text`。文件缺失 → 释放退避；第 3 次尝试 → `STORAGE_UNAVAILABLE` + `{attempts: 3, stage: parsing}`（LEASE-7）。块写入时 `OperationalError` → 回滚并释放。未预期错误 → `INTERNAL_ERROR` 且不含原文/异常名。已存在 ID 异文 → `INTERNAL_ERROR`，原块不变 |
| 租约 | 开始前被接管、解析中被接管、进度已报后检查点前被接管、失败写入前被接管、释放前被接管 → 均 `lost`，新持有者令牌与数据不受影响（LEASE-4） |
| 隔离 | 伪造课程的租约 → `ValueError` 不写；块只落在本课程；他课程任务不受影响；非 `parsing` 租约被拒 |
| 运行一次 | 解析后交还（`attempt` 回到 0）；无任务；非 `parsing` 阶段交还；先回收（过期且已请求取消的任务转 `cancelled`）|

所有落库的失败都再用 C08 `apply_event(fail)` 交叉校验可被接受。

## 实际命令与结果

scratchpad 为多会话共享；本任务使用自有目录 `S=<scratchpad>/d11`：`python3 -m venv $S/venv && $S/venv/bin/pip install -e "src/backend[test]" 'datamodel-code-generator==0.26.3'`（Python 3.13.5）。每次运行 `PYTHONPATH=<worktree>/src/backend`、新的 `PYTHONPYCACHEPREFIX=$S/pyc-$RANDOM$RANDOM`、`-p no:cacheprovider`（封装在 `$S/pt.sh`、`$S/verify.sh`），并确认 `app` 解析到本 worktree 的 `src/backend/app/__init__.py`。

| 命令 | 结果 |
| --- | --- |
| 基线 `pytest tests/backend -q`（实现前） | `2105 passed, 1 warning` |
| 红灯 `pytest tests/backend/test_d11.py -q`（只有测试） | 收集错误 `ModuleNotFoundError: No module named 'app.workers'` |
| 绿灯 `pytest tests/backend/test_d11.py -q` | 首次实现即 `41 passed`；反向篡改发现 M1 未检出后补「检查点前被接管」用例，`42 passed` |
| `pytest tests/backend -q` | `2147 passed, 1 warning`（基线 2105 + 42） |
| `PATH=$S/venv/bin:$PATH ./scripts/verify.sh` | 退出码 0：`PASS contracts gate`、`Scaffold verification passed.` |
| `git diff --check`、`git diff --cached --check` | 无输出 |

## 反向篡改（脚本先 `cp` 备份，逐项改写后跑 `test_d11.py`，改回后 `cmp` 一致）

| # | 篡改 | 结果 |
| --- | --- | --- |
| M1 | 检查点事务不做 fence，读行与 T4 都不带令牌条件 | 首轮 `41 passed`（未检出）→ 补用例后 1 failed |
| M2 | 检查点忽略取消标志（总按 false 判定，T4 去掉 `cancel_requested = 0`） | 2 failed |
| M3 | `DOCUMENT_UNREADABLE` 写成 `INTERNAL_ERROR` | 9 failed |
| M4 | `LeaseLost` 后仍以不带令牌的 UPDATE 写失败 | 2 failed |
| M5 | 修订键混入尝试次数（重跑生成新块 ID） | 8 failed |
| M6 | 存储故障直接 `INTERNAL_ERROR`、不主动释放 | 3 failed |
| M7 | 进度上报不做单调与区间检查 | 2 failed |

七处改回后 `cmp` 一致，复跑 `42 passed`。附带发现：只去掉 T4 的 `lease_token` 条件（保留 fence）不可检出——`leased_transaction` 在 `BEGIN IMMEDIATE` 开头已 fence，事务内令牌不会被他人改写；T4 上的令牌条件保留作纵深防御。

## 接口 / 数据变更

- 新增包 `app.workers`（无 API、契约、迁移、配置变更）。块、修订、任务行都经已有 C09/D10 表写入。
- 新的持久化格式：PDF 修订的 `parser_version` 为 `pdf/1,cleanup/1,headings/1+chunk/1@…`（进入 `revision_id` 与块 ID，见待决 1）。

## 风险

1. **E12 合入前 `run_once` 会反复领取 `extracting` 任务**：`claim_next` 按创建时间最早优先，推进到 `extracting` 的任务交还后立即可领，下一次 `run_once` 又会领到它并交还，排在其后的 `queued` 任务得不到处理。当前没有守护循环，影响仅限手动调用；E12/K08 接入时应把「交还」改为在同一租约下继续 `extracting`。
2. **所有 `sqlite3.OperationalError` 都按存储不可用处理**：包括「no such table」这类程序缺陷，会先退避重试到尝试耗尽，再以 `STORAGE_UNAVAILABLE` 结束，而非 `INTERNAL_ERROR`。
3. **文件永久缺失也按临时故障处理**：会用完 3 次尝试（约 30 s + 60 s 退避）后才 `STORAGE_UNAVAILABLE`。
4. **不校验文件内容与 `content_hash` 一致**（遵循 REVIEW-D01-R04）：若磁盘文件被替换，块会记在旧哈希的修订下。
5. **大 PDF 无解析超时**：pdfminer 纯 Python，心跳能保住租约，但单个任务可能长时间占用 worker。
6. **SQL 在 workers 层**：T4/T8/T9/进度的条件更新与按令牌读行写在 `parse_task.py`，因为 `repositories/` 不在文件锁内（同 C10 待决 2）。
7. **共享 scratchpad**：会话开始时曾向共享的 `<scratchpad>/venv` 执行过一次 `pip install -e`（把 `app` 指向本 worktree），并覆写过一次共享的 `<scratchpad>/pt.sh`；发现共享后即改用自有 `d11/` 目录，之后未再碰共享文件。此期间使用共享 venv 的其他任务，其结果可能需要重跑确认。

## 待决（未擅自拍板）

1. ~~**PDF 管线版本格式**~~：已由 ADR-018 修订 1（TD-01，#243）定稿，worker 改为引用 `pdf_headings.CLEANED_PARSER_VERSION`。
2. **D07 清洗默认开启**：课程级或资料级开关（D07 待决 2）未实现。
3. **存储故障分类**（风险 2、3）：是否把「文件不存在」与 SQLite 非 I/O 类 `OperationalError` 改为 `INTERNAL_ERROR` 不重试。
4. **SSE 推送**：`ParseOutcome.sse_event` 给 C11；阶段内进度（0.05）的 `stage` 事件由 C11 决定是否按 `progress` 变化推送。
5. **失败/取消任务的块回收**：本阶段失败与取消都不留块（块与转换同事务、取消不写块），无需清理；其他阶段失败后的 `delete_task_chunks` 仍归 C09/K08 回收，且依赖 G02 的 `committed_revision_ids`（D10 待决 1）。
6. **修订完整性标记**（D10 待决 4）：本实现整修订一个事务写入，读方不会看到部分块，D11 侧不需要标记。
7. **K08**：守护循环、停止信号时 `release_on_shutdown`、启动时 `load_settings` 校验（LEASE-16）都未在本任务实现。

## 下一步

- **E12**：`run_parse_stage` 返回 `advanced` 时租约仍持有、`stage = extracting`、`progress = 0.10`；可在同一租约和心跳下直接进入抽取，块由 `store.list_chunks(course_id, revision_id=outcome.revision_id)` 或 `outcome.chunk_ids` 取得。
- **C11**：对 `cancelled`/`failed`/`advanced` 结果按 `sse_event` 推送；`released`、`lost` 无事件。
- **K08**：以 `run_once` 为循环体，补信号处理与回收周期。

## 回滚

纯新增文件：删除 `src/backend/app/workers/` 与 `tests/backend/test_d11.py`（或 revert 本提交）即可；无迁移。若已处理过 PDF 资料且待决 1 改了版本格式，旧修订与块保留、不受影响，新处理产生新修订。
