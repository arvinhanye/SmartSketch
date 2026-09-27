# Claude 交接：H07 教师节点编辑面板

- `task_id`: H07（`docs/atomic-tasks.json`「实现教师节点编辑面板」），issue #119
- `review_status`: ready_for_review
- 分支：`claude/project-thread-130wun`；`base_commit`: `main@a7d8075`
- 依赖：H06（详情接口与迟到隔离模式）、F08（PATCH/解锁，ADR-035）、F09（删除，ADR-048），均已合并
- 决策：ADR-062（协调者预分配编号）

## 交付物

| 文件 | 内容 |
| --- | --- |
| `src/frontend/src/components/NodeEditor.vue`（文件锁） | 编辑面板：props `kpId`；事件 `saved(kp)`、`deleted(kpId)`、`refreshNeeded`、`close`、`courseForbidden`。空/加载/就绪/不存在/已删除各态；字段标签、`aria-invalid`、`aria-describedby` 关联错误；表单错误 `role=alert`、成功 `role=status`；冲突差异表与「采用最新内容 / 保留我的修改并重新保存」；锁状态与「解锁」；删除二次确认（`role=alertdialog`）；Esc/关闭按钮发 `close`；无 `v-html` |
| `src/frontend/src/composables/useNodeEditor.ts`（文件锁） | 纯函数 `parseAliases`、`toForm`、`diffForm`、`readConflict`；`useNodeEditor({ api, kpId, onSaved?, onDeleted?, onRefreshNeeded?, onCourseForbidden? })` → 状态、`form`、`dirty`、`locked`、`canSave`、`fieldErrors`、`error`、`notice`、`conflict`、`stale` 与 `save`/`unlock`/`remove`/`acceptTheirs`/`keepMine`/`dismissConflict`/`discard`/`reload` |
| `tests/frontend/h07.test.ts`（文件锁） | 56 项：API 路径/方法/请求体/查询参数、表单差异与校验、冲突详情解析、加载与迟到隔离、保存（成功写回图谱并锁定、本地/服务端字段错误、COURSE_BUSY/ROLE_FORBIDDEN/500、网络与超时不确定、响应不符、404、并发与切换、COURSE_FORBIDDEN）、冲突三种处理、锁与解锁（含冲突、响应不符、仍锁定）、删除（成功、冲突、404、网络）、组件交互与可访问性、XSS、HTTP 客户端回退 |
| `src/frontend/src/api/nodeEdit.ts`（**扩围**，新建） | `NODE_EDIT_API_KEY`、`createNodeEditApi`：`get`/`update`/`unlock`/`remove`（删除带 `expected_revision` 查询参数） |
| `docs/decisions.md`、`docs/tasks.md`（**扩围**） | 末尾追加 ADR-062 与 H07 任务记录 |

未改：契约、后端、`main.ts`、路由与页面。面板**未**接入页面；挂载页由新补登的 H14「实现教师图谱编辑页」负责（D-17）；H11 是学生端浏览页，不挂本面板。

## 行为要点（ADR-062）

1. 不做乐观更新；只有服务端确认且响应 `id`/`course_id` 相符才更新基准、写回 store 图谱、提示成功。失败保留表单并写明未保存/未解锁/未删除；网络与超时写明「不能确认」并给「重新加载节点」。
2. 只提交改过的字段；名称、定义不能为空；重要度、难度 0～1，已有值不能清空。
3. 保存冲突列出逐字段差异，阻止再次保存直到选择；「保留我的修改」以 `current_revision` 重新提交，未改字段跟随最新内容。
4. 一次一个写请求；切换知识点/课程中止在途请求并丢弃晚到结果。

## 验证

仓库根执行；`S` 为 scratchpad，`$S/venv` 按 `pip install -e "src/backend[test]" 'datamodel-code-generator==0.26.3'`，`$S/tools` 内 `npm i openapi-typescript@7.4.4`。

| 步骤 | 命令 | 结果 |
| --- | --- | --- |
| 依赖 | `(cd src/frontend && npm ci)` | exit 0 |
| 单测 | `npm --prefix src/frontend run test -- --run ../../tests/frontend/h07.test.ts` | 56 passed。首轮 3 failed：其中「保留我的修改」会把他人改的类型/状态改回去，是实现缺陷，已修（`rebase` 只保留教师改过的字段）；另一项是测试替身写错 |
| 类型检查 | `npm --prefix src/frontend run type-check` | exit 0 |
| 前端全量 | `npm --prefix src/frontend run test -- --run` | 15 files，494 passed |
| 构建 | `npm --prefix src/frontend run build` | exit 0 |
| 门禁 | `env PATH=$S/venv/bin:$S/tools/node_modules/.bin:$PATH ./scripts/verify.sh` | `PASS contracts gate`、`Scaffold verification passed.` |
| 空白 | `git diff --check` | 无输出 |

反向篡改 25 处（`$S/mut.py` 逐项替换、跑 h07、还原），全部使测试失败：不丢弃晚到保存结果、不带读到的修订号、保留我的修改时回退他人修改、不校验保存响应、本地字段错误仍提交、冲突未处理可直接保存、允许并发写、冲突不展示差异、网络失败假装成功、解锁/删除冲突不载入最新、删除/保存不写回图谱、422 不落到字段、编辑后不清服务端错误、未锁定也解锁、解锁不校验响应*、服务端仍锁定仍提示解锁、404 假装删除成功、404 不请求刷新、删除不带修订号、确认区显示时仍显示删除按钮*、确认按钮不删除、删除不经确认、错误不关联 `aria-describedby`。（* 首轮存活，补用例后检出）

## 接口 / 数据变更

无契约、后端、依赖或迁移变更。前端新增 `api/nodeEdit.ts` 与注入键 `NODE_EDIT_API_KEY`。

## 风险

- 真实后端未联调（本机无 Neo4j 服务）；接口形状按生成的 OpenAPI 类型检查，F08/F09 行为按其交接与契约描述。
- `details.current` 不含章节，「采用最新内容」时章节沿用本地值。
- 保存成功后节点被锁定是后端既定行为（ADR-035），面板只提示，不自动解锁。

## 待决

1. ADR-062 签收。
2. 已按 ArvinHan 选择补登 H14 教师图谱编辑页（D-17），K05 增加对 H14 的依赖；H14 待认领。

## 下一步

- H14：`<NodeEditor :kp-id="selected" @saved="…" @deleted="selected = null" @refresh-needed="重新加载草稿图谱" @close="selected = null" @course-forbidden="回课程列表" />`；如需统一注入，在 `main.ts` provide `NODE_EDIT_API_KEY: createNodeEditApi(http)`。

## 回滚

`git revert <本任务提交>`，或删除上表四个前端文件、ADR-062 与任务记录；无数据迁移或依赖变更。
