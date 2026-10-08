# Worker 提交传输截止 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 保留 R1 双租约提交围栏，以可取消异步传输和有序恢复关闭网络提交等待导致 SQLite 全库写锁无界占用的风险。

**Architecture:** 同步 worker 通过专用仓储门面驱动每尝试独占的 Runner/AsyncDriver，图尝试及 COMMIT 采用非延长绝对截止。取消后先退出 SQLite 围栏再等待资源清理；结果不确定由图草稿守卫后的接管/撤销恢复，不复用或重放已取消事务。

**Tech Stack:** Python ≥3.11、Neo4j 驱动 5.28.2、SQLite WAL、pytest、测试专用 TCP 代理及一次性 Neo4j 5.26-community；不升级项目依赖。

**Spec:** [已批准补充规格](../specs/2026-10-08-worker-persist-deadline-design.md)，补充 [R1 核心规格](../specs/2026-10-08-worker-persist-fence-design.md)。

**State:** 规格已获用户「确认实施」；计划已获用户「确认计划，开始实施」；当前按任务顺序实施，未验证步骤保持未勾选。复用当前受管 worktree；保留本会话顺序执行方式。代码基线 `e111315`，文档基线 `e41e951`。

## Global Constraints

- 仅 worker `persisting` 与其失败贡献清理；不修四项中严重程度发现，不改教师/发布/QA 图入口。
- 图 DraftWriteGuard → SQLite 双令牌围栏 → 显式图 COMMIT → 同连接 T6 → SQLite COMMIT；无跨库原子提交。
- `TASK_PERSIST_COMMIT_TIMEOUT_SECONDS` 默认 2.0 s，`0 < value ≤ 3.0`，有限；`TASK_PERSIST_CLEANUP_TIMEOUT_SECONDS` 默认 1.0 s，`0 < value ≤ 5.0`，有限。配置只来自环境。
- `D_tx = 入口单调时刻 + 初次剩余双租约预算`；心跳和分步应答不延长。最终提交截止取 `D_tx`、取得围栏时刻＋COMMIT 配置、双守卫截止中的最小值。
- 网络等待清理仅在 SQLite 围栏退出后，共享单一清理截止；无后台提交线程、shield、私有 socket patch 或跨线程 Session 操作。
- 取消不证明服务器未提交；提交已发起但未确认时不做 T6、不内联重放。failed 清理亦经图守卫排序，确认撤销后才清标记。
- 默认围栏 ≤3.0 s，上限配置 ≤4.0 s；资源退出 ≤清理配置＋1.0 s，均为健康本机/SQLite 下逐次实测准入，不外推 DNS 执行器、磁盘故障或进程暂停。
- 无公共 API/DTO/事件、数据库模型/迁移或依赖升级；不读用户 .env/课程资料、不连共享库、不发真实模型请求。
- 不删测试、不新增准入 skip、不调整阈值遮蔽失败；不推送、创建 PR、合并或技术冻结。任一必需证据欠缺，风险仍 OPEN。

## Review Focus

1. 活跃事件循环内调用同步门面：创建任何网络资源之前失败，且无未 await 协程警告（Task 1）。
2. 工厂/认证创建中途异常：已经创建的 loop/pool 退出，错误不泄露地址/凭据（Task 1～2）。
3. COMMIT 失败后重复调用：拒绝二次发送，即使第一次结果不确定（Task 2）。
4. 退出异常覆盖原 LeaseLost 或已确认 T6：保留原失效语义/成功结果，不误补偿（Task 2、4）。
5. failed 任务预读为空但旧事务未结局：清理不能提前清标记，也不能撤销其他任务/人工贡献（Task 5～6）。

## 环境与文件责任

