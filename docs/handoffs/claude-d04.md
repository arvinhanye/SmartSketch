# Claude 交接：D04 DOCX 段落和表格解析

- `task_id`: D04（GitHub issue #73，协调方已在解析并行批次 D02～D05 中认领）
- `review_status`: ready_for_review
- `worktree`: `.claude/worktrees/agent-a1c14389d12099b90`，分支 `claude/d04-docx-parser`
- `base_commit`: `588d00a`（origin/main，PR #188 合入后）
- 依赖：D01（`ParsedDocument` 等模型，已在 main）。
- 依据：`docs/atomic-task-plan.md` D04 行；`docs/architecture.md`「解析输出与来源定位（D01）」；`docs/handoffs/claude-d01.md`。

## 交付物

| 文件 | 内容 |
| --- | --- |
| `src/backend/app/services/parsers/docx.py` | `parse_docx(data, *, max_part_bytes=MAX_PART_BYTES) -> ParsedDocument`；常量 `PARSER_VERSION = "docx/1"`、`MAX_PART_BYTES`（64 MiB）、`DOCUMENT_PART`、`STYLES_PART` |
| `tests/backend/test_d04.py` | 53 个用例（含参数化），成功、边界、失败三类；样例 DOCX 全在测试里用 `zipfile` 拼到 `tmp_path`，不入库 |
| `docs/handoffs/claude-d04.md` | 本交接 |

未改 `pyproject.toml`（没有新依赖）、`parsers/__init__.py`、`parsers/models.py`、`tests/fixtures/documents/`、`docs/tasks.md`、`docs/architecture.md`、`docs/integrations.md`、`scripts/verify.sh`。

## 选型：标准库自解析，不用 python-docx

- **理由**：
  1. 标题判定要按样式 ID 和 `outlineLvl` 做，还要沿 `basedOn` 继承。python-docx 只暴露样式名，这部分仍需自己读 XML。
  2. 解压限额、拒绝 DTD、加密与旧版 `.doc` 的区分，都需要在 zip 和 XML 层自己控制。python-docx 在这些情况下抛的是各种泛化异常。
  3. 不新增依赖：避免与 D03、D05 在 `pyproject.toml` 的 `dependencies` 上产生文本冲突，也不引入 lxml 这个原生扩展。
- **许可**：只用 CPython 标准库（PSF 许可），不涉及第三方包。
- **安全措施**：
  - **XML**：用 `ElementTree.XMLParser` 配自定义 `TreeBuilder.doctype`，一遇到 DOCTYPE 就中止解析。这时内部子集里的实体声明还没处理，实体膨胀和外部实体都被挡住。OOXML 部件本来就不含 DTD。
  - **解压炸弹**：`zf.open(...).read(limit + 1)`，按实际读出的字节判断，不信任头部声明的大小。解析器只打开 `word/document.xml` 和 `word/styles.xml` 两个部件。
  - **命名空间**：同时支持 Transitional（`http://schemas.openxmlformats.org/wordprocessingml/2006/main`）和 Strict（`http://purl.oclc.org/ooxml/wordprocessingml/main`）。按根元素的命名空间取 `w:`，其他命名空间的元素一律忽略。

## 解析规则与关键决定

- **定位**：遵循 D01 规则。每块带 `section_titles` 和 `paragraph`（同一标题路径下从 1 起连续编号，同名路径再次出现时接续），`page` 和行号一律为空。`w:br w:type="page"` 与 `w:lastRenderedPageBreak` 不当作页码。表格和列表块同样占一个段落号。
- **标题判定**（不看显示名，例如样式名或别名写成「标题 1」但没有大纲级别的自定义样式，仍按正文处理）：
  1. 段落直接设置的 `w:pPr/w:outlineLvl`：0～8 对应第 1～9 级；9 表示正文，可以覆盖样式带来的标题级别。
  2. 否则沿 `pStyle → basedOn` 链找第一个带 `outlineLvl` 的样式。中文版 Word 的「标题 1」样式 ID 是 `"1"`，靠这一步识别。`basedOn` 成环时停止。
  3. 链上的样式 ID 形如 `HeadingN`（不区分大小写，允许中间有空格）时按第 N 级。这一条用于缺少 `styles.xml` 或样式没写大纲级别的生成器。
  4. 段落没有 `pStyle` 时，用 `styles.xml` 里 `w:default="1"` 的段落样式。
  - 标题文字先经 `normalize_heading`；标题为空时忽略，不改变标题栈；标题跳级（如一级后直接三级）时照常入栈。
- **块类型**：
  - 普通段落为 `paragraph`，文本去掉首尾空白。
  - 连续的编号段落合成一个 `list` 块，每项一行。判定条件：直接或经样式链带 `w:numPr`，且 `numId ≠ 0`，同一 `numId`。`numId` 变化、遇到标题、普通段落或表格时，列表结束。不生成编号文字（例如「1.」），因为那需要解析 `numbering.xml`，而编号文字本身不在原文中。
  - 表格为一个 `table` 块：每行占一行，单元格之间用 ` | ` 分隔并保持顺序。单元格内的多段文字和嵌套表按文档顺序用空格连接；全空的行跳过，全空的表不产生块。横向合并（`gridSpan`）的单元格只输出一次；纵向合并的续行（`vMerge` continue）输出空单元格，不复制上方内容。
  - 空白段落、只有分页符或只有图片的段落都跳过。
