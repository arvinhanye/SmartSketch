# 生成消歧后端第一批实施计划

> **For agentic workers:** Use superpowers:executing-plans task-by-task. 用户已授权实施，不再追加方案确认；按项目约定不自动提交或推送。

**Goal:** 交付提及身份、有界语义裁决和生成阶段持久化分析，为安全自动合并准备可测试输入。

**Architecture:** 复用不可变块/小节检查点。新模式保存提及而非同名折叠；独立 SemanticResolver 输出三态语义及技术状态；小节分析结果存入检查点，暂不调用图合并。

**Tech Stack:** Python、SQLite、既有 ModelCallPolicy；无新依赖。

**Spec:** `docs/superpowers/specs/2026-11-11-knowledge-disambiguation-design.md`；ADR-098；`specs/task-processing.md` 第一批实施边界。

## Global Constraints

- 后端、后端测试、提示词、评测和 Codex 文档归本任务；不碰前端、前端测试、Claude 工作树/交接或审核 DTO。
- 同名不是同义，引用存在不是同义证明；领域知识用于同义判断，不编造来源。
- 保持课程隔离、取消、租约、鉴权、预算、共享并发 8。
- 不使用付费模型；fake 只证明工程行为。自动合并须等最终映射、图校验、贡献版本、撤销及真实质量验收。

## Review Focus

- 接管旧任务：身份不能改变，使关系端点悬空。
- 单侧引用、超长输入和截断输出：不能返回可合并 SAME。
- 第一轮与差异复核冲突：必须保留 UNCERTAIN。
- 分析失败：不能丢失关系结果或伪装语义争议。
- 新模型调用：每次遵守凭据 guard 与调用预算，取消/失租不写检查点。

## Task 1: 有界语义裁决

**Files:** 新建 `src/backend/app/services/fusion/resolution.py`、`prompts/resolve_duplicate.yaml`、`tests/backend/test_disambiguation_resolution.py`；修改 MANIFEST。

**Interfaces:** `SemanticResolver(client, model, max_output_tokens=1024, max_input_bytes=24000).resolve(left: FusionEntity, right: FusionEntity) -> SemanticDecision`；包含 verdict/status/basis、双侧来源、理由、调用元数据。

- [x] RED：常识同义需独立复核；明确不同一次调用；复核冲突未决；坏 JSON、单侧引用、截断不能 SAME；跨课/超预算零调用；敏感内容不进 repr。
- [x] GREEN：版本化模板，最多 3 次逻辑调用（整对共享 1 次格式修复）；物理重试/备用切换另受既有策略和预算控制；完整请求预算含输出预留；不生成新定义。
- [x] 验证：`pytest tests/backend/test_disambiguation_resolution.py tests/backend/test_e10.py tests/backend/test_e01.py -q` 全部通过。

## Task 2: 提及身份及关系输入

**Files:** `src/backend/app/workers/extraction/{candidates,types,units,dispatch}.py`、`services/ai/{relations,gleaning}.py`；相关测试。

**Interfaces:** `mention_entity_id(task_id, candidate)`；新块 `entity_identity_version=2`，未标记旧块为 v1；`SectionEntity` 新增可选 definition/evidence。

- [x] RED：同名不同定义/类型/位置独立；同次出现同内容去重；任务隔离；旧检查点/旧关系可继续读取；关系模型收到限定语。
- [x] GREEN：精确重复键；保留旧 task_entity_id 兼容；gleaning 在新模式不能按名称丢掉不同义项。
- [x] 保留原有来源、幂等、隔离与旧身份行为断言；新身份模式由新增回归单独覆盖。
- [x] 验证：新身份测试及 E06/E11/E12/调度回归全部通过。

## Task 3: 生成分析检查点

**Files:** 新增 `workers/extraction/analysis.py`、`tests/backend/test_disambiguation_generation.py`；工具包、配置、worker 接线。

**Interfaces:** 工具包可选 resolver 工厂；小节检查点记录 analysis_version、input_digest、decisions、unprocessed_pairs、completion。

- [x] RED：关系前分析、结果持久化、接管不重复调用；缺工厂不调用；技术失败独立；每次请求 guard；候选预算超限如实 partial。
- [x] GREEN：复用受控客户端与共享池。`DISAMBIGUATION_ANALYSIS_ENABLED` 默认 false，开启时写 v2 身份；接管根据已存在块固定身份模式，配置切换不改变端点。
- [x] 本批只在小节内做有界全对分析，不声称实现最终混合召回；超过候选预算标记未检查。原始实体/关系不自动融合。
- [x] 验证：生成、worker、个人凭据与配置回归通过；独立审查后额外补齐物理重试前 guard 和重复引用定位保护，相关回归 101 passed。

## Task 4: 指标、验收与交接

**Files:** 离线判定指标、对应测试、测试索引、任务和 `docs/handoffs/codex-disambiguation-backend-foundation.md`。

- [x] 指标区分三态与技术失败；SAME 的错误/正确数单独报告，不用 fake 证明真实精度。
- [x] 更新索引，basic exit 0；最终后端全量 4393 passed / 27 登记跳过，gate exit 0；不把它当作跨任务图合并验收。
- [x] 一次独立最终代码审查；2 个 Important 均用失败回归复现并修复，7 red → green。2 个 Minor 延期，限制和处置见交接。
- [x] 核对前端/Claude 未动，记录启用状态、已完成项和下一批依赖；不标记完整方案完成。见 [交接](../../handoffs/codex-disambiguation-backend-foundation.md)。

## 执行记录

- 基线 `31a7e6c`，本地分支 `codex/knowledge-disambiguation`；保留前轮三份文档。Claude 工作树起点 `8420097`、干净。基线 E10/E11/E12：119 passed。
- Ruling：复用当前检出切后端分支；Claude 已在独立工作树，文件互斥。若发现共享文件变更，读取差异后合并。
- Ruling：基础分析默认关闭，待安全提交/撤销及质量门槛完成再启用自动写入；代价是本批不直接减少默认队列，后续全局融合仍必须实施。
- Ruling：不自动提交、推送；保留任务记录以支持后续接续。
