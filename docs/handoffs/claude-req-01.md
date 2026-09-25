# REQ-01 赛题抽取硬指标补登

- task_id: REQ-01
- 状态: DONE（仅文档补登；指标尚未实测）
- 分支 / base: `claude/pdf-course-model-training-0b0f46` / `6639e16`
- 执行: Claude，应 ArvinHan 2026-09-24 会话要求

## 背景

对照赛题原文（`【A10】基于AIGC的课程知识图谱智能构建与学习导航系统【金扬智能】.docx`，在主目录，不入库）发现：第 6 节「技术要求与指标（一）」的两项硬指标没有出现在 `docs/product.md`、`docs/atomic-task-plan.md` 或 `specs/` 中：

1. 以一门完整课程的一章为基准，抽取知识点实体不少于 20 个；
2. 知识抽取准确率（人工抽样）不低于 70%，并在文档中说明改进方向。

同时确认：赛题不要求训练或微调模型（调用大模型 API；路径推荐可用简单图遍历；不要求 GPU）。

## 改动

| 文件 | 改动 |
| --- | --- |
| `specs/course-knowledge-graph.md` | 关联任务补 K01/K02；新增验收 7：基准材料、实体数、准确率、判定对象、报告内容、失败路径 |
| `docs/product.md` | MVP 表新增「抽取质量」行 |
| `docs/atomic-task-plan.md`、`docs/atomic-tasks.json` | K01：输入改为「自编材料（至少一章完整课程量）」，验收加硬指标口径；K02：验收加两项指标的判定与改进方向，功能文件加 `evaluation/reports/extraction-accuracy.md`；人工决策门 D-01 行补一章基准与版权要求 |
| `docs/tasks.md` | D-01 行补材料要求；新增 REQ-01 节 |

## 关键决定

- **70% 按实体、关系分别达标**：赛题没有区分，取较严的理解；ArvinHan 2026-09-24 确认，登记为决策 D-15（原拟 D-14，与 PR #199 撞号，合并时改号）。
- **实体数统计口径**：处理到 `awaiting_review` 时草稿中 `source = ai` 的节点（融合去重后），即教师审核前的自动抽取结果，与赛题「自动抽取」一致。
- **只统计真实模型的输出**：依赖 D-02 签收，付费调用另行确认；fake 结果不能证明达标。
- 没有新增任务 ID，而是扩展已有的 K01/K02，避免评测口径分散。任务总数仍为 141。

## 验证

- `python3 docs/reviews/validate_atomic_plan.py`：PASS（141 项 = 133 主线 + 8 加分；MD/JSON ID 与数量一致；链接可解析）
- `./scripts/verify.sh`：见 `docs/tasks.md` REQ-01 行
- `git diff --check`：exit 0
- 没有代码、契约、配置或数据模型变更。

## 风险与下一步

- 指标只是写入了验收条件，还没有实测。实际达标取决于 E05/E06 抽取质量、D-01 的材料和 D-02 的模型选择。
- K01 认领者的第一步：在 `evaluation/README.md` 写明判定标准与抽样方法（固定种子、样本量或全量检查），再准备一章量的自编标注材料。
- 回滚：`git revert` 本提交即可，只涉及文档。