- 本机定向解释器：`/private/tmp/smartsketch-r1-venv/bin/python`；复用已存在的测试依赖，不把临时路径写入产品代码。若失效，按项目 `src/backend[test]` 声明创建新的临时 venv，网络下载走审批，不改用户应用环境。
- 定向命令前缀：`PYTHONDONTWRITEBYTECODE=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH="$PWD/src/backend" /private/tmp/smartsketch-r1-venv/bin/python -m pytest`；下文用 `P` 表示这个前缀，不是可直接执行的命令。均加 `-q -p no:cacheprovider` 并保存日志/XML。
- 基础门禁使用已验证 PATH；整次 integration 使用同一有效 Python、Node、Docker PATH，声明依赖完整安装。依赖缺失是真实失败/阻塞，不能以定向通过替代。
- `persist_transport.py` 只做传输；`neo4j.py` 只做 scope/守卫门面；`task_leases.py/sqlite.py` 只做围栏原语；`persist_graph.py` 负责状态和恢复。
- 每任务独立 RED→GREEN 与本地提交；共享文件串行修改。异常/偏离写入进度记录与最终交接，明确其代价，不偷偷改变批准规格。

## Task 1：可取消传输及预算配置

**Files:** Create `src/backend/app/repositories/persist_transport.py`、`tests/backend/test_worker_persist_transport.py`、`tests/backend/test_worker_persist_config.py`；Modify `src/backend/app/config.py`、`.env.example`、`docs/integrations.md`。

**Interfaces:**
- `AsyncDriverFactory = Callable[[], neo4j.AsyncDriver]`；测试按 duck typing 注入异步驱动。
- `PersistTransport(factory, *, deadline: float, remaining: Callable[[], float], check: Callable[[], None], commit_timeout: float, cleanup_timeout: float)`；方法 `open() -> None`、`run(query: str, parameters: Mapping[str, Any]) -> list[dict[str, Any]]`、`commit(*, started_at: float) -> None`、`close() -> None`；只读 `deadline/commit_started/committed`。
- 传输叶模块 `TransportTimeout(RuntimeError)`：`phase: Literal['open','run','commit','exit']`、`commit_started: bool`；文本只含稳定码。Task 2 将它映射成仓储错误，避免叶模块依赖 neo4j 仓储造成循环导入。

- [ ] Step 1：写失败测试 `test_timeout_cancels_connection_and_finishes_task`，假异步 COMMIT 永不返回；测试替身记录计数/loop/Task，断言 `assert fake.cancel_calls == 1`、`assert fake.commit_calls == 1`、`assert not fake.pending_tasks`。写 `test_run_consumption_uses_original_deadline`：RUN 及消费共同占预算，`assert transport.deadline == original_deadline`；`test_active_loop_rejects_before_factory`：`assert fake.factory_calls == 0`，无 RuntimeWarning；`test_each_attempt_owns_loop_and_closes_partial_factory_resources`：单尝试同线程/loop、跨尝试池不复用，`assert not fake.open_resources`。
- [ ] Step 2：配置测试断言缺省 `(2.0, 1.0)`、上限 `(3.0, 5.0)` 可用；逐字段拒绝 `0/-1/NaN/Inf/上限+0.01`，load_settings 错误只含变量名。运行 `P tests/backend/test_worker_persist_transport.py tests/backend/test_worker_persist_config.py`，保留缺接口/行为错误的 RED。
- [ ] Step 3：实现接口；每次独占 Runner/Driver/Session，显式 begin，完整网络操作用同 Task `asyncio.timeout(绝对截止剩余)`；捕获取消立即公开取消并重抛。不用 Transaction 自动提交上下文；清理共享一个截止，最后检查无遗留 Task，再关 Runner。Settings 两字段为有限 float，按规格默认/上限声明，.env 样例与 integrations 同步。
- [ ] Step 4：增加 `test_cleanup_layers_share_one_deadline` 和 `test_rollback_stall_forces_cancel`：各层无新预算，清理超时资源退出；全部 Task 1 测试 GREEN。不得把协程取消单独当成物理网络证明。
- [ ] Step 5：本地提交 `feat(worker): add cancellable persist transport budgets`，只 stage 本任务文件。

## Task 2：作用域门面及专用驱动工厂

**Files:** Modify `src/backend/app/repositories/neo4j.py`、`tests/backend/test_worker_graph_transaction.py`；Test Task 1 传输文件。

