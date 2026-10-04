# 计划 B（L11–L15）规划交接

```text
task_ids: L11–L15 规划（未实施）
review_status: 规划待用户确认
worktree: /Users/arvinhan/SmartSketch/.claude/worktrees/smartsketch-plan-a-fixes-e70a34
branch: claude/smartsketch-plan-a-fixes-e70a34（与 claude/smartsketch-contest-sprint-77644f 同为 d766f40）
base_commit: d766f40（计划 A 审查修复版本；代码 HEAD 959331e）
head_commit: 本交接所在提交（只含文档）
author: Claude
plan: docs/superpowers/plans/2026-10-03-contest-sprint-b-functional-loop.md
```

## 交付物

- 计划文件见上；`docs/tasks.md` 已登记 L11–L15 为「规划待确认」。
- 本次没有修改任何业务代码、契约、迁移或测试，也没有调用真实模型（累计台账仍为 140230 / 5000000 token）。

## 规划依据（只读核对）

- 已签收设计 §1、§6、§7、§8；计划 A 与 ADR-080/081/082。
- Codex 审查 R01–R13、赛题边界分析。早期未签收建议以已签收设计为准。
- 逐项读过的源码与测试：
  - 前端：`App.vue`、`router/index.ts`、`CoursesView.vue`、`StudentGraphView.vue`、`TeacherGraphView.vue`、`KnowledgeDetail.vue`、`useKnowledgeDetail.ts`、`graph/lifecycle.ts`、`useGraphFilters.ts`、`useLearning.ts`、`Recommendations.vue`、`useVersions.ts`、`useMaterials.ts`、`ChatView.vue`、`stores/course.ts`；
  - 后端：`services/graph/read.py`、`services/qa/context.py`、`services/qa/citations.py`、`services/versions/snapshot.py`、`services/ai/demo.py`、`workers/parse_task.py`、`repositories/materials.py`、`repositories/chunks.py`；
  - 契约：`SourceRef`、`Citation`、`PublishBlocked*`、`Recommend*`、`Course`；
  - 端到端：`tests/e2e/*.spec.ts`、`fixtures.ts`、`scripts/e2e.sh`。
  - 环境事实：G6 5.1.1 提供 `focusElement`/`zoomTo`/`getZoom`；PDF 解析基于 pdfminer.six；本机没有 Python PDF 生成库，改用 Chrome 无头打印。

## 风险

1. 中文文本型 PDF 首次进入网页链路（L11-1 先验证解析）。
2. 个人模式端到端依赖新写的本机假供应商（L11-2），它需要从提示词推断用途。
3. 真实模型的耗时与质量未知；60 秒、15 秒、70% 都是待实测指标。
4. L12、L13、L14 共用图谱与问答页面，必须串行。

## 需要用户决定

1. 是否批准计划 B 按文中顺序执行。
2. 是否批准计划内约 30～53 万 token 的真实模型调用（L11-6 与 L15-6 Step 4），执行后累计约 44～67 万 / 500 万。
3. 问答输出上限（`ANSWER_MAX_OUTPUT_TOKENS = 1024`）是否在 L16 之前调整。它影响长回答，计划 B 不动。
4. 第二门课的主题：计划默认用「操作系统 第 2 章 进程与线程」（自编）；若想换主题请指出。

## 下一步

用户确认后，从 B0 开始逐任务执行，每个子任务完成即提交并更新交接。