- **空结果**：没有任何正文块时抛 `DocumentUnreadableError("no_text")`，包括空文档、只有标题、只有图片、只有空表格。依据是 D01「标题不成块」。

## 嵌入内容的处理范围

| 内容 | 处理 |
| --- | --- |
| 正文段落、超链接文字、内容控件 `w:sdt`（段内和块级）、`w:smartTag`、`w:customXml`、`w:fldSimple`、`w:dir`/`w:bdo` | **解析** |
| 修订：插入 `w:ins`、移入 `w:moveTo` | **解析**（等同于接受全部修订后的文字） |
| 域：结果文字（`separate` 与 `end` 之间的 `w:t`） | **解析**；域代码 `w:instrText` 忽略 |
| `w:tab`/`w:ptab` 转为制表符，`w:br`/`w:cr` 转为换行，`w:noBreakHyphen` 转为 `-` | **解析** |
| 正文表格（含嵌套表、合并单元格） | **解析**，输出为 `table` 块 |
| 修订删除 `w:del`/`w:delText`、移出 `w:moveFrom` | 忽略 |
| 直接设为隐藏的文字（run 上的 `w:vanish`） | 忽略；样式层面的隐藏不追踪 |
| 图片与图形（`w:drawing`、`w:pict`，包括替代文字 `descr`） | 忽略 |
| 文本框 `w:txbxContent`（DrawingML 与 VML 两种写法，以及 `mc:AlternateContent` 整体） | 忽略：阅读顺序不可靠，而且 Choice 和 Fallback 两种写法会重复同一段文字 |
| 嵌入对象 `w:object`（OLE）、外部导入块 `w:altChunk` | 忽略 |
| 公式 `m:oMath`/`m:oMathPara` | 忽略：把线性化的 `m:t` 拼起来会丢失分式、上下标结构，容易误导 |
| 页眉页脚、脚注尾注、批注（`header*.xml`、`footer*.xml`、`footnotes.xml`、`endnotes.xml`、`comments.xml`） | 忽略：这些部件不打开；正文里的引用标记也不输出 |

## 失败映射

| 情况 | `DocumentUnreadableError.reason` |
| --- | --- |
| 以 OLE 文件头 `D0 CF 11 E0 A1 B1 1A E1` 开头，且含 `EncryptionInfo` 或 `EncryptedPackage` 流名（UTF-16LE） | `encrypted` |
| zip 条目带加密标志（通用标志位 bit 0） | `encrypted` |
| 以 OLE 文件头开头，但不含上述加密流（多半是改了扩展名的旧版 `.doc`） | `corrupted`，detail 注明「可能是旧版 .doc」 |
| 空字节、非 zip、截断的 zip、CRC 错误、不支持的压缩方式 | `corrupted` |
| 缺少 `word/document.xml`（部件名按 OPC 规则不区分大小写） | `corrupted`，detail 写明缺哪个部件 |
| `document.xml` 或 `styles.xml` 不是合法 XML、根元素不对、缺少 `w:body`、含 DOCTYPE | `corrupted` |
| 部件解压后超过 `max_part_bytes` | `corrupted`，detail 含「上限」 |
| 没有正文块 | `no_text` |
| 参数不是 `bytes`、`bytearray` 或 `memoryview` | `TypeError`（属于调用方缺陷） |

## 实际验证（macOS，Python 3.13.5；本任务专用 venv：`python3 -m venv <scratchpad>/venv-d04-a1c14389 && pip install -e './src/backend[test]'`）

| 命令 | 结果 |
| --- | --- |
| 红灯：只提交测试（`408b5f1`）时运行 `pytest tests/backend/test_d04.py -q` | 收集错误 `ImportError: cannot import name 'docx' from 'app.services.parsers'`，exit 非 0 |
| 绿灯：`pytest tests/backend/test_d04.py -q` | **53 passed** |
| 全部后端：`pytest tests/backend -q` | **527 passed**，1 warning（main 上已有的 Starlette `httpx` 弃用提示，与本任务无关） |
| 反向篡改（逐项改坏 `docx.py` 后跑 D04，再恢复） | 允许 DOCTYPE → 2 failed；去掉超限判定 → 1；读全量且不判定 → 1；OLE 一律当加密 → 1；忽略 outlineLvl → 2；不走 basedOn → 1；outlineLvl 9 当标题 → 1；表格不作 table 块 → 2；不过滤隐藏文字 → 1；不查 zip 加密标志 → 1；列表不合并 → 1；恢复后 53 passed |
| 真实样例抽查（不入库）：在 scratchpad 的独立 venv 里用 python-docx 1.2.0（它自带 Word 生成的默认模板）生成含 Heading 1/2、表格、List Number、页眉的 DOCX，再用 `parse_docx` 解析 | 标题路径、表格块、列表块（`ListNumber` 样式链上的 `numPr`）都正确，页眉被忽略。python-docx 只用于生成样例，不是项目依赖 |
| `./scripts/verify.sh`（系统 python3，退出码单独取） | exit 0 |
| `git diff --check`；`git diff --check origin/main...HEAD` | 均为 exit 0 |

