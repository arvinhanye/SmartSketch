# Codex — R1 worker 持久化提交围栏实施交接

## 状态与交付

- 用户在书面规格交付后要求「实施修改」。基线 `9c5ed3e`；复用受管 detached HEAD worktree，顺序实施。
- 状态：`IMPLEMENTED_LOCAL`，核心接管竞态修复及真实 Neo4j 回归通过；**发布准入 OPEN**。不推送、不合并、不操作用户业务库。
- 无 API/DTO/环境变量/项目依赖/数据表或 Neo4j 属性迁移；其他托管图事务调用者保留原入口。其余四项中严重程度发现、教师编辑 ADR-061 风险不在本次修复范围。

## 实际修改

| 文件 | 交付 |
| --- | --- |
| `src/backend/app/repositories/lease_guard.py` | 双租约单调截止、线程安全与终态失效；按已确认到期时刻保守初始化，不以新对象赋予新 TTL |
| `src/backend/app/repositories/task_leases.py` | worker 可选严格续约；同连接最终 `persist_transaction` 校验任务/课程双令牌、课程、阶段和到期等号 |
| `src/backend/app/repositories/course_locks.py` | worker 可选守卫，续约零行/本地截止传递失效；教师默认接口兼容 |
| `src/backend/app/repositories/neo4j.py` | `explicit_write_transaction`，语句发送前/返回后检查，显式 commit，关闭未提交事务而不自动提交，无透明重放 |
| `src/backend/app/workers/parse_task.py` | 任务心跳记录调用前续约时刻，拒绝到期复活，向 pipeline 暴露守卫 |
| `src/backend/app/workers/persist_graph.py` | 图草稿守卫 → SQLite 围栏 → 图 COMMIT → `_t6_in` → SQLite COMMIT；直接调用也有心跳；提交/退出异常读回已完成 T6 |
| `tests/backend/test_worker_persist_fence.py`、`test_worker_graph_transaction.py` | 确定性接管、截止、围栏互斥、正常 T6、提交应答丢失与资源退出回归 |
| `tests/integration/test_worker_persist_fence.py` | 实际 Neo4j 守卫排队后接管回滚、真实提交后注入丢失应答并重建一次、提交边界阻塞/断连注入 |
| `tests/backend/test_c02_phase_logs.py`、`test_d11.py`、`tests/integration/test_f13.py` | 内部显式事务/同连接 T6 注入点适配；保留原业务断言，D11 续约样例避整数秒等号竞态 |
| 设计、计划、任务协议、架构、ADR-093、任务状态 | 同步实际实施与未闭环发布条件 |

`neo4j_ms` 是显式事务作用域（含最终围栏），`t6_ms` 是嵌套跨库提交子区间，两者不相加；`neo4j_attempts` 为每次显式尝试的回调次数 1，失败重领是新尝试。阶段墙钟使用 `total_ms`。

## 已验证证据

日志与 XML 在 `/private/tmp/smartsketch-ocr-46o1tbcy/`（本机临时证据，不入库）：

1. `r1-guards-red.log` → `r1-guards-green.log`：新增接口缺失导致 10 失败；实现后 C09/D11/守卫合计 105 passed。
2. `r1-graph-red.log`：显式事务接口缺失 6 失败；后续组合验证通过。
3. `r1-worker-red.log` → `r1-worker-green.log`：接管仍提交/无最终围栏等 6 失败；C09/D11/清理/计时等合计 132 passed。
4. `r1-live-red.log`：真实 Neo4j 中临时加载旧 worker，在接管后仍有旧任务 `KnowledgePoint`，测试确实失败；工作区始终保留修复代码。
5. `r1-live-green.log`：修复版本 F13 与新真实事务回归 34 passed，无 skip；最终同范围再验 34 passed，见 `r1-live-final.log` / `r1-live-final.xml`。
6. `r1-exit-red.log` → `r1-exit-green.log`：确认 T6 后退出 `LeaseLost`/`RuntimeError` 导致错误返回，2 失败；修正结果读回后组合 39 passed。
7. 独立审查 Important 测试缺口已补：围栏校验后/提交发送前截止零 COMMIT/零 T6；提交已发送后截止仍阻挡双令牌接管且 T6/修订号各一次。临时进程内分别删除最终检查、增加事后失效检查，两测试各失败，见 `r1-final-mutation-before.log`、`r1-final-mutation-after.log`；仓库未保存变异代码。
8. `r1-targeted-final.log` / `r1-targeted-final.xml`：214 passed。命令：`PYTHONDONTWRITEBYTECODE=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH="/private/tmp/smartsketch-r1-testdeps:$PWD/src/backend" /Users/arvinhan/SmartSketch/.venv/bin/python -m pytest tests/backend/test_worker_persist_fence.py tests/backend/test_worker_graph_transaction.py tests/backend/test_f02.py tests/backend/test_c09.py tests/backend/test_d11.py tests/backend/test_264_cleanup_lock.py tests/backend/test_c02_phase_logs.py -q -p no:cacheprovider`。
9. `r1-code-verify.log`：`PATH="/opt/anaconda3/bin:$PATH" PYTHONDONTWRITEBYTECODE=1 PYTEST_ADDOPTS="-p no:cacheprovider" ./scripts/verify.sh` basic exit 0，237 契约测试及 25 门禁负向测试通过。最终文档同步后同一门禁 exit 0，见 `r1-final-basic.log`。
10. `git diff --check`：通过；新设计/计划/交接 TODO/TBD 扫描及设计链接解析通过。
11. `r1-backend-full-final.log`：`PYTHON=/Users/arvinhan/SmartSketch/.venv/bin/python ./scripts/verify/backend.sh full`（带临时依赖 PYTHONPATH、禁用插件自动发现）：3945 passed、27 skip、1 failed、6 errors；七项不通过均是 `tests/tooling/test_b07.py` 子进程移除 PYTHONPATH 后失去测试依赖，**该 full 门禁未通过**。
12. 创建 `/private/tmp/smartsketch-r1-venv`，通过仅该环境的 `.pth` 引用临时测试依赖及既有 Python 3.11 应用依赖，使子进程也有正确依赖；`r1-isolated-env.log` / `.xml`：`/private/tmp/smartsketch-r1-venv/bin/python -m pytest tests/tooling/test_b07.py tests/backend/test_worker_persist_fence.py tests/backend/test_worker_graph_transaction.py -q -p no:cacheprovider`，45 passed（包括全部原失败模块和新回归）。未重跑完整 full，不把分层复验表述成单次全量门禁通过。

