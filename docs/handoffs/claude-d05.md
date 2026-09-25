# Claude 交接：D05 PDF 正文与页码提取

- `task_id`: D05（GitHub issue #74）
- `review_status`: ready_for_review
- `worktree`: `/Users/arvinhan/Desktop/SmartSketch/.claude/worktrees/agent-a4e6db21278386290`，分支 `claude/d05-pdf-parser`
- `base_commit`: `588d00a`（origin/main，PR #188 合入后）
- 依赖：D01（`ParsedDocument`、`SourceLocator`、`DocumentUnreadableError`）已在 main。
- 依据：`docs/atomic-task-plan.md` D05～D08 行；`docs/architecture.md`「解析输出与来源定位（D01）」；`docs/handoffs/claude-d01.md`。

## 交付物

| 文件 | 内容 |
| --- | --- |
| `src/backend/app/services/parsers/pdf.py` | 新增。`extract_pdf` 提取分页文本行（中间结构）；`to_parsed_document`、`parse_pdf` 转成 D01 `ParsedDocument`；`PARSER_VERSION = "pdf/1"` |
| `tests/backend/test_d05.py` | 新增。33 个用例（含参数化），测试 PDF 全部在测试中手写字节生成，不入库，也不新增测试依赖 |
| `src/backend/pyproject.toml` | 只在 `dependencies` 列表加一行 `"pdfminer.six==20260107"`，其他部分未动 |

未改 `parsers/__init__.py`、`parsers/models.py`、`tests/fixtures/documents/`、`docs/tasks.md`、`docs/architecture.md`、`docs/integrations.md`、`scripts/verify.sh`。`pdf` 子模块没有在 `parsers/__init__.py` 中重导出，调用方用 `from app.services.parsers.pdf import ...`。

## 选库：pdfminer.six 20260107

| 项 | 内容 |
| --- | --- |
| 许可 | MIT |
| 传递依赖 | `charset-normalizer>=2.0.0`（MIT）、`cryptography>=36.0.0`（Apache-2.0 或 BSD-3-Clause 双许可）。都在允许的许可范围内 |
| 为什么选它 | 1）自带版面分析：字符 → 行（`LTTextLine`）→ 文本框（`LTTextBox`），并给出阅读顺序，多栏也有基本处理，D05 不必自己按坐标拼行。2）每个字符（`LTChar`）带字体名、有效字号和外框，D06、D07 需要的信息都能直接取到。3）内置 Adobe-GB1 等预定义 CMap，中文 CID 字体即使没有 ToUnicode 也能还原文字，测试中已验证。 |
| 放弃的候选 | `pypdf`（BSD，零依赖）：只有文本绘制回调，行切分、阅读顺序和有效字号都得自己实现，对 D06/D07 不够稳。PyMuPDF/fitz：AGPL，禁用。pdfplumber：依赖 pypdfium2 这个大型二进制库。 |
| 需要登记的事项 | `cryptography` 是 pdfminer.six 的**强制**依赖（在 `pdfdocument.py` 顶层导入），不是为读加密 PDF 另外加的。本实现不用它解密：只要 PDF 带 `/Encrypt`，一律拒绝。请协调方在 `docs/integrations.md` 登记 pdfminer.six 及这两个传递依赖。 |

## 给 D06、D07 的中间结构

```python
from app.services.parsers.pdf import PdfExtraction, PdfLine, PdfPage, extract_pdf, to_parsed_document

extraction: PdfExtraction = extract_pdf(pdf_bytes)   # 失败时抛 DocumentUnreadableError
extraction.pages      # tuple[PdfPage, ...]，包含空白页（lines == ()）
extraction.lines      # tuple[PdfLine, ...]，全部行，先按页序，再按页内阅读顺序
extraction.parser_version  # "pdf/1"
```

`PdfPage(number, width, height, lines)`：`number` 从 1 起，`width`、`height` 为页面尺寸（pt）。

`PdfLine`（冻结 dataclass）：

