# 前端规则

- 使用 Vue 3 + TypeScript + Vite；组件使用 Composition API，并保持严格类型检查。
- `views/` 负责路由级页面，`components/` 负责可复用 UI，`composables/` 负责状态/副作用，`api/` 只封装 HTTP 与 SSE 调用。
- G6 图数据由适配层转换；组件不得直接依赖后端原始响应。
- 图谱至少支持缩放、拖拽、节点详情、关系图例和按关系筛选。可访问性、空态、加载态、错误态均需覆盖。
- 新增接口前先更新 `src/contracts/` 和对应功能规格；新增交互需有可验证的验收条件。
