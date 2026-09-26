# Claude 交接：H02 资料上传和进度页面

- `task_id`: H02（`docs/atomic-task-plan.md`「H02 实现资料上传和进度页面」）
- `review_status`: ready_for_review
- 分支：`worktree-agent-a8f3ece6bb7d1719d`；`base_commit`: `5072a48`（origin/main，已含 H01、C07、C12）
- `head_commit`: 本交接所在提交
- 依赖：H01（课程页、课程 store 作用域）、C07（`listDocuments` / `uploadDocument`）、C12（`src/frontend/src/api/taskEvents.ts`）
- 依据：`src/contracts/api.v1.yaml` 的 `listDocuments`、`uploadDocument`、`cancelTask`、`Document`、`UploadAccepted`、`Task`、`TaskEvent`、`TaskNotCancellableError`；`src/contracts/errors.v1.md`「上传与解析」；`specs/task-processing.md` §1、§4、§6、§7、I3；`specs/identity-access.md` 访问矩阵；`docs/integrations.md` `UPLOAD_MAX_BYTES`（D-11）；`docs/handoffs/claude-c07.md`、`claude-c12.md` 的 H02 建议。
- 本任务未改 `docs/tasks.md`（由协调会话维护）。

## 交付物

- `src/frontend/src/api/materials.ts`（新增）：只封装 HTTP。
  - `createMaterialsApi(client)`：`list(cid)` → `GET /api/v1/courses/{cid}/documents`；`upload(cid, file)` → `POST` 同路径，`FormData` 字段 `file`（Content-Type 由浏览器生成）；`cancelTask(tid)` → `POST /api/v1/tasks/{tid}/cancel`。类型全部取自生成的 `components['schemas']`。
  - 注入键 `MATERIALS_API_KEY`、`TASK_EVENTS_CLIENT_KEY`（后者注入 C12 的 `TaskEventsClient`，C12 文件未改）。
- `src/frontend/src/composables/useMaterials.ts`（新增）：页面状态与副作用。
  - 访问：先 `GET /courses/{cid}` 看 `my_role`，非 `teacher` 显示「仅课程教师…」且不请求资料列表；列表 403 `ROLE_FORBIDDEN` 同样处理；`COURSE_FORBIDDEN` 显示无权访问。授权仍以后端为准。
  - 本地校验：扩展名 `.pdf/.docx/.txt/.md/.markdown`（大小写不敏感，与后端 `file_storage._EXTENSIONS` 一致，`.md` 这类纯点前缀名视为无扩展名），空文件拒绝，上限 `MATERIAL_MAX_BYTES = 50 MiB`（`UPLOAD_MAX_BYTES` 默认值）。非法时 `role=alert` 提示支持格式并 `aria-invalid`，不发请求。
  - 服务端错误：415 → 列出支持格式；413 → 按 `details.limit_bytes` 提示上限；422 → 文件名不合要求；401/403 固定文案；网络/超时/`STORAGE_UNAVAILABLE`/其他 5xx → 可「重试上传」（同一 `File`）。不回显服务端 `message`。上传防重入（同步标志）。
  - 上传成功：跟踪 `task_id`，经 `TaskEventsClient.subscribe(task_id, scope, …)` 订阅（`scope` 来自 `useCourseStore().beginRequest()`），静默刷新列表；列表未刷新到时以上传文件名占位成行。
  - 状态：`taskStatusOf` 把「取消中」（非终态且 `cancel_requested = true`）与「已取消」（`stage = cancelled`）分成两种 `kind`；`failed` 即使标志为 true 也按失败显示（TASK-7）。阶段文案：排队中/解析中/抽取中/融合中/入库中/待审核/已完成审核/处理失败/已取消。
  - 取消：仅 `queued/parsing/extracting/merging` 且未置标志时可点；提交中按钮禁用、不提前显示「取消中」；以响应体 `stage`/`cancel_requested` 为准；409 `TASK_NOT_CANCELLABLE` 以 `details.stage` 刷新并按 `details.reason` 给提示（不假装成功）；网络失败提示可再取消。
  - 失败重试：任务 `failed`/`cancelled` 且本次会话保留了文件 → 「重新上传」（新资料、新任务，符合 I3）；列表来的历史资料没有文件 → 提示「请重新选择文件上传」。失败原因按 `error.code` 给固定文案。
  - 流状态：`reconnecting`/`polling` 显示提示；`fatal` 关闭 → 「进度连接已中断」+「重新连接」（重新订阅）。
  - 离开关流：路由离开（含回同一课程的课程页，此时课程作用域不失效）、卸载、切到另一课程资料页时，关闭全部订阅、中止在途上传/列表/取消请求；迟到回调一律丢弃。
- `src/frontend/src/views/MaterialsView.vue`（新增）：加载（`role=status` + `aria-busy`）、空态、错误态（`role=alert` + 重试）、无权限态；文件控件有可见 `label` 与 `accept`、`aria-describedby` 指向格式提示与反馈；每行状态 `aria-live=polite`，进度条 `role=progressbar` + `aria-valuenow` + `aria-label`；按钮带具体 `aria-label`。
- `tests/frontend/h02.test.ts`（新增，53 项）。
- 范围扩展（最小）：
  - `src/frontend/src/router/index.ts`：新增 `MATERIALS_ROUTE = 'course-materials'` 与可选 `materialsComponent`，注入后注册 `/courses/:cid/materials`（`anyAccountRole`，课程内角色由页面判断）。与 H12 并行时只会在同一处追加各自的路由块。
  - `src/frontend/src/views/CoursesView.vue`：当前课程 `my_role = teacher` 且资料路由已注册时显示「资料上传与处理进度」链接。
  - `src/frontend/src/main.ts`：注册资料页，provide `MATERIALS_API_KEY` 与 `TASK_EVENTS_CLIENT_KEY`（`createTaskEventsClient({ client: http })`，复用会话 HTTP 客户端）。

