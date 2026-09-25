# Claude 交接：D03、D04 收尾与 B07 issue 关闭

- 日期：2026-09-24（PR 合并时间戳为 UTC 2026-09-25）
- 分支 / base：`claude/check-pending-prs-tasks-1ba7fe` / `origin/main@2694e3e`
- 角色：协调方（只改文档，不改代码）

## 交付物

| 文件 / 对象 | 变更 |
| --- | --- |
| `docs/tasks.md` | D03 → `DONE（PR #191 2694e3e）`，D04 → `DONE（PR #193 ebed3cd）`，补验收证据 |
| `docs/integrations.md` | 「计划集成」下新增「文档解析库（D02～D05）」表，登记 D03 `markdown-it-py==4.2.0`（MIT）与 D02/D04 仅用标准库；D05 待 PR #197 合入后登记 |
| GitHub issue #49（B07） | 关闭。依据：任务板 B07 已为 `DONE（PR #187 已合入 1d3e20c）`，PR #187 状态 MERGED |

D03、D04 交接都写明「任务板与 integrations 登记由协调方在合并时处理」，本次补上。#72（D03）、#73（D04）此前已随 PR 关闭。

## 核对方法

- 以 `origin/main` 的 `docs/tasks.md` 为准，逐个对照 open issue 标题中的任务 ID：状态为 DONE 而 issue 仍 open 的只有 B07（#49）。
- 反向核对：D03、D04 的 issue 已关闭、PR 已合并，但任务板仍为 IN PROGRESS。

## 验证

| 命令 | 结果 |
| --- | --- |
| `pytest tests/backend -q`（`2694e3e`，scratchpad venv，`pip install -e './src/backend[test]'`） | 687 passed，1 warning（既有 Starlette `httpx` 弃用提示） |
| `pytest tests/backend/test_d03.py tests/backend/test_d04.py -q` | 119 passed（66 + 53，与两份交接一致） |
| `gh pr view 191/193` | 均 MERGED，CI 6 项 SUCCESS |
| `./scripts/verify.sh`（PATH 前置 scratchpad venv） | exit 0，末行 `Scaffold verification passed.`；`git diff --check` 通过 |

## 接口 / 数据变更

无。

## 仍开放（未处理，需人工决定）

- PR #197（D05）：CI 绿，但与 main **有冲突**（预计是 `pyproject.toml` 的 `dependencies` 与 D03 的一行冲突），需 rebase 后再审。
- PR #196（REQ-01 指标补登）、PR #194（B11 图谱编辑与版本契约）：CI 全绿、可合并，尚无审查结论。
- `parsers/__init__.py` 是否统一重导出 D02～D05 的解析函数，D03 交接留给协调方，待 D05 合入后一并决定。

## 回滚

还原本 PR 的两处文档改动即可；如需重开 B07，`gh issue reopen 49`。
