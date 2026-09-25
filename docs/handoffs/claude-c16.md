# Claude 交接：C16 实现 SSE 一次性票据申领

- review_status: ready_for_review
- task_id: C16
- 目标 worktree：`/home/user/wt-c16-event-tickets`，分支 `claude/c16-event-tickets`
- base：认领提交 `9116315`；head：本交接所在提交
- 状态：DONE（待 PR 审查/合并）；未 push、未开 PR（本会话 GitHub 写权限被拒）

## 交付物

| 文件 | 内容 |
| --- | --- |
| `src/backend/migrations/006_event_tickets.sql` | 表 `event_tickets(ticket_hash 主键, user_id, task_id, expires_at, used_at, created_at)` 与 `expires_at` 索引 |
| `src/backend/app/repositories/event_tickets.py` | `issue_ticket`（申领：同一事务内先清理旧行再写哈希）、`redeem_ticket`（§5.2 第 1 步条件 UPDATE，供 C11）、`hash_ticket`、常量 `TICKET_TTL_SECONDS = 60`、`STALE_TICKET_RETENTION_SECONDS = 3600` |
| `src/backend/app/api/event_tickets.py` | `POST /api/v1/tasks/{tid}/event-ticket`，`operation_id="issueEventTicket"`，授权复用 C03 的 `task_teacher` 依赖 |
| `src/backend/app/main.py` | 仅新增路由 import 与 `include_router` 两行 |
| `tests/backend/test_c16.py` | 23 个用例 |

关键决定：

- 票据 `secrets.token_urlsafe(32)`：256 位随机数，43 个 URL 安全字符（契约要求 ≥22、`^[A-Za-z0-9_-]+$`）。
- 只存 `sha256(ticket)` 的 64 位小写十六进制；表上 CHECK 拒绝非 64 位 hex 的值（误存明文会直接失败）。
- 时间是 Unix 秒（整数），由 `app.state.auth_clock` 提供（与 C03 令牌校验同一可注入时钟），向下取整，因此实际有效期落在 (59, 60] 秒，不会超过 60 秒；表上 `CHECK (expires_at - created_at BETWEEN 1 AND 60)` 兜底，使有效期无法被配置得更长。
- 清理规则：`DELETE ... WHERE expires_at < now - 3600`，即过期**超过** 1 小时才删；恰好 1 小时的保留（测试含边界）。
- 核销：`BEGIN IMMEDIATE` 内执行 `UPDATE event_tickets SET used_at = ? WHERE ticket_hash = ? AND task_id = ? AND used_at IS NULL AND expires_at > ?`，影响 1 行才读回 `user_id`；不依赖 `RETURNING`。长度超过 128 或为空的输入直接返回 `None`，不做哈希。跨任务核销失败不会消耗该票据。
- 200 响应只含 `ticket`、`expires_in`，并带 `Cache-Control: no-store`；错误响应走 C03 的 `access_error_response`，只含 `code`、`message`。

## 验证（实际命令与结果）

均在 worktree 根目录执行，`V=/tmp/claude-0/-home-user-SmartSketch/f5e8fe9b-ebac-5377-b10c-8bfbef53bfde/scratchpad/venv`（未向其安装任何包）。

| 命令 | 结果 |
| --- | --- |
| 红灯：`PYTHONPATH=$PWD/src/backend $V/bin/python -m pytest tests/backend/test_c16.py -q`（仅有测试时） | 收集错误：`ImportError: cannot import name 'event_tickets' from 'app.repositories'` |
| 绿灯：同上（实现后） | `23 passed` |
| `PYTHONPATH=$PWD/src/backend $V/bin/python -m pytest tests/backend -q` | `1073 passed`（基线 1050 + C16 的 23） |
| `PYTHONPATH=$PWD/src/backend $V/bin/python -m pytest tests/contracts tests/tooling -q` | `4 failed, 269 passed`；与基线 `9116315`（`git stash -u` 后复跑）完全相同的 4 项：`test_b14.py` 两项、`test_contracts.py::test_gencheck_missing_stage_fails_in_every_locale`、`test_b07.py::test_dispatcher_reports_aggregate_status[0-PASS]`，原因均为本环境缺少生成器 `openapi-typescript` |
| `PATH=$V/bin:$PATH ./scripts/verify.sh` | 退出码 1，`FAIL contracts gate`（同上环境原因：B14 生成回归缺 `openapi-typescript`）；基线同样退出码 1。契约结构校验本身 `PASS contracts: OpenAPI 3.1.0，25 条路径 / 104 个 schema / 309 处 $ref`。C16 未改契约、未接入 `scripts/verify/contracts.sh` |
| `git diff --check` | 无输出，通过 |

## 反向篡改（改前 `cp` 备份，改回后 `cmp` 一致）

对象均为 `src/backend/app/repositories/event_tickets.py`：