## 验证

在 worktree 根目录执行：

| 步骤 | 命令 | 结果 |
| --- | --- | --- |
| 依赖 | `npm --prefix src/frontend ci` | exit 0，0 vulnerabilities |
| 红灯 | `npm --prefix src/frontend run test -- --run ../../tests/frontend/h02.test.ts`（仅测试，实现前） | 测试文件加载失败，`Tests no tests`（模块不存在） |
| 绿灯 | 同上 | 53 passed |
| 类型检查 | `npm --prefix src/frontend run type-check` | exit 0 |
| 前端全量 | `npm --prefix src/frontend run test -- --run` | 8 files，203 passed |
| 门禁 | `PATH=<scratchpad>/venv/bin:<scratchpad>/tools/node_modules/.bin:/usr/local/bin:/usr/bin:/bin ./scripts/verify.sh` | exit 0，`PASS contracts gate`、`Scaffold verification passed.` |
| 空白 | `git diff --check` | exit 0 |

说明：不带 venv 直接跑 `./scripts/verify.sh` 时，契约门禁因本机系统 Python 没有 `pytest` 失败（B10/B12/B13 契约回归报 `No module named pytest`），属环境问题；把装有后端工具链的 venv 与 `datamodel-codegen` 等工具放进 PATH 后通过。

### 反向篡改（改前 `cp` 备份 `useMaterials.ts`，每次跑完恢复，最后 `cmp` 一致）

| # | 篡改 | 结果 |
| --- | --- | --- |
| S1 | `taskStatusOf` 忽略 `cancel_requested`（不再有「取消中」） | 4 failed |
| S2 | 离开页面不关闭订阅 | 3 failed |
| S3 | 409 不按 `details.stage` 刷新 | 2 failed |
| S4 | 不校验大小 | 2 failed |
| S5 | 不校验格式 | 6 failed |
| S6 | 离开页面不中止在途请求 | 1 failed（首轮只测离开到 `/teacher`，被课程作用域失效掩盖、未检出；已补「回同一课程的课程页」用例后检出） |
| S7 | 上传网络失败不提供重试 | 1 failed |

测试覆盖：API 路径/方法/multipart 字段；格式与大小边界（恰好 50 MiB 可接受、+1 字节拒绝、空文件、伪扩展名）；加载/空/错误/无权限四态与可访问性属性；学生课程内角色不请求列表；415/413（`limit_bytes`）/网络失败重试；上传防重入；订阅使用当前课程作用域；阶段事件与轮询快照更新状态与进度条；取消中 → 已取消、排队中直接已取消、SSE 推来的取消标志、提交中禁用、409 persisting/already_terminal、取消网络失败；任务失败固定文案与同文件重新上传、已取消重新上传；重连/轮询提示与 fatal 后重新连接；路由离开、卸载、切课关闭流并中止请求；路由注册与课程页入口只对课程内教师显示。

未做：没有连真实后端在浏览器里手动操作（只用假接口与假任务流客户端验证；C12 真实客户端的行为由 c12 测试覆盖）。

## 接口 / 数据变更

- 无契约、后端、数据或依赖变更。新增前端路由 `/courses/:cid/materials`（名 `course-materials`）与两个注入键。

## 风险

1. **契约 `Document` 不含 `task_id`**：页面只能跟踪本次会话上传产生的任务；刷新页面后，处理中的历史资料只显示列表中的 `parse_status`，不能订阅进度或取消。若需要，应在契约给 `Document` 加最新任务 ID（归 B/C 组），前端再补订阅。
2. **中止在途上传不等于撤销**：离开页面时中止上传请求，若服务端已收完请求体，资料与任务仍会创建；回到页面后在列表中可见（无进度流，见 1）。
3. 本地 50 MiB 上限是 `UPLOAD_MAX_BYTES` 的默认值；部署若改小，以服务端 413 的 `limit_bytes` 提示为准，若改大则前端会误拒超过 50 MiB 的文件（契约未暴露上限，需时可加配置接口或构建期变量）。
4. 「重新上传」生成新资料行，旧的失败/取消资料行仍保留在列表中（契约无删除资料端点）。

## 待决

1. 是否在契约 `Document` 暴露最新 `task_id`（见风险 1）。
2. 前端上传上限是否需要可配置（见风险 3）。

## 下一步

- K05（教师主线 E2E）可用 `/courses/:cid/materials` 走「上传 → 进度 → 失败重试/取消」。
- H08/H09（审核页）可从资料行的「待审核」状态加入口；审核完成（`completed`）不经处理期连接送达，需要时轮询 `GET /api/v1/tasks/{tid}` 或课程发布状态（`specs/task-processing.md` §7）。

## 回滚

`git revert <H02 提交>`：删除新增的 4 个文件，恢复 `router/index.ts`、`CoursesView.vue`、`main.ts` 的小改动。无迁移、依赖或数据变更。