**Interfaces:**
- `Neo4jRepository(driver, *, persist_driver_factory: AsyncDriverFactory | None = None, persist_commit_timeout: float = 2.0, persist_cleanup_timeout: float = 1.0)`；from_settings 提供工厂/两预算，工厂调用 `neo4j.AsyncGraphDatabase.driver`，不从同步驱动私有字段取配置。
- `persist_write_transaction(scope: GraphScope, *, check: Callable[[], None], remaining: Callable[[], float]) -> Iterator[PersistTransaction]`（contextmanager）；`PersistTransaction.scope/run/commit(started_at=...)/deadline/commit_started/committed` 复用 Task 1，不复制提交状态。
- `RepositoryTransportTimeout(RepositoryError)` 稳定码 `NEO4J_TRANSPORT_TIMEOUT`，仅 phase/commit_started；旧 DeadlineExceeded 和旧入口不变。

- [ ] Step 1：写 `test_persist_factory_missing_never_falls_back`，缺工厂时 `assert fake.sync_session_calls == 0`；`test_persist_scope_and_reserved_parameters`：不合规 query 在语句发送前拒绝，`assert fake.statement_calls == 0`，scope 覆盖 extras；`test_persist_repeat_commit_after_uncertain_result_is_rejected`：`assert fake.commit_calls == 1`。
- [ ] Step 2：写 `test_persist_partial_start_error_is_redacted`：`assert 'private-host' not in str(error)`、`assert 'private-token' not in str(error)`；`test_exit_error_preserves_primary_lease_loss`：`pytest.raises(LeaseLost)` 而非退出错误。运行 Task 2 测试确认 RED。
- [ ] Step 3：实现门面/工厂/错误映射，捕获一次 `D_tx`，语句前/后守卫检查，提交 Task 内发起前再检查；成功应答后不追溯租约截止。传输退出的等待仅发生在 caller 的内层 SQLite 上下文退出后；原异常存在时保留它，追加清理失败仅记脱敏码。
- [ ] Step 4：运行 `P tests/backend/test_worker_graph_transaction.py tests/backend/test_worker_persist_transport.py tests/backend/test_f02.py`；旧入口断言和新门面均 GREEN，提交 `feat(graph): expose scoped bounded persist transactions`。

## Task 3：有绝对预算的 SQLite 围栏

**Files:** Modify `src/backend/app/repositories/sqlite.py`、`src/backend/app/repositories/task_leases.py`、`tests/backend/test_c01.py`、`tests/backend/test_worker_persist_fence.py`。

**Interfaces:**
- `SQLiteDeadlineExceeded(sqlite3.OperationalError)`；`connect(sqlite_url: str, *, deadline: float | None = None) -> Iterator[sqlite3.Connection]`。
- `_immediate(sqlite_url, *, deadline=None, on_acquired: Callable[[float], None] | None = None)` 和 `persist_transaction(sqlite_url, lease, course_token, *, deadline=None, on_acquired=None)`；旧调用默认 None 行为不变。BEGIN 返回后立即向回调传单调时刻，回调只记录 `t_f`，其异常也须回滚；不等到令牌 SELECT 完成才重新起计时。
- 连接初始化 PRAGMA/BEGIN 前重算 `min(5000, floor(剩余秒*1000))`，不足 1 ms 失败，返回后检查截止；连接和 SQLite 事务始终 caller 线程。

- [ ] Step 1：写 `test_fence_wait_uses_remaining_absolute_budget`：另一个连接持写锁，100 ms 预算在 1 s 测试余量内失败且未改变 token/T6；`test_expired_fence_deadline_sends_no_begin`：过期预算 BEGIN 次数 0。注入时钟验证 PRAGMA 与 BEGIN 不各领完整预算；默认连接仍 `busy_timeout=5000`。`test_fence_acquired_clock_precedes_validation_and_callback_error_rolls_back` 断言回调早于令牌查询，回调错误不留写锁。
- [ ] Step 2：运行 `P tests/backend/test_c01.py tests/backend/test_worker_persist_fence.py` 并确认新案例 RED。
- [ ] Step 3：实现可选截止/失败类型，BEGIN 后检测过期须回滚/退出，保留原双令牌/阶段/DB 有效期 predicate 和同连接 T6。预算用于初始化/获取锁，不对已确认图提交后的 T6/SQLite COMMIT 增加追溯截止回滚。
- [ ] Step 4：上述测试及 `P tests/backend/test_c09.py tests/backend/test_d11.py` GREEN，提交 `fix(sqlite): bound persist fence acquisition by deadline`。