| 篡改 | 结果 |
| --- | --- |
| 写入明文而非 `hash_ticket(ticket)` | 12 failed |
| 核销去掉 `task_id = ?` 条件 | 1 failed（跨任务用例） |
| 核销去掉 `expires_at > ?` 条件 | 4 failed（过期用例） |
| 核销去掉 `used_at IS NULL` 条件 | 1 failed（重复核销用例） |
| 申领时不清理旧行 | 1 failed（清理用例） |

五处改回后 `cmp` 均一致，复跑 `23 passed`。

## 测试覆盖

- 仅存哈希：库内行等于 `sha256(ticket)`；`iterdump` 与主库/WAL 原始字节中都查不到明文。
- 60 秒过期（注入时钟，无 sleep）：0、59、59.999 秒可用；60、61、7200 秒拒绝；非整数申领时刻取整后仍不超过 60 秒。
- 重复核销拒绝且 `used_at` 不变；跨任务（同课、异课）拒绝且票据不被消耗；普通 Bearer 令牌、库内哈希值、空串、超长串、截断/追加字符均拒绝。
- 过期超过 1 小时的旧行被清理；恰好 1 小时与未过期已用行保留。
- 表约束拒绝 >60 秒的有效期与非哈希主键。
- 授权矩阵：匿名/坏令牌 401、非成员与不存在任务 404 且响应体一致、异课任务 404、学生成员 403 `ROLE_FORBIDDEN`、停用教师 401、教师 200；拒绝时不写任何行，错误体只有 `code`/`message` 且不回显 `tid`。
- 迁移：把 001～004 复制到临时目录先迁移，再复制 006 → `["006"]`，重复执行为空；列与主键符合规格；用 `*-before-006.sqlite` 覆盖主库后 `event_tickets` 不存在、`pending_migrations` 重新为 `["006"]`，可再次迁移。不断言真实迁移目录的全集。

## 接口 / 数据变更

- 新增端点实现 `issueEventTicket`（契约 B10 已有，未改契约）。
- 新迁移 006：新增表 `event_tickets` 与索引 `idx_event_tickets_expires_at`；外键 `user_id → users(id)`、`task_id → processing_tasks(id) ON DELETE CASCADE`。
- 回滚：停止 API 与 worker，按 `src/backend/README.md` 用 `backups/*-before-006.sqlite` 覆盖主库（先保留失败库及 `-wal`/`-shm`）。该表无其他引用，等价的手工回滚为 `DROP TABLE event_tickets;` 并删除 `schema_migrations` 中 `version = '006'` 的行。回滚只丢失尚未核销的票据，前端重新申领即可。

## 风险

- 006 以 C09 #220 的 005 先合并为前提。迁移器允许版本号空缺，但若某个库在 005 之前已应用 006，之后 005 会被拒绝（`Cannot apply a migration older than an already applied version`）。所以部署/合并顺序必须是 005 先于 006；若 C16 先合，按 D-10 改号为 main 最大号 + 1。
- 仅在有人申领时清理旧行；无人申领期间旧行不会被删，数量受申领频率约束。
- 申领不限次数：同一教师可为同一任务反复申领，每次一行（规格未要求限流）。

## 待决（未擅自拍板，均为保守可逆实现）

1. **响应模型位置**：后端规则要求响应模型放 `schemas/`，但 `app/schemas/` 不在本任务文件锁内，`EventTicket` Pydantic 模型暂定义在 `app/api/event_tickets.py`。建议后续小任务移到 `app/schemas/event_tickets.py`。
2. **服务层**：`app/services/` 不在文件锁内，票据生成（随机数、哈希、有效期常量）放在仓储模块。若要严格分层，可新增 `services/event_tickets.py` 包一层，路由改调服务。
3. **`Cache-Control: no-store`**：规格未要求，出于票据不应被缓存而添加；如不需要可删一行。
4. **时间精度**：用整数秒并向下取整（有效期 (59, 60] 秒）。若规格希望精确 60 秒，可改为毫秒整数，需要改迁移。
5. **申领限流 / 每任务票据数上限**：规格未提，本任务未实现。
6. `verify.sh` 与 contracts/tooling 的 4 项失败是环境缺 `openapi-typescript`，与 C16 无关；需要有该生成器的环境复跑确认。

## 下一步（C11 如何调用核销）

C11 实现 `GET /api/v1/tasks/{tid}/events?ticket=...`：

1. 只读查询参数 `ticket`，不读 `Authorization` 头；调用 `app.repositories.event_tickets.redeem_ticket(settings.SQLITE_URL, ticket=ticket, task_id=tid, now=request.app.state.auth_clock())`。返回 `None` → 401 `UNAUTHENTICATED`（用 `app.services.access.unauthenticated()`）。
2. 返回的 `user_id` 用 `find_by_id` 回查账号，不存在或已停用 → 401。
3. 以该账号调用 `AccessService.require_task(account, tid)`，重新执行 §4.1 第 2～4 步（非成员 404、非教师 403），全部通过才开流。
4. 测试需覆盖 IAM-13、IAM-22：申领后、连接前被移出课程 → 404。
