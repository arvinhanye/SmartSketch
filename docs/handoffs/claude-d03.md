# Claude 交接：D03 Markdown AST 解析

- `task_id`: D03（GitHub issue #72，协调方已在 `claude/claim-d02-d05` 认领）
- `review_status`: ready_for_review
- 分支：`claude/d03-markdown-parser`，base `origin/main` `588d00a`（PR #188 合入后）；放宽标题前已合并 `origin/main`（`6ba260d`，含 D02）
- 依赖：D01（`ParsedDocument` 等模型，已在 main）
- 依据：`docs/atomic-task-plan.md` D03 行；`docs/architecture.md`「解析输出与来源定位（D01）」；`docs/handoffs/claude-d01.md`

## 交付物

| 文件 | 内容 |
| --- | --- |
| `src/backend/app/services/parsers/markdown.py` | `PARSER_VERSION = "markdown/1"`；`parse_markdown(data: bytes) -> ParsedDocument` |
| `tests/backend/test_d03.py` | 66 个用例（含参数化；首版 48 个，放宽无空格标题后 66 个），覆盖成功、边界、失败三类，外加固定种子随机组合检查 |
| `src/backend/pyproject.toml` | `dependencies` 新增一行 `"markdown-it-py==4.2.0"`，其余未动 |
| `docs/handoffs/claude-d03.md` | 本交接 |

未改 `parsers/__init__.py`、`parsers/models.py`、`tests/fixtures/documents/`、`docs/tasks.md`、`docs/architecture.md`、`docs/integrations.md`、`scripts/verify.sh`，也未改 `pyproject.toml` 的 `test` 组。`markdown.py` 没有加入 `parsers/__init__.py` 的重导出，调用方需从 `app.services.parsers.markdown` 导入（是否统一重导出由协调方在 D02～D05 合并后决定）。

## 选库与许可（请协调方登记到 `docs/integrations.md`）

| 包 | 版本 | 许可 | 引入方式 | 说明 |
| --- | --- | --- | --- | --- |
| `markdown-it-py` | `==4.2.0`（本次 `pip index versions` 查到的最新版） | MIT（`License :: OSI Approved :: MIT License`） | 直接依赖 | `Requires-Python >=3.10`，满足项目 `>=3.11`；CI 为 3.12，本地验证用 3.13.5 |
| `mdurl` | 0.1.2 | MIT | 传递依赖（`markdown-it-py` 声明 `mdurl~=0.1`） | 按文件锁只加一行，未单独固定 |

选择理由：

- 真正的 CommonMark 解析器，符合规范测试集，围栏/缩进代码块、Setext 标题、引用块、嵌套列表都按规范切分，不需要自己写正则逐行猜。
- 每个块级 token 带 `map = [起始行, 结束行)`，可直接得到 D01 要求的物理行号，块文本能按行号映射回原文。
- 内置 GFM 表格规则（`enable("table")`），无需插件。
- 纯 Python，无编译依赖；唯一传递依赖 `mdurl` 也是 MIT。
- 未选：`commonmark.py`（官方已声明弃用，并推荐改用 markdown-it-py）；`mistune`（BSD）与 `marko`（MIT）的默认 AST 不直接给出块级源行号，需要额外改造；`mdit-py-plugins` 虽有 front matter 插件，但会多一个依赖，front matter 改由本模块做最小预处理（见下）。

## 关键决定

