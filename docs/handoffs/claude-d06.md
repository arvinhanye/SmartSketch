# Claude 交接：D06 PDF 标题判定

- `task_id`: D06（GitHub issue #75）
- `review_status`: ready_for_review
- `worktree`: `/Users/arvinhan/Desktop/SmartSketch/.claude/worktrees/d06-pdf-headings`，分支 `claude/d06-pdf-headings`
- `base_commit`: `8eeac3b`（认领提交 `38ef62d`）
- 依赖：D05（`PdfLine`、`extract_pdf`、`to_parsed_document`）、D02（`heading_rank`）、D01（`ParsedDocument`、`SourceLocator`、`normalize_heading`），都已在 main。
- 依据：`docs/atomic-task-plan.md` D06 行；`docs/handoffs/claude-d05.md`「给 D06、D07 的中间结构」；`docs/architecture.md`「解析输出与来源定位（D01）」。

## 交付物

| 文件 | 内容 |
| --- | --- |
| `src/backend/app/services/parsers/pdf_headings.py` | 新增。`detect_headings`、`build_section_tree`、`to_sectioned_document`、`parse_pdf_with_headings`；`PARSER_VERSION = "pdf/1+headings/1"` |
| `tests/backend/test_d06.py` | 新增。34 个用例。行数据在代码中构造，另有 1 个端到端用例在测试里手写 PDF 字节，不入库 |
| `docs/tasks.md` | 只改 D06 那一张表的状态列和证据列 |

未改 `parsers/__init__.py`、`parsers/models.py`、`parsers/pdf.py`、`parsers/txt.py`、`tests/fixtures/documents/`、`pyproject.toml`，也没有新增依赖。`pdf_headings` 没有在 `parsers/__init__.py` 中重导出，调用方用 `from app.services.parsers.pdf_headings import ...`。

## 接口

```python
from app.services.parsers.pdf_headings import (
    HeadingResult, HeadingStrategy, PdfHeading, SectionNode,
    detect_headings, build_section_tree, to_sectioned_document, parse_pdf_with_headings,
)

result = detect_headings(lines)        # lines: Iterable[PdfLine]，可以是 D07 清洗后的子集
result.strategy                        # HeadingStrategy.FONT / NUMBERING / NONE
result.body_size                       # 正文字号
result.headings                        # tuple[PdfHeading(level, title, page, lines)]，按文档顺序
result.tree                            # tuple[SectionNode(title, level, page, children)]，章节树的根

doc = to_sectioned_document(lines, result)   # ParsedDocument，parser_version="pdf/1+headings/1"
```

- 标题行不成块，只进入后续块的 `section_titles`（与 D02～D04 一致）。块仍按「相邻且 `(page, box)` 相同」合并，标题会把所在文本框切开。每块只填原始 `page` 和 `section_titles`，不填 `paragraph` 和行号，因此 `to_source_fields()` 为 `{"page": n, "section_path": "第1章 绪论 > 1.1 基本概念"}`，没有标题时只有 `page`。
- 没有识别出标题时，输出与 D05 `to_parsed_document(lines, PARSER_VERSION)` 完全相同（有测试断言）。
- 全部行都是标题时，与 D02 一致，退回为不带标题的普通段落，不丢文本。没有任何行时抛 `DocumentUnreadableError(no_text)`。
- `parse_pdf_with_headings(data)` = `extract_pdf` + `to_sectioned_document`，**不做** D07 清洗。D11 编排时应按 `extract_pdf → D07 清洗 → to_sectioned_document` 的顺序串联。

## 判定规则与阈值

正文字号：按非空白字符数加权的最常见字号，相同时取较小者。

**策略 1：字号层级（`FONT`）**

| 规则 | 阈值 / 说明 |
| --- | --- |
| 大字号行 | 字号 ≥ 正文 + `MIN_SIZE_DELTA` = 1.0pt。选绝对差而不是比例，是为了兼容「五号 10.5pt 正文 + 小四 12pt 标题」（比值只有 1.14） |
| 字号簇 | 降序排列后，相邻字号相差 ≤ `SIZE_TOLERANCE` = 0.5pt 的归为同一簇 |
| 多行合并 | 相邻、样式相同（字号簇 + 是否整行加粗），且同页同框，或前一行是某页最后一行、后一行是紧接下一页的第一行（**跨页标题**）。后一行本身以编号开头时不合并。中文之间直接相连，两侧都是 ASCII 时加空格 |
| 候选文本 | 规范化后 1～`MAX_HEADING_CHARS` = 60 字；必须含字母或汉字（排除页码、符号）；不含「。；;」；不以「，,、：:….．」结尾；不含目录引导符（两个以上 `…`，或四个以上的点） |
| 启用条件 | 通过的大字号候选 ≥ `MIN_FONT_HEADINGS` = 2 个；只有一个（例如封面标题）时视为「无字号层级」 |
| 层级 | 样式按（字号簇降序，同字号加粗优先）依次为第 1、2…级 |
| 正文字号标题 | 需同时满足：整行加粗（`bold_ratio ≥ BOLD_LINE_RATIO` = 0.8）、以编号开头（D02 `heading_rank`）、独立成行（见下）。层级排在所有字号层级之后，再按编号层级细分。加粗编号标题自动换行时，续行只要也整行加粗、同框、合并后仍满足 `heading_rank`，就合并 |

