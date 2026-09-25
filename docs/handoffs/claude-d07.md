# Claude 交接：D07 重复页眉页脚清洗

- `task_id`: D07（GitHub issue #76）
- `review_status`: ready_for_review（DONE，待 PR 审查/合并）
- `worktree`: `/Users/arvinhan/Desktop/SmartSketch/.claude/worktrees/d07-header-footer`，分支 `claude/d07-header-footer`
- `base_commit`: `8eeac3b`（认领提交 `38ef62d`）
- 依赖：D05（`PdfExtraction`、`PdfPage`、`PdfLine`、`to_parsed_document`）已在 main，接口见 `docs/handoffs/claude-d05.md`。
- 依据：`docs/atomic-task-plan.md` D07 行；`docs/tasks.md`「2026-09-25 并行批次（Claude）」D07 表；`specs/grounded-qa.md` QA-5（引用须能展示原文与页码）。

## 交付物

| 文件 | 内容 |
| --- | --- |
| `src/backend/app/services/parsers/cleanup.py` | 新增。`clean_pages(source, options=None) -> CleanupResult`；`CleanupOptions`、`LineSpan`、`RemovedLine`、`RemovalReason`；`CLEANUP_VERSION = "cleanup/1"` |
| `tests/backend/test_d07.py` | 新增。43 个用例（含参数化），分页行全部在代码中构造；1 个端到端用例在测试中手写最小 PDF 字节交给 `extract_pdf` |
| `docs/tasks.md` | 只改 D07 表的状态与证据列 |

未改 `parsers/__init__.py`、`parsers/models.py`、`parsers/pdf.py`、`tests/fixtures/documents/`、`pyproject.toml`，无新依赖（只用标准库 `unicodedata`、`bisect`）。`cleanup` 未在 `parsers/__init__.py` 重导出，调用方用 `from app.services.parsers.cleanup import ...`。

## 接口

```python
from app.services.parsers.cleanup import CleanupOptions, clean_pages
from app.services.parsers.pdf import extract_pdf, to_parsed_document

result = clean_pages(extract_pdf(data))            # 也接受 PdfPage 可迭代对象
result = clean_pages(pages, CleanupOptions(enabled=False))   # 关闭清洗
doc = to_parsed_document(result.lines)             # 保留行仍带原始物理页码
```

`CleanupResult`（冻结 dataclass）：

| 字段/方法 | 含义 |
| --- | --- |
| `lines` | 保留的原始 `PdfLine` 对象，顺序不变，`page` 是原始物理页码 |
| `removed` | `RemovedLine(line, reason, original_start)`，`reason` ∈ `header` / `footer` / `page_number` |
| `original_text` | 全部输入行以 `\n` 连接 |
| `text` | 保留行以 `\n` 连接（清洗后文本） |
| `spans` | 每条保留行一个 `LineSpan(start, end, original_start, line)`，`page`/`index` 为原始页与页内行号 |
| `locate(offset)` | 清洗后位置 → 所在保留行；行间换行归前一行，`len(text)` 归最后一行；越界抛 `IndexError` |
| `to_original(offset)` | 清洗后位置 → `original_text` 中的位置；关闭清洗时恒等 |
| `spans_between(start, end)` | 清洗后半开区间覆盖的保留行（D08 可用来求块覆盖的页）；空区间返回 `start` 所在行 |
| `applied` | 是否真的删了行；关闭清洗、没有命中或触发兜底时为 False |

## 判定规则与阈值

只删「位于页首/页尾且跨页重复」的行，默认值在 `CleanupOptions`：

1. **页边位置**，两个条件都要满足：
   - 整行在页边带内：页眉要求行底 `y0 ≥ 页高 × (1 − header_ratio)`，页脚要求行顶 `y1 ≤ 页高 × footer_ratio`，默认 `header_ratio = footer_ratio = 0.10`（A4 即上下各 84.2pt）。
   - 按坐标是本页最靠上（或最靠下）的 `edge_lines = 2` 行之一。排名看坐标，不看阅读顺序，所以最后才绘制的页眉也能识别。
2. **跨页重复**：候选行先归一成模式（NFKC 把全角数字转成半角，合并空白，忽略大小写，连续数字记为 `#`）。整行是页码时，模式统一记为「页码」。能识别的页码写法：`3`、`- 3 -`、`— 3 —`、`第 3 页`、`第3页 共 9 页`、`Page 3`、`Page 3 of 9`、`p. 3`、`3 / 9`，以及 1～39 的小写或大写罗马数字。页眉和页脚分开统计。同一模式出现在至少 `max(2, min(min_pages=3, 有文字的页数))` 个不同页上才删除，空白页不计入页数。因此单页文档永不清洗，两页文档要两页都出现，三页及以上要至少 3 页出现。
3. **兜底**：如果清洗会删光全部行，就放弃清洗、原样返回（`applied=False`），以免下游误报 `no_text`。
4. **关闭清洗**：`enabled=False` 时 `lines` 等于全部行，`text == original_text`，`to_original(i) == i`，`removed == ()`。测试也确认它与 D05 `to_parsed_document(extraction.lines)` 的结果相同。
5. 只过滤行，不改写行文本；不读印刷页码去改写定位，来源页码始终是物理页序号。所以删掉罗马数字前言页码或错位的印刷页码后，块的 `page` 仍是阅读器的页码（与 D05 一致）。

