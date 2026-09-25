# Claude 交接：D09 实现块身份与缓存键

- task_id: D09（PR #226，未合并；ADR-018 追加由子代理本地提交，未 push、未改 PR/issue）
- review_status: ready_for_review
- worktree: `/home/user/wt-d09-chunk-identity`，分支 `claude/d09-chunk-identity`
- base: `9116315`（第三批认领提交）
- head: `360c37b`（实现与测试）+ `77c98cd`（交接）+ ADR-018 追加：`686f57c`（ADR-018 本文）与其后的实现提交
- 状态：实现与验证完成（含 ADR-018 追加），待 PR 审查/合并

## 改动文件

| 文件 | 说明 |
| --- | --- |
| `src/backend/app/services/chunk_identity.py` | 修订 ID、块 ID、块身份分配、抽取缓存键；纯计算，只用标准库与项目内模块 |
| `tests/backend/test_d09.py` | 154 条测试（初版 96 + ADR-018 追加 58） |
| `src/backend/app/services/chunking.py` | ADR-018 追加（范围扩展，ADR-018 授权）：`CHUNKER_VERSION`、`chunking_version()`；参数校验抽为共用函数，`chunk_blocks` 行为不变 |
| `docs/decisions.md` | ADR-018 本文（协调方撰写，原样提交于 `686f57c`） |
| `docs/architecture.md`、`specs/teacher-review-publish.md` | 「资料修订」各补注复合版本（ADR-018） |
| `docs/handoffs/claude-d09.md` | 本文件 |
| `docs/tasks.md` | 仅「2026-09-25 第三批并行（Claude）」D09 行的状态与证据列 |

未新增依赖，未改其他文件；`tests/backend/test_d08.py` 未改。

## 输入与输出

| 函数 | 输入 | 输出 |
| --- | --- | --- |
| `chunking.chunking_version(target_chars=1500, overlap_chars=200)`（D08） | 本次实际分块参数 | `chunk/1@1500-200`（`f"{CHUNKER_VERSION}@{target}-{overlap}"`）；参数非法抛 `ValueError`，信息与 `chunk_blocks` 相同 |
| `revision_parser_version(parser_version, chunking_version)` | 解析器 `PARSER_VERSION` + 分块版本 | `f"{parser_version}+{chunking_version}"`，如 `pdf/1+chunk/1@1500-200`；解析器段须非空、无空白、无 `+`，分块段须匹配 `chunk/<规则版本>@<正整数>-<非负整数>`（规则版本无空白、`@`、`+`；数字仅 ASCII、无前导零），否则抛 `ChunkIdentityError`（信息含字段名 `parser_version` 或 `chunking_version`） |
| `derive_revision_id(document_id, content_hash, parser_version)` | 资料修订三元组（`parser_version` 须为复合版本） | `rev_<64 位小写十六进制>`；不含合法分块段时抛 `ChunkIdentityError`（信息含 `parser_version`） |
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
7. **校验**：`content_hash` 必须 `sha256:<64 位小写十六进制>`；`parser_version` 必须是复合版本（按第一个 `+` 拆分：解析器段非空、无空白；分块段匹配上述格式，因此多余的 `+` 或缺分块段均被拒绝），`derive_revision_id`、`revision_id_for`、`assign_chunk_identities` 三个入口共用同一校验；`document_id`/`course_id`/`model_id` 非空白字符串（与 `RevisionKey`、E02 `_check_model_id` 同口径）；序号为非 bool 的整数且 ≥ 0；块序号必须从 0 起连续；块必须有非空文本与至少一个出处；`prompt_purpose` 为小写标识符，`prompt_version` ≥ 1，`prompt_sha256` 为 64 位小写十六进制。`extraction_cache_key` 会复核 `ChunkIdentity` 内 `chunk_id` 与 `revision_id`/`ordinal` 一致。
8. **日志安全**：`ChunkIdentity` 不带原文，repr 不含文本（有测试）。
9. **复合版本（ADR-018）**：修订 ID 公式、方案标签 `smartsketch.revision/1` 与块 ID 公式均未改，只是 `parser_version` 输入改为复合版本。固定值测试的输入由 `pdf/1` 改为 `pdf/1+chunk/1@1500-200`，期望值随之重算：`rev_228fb4b5…ab4e`（原 `rev_2a6650fb…afb0`），缓存键 `xc_8395acd0…20ac`（原 `xc_a94e56b1…833c`）；新值由测试外的独立 `hashlib` 脚本按公式算出，同一脚本对旧输入仍算出旧值。D10 尚未持久化任何块，不涉及迁移。