1. **只看顶层块 token**（`level == 0`）。标题只取顶层 ATX/Setext 标题；引用块、列表项内部的 `#` 行或标题不改变章节路径，随所在块保留在文本中。
2. **块类型映射**：段落 → `PARAGRAPH`；有序/无序列表（含全部嵌套层）整体一个 `LIST` 块；表格一个 `TABLE` 块；围栏与缩进代码块 → `CODE`；引用块整体 → `PARAGRAPH`；HTML 块 → `PARAGRAPH`（只有 HTML 注释的块丢弃）；分隔线与链接引用定义不成块。
3. **块文本 = 原文行**：`text` 是解码、统一换行后的第 `line_start`～`line_end` 行原样拼接，保留 Markdown 标记（表格竖线、列表符号、代码围栏、行内 `**`、链接）与缩进。`map` 带的尾部空行会被去掉，所以块首尾都不是空行。去掉空白后为空的块（空代码块、只有全角空格的行）丢弃，不交给 D01。
4. **标题文本**：取行内纯文本（去掉强调、链接、行内代码的标记，图片取替代文本，内联 HTML 丢弃），再经 `normalize_heading`（半角 `>` 变 `＞`）。`## 标题 ##` 的收尾 `#` 由解析器去掉。空标题（如单独的 `##`）忽略，不改变路径。
5. **标题层级跳跃**：用栈维护路径，新标题弹出所有同级和更深的标题再入栈。`#` 后直接 `###` 得到两级路径（不补空层级）；之后的 `##` 会关闭 `###`。文档从 `###` 开始时路径只有一级。
6. **front matter**：只有第 1 行（去 BOM 后）是 `---`，且后面某行是 `---` 或 `...` 时，才把这一段当作 YAML front matter，替换成空行后再交给 markdown-it，不成块、不参与标题，行号不偏移。未闭合的 `---` 按 CommonMark 处理（分隔线）。不支持 TOML `+++`。代价：以分隔线开头、之后又出现单独 `---` 行的文档，开头这一段会被当作 front matter 丢掉。
7. **解码与换行**：严格 UTF-8，允许开头 BOM 并去掉。解码失败 → `DocumentUnreadableError("corrupted", "不是有效的 UTF-8：第 N 字节起无法解码")`；含 NUL 字节 → `corrupted`（疑似二进制）。不做 GBK 回退：Markdown 生态默认 UTF-8，编码探测属于 D02 的 TXT。`\r\n` 和单独的 `\r` 统一为 `\n`（与 markdown-it 自身的规范化一致）后按 `\n` 计物理行，所以 CRLF/CR 文件的行号与 LF 相同。块文本中不含 `\r`。
8. **空文**：空文件、只有空白（含全角空格、只有 BOM）、只有标题、只有 front matter / HTML 注释 / 分隔线 / 空代码块 / 链接引用定义 → `DocumentUnreadableError("no_text")`。只有标题时 `detail` 为「只有标题，没有正文」，其他为「没有可提取的正文」。
9. **放宽「`#` 后无空格」的标题写法**（ArvinHan 决定，2026-09-24；PR 合并前补入，没有资料按旧规则入库，所以 `PARSER_VERSION` 仍为 `markdown/1`）：
   - **规则**：行首（最多 3 格缩进）1～6 个 `#`，紧跟一个**非 ASCII、非空白、非 `#`** 的字符，按 ATX 标题处理，层级等于 `#` 的个数。例：`#第一章 绪论` → 一级「第一章 绪论」；`##概述` → 二级；`###（一）背景 ###` → 三级「（一）背景」（和标准 ATX 一样，空白后的收尾 `#` 会去掉）。标题文本同样取行内纯文本，再经 `normalize_heading`。
   - **不放宽的情况**：紧跟 ASCII 字符的行，如 `#include <stdio.h>`、`#1`、`#tag`、`#!/bin/sh`，以及 `###1.1顺序表`（首字符是 ASCII 数字；为了不误伤 `#1` 这类写法，宁可漏判）；7 个及以上 `#`；`#` 后紧跟全角空格（`#　第一章`，全角空格属空白）；`\#第一章`（转义）；结尾 `#` 紧贴文字的话题标签（`#话题#`）；缩进 4 格（缩进代码块）。
   - **实现**：在 markdown-it 里注册块规则 `loose_heading`，排在内置 `heading` 之前，产出与内置规则相同的 `heading_open / inline / heading_close` token 和 `map`。不改源文本，行号和块文本都不受影响。它能打断段落和引用块的懒惰续行（`alt = paragraph, reference, blockquote`，与内置 ATX 规则相同），所以 `前言。\n#第一章` 和 `前言。\n# 第一章` 结果一致。
   - **只影响顶层**：围栏代码块内的行由 `fence` 规则整体吃掉，不会走到这条规则。引用块、列表项内部的 `#第一章` 可能在嵌套层级生成标题 token，但 `parse_markdown` 只看顶层 token，这些行不改变章节路径，原样留在所在的 `PARAGRAPH` 或 `LIST` 块文本里。这和嵌套位置的 `# 标题` 处理一致。没有给规则加「只在顶层」的限制，是为了让列表、引用块的结束位置与标准 ATX 标题一样，不因写法不同而把后面一行吞进列表。
