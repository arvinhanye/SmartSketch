# Codex 交接：D08 章节内语义分块

- `task_id`: D08；分支 `codex/d08-semantic-chunking`；基线 `8c94e46`；认领提交 `0bae415`。
- 输入：D01～D07 的 `ParsedBlock` 序列。输出：冻结的 `SemanticChunk` 序列；不修改解析器模型或解析结果。
- 文件：`src/backend/app/services/chunking.py`、`tests/backend/test_d08.py`、本交接。

## 接口与行为

```python
from app.services.chunking import chunk_blocks

chunks = chunk_blocks(parsed_document.blocks)
# 可覆盖 target_chars=1500、overlap_chars=200
```

- `SemanticChunk(ordinal, text, section_titles, sources)`：序号从 0 连续；`text` 供 D12 抽取；同一块只包含同一组 `section_titles`。标题变化立即结算当前章；相同章节后来再次出现也按连续 run 处理，不跨中间章节拼接。
- `ChunkSource(block_ordinal, start, end, locator)`：`[start,end)` 是原始 `ParsedBlock.text` 的字符切片；含全部 `SourceLocator` 字段（包括 PDF 原始物理页码、无页码格式的段落和行号）。多个来源和重叠来源均逐项保留。章节路径前缀和块间分隔符是展示文本，不映射成原文字符。
- 每个有 `section_path` 的来源片段前加 `section_path + "\\n"`，落实 D-13；PDF 没有标题时只输出正文、不制造章节路径。块编号、正文和定位对象原样保留。
- 目标长度预算包含章节路径前缀与分隔符。优先在目标附近（窗口长度 80%～100%）的句末或换行处断开；没有合适边界就按字符硬切长句、长段，保证推进。非末块下一窗口回退约 200 个展示字符；章际不重叠。空 iterable 返回空 tuple。
- 参数要求正整数目标、`0 <= overlap_chars < target_chars`。输入必须是从零连续的 `ParsedBlock` 序列；无新依赖、无数据库或 wire DTO 变更。

## 验证

测试先行：只有测试文件时，`test_d08.py` 在收集阶段因缺 `app.services.chunking` 红灯。实现后 6 个基本用例绿灯；自审时将前缀纳入预算，并增加多短段、无标题 PDF、参数校验用例，最终 9 个用例绿灯。

| 命令 | 结果 |
| --- | --- |
| `python3 -m pytest tests/backend/test_d08.py -q`（venv + 绝对 `PYTHONPATH`） | 9 passed |
| `python3 -m pytest tests/backend -q -p no:cacheprovider`（同环境；提权仅供已有 C13 本地端口测试） | 987 passed，1 条既有 Starlette/httpx 弃用警告 |
| `./scripts/verify.sh`（同 venv） | exit 0，`Scaffold verification passed.` |
| `git diff --check`（暂存后） | exit 0 |

系统 Python 3.11 没有安装 pytest；系统 Anaconda 的全套后端测试缺 FastAPI/pdfminer 等依赖。最终测试使用现有 `/private/tmp/c06-venv`。未提权的全套后端测试另有 2 个 C13 测试因沙箱禁止绑定 127.0.0.1 失败，并有 1 个 E02 子进程因相对 `PYTHONPATH` 找不到 `app` 失败；用绝对路径和现有测试要求的本地端口权限重跑后 987 passed。

## 风险、下一步与回滚

- 此处的“语义”边界是句末标点和段落换行，不是模型判句。单个超长表格/代码块也会硬切，符合前进性；后续可对 `BlockKind` 增加专门策略，但必须保持来源切片契约。
- 约 200 字符重叠是预算流（含路径前缀和分隔符）的长度；若重叠跨多个极短段落，原文正文的重复字数可能低于 200。长段内则是精确 200 字符。
- D09 可用 `ordinal` 与每项来源切片构造身份；D11 接收解析结果后调用 `chunk_blocks`，不需要解析器新增字段。
- 回滚：移除本任务的 `chunking.py`、`test_d08.py` 和交接文件；无迁移、依赖或已有格式改动。

## 独立审查修订（2026-09-25）

- 句末优先级现在也识别 ASCII 句点（后接空白或结尾），并排除小数点；中文句末标点、分号和换行行为不变。
- 分块按实际渲染的 `text` 限制每块不超过 `target_chars`，包括恢复的完整章节路径和块间分隔符。若 `section_path + "\\n"` 已占满目标、没有正文字符空间，则抛出 `ValueError`，不截断路径或静默丢弃来源；长路径还会相应收紧重叠，确保每个窗口有前进空间。
- 重叠规则仍按展示流（路径前缀、正文、分隔符）计字符；例如多短段测试中展示流重叠 50 字时，原文正文重叠为 24～25 字。路径/分隔符造成的差额是已知边界，来源切片仍覆盖全部正文且保持精确映射。
- 审查验证：D08 定向测试 13 passed；后端全套 991 passed（1 条既有 Starlette/httpx 弃用警告）；`./scripts/verify.sh` exit 0；另对 500 组随机短路径/长路径与分章输入验证了输出长度上限、章界隔离及来源覆盖。
