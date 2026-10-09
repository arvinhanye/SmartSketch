# PR #324 冲突与 CI 可移植性修复

- 日期：2026-10-09；负责人：Codex；任务：R1-PR324-REPAIR。
- 最初用户请求：检查 #324 为什么冲突、失败原因并修复，仅更新现有 PR；后续用户明确授权「CI通过就合并PR」，按最终 head 全绿门禁合入 main。不强推、不部署、不冻结。
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

## 独立只读审阅与边界裁决

按 requesting-code-review 技能，独立审阅本轮六份代码/测试修复、文档合并与编号引用；未发现 Critical/Important/Minor 阻塞，未编辑文件或运行服务。实查完整基线 SHA 是当前 head 祖先，双方文档所有非空主线行保留，worker 决定在重编号后完整保留。审阅未将尚未结束的全量门禁/CI 判作通过。

- 原 worker 事务/取消/恢复协议：接受不重复审查，原独立审阅已完成，本轮逐项确认预算/断言与可执行 AST 未被更改。
- 无关主线 UI/模型/迁移：接受本轮不扩展修复范围，但纳入合并结果全门禁；主线内容完整保留。
- 一般进程组/PID 生命周期：接受既有非本轮变更边界，不宣称本次解决其所有情况。
- 调度暂停下的生产硬实时停机：接受不在 E2E 清理脚本承诺内；不外推 worker 围栏限定保证。
- 合并结果完整门禁/Linux CI：保留为本任务必须取得的最终证据，不接受以定向 GREEN 或旧 head 替代。
- ready/合并/部署/冻结：原 PR 保持草稿；本次更新不自动合并/部署/冻结，最终是否送审由用户决定。


## 最终代码 CI 验收及合并决定

代码 head `36b421e165772c7428aac26d30d3b4009f9ad510` 已在 push run [37904046120](https://github.com/arvinhanye/SmartSketch/actions/runs/37904046120) 和 PR run [37904049198](https://github.com/arvinhanye/SmartSketch/actions/runs/37904049198) 中全部通过，共 8 项 SUCCESS；base `5398a1f0`，MERGEABLE/CLEAN。原 CI 的 63 项失败均消除，E2E 不靠跳过获取通过。

| 阶段 | 本轮 Ubuntu CI 实际结果 |
| --- | --- |
| scaffold/contracts | PASS |
| backend + tooling | 4064 passed / 27 原登记 skip |
| frontend | 1227 passed / 66 文件；type-check/build PASS |
| integration | 462 passed / 4 原登记 skip |
| backend-live | 44 passed |
| 演示 E2E / 个人 E2E | 2 passed / 4 passed |

网络 artifact `11603737657` / `worker-network-evidence` 已下载，73 行逐次计时机读通过；所有行产品 SHA `12dcfdbfc6caa30898a357196dff9ebcd1a61539a67ee4ccd40e7fc675e22629`、测试 SHA `3bcedc1e00fb31d5c699112829c9b85b1cfb70417e7817a82ea39faba8b54cfa` 与当前文件一致。默认/上限围栏最大 2.002760/3.003735s，写者 2.031202/3.031960s；退出 1/5s 最大 1.170164/5.176260s；迟到提交 takeover 5/5、failed_cleanup 3/5，恢复收敛；旧基线 10s watchdog 仍占围栏。保持原 3/4s 与预算+1s 阈值、所有真实物理退出/恢复断言。

本地整次门禁因用户中断停止，backend 未完且无完整退出码；已实查原进程不再运行。登记 INTERRUPTED，不记成功或编造失败；CI 分别完整运行本轮同源码的四个实际门禁，作为 Ubuntu 可移植性最终验收。保留 `whole.log` 原始未完成记录；补充最终本地 basic 后再推送纯文档提交，最终提交 CI 独立核对。

用户本轮授权条件合并；使用 `--merge --match-head-commit <最终已验 SHA>`，不 bypass/强推，不删除分支或宿主受管工作区。保留 Git 历史以支持 pinned 历史基线后续在 main 的真实负向回归，不使用 squash 丢失祖先。PR 实时状态/mergeCommit 为最终合并结局权威；本地交接不预写尚未发生的合并。无部署/冻结授权。

**状态**：R1-PR324-REPAIR DONE_CI_VERIFIED；worker 网络 COMMIT 无界占用 SQLite 围栏限定风险 CLOSED。其他入口/DNS 执行器/一般进程停机/宿主暂停/存储异常，以及原中严重程度问题仍为原边界；全项目 stage_c_status OPEN、technical_freeze NOT_PERFORMED。历史“草稿/不合并”决定只属于用户新指令前的阶段。

证据目录 `/private/tmp/smartsketch-pr324-repair-20261009/`：`ci-code-head.log`、`pr-merge-current.json`、`ci-code-network/`、`ci-code-network-summary.json` 及全部 RED/GREEN/中断记录。

- 最终文档收尾验证：本地 `./scripts/verify.sh` 实际 exit 0，scaffold/contracts 全 PASS；文档版本的 CI 可移植性/ADR 唯一编号三项回归 3 passed，`git diff --check` 通过。最终待提交差异仅 `docs/tasks.md`、`docs/decisions.md`、本交接三份文档；产品/测试/脚本与已通过代码 head `36b421e` 完全相同。
