# 有界抽取窗口与覆盖保护实施计划

> Use superpowers:executing-plans，在当前会话连续执行；测试先失败后实现，一次独立终审。基于已推送的 `04286ec`，本批先保留本地可审查增量，不修改 PR #348 的 head。

**Goal:** 限制实体/关系抽取完整请求，保留原始来源，防止不完整抽取进入自动合并。
**Architecture:** 纯窗口规划与请求预算负责分割；worker 负责现有重试、检查点与来源复原；全局融合消费完整性摘要。共享池和原有任务状态机保持不变。
**Tech Stack:** Python 3.11+、既有 ModelClient、SQLite/Neo4j；无新依赖；迁移 022 增加检查点元数据列（集成发现既有失败 result 必须 NULL）。
**Spec:** `specs/generation-disambiguation.md` §8、ADR-101。

## Global Constraints
- 不改前端/公开契约/默认开关，不迁移开发数据，不调用真实模型。
- 完整输入预算为 UTF-8 bytes + 256 + 4×max_output_tokens；默认 24000，每单元最多 64 窗口，默认重叠 512 字符。均为工程参数，不能当作模型有效窗口结论。
- 短输入保留一次请求；不得切掉实体定义、把失败当 UNCERTAIN、静默放弃尾部或跨实体批次组合。
- 原始块 ID/出处/字符偏移保持；只去掉相同出现与内容；每次物理请求仍受取消、租约、凭据和原有预算保护。
- 旧任务固定原有检查点策略；新窗口失败仍按原成功/失败单元处理，不把半份结果写成 done。

## Review Focus
- 多字节文本、重复证据和重叠窗口是否被还原到错误的原始位置。
- 单个完整实体对/包装输出本身超预算是否仍调用模型，repair/gleaning 是否绕过限制。
- 大实体表是否遗漏跨批次对、长来源是否默默丢尾部；上限是否防止二次规模内存/调用。
- 接管后不同设置/旧检查点是否混用策略，取消发生在第二窗口时是否仍有后续模型调用。
- 窗口或关系失败后，剩余候选是否被错误当成完整图而自动合并。

## Task 1: 预算与窗口规划
**Files:** `services/ai/request_budget.py`、`services/ai/extraction_windows.py`、实体/关系/补漏抽取器输入大小方法、`tests/backend/test_extraction_windows.py`。
**Interfaces:** `WindowPolicy`；`entity_windows(extractor, chunk, policy)`、`relation_windows(extractor, entities, chunks, policy)` 返回保留原始范围的窗口；超限抛含原因码的 `WindowBudgetError`。
- [x] RED：Unicode 完整覆盖/重叠、证据位于开头中间结尾、实体跨批组合、单卡/总窗口超限无调用、短输入一窗。
- [x] GREEN：确定性预规划，二分最大字符窗口，完整表优先；放不下时按实体对，超过窗口上限立即停止规划。
- [x] 验证：`.venv/bin/python -m pytest tests/backend/test_extraction_windows.py -q`，Expected PASS。

## Task 2: worker 原子检查点与来源恢复
**Files:** `workers/extraction/windowed.py`、`units.py`、`types.py`、`dispatch.py`、工厂、配置、检查点仓储与迁移 022 及 `tests/backend/test_extraction_window_worker.py`。
**Interfaces:** 窗口逐次消费现有 ModelClient；检查点 metadata 的 `window_policy` / `window_coverage` 附策略和输入摘要，旧字段保持兼容。
- [x] RED：真实抽取器输出还原到原始偏移/页码、重叠不重复、同名不同处保留、部分失败不写半份、完整消息含输出预留、取消/修复/补漏守卫、旧/新任务接管。
- [x] GREEN：复用现有 L2，不新增重试层；成功和失败都保存覆盖，工厂仅消歧新任务启用，固定检查点策略。
- [x] 验证：新 worker 测试及 E05/E06/E11/E12/调度/个人模型相关回归，Expected PASS。

## Task 3: 融合完整性、集成与交接
**Files:** `workers/fusion_task.py`、相关后端/真实 Neo4j 集成测试、规格/任务/交接。
**Interfaces:** 抽取检查点摘要进入全局 plan digest；失败单元或 partial 窗口 → 无合并组、partial/extraction_incomplete，不发语义合并判断。
- [x] RED→GREEN：缺失关系/失败窗口禁止合并，检查点覆盖摘要变化后旧计划失效，正常窗口仍可生成到审核；真实 Neo4j 验证可见图保持独立。
- [x] 一次独立终审；相关回归、basic 和后端 full，Expected PASS。无 real-model 质量/速度结论。
- [x] 更新任务与交接、记录所有裁定/限制、最终差异核对；本批不向既有 PR 自动追加。
