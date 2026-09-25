# Claude 交接：D02 TXT 编码与标题解析

- `task_id`: D02（GitHub issue #71）
- `review_status`: ready_for_review
- `worktree`: `/Users/arvinhan/Desktop/SmartSketch/.claude/worktrees/agent-a6e6226be56d04b53`，分支 `claude/d02-txt-parser`
- `base_commit`: `588d00a`（origin/main，PR #188 合入后，含 D01）
- 依赖：D01（`src/backend/app/services/parsers/models.py`）。只用标准库，无新依赖。
- 文件锁：只写了 `src/backend/app/services/parsers/txt.py`、`tests/backend/test_d02.py` 和本交接。未改 `parsers/__init__.py`、`models.py`、fixture、`docs/tasks.md`、`docs/architecture.md`、`scripts/verify.sh`、`pyproject.toml`。

## 交付物

| 文件 | 内容 |
| --- | --- |
| `src/backend/app/services/parsers/txt.py` | `PARSER_VERSION = "txt/1"`；`decode_txt(bytes) -> DecodedText(text, encoding)`；`heading_rank(line) -> int \| None`；`parse_txt(bytes) -> ParsedDocument`。规则写在模块说明里 |
| `tests/backend/test_d02.py` | 94 个用例（含参数化），覆盖成功、边界、失败三类，外加一组「像编号但应是正文」的误判用例 |

## 接口（给 D08、D11）

```python
from app.services.parsers.txt import PARSER_VERSION, decode_txt, heading_rank, parse_txt

doc = parse_txt(raw_bytes)   # ParsedDocument(SourceFormat.TXT, "txt/1", blocks)
```

- 输入只接受 `bytes`，其他类型抛 `TypeError`。无 I/O，无全局状态。
- 输出每块：`kind = paragraph`（TXT 没有表格或代码标记）；`page = None`；`section_titles` 为当前标题栈（已 `normalize_heading`）；`paragraph` 按 D01 规则编号；`line_start`/`line_end` 是解码后源文本的物理行号（从 1 起的闭区间）。
- 块文本是 `line_start..line_end` 各行原文按 `\n` 连接，保留缩进和行尾空白，不含 `\r`。D08 可以按行号把 Chunk 映射回原文。
- 标题本身不成块，只进入后续块的 `section_titles`。标题后面没有正文时，该标题不出现在任何块里。
- 失败：`DocumentUnreadableError(no_text)` 表示没有可见文本；`DocumentUnreadableError(corrupted)` 表示无法解码，`detail` 是中文原因（含字节位置），便于排查。D11 按 D01 交接映射为 `DOCUMENT_UNREADABLE`。
- `decode_txt` 只做解码，返回 `encoding ∈ {utf-8, utf-8-sig, gbk}`，可用于日志。空文本不在这一步报错。
- `heading_rank` 公开，便于 D03 或评测复用同一套中文编号规则。

## 关键决定

### 编码检测（顺序执行）

1. 以 UTF-8 BOM 开头：视为已声明 UTF-8，去掉 BOM 后严格解码；解不开就报 `corrupted`，不再试 GBK。
2. 严格按 UTF-8 解码。
3. UTF-8 失败，且第一个错误是文末被截断的多字节字符（此前已有合法的非 ASCII 字符）：判为被截断的 UTF-8，报 `corrupted`。这种字节常常恰好能按 GBK 解码，回退只会得到乱码。测试 `test_truncated_utf8_that_happens_to_be_valid_gbk_is_corrupted` 用 fixture 前 14 字节复现了这种情况。
4. 严格按 GBK（Python `gbk` 编解码器）解码；失败报 `corrupted`。
5. 解码结果含 NUL 时报 `corrupted`，识别改了扩展名的二进制文件和 UTF-16 文本。

- **坏编码用 `corrupted`**：`reason` 闭集只有 corrupted、encrypted、no_text。字节存在但无法还原成文本，属于资料损坏；`no_text` 只留给解码成功但没有可见文本的情况（空文件、只有空白、只有 BOM、只有 Ctrl-Z）。
- **不用 GB18030**：它几乎能接受任意字节，会把坏文件静默解成乱码。GBK 更严格，能识别出更多坏编码。
- **曾实现后撤回的规则**：首版还有一条比例规则（合法非 ASCII 字符数 ≥ 坏字节段数 × 8 时判为坏 UTF-8）。抽样 30 万次都找不到「UTF-8 中间夹坏字节、又能被 Python GBK 解码」的样例，这条规则成了没有测试覆盖的死代码，所以在第三个提交中删除。

### 分段

- 物理行只按 CRLF、CR、LF 切分。不用 `str.splitlines()`，因为它还会在 `\f`、`\v`、NEL、U+2028/2029 处断行，导致行号和编辑器看到的不一致。有测试锁定。
- 空行（只含空白，包括全角空格）分段；标题行也会结束当前段落。
- 以全角空格 U+3000 开头的行另起一段，适配「首行缩进两字、段间不空行」的中文排版。半角空格缩进不分段，避免把整体缩进的引文切碎。
- 文末的 Ctrl-Z（`\x1a`，DOS 文件结束符）忽略。
- 整篇只有标题、没有正文时，关闭标题判定重新分段，把这些行当普通段落输出。理由是不丢弃用户的文本；只含空白才报 `no_text`。

### 标题判定与层级

对去掉首尾空白的整行判定。通用条件：不超过 40 字；不含「。」「；」「;」；不以「，,、：:….．」结尾。

