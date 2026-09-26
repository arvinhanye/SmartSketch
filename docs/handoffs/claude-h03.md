# Claude 交接：H03 契约到 G6 数据适配

- `task_id`: H03（`docs/atomic-task-plan.md`「H03 实现契约到 G6 数据适配」）
- `review_status`: ready_for_review
- 分支：`claude/project-thread-m4mk7n`；`base_commit`: `ebb0f42`（origin/main，已含 B14、F07）
- `head_commit`: 本交接所在提交
- 依赖：B14（生成的 TypeScript 契约类型）、F07（`GET /api/v1/courses/{cid}/graph` 返回 `GraphExchange`）
- 依据：`src/contracts/api.v1.yaml` 的 `GraphExchange`、`KnowledgePoint`、`Relation`（`RelationStandard | RelationDowngraded`）；`specs/course-knowledge-graph.md`（`PREREQUISITE` 方向为 `from_id` 是 `to_id` 的前置、B11 降级标记、验收 3 课程隔离、验收 5 图例/筛选）；`docs/architecture.md` 关系中文名。

## 交付物

- `src/frontend/src/graph/adapter.ts`（新增）：纯函数，无 G6 运行时依赖（G6 依赖留给 H04 画布组件）。
  - `toG6Data(graph)` → `{ nodes, edges, issues }`，形状即 G6 v5 `GraphData`（`id`/`data`/`style`、边 `source`/`target`）。
  - 元素 ID：节点 `kp:<id>`、边 `rel:<id>`（`nodeElementId`/`edgeElementId` 导出），节点与边同名 ID 不冲突；节点、边、问题均按契约 ID 的码点顺序输出（不用 `localeCompare`），同一张图不论输入顺序输出逐字节相同。
  - `RELATION_STYLES`（深冻结）：包含 灰实线有箭头、前置 蓝粗实线有箭头、相关 绿虚线无箭头、应用实例 橙点线有箭头；`label` 供图例与边标签复用。边上的 `lineDash` 是副本。
  - 方向：`source = from_id`、`target = to_id`，`RELATED_TO` 不画箭头（`data.directed = false`）。成环降级边按 `RELATED_TO` 画，`data.downgraded = true`。
  - 不进画布、逐条记入 `issues` 的情况：`course_id` 与图不符（`foreign_course`）；重复 ID 只留首个（`duplicate_id`）；端点不在保留节点集（含指向外课节点）的边（`missing_endpoint`，带缺失的知识点 ID）。自环两端在即保留。
  - 不修改输入；输出不引用输入的任何对象或数组。节点数据只带画布与筛选所需字段（`kpId/name/type/level/chapterId/status/confidence/source/locked`），定义与来源由详情接口取。
- `tests/frontend/h03.test.ts`（新增，22 项）：四类边样式、方向、降级边、缺端点、课程隔离、重复 ID、空图、稳定 ID/排序、深冻结输入与引用泄漏检查。

## 验证

仓库根目录执行：

| 步骤 | 命令 | 结果 |
| --- | --- | --- |
| 依赖 | `npm --prefix src/frontend ci` | exit 0 |
| 红灯 | `npm --prefix src/frontend run test -- --run ../../tests/frontend/h03.test.ts`（仅测试） | 无法解析 `graph/adapter`，`Tests no tests` |
| 绿灯 | 同上（实现后） | 22 passed |
| 类型检查 | `npm --prefix src/frontend run type-check` | exit 0；测试文件另拷入 `src/` 用同一 tsconfig 检查也 exit 0（检查后删除） |
| 前端全量 | `npm --prefix src/frontend run test -- --run` | 10 files，285 passed |
| 构建 | `npm --prefix src/frontend run build` | exit 0 |
| 门禁 | `./scripts/verify.sh`（PATH 前置 `src/backend/.venv/bin` 与仓库外临时安装的 `openapi-typescript@7.4.4`，venv 另装 `src/contracts/toolchain.txt` 列出的校验/生成依赖） | exit 0 |

反向篡改 11 处，均使 h03 失败，恢复后 `cmp` 一致：相关边改有向、端点反向、不丢缺端点边、不按 ID 排序、改用 `localeCompare`、`lineDash` 共享样式表引用、不做课程隔离、不去重、元素 ID 无前缀、原地排序输入数组、降级标记恒为假。

## 接口 / 数据变更

无。只读消费现有契约类型，未改 `src/contracts/`、后端或路由。

## 待决与下一步

- 颜色取值是占位视觉方案，未经设计签收；改色只需改 `RELATION_STYLES`，测试只要求四类可区分。
- 未对 `status = rejected` 或 `low_confidence` 做样式区分，也不在适配层过滤；是否在教师草稿视图隐藏驳回项由 H04/H05 的筛选决定。
- `issues` 目前只返回不提示；页面是否给教师显示「N 条关系端点缺失」由后续视图任务决定。
- 下一位（H04）：安装 `@antv/g6`，`graph.setData(toG6Data(dto))`，节点点击用 `data.kpId` 调 `getKnowledgePoint`；B04-R01 提到的图谱槽位只读暴露可在接入时处理。

## 回滚

只新增两个文件与本交接、看板一节；`git revert` 本任务提交即可，无迁移或依赖变更。
