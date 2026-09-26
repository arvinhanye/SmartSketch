# Claude 交接：H11 学生图谱和卡片视图

- `task_id`: H11（`docs/atomic-tasks.json`「实现学生图谱和卡片视图」），issue #123
- `review_status`: ready_for_review
- 分支：`claude/project-thread-vrtfxt`；`base_commit`: `a7d8075`（origin/main）
- 依赖：H05（`useGraphFilters`、`GraphToolbar`）、H06（`KnowledgeDetail`）、G07（发布版本解析，后端）、H04（`GraphCanvas`）
- 决策：ADR-063（协调方预分配）

## 交付物

| 文件 | 内容 |
| --- | --- |
| `src/frontend/src/views/StudentGraphView.vue`（文件锁） | 路由页 `/courses/:cid/graph`：加载/非学生/未发布/错误（可重试）/空图/就绪六态；就绪后「图谱 / 卡片」切换（`aria-pressed`），共用 `GraphToolbar`（关闭审核状态筛选）、`useGraphFilters` 的筛选与选中；选中后显示 H06 详情抽屉，关闭即取消选中；`COURSE_FORBIDDEN` 回首页并带 `notice=course-forbidden` |
| `src/frontend/src/components/KnowledgeCards.vue`（文件锁） | 受控卡片视图：分页（缺省 12，非法值回退）、空态、`aria-live` 页码；原生按钮卡片 + 漫游 tabindex；方向键跨页、Home/End、PageUp/PageDown；选中项变化跳页，列表变短收回末页 |
| `tests/frontend/h11.test.ts`（文件锁） | 46 项：卡片视图模型排序/不改输入；API 必带 `version`、非法版本不发请求；不取草稿 9 项（课程详情 404 `GRAPH_NOT_PUBLISHED`、未发布、读图 `GRAPH_NOT_PUBLISHED`、课程内教师、版本号透传、4 种异常响应、卡片不另发请求、课程页入口、路由放行）；状态 6 项（加载、空图、网络重试、版本已替换、无权限、切课迟到响应）；图/卡片联动 5 项；分页 8 项；键盘 7 项 |
| `src/frontend/src/api/graph.ts`（**扩围**，新建） | `PublishedGraphApi.getPublished(cid, version)`、`PUBLISHED_GRAPH_API_KEY`、`createPublishedGraphApi` |
| `src/frontend/src/composables/useStudentGraph.ts`（**扩围**，新建） | `useStudentGraph`（课程作用域 + 序号迟到隔离）、`toKnowledgeCards` |
| `router/index.ts`、`main.ts`、`views/CoursesView.vue`（**扩围**） | `STUDENT_GRAPH_ROUTE` 与 `studentGraphComponent` 选项；`main.ts` 注册页面并注入图谱 API；课程页只对课程内学生显示「浏览课程图谱」 |
| `components/GraphToolbar.vue`（**扩围**，H05 文件） | 新增 `showStatuses` 属性（缺省 true，原行为不变），审核状态字段集加 `data-test="status-filter"` |
| `docs/decisions.md`、`docs/architecture.md`、`docs/tasks.md` | ADR-063、前端节一行、H11 节 |

## 「任何入口不取草稿」如何保证（ADR-063）

1. 前端唯一的读图封装要求 `version`，并拒绝非正整数。
2. 只有课程内角色为 `student` 时才读图；课程内教师既不读图也不渲染详情抽屉（详情接口无版本参数，教师会读到草稿）。
3. `published_version = null` 不发请求；响应 `course_id`/`graph_version` 必须与请求一致，草稿（`graph_version = null`）被拒绝。
4. 卡片由已发布图派生，不调用 `GET /kp`。

## 验证

仓库根目录执行（`npm --prefix src/frontend ci` 后）：