- 清单中的原命令 `python3 -m pytest tests/backend/test_d04.py -q`，如果用未安装后端包的系统 python3（anaconda）运行，会报收集错误 `ImportError`，找不到 `app`。这与 D01 交接记录的环境问题相同，上表结果都来自装了后端包的 venv。
- 注意：会话 scratchpad 由多个子代理共用。最初用的公共 venv 路径被另一个 worktree 的 `pip install -e` 覆盖了，导致导入指向别的 worktree。之后改用本任务专用的 venv 路径，上表所有结果都在这个 venv 里重新跑过。
- `src/backend/smartsketch_backend.egg-info` 已被 `.gitignore` 忽略，没有提交。

## 接口说明（给 D08、D11）

```python
from app.services.parsers.docx import PARSER_VERSION, parse_docx

doc = parse_docx(stored_bytes)          # -> ParsedDocument(SourceFormat.DOCX, "docx/1", blocks)
for block in doc.blocks:
    block.kind                         # paragraph / list / table（DOCX 不产生 code）
    block.locator.section_titles       # 标题路径元组，可为空
    block.locator.paragraph            # 同一标题路径下的段落号，≥ 1
    block.locator.page                 # 恒为 None
    block.locator.to_source_fields()   # {"section_path": "第3章 > 3.1 栈 > 第2段"}
```

- **D08**：`table` 块的文本是「行按 `\n` 分隔、单元格按 ` | ` 分隔」，超长表格需要切分时，建议按行切，不要从单元格中间切开。`list` 块每项一行。块文本不含标题，标题只在 `section_titles` 里。
- **D11**：`RevisionKey(document_id, stored.content_hash, doc.parser_version)`。捕获 `DocumentUnreadableError` 后映射为 `DOCUMENT_UNREADABLE`，`details.reason = err.reason.value`。`max_part_bytes` 使用默认值即可。
- `parsers/__init__.py` 没有重导出 `parse_docx`，因为该文件不在本任务的文件锁内。需要统一入口（例如按 `SourceFormat` 分发）时，由 D11 或协调方决定。

## 风险与未决事项

- **旧版 `.doc` 与加密包的区分是启发式的**：判断依据是 OLE 文件中是否出现 `EncryptionInfo` 或 `EncryptedPackage` 的 UTF-16LE 流名，没有完整解析 OLE 目录。正文里恰好含有这段 UTF-16 字节的 `.doc` 会被误报为 `encrypted`，概率极低。任务要求写的是「OLE 文件头即 `encrypted`」，我把不含加密流的 OLE 文件改判为 `corrupted`，避免告诉教师「文件加了密码」而实际上只是格式不对。**如果协调方要求严格按文件头判定，只需删掉一个条件，测试 `test_ole_without_encryption_streams_is_legacy_doc_and_corrupted` 相应改写。**
- **主文档部件固定为 `word/document.xml`**：没有按 `_rels/.rels` 的 officeDocument 关系去解析实际路径。个别生成器可能用别的文件名（例如 `word/document2.xml`），这类文件会被判为 `corrupted`。样式部件也固定为 `word/styles.xml`。
- **内存**：ElementTree 会把整棵树读进内存，64 MiB 的 XML 大约占用 1 GB 以上。在 50 MiB 上传上限（D-11）下，正常课程资料远达不到这个量，但仍是 Worker 内存的上界。如果需要，可以调小 `MAX_PART_BYTES`，或以后改成 iterparse 流式解析。
- **信息损失**（有意为之，已写入模块说明）：文本框、公式、脚注、图片替代文字不进块；列表不带编号文字；纵向合并的单元格不复制内容。如果教师资料大量依赖文本框或公式，需要另立任务扩展，并递增 `PARSER_VERSION`。
- **没有用真实 Word/WPS 文件做回归**：测试样例按 ECMA-376 手工拼装，并用 python-docx 的 Word 模板抽查过一次。WPS 的样式 ID 习惯未实测。按 ID 兜底只认 `HeadingN`，WPS 只要在样式中写了 `outlineLvl` 就能识别。
- `docs/tasks.md` 的 D04 状态与验收证据没有更新（不在文件锁内），由协调方在合并时更新。选型「标准库、无新依赖」如需登记到 `docs/integrations.md`，也由协调方处理。

## 下一步

- 请 Codex 审查 PR。合并后，D08 可在 D02、D03、D06、D07 就绪后开工。

## 回滚

只新增了 3 个文件（解析器、测试、本交接），没有依赖、数据或契约变更。删除这 3 个文件即可回滚。
