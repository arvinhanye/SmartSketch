# REVIEW-C08 修复交接（Claude，2026-09-24）

- **任务与状态**：修复 PR #176（C08 状态迁移纯函数，Codex 实现）审查评论 REVIEW-C08 的 R01～R04。ArvinHan 2026-09-24 授权 Claude 直接在 PR 分支上修。状态：已修复并验证，待 ArvinHan 合入。
- **分支**：`codex/c08-task-state`，修复前 head `a5b8c79`；已同步 `origin/main@28b09b4`（含 PR #179、#180），合并无冲突。
- **改动文件**：`src/backend/app/services/task_state.py`、`tests/backend/test_c08.py`；协作状态 `docs/tasks.md` C08 行与本交接。未改契约、规格、Codex 交接（`codex-c08.md` 里「wire 序列化方需转换成普通 dict/list」一句已被 R01 取代，由 Codex 后续自行更新）。

## 修复内容

| 编号 | 问题 | 修复 | 回归测试 |
| --- | --- | --- | --- |
| R01 (P2) | `details` 冻结为 `MappingProxyType`，`json.dumps` / `dataclasses.asdict` 抛错，C09 写库、C11 推 `TaskErrorEvent` 会崩 | 改为只读 `dict` 子类 `_FrozenDetails`（所有写方法抛 `TypeError`，`__reduce__` 支持 pickle/deepcopy），列表仍冻结为 tuple；另拒绝 NaN/Inf 以保证严格 JSON | JSON 往返、`asdict` 后再 `json.dumps`、pickle、deepcopy；8 种写操作逐一抛错；非法 details 构造即抛 `TypeError` |
| R02 (P2) | `fail` 不校验失败码 | 新增公开常量 `FAILURE_CODE_STAGES`，按 `specs/task-processing.md` §6 闭集：`DOCUMENT_UNREADABLE`→parsing；`LLM_UNAVAILABLE`、`EXTRACTION_INCOMPLETE`→extracting；`CYCLE_DETECTED`→persisting；`STORAGE_UNAVAILABLE`、`INTERNAL_ERROR`、`TASK_ATTEMPTS_EXHAUSTED`→任意处理中阶段。表外码返回 `invalid_error`，阶段不符返回 `error_stage_mismatch`；输入 `failed` 状态携带表外码视为 `invalid_state` | 7 码 × 4 阶段全矩阵；`PUBLISH_BLOCKED`、`NOT_A_CODE` 等表外码 |
| R03 (P3) | 未知 `kind` 返回 `invalid_transition` | 入口按 §2 事件词表校验，词表外返回 `invalid_event` | `made_up`/`resume`/`CLAIM`/空串；合法事件错阶段仍为 `invalid_transition` |
| R04 (P3) | 阶段字符串与区间另写一份，可能漂移 | 新增公开 `TASK_STAGES` 与 `stage_progress_range()`；测试从生成物 `openapi.json` 读 `TaskStage` 枚举、`FixedStageProgress`/`TaskCompleted` 常量、`ErrorCode` 枚举，从 `events.v1.md`「阶段与进度映射」表读区间并逐项比对 | 4 条契约对齐测试 |

新增拒绝原因 `error_stage_mismatch`；C09/C11 映射 `Rejected.reason` 时需一并处理（与已有 `invalid_error` 同属 worker 内部错误，不对外暴露）。

## 验证（实际结果）

- 修复前先写测试：`python3 -m pytest ../../tests/backend/test_c08.py -q`（在 `src/backend`）→ 35 failed, 87 passed。
- 修复后同命令 → 122 passed。
- `PYTHONPATH=src/backend PYTHONDONTWRITEBYTECODE=1 PYTEST_ADDOPTS='-p no:cacheprovider' /private/tmp/smartsketch-c08-venv/bin/python -m pytest tests/backend -q` → 198 passed, 1 warning（既有 httpx 弃用警告）。系统 Python 无 fastapi，故用 Codex 的锁定依赖 venv。
- `./scripts/verify.sh` → exit 0（B09 45、B10 45、B13 53 等全过）。
- `python3 docs/reviews/validate_atomic_plan.py` → PASS；`git diff --check origin/main...HEAD` → 通过。

## 风险与下一步

- `details` 仍只校验 JSON 形状，未按码校验字段（如 `DOCUMENT_UNREADABLE.reason ∈ {corrupted, encrypted, no_text}`）；§6 其他码的 details 字段非闭集，留给 C09/C11 或后续规格收紧。
- `TaskError` 带 details 时不可哈希（修复前同样如此），不要把 `TaskState` 放进 set/dict 键。
- 下一步：ArvinHan 审核并合入 PR #176；合入后关闭 #65、任务板 C08 转 DONE。
- 回滚：`git revert` 本次修复提交即可，无迁移、无契约改动。