## Task 4：worker 接入与提交不确定分类

**Files:** Modify `src/backend/app/workers/persist_graph.py`、`tests/backend/test_worker_persist_fence.py`、`tests/backend/test_c02_phase_logs.py`；Adapt 相关 worker 纯测试替身，不变更其业务断言。

**Interfaces:** run_persist_stage 公共内部参数不变；使用 Task 2 专用事务、Task 3 `deadline=tx.deadline, on_acquired=记录时刻回调` 围栏，使用其 `t_f` 执行 `tx.commit(started_at=t_f)`。预算/传输失败分支只做令牌条件 SQLite 状态操作，不调用旧同步 cleanup；LOST 继续优先于临时故障。

- [ ] Step 1：新增 `test_commit_timeout_releases_fence_before_transport_close`：记录事件，`assert events.index('fence_released') < events.index('transport_close')`、`assert t6_calls == 0`；`test_uncertain_commit_keeps_token_and_stops_new_renewals`：`assert outcome.status == PersistStatus.LOST`、`assert guard.lost.is_set()`，无释放/撤销/二次 COMMIT；`test_precommit_last_attempt_timeout_defers_cleanup`：从 DB 查询 stage/cleanup_pending，`assert state_row == ('failed', 1)`，同步图清理调用 0。
- [ ] Step 2：增加 `test_confirmed_t6_survives_transport_exit_failure`：仅我们的 t6_seq 完成返回 ADVANCED，修订号/水位各 1；覆盖图已提交但 T6 失败和读回失败，不把新 owner 的完成当本次成功。运行 `P tests/backend/test_worker_persist_fence.py tests/backend/test_c02_phase_logs.py` 留 RED。
- [ ] Step 3：接入双守卫的 remaining/check；采用新事务/围栏，分类不确定结果并使守卫终止新续约；保留已发起续约的最终 DB 到期值，禁止复活守卫。所有专用事务故障均不回旧同步图补偿；完成读回继续优先。
- [ ] Step 4：在 test_worker_persist_fence 中为真实 LeaseHeartbeat/course_locks.held 写延迟、连续 SQLite 异常和零行续约案例，使用可控 Event/时钟，不用长期 sleep；截止后不复活、不继续发图语句。阶段计时字段继续允许 neo4j/t6 嵌套，不相加算总耗时。
- [ ] Step 5：运行 Task 4 与 C09/D11/F02 定向 GREEN；提交 `fix(worker): cancel uncertain graph commits without retaining fence`。

## Task 5：失败清理的图守卫排序

**Files:** Modify `src/backend/app/workers/persist_graph.py`、`tests/backend/test_264_cleanup_lock.py`、`tests/backend/test_worker_persist_fence.py`；同步 `docs/decisions.md` ADR-072 修订及 `specs/task-processing.md` 当前状态。

**Interfaces:** cleanup_failed_task 参数/返回 bool 不变；course_guard 提供 Task 2 check/remaining，专用事务内 `lock_draft` 后无条件幂等 `revoke_task`，commit(started_at=单调现在)，确认退出后才 clear_cleanup_pending；任何不确定/失效返回 False 保留标记。

- [ ] Step 1：保留无贡献、有贡献、图故障、空 task_id 用例；将旧“无工作 0 次取锁”政策断言改成批准新顺序：取锁→图守卫→撤销→确认提交→清标记，注明 ADR-092 替代此 ADR-072 快路径，不能删除这些用例。
- [ ] Step 2：新增 `test_empty_cleanup_waits_for_old_graph_guard`：旧事务持守卫、贡献尚不可见，清理开始后 `assert cleanup_pending == 1`；旧事务结局后 `assert late_contributions == 0`、`assert cleanup_pending == 0`。`test_cleanup_uncertain_ack_keeps_marker_and_preserves_other_contributions`：`assert cleanup_pending == 1`、`assert other_contributions == before`，后续幂等成功才 0。运行 Task 5 用例保留 RED。
- [ ] Step 3：移除该入口的无贡献预读快路径，接 Task 2 单课程守卫、非延长图预算及有截止 COMMIT；不在 SQLite 写事务中做撤销图网络请求。
- [ ] Step 4：Task 5、F13、现有失败清理回归 GREEN；提交 `fix(worker): serialize failed cleanup after uncertain graph outcomes`。