10. **输入类型**：接受 `bytes`、`bytearray`、`memoryview`；`str` 等其他类型抛 `TypeError`（调用方缺陷，不是资料问题）。

## 接口说明（给 D08 / D11）

```python
from app.services.parsers.markdown import PARSER_VERSION, parse_markdown

doc = parse_markdown(raw_bytes)          # ParsedDocument
doc.source_format                        # SourceFormat.MARKDOWN
doc.parser_version                       # "markdown/1"，D11 用它构造 RevisionKey
for block in doc.blocks:                 # 按 ordinal 0.. 排列
    block.kind                           # PARAGRAPH / LIST / TABLE / CODE
    block.text                           # 原文第 line_start～line_end 行，保留 Markdown 标记
    block.locator.section_titles         # 顶层标题路径（已规范化）
    block.locator.paragraph              # 同一标题路径下的序号，从 1 起
    block.locator.line_start/line_end    # 物理行号，闭区间，块间递增不重叠
    block.locator.to_source_fields()     # {"section_path": "第3章 栈与队列 > 3.1 顺序栈 > 第2段"}
```

- **D08**：一个 `LIST`、`TABLE` 或 `CODE` 块就是一整张表 / 一整个列表 / 一整段代码，尽量不要从中间切开；过长时再按行切，行号可由 `line_start` 加块内行偏移算出。块文本含 Markdown 标记，抽取前是否渲染为纯文本由 D08 或 E 组决定。
- **D11**：捕获 `DocumentUnreadableError`，映射为 `DOCUMENT_UNREADABLE`，`details.reason = err.reason.value`（本解析器只会给 `no_text` 或 `corrupted`）；`TypeError` 与 `ParseModelError` 都属实现缺陷。
- **与 D02 对齐的建议**：D02～D05 若都采用 `PARSER_VERSION` 常量 + `parse_<格式>(data: bytes) -> ParsedDocument` 的形状，D11 可以按 `SourceFormat` 查表分派。D02（TXT）对 CR 换行、BOM 的行号计法最好与本模块一致。

## 命令与结果

环境：macOS，Python 3.13.5（anaconda 的 python3 建的独立 venv），`pip install -e './src/backend[test]'`，`pip check` 无冲突。

| 命令 | 结果 |
| --- | --- |
| 红灯：实现前 `pytest tests/backend/test_d03.py -q`（提交 `c394fe0`） | 收集错误 `ModuleNotFoundError: No module named 'app.services.parsers.markdown'` |
| 绿灯：`pytest tests/backend/test_d03.py -q` | **48 passed** |
| 全部后端 `pytest tests/backend -q` | **522 passed**，1 warning（main 已有的 Starlette `httpx` 弃用提示，与本任务无关） |
| `./scripts/verify.sh`（系统 python3，输出写入文件后单独取 `$?`） | **exit 0**，末行 `Scaffold verification passed.` |
| `git diff --check origin/main...HEAD` | **exit 0** |
| 反向篡改（逐项改坏 `markdown.py` 后跑 D03，再恢复） | 标题/块不限顶层 → 28 failed；不跳过 front matter → 2；不去尾部空行 → 3；不丢弃 HTML 注释 → 2；不丢弃空代码块 → 2；不检查 NUL → 1；同级标题不出栈 → 4；不去 BOM → 3；标题直接用原始行内文本 → 1；不统一 CR → 2；不启用表格 → 3；恢复后 48 passed |
| 随机组合检查（临时脚本，20000 份随机拼接的 Markdown，含 CRLF） | 19391 份得到合法 `ParsedDocument`，609 份 `no_text`，无 `ParseModelError`，块文本全部能按行号映射回原文。测试文件里保留了 1500 份的固定种子版本 |

### 放宽无空格标题（ArvinHan 决定后补入同一 PR）

先把 `origin/main`（含 D02 PR #190、任务板 PR #189、B07 PR #192）合并进分支，合并提交为 `6ba260d`，无冲突。B07 改了 `test` 组，因此重新在 `venv-d03` 里执行了 `pip install -e './src/backend[test]'`。

