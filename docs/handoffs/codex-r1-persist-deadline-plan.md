# Codex 交接：R1 截止补充实施计划

- 日期：2026-10-08；任务 `R1-PERSIST-DEADLINE`。
- 工作区：`/Users/arvinhan/.codex/worktrees/0cf7/SmartSketch`，复用受管 detached HEAD worktree。
- 输入文档提交：`e41e951`；产品代码仍为 `e111315` 的 R1 核心修复，无本轮产品改动。
- 用户确认：「确认实施」，批准已交付书面规格与实施意图；未存在的书面计划尚待审阅。保留本会话顺序执行方式，计划确认后使用 executing-plans。
- 当前：PLAN_WRITTEN_PENDING_REVIEW；可用性风险/发布准入 OPEN。

## 交付与范围

计划 `docs/superpowers/plans/2026-10-08-worker-persist-deadline.md`；同步规格已批准/计划待审阅状态到 tasks、架构、ADR-092、集成说明、原 R1 规格和任务协议。不改产品代码、测试、有效配置、依赖或数据库；不创建新 worktree、不派发实施 Agent、不推送/PR/合并/冻结。

计划按七个可独立验收任务：传输/配置、仓储门面、SQLite 围栏预算、worker 状态恢复、failed 清理排序、真实 TCP 故障、完整门禁/独立审查/交接。每任务 RED→GREEN 后本地提交，共享文件串行修改。

计划细化：传输叶层超时在仓储门面映射为 RepositoryTransportTimeout，避免循环依赖；围栏增加可选 `on_acquired(单调时刻)` 记录回调，BEGIN 后立即捕获时刻，旧调用默认 None/同一连接返回不变。这两项是计划中待评审的内部接口细节，不是已实施变化。

确认的预算为提交默认 2 s/上限 3 s、退出清理默认 1 s/上限 5 s；默认围栏 ≤3 s、上限配置 ≤4 s 是待实测准入。真实 TCP 代理须透明处理固定/Manifest 握手，认证正文不写日志；每故障至少 5 次，记录最大值。迟到结局需真实观察取消后服务端提交；只观察回滚不冒充该项覆盖。

## 验证与证据

- 计划自审：规格 §1～§9 覆盖、跨任务类型/接口和五项 Review Focus 对应测试核对通过；9 个 docs/specs 文件、24 条本地链接通过，35 项实施步骤未执行，产品树/运行配置不变。
- `git diff --check`：exit 0。
- `PATH="/opt/anaconda3/bin:$PATH" PYTHONDONTWRITEBYTECODE=1 PYTEST_ADDOPTS="-p no:cacheprovider" ./scripts/verify.sh`：本轮实际 exit 0，契约测试 237 passed（3/6/5/45/125/53）、负向门禁 25 项通过，契约真源/生成物一致。
- 日志 `/private/tmp/smartsketch-ocr-46o1tbcy/r1-deadline-plan-verify.log`；文件/链接/状态/哈希记录 `/private/tmp/smartsketch-ocr-46o1tbcy/r1-deadline-plan-check.json`。
- 本轮仅计划与既有基础门禁，无新产品/物理网络/full/integration 验收；不把旧 214/34 回归或本轮 237 契约测试写作补充实现证明，风险仍 OPEN。

## 下一动作与准入

请用户审阅实施计划；确认后按已保留的本会话顺序方式实施。真实测试新建仅自有随机名/标签容器及回环代理，移除仅本任务资源。完整 integration 需有效临时 Python、前端/root npm/Playwright 与 Docker，安装/网络/端口受限时走工具审批。

资源退出、SQLite 时限、迟到结局/清理排序或全量门禁缺任一证据仍 OPEN，不新增 skip、不放宽阈值、不擅用私有 socket patch。未来回退至 `e111315` 保留核心 R1 围栏但可用性重新 OPEN；无迁移，本轮仅文档可独立回退。