## 验证（实际结果）

| 步骤 | 命令 | 结果 |
| --- | --- | --- |
| 红灯 | `PYTHONPATH=$PWD/src/backend <venv>/bin/python -m pytest tests/backend/test_d09.py -q`（实现前） | 收集错误 `ModuleNotFoundError: No module named 'app.services.chunk_identity'`，`1 error` |
| 绿灯 | 同上（实现后） | `96 passed` |
| 后端全量 | `PYTHONPATH=$PWD/src/backend <venv>/bin/python -m pytest tests/backend -q` | `1146 passed, 1 warning`（基线 1050 + 本任务 96） |
| 门禁（初版） | `PATH=<venv>/bin:$PATH ./scripts/verify.sh` | exit 1：`contracts gate` 中 B14 两条（`test_generation_is_byte_identical_across_two_runs`、`test_check_detects_missing_stage_and_regeneration_restores_it`）与负例 `test_gencheck_missing_stage_fails_in_every_locale` 失败，原因均为本机缺 `openapi-typescript`（无 `node_modules`）。在 base `9116315` 的临时 worktree 上同命令同样 exit 1，两份日志去掉时间与临时目录编号后逐行相同；契约门禁之前的所有检查通过。与本任务无关 |
| 空白 | `git diff --check` | 无输出，exit 0 |

### ADR-018 追加的验证

| 步骤 | 命令 | 结果 |
| --- | --- | --- |
| 红灯 | `PYTHONPATH=$PWD/src/backend <venv>/bin/python -m pytest tests/backend/test_d09.py -q`（先改测试，实现前） | 收集错误 `ImportError: cannot import name 'revision_parser_version'`，`1 error` |
| 绿灯 | `... -m pytest tests/backend/test_d09.py tests/backend/test_d08.py -q` | `167 passed`（D09 154 + D08 13） |
| 后端全量 | `... -m pytest tests/backend -q` | `1204 passed, 1 warning`（初版 1146 + 58） |
| 门禁 | `PATH=<venv>/bin:<scratchpad>/b15-tools/node_modules/.bin:$PATH ./scripts/verify.sh` | exit 0（`PASS contracts gate`、`Scaffold verification passed.`）；借用已有的 `openapi-typescript`，未安装任何东西 |
| 空白 | `git diff --check` | 无输出，exit 0 |

ADR-018 追加测试覆盖：`CHUNKER_VERSION == "chunk/1"`、`chunking_version()` 默认值 `chunk/1@1500-200` 且等于 `chunk/1@{DEFAULT_TARGET_CHARS}-{DEFAULT_OVERLAP_CHARS}`、带实际参数、读取的是 `CHUNKER_VERSION` 常量；非法参数（10 组）与 `chunk_blocks` 同样被拒且错误信息相同；组合格式；解析器段为空/含空白/含 `+` 被拒；分块段缺失或格式错（20 组，含前导零、全角数字、target 为 0、尾随空白、多余 `+`）被拒；`derive_revision_id`/`revision_id_for`/`assign_chunk_identities` 对 11 种不含合法分块段的 `parser_version` 均拒绝；同资料同内容仅 `target_chars` 或仅 `overlap_chars` 不同 → `revision_id` 不同且块 ID 集合不相交；仅 `CHUNKER_VERSION` 不同 → 修订与块 ID 不同。

ADR-018 反向篡改（先 `cp` 备份，改回后 `cmp` 均一致；以 `test_d09.py` + `test_d08.py` 计）：

| 篡改 | 结果 |
| --- | --- |
| A1 `revision_id` 校验退回为「非空无空白」，不查分块段 | 11 failed |
| A2 `chunking_version` 丢掉参数，恒返回默认参数 | 4 failed |
| A3 `revision_parser_version` 拼接时交换两段顺序 | 6 failed |