## 关键决定

1. **位置映射以行为单位**：`LineSpan` 直接引用原始 `PdfLine`。从清洗后文本任一字符都能回到原始页、页内行号和原文偏移。测试 `assert_mapping_invariants` 逐字符验证：`original_text[to_original(i)] == text[i]`。
2. **页边带和最外侧行数同时约束**：只看页边带时，贴近页边的正文首行也可能落入带内；只看排名时，任何页首的正文行都会成为候选。两者一起用，再加上跨页重复，正文里重复的句子不会被删。
3. **数字归一**：让「第 N 页」这类带变化页码的页眉，以及所有页码行，都能识别为同一个模式。代价见风险 1。
4. `CLEANUP_VERSION = "cleanup/1"`。规则或默认阈值一旦变化就递增。是否并入 `RevisionKey.parser_version`（例如 `pdf/1+cleanup/1`）由 D11 决定，见未决事项。

## 实际验证

环境：macOS，Python 3.13.5 venv（在本会话的 scratchpad 中新建），在本 worktree 中执行 `pip install -e './src/backend[test]'`，从 PyPI 装到 pdfminer.six 20260107。

| 命令 | 结果 |
| --- | --- |
| 红灯：只有测试文件时运行 `python -m pytest tests/backend/test_d07.py -q`（venv） | 收集错误 `ModuleNotFoundError: No module named 'app.services.parsers.cleanup'`，exit 2 |
| 绿灯：同一命令 | **43 passed**，exit 0 |
| 反向篡改（逐项改坏 `cleanup.py` 后跑 D07，再从备份恢复） | 去掉页眉带位置检查 → 25 failed；不要求跨页重复（阈值为 1）→ 4 failed；忽略关闭开关 → 2 failed；映射退化为恒等 → 3 failed；不限最外侧行数 → 1 failed；去掉删光兜底 → 1 failed。恢复后 43 passed，`cmp` 确认与备份逐字节相同 |
| `python -m pytest tests/backend -q`（venv） | **763 passed**，1 warning（main 已有的 Starlette/httpx 弃用提示），exit 0 |
| `python3 -m pytest tests/backend/test_d07.py -q`（系统 anaconda python3） | exit 2：`No module named 'app'`。系统解释器没有安装后端包，与本改动无关 |
| `python3 -m pytest tests/backend -q`（系统 python3） | exit 2：13 个模块收集错误（9 个 `No module named 'app'`，4 个 `No module named 'fastapi'`），原因同上，既有环境问题 |
| `./scripts/verify.sh` | exit 0（Scaffold verification passed） |
| `git diff --check` | exit 0 |

## 风险

1. **数字归一可能误删**：如果页边带内最外侧的行只有数字不同（例如每页顶端都是「例 3.N」），而且连续出现在 3 页以上，会被当成页眉删掉。篡改实验也说明，去掉页边带检查后，只有数字不同的正文首行会被误删。页边带是主要防线。
2. **页边带宽度固定为页高的 10%**：页眉离正文很近（上边距小于 10% 页高），而正文首行又恰好跨页重复时，会误删。反过来，页眉落在 10% 之外（大页边距排版）时，不会被识别。两个比例都可以通过 `CleanupOptions` 调整。
3. **少于 3 页的章节页眉不删**：每章只有 1～2 页的讲义里，章节级页眉会留在正文中。它只会在块中多出一行，不影响定位。
4. **页眉与正文在同一 pdfminer 行**：如果 pdfminer 把页眉和正文合成一行（极少见），该行不会落在页边带内，不会被删。
5. **印刷页码不做校验**：不检查数字是否递增。页脚里跨页出现的纯数字都会被当作页码删掉，例如脚注编号恰好在页底最外侧的情况。

## 未决事项（请协调方决定并登记）

1. 是否把 `CLEANUP_VERSION` 并入修订的 `parser_version`（D11）。清洗规则变化会改变块文本，进而影响 D09 块身份。
2. D11 编排时默认开启清洗，是否需要课程级或资料级的关闭开关（接口层）。本任务只提供 `CleanupOptions(enabled=False)`。
3. D06 标题判定与 D07 的先后：建议先 `clean_pages`，再用 `result.lines` 做标题判定，以免页眉被误认为标题。这需要 D06/D08 的调用方确认。

## 下一步

- 请 Codex 审查。合并后，D08 用 `result.lines`（或 D06 在其上得到的带标题结果）分块。块跨页时可以用 `spans_between` 求覆盖的页。
- `architecture.md`「解析输出与来源定位（D01）」可以补一句：PDF 先清洗页眉页脚，定位仍是物理页。该文件是共享文件，交由协调方处理。

## 回滚

删除 `src/backend/app/services/parsers/cleanup.py`、`tests/backend/test_d07.py` 和本交接，并把 `docs/tasks.md` 中 D07 表的状态和证据改回。不涉及数据、依赖或迁移。
