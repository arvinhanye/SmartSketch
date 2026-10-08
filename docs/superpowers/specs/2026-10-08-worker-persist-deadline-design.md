# R1 补充设计：worker 提交传输截止与可取消退出

- 日期：2026-10-08。
- 任务：`R1-PERSIST-DEADLINE-DESIGN`；补充 ADR-091，ADR-092。
- 代码基线：`e111315ffabdc5ce980afdf525b8321ef572dc8e`。
- 状态：用户于书面规格交付后要求「确认实施」；**规格已批准，实施计划待审阅，产品代码未实施，发布准入 OPEN**。
- 前置设计：[双租约与提交围栏](2026-10-08-worker-persist-fence-design.md) §3～§6 继续有效；本文细化其 §7，不将已有真实接管测试当作网络故障截止证据。

## 1. 目标、范围与成功标准

用户希望关闭的风险是：Neo4j COMMIT 应答停滞时，同步 worker 持有 SQLite `BEGIN IMMEDIATE` 全局写锁，其他课程及业务写者长期等待。本设计保留 R1 的防旧提交围栏，给其中的网络等待设置客户端总截止，并证明取消后资源退出及恢复行为。

设计轮交付只有书面设计、协议/架构/决策记录和交接；没有新增产品代码、配置生效、网络实验或风险关闭声明。2026-10-08 规格已获用户确认，进入 [实施计划](../plans/2026-10-08-worker-persist-deadline.md) 的编写/审阅阶段；保留先前本会话顺序执行方式，书面计划确认后开始实施。

实施范围限定为 worker `persisting` 显式图事务，以及其必须具备的失败贡献清理顺序。保持同步 worker 编排和 SQLite 同线程事务；教师编辑、发布、QA、融合及维护的其他图入口保持现状。四项中严重程度发现、ADR-061 教师锁残留窗口、整个 worker 进程的一般停机时限均不在范围内。

成功标准：

1. COMMIT 应答黑洞、持续小包/NOOP、断连及已提交但应答丢失，均不能无限延长 SQLite 最终围栏。
2. 取消时真正关闭该事务占用的连接，操作协程结束；不留下后台提交，不跨线程使用 Session/Transaction。
3. 保留双租约、图草稿守卫、SQLite 令牌围栏、图先提交/T6 后可见及完成结果读回；不以取消证明图未提交。
4. 新领取者在同一图草稿守卫后撤销/重建，最终完成不会被旧事务迟到覆盖；耗尽后的清理同样排序。
5. 在约定的健康本机/SQLite测试环境下，量化围栏占用、其他写者等待及资源退出，并运行完整门禁。未满足任一条件仍为 OPEN。

## 2. 已确认事实与方案取舍

本机已安装项目锁定的 Neo4j 5.28.2，Python 下限为 3.11。读取该版本源码确认：同步提交发送后等待应答；同步 Session 无公开 `cancel()`；异步 `AsyncSession.cancel()`/`AsyncTransaction.cancel()` 可终止所持连接，异步提交捕获取消后走连接退出。此为静态证据，不是故障时限实测。