## Task 6：真实 TCP 故障及可用性证据

**Files:** Create `tests/integration/bolt_fault_proxy.py`、`tests/integration/test_worker_persist_transport.py`、`tests/tooling/test_worker_bolt_proxy.py`；Modify `tests/integration/test_worker_persist_fence.py`、`tests/integration/test_f13.py` 的专用工厂/边界替身；生产代码不得导入代理。

**Interfaces:**
- 测试 `MessageEvent(direction: Literal['c2s','s2c'], signature: int | None, phase: Literal['handshake','message','noop'])` dataclass；`BoltFrameObserver.feed(direction, data: bytes) -> list[MessageEvent]` 仅输出这些字段，不输出 payload；正确跨 TCP/消息 chunk 分片，处理固定握手与 Manifest v1，认证正文中 0x12 不算 COMMIT。
- `BoltFaultProxy(upstream_host, upstream_port, *, mode)` contextmanager，仅允许回环；mode 为 `healthy/commit_blackhole/commit_noop/commit_fragment/disconnect_before/disconnect_after/begin_blackhole/pull_blackhole/rollback_blackhole`，提供 `uri: str`、`forwarded_commits: int`、`timestamps: dict[str, list[float]]`、`client_eof: threading.Event`、`closed: bool`。所有关闭有 watchdog、连接和线程 join，计时字典没有认证/正文。
- 同文件 `owned_neo4j` fixture 自建随机名＋随机所有权标签的 5.26-community 容器，回环随机端口、测试口令、小堆/页缓存；退出只删除确认为本 fixture 创建的 ID。Docker 缺失即 FAIL，不复用用户/外部 URI，不新增 skip，不受重型镜像用例的 skip 开关豁免。

