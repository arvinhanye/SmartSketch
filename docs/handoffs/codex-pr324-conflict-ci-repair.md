# PR #324 冲突与 CI 可移植性修复

- 日期：2026-10-09；负责人：Codex；任务：R1-PR324-REPAIR。
- 用户请求：检查 #324 为什么冲突、失败原因并修复。只更新现有分支/PR，不强推、不合并 PR、不部署、不冻结。
- 输入：原 PR head `350d7c6f0569fa5a77f234c0df846d8e1851c402`；抓取 main `5398a1f0d6ea4e27483c3ddb86c2ddecacc77972`；原失败 run `37878331607`。

## 原因及修复

1. `docs/tasks.md` 与 `docs/decisions.md` 双方在相同末尾追加，且 ADR-091/092 各代表两种决定。整合保留主线全部 UI/模型/迁移内容及修复历史，worker 改为 ADR-093/094，同步专属引用；不覆盖主线教师/图谱决定。
2. 原 integration 63 failed/399 passed/4 登记 skip：62 个网络实验在最后记录证据时写入硬编码 macOS `/private/tmp`，Ubuntu 路径不存在；实际故障断言未被删除。改为自有 fixture 输出路径（本地 pytest 临时目录，CI runner.temp），每个实例独立 JSONL，保留写入失败及全部真实网络断言。
3. 1 个真实旧 worker 对照因 checkout 浅克隆找不到 `e111315`。Integration job 拉取完整历史，基线固定完整 SHA；保留真实归档、子进程、10 秒外部 watchdog 及围栏断言。
4. 原失败 run backend-live 44 passed、演示 E2E 2 passed、个人 E2E 4 passed；不是新增产品 E2E 故障。

## 验证计划与当前证据

- 新回归 `tests/tooling/test_worker_network_ci.py`：3 项先 RED，修复后 GREEN（3 passed），日志 `portability-red.log` / `portability-green.log`。
- 定向工具/worker 回归及完整合并结果 `./scripts/verify.sh integration`：待结果；所有原预算/登记 skip 不变。
- 推送现有 PR 后，检查最新 head 的 Linux CI、mergeable；不引用旧 head 结果为新 head 准入。
- 证据根目录：`/private/tmp/smartsketch-pr324-repair-20261009/`；原 CI 完整失败日志 `ci-before-failed.log`。临时文件不提交。

## 变更边界及回退

应用行为无本轮新增修改，worker 源文件仅 ADR 注释引用变化；主线自带迁移/契约/UI 保留。本轮不新增迁移、依赖或预算变化。若需撤销可移植性修复，应针对修复提交逐项回退（将恢复 CI 失败）；不得清理他人修改、强推或删除失败用例。整合前受测代码由 `350d7c6` 保留，但该版本仍与主线文档冲突。原限定风险 CLOSED 证据不删除；新合并结果及远程验收在本任务完成前为待验证。

## 合并后额外计时缺陷

定向 77 项首次为 76 passed/1 failed，失败是主线新增 `test_stop_procs.py` 要求 2 秒宽限，实测全流程 1.770 秒。源码 `SECONDS + grace` 使用整数 wall-clock，最多少等约一秒；新秒边界真实子进程回归测得清理等待 1.305 秒并 RED。最小修复计满 grace×5 次 0.2 秒等待，仍允许已退出进程立即结束，仍在宽限后 SIGKILL；不加依赖、不扩大调用方给定宽限、不改变 worker 围栏或资源退出预算。该修复及原断言进入合并结果全门禁。

Worker 可执行 AST 比较排除文档字符串后完全一致；编号改变只涉及注释/文档字符串。未修改依赖或锁文件。
