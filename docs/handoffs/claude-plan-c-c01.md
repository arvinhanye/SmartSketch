# C01（B-EVAL-01）测量工具与预算分账 交接

```text
task_id: C01
review_status: ready_for_review
worktree: /Users/arvinhan/SmartSketch/.claude/worktrees/smartsketch-plan-a-fixes-e70a34
branch: claude/plan-c-reliability（base ec1291a）
author: Claude
paid_calls: 0（全部离线；未连接任何真实库或模型）
```

## 交付物

- `evaluation/measure_web_flow.py`：
  - 新增纯函数 `parse_utc`、`in_window`、`normalize_ask_result`、`open_readonly`、`ledger`、`audit`、`budget_stop`、`nearest_rank`、`summarize`、`read_chat_sse`。
  - `ask` 新增 `--out`（逐题 JSONL）、`--stream`（SSE，记客户端首个 delta）、`--audit-db` + `--cap`（每题后按生成 token 硬止损，usage 未知也停）。
  - 新增 `audit` 子命令：按 JSONL 的请求 ID、固定 ID，或 `[since, until)` 窗口只读关联。
  - `extract` 未改（C03 再扩展阶段分解）。
- `evaluation/README.md` §9：用法与口径。
- `tests/tooling/test_c01_measure.py`：22 例。

## 修正的问题（第二阶段收尾审查 E1/E2）

| 问题 | 现在的行为 |
| --- | --- |
| HTTP 错误的编号在 `details.request_id`，旧脚本取顶层得到 null，并把错误码写进 outcome | `request_id` 兼容 details；`outcome=error`、`error_code`、`error_reason` 分列；拿不到响应单列 `no_response` |
| `18:16:00.314Z >= 18:16:00Z` 字符串比较为假，漏掉 1 条（3 token 向量） | 一律按 UTC 时刻比较；窗口 `[since, until)` 必须有结束边界，或用固定请求 ID；缺时区直接拒绝 |
| 生成与向量混算（29007） | 生成（`purpose != embedding`）与向量分账，另列 `by_purpose` |
| usage 缺失按 0 处理 | 计入 `unknown_usage_calls`，`tokens_complete=false`；止损遇未知即停 |
| 工具 exit 0 被当作十题通过 | 汇总给出 `counts` 与 `all_answered`；提前停止退出码为 3 |
| 首字口径混用 | 三列分开：服务端首个 delta（`chat_logs`）、客户端 SSE 首个 delta（`--stream`）、浏览器（「未测」） |

离线重算（夹具由 `evaluation/raw/l15/codex-closeout-audit.json` 生成）：11 个请求、19 次调用 = 9 生成 + 10 向量，生成 28951（输入 18764 + 输出 10187）、向量 59；已回答题服务端首个 delta 的最近秩 p50 为 5020、p95 和最大值均为 9287（n=7）。

## 验证

- 先红：17 个纯函数用例在实现前全部失败（`AttributeError`，模块本身可加载）。
- 后绿：实现后 17 passed。之后补的 5 个命令行端到端用例在实现之后编写，首次运行即通过，属验证而非红绿。它们用本机假 HTTP 服务（JSON / SSE / 503 截断）写临时 SQLite，覆盖退出码、SSE 首字、生成预算硬止损、usage 未知停止、按请求 ID 关联。
- `PYTHONPATH=$PWD/src/backend .venv/bin/python -m pytest tests/tooling -q -p no:cacheprovider`：97 passed（含 `test_l02_measure` 回归）。
- `env -u LLM_MODE -u EMBEDDING_MODE PYTHON=.venv/bin/python PATH="$PWD/.venv/bin:$PATH" ./scripts/verify.sh basic`：exit 0。
- `git diff --check`：exit 0。

## 接口/数据变更

无。只改评测工具与文档；不改业务代码、契约、数据库模式。

## 风险与限制

- `audit` 的窗口模式会把同期其他调用（例如抽取任务）一并计入生成账本，并单列 `unmatched_calls`。对止损来说这是保守的；做精确归因时请用请求 ID 模式。
- `ask --stream` 测的是客户端收到第一条 `delta` 事件的时刻，不是浏览器渲染首字。
- 真实环境尚未用新工具跑过；下一轮付费测量（C02-4 / C03）由 DeepSeek 用本工具执行。

## 下一步

C02-1：比较题截断的离线定位。
