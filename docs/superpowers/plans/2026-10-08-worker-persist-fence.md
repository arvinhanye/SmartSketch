# Worker 持久化租约围栏 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** 接管发生后旧 worker 零图提交，正常 T6 与草稿修订号恰好增加一次。

**Architecture:** 双租约单调截止守卫贯穿显式图事务。图构建后进入 SQLite 最终提交围栏，图提交与同连接 T6 期间排斥接管；失败区分未提交和结局不确定，保持既有可见性恢复协议。

**Tech Stack:** Python、SQLite WAL、Neo4j 5.28.2 同步驱动、pytest；不升级项目依赖。

**Spec:** `docs/superpowers/specs/2026-10-08-worker-persist-fence-design.md`

## Global Constraints

- 仅调整 worker `persisting`；其他四项中严重程度发现和教师写协议保留。
- 截止为最近成功续约时刻加 `L - L/3`；迟到续约不复活，数据库有效期必须严格大于 `unixepoch()`。
- 图草稿守卫 → SQLite `BEGIN IMMEDIATE` → 校验双令牌 → 图 COMMIT → 同连接 T6 → SQLite COMMIT。
- 不新增公共 API、契约、数据库迁移、环境变量或项目依赖；不操作用户业务库，不推送。
- 图提交应答不确定不重放回调、不宣称跨库原子提交或客户端硬取消。
- 复用当前受管 detached HEAD worktree，当前会话顺序实施；最后独立审查。

## Review Focus

1. SQLite 续约排队后才返回：使用续约开始时刻，迟到成功不延长守卫。
2. 图语句返回前本地截止/锁接管：返回后复核，下一语句与 COMMIT 零发送。
3. 校验后租约过期但另一连接接管：围栏互斥，提交前失效应回滚。
4. 图已提交后 T6/退出故障：已生效 T6 不释放/撤销；未生效贡献由新尝试撤销重建。
5. 正常 T6 清空令牌时心跳误报 lost：保持成功结果，不逆转到失败。

## 验证运行环境

当前 Python 3.11 项目环境缺少 pytest/jsonschema；先使用项目解释器，追加既有 Anaconda 纯 Python 测试工具路径，不覆盖其原生依赖。若全量收集需要兼容原生测试依赖，安装到独立临时测试环境，不修改项目锁文件。每次记录实际命令和日志。

## Task 1: 双租约截止与 SQLite 围栏

**Files:** 新增 `src/backend/app/repositories/lease_guard.py`、`tests/backend/test_worker_persist_fence.py`；修改 `task_leases.py`、`course_locks.py`、`workers/parse_task.py`。

**Interfaces:**
- Produces: `LeaseGuard(lease_seconds: int, *, last_success: float, clock: Callable[[], float])`；`check() -> None`、`remaining() -> float`、`renewed(started: float) -> None`、`lose() -> None`。
- Produces: `persist_transaction(sqlite_url: str, lease: Lease, course_token: str) -> context manager[sqlite3.Connection]`。
- Produces: `LeaseHeartbeat.guard: LeaseGuard`；课程锁 `held(..., guard: LeaseGuard | None = None)`，原调用者兼容。

- [x] 写注入时钟测试：`test_guard_cutoff_is_terminal`，在 60 秒 TTL 的 40 秒边界失效，迟到续约保持失效；`test_delayed_renewal_uses_start_time`。
- [x] 写数据库条件测试：`test_persist_fence_rejects_stale_task_or_course`、到期等号、错误课程/阶段，以及续约拒绝到期复活；先运行证明失败。
- [x] 实现上述接口：锁保护截止，心跳失败传递，围栏双令牌/阶段/课程/到期校验；守卫用领取/续约确认的时刻初始化。
- [x] 跑新测试及 C09/D11/课程锁回归，期待全部通过，记录结果并保存提交。

## Task 2: 无透明重试的显式图事务

**Files:** 修改 `src/backend/app/repositories/neo4j.py`；新增 `tests/backend/test_worker_graph_transaction.py`。

