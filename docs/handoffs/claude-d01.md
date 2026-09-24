# Claude 交接：D01 解析输出模型与自编 fixture

- `task_id`: D01（GitHub issue #70，协调方已认领）
- `review_status`: ready_for_review
- `worktree`: `/Users/arvinhan/Desktop/SmartSketch/.claude/worktrees/agent-aec40eaf0087d513d`，分支 `claude/d01-parse-model`
- `base_commit`: `68affa8`（origin/main，PR #179 合入后）
- `head`: 本交接所在的提交（单提交，见 PR）
- 依赖：B08（`SourceRef` 的 `page` / `section_path` 至少一个、`DOCUMENT_UNREADABLE` 的 `reason` 闭集）已在 main。
- 依据：`docs/atomic-task-plan.md` D01～D11 行；`specs/teacher-review-publish.md` V2（资料修订、文本块不可变）；`specs/task-processing.md` §6、§8.4 `parsing`；ADR-003；ADR-012 修订 1；ADR-016 决定 6（命名用 `document_id`）。

## 交付物

| 文件 | 内容 |
| --- | --- |
| `src/backend/app/services/parsers/models.py` | 纯数据模型（stdlib `dataclass(frozen=True, slots=True)`，无新依赖），见下「模型」 |
| `src/backend/app/services/parsers/__init__.py` | 包入口，重导出全部公共名称 |
| `tests/backend/test_d01.py` | 83 个用例（含参数化），覆盖成功、边界、失败三类，外加 fixture 检查 |
| `tests/fixtures/documents/README.md` | 来源与许可（自编）、每份样例用途、DOCX/PDF/GBK 不入库的约定 |
| `tests/fixtures/documents/stack-queue-notes.md` | 自编 Markdown：标题前段落、两级标题、表格、列表、代码块中的 `#` |
| `tests/fixtures/documents/linear-list-numbered.txt` | 自编 TXT：中文编号「第一章」「二、」与「1.1」混用 |
| `tests/fixtures/documents/sorting-plain.txt` | 自编 TXT：无任何标题，只有段落 |
| `tests/fixtures/documents/empty.txt` | 0 字节，空文档用例 |

未改 `docs/tasks.md`、`docs/architecture.md`、`scripts/verify.sh`、`src/contracts/`、`config.py`、`pyproject.toml`。

## 模型

- `SourceFormat`：`txt` / `markdown` / `docx` / `pdf`；`.paginated` 只有 PDF 为真（DOCX 分页随渲染变化，不算页码）。
- `BlockKind`：`paragraph` / `list` / `table` / `code`。标题不是块，只进入后续块的 `section_titles`。
- `SourceLocator(page, section_titles, paragraph, line_start, line_end)`：
  - `page`：`None` 或 ≥ 1 的整数（拒绝 `bool`、`float`、字符串）。
  - `section_titles`：各级标题元组（列表会转为元组）；每个标题必须非空、且已经过 `normalize_heading`（无首尾空白、无换行、无半角 `>`）。
  - `paragraph`：`None` 或 ≥ 1 的整数。
  - `line_start` / `line_end`：同时给或同时空，`1 ≤ start ≤ end`。
  - 三者（`page`、`section_titles`、`paragraph`）至少有一个。
  - `.section_path`：有标题时为 `" > ".join(section_titles)`（与 `SourceRef` 示例「第3章 > 3.1 栈」一致）；无标题时为 `第N段`；二者皆无时为 `None`。
  - `.to_source_fields()`：返回 `SourceRef` 的定位字段，缺失的键直接省略，不写 `null`。