- [ ] Step 1：写代理单测：逐字节分片固定/Manifest 握手、同包握手结束＋消息、跨 chunk COMMIT、连续消息、认证内假签名、NOOP、截断与正常 EOF；断言只有完整真实 COMMIT 事件、原样转发、日志不含凭据样例。RED→实现透明握手/消息 framing→GREEN。协议依据：[官方握手](https://neo4j.com/docs/bolt/current/bolt/handshake/)、[消息](https://neo4j.com/docs/bolt/current/bolt/message/)；驱动 5.28.2 已会请求 Manifest，不能只处理 4 字节回复。
- [ ] Step 2：通过测试级 SQLite Connection subclass 在执行 BEGIN IMMEDIATE 返回及 COMMIT/ROLLBACK 退出处记单调时间；代理记真实 COMMIT 见到/转发/应答截断及客户端 EOF。启动其他课程独立连接写者（busy_timeout=0 探针和默认 5000 ms 写者），不以 tx.commit 替身代替网络故障。
- [ ] Step 3：从 `git show e111315:...` 在临时目录复原原 worker/仓储，独立子进程经相同代理做黑洞；10 s 外部 watchdog 内未释放围栏须形成 RED，终止仅测试子进程并保留日志。修复版本相同案例返回并释放写锁，真实读取图结果/任务状态，不猜测回滚。
- [ ] Step 4：每 mode 至少 5 次；默认围栏/探针写等待 ≤3.0 s、上限配置 ≤4.0 s；网络 COMMIT 符合 2.0 s/3.0 s＋1.0 s 余量；清理退出 ≤1.0 s/5.0 s＋1.0 s，逐次保存最大值。NOOP/少量片段不得延长；before-disconnect 转发数 0 与 after-disconnect 分开，提交调用开始两者均可保守归不确定。提交成功丢应答后新领取重建、T6/修订号一次、接管者保留。
- [ ] Step 5：迟到结局实验仅暂停自有 Neo4j：在代理识别 COMMIT 后暂停服务器，再把旧请求转发进已有连接，确认转发发生在客户端取消前；取消后解除暂停，直连核验实际贡献/图锁结局。必须至少观察到一次“取消后服务器实际提交”，再验证接管与 failed 清理在图守卫后收敛；不能在客户端断开后重新注入请求。代理见到/转发≠Neo4j 已执行，分别记证据；若只能观察回滚而不能形成必要迟到证据，记录缺口并保留 OPEN，不宣称覆盖。
- [ ] Step 6：使用真实旧图事务持守卫的确定性案例单独验证无贡献清理排序，标注为图锁故障案例而非物理取消证明；补健康 latency、BEGIN/PULL/rollback 黑洞及客户端连接 EOF/无遗留 Task。运行 `P tests/tooling/test_worker_bolt_proxy.py` 和获审批的 `P tests/integration/test_f13.py tests/integration/test_worker_persist_fence.py tests/integration/test_worker_persist_transport.py`，真实必需用例零 skip。
- [ ] Step 7：临时故障变异分别去掉截止、公开取消和清理守卫，关键测试均须 RED；还原正常实现 GREEN 后提交 `test(worker): prove persist fence release under Bolt faults`。真实矩阵/资源退出任一失败则停止准入，不私有 patch/放宽阈值。

## Task 7：完整门禁、独立审查与交接

**Files:** Update `docs/tasks.md`、`docs/architecture.md`、`docs/decisions.md`、`specs/task-processing.md`、`docs/superpowers/specs/2026-10-08-worker-persist-deadline-design.md`、`docs/superpowers/plans/2026-10-08-worker-persist-deadline.md`；Create `docs/handoffs/codex-r1-persist-deadline.md`。日志/XML/哈希/逐次计时存临时证据目录，不入库课程/认证内容。

- [ ] Step 1：完整定向选择 Task 1～6 及 F02/C01/C09/D11/失败清理/计时回归，保存准确 XML、源 SHA、配置与逐次最大时延；检查额外图入口仍原行为，静态扫描无 thread/executor/shield 提交及私有驱动字段访问。
- [ ] Step 2：先校验临时 Python 的项目声明依赖可被子进程导入；按锁文件安装前端/root npm/Playwright 依赖（缺依赖/受限网络请求审批），保持项目依赖文件不变、不复制 .env。网络/Docker 运行走工具审批，不绕过沙箱。
- [ ] Step 3：运行 basic 以及整次 integration，记录整次 exit 而非拼接部分通过：

```bash
PATH="/opt/anaconda3/bin:$PATH" PYTHONDONTWRITEBYTECODE=1 \
  PYTEST_ADDOPTS="-p no:cacheprovider" ./scripts/verify.sh
PATH="/Users/arvinhan/.docker/bin:/opt/anaconda3/bin:$PATH" \
  PYTHON=/private/tmp/smartsketch-r1-venv/bin/python \
  PYTHONDONTWRITEBYTECODE=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 \
  PYTEST_ADDOPTS="-p no:cacheprovider" ./scripts/verify.sh integration
git diff --check
```

- [ ] Step 4：使用 requesting-code-review 技能安排一次新上下文的只读整分支审查（执行阶段再派发，不并行编辑），重点复核本计划 Review Focus、取消资源退出及迟到结局；修复确定性缺陷后重跑受影响测试和最终完整门禁，记录 deferred 项，不直接信任审查口头通过。
- [ ] Step 5：仅全部网络矩阵、资源退出、R1 恢复和完整门禁有证据时把可用性风险记 CLOSED；缺失/失败则任务保留 OPEN，交接写清结果与后续首步。审批不自动等于关闭、PR 或发布。
- [ ] Step 6：同步实施状态/候选配置已生效状态、ADR-072 清理修订和验证证据；本地提交。停止 worker 后回退至 `e111315` 无迁移，但可用性重新 OPEN；不移除核心 R1 围栏、不删失败测试、不破坏性 reset。移除仅本任务创建的容器/代理，工作区保留。

## 计划自审与执行交接

- 规格 §1～§3：Task 1～2；§4：Task 1/3；§5：Task 1/4；§6：Task 4～5；§7：文件映射；§8：Task 4/6/7；§9：Task 7 回滚/准入。
- Review Focus 五项均绑定测试；接口使用 Task 1 传输→Task 2 门面→Task 4/5 编排，SQLite 不依赖图模块，测试代理不进入产品依赖。
- 本计划只描述未执行步骤；真实网络证据/性能阈值/完整门禁不能引用旧通过。计划书面确认后用 executing-plans，在当前会话顺序实施，不重新询问已选方向或创建新工作区。