| 形式 | 例 | 层级 |
| --- | --- | --- |
| 第X章、讲、课、单元、部分、篇 | 第一章 线性表、第二十讲：散列 | 1 |
| 第X节 | 第一节 顺序栈 | 2 |
| 中文数字 + 「、」 | 一、基本术语 | 3 |
| 两级数字编号 | 1.1 顺序表、3.2顺序栈 | 3 |
| （中文数字）或 (中文数字) | （一）入栈 | 4 |
| 三级、四级数字编号 | 1.1.1 逻辑结构 | 4、5 |

- 层级固定，不按出现顺序推断。新标题先弹出层级 ≥ 自身的祖先再入栈，`section_titles` 即标题栈。缺级不影响（如「第二章」下直接出现「二、」）。
- 「第X章」后必须是行尾、空白或「：:、.．」之一；数字编号首段为 1～99、其余段为 0～99 且无前导零，最多四级，后面接空白再接标题，或直接接汉字。
- 单级阿拉伯编号（「1.」「1、」「(1)」「（1）」）一律当列表项，不当标题。没有编号的行（包括 fixture 首行的文档名）不当标题，作为第一个段落「第1段」。
- 以冒号结尾的正文行之后，到下一个空行为止，编号行都算列表项，留在同一段里。

## 误判边界（已知、未处理）

- **会被误判为标题**：以编号开头、不到 40 字、又不含句号分号的正文行，例如「3.14 是圆周率的近似值」「第一章 讲的是线性表」「一、线性结构」（前一行不以冒号结尾时）。这类行会开启一个新小节，后续段落的章节路径随之改变。
- **会漏判的标题**：无编号标题（如「绪论」「参考文献」）；「第一章线性表」这类「章」后没有分隔符的写法；全角数字的多级编号「１．１」；超过 40 字或含句号的标题；紧跟在冒号行后面、中间没有空行的真标题。
- **中文编号和数字编号同属第 3 层**：「一、」和「1.1」在同一文档混用时会被当作兄弟节点，而不是父子节点。
- **编码歧义**：非常短、几乎全是 ASCII 的 GBK 文本（如只含一个「栈」字），可能恰好是合法 UTF-8，会按 UTF-8 解出错字。反过来，UTF-8 在文末截断、且此前没有任何非 ASCII 字符时，会回退 GBK。UTF-8 中间夹坏字节、同时整篇又恰好是合法 GBK 的情况，抽样中没有出现；如果出现，会按 GBK 解出乱码。
- 不支持 UTF-16/UTF-32、Big5、GB18030 独有字符，这些都会报 `corrupted`。

## 实际验证（macOS，Python 3.13.5，venv 位于会话 scratchpad，`pip install -e <本 worktree>/src/backend[test]`）

| 命令 | 结果 |
| --- | --- |
| 红灯：只提交测试后 `pytest tests/backend/test_d02.py -q` | 收集错误 `ModuleNotFoundError: No module named 'app.services.parsers.txt'`，exit 2 |
| 绿灯：`pytest tests/backend/test_d02.py -q` | 94 passed |
| 全部后端：`pytest tests/backend -q` | 568 passed，1 warning（main 已有的 Starlette `httpx` 弃用提示） |
| 反向篡改（scratchpad 脚本逐项改坏 `txt.py` 后跑 D02，再恢复原文件） | 取消截断判定 1 failed；取消 NUL 检查 2；带 BOM 也回退 GBK 4；取消冒号列表规则 2；取消全角缩进分段 1；取消只有标题的回退 1；取消 40 字上限 1；改用 `splitlines` 1；段落号不接续 11；所有标题同级 6；数字编号允许前导零 1；不忽略 Ctrl-Z 2。恢复后 94 passed |
| `./scripts/verify.sh`（系统 python3，输出重定向到文件，单独取 `$?`） | exit 0，末行 `Scaffold verification passed.`（约 2 分钟以上，主要耗在契约检查） |
| `git diff --check origin/main` | exit 0 |

- **环境注意**：第一次在 scratchpad 建 venv 并 `pip install -e './src/backend[test]'` 时，editable finder 指向了另一个 worktree（`agent-a1c14389d12099b90`）的 `src/backend/app`，导致 `app.services.parsers.txt` 找不到。改用本 worktree 的绝对路径，并加 `--no-cache-dir --force-reinstall --no-deps` 重装后恢复正常。上表结果全部来自重装之后。其他 worktree 共用 venv 时，建议先检查 `__editable___*_finder.py` 里的 `MAPPING`。
- 本 worktree 的 `src/backend/smartsketch_backend.egg-info` 已被 `.gitignore` 忽略，未提交。

## 风险

- 标题判定是启发式规则，真实课程 TXT 的格式可能超出上表。规则有任何改变都必须把 `PARSER_VERSION` 递增为 `txt/2`，资料修订（ADR-012 修订 1）才会随之变化。
- 标题只进入 `section_titles`，本身不成块，所以标题文字不会进入 Chunk 正文。例如「1.1 顺序表」这几个字只出现在来源路径里。如果 D12 抽取需要看到标题文字，由 D08 在 Chunk 前拼接路径，或回到 D01 另议。
- 未做 50 MiB 级大文件的性能测试。实现是逐行线性扫描，按行跑正则，预计可以接受。

## 下一步

- 请 Codex 审查。
- 协调方：在 `docs/tasks.md` 登记 D02 状态与验收证据（不在本任务文件锁内）。
- D08：按上文「接口」消费；Chunk 映射回原文时可直接用块的 `line_start`/`line_end`。
- D03（Markdown）如需同一套中文编号规则，可复用 `heading_rank`。

## 回滚

只新增 `txt.py`、`test_d02.py` 和本交接三个文件，删除即可回滚。无数据、依赖或配置变更。
