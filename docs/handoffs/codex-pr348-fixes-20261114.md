# PR #348 后端复审修复

- 日期：2026-11-14；负责人 Codex；状态：实现完成，完整门禁与独立复审进行中。
- 基线：PR #348 `04286ec9aae4db818e67109a2d82ad73b8f6c620`，协调者在 `codex/pr348-fixes-20261114` 整合当前 main。仅处理已确认 R348-1/2；不纳入撤下的租约观察。
- 输入：[复审记录](../reviews/codex-pr-review-20261114.md)、[修复计划 Task 1](../superpowers/plans/2026-11-14-pr-review-fixes.md)；输出：两项后端修复、永久回归及规格补充。

## 修改与决定

- `src/backend/app/services/fusion/undo.py`：逆向补丁对实际恢复或改变的节点使用 `max(恢复内容的历史修订号, 当前节点修订号) + 1`。被吸收节点重新出现也获得新令牌；其他节点及其修订号保留当前值。冲突检查仍比较完整事实，包括 revision，教师修改后改回也不能绕过。
- 独立组不需要忽略 revision 或从审计中放宽预期：原算法只替换 expected→desired 的 changed IDs，已撤销独立组在这两个快照中完全相同，不会再次改写。保留原 `inverse_patch` 调用协议和审计结构。
- `src/backend/app/repositories/materials.py`：在现有任务阶段、贡献、cleanup guard 之后，若本资料存在 committed、applied 或带撤销审计的计划，返回既有 `MaterialNotDeletable(..., "contributed")`；否则仅在同一个事务内清理本课程、本资料 failed/cancelled 任务的未应用 prepared/skipped 计划。其他课程/资料和已生效历史保留。
- `tests/backend/test_fusion_undo.py`：节点 ABA、恢复被吸收节点的较高历史修订号、独立组双顺序撤销并保留第一组后续教师修改、仅修订号改变仍冲突。
- `tests/backend/test_fusion_storage.py`：取消/失败资料删除、prepared/skipped、其他课程和资料隔离、现有阶段/清理保护、异常任务状态下 committed/applied/audit 历史保护与事务整体保留。
- `tests/integration/test_fusion_pipeline.py`：真实投影恢复新修订号，四节点两独立组任意顺序撤销。
- `specs/generation-disambiguation.md`：同步修订号和未生效计划删除边界。

## 验证证据

- 先红后绿：`.demo/pr-fixes-20261114/backend-red-verified.log` 为 **10 failed / 19 passed**，失败为旧 revision 复用和计划外键删除错误。首轮测试种子漏填 failed 任务的 error_code，已修正，原记录保留在 `backend-red.log`，不计为有效红证据。
- `PYTHONPATH=src/backend:. .venv/bin/python -m pytest -q tests/backend/test_fusion_undo.py tests/backend/test_fusion_storage.py tests/backend/test_adr021.py tests/backend/test_disambiguation_api.py tests/backend/test_disambiguation_review.py`：**106 passed**，50.27s，既有 Starlette 弃用警告；日志 `backend-targeted-green.log`。
- `scripts/verify/backend.sh full`：运行中；日志 `.demo/pr-fixes-20261114/backend-full.log`，结束码另存 `backend-full.exit`。
- 本轮受控文件 `git diff --check` 通过。basic、测试索引、前端、隔离 Neo4j 与最终独立复审由协调者统一运行并记录。

## 接口、风险与交接

- 无新增 HTTP/API、配置、依赖或数据库迁移；不改已有迁移 021。不可变计划和撤销审计结构不变。
- 正常撤销后的节点 revision 增大；旧编辑请求会按已有契约返回修订冲突。有关联后续变更仍保守拒绝；未放宽跨计划依赖冲突。
- 自动合并仍默认关闭；未调用真实模型或操作开发数据库。本轮不能证明真实语义质量、生成速度或审核减负。
- 下一步：协调者等待后端 full、真实 Neo4j 和独立复审，更新总任务记录后提交、推送、CI、按固定 head 合并。执行子任务未运行 git add/commit/switch/push。
- 回退：本轮无破坏性迁移；若回退代码，须同时回退这两处修复及其测试/规格，已写入较高 revision 的节点仍兼容旧整数契约。不可删除已提交审计或手动降低 revision。