测试工具只安装到 `/private/tmp/smartsketch-r1-testdeps`，最终 test 顶层版本与项目 optional-dependencies 一致。Python 3.11 运行时来自既有环境，项目依赖文件未变。第一轮 full 后端因缺 PyYAML 收集失败，补齐测试依赖后重跑，原失败日志不作为修复验收。

## 独立审查与明确跳过

- 独立只读 reviewer 审查 13/13 核心代码/测试/计划文件，无确定性新运行时缺陷；Important 提交前/后截止验收缺口已补，以故障变异与最终正常测试验证，不再派第二轮 reviewer。
- Minor 暂缓：延迟/连续异常续约已测守卫本身，但两个实际心跳调用者循环的对应故障注入尚待补充。
- 新文档状态同步由主 Agent 自审；未把它表述为 reviewer 重审通过。
- 前端门禁尝试结果 `r1-frontend-full.log`：缺 `src/frontend/node_modules`；本任务不安装/调整无关前端依赖。不宣称完整 `full` 或 `integration` 门禁通过；未跑 E2E。
- 真实 Neo4j 测试使用本任务新建临时容器、随机课程，仅清理各自课程；不调用真实模型。测试后已移除本任务容器（`docker rm -f smartsketch-r1-fence-20261008` exit 0）。公开事务边界的注入不是物理网络断连/总截止证明。

## 执行决定（含代价）

1. 将「实施修改」按规格确认和直接顺序执行指示处理，不再重复启动确认；若理解偏差，用户可能原希望先看独立计划评审。
2. 逐步红/绿日志保留，任务代码在整体验证后统一保存本地提交；Git 元数据在 worktree 沙箱外，减少反复提交审批，代价是中间提交粒度较粗。
3. 守卫在开 Session 前拒绝时，测试断言“没有创建资源”，而非“未创建的 Session 已关闭”；错误断言会把正确的提前拒绝误报成泄漏。
4. D11 fixture 续约窗口由 `unixepoch()+1` 变为 `+5`，到期等号拒绝另有明确测试；代价是该续约 fixture 允许更长启动间隔，不改变产品 TTL。
5. 计时替身改显式事务而非模拟透明重跑，异常退出先识别已完成 T6；代价是仅实现旧内部 API 的自定义替身须适配新 worker 内部入口。
6. 保留发布阻塞：公开提交边界注入不视作传输层截止证据；忽略此决定的代价是图应答停滞时 SQLite 全库写者长期等待。

## 首个后续动作与回滚

先在独立环境完成物理网络停滞/断连的端到端总截止、资源退出与全库写者等待上限验证。当前服务器事务 timeout 不保证同步驱动客户端总等待，未引入跨线程取消或后台提交。若等待持续无界，按已确认设计补充传输截止/隔离方案评审后再发布。

本轮仅本地保存，代码没有安装到用户运行进程。无数据迁移；需要回滚时先停 worker，再恢复基线 `9c5ed3e` 的产品代码。回滚重新暴露 R1，不作为问题已处理；不对共享工作区使用破坏性 reset，不删除测试或业务数据。
