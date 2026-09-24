# Codex 交接：A10 批 0 规划文档对齐

- 状态：DONE（本地分支，待独立审查与主线集成）；执行分支 `codex/a10-batch0`。
- 基线：A10 已签收提交 `37da669`；在隔离工作树中合入 `origin/main@f9dfc8f`，保留当前主线 A08 规格。
- 来源：A10 [导入映射](../reviews/branch-integration-map.md) 第 3 节批 0 与第 6 节 G-1～G-6；ADR-016 决定 2、4、7。

## 交付与决定

- `docs/atomic-task-plan.md`、`docs/atomic-tasks.json`：将 B08～B14、O02、O05 的白名单从手写 `v1/python/*.py` 映射为 `api.v1.yaml` 与生成物；B08/B10/B13 同步允许错误/SSE 时序文档。明确“先改真源、再生成”的边界。
- 将 G-1～G-4 拆为 13 个可认领叶子任务：C13～C16、F14、H12、K13～K19；G-5 明确归批 5，G-6 归 C13。C03 依赖 C13，C11 依赖 C16，避免无身份或无票据实施。
- `docs/reviews/validate_atomic_plan.py` 改为从脚本位置找当前 checkout，动态读取任务数与主线/可选计数，校验编号唯一、依赖无环、JSON/Markdown 一致、逻辑路径安全和本地链接。
- 更新 `docs/tasks.md` 状态与范围。未修改产品接口、数据库或真实课程资料。新任务的测试命令仍为未来验收契约，不声称已经执行。

## 实际验证

| 命令/检查 | 结果 |
| --- | --- |
| `python docs/reviews/validate_atomic_plan.py` | PASS：140 项 = 132 主线 + 8 可选；ID、依赖、路径、11 个链接通过 |
| 在临时副本中把 A01 依赖改成不存在的 ID，再运行验证器 | 非 0，明确拒绝 `NO_SUCH_TASK` |
| `python -m json.tool docs/atomic-tasks.json` | exit 0 |
| `./scripts/verify.sh`（Git Bash 中为本机 Python 提供 `python3` 临时别名） | hook tests PASS；scaffold verification PASS |
| `git diff --check` | exit 0 |

## 接口、风险与下一步

- 无 REST/SSE/数据迁移。本批仅计划与校验器；业务任务均为 PROPOSED。
- A10 本身尚未进入远端 `main`。本分支在 A10 之上，后续 PR 需等 A10 集成后按 ADR-016 的每批单 PR 顺序审查。B02 与 B06 原工作树未被修改。
- 下一步：A10 批 1，按第 3 节导入契约真源与生成链并重新生成，校验命名和负例；批 1 验收后再认领 B07/B08。
- 回滚：仅撤销本批本地提交；没有数据库、远端或依赖安装需要恢复。