| 命令 | 结果 |
| --- | --- |
| 红灯：只加用例后跑 `pytest tests/backend/test_d03.py -q`（提交 `b070825`） | **3 failed** / 63 passed。失败的是 3 个正向用例：`#第一章`、`##概述` 成为标题，打断段落，标题文本规范化。`#include`、`#1`、`#tag`、容器内 `#第一章` 等反向用例本来就通过，保留作回归护栏 |
| 绿灯：`pytest tests/backend/test_d03.py -q` | **66 passed** |
| 全部后端 `pytest tests/backend -q` | **634 passed**，1 warning（同上，Starlette `httpx` 弃用提示） |
| `./scripts/verify.sh`（输出写入文件后单独取 `$?`） | **exit 0** |
| `git diff --check origin/main...HEAD` | **exit 0** |
| 反向篡改（逐项改坏放宽规则后跑 D03，再恢复） | 不注册规则 → 3 failed；允许 ASCII 首字符 → 6；不排除话题标签 → 1；不能打断段落 → 1；不去收尾 `#` → 1；允许 7 个 `#` → 1。去掉 `is_code_block` 检查后测试仍全过：缩进 4 格的行在顶层先被 `code` 规则吃掉，在段落里又被 `paragraph` 规则直接当作续行，这条检查只是与内置规则保持一致的防御，去掉它是等价改动 |
| 随机组合检查（临时脚本 20000 份，加入 `##概述`、`#话题#`、`#include x`、`> #引用`、`- #项` 等片段） | 19344 份合法、656 份 `no_text`，无 `ParseModelError`，块文本全部能按行号映射回原文。测试里固定种子的 1500 份版本也加入了 `##概述`、`#话题#`、`#include x`、`> #引用` |

说明：系统 python3 没有安装后端包，直接运行 `python3 -m pytest tests/backend/test_d03.py -q` 会报 `No module named 'app'`（D01 交接已记录的环境问题）；上述 pytest 结果都来自 venv。

## 风险

- **放宽标题的边界**：`###1.1顺序表`、`#　第一章`（全角空格）这类写法仍按正文处理，章节路径会变浅。以后如果要继续放宽，属于解析规则变化，届时须把版本升到 `markdown/2`。非 ASCII 首字符的误判面较小，但像 `#话题` 这样没有收尾 `#` 的中文话题标签，会被当成标题。
- **front matter 误判**：见关键决定 6。以分隔线开头的讲义较少见，暂接受。
- **HTML 块原样保留**：`<div>`、`<table>` 等 HTML 以源码形式进入 `PARAGRAPH` 块，HTML 表格不会标为 `TABLE`。课程资料若大量内嵌 HTML，D08/抽取阶段可能需要剥离标签。
- **引用块内的表格或代码**整体标为 `PARAGRAPH`，D08 可能从中间切开。
- **不做 GBK 回退**：GBK 编码的 `.md` 会得到 `corrupted`。若教师常上传 GBK 的 Markdown，可以复用 D02 的编码探测，届时提升为 `markdown/2`。
- **依赖升级会改变输出**：升级 `markdown-it-py` 可能改变 token 切分或行号，应视为解析规则变化，同步提升 `PARSER_VERSION`（ADR-012 修订 1：修订按解析器版本区分）。
- markdown-it 的 `maxNesting`（CommonMark 预设为 20）以下的超深嵌套不会被逐层解析，但顶层块的行号仍然正确，只影响块内结构，不影响本模块输出。

## 下一步

- 请 Codex 审查；协调方合并时：更新 `docs/tasks.md` 的 D03 行与证据，把上面的选库信息登记到 `docs/integrations.md`，并与 D04、D05 在 `pyproject.toml` `dependencies` 的一行改动按顺序解决文本冲突。
- 决定 `parsers/__init__.py` 是否重导出各格式的 `parse_*` 函数（本任务按文件锁未改）。
- D08 可在 D02～D07 合并后开工。

## 回滚

只新增 `markdown.py`、`test_d03.py` 和本交接，并在 `pyproject.toml` 加一行依赖。回滚时删除这三个文件、去掉该行依赖即可；无数据、契约或迁移变更。