注意：A3 篡改与改回长度相同且落在同一秒内，Python 沿用了篡改版的 `__pycache__` 字节码（按 mtime 秒 + 大小判定），导致改回后首轮全量出现 6 条假失败。已删除 `src/backend/app/services/__pycache__/` 下 `chunk_identity`/`chunking` 两个 `.pyc`（被 `.gitignore` 忽略）后重跑：D09+D08 167 passed、全量 1204 passed、`verify.sh` exit 0。复现篡改时建议加 `python -B` 或 `PYTHONDONTWRITEBYTECODE=1`。

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

- ~~**分块参数不在修订内**~~：已由 ADR-018 解决（分块版本进入复合 `parser_version`）。剩余风险：分块输出规则变了却忘记递增 `CHUNKER_VERSION` 时仍会出现同 ID 异文，D10 不可变检查会报错拦截；改 `chunking.py` 输出规则的任务须同时递增该常量。
- **修订数量**：分块参数若按课程或资料频繁调整，修订与块数会膨胀（ADR-018 推翻条件）。
- **同文不同处不共享抽取缓存**：重复段落各自计费一次。MVP 规模可接受。
- **别名模型**：`integrations.md` 已登记的风险依旧成立（ID 不变而行为变化时缓存不失效）。

## 待决

1. ~~**分块版本归属**~~：**已由 ADR-018 关闭**（2026-09-25 签收）。分块版本并入修订键的 `parser_version`，实现见上文「ADR-018 追加」；风险一节的「分块参数不在修订内」随之消除。
2. **缓存键的模型 ID**（接 `claude-e02.md` 待决 2）：本实现取成功调用的 `model_requested`。若要改为 `model_responded`，只需改 `cache_model_id` 与一条测试，但查找时机需重新设计。建议协调方把此决定写入 `docs/integrations.md`「模型版本与向量空间」。
3. **fake 模式模型 ID**（接 `claude-e02.md` 待决 1）：缓存键要求非空 `model_id`；fake 模式由装配处（E03/E04）填固定 ID（如 `fake`），本模块不代填。
4. **除块文本外的提示词输入**：关系抽取、gleaning 等提示词若带块文本之外的变量（已抽实体列表、上一轮输出），这些变量不在缓存键中。E05/E06 若需要，应在本模块加一个显式的「附加输入哈希」参数（先改规格），而不是在调用方拼接进 `model_id` 或 `purpose`。
5. **跨修订复用抽取结果**：解析器升级后块 ID 全变，抽取缓存全部失效（保守）。若要按文本哈希跨修订复用，需要规格说明出处如何重新绑定。

## 下一步

- **D10**：写 `Chunk` 节点时用 `ChunkIdentity.chunk_id` 作唯一键、`revision_id` 作过滤属性、`text_sha256` 作不可变比对值（已存在 ID 且哈希不同即拒绝，PUB-30）；`split_chunk_id` 可从引用中的块 ID 取修订。
- **D11**（ADR-018 用法）：取定本次分块参数 `t, o`，`chunks = chunk_blocks(doc.blocks, target_chars=t, overlap_chars=o)`；`pv = revision_parser_version(doc.parser_version, chunking_version(t, o))`；`key = RevisionKey(document_id=material_id, content_hash=stored.content_hash, parser_version=pv)`；`assign_chunk_identities(course_id, key, chunks)`。`chunking_version` 的参数必须与 `chunk_blocks` 实际所用一致；解析器模块的 `PARSER_VERSION` 保持只表示解析器，不要在解析器里拼分块段。直接用 `doc.parser_version` 构造修订键会被拒绝。
- **E05**：查缓存前用 `PromptLibrary.get(purpose, version)` 的 `purpose`/`version`/`sha256` 与将要请求的模型 ID 算键；写缓存时用 `cache_model_id(result)` 重新算键后写入。E10 的合并裁决缓存（`specs/task-processing.md` §8.4 `merging` 行）键形不同，归 E 组，不复用本函数。

## 回滚

无破坏性修改；回滚即 revert 本分支的实现与交接提交。只回滚 ADR-018 追加时，revert ADR-018 实现提交（并视协调方决定 revert `686f57c`），固定值测试随之恢复旧期望值；D10 未持久化块前不涉及数据迁移。
