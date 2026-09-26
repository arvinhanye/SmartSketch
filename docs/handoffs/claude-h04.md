# Claude 交接：H04 G6 画布生命周期

- `task_id`: H04（`docs/atomic-task-plan.md`「H04 实现 G6 生命周期组件」）
- `review_status`: ready_for_review
- 分支：`claude/project-thread-3eixq2`；`base_commit`: `95d5c9a`（origin/main，已含 H03）
- `head_commit`: 本交接所在提交
- 依赖：H03（`graph/adapter.ts` 的 `toG6Data` 输出）
- 决策：ADR-040（编号由协调方预分配）

## 交付物

- `src/frontend/src/graph/lifecycle.ts`（新增）
  - `createGraphLifecycle(container, { data, factory?, onNodeClick?, onStatus? })` → `{ status, update, refreshSize, destroy }`；状态 `waiting | rendering | ready | error | destroyed`。
  - 建图：量容器 `clientWidth/clientHeight`，为 0 时推迟到 `ResizeObserver` 报出尺寸。对 G6 的操作排成一条串行链，渲染中的多次 `update` 只画最后一次。
  - resize：观察器回调经 `requestAnimationFrame` 合并，尺寸变化才 `setSize` + `fitView`；无 `ResizeObserver` 时退回 `window` resize。
  - 销毁：幂等；断开观察、取消帧、销毁图；工厂迟到返回的图立即销毁，迟到的渲染不改状态。
  - 交给 G6 的数据逐层复制，调用方对象不被改写。点击只对当前画布上的节点回传 `data.kpId`。
  - `buildGraphOptions`（默认参数，见 ADR-040 第 6 条）、`loadG6Graph`（动态导入 G6）、`GRAPH_FACTORY_KEY`（注入键）。
- `src/frontend/src/components/GraphCanvas.vue`（新增）：props `graph: GraphCanvasData | null`、`label?`；事件 `nodeClick(kpId)`。`null` 与首次渲染前显示加载（`role="status"`、`aria-busy`），空图显示「暂无知识点」，失败显示 `role="alert"` 与重试按钮；画布区 `role="img"`，`aria-label` 含知识点数与关系数。KeepAlive 激活时复查尺寸。
- `src/frontend/package.json` / `package-lock.json`：新增 `@antv/g6` `5.1.1`（精确版本）。锁文件用 `npx npm@11` 生成，只有新增条目（本机 npm 10 会删掉已有的 `libc` 字段，已弃用）。任务清单的文件范围未列出这两个文件，但 H03 交接已指明 H04 安装 G6，这里一并记录。
- `tests/frontend/h04.test.ts`（新增，27 项）：挂载、数据副本、零尺寸推迟、默认参数、更新与合并、加载中更新、resize 合并/零尺寸/未变、window 退路、销毁（含加载中、渲染中两种迟到）、失败、节点点击；组件的加载/空/失败重试/更新/点击/卸载、路由来回 20 次无泄漏、KeepAlive 激活。
- 文档：ADR-040；`docs/architecture.md` 前端节加一条；`docs/tasks.md` H04 节。

## 验证

仓库根目录执行：

| 步骤 | 命令 | 结果 |
| --- | --- | --- |
| 依赖 | `npm --prefix src/frontend ci` | exit 0 |
| 红灯 | `npm --prefix src/frontend run test -- --run ../../tests/frontend/h04.test.ts`（仅测试） | 无法解析 `components/GraphCanvas.vue`，`Tests no tests` |
| 绿灯 | 同上 | 27 passed |
| 类型检查 | `npm --prefix src/frontend run type-check` | exit 0（含 `tests/frontend`） |
| 前端全量 | `npm --prefix src/frontend run test -- --run` | 11 files，312 passed |
| 构建 | `npm --prefix src/frontend run build` | exit 0（尚无页面引用画布，G6 未进产物） |
| 门禁 | `./scripts/verify.sh`（PATH 前置临时 venv：`toolchain.txt` 所列 pyyaml/openapi-spec-validator/jsonschema/pytest；与临时安装的 `openapi-typescript@7.4.4`） | exit 0 |
| 浏览器冒烟 | 临时入口（验证后已删除）+ `vite` + Playwright Chromium | 四类边正确绘制、平行边分开；滚轮缩放与拖拽画布改变画面；容器 600×480 → 900×600 → 500×520 时画布尺寸随之变化；更新数据后标签计数变化；挂载/卸载 10 次后文档中 canvas 为 0；无页面错误（仅 favicon 404） |

反向篡改 16 处均使测试失败，恢复后 `cmp` 一致：生命周期 11 处（零尺寸即建图、resize 到 0、迟到图不销毁、更新不复制、不断开观察、不取消帧、不 fitView、点击未知节点回传、建图/更新渲染后不查存活×2、首次渲染期间的更新被丢），组件 5 处（卸载不销毁、不响应激活、重试不销毁旧图、不转发更新、无空态）。一处等价变异（去掉重复排队标记）说明该标记冗余，已删除。

## 接口 / 数据变更

无契约、后端或路由变更。新增前端运行时依赖 `@antv/g6@5.1.1`。

## 待决与下一步

- 画布尚未接入页面：教师/学生图谱页（H05、H11）用 `toG6Data(store.graph)` 喂给 `GraphCanvas`，`nodeClick` 接 H06 详情。
- 布局切换、图例与按关系筛选归 H05；切换布局时可在 lifecycle 上加方法，保留串行链。
- `rejected`/`low_confidence` 样式、`issues` 提示仍按 H03 待决处理。
- 画布不可键盘操作；键盘可达由 H11 卡片视图承担。
- 默认视觉（节点 28px 蓝框、层次布局）为占位，未经设计签收。

## 回滚

见 ADR-040「回滚」：撤销三个新文件，删除 `@antv/g6` 依赖并还原锁文件；无数据迁移。
