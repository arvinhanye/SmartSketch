# Claude 交接：H05 图搜索筛选与布局切换

- `task_id`: H05（`docs/atomic-task-plan.md`「H05 实现图搜索筛选与布局切换」）
- `review_status`: ready_for_review
- 分支：`task/h05`（本地，未推送）；`base_commit`: `ddae1ed`（第九批认领提交，基于 `main@0b8aa73`）
- `head_commit`: 本交接所在提交
- 依赖：H03（`graph/adapter.ts` 适配图、`RELATION_STYLES`）、H04（`graph/lifecycle.ts`、`components/GraphCanvas.vue`）
- 决策：ADR-052（协调方预分配）

## 交付物

- `src/frontend/src/composables/useGraphFilters.ts`（新增，文件锁内）
  - `filterGraph(适配图, 条件, 选中kpId)` 纯函数：知识点按类型、审核状态、章节、名称搜索（NFKC + 小写 + 去首尾空白后包含匹配）筛；关系按类型、审核状态筛且两端必须可见——**无悬空边**。输出保持输入顺序，并打状态：`rejected`、`lowConfidence`、`selected`（审核状态在前、选中在后）。不修改输入。
  - `defaultFilterState()`（四类关系、五类知识点、四种状态、全部章节、空搜索）、`sameFilterState`、`chapterOptions(图, GraphExchange.chapters?)`（只列图中出现的章节，按 `order` 排序，标题缺失用 ID，末尾「未分章」）。
  - `useGraphFilters(source, { initial?, layout? })` → `state`、`layout`、`selected`、`visible`、`summary`、`isDefault`、`selectedHidden`、`clear()`、`select()`、`toggleRelationType()`。**清空恢复**到 `initial`（缺省为全量）；清空和切换布局都不改选中；筛选隐藏选中节点时保留选中并置 `selectedHidden`；新图里已无选中知识点时清除选中。
  - 中文名表 `NODE_TYPE_LABELS`（概念/定理/公式/方法/例题）、`STATUS_LABELS`（待审核/低置信度/已通过/已驳回）。
- `src/frontend/src/components/GraphToolbar.vue`（新增，文件锁内）：受控组件，`v-model` 筛选条件、`v-model:layout`、`clear` 事件；props `chapters`、`summary`、`canClear`、`selectedHidden`。含搜索框（`aria-label="搜索知识点"`）、**关系图例兼按关系筛选**（颜色/线型/箭头取自 `RELATION_STYLES`）、知识点类型、审核状态（带与画布一致的状态图例）、章节下拉、布局单选组（`role="radiogroup"`，层次/力导向）、清空按钮（默认条件下禁用）、`aria-live` 数量与「选中的知识点已被筛选隐藏」「没有符合条件的知识点」提示。只发出新对象，不改 props。
- `tests/frontend/h05.test.ts`（新增，文件锁内，44 项）：纯筛选（含 5×4×4×16=320 种组合无悬空边）、搜索/章节/状态/状态标记/不改输入、章节选项、组合式（清空恢复、自定义默认、初始条件不被别名修改、布局切换不丢选中、隐藏选中、失效选中、切换关系类型）、布局参数与状态样式、生命周期布局切换（原图重排不重设数据、相同/销毁后忽略、加载中切换补做、零尺寸时用新布局建图、连续切换合并、状态副本）、工具栏 8 项、工具栏+筛选+画布联动 2 项。

### 扩围（文件锁外，最小改动）

- `src/frontend/src/graph/lifecycle.ts`（H04 文件）：
  - 新类型 `CanvasElementState`、`CanvasNode`/`CanvasEdge`（适配图元素 + 可选 `states`）、`GraphLayoutName`；`GraphCanvasData` 由 `Pick<AdaptedGraph,…>` 改为等价接口 `{ nodes: CanvasNode[]; edges: CanvasEdge[] }`，适配图仍可直接传入。
  - `layoutOptions(name)`：`hierarchical` = 原 `antv-dagre` 参数，`force` = `d3-force`。`buildGraphOptions` 读 `init.layout`（缺省层次），新增 `node.state`/`edge.state` 三种状态样式。
  - `CanvasGraphInit.layout?`、`GraphLifecycleOptions.layout?`；`CanvasGraph.setLayout?`/`layout?` 为**可选**成员（H04 及 H06/H08 可能写的替身不需改）。
  - `GraphLifecycle.setLayout(name)`：串行链上 `setLayout → layout() → fitView`，不重建、不 `setData`；复制数据时保留 `states` 副本。
- `src/frontend/src/components/GraphCanvas.vue`（H04 文件）：新增 `layout` prop（缺省 `hierarchical`），建图时传入，变化时调 `lifecycle.setLayout`。共 +12/-3 行，未动 `nodeClick`、状态显示与生命周期挂载逻辑（H06/H08 可能会碰的部分）。
- `docs/decisions.md`：追加 ADR-052。
- `docs/architecture.md`：前端节 H03/H04 条目后加一条 H05。