Neo4j 官方说明：取消可能导致连接关闭，但发生取消时服务端操作仍可能已经完成。因此结果不确定的恢复是本设计的一部分。[异步取消说明](https://neo4j.com/docs/api/python-driver/current/async_api.html#async-cancellation)（当前页面版本高于项目锁定版本，能力另外以本机 5.28.2 源码核对）。Python 的截止基于任务取消，调用链必须传播 `CancelledError`，而非吞掉后继续等应答。[Python 3.11 任务与截止](https://docs.python.org/3.11/library/asyncio-task.html#timeouts)

| 方向 | 取舍 |
| --- | --- |
| **选择：worker 专用异步传输＋同步仓储门面** | 使用公开取消能力，无驱动私有 socket patch；改动只落在专用事务及恢复入口。代价是每次尝试独占异步连接池/事件循环和取消故障测试。 |
| 独立进程隔离 | 更强的进程级隔离，但需 IPC、进程监督、退出后的锁/提交恢复协议；保留作首选无法通过准入时的后续评审方向，本轮不引入。 |
| 仅调服务端 timeout/后台提交线程 | 前者不限制应答传输总等待；后者外层返回仍可能留下执行中的提交/写锁，不满足成功标准。 |

不升级 neo4j、不转换全项目到 async、不新增队列/跨库原子提交，不从同步驱动私有字段提取地址、凭据或 socket。

## 3. 组件与线程/事件循环所有权

### 3.1 独立异步传输资源

`Neo4jRepository.from_settings` 保留当前同步驱动，同时保存一个由已加载 Settings 构造的异步驱动工厂。工厂只捕获现有 Neo4j URI/认证参数，不保存或打印凭据副本到文件；创建资源延迟到 worker 专用显式事务入口。

新增内部 `persist_write_transaction` 入口，供 `run_persist_stage` 和失败贡献清理调用；原 `explicit_write_transaction`、`write_transaction` 及读入口保持兼容。worker 生产路径必须使用新入口，缺工厂即在提交前报配置/仓储错误，**没有静默回退同步提交**。纯测试可注入实现同一内部协议的传输替身；替身不是生产回退。

每次专用事务拥有一个 `asyncio.Runner`、一个 AsyncDriver、一个 Session 和一个显式 AsyncTransaction。所有异步资源在该 Runner 的同一线程、同一事件循环中创建、操作和关闭；不跨事务或事件循环复用池。同步门面逐次 `Runner.run`，上一操作完成后才启动下一操作，不并行共享 Session。返回值为已完整消费的普通 dict 列表，原图构建/环检测函数仍同步。使用显式 begin/commit/close，不使用可能在正常退出时自动提交的 Transaction 上下文管理器。

调用前检查线程内没有运行中的事件循环；若有，在创建图资源前明确失败，不通过另起线程、嵌套 `asyncio.run` 或修改事件循环补丁绕过。API 的既有同步图入口不受影响。

### 3.2 职责划分

- `repositories/persist_transport.py`（拟新增）：驱动工厂、Runner 生命周期、绝对截止、同 Task 取消、连接关闭和脱敏传输异常；无任务状态机或 Cypher 业务。
- `repositories/neo4j.py`：复用 `_parameters`/GraphScope 校验，提供同步 ScopedTransaction 门面，检查守卫并记录提交状态。
- `workers/persist_graph.py`：选择专用事务，编排图构建、SQLite 围栏、T6、状态识别和恢复；不得操作私有驱动/socket。
- `repositories/task_leases.py`/`sqlite.py`：为最终围栏提供调用者剩余预算内的锁获取，连接不跨线程；其他连接的默认 busy timeout 保持 5000 ms。

内部接口约定：`repo.persist_write_transaction(scope, check=..., remaining=...)` 接收守卫检查和剩余租约预算回调；门面捕获 `D_tx`，提供原样的同步 `run`、`scope`、`commit_started/committed`，以及 `commit(started_at=...)`。持久化传入 SQLite 取得围栏时的 `t_f`，清理传入其提交开始时刻；门面从该时刻、配置和守卫计算提交绝对截止，不把预算交给底层驱动自行重置。`persist_transaction(..., deadline=D_tx)` 为最终围栏增加可选内部绝对截止；不传时原行为保持。实施计划进一步定义可选 `on_acquired(单调时刻)` 记录回调，在 BEGIN 成功后立即取得 `t_f`，避免令牌查询之后才起计时；旧调用仍得到同一 SQLite 连接。

## 4. 截止预算与时钟

以下取值已随本书面规格获批，**待代码实施才生效**；不是现有运行配置：

| 项目 | 已批准、待实施的取值与规则 |
| --- | --- |
| `TASK_PERSIST_COMMIT_TIMEOUT_SECONDS` | 环境配置，有限正数，默认 **2.0 s**，上限 **3.0 s**；不允许 0/负数/NaN/Inf 或无限等待。 |
| `TASK_PERSIST_CLEANUP_TIMEOUT_SECONDS` | 环境配置，有限正数，默认 **1.0 s**，上限 **5.0 s**；只用于退出时的网络清理，不用于重试，也不放在 SQLite 围栏内。 |
| 本机调度/SQLite 收尾验收余量 `J` | **1.0 s**；是测试准入阈值，不是新的运行配置，也不是 OS/磁盘实时性保证。 |

配置只来自环境与 Settings；实施时才增加 `.env.example` 中无敏感样例和启动校验。当前只在 [集成说明](../../integrations.md) 登记待实施项，不增加生效字段。

定义：

```text
t0 = 专用事务入口的单调时刻
R0 = min(task_guard.remaining(), course_guard.remaining())
D_tx = t0 + R0                       # 图尝试总截止；初次捕获，心跳不延长

t_f = SQLite BEGIN IMMEDIATE 成功后的单调时刻
D_f = min(D_tx, t_f + COMMIT_TIMEOUT,
          t_f + task_guard.remaining(), t_f + course_guard.remaining())

网络阶段的剩余预算 = D - 单调现在     # 不为 run/pull/COMMIT/每个包重置完整 timeout
```

`D_tx` 包括连接建立、认证/路由/池获取、BEGIN、草稿守卫等待、各语句发送及结果消费，直到 COMMIT。初始服务端事务 timeout 使用正的剩余 `D_tx` 预算，但客户端还有独立截止。失败清理没有任务租约，其 `R0` 取课程守卫剩余预算，仍遵守同一非延长规则。

每个有网络等待的完整操作由同一 Task 的 `asyncio.timeout(remaining)` 包围，包括 RUN 后的结果消费；Task 在截止时捕获取消，调用公开 `session.cancel()`，立即重抛 `CancelledError`，由 timeout 外层转换为脱敏异常。每个操作从绝对截止计算剩余时间，持续收到 NOOP/字节也不延长总预算。不使用 `to_thread`、executor 或 shield 包住提交，不使用 timeout 创建的并行 Task 与退出清理竞争资源。

门面每次操作前/返回后还检查双租约与 `D_tx`；COMMIT 发起前再检查 `D_f`。确认收到提交成功后不追溯套用租约失效，把已提交当作回滚；此后按 ADR-091 完成 T6/读回。

申请 SQLite 围栏前先检查剩余 `D_tx`；专用连接的锁等待 budget 取 `min(5000 ms, 剩余预算)`，小于 1 ms 则直接失败，不能向上取整后发新写。连接初始化中可能阻塞的 PRAGMA 与 BEGIN 前均从同一绝对截止重算剩余 busy timeout，不为多次锁等待各分配一份初始完整预算；返回后再检查是否到期。成功取得写锁后立即检查预算/令牌，不为已耗尽的请求发送 COMMIT。该预算只限制锁获取，不修改其他连接的全局默认值。

实际围栏占用从 `t_f` 计到 SQLite COMMIT/ROLLBACK 并退出连接。默认黑洞测试要求 **≤ 3.0 s（2.0 + J）**；配置上限下要求 **≤ 4.0 s（3.0 + J）**。这不是整个持久化耗时、其他写者在所有并发业务下的响应上限，也不是声称 Python 可以在进程暂停/磁盘故障期间硬实时退出。

## 5. 提交顺序、取消与退出

正常路径保持：

```text
专用异步图事务（同步门面）
  → 图 DraftWriteGuard
  → 构建并消费所有图结果
  → SQLite BEGIN IMMEDIATE（有预算的锁获取）
  → 校验任务/课程令牌、阶段、DB 有效期、双守卫与剩余预算
  → 在 D_f 下 await 图 COMMIT
  → 同一 SQLite 连接 T6
  → SQLite COMMIT / 连接退出
  → 专用传输资源清理 / 课程锁退出 / 停心跳
```

网络超时/取消路径：

1. 在正在等待的操作 Task 内调用公开 Session 取消，断开其持有的连接；继续抛出取消，不执行下一条图语句，也不重发 COMMIT。
2. 将 timeout 转成新的内部 `RepositoryTransportTimeout`（拟定稳定脱敏码 `NEO4J_TRANSPORT_TIMEOUT`）。附加状态只含固定阶段枚举 `open/run/commit/exit` 和 `commit_started`，不包含地址、SQL/Cypher、令牌或凭据；与现有语义“未发送查询”的 `RepositoryDeadlineExceeded` 分开。
3. 异常先穿过最内层 SQLite 围栏，使其 ROLLBACK/关闭；**Session/Driver 正常关闭等可等待清理放在围栏退出之后**。取得围栏后除了有截止的 COMMIT，不发起图查询、ROLLBACK/RESET、驱动关闭或连接建立。
4. 专用传输退出统一使用一个固定 `D_cleanup = 清理开始 + CLEANUP_TIMEOUT`；各层关闭共享余量，而非每层各领一份。未提交正常退出可在该预算内尝试 rollback；清理预算耗尽再次公开取消 Session，禁止在无截止的 `finally` 继续等网络。
5. Runner 关闭前，操作 Task 已完成、取消定时器已移除、传输连接已退出；实现测试必须检查没有遗留 Task/执行器网络操作。若驱动退出链吞取消、资源仍占用或 Runner 关闭继续无界等待，准入失败，保留 OPEN，不以外层提早返回代替证明。

清理晚于已确认 T6 时，先使用已有 `t6_seq` 读回识别我们的完成结果；其结果不因传输退出异常被降为 LOST 并撤销。失败清理不得重用已取消的 Transaction/Result。

## 6. 状态分类与恢复

内部状态沿用 `commit_started`（即将调用实际提交前置 true）与 `committed`（完整成功应答后 true）；前者保守包含“调用开始但是否上网未知”，不谎称已证实发送字节。公共任务状态/DTO/错误类型不新增。

| 位置与证据 | 行为 |
| --- | --- |
| COMMIT 前双租约校验失效 | 沿用 R1 返回 LOST，不把租约失效当作预算临时故障主动修改状态；未提交图事务退出。 |
| BEGIN/语句/围栏前截止，`commit_started=false` | 取消并退出未提交图事务；退出资源后仅执行令牌条件的 SQLite 释放/退避。达到最后尝试则 T9 并留 `cleanup_pending=1`，不在该故障分支内调用同步 Neo4j 清理。 |
| COMMIT 发起后超时/断连，未确认成功 | SQLite 回滚、不执行 T6；双守卫标永久失效、停止该尝试发起新续约，返回 LOST（内部日志说明提交不确定）。保留任务 token，由数据库最终租约到期后的新领取/回收判断，不主动撤销、内联重放或宣布图已回滚。课程锁仅令牌条件释放，失败则等过期。 |
| 已确认图 COMMIT，T6/SQLite 提交失败 | 保留 ADR-091：按我们的 `t6_seq` 读回；确认落地则返回成功，未落地/读回失败不得猜测成功或撤销接管者。本专用事务路径的故障恢复不调用旧同步图补偿，必要清理留给后续回收。 |
| 图与 SQLite 均确认成功，随后传输退出失败 | 确认我们的 T6 后仍返回成功；不重复递增水位/修订号。 |

**迟到服务端完成的恢复边界**：取消关闭客户端连接，不保证服务器立刻停止已接收的 COMMIT。此时 SQLite 围栏已释放，接管可能先更新 token；任务未进入 V，旧贡献仍不可见。新尝试必须等待同一个 Neo4j DraftWriteGuard：旧事务的提交或回滚结局在释放该图锁前确定，新尝试随后撤销该任务旧贡献并重建。证明目标是“旧事务不越过已完成的新图尝试并覆盖它”，不是“所有取消都使服务器 COMMIT 数为零”。

心跳标失效前已发起的 SQLite 续约可能仍在锁等待中，退出使用既有 busy timeout 收束；其迟到成功不使本地守卫复活，但可能改变数据库最后有效期。恢复读取 DB 的最终到期值，不将对象创建时的 expires_at 当作固定接管时刻；不承诺整个 worker 在提交预算内完成所有线程退出。

若未进入 COMMIT 就检测到接管，原 R1 的旧 worker 零提交要求保持不变。未取消且正常提交期间 SQLite 围栏仍阻止接管更新穿越，原一致性证明保持。

### 6.1 必需的失败贡献清理修订

现有 `cleanup_failed_task` 先通过 `task_has_contributions` 预读；无贡献时不取图锁直接清标记。取消后存在服务端迟到提交，因此“failed 任务不会再写”的前提不足：回收可先 T9，预读看到空，随后旧服务器事务提交贡献。

对该 worker 清理入口统一采用：

```text
课程写锁/守卫 → 专用有截止显式图事务 → DraftWriteGuard
  → 幂等 revoke_task（即使无贡献）
  → 有截止 COMMIT，确认成功 → 退出传输/课程锁 → 清 cleanup_pending
```

不在 SQLite 围栏内等待清理图 COMMIT。只有确认清理提交且退出后才清标记；应答不确定、守卫失效或退出错误均保留 `cleanup_pending=1`，下一轮幂等重试。取消恢复路径不绕回旧同步清理。无贡献清理也需要图守卫，代价是额外连接/锁等待；此为 ADR-072 该特定入口快路径的拟议修订，不调整发布清扫其他协议。

清理业务事务的提交截止为 `min(D_tx, 提交开始 + COMMIT_TIMEOUT, 课程守卫截止)`；其图锁/撤销仍在整个 `D_tx` 内。`CLEANUP_TIMEOUT` 只控制退出资源清理，不指撤销贡献的完整业务耗时。课程守卫失效时清理返回 `False` 并保留标记；持久化的任务租约失效继续返回 LOST。

测试必须让旧事务持有 DraftWriteGuard，清理先开始并观察不到贡献，然后旧事务完成；清理应在同一图守卫之后撤销迟到贡献，不能提前清标记。只测“提交成功后丢客户端应答”不足以覆盖此排序风险。

## 7. 文件与接口边界

| 拟改范围 | 变化 |
| --- | --- |
| `src/backend/app/repositories/persist_transport.py`（新增） | 异步资源/Runner、截止与取消、统一清理预算及可注入工厂。 |
| `src/backend/app/repositories/neo4j.py` | worker 专用同步门面/工厂；原仓储入口保留；新增内部传输错误，不改外部 error wire。 |
| `src/backend/app/repositories/sqlite.py`、`task_leases.py` | 专用围栏的可选连接锁获取预算；原默认值/其他调用者不变。 |
| `src/backend/app/workers/persist_graph.py` | 使用新入口与预算；不确定结果分类、超时失败延迟清理、失败贡献清理取得图守卫。 |
| `src/backend/app/config.py`、`.env.example` | 实施时新增两个有限正数环境配置及范围校验；复用 Neo4j 地址/认证，不新建密钥。 |
| `tests/backend/test_worker_persist_fence.py`、`test_worker_graph_transaction.py` 及拟新增 `test_worker_persist_transport.py` | 生命周期/截止/守卫/状态分类与取消回归；保持既有 R1 断言。 |
| `tests/integration/test_worker_persist_fence.py` 及测试专用 TCP 代理夹具 | 真 Neo4j/SQLite 网络故障、独立写者和恢复验证。 |
| 配置/清理相关现有回归 | 覆盖新的配置边界和 ADR-072 清理顺序，不删除无贡献用例或降低原断言。 |

无公共 API/事件/DTO、SQLite 表/迁移或 Neo4j 持久化属性变更，无项目依赖升级。代码不解析测试代理协议、不创建生产代理或后台网络线程。

## 8. 验收矩阵与可复跑证据

### 8.1 确定性回归

- 注入单调时钟，验证总预算不会因心跳、RUN/PULL 分步、分片应答而重置；到期前不发新语句/COMMIT。
- Session/Transaction/Driver 与 SQLite 围栏均在调用线程；不同尝试用不同 loop/pool；活跃事件循环调用在网络前失败。
- 取消确实调用公开取消、协程退出且结果/连接不可复用；没有后台提交、shield 或跨线程 close。
- 图成功应答后越过本地截止仍按已提交结果做 T6；应答丢失不声称回滚，T6 只增一次。
- SQLite 围栏退出先于异步等待清理；正常 rollback、清理故障、清理截止共享同一退出预算。
- 实际任务/课程心跳调用者覆盖延迟、连续失败、零行续约和失效不复活；闭环原独立审查的 Minor 缺口。
- 超时的最后一次尝试进入 failed 时保留清理标记，故障分支不触发同步图清理；失败任务无贡献清理也等待 DraftWriteGuard。
- 正常路径、原入口与阶段计时回归；新增围栏计时不与 `neo4j_ms`/`t6_ms` 叠加算总耗时。

### 8.2 真网络故障（不是 tx.commit 替身）

临时 Neo4j 5.26-community、临时 SQLite、仅回环的测试 TCP 代理；不连接用户数据库，不调用模型。测试代理记录阶段/单调时刻，不记录认证内容或课程正文。对 Bolt COMMIT 消息及应答定向注入，基线/修复均经相同代理。

| 场景 | 必需断言 |
| --- | --- |
| COMMIT 下行应答被丢弃但 TCP 保持打开 | 在截止内结束操作，SQLite 回滚且其他课程写者取得锁；客户端连接关闭；图结果经直连独立查询识别，而非推测。 |
| COMMIT 应答期间持续 NOOP/少量字节 | 不按每包重置截止；达到同一总预算退出，无半响应留下后台任务。 |
| COMMIT 出站前/后分别断开 | 分开记录 dispatch 状态、图实际结果、T6 未执行及后续恢复，不用一个失败断言替代。 |
| COMMIT 成功但成功应答不达客户端 | 旧任务未进入 V；新领取在图守卫后撤销/重建，T6/修订号只增加一次，接管者贡献保留。 |
| 延迟旧 COMMIT 的服务端执行/图锁释放 | 旧请求可在取消后结局确定；接管/failed 清理通过同一图守卫排序，最终无迟到孤儿贡献或提前清标记。 |
| BEGIN、草稿锁或结果消费应答黑洞 | 不持有 SQLite 最终围栏；按 `D_tx` 退出，连接与 Task 释放。 |
| 回滚/Session 退出应答停滞 | SQLite 围栏先退出；清理不超过共享预算，客户端资源不留存。 |
| 健康网络正常执行 | 记录提交 latency 与围栏时长，T6 一次、其他入口兼容，无新增失败/skip。 |

服务器执行延迟场景可用独立第三方事务持锁及真实代理定向转发形成屏障；不能在代理缓冲 COMMIT 后待客户端断开再人为注入新请求，冒充服务器已接收旧请求。具体夹具在实施计划中定义，验收必须区分代理已见字节、服务器已接收/执行和图锁已释放的证据。

独立 SQLite 写者在 `BEGIN IMMEDIATE` 成功的屏障后启动，写其他课程/业务行，`busy_timeout=0` 做探针并统计失败次数/直到成功的墙钟时长；另用默认 5000 ms 的写者核验默认配置下能完成。记录：`fence_acquired`、`commit_started`、`cancelled`、`fence_released`、`writer_acquired`、`transport_closed`，使用同一单调时钟。

每个网络场景至少 5 次，逐次保存最大值，不用均值/百分位掩盖超阈值。默认网络等待 ≤2.0 s＋调度余量、围栏/单个探针等待 ≤3.0 s；配置上限围栏 ≤4.0 s。所有故障下 Session 退出及操作 Task 结束在清理预算＋J 内完成。测试总 watchdog 为安全兜底；触发即 FAIL，清理测试夹具后保留失败日志，不当作产品取消成功。

这些限值依赖健康 SQLite 与可调度进程，不能外推磁盘挂死、SIGSTOP、任意并发写流或服务器自身永不释放锁。其他写者的多业务总体 SLA 不在本次保证内。

### 8.3 命令与发布准入

本轮设计验证：

```bash
git diff --check
PATH="/opt/anaconda3/bin:$PATH" PYTHONDONTWRITEBYTECODE=1 \
  PYTEST_ADDOPTS="-p no:cacheprovider" ./scripts/verify.sh
```

实施后的最低命令（新测试文件只有实施后才存在）：

```bash
PYTHONPATH=src/backend python -m pytest \
  tests/backend/test_worker_persist_transport.py \
  tests/backend/test_worker_persist_fence.py \
  tests/backend/test_worker_graph_transaction.py \
  tests/backend/test_c09.py tests/backend/test_d11.py \
  tests/backend/test_264_cleanup_lock.py tests/backend/test_c02_phase_logs.py -q
./scripts/verify.sh integration
```

真实故障用例必须纳入 integration 入口、运行到位，不新增忽略/登记 skip 来关闭风险。实施交接记录准确环境/配置、每种故障的计时/XML、代码 SHA、资源退出及接管/清理图结果。旧代码经黑洞夹具应超过预算（由测试 watchdog 收束）形成负向证据。另做删除 deadline/取消及恢复排序的临时故障变异，证明测试有效。

原 214/34 测试证据继续只证明 `e111315` 的 R1 核心结果；不代替补充方案及整次完整门禁。风险 CLOSED 需新代码、全部矩阵与全量门禁证据，随后仍由用户决定提交 PR/合并/发布。

## 9. 风险、回滚与审批

- 默认 2 s 提交预算可能在慢图存储上增加 L3 重试；实施需测健康路径 latency。超阈值先评审预算/容量，不在失败测试里自动增大配置或跳过断言。
- 每次图尝试的独占池会增加握手开销；先保持易证明的生命周期，不提前引入跨 loop 池共享。
- asyncio 取消是协作式机制；单靠源码/API 不能宣布总截止。公开取消、物理 TCP 退出、Runner 清理和 SQLite 围栏时限同时通过才准入；失败则评审进程隔离，不私有 patch 驱动。
- 图连接在取得 SQLite 围栏前建立；截止覆盖其协程等待，但不将 Python 默认 DNS 执行器的线程退出称作硬取消。连接/解析挂起时不得取得围栏，Runner 退出异常照实登记；本次围栏可用性验收假设本机解析可完成，不扩展到 DNS 进程隔离或整个 worker 的停机 SLA。
- 无贡献清理改为图守卫内幂等撤销，增加课程锁争用；正确排序优先，性能回归实测。
- 停止 worker 后恢复 `e111315` 的产品代码即退回本轮前行为；无数据迁移，但会重新暴露无界提交等待，发布准入随之重新 OPEN，不能把该版本当作已关闭风险的回滚目标。保留日志与测试，避免破坏性 reset。
- 当前文档可独立回退；没有业务库/密钥/部署修改。规格已获确认，实施计划待书面审阅；计划轮不实施产品代码、不推送、不创建 PR、不合并或冻结。