| 字段 | 含义 |
| --- | --- |
| `page` | 从 1 起的物理页序号，与阅读器的「跳到第 N 页」一致，不读页面标签 |
| `index` | 本页内按阅读顺序从 0 起的行号 |
| `box` | 本页内文本框（近似段落）从 0 起的序号，只给有内容的框编号，连续不跳号 |
| `text` | 行文本：去掉首尾空白，行内空格原样保留，保证非空 |
| `font_name` | 主字体名：取行内非空白字符最多的「字体名 + 字号」组合，并去掉 `ABCDEF+` 子集前缀 |
| `font_size` | 主字体的有效字号（已乘文本矩阵缩放，保留两位小数） |
| `bold` | 主字体是否为粗体：字体名中含 Bold、Black、Heavy、Semibold 或 Demi（不区分大小写），能识别 Word 输出的 `SimSun,Bold` |
| `bold_ratio` | 行内非空白字符中粗体字符的占比，范围 0～1。D06 可以据此区分「整行加粗」和「正文里夹着一个粗体词」 |
| `x0, y0, x1, y1` | 行外框，PDF 用户空间坐标：原点在页面左下角，y 向上增大，保留两位小数。D07 可以用 `y1 / page.height` 判断是否在页眉区，用 `y0` 判断是否在页脚区 |

- **D06** 只需判定哪些行是标题，并据此给后续行的块填 `section_titles`。`to_parsed_document` 目前不接受标题参数；D06 可以另写一个转换函数，也可以扩展这个函数（该文件归 D05，扩展时请顺序认领）。
- **D07** 删除页眉、页脚、页码行时，直接过滤 `PdfLine` 序列即可，再交给 `to_parsed_document(kept_lines)`。每行自带原始 `page`，删行不影响页码。测试 `test_to_parsed_document_keeps_original_pages_after_lines_are_removed` 演示了这个用法。
- **转成 `ParsedDocument`**：相邻且 `(page, box)` 相同的行合为一个 `ParsedBlock`，行间用 `\n` 连接，`kind=paragraph`。定位只填 `SourceLocator(page=原始页码)`：不填 `paragraph`，不填行号，`section_titles=()`，因此 `to_source_fields()` 等于 `{"page": n}`。没有任何行时抛 `no_text`。

## 失败状态（`DocumentUnreadableError.reason`）

| 情形 | reason | 说明 |
| --- | --- | --- |
| trailer 带 `/Encrypt`，空密码打不开 | `encrypted` | pdfminer 抛 `PDFPasswordIncorrect` 或 `PDFEncryptionError`，统一映射 |
| trailer 带 `/Encrypt`，空用户密码能打开（只限制了权限） | `encrypted` | **有意拒绝**：不绕过作者设置的加密和权限，detail 提示上传未加密版本 |
| 前 1024 字节内没有 `%PDF-`，包括空字节、纯文本、其他格式 | `corrupted` | 不交给 pdfminer 处理 |
| 末尾 1024 字节内没有 `%%EOF` | `corrupted` | 截断的上传。pdfminer 会退回全文扫描，可能静默丢页，所以提前拒绝 |
| 解析时遇到被引用但缺失的对象 | `corrupted` | pdfminer 默认把缺失对象当作 None，中段损坏的页会变成空白页，进而被误报为扫描件。现在由 `_TrackingDocument` 记录缺失对象，一旦出现即拒绝 |
| pdfminer 抛出任何其他异常（`MemoryError` 除外） | `corrupted` | detail 带异常类名 |
| 没有任何页面 | `corrupted` | |
| 所有页都没有文字，或只有图片 | `no_text` | detail 写明「可能是扫描件……系统未提供 OCR」 |
| 所有字形都无法映射为 Unicode（只剩 `(cid:N)`） | `no_text` | detail 写明缺少 ToUnicode，且系统未提供 OCR |
| 入参不是 bytes、bytearray 或 memoryview | `TypeError` | 属调用方错误，不是资料问题 |

## 关键决定

1. **拒绝所有带 `/Encrypt` 的 PDF**，包括空用户密码能打开的。这样做一是不绕过权限限制，二是结果与加密算法无关（RC4 或 AES 都一样）。代价是教师拿到的「禁止复制」讲义也会被拒，需要先导出一份未加密版本。是否放宽，见未决事项。
2. **行序用 pdfminer 的版面分析**（`LAParams(all_texts=True)`，其余参数用默认值，`boxes_flow=0.5`），不用内容流的绘制顺序。`all_texts=True` 让表单 XObject（`LTFigure`）里的文字也参与分析，否则这类文字会整段丢失。
3. **主字体按字符数投票**，粗体只看字体名。字体描述符里的 `FontWeight`、`ForceBold` 和渲染模式 2（描边伪粗体）都没有读取，风险见下。
4. **空白页保留在 `pages` 中，但不产生行**，因此后续页码不变。只含空白字符的页同样按空白页处理。
5. **只含 `(cid:N)` 的行直接丢弃**；部分字符是 `(cid:N)` 的行原样保留。
6. `parser_version = "pdf/1"`。行切分、行序或过滤规则一旦变化就递增。

## 实际验证

