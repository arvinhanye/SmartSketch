# J10 问答审计与统计 —— Claude 接手交接

- 基线：`main@9c66dcf` + 合并 kongsc 的 `codex/j10-chat-logs@bfeb16c`（PR #295，保留原提交）。前半段见 `docs/handoffs/codex-j10.md`。
- 接手时的缺口：J07 已在 main，但从未调用 `write_chat_log`，任何请求都不写日志；无查询/统计；未核对版本属于课程；测试只覆盖一次插入。

## 交付

- `app/services/qa/audit.py`：`ChatAudit` 记录器（observe 已送达事件 → 一次写入；`diagnose` 接收引用校验诊断；写失败只告警）。
- `app/api/chat.py`：P2 之后创建记录器；P3～P4 失败、JSON 终态、SSE 终态/断开（`finally` 中守护线程写入）各写一行。
- `app/services/qa/chat.py`：`events(..., audit=None)`，`finalize` 后传 `unknown_count`/子类/未覆盖单元数/`truncated`。
- `app/repositories/chat_logs.py`：写入前核对 `version_id` 属于 `course_id`（`ChatLogScopeError`）；`list_chat_logs`（课程必填，可按用户/时间/结局筛选，limit 1～500）、`get_chat_log`、`chat_stats`。
- `migrations/014_chat_logs.sql`：新增 `chat_logs(course_id, created_at)` 索引及其回滚行（迁移尚未合入 main，可改）。
- 决策 ADR-073；规格 `specs/grounded-qa.md` Q10 补一句终态判定与课程限定。

## 验证（本机实测）

- `PYTHONPATH=$PWD/src/backend .venv/bin/python -m pytest tests/backend/test_j10.py -q` → 19 passed。
- 反向篡改 12 处全部判红：去版本-课程核对、去 30 天清理、去课程过滤（11 failed）、失败路径不记、SSE 不 observe、不传诊断、首字不记、丢 `reason`、丢 `details.reason`、SSE 不写、告警带原问题、「首个终态胜出」去除（补测试后判红）。
- `.venv/bin/python -m pytest tests/backend -q` → 3466 passed / 27 skipped，exit 0。
- `./scripts/verify.sh` → exit 0（需 PATH 中有 `openapi-typescript@7.4.4`，本机在仓库外临时安装；缺它时 B14 两例失败，与基线相同）。`./scripts/gen-contracts.sh --check` 一致；`git diff --check` 干净。
- 本机 Python 3.11.15（CI 为 3.12）。

## 接口 / 数据变更

- 无契约变更、无新增 HTTP 端点、无依赖变更。迁移 014 新表 `chat_logs`（kongsc）+ 1 个索引（本轮）。
- 回滚：见 ADR-073「回滚」与迁移文件头。

## 风险与待决

- ADR-073 待签收三项：原问题原文留存 30 天且不自动脱敏；断开以「已送达」判定；本轮不提供查询端点。
- SSE 模式日志在响应结束后由线程写入，进程在此瞬间退出会丢这一行（守护线程）。
- 未在真实 Neo4j/真实模型下做端到端联调；API 测试注入脚本化 `ChatService`，服务层诊断用真实 `ChatService.events` + 假生成器覆盖。

## 下一步

- 教师侧日志/统计 HTTP 端点（需先定契约）；K03/K05 可用 `chat_stats` 与 `list_chat_logs` 取数。
