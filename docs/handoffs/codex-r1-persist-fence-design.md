# Codex — R1 持久化提交防护设计交接

## 任务与状态

- 任务：R1-PERSIST-FENCE。
- 基线：`bdb89c4`，受管 worktree 初始无未提交变更。
- 用户已确认聊天方案；本轮落书面规格，尚待书面评审。产品代码、测试和业务数据保持原样，R1 未修复。

## 文件与关键决定

- `docs/superpowers/specs/2026-10-08-worker-persist-fence-design.md`：意图、双租约截止、显式事务、最终围栏、故障恢复、文件边界、九项验收。
- `specs/task-processing.md`、`docs/architecture.md`：增加有明确「尚未实现」状态的设计引用。
- `docs/decisions.md`：ADR-091，区分聊天确认、书面评审与实现验收。
- `docs/tasks.md`：认领与状态、输入输出、依赖、风险和下一步。

最终顺序：图守卫 → SQLite 提交围栏 → 验证两个数据库令牌/有效期 → 图提交 → 同连接 T6 → SQLite 提交。围栏不覆盖图构建，不做透明回调重试。没有数据库迁移/公共接口/依赖/配置变化。

## 验证

- `PATH="/opt/anaconda3/bin:$PATH" PYTHONDONTWRITEBYTECODE=1 PYTEST_ADDOPTS="-p no:cacheprovider" ./scripts/verify.sh`：basic exit 0；契约回归 237 passed，门禁负向测试 25 项通过。
- `git diff --check`：exit 0。
- 新规格/交接 TODO/TBD 扫描与任务协议/架构设计链接解析：通过。
- 门禁完整日志：`/private/tmp/smartsketch-ocr-46o1tbcy/r1-design-verify.log`（本机临时证据，不随 Git 提交）。
- 自审澄清 COMMIT 发出前失效应回滚、发出后应识别实际结果；范围、锁顺序和剩余可用性风险保持一致。规格产物与 basic 结果不作为漏洞修复验证证据。

## 未完成与首个动作

用户评审本书面规格后，编写实施计划并确定执行方式，再写失败测试和产品修复。本轮未运行新增代码回归或真实 Neo4j 故障测试。

重点风险是全库 SQLite 写者等待和图 COMMIT 应答阻塞；当前同步驱动没有公开 `Session.cancel()`，服务器事务 timeout 不是客户端提交应答硬截止。实现准入必须证明故障退出/恢复，出现持续无界等待则不发布，并按任务记录提请补充设计评审。其余四项中严重程度发现和教师编辑旧租约审计风险仍保留。

## 回滚

本轮仅文档，可独立回退本轮文档提交；不需业务库操作。后续代码回退会重新暴露 R1，须停 worker 并明确记录。
