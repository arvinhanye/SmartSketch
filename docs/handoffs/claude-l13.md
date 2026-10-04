# L13 图谱可读、搜索定位与问答跳转（计划 B，R06、R08）交接

```text
task_ids: L13-1～L13-5
review_status: ready_for_review（随计划 B 阶段门禁再跑一次）
worktree: /Users/arvinhan/SmartSketch/.claude/worktrees/smartsketch-plan-a-fixes-e70a34
branch: claude/smartsketch-plan-a-fixes-e70a34
author: Claude
```

## 交付物

| 子任务 | 提交 | 内容 |
| --- | --- | --- |
| L13-1 | `1d50a33` | `graph/lifecycle.ts`：`READABLE_ZOOM = 0.7`；`CanvasGraph` 可选 `getZoom`/`zoomTo`/`focusElement`；首次渲染、重新布局、尺寸变化后若缩放低于 0.7 则放大并聚焦（待聚焦节点优先，否则第一个没有前置的节点）；`focus(kpId)`、`onZoom`。`GraphCanvas.vue` 暴露 `focus`，容器 `data-test="graph-canvas"` 带 `data-zoom` |
| L13-2 | `50e5389` | `useGraphFilters.locateNode` / `filters.locate`：名称完全一致优先、包含其次，只匹配当前筛选可见节点，未命中不清空选中；工具栏回车发 `locate`；两个图谱页收到后选中并聚焦，未命中提示 |
| L13-3 | `25470ab` | 工具栏类型、状态、章节收进默认收起的 `<details data-test="gt-advanced">`；搜索、关系图例（兼按关系筛选）、布局常显 |
| L13-4 | `8aa5cfb` | `composables/kpLink.ts`（纯函数）；问答知识点按钮改为指向 `?kp=&v=` 的链接；学生图谱消费参数：选中并聚焦、目标不在当前版本或版本不同时提示、不跨课找同 ID 节点 |
| L13-5 | 本交接所在提交 | `personal.spec.ts`：问答点知识点 → 图谱详情标题与按钮名称一致 → 刷新直达仍选中；画布 `data-zoom` ≥ 0.7 且节点数 ≥ 20；搜索回车选中 |

## 设计取舍

- 计划 L13-3 写「未选中时不渲染右栏」。学生页右栏同时承载学习路径面板，详情与掌握标记本就只在选中时渲染；整栏收起会让学习路径不可见，因此只做了筛选折叠。
- 端到端的「搜索后详情标题正确」用教师新建的节点而不是「循环队列」：L11-7 后同章 PDF 与 Markdown 抽出的名称完全相同，同名节点存在多份，完全一致匹配只能命中其中之一，用唯一名称断言更稳定。
- 端到端先等问答按钮显示知识点名称（不是 `kp_` 编号）再点击：问答页的已发布图谱名称是异步取回的，过早读取按钮文字会拿到编号。

## 验证

- `tests/frontend/l13.test.ts` 10 passed；`tests/frontend/l13-kp-link.test.ts` 8 passed。
- 个人模式端到端 3 passed（`.e2e/20261003-115144`，独立端口 18100/15273/17788/18990，本机假供应商，无费用）。
- 阶段门禁见下一节（随 L13 一起运行）。

## 接口/数据变更

无契约、后端或数据模型变更。

## 下一步

L14：学习路径纯函数、画布路径高亮与序号、推荐解释。
