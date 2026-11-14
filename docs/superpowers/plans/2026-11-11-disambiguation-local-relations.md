# BE-05 局部规范化与关系依赖清算实施计划

> 承接用户已批准完整消歧方案，Codex 本会话顺序实施并进行一次独立终审。后续增量本地留存，BE-04 已提交并开 PR #350。

**Goal:** 小节关系生成前采用可拆分的语义卡，全局冲突只重抽受影响小节，减少重复而保留原始端点及安全回退。
**Spec:** `specs/generation-disambiguation.md` §9、ADR-102、完整方案 §4.5。
**Architecture:** 新规范化关系提示词、局部 complete-link 映射；追加关系版本仓储；融合阶段单调拆分清算；精确版本选择及持久化兜底。保持原始实体检查点和旧任务语义。
**Scope:** 后端/提示词/测试/文档；不编辑 `src/frontend`、`src/contracts` 或 Claude 工作树。默认开关不变，不用真实模型。

### Task 1: 局部语义卡和严格关系抽取

**Files:** services/fusion/local.py、services/ai/relations.py、prompts/extract_normalized_relations.yaml、MANIFEST、tests/backend/test_local_normalization.py、test_normalized_relations.py、test_e01.py。
1. RED：双判完整组与不完整同义链、确定性；卡内完整成员/原始端点反证；重复引文/坏端点不得静默丢弃；唯一证据及明确偏移。
2. 实现 `local_normalization(entities, analysis)` 返回 version/mapping/groups/digest，复用 complete-link 安全准则。`RelationExtractor.normalized()` 返回新模式副本，保留模型/输出预算；新模式严格校验及一次修复，旧模式兼容。
3. GREEN：`.venv/bin/python -m pytest tests/backend/test_local_normalization.py tests/backend/test_normalized_relations.py tests/backend/test_e01.py tests/backend/test_e11.py -q`。
Expected: 旧新提示词、来源与实体规则全部通过，坏输出整单元失败。

### Task 2: 生成流程绑定局部版本和关系依赖

**Files:** workers/extraction/{types,units,dispatch,candidates}.py、runner/toolkits、tests/backend/test_local_normalization_worker.py。
1. RED：局部双判先于规范化关系输入；检查点含原始成员/映射/完整输入摘要；v1/旧 v2 接管不升级；开关变化按固定版本继续。
2. 在首个实体检查点固定 normalization_version；先完整输入预检，再分析/局部卡，再严格关系窗口；原始实体不变。
3. 默认 `load_candidates` 排除规范化依赖关系，显式 provisional 读取只供融合校验；版本选择参数留给 Task 3。
4. GREEN：`.venv/bin/python -m pytest tests/backend/test_local_normalization_worker.py tests/backend/test_extraction_window_worker.py tests/backend/test_e12.py tests/backend/test_extraction_perf_scheduler.py -q`。
Expected: 生成/接管和窗口保护兼容，默认不泄漏暂定关系。

### Task 3: 不可变关系重抽与融合/持久化清算

**Files:** migration023、repositories/relation_revisions.py、workers/relation_reconciliation.py、fusion_task.py、persist_graph.py、candidates.py；backend/integration 对应新测试。
1. RED：关系版本课程隔离/不可变/缓存、原始端点重抽、精确版本选择；失败/上限不复用旧边；拆分传播与禁止重新合并。
2. 添加 leased merging 追加版本，key 含完整来源/实体/模型/提示词/预算/映射；复用 L2/窗口与取消/租约/任务级异常。
3. 全局先读取暂定边；映射否决后清算受影响小节，重建原始图并复用语义结论校验；失败禁止自动合并；计划保存原分析身份和精确版本选择/覆盖。
4. 关闭自动合并但存在固化规范化检查点仍清算；过期草稿只用独立版本，不能把暂定关系写进兜底原始图；回滚检查活动任务。
5. GREEN：`.venv/bin/python -m pytest tests/backend/test_relation_revisions.py tests/backend/test_relation_reconciliation.py tests/backend/test_relation_reextract_worker.py tests/backend/test_fusion_generation.py tests/backend/test_fusion_storage.py -q` 及隔离 Neo4j 新集成。
Expected: 原有和新候选选择一致、零跨版本残留，失败/租约变化不误报成功。

### Task 4: 验收、终审和交接

**Files:** tests/INDEX.md、docs/tasks.md、docs/handoffs/codex-disambiguation-local-relations.md、specs/task-processing.md。
1. 执行新功能定向与 Neo4j 集成；归档实际结果。
2. 一次独立全批终审，Important/Critical 每项 RED→GREEN 修复；minor 明确登记。
3. `PATH="$PWD/.venv/bin:$PATH" ./scripts/verify.sh` 和后端 full 门禁；不为未改代码重复完整测试。
4. `git diff --check`、核对文件范围；报告 PR #350 和 BE-05 本地成果、实际验证及真实模型验收边界，清理仅本批临时容器。
Expected: basic/full/专项 exit 0，文档与结果一致，Claude 改动未触碰。

## Review Focus

- 多个局部组通过重抽产生交叉先修边：每个小节至多一次、受影响闭包覆盖、禁止重并（Task 3）。
- 模型出错/熔断/凭据撤销/取消在重抽调用与存储之间，不能落错误完成版本或回退旧边（Task 3）。
- 新 owner 在关闭开关后接管固化任务，以及旧任务无元数据的兼容（Tasks 2–3）。
- 计划生成后教师编辑导致草稿头变化：落库不能沿用有失效依赖的关系（Task 3）。
- 来源重复、跨窗口重叠与卡内反证：严格定位、原始成员保存、撤销快照来源一致（Tasks 1–3）。
