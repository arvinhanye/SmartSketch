# L14 掌握标记 → 推荐更新 → 看懂学习路径（计划 B，R11）交接

```text
task_ids: L14-1～L14-4
review_status: ready_for_review（随 L13+L14 阶段门禁）
worktree: /Users/arvinhan/SmartSketch/.claude/worktrees/smartsketch-plan-a-fixes-e70a34
branch: claude/smartsketch-plan-a-fixes-e70a34
author: Claude
```

## 交付物

| 子任务 | 提交 | 内容 |
| --- | --- | --- |
| L14-1 | `3b50380` | `src/frontend/src/graph/learningPath.ts`：`buildLearningPath`（焦点、角色、高亮边、叙述、推荐序号），纯函数 |
| L14-2 | `8d6988e` `aa2d7ad` `09349d3` | 画布状态 `pathPrereq`/`pathUnlock`/`dimmed`、边 `pathEdge`/`dimmed`（颜色只在 `buildGraphOptions`）；`nodeLabel` 加序号；`useLearning` 按完整已发布图计算路径（`pathGraph`、`focus` 选项、`learningPath` 输出）；学生页焦点为点选的推荐项，视口跟随；首次渲染后关闭 G6 `autoFit`，记住最近聚焦节点 |
| L14-3 | `5d171e4` `d668e0d` | `Recommendations.vue` 顶部路径行（`rc-path-line`）、显式序号（`rc-order`）、「排序参考」、中性值 0.5 写「未标注（按中性值 0.5 排序）」；后端理由句在属性缺失时写「未标注，按中性值 0.5 计」 |
| L14-4 | `653089e` | `personal.spec.ts` 掌握联动；`tests/e2e/api.ts` 新增 `registerStudent` |

## 设计取舍

- 计划示例里「A 已掌握、焦点 B 时 A 是 mastered」与只看直接前置的规则矛盾（A 不是 B 的前置）。实现为：促成解锁的其他已掌握前置也标「已掌握」并高亮其边，叙述因此是「已掌握：A → 下一步：B → 之后解锁：C」。
- 缺失前置（焦点为推荐项时理论上不会出现，越序掌握的投影下可能出现）单列「还需先学」，叙述类型多一个 `missing` 字段。
- 没有推荐（全部掌握）时不叠加路径状态，避免整图变灰；选中的节点不淡化。
- 前端无法区分「属性缺失」与「明确为 0.5」，展示统一写「未标注」；目前抽取与教师编辑都不填这两个属性。后端知道是否缺失，理由句精确区分（明确为 0.5 仍写数值）。
- G6 `autoFit` 只在首次渲染生效；之后的数据更新保持视口。新版本重载图谱时不会自动整图适配（尺寸变化、切换布局仍会）。

## 验证

- `tests/frontend/l14.test.ts` 21 passed（其中 L14-1 纯函数 8 例，惰性桩下 5 failed → green）。
- `tests/backend/test_l14_reason.py` 3 passed（red 2）；`test_i04.py`、`test_i05.py` 154 passed。
- `h04`/`h05`/`h11`/`i06`/`l13`/`l13-kp-link` 回归通过；type-check exit 0。
- 个人模式端到端 3 passed（`.e2e/20261003-120719` 为加入视口修复前；视口修复后以截图运行复核 exit 0，最终以阶段门禁为准）。
- 真实浏览器截图（本会话 scratchpad，不入库）：初始视口落在「1. 链栈」并显示紫色路径边；标记已掌握后焦点移到新的第 1 项。

## 接口/数据变更

- 无契约变更。`reason` 文案在属性缺失时变化（`specs/learning-path.md` §4.1）。
- `G6NodeData` 增加可选 `pathOrder`（仅学生页叠加，适配层不填）。

## 已知限制

- 路径的解锁节点可能离焦点很远（层次布局横向展开），视口只保证焦点可见。
- 同章 PDF 与 Markdown 同时上传时推荐列表会出现同名项（R05，跨任务融合不在本期）。

## 下一步

L15：课程内角色侧栏、概览阶段与下一步、入课空态、跨课隔离、恶意文本、两课程总验收。
