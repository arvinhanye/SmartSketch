# E10 交接：重复裁决与定义归并

- 负责人：Codex；分支 `codex/e10-fusion-design`；基线 `main@5072a48`。
- 状态：实现待 PR 审查/合并。E10 只输出单对候选的裁决与统一定义提案，不查库、不合流 E08/E09 候选、不修改草稿。

## 交付与关键决定

- `src/backend/app/services/fusion/judge.py`：同课/来源边界校验，`FusionJudge.judge_duplicate` 与 `evaluate_pair`，最多一次同模型修复；结构化 `PROPOSAL`/`REVIEW`、理由、来源 ID、提示词版本/摘要/模型元数据及调用次数。原名称/定义/证据不进入对象 `repr`。
- `prompts/judge_duplicate.yaml`、`prompts/summarize_definition.yaml` 升到 v2，`prompts/MANIFEST.md` 同步摘要；来源为可追溯 ID，统一定义引用左右两侧证据。来源 ID 的确定性校验不等于语义真实性证明；提案仍供教师审核。
- `tests/backend/test_e10.py`：同义/非同义、坏 JSON、截断、结构错误、修复、预算、阶段级不可用、跨课与重复来源、半成品防护及输入不变。ADR-020 与两份规格记录边界及缓存失效规则。
- 审查修正：E12 的缓存身份必须覆盖**两侧完整规范化模型输入**（名称、类型、原定义、来源 ID/定位/原文），而非仅证据原文；定义提示词用 `side` 区分左右，不把 `left`/`right` 伪装成可引用的 `source_id`。

## 验证

| 命令 | 实际结果 |
| --- | --- |
| `.venv/bin/python -m pytest tests/backend/test_e10.py tests/backend/test_e01.py tests/backend/test_e04.py tests/backend/test_e05.py tests/backend/test_e08.py tests/backend/test_e09.py -q` | 468 passed |
| `.venv/bin/python -m pytest tests/backend -q`（允许本机回环测试） | 2681 passed，1 个既有 Starlette 警告；首次受限沙箱运行有 8 项 `PermissionError`，获准复跑后全绿 |
| `PATH="$PWD/.venv/bin:$PATH" ./scripts/verify.sh` | `PASS contracts gate`，`Scaffold verification passed.`，exit 0 |
| `git diff --check` | exit 0 |

## 接口、风险与下一步

- 无 REST/SSE DTO、数据库迁移、环境变量或新依赖。E12 传入一对具有稳定实体 ID、同课与可定位证据的 `FusionEntity`，消费 `FusionDecision`；`REVIEW` 时不使用统一定义。`ModelUnavailableError`/存储级故障上抛，由任务阶段协议处理。
- D-08 自动合并/审核阈值尚未签收；E10 不设默认值。E08/E09 候选合流、E05 候选稳定 ID、V 过滤、缓存持久化与教师加锁保护属于 E12/F13。下一位 Agent 首先确认这些边界，再接 `evaluate_pair`，不得把 E10 提案直接当作已获教师确认的事实。
- 回滚：撤销 E10 实现、提示词 v2 与 MANIFEST、ADR-020 和规格修订；无数据迁移。若 E12 已依赖新接口，需同步撤销 E12 调用。
