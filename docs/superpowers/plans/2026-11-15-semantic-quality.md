# 课程图谱语义与关系覆盖修复实施计划

> **For agentic workers:** Use superpowers:executing-plans inline; existing user approval covers execution.

**Goal:** 修复已复现的漏合并、定义退化和明确关系遗漏，减少有来源支持的孤立节点。
**Architecture:** 保留两阶段抽取、同义双判与图安全围栏；优先召回、有限补证、确定性定义投影和显式关系补漏分别实现为小模块。
**Tech Stack:** Python / FastAPI / SQLite / Neo4j；无新依赖/迁移/公开API。
**Spec:** specs/generation-disambiguation.md §13。

## Global Constraints
- 保留教师编辑、旧草稿和现有未提交修复；不调用真实模型。
- 同名仅召回；四类关系、有向先修DAG、证据逐字定位保持。
- 最多3次语义+1次格式修复；同输入完整结果缓存和并行8保持。

## Review Focus
- 大同名组超硬预算必须报告截断；不能静默越预算。
- 补证伪引用、真实限定冲突、初判不确定后未复核不能自动合并。
- 公式/条件长度超500不截断原定义；人工节点不改写。
- 否定句/同名多义/不在材料中的端点不能由显式规则连边。
- 规则和提示词改版不能复用不兼容语义计划；旧完成任务不改写。

### Task 1: 优先召回与定义保留
**Files:** fusion/recall.py, fusion/mapping.py, 新fusion/definitions.py；test_disambiguation_recall.py、test_disambiguation_mapping.py。
**Interfaces:** recall_candidates原签名；project_snapshot原签名；merged_definition(nodes, canonical) -> str。
- [x] RED：单名匹配不能被两个弱通道挤出；多成员名字组越top-k仍有候选；预算截断。
- [x] RED：代表ID不变但实质定义保留；互补定义保留条件、500字符及人工保护。
- [x] 实现并运行两个测试文件，PASS。

### Task 2: 有限语境补证
**Files:** fusion/resolution.py、prompts/resolve_duplicate.yaml及MANIFEST；test_disambiguation_resolution.py。
**Interfaces:** SemanticResolver.resolve原签名，SemanticDecision原协议；补证原始JSON包含grounding及resolved_differences，验证后不扩公开DTO。
- [x] RED：冲突后有据SAME恢复、无据仍未决、初判UNCERTAIN后SAME要盲复核；调用有界与技术失败。
- [x] 实现最多一次补证，版本升级；缓存回归PASS。

### Task 3: 实体与关系补漏
**Files:** prompts/extract_entities*.yaml、extract_normalized_relations.yaml、调用版本；新services/ai/explicit_relations.py，relations.py；tests/backend/test_explicit_relations.py。
**Interfaces:** explicit_relations(entities, chunks) -> list[dict]；只为精确唯一名称和无否定的显式句给出原始端点及定位，作为单次模型请求中的候选，须经模型确认后走现有验证；不直接自动写边。
- [x] RED：一般中文先修、包含、例子句补漏；否定/多义/端点不存在/长证据不产边；模型已有同边不重复。
- [x] 实现并更新提示词版本/清单；关系及抽取测试PASS。

### Task 4: 验证与部署
- [x] 已运行定向回归、./scripts/verify.sh、后端full、隔离Neo4j相关检查。最后full受磁盘耗尽影响失败；用户接受本轮结果并明确要求不再重测，详见交接，不声称全量通过。
- [x] 独立最终审查；保留失败记录并修复确认问题。
- [ ] 构建更新本机后端，保留当前web；无活动任务时重启，核对业务数据/模型调用不变与健康。
- [ ] 更新任务与交接，说明旧图未重跑、真实效果由用户新任务验收。
