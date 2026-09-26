---
review_status: ready_for_review
task_id: TD-01
worktree: .claude/worktrees/a1-a10-meta-task-wrap-ddbf4b
branch: claude/pdf-parser-version-tech-debt-e95eaf
base: ddbeb82
---

# TD-01 交接：PDF 解析器版本定稿、E04 问答截止时间、改写预写失败口径

## 任务与状态

来自 D11（#239）、J03（#242）、C10/C11 实现中发现的四个问题，ArvinHan 在会话中确认「按建议修改」。状态：DONE，待 PR 审查。

| 项 | 处理 |
| --- | --- |
| 1 PDF 解析器版本 | ADR-018 修订 1：解析器段内多个步骤用 `,` 连接、按处理顺序排列，`+` 只作分块段分隔符。D06 定常量，D09 按新格式严格校验 |
| 2 问答重试时长 | E04 增加截止时间（不采用 J07 关闭重试的办法） |
| 3 服务层读任务 SQL | 新建 TD-02（TODO），等 C10/C11/D11 合并后再做 |
| 4 改写调用预写失败 | 确认 J03 的理解：改用原问题；已在 `docs/integrations.md` 与 `specs/grounded-qa.md` P3 写明 |

## 改动文件与关键决定

- `src/backend/app/services/parsers/pdf_headings.py`：`PARSER_VERSION = "pdf/1,headings/1"`（不清洗路径）；新增 `CLEANED_PARSER_VERSION = "pdf/1,cleanup/1,headings/1"`（D05 → D07 → D06，D11 应引用）。取值与 D11 的临时写法逐字相同，不产生块 ID 迁移。
- `src/backend/app/services/chunk_identity.py`：解析器段校验收紧为 `<名称>/<版本>(,<名称>/<版本>)*`，名称 `[a-z][a-z0-9_-]*`，版本为无前导零正整数，只收 ASCII。
- `src/backend/app/services/ai/policy.py`：`bind(attribution, *, deadline=None)`；每次请求超时取「请求自身超时」与「剩余时间」的较小者（请求未设超时则取剩余时间）；退避会到达截止时间时不等待，改试备用；无剩余时间时不写 `model_calls`、不发请求；新增 `CallDeadlineExceededError`（`code = LLM_UNAVAILABLE`、`reason = "timeout"`，`__cause__` 为最后一次供应商错误）。不传 `deadline` 时行为不变。
- 文档：`docs/decisions.md`（ADR-018 修订 1）、`docs/architecture.md`（资料修订一行）、`docs/integrations.md`（调用记录第 1 条、新增「问答链路截止时间」段）、`specs/grounded-qa.md`（链路时限、P3）、`docs/tasks.md`（TD 节）。
- 测试：`test_d06.py`（两个版本常量）、`test_d09.py`（16 个格式负例、4 个正例、全部解析器模块常量都能进入修订键；字段边界用例改用合法版本）、`test_e04.py`（12 个截止时间用例）。

## 已运行命令与结果

以下 `<venv>` 为本机 scratchpad 中按 `pip install -e './src/backend[test]'` 建的虚拟环境（Python 3.13）。

| 步骤 | 命令 | 结果 |
| --- | --- | --- |
| E04 红灯 | 旧 `policy.py` + 新测试：`PYTHONPATH=$PWD/src/backend <venv>/bin/python -m pytest tests/backend/test_e04.py -q` | `12 failed, 67 passed` |
| E04 绿灯 | 同上，新实现 | `79 passed` |
| D09 红灯 | 旧 `chunk_identity.py` + 新测试：`... -m pytest tests/backend/test_d09.py -q` | `15 failed, 160 passed` |
| D06/D09 绿灯 | `... -m pytest tests/backend/test_d06.py tests/backend/test_d09.py -q` | `210 passed` |
| 后端全量 | `PYTHONPATH=$PWD/src/backend <venv>/bin/python -m pytest tests/backend -q` | `2140 passed, 1 warning` |
| D11 兼容 | 在 `origin/claude/d11-parse-worker` 的临时 worktree 上只套用本任务的 `src/backend` 改动，运行 `-k "d11 or d09 or d06 or e04"` | D11 全部通过；仅 2 个旧的 D06/D09 用例失败（它们断言旧格式，本任务已改），属预期 |
| 门禁 | `./scripts/verify.sh` | `Scaffold verification passed.` |
| 空白 | `git diff --check` | 无输出 |

## 接口 / 数据 / 配置变更

- 新增公开符号：`pdf_headings.CLEANED_PARSER_VERSION`、`policy.CallDeadlineExceededError`、`ModelCallPolicy.bind` 的 `deadline` 关键字参数、`BoundModelClient.deadline`。
- `pdf_headings.PARSER_VERSION` 由 `pdf/1+headings/1` 改为 `pdf/1,headings/1`。旧值本来就会被 D09 拒绝，因此不存在用旧值写入的数据。
- 无迁移、无新依赖、无环境变量变化。

## 未完成项 / 风险 / 下一步

- **D11（#239）**：删除 worker 里自拼的 `PDF_PARSER_VERSION`，改为引用 `pdf_headings.CLEANED_PARSER_VERSION`。本 PR 先合并时，D11 rebase 后应把原来断言 `pdf/1+headings/1` 的 D06 用例一并对齐。
- **J03（#242）**：补测试——改写调用抛 `CallRecordError` 时改用原问题。
- **J07**：按 `docs/integrations.md`「问答链路截止时间」传入截止时间，并把 `CallDeadlineExceededError` 映射到 O9。
- **TD-02**：服务层读任务 SQL 迁移，等 C10/C11/D11 全部合并后认领。
- 风险：请求未设超时且截止时间晚于适配器默认超时（60 秒）时，单次请求可能等待超过默认值。问答链路只有 15 秒，不会触发；worker 不传截止时间，也不受影响。

## 回滚

还原本分支提交即可。前提是还没有 PDF 块入库；一旦 PDF 块已入库，再改版本字符串就会改变块 ID，须按 ADR-012 重新处理资料。E04 的改动只增不改，不传 `deadline` 的调用方不受影响。
