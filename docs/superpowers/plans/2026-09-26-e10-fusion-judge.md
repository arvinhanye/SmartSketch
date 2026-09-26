# E10 Fusion Judge Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** 对一对有来源的同课知识点产出可解释的重复裁决及有引用的统一定义提案，失败时保留原项供教师审核。

**Architecture:** `fusion/judge.py` 是纯服务边界，注入 E02/E04 `ModelClient` 与 E01 `PromptLibrary`；不查库、不合流候选、不写图。裁决与定义归并分两次模型调用，E12 负责 V 过滤、缓存和持久化。

**Tech Stack:** Python 3.13、pytest、现有 `app.services.ai.client` / `prompts` / `policy`，无新运行时依赖。

**Spec:** `docs/superpowers/specs/2026-09-26-e10-fusion-judge-design.md`

## Global Constraints

- 固定提示词用途和版本：`judge_duplicate@2`、`summarize_definition@2`；正文、变量及 sha256 与 `prompts/MANIFEST.md` 同提交更新。
- 不设 `auto_merge`、`review` 默认阈值；不改 E08/E09 分层、不生成实体 ID、不新增 API DTO、仓储或迁移。
- 仅接受同一非空 `course_id`、不同且升序的节点 ID；每侧至少一条可定位证据。原文不进入日志、异常字符串或 `repr`。
- `same=false`、坏输出、预算拒绝：原项与原定义保持独立，带可机读原因进入审核；`ModelUnavailableError` 和 `CallRecordError` 原样上抛 E12。
- E10 仅返回提案；自动合并层级、教师加锁、V 过滤、缓存存储和写图由 E12/F13 负责。
- 执行测试使用仓库 `.venv/bin/python`；`verify.sh` 用 `PATH="$PWD/.venv/bin:$PATH"`，默认 `/usr/local/bin/python3` 缺少契约工具链。

## Review Focus

1. 证据 `course_id` 与实体不一致时，边界校验拒绝而非拼进提示词（Task 1 测试）。
2. 左右证据复用同一 `source_id` 时拒绝，避免出处归属混淆（Task 1 测试）。
3. 模型将 `same` 输出为 `1` 而非 JSON 布尔时视为坏输出（Task 2 测试）。
4. 归并定义只引单侧来源时降为独立待审核（Task 3 测试）。
5. 第二次模型调用被预算拒绝时不保留第一次的半成品合并（Task 3 测试）。

---

## File map

| 文件 | 单一职责 |
| --- | --- |
| `src/backend/app/services/fusion/judge.py` | E10 输入/结果类型、边界校验、两阶段调用及失败归类 |
| `prompts/judge_duplicate.yaml`、`prompts/summarize_definition.yaml` | 版本 2 的两种 JSON 输出约束和证据要求 |
| `prompts/MANIFEST.md` | 版本、变量、正文摘要登记 |
| `tests/backend/test_e10.py` | E10 黑盒行为、失败路径、输入不变及提示词资产测试 |
| `specs/course-knowledge-graph.md`、`specs/task-processing.md`、`docs/decisions.md` | E10 边界、缓存失效收紧与已确认决定 |
| `docs/tasks.md`、`docs/handoffs/codex-e10.md` | 任务状态、验收证据与异步交接 |

### Task 1: 锁定 E10 领域边界与输入类型

**Files:** Modify `specs/course-knowledge-graph.md`, `specs/task-processing.md`, `docs/decisions.md`; create `tests/backend/test_e10.py`, `src/backend/app/services/fusion/judge.py`.

**Interfaces:** `FusionEvidence(source_id: str, course_id: str, document_id: str, revision_id: str, chunk_id: str, quote: str)`；`FusionEntity(entity_id: str, course_id: str, name: str, type: str, definition: str, evidence: tuple[FusionEvidence, ...])`；`FusionJudge(client: ModelClient, *, model: str, max_output_tokens: int, prompts: PromptLibrary | None = None)`；`validate_pair(left: FusionEntity, right: FusionEntity) -> None`。`quote`、`definition` 使用 `field(repr=False)`。

