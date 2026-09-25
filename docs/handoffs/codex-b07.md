# Codex 交接：B07 契约门禁缺依赖假绿

- 任务与状态：B07 实现及本地验收完成；[PR #187](https://github.com/arvinhanye/SmartSketch/pull/187) 已创建，待审查与合并。
- 基线：`origin/main@28b09b4`，隔离工作树 `b07-main`；没有合并到 main。
- 范围：`scripts/check_contracts.py`、`scripts/verify/contracts.sh`、`src/backend/pyproject.toml`、`tests/tooling/test_b07.py`，以及 `docs/architecture.md`、`docs/tasks.md`、本交接。

## 交付与决定

- 保留现有唯一契约门禁。真源校验成功标 `PASS`，失败标 `FAIL`；显式 `--allow-scaffold` 缺依赖降级标 `SKIP` 与 `INCOMPLETE`，不构成验收。仓库门禁不使用降级参数，聚合退出前明确打印 `PASS contracts gate` 或 `FAIL contracts gate`。
- `check_contracts.py` 同时检查 PyYAML、OpenAPI 校验器和 JSON Schema 校验器可用性；缺任一项的普通执行非 0。后端 `[test]` 额外依赖按 `src/contracts/toolchain.txt` 锁定三者版本。
- 独立审查发现畸形 YAML 的 `components`/`paths`/`schemas` 可触发未捕获异常而不打印 `FAIL`；已补结构类型校验与闭锁异常处理，四个畸形结构回归先红后绿。
- `tests/tooling/test_b07.py` 在真实契约副本上测试坏 `$ref`、关系枚举与缺依赖；在测试工作区验证 shell 门禁的聚合状态。未改 REST/SSE DTO、业务数据或数据库。

## 实际验证

| 命令 | 结果 |
| --- | --- |
| `PATH=/opt/anaconda3/bin:$PATH /opt/anaconda3/bin/python -m pytest -p no:cacheprovider tests/tooling/test_b07.py -q --tb=short` | 14 passed（审查补丁后） |
| `PATH=/private/tmp/smartsketch-c08-venv/bin:$HOME/.local/share/smartsketch/contracts-venv/bin:$PATH PYTHONPATH=src/backend /private/tmp/smartsketch-c08-venv/bin/python -m pytest -p no:cacheprovider tests -q --tb=short` | 218 passed，1 条上游弃用警告（审查补丁前；此临时 venv 后来被清理） |
| `PATH=/private/tmp/smartsketch-c08-venv/bin:$HOME/.local/share/smartsketch/contracts-venv/bin:$PATH PYTEST_ADDOPTS='-p no:cacheprovider' ./scripts/verify.sh` | exit 0；契约负例 24 项、B08 5、B09 5、B10 45、B13 53 均通过（审查补丁前） |
| `PATH=/opt/anaconda3/bin:$HOME/.local/share/smartsketch/contracts-venv/bin:$PATH PYTEST_ADDOPTS='-p no:cacheprovider' ./scripts/verify.sh` | exit 0；契约负例 24 项、B08 5、B09 5、B10 45、B13 53 均通过（审查补丁后） |

单独系统 `python3` 缺 PyYAML、pytest 等依赖；最初无环境 PATH 的全仓收集失败。上述命令使用当时已存在的测试环境，未向系统环境安装包。门禁运行所需生成器保持在独立 venv 的 PATH 中。最终补丁后的全仓测试未重跑：临时测试 venv 已清理，conda Python 缺 FastAPI；定向 14 项与最终契约门禁均已通过。

## 接口、风险与下一步

- 无对外接口或数据模型变更；只增加本地测试依赖声明，不改生产依赖。无迁移或外部服务状态。
- C13 并行分支也可能改 `src/backend/pyproject.toml` 的生产依赖；合并时须同时保留其生产依赖与 B07 的三个测试依赖。本分支不覆盖 C13 工作区。
- 下一位 Agent：审查 PR #187，由 ArvinHan 合并；在 PR 基线如有 C13 并入，先复核 `pyproject.toml` 的两组依赖，再重跑定向测试和 `verify.sh`。
- 回滚：仅撤销 B07 自有提交；不删契约真源、生成物或 C13 依赖，无数据恢复步骤。

## PR 审查复核（2026-09-25 UTC）

- 已在 `origin/main@588d00a` 的临时合并副本审查七个文件；无 P1/P2，C13 生产依赖与 B07 测试依赖均保留。
- 合并副本定向 B07 14 passed、全量 620 passed、`./scripts/verify.sh` exit 0、`git diff --cached --check` PASS。受限沙箱中另有两例 C13 测试因本地 socket 权限失败；允许本地 socket 的全量复跑 620 passed。
- 详细审查与命令见 `docs/reviews/codex-b07-pr187-2026-09-25.md`。合并后须将任务板状态与本交接中的“待 PR 合并”更新为已合并并补入 merge SHA。
