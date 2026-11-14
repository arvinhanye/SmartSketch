# 消歧混合召回与可撤销后端实施计划

> **For agentic workers:** Use superpowers:executing-plans task-by-task. 用户已授权连续实施，复用当前分支和前批成果，不自动提交或推送。

**Goal:** 修复审计缺口，交付生成链路中的混合召回、保守映射、图校验和有冲突保护的单项自动合并撤销。

**Architecture:** 有界裁决生成版本化映射，独立草稿副本承载合并结果；SQLite 有效指针在 T6 中切换。逆向差异只触及相关对象，后续变更冲突显式返回。

**Tech Stack:** 现有 Python/FastAPI、SQLite、Neo4j；不新增依赖，不更改前端。

**Spec:** `specs/generation-disambiguation.md` 和完整消歧设计。

## Global Constraints

- 同课程、教师锁定、来源、原始关系、取消/租约/预算保护不可放宽；默认并发 8。
- 不调用旧手动合并代替自动合并；不持锁调用模型；不进行真实付费评测。
- 前端/前端测试/Claude 工作树不改；复用当前分支，不覆盖前批未提交文件。
- 自动执行默认关闭，质量验收仍独立于工程测试。

## Review Focus

- 新副本图提交后 SQLite 提交失败：旧草稿字段/来源必须完全不变。
- 物理草稿 ID 不得绕过学生权限或被发布清扫误删。
- 反向或多步映射使 PREREQUISITE 成环：不能删边换取通过。
- 撤销时存在后来任务或教师变更：保留无关贡献，相关冲突明确返回。
- 接管、预算失败、配置切换：不复用旧输入结论，不把技术未完成当成语义未决。

## Task 1: 修复两项审计待办

**Files:** `fusion/resolution.py`、`workers/extraction/analysis.py`、`tests/backend/test_disambiguation_generation.py`。
**Interfaces:** `SemanticResolver.resolve` 返回技术失败时保留元数据；输入摘要加入输出预算。
- [x] RED：不同输出预算摘要不同；首轮 SAME 后服务端错误保留两次逻辑调用及首轮模型。
- [x] GREEN：普通 ModelError 在裁决服务内归档，任务级错误仍抛出。
- [x] 验证：generation/resolution/E04；预期全部通过。

## Task 2: 混合召回与整组/图安全映射

**Files:** 新增 `fusion/recall.py`、`fusion/mapping.py`、相应后端测试；接入 `extraction/analysis.py`。
**Interfaces:** `recall_candidates(cards, *, top_k, max_pairs, vectors=None)`；`plan_mapping(snapshot, decisions, *, existing_ids)`；结果带候选覆盖、组、原始到规范 ID、拒绝原因。
- [x] RED：多通道并集、同课/同空间、候选上限、不因相似度自动合并；传递陷阱、锁定、自环、间接环、别名和来源保留。
- [x] GREEN：词项索引召回与可选真实向量 top-k；全组两两 SAME；图模拟后才接受组。
- [x] 验证：新增 recall/mapping 测试及 E08/E09/E10、生成回归；预期全部通过。

## Task 3: 草稿投影和版本化存储

**Files:** 新增迁移 `021_fusion_projections.sql`、`repositories/fusion.py`、`repositories/graph_projection.py`；调整 `GraphScope` 和草稿作用域读取；相关测试。
**Interfaces:** `read_draft_scope(database, course_id)`；`GraphScope.storage_version_id`；`read_snapshot(repo, scope)`、`write_snapshot(tx, snapshot)`；准备计划及 T6 激活。
- [x] RED：默认旧草稿兼容、课程隔离、学生不能读物理草稿、发布清扫排除草稿副本、快照往返与来源贡献不丢。
- [x] GREEN：逻辑/物理作用域分离；SQLite 不可变计划记录与头指针；隔离副本写入。
- [x] 验证：迁移/F02/草稿读写/发布范围回归和真实 Neo4j 隔离集成；预期全部通过。

## Task 4: 接通生成全局消歧与 T6 提交

**Files:** 新增 `workers/fusion_task.py`；`persist_graph.py`、配置/工厂、生成集成测试。
**Interfaces:** `prepare_fusion(...)` 返回已保存的当前输入计划；持久化读取指定计划并在 T6 激活。
- [x] RED：跨章节与已有草稿同义映射；生成真正使用结果；无效/过期计划保留原始候选；租约丢失/图提交故障/SQLite 故障不可见；重跑复用一致计划。
- [x] GREEN：锁外召回/裁决、锁内快照校验；独立副本和原子指针；默认关闭的新自动执行开关。
- [x] 验证：新 pipeline 回归、E12/F13/调度/提交围栏及 Neo4j 集成；预期全部通过。

## Task 5: 单项撤销及后端入口

**Files:** 新增 `services/fusion/undo.py`、维护脚本、单元/Neo4j 撤销测试。
**Interfaces:** `preview_undo(...)` / `undo_merge(..., expected_revision, actor_id)`，结果包含 changed、冲突、影响范围和新投影。
- [x] RED：单组撤销、保留其他组和后续无关贡献、教师修改/新依赖冲突、幂等、过期修订、发布快照不变。
- [x] GREEN：计算逆向差异；写新副本，守卫内切指针及追加撤销记录，不改变任务终态。
- [x] 验证：undo 测试与教师写入/发布相关回归、真实 Neo4j；预期全部通过。

## Task 6: 最终验收与交接

- [x] 一次独立全变更审查；重要发现 RED→GREEN 后完整复测。
- [x] basic、后端全量、隔离 Neo4j 及必要故障注入通过；报告真实质量未验证的边界。
- [x] 更新规格/ADR/索引/任务/交接，核对 Claude 和前端未动；保留未提交成果及执行记录。

验收：后端全量 4438 passed / 27 登记跳过；隔离集成 494 passed / 4 登记跳过 + 44 backend-live passed；其后 reembed 兼容模块 34 passed。完整命令、原失败、实施取舍和交付边界见 `docs/handoffs/codex-disambiguation-reversible-backend.md`。