## 验证

worktree 根目录执行：

| 步骤 | 命令 | 结果 |
| --- | --- | --- |
| 红灯 | `npm --prefix src/frontend run test -- --run ../../tests/frontend/h05.test.ts`（仅测试） | 无法解析 `components/GraphToolbar.vue` 等，`Tests no tests` |
| 任务验证 | `npm --prefix src/frontend run type-check && npm --prefix src/frontend run test -- --run ../../tests/frontend/h05.test.ts` | type-check exit 0；44 passed |
| 前端全量 | `npm --prefix src/frontend run test -- --run` | 12 files，356 passed（基线 312 + 44；h04 27 项不变通过） |
| 构建 | `npm --prefix src/frontend run build` | exit 0 |
| 门禁 | `./scripts/verify.sh`（PATH 前置共享 venv 与 `tools-f10`，即 scratchpad 中的 `vf-f10.sh`；本机 venv 缺 `datamodel-codegen`，未另装） | exit 0，`Scaffold verification passed.` |
| 空白 | `git diff --check` | 无输出 |
| 浏览器冒烟 | 临时入口（验证后已删除）+ `vite` + Playwright Chromium，真实 G6 5.1.1 | 7 节点/7 边渲染；驳回节点渲染样式 opacity 0.4、stroke `#bfbfbf`，驳回边 opacity 0.3，低置信度节点 stroke `#fa8c16` 虚线；选中 `bst` 后状态 `["selected"]`、描边 `#0958d9`；切换力导向后 `getLayout().type = d3-force`、节点坐标全部变化、选中态仍在；切回层次坐标与首次完全相同、选中态仍在；搜索「树」只剩 `kp:avl`、`kp:bst` 与 `rel:e3`；清空后恢复 7/7；无页面错误 |

反向篡改 21 处均使 h05 失败，恢复后逐字节一致（脚本比对）：筛选 9 处（不查端点、忽略关系类型、关系不按状态筛、搜索不做 NFKC、未分章匹配全部、不标选中、选中排在审核状态前、clear 共享初始条件对象、不清除失效选中），生命周期 7 处（副本丢 states、副本共享 states 数组、换布局不 fitView、加载中切换不补做、连续切换不合并、切换时重设数据、建图不传布局），画布 1 处（不响应 layout），工具栏 4 处（图例无线型、清空按钮常可用、改动 props、无匹配不提示）。

## 接口 / 数据变更

无契约、后端、路由或依赖变更。前端内部类型：`GraphCanvasData` 改为显式接口（结构兼容）；`CanvasGraph` 新增两个可选方法；`GraphLifecycle` 新增 `setLayout`；`GraphCanvas` 新增可选 `layout` prop。

## 风险

- 每次筛选变化都会 `setData` 并重新布局，节点位置不保持；大图时力导向会有明显重排（MVP 课程图规模可接受，未做性能测量）。
- 若 H06/H08 同批也改 `GraphCanvas.vue`/`lifecycle.ts`，合并时需手工合并；本任务改动集中在 props 声明、`start()` 的一行与新增一个 `watch`，lifecycle 改动集中在类型、`buildGraphOptions`、`copyNode/copyEdge` 与新增 `relayout`/`setLayout`。
- 状态颜色、力导向参数为占位视觉，未经设计签收。

## 待决

- 教师草稿视图是否默认隐藏驳回项：当前默认全部可见但淡化（最保守，不藏数据）；页面可传 `initial: { statuses: ['draft','low_confidence','approved'] }` 改默认。需产品确认。
- 搜索只匹配名称：适配图不带别名与定义（H03 设计），别名搜索需适配层加字段，留给后续。
- 搜索语义是「只显示匹配知识点及其间关系」，不带邻居；是否需要「显示匹配项 + 一跳邻居」待定。
- 适配层 `issues`（缺端点等）是否提示给教师仍未处理（H03 待决，与本任务无关，留视图任务）。

## 下一步

- 视图任务（H11 等）接入：`const f = useGraphFilters(() => adapted)`，`<GraphToolbar v-model="f.state.value" v-model:layout="f.layout.value" :chapters="chapterOptions(adapted, exchange.chapters)" :summary :can-clear="!f.isDefault.value" :selected-hidden @clear="f.clear" />` + `<GraphCanvas :graph="f.visible.value" :layout="f.layout.value" @node-click="f.select" />`；H06 详情读 `f.selected`。

## 回滚

见 ADR-052「回滚」：删除三个新文件，`git checkout ddae1ed -- src/frontend/src/graph/lifecycle.ts src/frontend/src/components/GraphCanvas.vue docs/architecture.md`，并删去 `docs/decisions.md` 末尾 ADR-052 一节；无数据迁移或依赖变更。
