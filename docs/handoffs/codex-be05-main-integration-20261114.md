# BE-05 主线整合与发布

- 状态 VERIFIED（整合实现、独立复审与本地工程验收完成）；负责人 Codex。用户已授权提交、推送、创建 PR，最终远端 CI 全部通过后合并；发布状态以本分支对应 PR 为准。
- 主线基线 `b6a93020cd8165e8a7a010cd1b9d56013467ca8a`；来源工作树 `/Users/arvinhan/Desktop/SmartSketch-main`，基线 `27339d9`。只取已确认的 BE-05：25 个修改文件、15 个新增文件。原工作树及其他工作树保持原样。
- 计划与规格：[原实施计划](../superpowers/plans/2026-11-11-disambiguation-local-relations.md)、`specs/generation-disambiguation.md` §9、ADR-102。

## 整合与保护

源状态与上一轮清理审计完全一致；40 个文件已保存完整 tar 副本、二进制差异和 SHA256 清单，位于本工作树 `.demo/be05-publish-20261114/`。三方应用只有 `docs/tasks.md` 和 `tests/INDEX.md` 冲突；保留主线任务记录和融合撤销测试描述，并加入 BE-05 任务与测试索引。没有覆盖主线产品修复。

## 验证与复审

本次基于最新 main 的验证：

- 定向回归 192 passed，exit 0；包含 BE-05 新模块、主线融合撤销/资料删除修复、迁移及测试索引。
- `PATH="$PWD/.venv/bin:$PATH" ./scripts/verify.sh` exit 0。
- 独立复审覆盖 41/41 文件（17 生产/提示词 + 24 测试/文档），跳过 0，无确认问题，`declined_to_judge=[]`；独立边界实验 4 passed，覆盖资料删除级联、凭据撤销、缺失来源与跨窗口偏移。复审文件哈希已由协调者核对一致。
- `PYTHONPATH="$PWD/src/backend:$PWD" PYTEST_ADDOPTS=-x PATH="$PWD/.venv/bin:$PATH" scripts/verify/backend.sh full`：4566 passed / 27 登记 skip / 1 既有 Starlette 弃用警告，1104.24s，PASS backend gate，exit 0。
- `env -u VERIFY_NEO4J_URI -u VERIFY_NEO4J_USER -u VERIFY_NEO4J_PASSWORD PYTHONPATH="$PWD/src/backend:$PWD" PATH="$PWD/.venv/bin:$PATH" scripts/verify/integration.sh --no-e2e`：Neo4j 516 passed / 4 登记 skip，864.36s；backend-live 44 passed，33.44s；门禁和整条命令均 exit 0。临时容器已清理。
- 前端与契约没有代码差异；本地未重复前端全量或浏览器 E2E，最终 PR CI 会执行两者及仓库全部检查。未将旧工作树结果冒充此次整合结果。
- 41 文件复审覆盖完整；生产代码、提示词、测试与规格的复审哈希未变化。复审后只补充文档中的实际验收证据与复现命令。桌面原工作树 40 项状态/内容哈希保持原样。

首轮定向入口未显式指定当前源码，因共享虚拟环境的 editable install 指向桌面旧工作树，10 条主线新增回归失败。根据异常路径及模块 `__file__` 确认导入来源后，仅修正测试入口为 `PYTHONPATH="$PWD/src/backend:$PWD"`，192 条全部通过；产品代码未因此改变，失败日志保留为 `targeted-wrong-import.log`。后端/集成门禁自身设置当前工作树路径，均已核实。

## 接口、数据和回退

公开 API、前端、依赖与默认开关不变。迁移 023 新增 `task_relation_revisions`，不可变关系版本按课程隔离且在 merging 租约事务内写入。仅隔离测试库执行迁移；开发数据库不动。回滚须停止服务并备份，完成或取消已固定规范化的活动任务；先退 023 再退 022，严格执行迁移内的活动任务保护，保留审计备份。

真实模型质量、误合并率、审核减负与耗时仍待独立评测；当前范围为工程整合、兼容及失败保护。

## 发布与证据

分支 `codex/disambiguation-be05-integration`；保留上述来源快照，不重写桌面原分支、不清理其他工作树。发布前核对最新 main 仍为 `b6a9302`，限定范围与差异检查通过；提交后将以实际 head 运行远端 CI，并使用 expected-head SHA 合并。最终 PR 是发布状态的权威记录，不用历史验收替代新提交检查。

详细日志、独立逐文件审查、恢复副本与源状态哈希在 `.demo/be05-publish-20261114/`，其中临时审查实验首轮仅有失败任务夹具缺少 error_code，修正独立夹具后 4 passed；没有修改正式测试或产品代码。