- [x] **Step 1: 先更新规格和 ADR。** 在课程图谱规格明确 E10 只给提案、失败送审、D-08 仍待签收；在任务规格 §8.4 把缓存键加上两侧完整规范化模型输入摘要，并说明 E12 持有缓存；在 `docs/decisions.md` 追加 ADR-020（背景/决定/后果/日期），记录用户已确认的三项边界。运行 `git diff --check`，预期 exit 0。
- [x] **Step 2: 写边界红例。** `test_validate_pair_rejects_cross_course_evidence`、`test_validate_pair_rejects_reused_source_id`、`test_validate_pair_rejects_missing_evidence_and_equal_ids`、`test_validate_pair_rejects_blank_definition_type_or_quote`、`test_sensitive_fields_not_in_repr`；分别断言前四类输入抛 `ValueError`、`quote/definition not in repr`。
- [x] **Step 3: 运行红例。** `.venv/bin/python -m pytest tests/backend/test_e10.py -q`；预期模块或接口尚不存在导致失败。
- [x] **Step 4: 实现类型与校验。** `validate_pair` 拒绝空白 ID/名称/定义/证据原文/定位字段、非法知识点类型（复用 E05 `ENTITY_TYPES`）、非升序或相等 ID、跨课证据、空证据、全对重复 `source_id`；不调用模型、不改变输入。
- [x] **Step 5: 复跑并提交。** 同一 pytest 命令预期新增边界用例通过；`git add specs/course-knowledge-graph.md specs/task-processing.md docs/decisions.md tests/backend/test_e10.py src/backend/app/services/fusion/judge.py && git commit -m "feat: define E10 fusion evidence boundary"`。

### Task 2: 重复裁决阶段与提示词版本

**Files:** Modify `src/backend/app/services/fusion/judge.py`, `tests/backend/test_e10.py`, `prompts/judge_duplicate.yaml`, `prompts/MANIFEST.md`.

**Interfaces:** `FusionJudge.judge_duplicate(left: FusionEntity, right: FusionEntity) -> DuplicateJudgment`；`DuplicateJudgment(same: bool | None, reason: str | None, source_ids: tuple[str, ...], review_reason: FusionReviewReason | None, provenance: PromptUse, model_calls: int)`；`PromptUse(purpose: str, version: int, sha256: str, model_id: str | None)`；`FusionReviewReason` 含 `NOT_SAME`、`INVALID_JUDGMENT`、`INVALID_DEFINITION`、`BUDGET_EXCEEDED`。

- [x] **Step 1: 写裁决红例。** `test_judge_same_has_reason_and_known_sources`（`same is True`、理由非空、来源 ID 有效、一次调用）；`test_judge_false_skips_summary`（`same is False`、`NOT_SAME`）；`test_judge_rejects_integer_same_and_repairs_once`（先 `same:1` 后有效 JSON，调用数 2）；`test_judge_bad_json_twice_goes_review`（`INVALID_JUDGMENT`）；`test_judge_truncated_then_bad_goes_review`；`test_judge_blank_or_overlong_reason_reviews`；`test_judge_budget_exceeded_goes_review`；`test_judge_unavailable_propagates`。用现有 `FakeModelClient.script()` / `FakeReply`，不发网络。
- [x] **Step 2: 运行红例。** `.venv/bin/python -m pytest tests/backend/test_e10.py -q`；预期新增裁决用例失败。
- [x] **Step 3: 实现裁决。** `judge_duplicate@2` 的变量为 `name_a`、`definition_a`、`sources_a`、`name_b`、`definition_b`、`sources_b`，其中 sources 用稳定 JSON 序列化；只接受 JSON 对象 `same` 为严格 `bool`、去首尾空白后 1～500 字的 `reason`、至少一个且均属于输入的 `source_ids`。坏输出或 `finish_reason="length"` 用相同模型/消息、`purpose="repair"` 再请求一次；预算拒绝转审核，阶段级不可用/存储异常上抛。版本与正文摘要同步写 `prompts/MANIFEST.md`。
- [x] **Step 4: 复跑并提交。** `.venv/bin/python -m pytest tests/backend/test_e10.py tests/backend/test_e01.py -q` 预期 PASS；`git add src/backend/app/services/fusion/judge.py tests/backend/test_e10.py prompts/judge_duplicate.yaml prompts/MANIFEST.md && git commit -m "feat: judge duplicate candidates with evidence"`。

