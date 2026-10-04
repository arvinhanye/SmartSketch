# 计划 C · C05 剩余交互问题 交接

```text
task_id: C05-1～C05-4（视觉美化不在本阶段：用户 2026-10-03 决定技术达标后另开前端设计任务）
review_status: ready_for_review
worktree: /Users/arvinhan/SmartSketch/.claude/worktrees/smartsketch-plan-a-fixes-e70a34
branch: claude/plan-c-reliability
author: Claude
paid_calls: 0
```

## 交付物

| 子任务 | 提交 | 内容 |
| --- | --- | --- |
| C05-1 | `ce378bc` | 教师图谱有未保存修改时，搜索定位先弹确认。画布只在选中真正切换后聚焦：取消则画布与详情都留在原节点；确认则二者一起切换。`useSelectionGuard.request` 增加 `then`（立即切换或确认后执行；取消、或选中被外部改变如删除节点、换课时丢弃） |
| C05-2 | `1a8da3f` | 问答右栏点开出处改用 `SourceViewer`：与图谱来源同一 600 字折叠、文件名与位置、纯文本渲染、收起；保留「出处 [n]」标题 |
| C05-3 | `c7f15e4` | 推荐列表路径行「之后解锁」的名称可点击：选中该节点并把画布移过去（解锁节点可能在视口外）。路径行文字不变；`learningPath` 增加与 `narrative` 同序的 `narrativeIds` |
| C05-4 | `3101b54` | 上传页：已上传同一章的另一种格式（同名不同扩展名，`.markdown` 与 `.md` 视为同一格式）时，上传前提示会产生同名知识点，**不阻止上传**；不做融合 |

## 验证

- 先红后绿：
  - h14：守卫 1 例 + 页面 3 例，其中 2 例先红，复现了「确认框还开着时画布已移到新节点」；
  - l12：1 例；
  - l14：3 例；
  - h02：2 例。
- 前端全量：37 文件 **911 passed**；`npm run type-check` exit 0；`npm run build` 成功（既有的 chunk 体积告警仍在）。
- 随之调整：`l12.test.ts` 原断言「展开的原文带文件名」从 `.source__where` 改为 `SourceViewer` 的 `sv-document`（标题不再重复文件名）。

## 接口/数据变更

无契约、后端或数据变更。

## 风险与限制

- C05-3 只保证点击后可见，不保证路径上所有节点同时在视口里。
- C05-4 只看文件名主干，不比较内容；改了文件名的同章资料不会被提示。