环境：macOS，Python 3.13.5 venv（在 scratchpad 中），`pip install -e './src/backend[test]'`。安装期间访问 PyPI 反复超时，`cryptography` 的 wheel 下不下来。所以 pdfminer.six 20260107 用的是已下载的官方 wheel（`pip install --no-deps`），`cryptography`（44.0.1）和 `charset-normalizer`（3.3.2）来自 anaconda 的 site-packages（venv 开启了 `include-system-site-packages`）。两者的版本都满足 pdfminer 的下限。**`pip check` 和从 PyPI 完整安装没有在本机验证，要靠 CI 的 Backend job 确认。**

| 命令 | 结果 |
| --- | --- |
| 红灯：只提交测试时运行 `python -m pytest tests/backend/test_d05.py -q` | 收集错误 `ImportError: cannot import name 'pdf' from 'app.services.parsers'`，exit 2 |
| 首版实现后运行同一命令 | 30 passed |
| 补充的中段损坏用例在未追踪缺失对象时 | 中段被截掉或被清零的 PDF 返回 `no_text`（误报为扫描件）。探针脚本已确认，随后加入 `_TrackingDocument` |
| 绿灯：`python -m pytest tests/backend/test_d05.py -q` | **33 passed** |
| 全部后端测试：`python -m pytest tests/backend -q` | **507 passed**，1 warning（main 已有的 Starlette `httpx` 弃用提示） |
| 反向篡改（逐项改坏 `pdf.py` 后跑 D05，再恢复） | 不拒绝空密码可开的加密 → 1 failed；不检查 `%%EOF` → 1；不追踪缺失对象 → 3；页码从 0 起 → 5；空白页不计页码 → 4；不过滤 cid 占位 → 1；粗体恒为 False → 2；不去子集前缀 → 1；不按版面分析排序（`boxes_flow=None, line_margin=0`）→ 1；不去首尾空白 → 1。恢复后 33 passed |
| `./scripts/verify.sh`（系统 python3，单独取退出码） | exit 0 |
| `git diff --check` | exit 0 |

## 风险

- **CJK 字体**：没有 ToUnicode、也不是预定义 CMap 的子集字体（常见于某些国产排版软件）只能得到 `(cid:N)`。全文都是这种情况时报 `no_text`；只有部分字符如此时，这些行会带着占位符进入正文。
- **多栏与复杂版面**：`boxes_flow=0.5` 对规整的双栏有效，但遇到栏间距小、图文混排、表格时，行序可能在两栏之间交错。表格没有结构化，每个单元格按行输出。
- **竖排文字**：没有开启 `detect_vertical`，竖排中文会被拆成逐字的行。
- **粗体识别**：只看字体名。渲染模式 2 描边的伪粗体、名字里不带 Bold 的黑体类字体（例如 `SimHei`）都不算粗体。D06 可以把 `font_name` 和 `font_size` 一起用。
- **表单 XObject 中的文字**：它们在页内的顺序取决于 pdfminer 的排列方式（通常在正文文本框之后），可能不在视觉位置上。
- **严格的完整性检查**：要求末尾有 `%%EOF`、引用对象不得缺失。这可能拒绝一些阅读器能勉强打开的轻度损坏文件。取舍是宁可明确报 `corrupted`，也不静默丢页。
- **性能**：pdfminer 是纯 Python，大文件（上限 50 MiB，D-11）逐页做版面分析可能要数十秒。D11 编排时需要放进异步任务并设置超时，本任务没有测性能。
- **页码**：只用物理页序号。教材正文页码（如前言用罗马数字）和 PDF 页码不一致，学生看到的「第 N 页」是阅读器的页码。

## 未决事项（请协调方决定并登记）

1. 只设了所有者密码（空用户密码能打开）的 PDF 是否放行？现在一律按 `encrypted` 拒绝。若要放行，就要读取 `is_extractable` 并决定是否遵守「禁止复制」的权限，这涉及版权。
2. 在 `docs/integrations.md` 登记 pdfminer.six 20260107（MIT）及其传递依赖 `cryptography`、`charset-normalizer`。
3. 把 D05 的状态和验收证据写入 `docs/tasks.md`（不在本任务的文件锁内）。

## 下一步

- 请 Codex 审查。合并后，D06（标题判定）和 D07（页眉页脚清洗）都以 `extract_pdf` 的 `PdfLine` 序列为输入，可以并行开发。两者都改 `pdf.py` 的转换路径时，请顺序认领。

## 回滚

删除 `pdf.py`、`test_d05.py` 和本交接，并从 `pyproject.toml` 的 `dependencies` 删掉 `pdfminer.six` 那一行。不涉及数据或迁移。