### Task 3: 定义归并与原子化决策

**Files:** Modify `src/backend/app/services/fusion/judge.py`, `tests/backend/test_e10.py`, `prompts/summarize_definition.yaml`, `prompts/MANIFEST.md`.

**Interfaces:** `FusionJudge.evaluate_pair(left: FusionEntity, right: FusionEntity) -> FusionDecision`；`FusionDecision(left_id: str, right_id: str, same: bool | None, reason: str | None, status: FusionStatus, review_reason: FusionReviewReason | None, definition: str | None, source_ids: tuple[str, ...], original_sources: tuple[FusionEvidence, ...], prompt_uses: tuple[PromptUse, ...], model_calls: int)`；`FusionStatus` 为 `PROPOSAL` 或 `REVIEW`。`PROPOSAL` 必有定义与两侧来源，`REVIEW` 必无统一定义。

- [x] **Step 1: 写归并红例。** `test_evaluate_same_proposes_definition_with_both_sources`（两次调用、`PROPOSAL`、定义/两侧来源齐）；`test_evaluate_false_makes_one_call_and_reviews`；`test_summary_one_sided_sources_reviews_without_definition`；`test_summary_unknown_source_then_bad_repair_reviews`；`test_summary_budget_exceeded_keeps_originals`；`test_summary_unavailable_propagates`；`test_inputs_unchanged_after_success_and_failure`。
- [x] **Step 2: 运行红例。** `.venv/bin/python -m pytest tests/backend/test_e10.py -q`；预期新增归并用例失败。
- [x] **Step 3: 实现归并。** `summarize_definition@2` 变量为 `name`、`definitions`、`sources`；只接受 JSON 对象的非空 `definition` 与非空 `source_ids`，来源均在输入中且左右各至少一个；定义不超过 E05 `DEFINITION_MAX_CHARS`。坏输出同模型最多修复一次。`evaluate_pair` 仅在裁决 `same=True` 且定义合规时返回 `PROPOSAL`，否则 `REVIEW` 且 `definition=None`；保留两侧原来源和每阶段版本/模型元数据。更新 MANIFEST 摘要。
- [x] **Step 4: 复跑并提交。** `.venv/bin/python -m pytest tests/backend/test_e10.py tests/backend/test_e01.py -q` 预期 PASS；`git add src/backend/app/services/fusion/judge.py tests/backend/test_e10.py prompts/summarize_definition.yaml prompts/MANIFEST.md && git commit -m "feat: propose grounded fusion definitions"`。

### Task 4: 回归、验收与交接

**Files:** Modify `docs/tasks.md`; create `docs/handoffs/codex-e10.md`; adjust only E10-owned files if verification reveals defects.

**Interfaces:** E12 consumes `FusionJudge.evaluate_pair(...) -> FusionDecision` and must enforce V 过滤、缓存、教师锁与写入；本任务不增加该接口的持久化实现。

- [x] **Step 1: 验证最小与邻接回归。** `.venv/bin/python -m pytest tests/backend/test_e10.py tests/backend/test_e01.py tests/backend/test_e04.py tests/backend/test_e05.py tests/backend/test_e08.py tests/backend/test_e09.py -q`；预期全绿。若失败，按 `superpowers:systematic-debugging` 定位，只修 E10 自有问题后复跑。
- [x] **Step 2: 跑项目门禁和差异检查。** `PATH="$PWD/.venv/bin:$PATH" ./scripts/verify.sh && git diff --check`；预期 `PASS contracts gate`、`Scaffold verification passed.`、exit 0。
- [x] **Step 3: 记录交接与证据。** `docs/tasks.md` E10 行改 `DONE（待 PR 审查/合并）` 并写实测数字；`docs/handoffs/codex-e10.md` 列文件、命令/结果、接口、D-08/E12 待决、回滚步骤，不写真实课程材料。
- [x] **Step 4: 最终复验并提交。** 重跑 E10 测试、门禁、`git diff --check`；`git add docs/tasks.md docs/handoffs/codex-e10.md && git commit -m "docs: hand off E10 fusion judge"`。是否推送/开 PR 由执行阶段按用户指示决定；未合并前不宣称主线已具备 E10。