- `ParsedBlock(ordinal, text, locator, kind=paragraph)`：`ordinal` ≥ 0 的整数；`text` 去掉空白后必须非空，原文（含首尾空白）原样保存；`kind` 接受枚举值字符串。
- `ParsedDocument(source_format, parser_version, blocks)`：文档级规则见下；`blocks` 转为元组。
- `RevisionKey(document_id, content_hash, parser_version)`：资料修订三元组；`content_hash` 必须形如 `sha256:<64 位小写十六进制>`（与快照摘要格式一致）；`parser_version` 为不含空白的非空字符串（如 `txt/1`）。
- `sha256_digest(bytes)`：对**原始上传字节**求上述格式的哈希；传入 `str` 会被拒绝。
- `normalize_heading(str)`：合并所有空白为单个空格、去首尾，半角 `>` 改为全角 `＞`，保证 `section_path` 能按连接符无歧义地拆回各级标题。
- `DocumentUnreadableError(reason, detail="")`：`reason ∈ {corrupted, encrypted, no_text}`，与 `DOCUMENT_UNREADABLE.details.reason` 的 wire 闭集一致；传其他值抛 `ParseModelError`。
- `ParseModelError(ValueError)`：违反不变量即抛出，说明解析器实现有缺陷。

## 定位规则（ParsedDocument 构造时校验）

1. `ordinal` 必须按顺序从 0 连续编号，不能重复、跳号或乱序。
2. **PDF**：每块必须有 `page`；`section_titles` 可空（由 D06 给）；不带行号。
3. **TXT / Markdown / DOCX（无页码）**：`page` 必须为空，不得编造页码；每块必须有 `paragraph`。
4. **段落编号**：凡是带 `paragraph` 的块，按相同的 `section_titles` 分组、按 `ordinal` 顺序，编号必须恰为 1、2、3……。同一标题路径在文档中再次出现时接续编号，所以「章节路径 + 段落号」在一份文档内唯一。块前没有标题时，`section_titles = ()`，`section_path` 为 `第N段`。
5. **行号**：TXT 与 Markdown 必须带行号（指解码后源文本的物理行号，闭区间），且块与块之间严格递增、不重叠；DOCX 与 PDF 不得带行号。
6. **空文档**：`blocks` 为空时拒绝构造。解析器应改抛 `DocumentUnreadableError("no_text")`，对应 TASK-14 的 `reason = no_text`。

## 决定与理由

- **修订信息放在文档级，不放在每个块上**：解析器只拿到字节，不知道 `document_id`。所以 `ParsedDocument` 只带 `parser_version`，D11 编排时用 `RevisionKey(document_id, sha256_digest(原始字节), parsed.parser_version)` 补齐。同一 `ParsedDocument` 的所有块属于同一个修订。`revision_id` 与块 ID 的派生公式留给 D09，本任务不定义，以免抢先做 D09 的决定。
- **`ordinal` 是解析块的序号，不是文本块（Chunk）的序号**：D08 会把多个解析块合并或切分成约 1500 字的块，规格中「`revision_id` + 块序号」的块序号由 D08/D09 给出。
- **无页码格式一律要求 `paragraph`，即使已有标题**：保证兜底定位始终存在，也给 D08 的「来源映射回原文」留出比章节更细的位置。
- **标题禁用半角 `>`**：连接符是 `" > "`，标题里若出现 `>`，路径就无法唯一拆分。由 `normalize_heading` 统一替换，校验只认规范化后的标题。
- **命名用 `document_id`**：遵循 ADR-016 决定 6。`specs/teacher-review-publish.md` V2 与快照示例中的 `material_id` 指同一概念，等 A10 批 5 统一改名。
- **使用 stdlib dataclass，不用 Pydantic**：纯内部值对象，不上 wire，无需序列化；冻结后与「文本块不可变」一致；D02～D07 无需额外依赖。

## 实际验证（macOS，Python 3.13.5 venv，`pip install -e './src/backend[test]'`）

| 命令 | 结果 |
| --- | --- |
| 红灯：实现前 `pytest tests/backend/test_d01.py -q` | 收集错误 `ModuleNotFoundError: No module named 'app.services.parsers'`（exit 非 0） |
| 模型实现后、fixture 写入前 | 2 failed / 81 passed（fixture 目录与 README 缺失） |
| 绿灯：`pytest tests/backend/test_d01.py -q` | 83 passed |
| 全部后端 `pytest tests/backend -q` | 159 passed，1 warning（main 已有的 Starlette `httpx` 弃用提示，与本任务无关） |
| 反向篡改（逐项改坏 `models.py` 后跑 D01，再恢复） | 无页码格式允许页码 → 3 failed；取消「定位全缺」检查 → 1；取消段落断档检查 → 4；页码允许 0 → 1；行号允许重叠 → 1；允许空文档 → 1；恢复后 83 passed |
| `./scripts/verify.sh`（系统 python3） | exit 0 |
| `git diff --check` | exit 0 |