**策略 2：编号正则退路（`NUMBERING`）**：不看字号与粗体。满足 D02 `heading_rank`（第X章/讲/节、一、、1.1、（一）等，单级「1.」「(1)」视为列表项）且独立成行的行为标题，层级就是 `heading_rank` 的值（章 1、节 2、「一、」与「1.1」为 3……），与 TXT 解析的层级一致。一个标题也没有时为 `NONE`。

**独立成行**（只用于正文字号的编号行）：

1. 同一文本框中，自上一个标题以来已有以冒号结尾的行 → 视为列表项（与 D02「冒号后的编号行是列表项」一致）；
2. 同框前一行存在时，它必须是标题、以句末标点「。！？!?；;」结尾，或没有排满到右边距（说明段落已结束）；
3. 本行排满到右边距、且同框下一行不是标题 → 是自动换行的段首（如「1.3 节所述的方法……」），不是标题。
   「排满」= `x1 ≥ 本页最右行 x1 − 2 × 正文字号`。

**验收对应**

- 正文加粗不误做所有标题：正文字号的行只看 `bold_ratio`（不看主字体 `bold`），行内加粗词达不到 0.8；整行加粗的正文、没有编号的短粗体行（「注意」「本节小结」）、整篇正文都用粗体的文档，都不会成为标题。
- 标题跨页：页底标题对下一页正文生效（标题栈跨页保持）；标题本身被分页拆开时合并，`PdfHeading.page` 取首行页码，`lines` 保留两页的原始行。
- 无字号层级有退路：退回编号正则，并有独立成行规则防止误判段落中的编号。

## 命令与实际结果

环境：macOS。系统 `python3`（anaconda 3.13.5）没有安装后端依赖，`python3 -m pytest tests/backend/test_d06.py -q` 在收集阶段报错（缺 `pdfminer`，exit 2），与本改动无关。因此在 scratchpad 建了 venv，从 PyPI 完整安装 `pip install -e './src/backend[test]'`，`pip check` 显示无冲突。下表中的 pytest 都用这个 venv 运行。

| 命令 | 结果 |
| --- | --- |
| 红灯：只有测试时运行 `python -m pytest tests/backend/test_d06.py -q` | 收集错误 `ModuleNotFoundError: No module named 'app.services.parsers.pdf_headings'`，exit 2 |
| 基线：实现前 `python -m pytest tests/backend -q` | 720 passed |
| 绿灯：`python -m pytest tests/backend/test_d06.py -q` | **34 passed**，exit 0 |
| 全部后端测试：`python -m pytest tests/backend -q` | **754 passed**，1 warning（main 已有的 Starlette/httpx 弃用提示），exit 0 |
| 反向篡改（逐项改坏 `pdf_headings.py` 后跑 D06，再恢复，`cmp` 确认与原文件一致） | 正文字号不要求加粗 → 1 failed；取消跨页合并 → 1；去掉编号退路 → 7；取消独立成行检查 → 2；整行加粗阈值降到 0.1 → 1；取消排满换行检查 → 1。恢复后 34 passed |
| `./scripts/verify.sh`（系统 python3） | exit 0（`Scaffold verification passed.`） |
| `git diff --check`（含暂存的新文件） | exit 0 |

## 风险

- **页眉页脚**：如果不先经过 D07 清洗，字号大于正文的页眉可能被当作重复标题（同名标题重复入栈，章节路径不变，影响有限）；页码行会阻断跨页标题的合并。D11 须先清洗再判定。
- **跨页合并**：页底和下一页页首恰好都是同样式、都不带编号的两个独立标题时，会被错误合并。排版通常会避免页底孤立标题，风险较低。
- **粗体识别**依赖 D05 的字体名规则：`SimHei` 这类名字里不带 Bold 的黑体不算粗体，所以正文字号的黑体编号标题在字号策略下不会被识别（编号退路只在没有字号层级时启用）。
- **不带编号、只加粗的正文字号标题**一律不识别，这是为满足「正文加粗不误判」而做的保守取舍。
- **只有一个大字号标题**时整体退回编号正则，这个大字号标题（通常是封面书名）不进入章节路径。
- **「排满」判断**取本页最右行作为右边距。双栏页的左栏行永远不算排满，因此独立成行的第 2、3 条在左栏会失效，更容易把段首编号误判成标题；只有短行的页上，最宽的行会被当成排满。
- **目录页**：只识别带引导符的目录行。没有引导符的目录项在编号退路下会被当成标题。
- 没有读取 PDF 书签（outline）：它可能比版面推断更准确，但 D05 的中间结构没有提供。
- 阈值是按常见中文教材排版设定的经验值，没有在真实课程资料上评测，需要 D-01 首批资料导入后抽样复核。

## 未决事项（请协调方决定）

1. D11 编排时的 `parser_version`：本任务定为 `pdf/1+headings/1`。D07 若也有自己的版本号，需要统一拼接规则（例如 `pdf/1+cleanup/1+headings/1`）。
2. 是否把 `pdf_headings` 的公开函数重导出到 `parsers/__init__.py`（不在本任务文件锁内）。
3. 是否需要读取 PDF 书签作为第一优先的标题来源（需要扩展 D05 的 `pdf.py`，须顺序认领）。

## 下一步

- 请 Codex 审查。合并后，D08 分块可以直接使用 `to_sectioned_document` 输出的 `section_titles`；D11 按「提取 → D07 清洗 → D06 判定」的顺序串联。

## 回滚

删除 `pdf_headings.py`、`test_d06.py` 和本交接，并把 `docs/tasks.md` 中 D06 行的状态和证据改回。不涉及依赖、数据或迁移。
