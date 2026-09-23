# PLAN-01 架构审查和原子任务规划交接

- 负责人：Codex；日期：2026-09-22；状态：DONE（仅本轮文档与初始审查，不是全部实施完成）。
- 当前目录：`/Users/arvinhan/Desktop/SmartSketch`；基线：`05d214c09b770b0a18268f5e1ee27bb5194bc1dd`。
- 执行前 main 与四个 Claude worktree 干净。本轮没有修改 Claude worktree，没有业务源码变更，没有 git 提交/合并/推送。

## 交付物

- `docs/architecture-review-2026-09-22.md`：全部已读技术领域、实现状态、数据流、模型不变量与风险。
- `docs/atomic-task-plan.md`、`docs/atomic-tasks.json`：127 个未认领叶子任务（119 主线 + 8 条件性加分），含输入/输出/依赖/范围/验收/单测命令/风险/回滚。
- `docs/reviews/codex-claude-initial-2026-09-22.md`：5 项首轮问题，具体到 worktree 文件和行号。
- `docs/claude-review-workflow.md`、`docs/reviews/claude-review-state.json`：完成信号、稳定性、增量游标、去重与尚未审查范围。
- `docs/reviews/validate_atomic_plan.py`：计划结构检查器；检查固定日期快照，任务数变更时需同步期望值。
- `docs/tasks.md`、`docs/architecture.md`、`docs/integrations.md`、`docs/handoffs/README.md`：增加入口、未决事项和审查登记。

## 实际验证

| 命令/动作 | 结果 |
| --- | --- |
| main：`./scripts/verify.sh` | exit 0；仅 scaffold 结构通过 |
| 契约 worktree：`./scripts/verify.sh` | exit 0；PyYAML 缺失，契约 SKIP；首轮报告 R02 |
| 协作 worktree：`./scripts/verify.sh` | exit 0；结构通过，backend/frontend/contracts 全部 SKIP |
| `python3 docs/reviews/validate_atomic_plan.py` | 127 ID 唯一、依赖存在且无环、Markdown/JSON 对齐、字段齐全、11 个本地链接有效 |
| `git diff --check` | exit 0 |
| 当前项目 JSONL 元数据和两分支末尾答复读取 | 成功；已核对 cwd/分支/stop 标记，不复制原始对话入库 |
| 原子清单中未来的 pytest/npm/E2E 命令 | 未执行；所有条目均标记 NOT_RUN_PLANNED，非本轮验收证据 |
| YAML/JSON Schema 运行库探测 | 缺少解析器/验证器；引用问题为静态审查，没有宣称 schema 负例实跑 |

可复跑协调文档验证：

```bash
cd /Users/arvinhan/Desktop/SmartSketch
python3 docs/reviews/validate_atomic_plan.py
./scripts/verify.sh
git diff --check
```

## 接口与数据影响

没有修改运行时 API、数据库、依赖或密钥。机器可读计划和审查游标是新增协调资产。现有 M0/M1 状态未因其他 worktree 的提交而自动标完成。未把本次建议写成已签收 ADR。

## 自动审查

通过应用工具实际创建 `claude-smartsketch` heartbeat，返回 ACTIVE；每 10 分钟检查，绑定本任务。首次调用缺 destination 导致参数错误，补 `destination=thread` 后创建成功，并调用 view 查看。没有重复创建，也没有自制 cron/Stop hook。自动跟进本身已启用；未来调度/审查尚未发生，本轮不把它当作已验证的端到端联动。

暂停/删除通过应用自动化工具执行；运行前提见集成文档。尚未完整审查的 hook/Compose/脚本列在 state 中，不能把初始报告当全分支通过。

## 首个后续动作与风险

1. 技术负责人签收 A01 的契约真源与编号，项目负责人确认 A10 的集成基线；两个分支目前不能直接按各自“唯一来源”同时实现。
2. 先处理 R02 门禁假绿与 R03/R04 引用/事件结构缺口，再派发消费者任务。
3. Claude 只认领一个原子任务，按自己的 worktree 规则写 ready_for_review 交接；Codex 基于实际差异审查，测试缺依赖照实记录。
4. 127 项不是工期承诺；遇外部决策、超过单轮文件/领域预算或环境安装，要拆子项而不是跨范围补实现。

回滚：本轮仅文档与应用 heartbeat。可在审查 diff 后定向恢复本轮协调文档；要停止后台跟进先暂停对应 heartbeat。不要 reset 其他 worktree 或删除他人文件。
