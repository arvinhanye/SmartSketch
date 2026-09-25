# Claude 交接：D09 实现块身份与缓存键

- task_id: D09（未改 issue、未建 PR、未 push：本会话 GitHub 写权限被拒）
- review_status: ready_for_review
- worktree: `/home/user/wt-d09-chunk-identity`，分支 `claude/d09-chunk-identity`
- base: `9116315`（第三批认领提交）
- head: `360c37b`（实现与测试）+ 本交接提交
- 状态：实现与验证完成，待 PR 审查/合并

## 改动文件

| 文件 | 说明 |
| --- | --- |
| `src/backend/app/services/chunk_identity.py` | 修订 ID、块 ID、块身份分配、抽取缓存键；纯计算，只用标准库与项目内模块 |
| `tests/backend/test_d09.py` | 96 条测试 |
| `docs/handoffs/claude-d09.md` | 本文件 |
| `docs/tasks.md` | 仅「2026-09-25 第三批并行（Claude）」D09 行的状态与证据列 |

未新增依赖，未改其他文件。

## 输入与输出

| 函数 | 输入 | 输出 |
| --- | --- | --- |
| `derive_revision_id(document_id, content_hash, parser_version)` | 资料修订三元组 | `rev_<64 位小写十六进制>` |
| `revision_id_for(key: RevisionKey)` | D01 `RevisionKey` | 同上 |
| `derive_chunk_id(revision_id, ordinal)` / `split_chunk_id(chunk_id)` | 修订 ID + D08 块序号 | `rev_<hex>-<序号>`；可拆回 `(revision_id, ordinal)` |
| `text_sha256(text)` | 块文本 | `sha256:<hex>`（与 `content_hash` 同格式） |
| `assign_chunk_identities(course_id, revision, chunks)` | 课程、`RevisionKey`、D08 `SemanticChunk` 序列 | `tuple[ChunkIdentity]`：`course_id`、`document_id`、`revision_id`、`chunk_id`、`ordinal`、`text_sha256`、`sources`（不带原文） |
| `extraction_cache_key(identity, *, prompt_purpose, prompt_version, prompt_sha256, model_id)` | 块身份 + E01 模板的 `purpose`/`version`/`sha256` + 模型 ID | `xc_<64 位十六进制>` |
| `cache_model_id(result: ModelResult)` | E02 调用结果 | 该次调用请求的模型 ID（`model_requested`） |

错误：违反前置条件抛 `ChunkIdentityError`（`ValueError` 子类，信息指出字段名与收到的值）；类型错误（非 `RevisionKey`/`SemanticChunk`/`ChunkIdentity`/`ModelResult`）抛 `TypeError`。

## 关键决定（依据）

1. **公式**（模块说明为准，测试含固定值）：
   - 规范编码 = `json.dumps(parts, ensure_ascii=False, separators=(",", ":"))` 的 UTF-8。用 JSON 数组区分字段边界，`("a|b","c")` 与 `("a","b|c")` 不会同 ID。
   - `revision_id = "rev_" + sha256(canon(["smartsketch.revision/1", document_id, content_hash, parser_version]))`。方案标签进哈希，将来改公式必须升标签。
   - 块 ID = `f"{revision_id}-{ordinal}"`，十进制、无前导零。ADR-012 修订 1 只写「`revision_id` + 块序号」，未要求再哈希；直接拼接可读、无碰撞、D10 可从块 ID 取出修订用于检索过滤。
   - 缓存键 = `"xc_" + sha256(canon(["smartsketch.extraction-cache/1", course_id, chunk_id, text_sha256, purpose, version, template_sha256, model_id]))`。
2. **修订 ID 不含 `course_id`**：规格公式为 `(material_id, 内容哈希, 解析器版本)`；`materials.id` 是 SQLite 全库主键（`003_tasks.sql`），同一文件传到两门课即两个资料 ID，修订与块 ID 不同。跨课程隔离另由缓存键中的 `course_id` 兜底（测试覆盖「上游误复用资料 ID 时缓存仍不跨课程命中」）。
3. **缓存键含块文本哈希**：块 ID 已决定文本（块不可变），多放一个哈希是防御：不可变被破坏时宁可不命中也不误命中。
4. **同文不同页**：身份按序号区分，每个 `ChunkIdentity` 带自己的 `sources`；缓存键含块 ID，因此同文不同处各自抽取、各自出处，不共享缓存。代价见「风险」。
5. **模型 ID 取「请求的」**：缓存查找发生在调用前，只能知道将要请求的模型；写入时用 `cache_model_id(result)` 即实际给出结果那次调用（主用或备用）所请求的 ID。备用给出的结果以备用 ID 入缓存，下次按主用查找不命中，会重算——偏保守。`model_responded` 可能为空或是别名展开，不进键。
6. **提示词三项全进键**：用途、版本号、模板 `sha256`。模板改了但忘记升版本也会失效（E01 已要求二者同步，此处是兜底）。
7. **校验**：`content_hash` 必须 `sha256:<64 位小写十六进制>`；`parser_version` 非空且不含任何空白；`document_id`/`course_id`/`model_id` 非空白字符串（与 `RevisionKey`、E02 `_check_model_id` 同口径）；序号为非 bool 的整数且 ≥ 0；块序号必须从 0 起连续；块必须有非空文本与至少一个出处；`prompt_purpose` 为小写标识符，`prompt_version` ≥ 1，`prompt_sha256` 为 64 位小写十六进制。`extraction_cache_key` 会复核 `ChunkIdentity` 内 `chunk_id` 与 `revision_id`/`ordinal` 一致。
8. **日志安全**：`ChunkIdentity` 不带原文，repr 不含文本（有测试）。