**Interfaces:**
- Consumes: `check: Callable[[], None]`；Task 1 的守卫在 worker 合成该回调。
- Produces: `explicit_write_transaction(scope: GraphScope, *, check: Callable[[], None], timeout: float)`，yield `ExplicitTransaction`，其 `run(...)` 继承 scope 校验，其 `commit() -> None` 只显式提交一次。

- [x] 写记录驱动测试：没有显式 commit 就回滚；每条语句发送前/结果消费后复核；失效零 commit；commit 故障不重跑；错误脱敏且关闭资源；先运行失败。
- [x] 实现生命周期，原 `write_transaction` 保留；不跨线程操作 driver，不以服务器 timeout 当客户端硬截止。
- [x] 跑新测试与 F02/F06 仓储相关测试，期待通过，记录结果并保存提交。

## Task 3: Worker 编排与接管回归

**Files:** 修改 `workers/persist_graph.py`；扩展 `tests/backend/test_worker_persist_fence.py`，更新既有内部计时/故障注入测试至新事务边界。

**Interfaces:**
- Consumes: Task 1 的守卫和 `persist_transaction`、Task 2 的显式事务。
- Produces: `_t6_in(database: sqlite3.Connection, lease: Lease) -> int`，保留 `_t6` 包装；`run_persist_stage(..., task_guard: LeaseGuard | None = None)`。

- [x] 写真实 SQLite + 图记录器测试：接管在图构建期间完成后旧提交 0；最终围栏内另一连接写者被阻挡；正常提交 seq/revision 各一次；T6 崩溃与丢失提交应答不重放；先验证失败。
- [x] 实现显式事务 → 围栏 → commit → `_t6_in`；pipeline 将心跳守卫传至持久化。直接调用创建阶段心跳，避免无续约有效期初始化。
- [x] 图提交后的异常先读回 SQLite 阶段/seq 识别已完成；退出失败不回写/清理已完成任务；未完成仍按现有令牌条件恢复。
- [x] 跑全部新测试、C09/D11/cleanup/计时/F13 定向回归，期待通过，保存提交。

## Task 4: 真实事务验收与交付

**Files:** 新增 `tests/integration/test_worker_persist_fence.py`；同步设计状态、ADR、任务与交接。

- [x] 写独立 Neo4j 测试：实际图回滚、实际 T6、图守卫等待期间接管；故障注入 commit 阻塞/断连/丢失应答，记录实际等待与资源释放。
- [x] 仅启动临时测试实例；若环境未具备或持续无界提交等待，保留明确未验收状态与发布阻塞，不使用替身冒充真实证据。
- [x] 跑 `./scripts/verify.sh`、最小相关测试；尝试 full/integration 并记录环境限制。`git diff --check` 期待 exit 0。
- [x] 独立 whole-branch 审查，重要发现按 RED→GREEN 修正；更新任务、ADR/规格和交接，写清回滚及剩余风险。
- [x] 仅本地提交，不推送/合并；报告代码修复证据与未完成的真实故障准入条件。

## 实施指示与自审

2026-10-08 用户在书面规格交付后明确要求「实施修改」，作为规格确认及本会话直接实施指示；计划是这次实施的执行记录，遵从该直接指示不重复请求启动确认。四任务与规格十节对应，五项 Review Focus 均有归属测试；保留独立集成准入而非宣称已部署。

## 实施结果

本地实现与审查 Important 回归缺口已落实：最终定向 214、真实 Neo4j 34、独立环境工具模块/新回归 45 全部通过；basic exit 0。执行步骤已完成，但发布准入尚未完成：网络总截止/真实断连资源释放仍未验证；单次 backend full 环境失败后只作定向复验，frontend 缺依赖，完整 integration/E2E 未跑。准确命令、跳过原因与全部 Ruling/暂缓 Minor 见 `../../handoffs/codex-r1-persist-fence.md`。