测试后已删除 `src/backend/smartsketch_backend.egg-info`，未提交。

## 给 D02～D11 的使用说明

- **D02（TXT）**：输出 `ParsedDocument(SourceFormat.TXT, "txt/<n>", blocks)`。标题先经 `normalize_heading` 再放入 `section_titles`，每块带 `paragraph` 和行号。空文或只有空白抛 `DocumentUnreadableError("no_text")`。坏编码建议用 `corrupted`，由 D02 决定并测试。GBK 与坏编码样例在测试中由 fixture 重新编码得到。
- **D03（Markdown）**：同上。表格、列表、代码分别用 `BlockKind.TABLE`、`LIST`、`CODE`。代码块内以 `#` 开头的行不是标题，fixture `stack-queue-notes.md` 里有这种行。
- **D04（DOCX）**：不带 `page` 和行号，每块带 `paragraph`。样例在测试中用代码生成，不入库。
- **D05～D07（PDF）**：D05 的「分页文本行」是 D05 自己的中间结构。最终交给 D08 的 `ParsedBlock` 必须带原始页码；D07 删除页眉页脚后仍保留原页码。扫描件或没有文本层的 PDF 抛 `no_text`，不声称有 OCR。
- **D08（分块）**：输入 `ParsedDocument.blocks`，不跨 `section_titles` 合块。建议一个 Chunk 的定位取首块的 `SourceLocator`，并记录覆盖的 `ordinal` 区间，以便映射回原文。对于都是 `第N段` 兜底的块，合并后的 `section_path` 取首段还是区间，由 D08 决定。
- **D09（块身份）**：用 `RevisionKey` 派生 `revision_id`，再用「`revision_id` + 块序号」派生块 ID。`content_hash` 已固定为 `sha256:` 格式。
- **D10（持久化）**：定位字段用 `SourceLocator.to_source_fields()` 或等价逻辑写入，保证 `page` / `section_path` 至少一个，无页码时不写 `null`。
- **D11（编排）**：捕获 `DocumentUnreadableError`，映射为 T9 `DOCUMENT_UNREADABLE`，`details.reason = err.reason.value`。`ParseModelError` 属实现缺陷，按 `INTERNAL_ERROR` 处理。建议由 D11 定下这一映射。

## 未验证项与风险

- 未做任何真实解析；定位规则在 D02～D07 实现时才第一次接触真实资料结构。若发现规则不够用（例如 DOCX 需要表格内定位），需回到本模型修改，并同步本交接和 D01 测试。
- `paragraph` 在同一 `section_titles` 下连续编号，要求解析器在整个文档范围内按路径计数。重复的同名同级小节会接续编号，这是有意设计，但报告给学生时可能显得不直观。
- 本任务提出了 `第N段` 兜底格式和 `parser_version` 不含空白的约束，但尚未写入 `specs/` 或 `docs/architecture.md`（不在本任务文件锁内）。建议协调方决定是否在 D 组规格或架构文档中登记。
- `docs/tasks.md` 的 D01 状态与验收证据未更新（不在文件锁内），由协调方在合并时更新。
- 系统 python3（anaconda，pytest 8.3.4）没有安装后端包。直接运行清单中的单项命令 `python3 -m pytest tests/backend/test_d01.py -q` 会报收集错误 `No module named 'app'`，已有的 `test_c01.py` 也一样，属于环境问题。本任务的 pytest 结果全部来自上面的 venv（先 `pip install -e`）。

## 下一步

- 请 Codex 审查。合并后，D02、D03、D04、D05 可以并行认领（都只依赖 D01）。

## 回滚

只新增文件，不改任何已有文件。回滚时删除上表中的 8 个新文件和本交接即可，无数据或依赖变更。