| 步骤 | 命令 | 结果 |
| --- | --- | --- |
| 任务验证 | `npm --prefix src/frontend run type-check && npm --prefix src/frontend run test -- --run ../../tests/frontend/h11.test.ts` | type-check exit 0；45 passed |
| 前端全量 | `npm --prefix src/frontend run test -- --run` | 15 files，483 passed |
| 构建 | `npm --prefix src/frontend run build` | exit 0（仅既有的 chunk 体积警告） |
| 门禁 | `PATH=$S/venv/bin:$S/tools/node_modules/.bin:$PATH ./scripts/verify.sh`（`$S` 为 scratchpad；venv 按 `src/contracts/toolchain.txt` 装 pyyaml/openapi-spec-validator/jsonschema/pytest/datamodel-code-generator，npm 装 openapi-typescript@7.4.4、typescript@5.9.3） | `PASS contracts gate`、`Scaffold verification passed.` |
| 任务验证（复审补测） | `npm --prefix src/frontend run type-check && npm --prefix src/frontend run test -- --run ../../tests/frontend/h11.test.ts` | type-check exit 0；46 passed |
| 前端全量（复审补测） | `npm --prefix src/frontend run test -- --run` | 15 files，482 passed / 2 failed（总计 484 = 原 483 + 新增 1）；`b02.test.ts > B02 前端测试配置 > npm test 的退出码` 2 例 5s 超时失败（慢机既有 flake，`origin/main` 同样），单独 `--testTimeout=90000` 复跑 b02 `5 passed` |

测试与实现同批写成，未单独跑红灯。「课程详情本身返回 404 `GRAPH_NOT_PUBLISHED`」用例是对既有正确行为的回归锁：写入后未改实现即通过，**未观察到红灯**（课程详情请求与读图共用同一 `catch`，`handle()` 对 `GRAPH_NOT_PUBLISHED` 一律置 `unpublished`）。非空洞性用输入探针核对：把该用例注入的错误码换成 `NOT_FOUND` 后同一用例失败（`sg-unpublished` 不存在），随即还原，产品代码未改动。

反向篡改 15 处（脚本逐项篡改、跑 h11、还原），14 处检出：去掉学生角色判断、去掉 `graph_version` 核对、去掉未发布判断、卡片排序去掉章节分组、去掉 `GRAPH_NOT_PUBLISHED` 分支、API 去掉 `version` 查询、卡片不跳到选中页、所有卡片可 Tab、方向键不跨页、列表变短不收回页码、不阻止默认滚动、工具栏忽略 `showStatuses`、关闭详情不取消选中、课程页对教师也显示入口。存活 1 处：读图后去掉 `current()` 复核——`store.commit(scope)` 同样丢弃旧作用域的写入，属冗余防护。

未做真实浏览器冒烟（画布部分沿用 H04/H05 已冒烟的组件）。

## 接口 / 数据变更

无契约、后端、迁移或依赖变更。前端新增路由 `/courses/:cid/graph`、注入键 `PUBLISHED_GRAPH_API_KEY`，`GraphToolbar` 新增可选属性。

> **依赖（后端未就绪，非本任务缺陷）**：本页进入就绪态依赖 `GET /api/v1/courses/{cid}`（`getCourse`）返回课程详情中的 `my_role` 与 `published_version`；该端点后端当前尚未实现（`src/backend/app/api/courses.py` 只有 `GET ""` 与 `POST ""`，`tests/backend/test_c15.py:362` 有注释承认），H01/H02 有同样依赖 —— 因此真机端到端「学生打开图谱页」幸福路径暂不可达，验收时不要据此判定 H11 有缺陷。

## 风险

- 详情响应不带版本号：读图与点开详情之间若发布新版本，详情可能来自新版本。
- 课程内教师无法用本页预览学生所见。
- 卡片视觉、每页 12 条为占位，未经设计签收。

## 待决

1. 是否给教师开放「按已发布版预览」（需 `getKnowledgePoint` 加 `version`，改契约）。
2. 原文阅读器落点（`locateSource` 目前在本页无处理）与学生端资料名（H06 待决）。

## 下一步

- I 组学习路径/进度可在本页加入口；H07 等教师页可复用 `KnowledgeCards`。

## 回滚

见 ADR-063「回滚」；无数据迁移或依赖变更。
