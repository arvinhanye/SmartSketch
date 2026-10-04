# L12 来源可查看（计划 B，R04）交接

```text
task_ids: L12-1～L12-4
review_status: ready_for_review（随计划 B 阶段门禁再跑一次）
worktree: /Users/arvinhan/SmartSketch/.claude/worktrees/smartsketch-plan-a-fixes-e70a34
branch: claude/smartsketch-plan-a-fixes-e70a34
author: Claude
```

## 交付物

| 子任务 | 提交 | 内容 |
| --- | --- | --- |
| L12-1 | `af671cc` | 契约 `SourceRef`/`Citation` 增加可选 `document_name`（1～255），DTO 重新生成；ADR-085；`specs/grounded-qa.md` Q4、`specs/course-knowledge-graph.md` 验收 5 同步 |
| L12-2 | `af671cc` | `repositories/materials.material_names`（按课程过滤）；知识点详情、关系来源（图谱读取、关系编辑、审核队列）、问答引用填写文件名 |
| L12-3 | `8b79ccc` | `composables/sourceLabel.ts`、`components/SourceViewer.vue`；`KnowledgeDetail` 点开来源即展开查看器；问答右栏带文件名 |
| L12-4 | 本交接所在提交 | `personal.spec.ts` 三入口（教师图谱、学生图谱、问答引用）断言文件名与位置格式 |

## 设计取舍

- 计划原写「两个图谱页处理 `@locate-source` 打开查看器」。实施时改为在详情组件内展开：H06 已约定的事件载荷不变，教师与学生图谱复用同一组件，不必两页分别接线。
- 缺文件名统一写「资料不可用」，不再显示资料编号（H06 原约定随 ADR-085 修订）。
- 查看器只显示随来源返回的片段，不新增读取整份资料的接口；学生不需要资料列表权限即可看到文件名（`test_student_sees_document_name_without_material_list_permission`）。

## 验证

- `tests/backend/test_l12.py` 8 passed；图谱、问答、关系相关后端用例 734 passed / 27 skipped。
- `tests/contracts/test_b08.py` 6 passed；契约生成物与真源一致。
- `tests/frontend/l12.test.ts` 11 passed；前端全量 835 passed；type-check exit 0。
- 个人模式端到端 3 passed（`.e2e/20261003-113400`）；演示端到端 2 passed（`.e2e/20261003-113552`）。

## 随之调整的测试

- `personal.spec.ts`：L11-7 修复后同章 PDF 与 Markdown 抽出的节点名称完全相同，没有名称唯一的 AI 节点；修改定义与「发布后改草稿」改用教师新建的节点。
- `h06.test.ts`、`redesign-chat.test.ts`：按新的来源文字格式更新断言。

## 下一步

L13 图谱可读、搜索定位与问答跳转。
