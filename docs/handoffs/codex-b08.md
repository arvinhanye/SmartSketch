# B08 交接：公共错误和来源契约

- task_id：B08
- 工作树：`C:/Users/asus/Desktop/SmartSketch/.worktrees/b08-contracts`，分支 `kongsc/b08-contracts`
- 基线：`codex/a10-batch1@b801553`；首次交付提交 `21253f8`
- 审查修复：B08 首次交付为 `21253f8`；本轮修复 429 响应描述和统一门禁接入，完成后以新提交为准。

## 交付物

- `src/contracts/api.v1.yaml` 的 `ErrorCode` 增加八项：`DOCUMENT_UNREADABLE`、`EXTRACTION_INCOMPLETE`、`STORAGE_UNAVAILABLE`、`INTERNAL_ERROR`、`TASK_ATTEMPTS_EXHAUSTED`、`PUBLISH_IN_PROGRESS`、`COURSE_BUSY`、`BUDGET_EXCEEDED`。`SourceRef` 与 `RelationType` 已有的约束保持不变，由 B08 测试固定。A05 §7 的 Bearer 说明、受保护操作的 401 响应和 `eventTicket` 安全方案也已补齐。
- `src/contracts/errors.v1.md` 明确异步任务失败仍通过 HTTP 200 的任务快照返回；同步存储故障为 503、内部错误为 500、预算耗尽为 429，两种发布冲突为 409。`COURSE_BUSY.details.holder` 和任务失败细节也已记录。
- 重新生成 `src/contracts/v1/generated/` 的 OpenAPI JSON、JSON Schema、Python 模型和 TypeScript 类型；同步 `docs/architecture.md`、`specs/task-processing.md`、`specs/teacher-review-publish.md`、`docs/integrations.md` 的 B08 状态。
- 新增 `tests/contracts/test_b08.py`，覆盖新增码、领域状态不进入错误码、来源定位正反例及四类关系闭集；另覆盖 Bearer 说明、受保护操作的 401 响应和 eventTicket 安全方案。
- 审查修复：共享 429 响应明确 `RATE_LIMITED` 可按 `Retry-After` 重试、`BUDGET_EXCEEDED` 不重试；新增回归用例，并由 `scripts/verify/contracts.sh` 每次执行 B08 测试。

## 验证

- 先写测试并执行：`python -m pytest tests/contracts/test_b08.py -q`，改真源前 1 failed / 2 passed（缺八项错误码）；改后 4 passed。
- `python scripts/check_contracts.py`：结构、来源、状态机及命名校验通过。
- `./scripts/gen-contracts.sh --check`：生成物与真源一致。
- `./scripts/verify.sh`：hook 回归、契约结构、生成物漂移、22 项契约门禁负例均通过，exit 0。
- `git diff --check`：exit 0。

审查修复轮：先确认新增 429 测试失败（1 failed / 4 passed），再改真源并重新生成；`python -m pytest tests/contracts/test_b08.py -q` 5 passed；`./scripts/gen-contracts.sh --check` PASS；`./scripts/verify.sh` exit 0（22 项门禁负例 + 5 项 B08 测试）。

Windows 上通过 Git Bash 执行上述 `.sh`；临时命令别名仅解决本机 `python3` 与生成器入口的路径差异，不纳入交付。

## 接口、风险与下一步

- 接口变化是 `ErrorCode` 扩充；无新增路径或 DTO 字段，无数据库迁移。前端应按 `errors.v1.md` 为未知错误码保留兜底分支。
- 本基线尚无 B05 的 FastAPI 应用工厂；本任务验收的是契约与生成物，运行时映射由后续 API 任务实现。A10 批 1 尚待集成，合并顺序需保留其为本分支前置。
- 首个后续动作：在 A10 批 1 的集成路径上安排 B09/B10/B11 对新增错误码的引用；本次修复提交后继续按集成顺序处理。