## 验证（实际结果）

| 步骤 | 命令 | 结果 |
| --- | --- | --- |
| 红灯 | `PYTHONPATH=$PWD/src/backend <venv>/bin/python -m pytest tests/backend/test_d09.py -q`（实现前） | 收集错误 `ModuleNotFoundError: No module named 'app.services.chunk_identity'`，`1 error` |
| 绿灯 | 同上（实现后） | `96 passed` |
| 后端全量 | `PYTHONPATH=$PWD/src/backend <venv>/bin/python -m pytest tests/backend -q` | `1146 passed, 1 warning`（基线 1050 + 本任务 96） |
| 门禁 | `PATH=<venv>/bin:$PATH ./scripts/verify.sh` | exit 1：`contracts gate` 中 B14 两条（`test_generation_is_byte_identical_across_two_runs`、`test_check_detects_missing_stage_and_regeneration_restores_it`）与负例 `test_gencheck_missing_stage_fails_in_every_locale` 失败，原因均为本机缺 `openapi-typescript`（无 `node_modules`）。在 base `9116315` 的临时 worktree 上同命令同样 exit 1，两份日志去掉时间与临时目录编号后逐行相同；契约门禁之前的所有检查通过。与本任务无关 |
| 空白 | `git diff --check` | 无输出，exit 0 |

`<venv>` = `/tmp/claude-0/-home-user-SmartSketch/f5e8fe9b-ebac-5377-b10c-8bfbef53bfde/scratchpad/venv`（未安装任何新包）。

### 反向篡改（每次先 `cp` 备份，改回后 `cmp` 与备份一致）

| 篡改 | 结果 |
| --- | --- |
| M1 缓存键去掉 `course_id` | 3 failed |
| M2 缓存键去掉 `model_id` | 3 failed |
| M3 块序号改为 4 位补零 | 28 failed |
| M4 修订哈希输入交换 `document_id` 与 `content_hash` | 2 failed |
| M5 `cache_model_id` 改取 `model_responded` | 1 failed |

五次改回后 `cmp` 均一致，最终工作区只有本任务文件。

## 接口 / 数据变更

- 新模块 `app.services.chunk_identity`，无 API、契约、迁移、配置变更。
- 本模块定义的块 ID 与修订 ID 格式一旦被 D10 持久化即成为数据格式；改公式须升方案标签并提供迁移。

## 风险

- **分块参数不在修订内**：块 ID = 修订 + D08 块序号，但 D08 的 `target_chars`/`overlap_chars` 与分块规则不在 `RevisionKey` 中。若只改分块参数或 D08 规则而 `parser_version` 不变，同一块 ID 会对应不同文本；D10 的不可变检查会拒绝写入（报错而非静默覆盖），缓存键因含文本哈希也不会误命中，但处理会失败。见待决 1。
- **同文不同处不共享抽取缓存**：重复段落各自计费一次。MVP 规模可接受。
- **别名模型**：`integrations.md` 已登记的风险依旧成立（ID 不变而行为变化时缓存不失效）。

## 待决

1. **分块版本归属**：D08 分块参数/规则变化是否应进入修订（例如 D11 把 `parser_version` 组合为 `pdf/1+chunk/1`，或 ADR 另加 `chunker_version` 字段）。本实现未改变规格公式，只在本文登记。需协调方在 ADR-012 或 `docs/architecture.md` D01 节定夺，D11 前。
2. **缓存键的模型 ID**（接 `claude-e02.md` 待决 2）：本实现取成功调用的 `model_requested`。若要改为 `model_responded`，只需改 `cache_model_id` 与一条测试，但查找时机需重新设计。建议协调方把此决定写入 `docs/integrations.md`「模型版本与向量空间」。
3. **fake 模式模型 ID**（接 `claude-e02.md` 待决 1）：缓存键要求非空 `model_id`；fake 模式由装配处（E03/E04）填固定 ID（如 `fake`），本模块不代填。
4. **除块文本外的提示词输入**：关系抽取、gleaning 等提示词若带块文本之外的变量（已抽实体列表、上一轮输出），这些变量不在缓存键中。E05/E06 若需要，应在本模块加一个显式的「附加输入哈希」参数（先改规格），而不是在调用方拼接进 `model_id` 或 `purpose`。
5. **跨修订复用抽取结果**：解析器升级后块 ID 全变，抽取缓存全部失效（保守）。若要按文本哈希跨修订复用，需要规格说明出处如何重新绑定。

## 下一步

- **D10**：写 `Chunk` 节点时用 `ChunkIdentity.chunk_id` 作唯一键、`revision_id` 作过滤属性、`text_sha256` 作不可变比对值（已存在 ID 且哈希不同即拒绝，PUB-30）；`split_chunk_id` 可从引用中的块 ID 取修订。
- **D11**：取 C05 `StoredFile.content_hash` 与解析器 `parser_version` 构造 `RevisionKey`，对 `chunk_blocks(...)` 的结果调用 `assign_chunk_identities(course_id, key, chunks)`。
- **E05**：查缓存前用 `PromptLibrary.get(purpose, version)` 的 `purpose`/`version`/`sha256` 与将要请求的模型 ID 算键；写缓存时用 `cache_model_id(result)` 重新算键后写入。E10 的合并裁决缓存（`specs/task-processing.md` §8.4 `merging` 行）键形不同，归 E 组，不复用本函数。

## 回滚

无破坏性修改；回滚即 revert 本分支两个提交。
