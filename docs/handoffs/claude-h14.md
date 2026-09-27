# Claude 交接：H14 教师图谱编辑页

- `task_id`: H14（`docs/atomic-tasks.json`「实现教师图谱编辑页」，D-17 补登），issue #281
- `review_status`: merged（PR #285）
- 分支：`claude/project-thread-n5wcl5`；`base_commit`: `f2fbf1e`（origin/main，含集成 PR #283 的 H07/H11）
- 依赖：H05（`useGraphFilters`、`GraphToolbar`）、H06（`KnowledgeDetail`）、H07（`NodeEditor`）、H08（`RelationEditor`、`useRelationEditor`）、H04（`GraphCanvas`）
- 决策：ADR-067
- 断点：上一会话只给 issue 打了 `status:in-progress`，远端无分支/PR、四个允许文件都不存在；本轮从零实现。

## 交付物

| 文件 | 内容 |
| --- | --- |
| `src/frontend/src/views/TeacherGraphView.vue`（文件锁） | 路由页 `/courses/:cid/graph/edit`：加载 / 非教师 / 错误（可重试）/ 空图 / 就绪五态；就绪后工具栏（含审核状态筛选）+ 草稿画布 + 右侧三页签（详情 H06、编辑知识点 H07、编辑关系 H08）；页内未保存确认框（`alertdialog`，获焦点）、页面级提示（删除成功、节点被刷新掉）、刷新中与刷新失败提示；离开路由/换课 `window.confirm`，`beforeunload` |
| `src/frontend/src/composables/useTeacherGraph.ts`（文件锁） | `useTeacherGraph`：课程教师校验、草稿读取（`isDraftOf`：同课程且 `graph_version` 为 null）、写入课程 store、`refresh`（保留画布；在途期间 store 被编辑器写回则重拉）、课程上下文被清空时转错误态；`useSelectionGuard`：有未保存修改时挂起切换 |
| `src/frontend/src/router/index.ts`（文件锁） | `TEACHER_GRAPH_ROUTE`、`teacherGraphComponent` 选项，`meta.accountRole = 'teacher'` |
| `tests/frontend/h14.test.ts`（文件锁） | 42 项：草稿 API 不带 `version`；`isDraftOf`；`useSelectionGuard` 4 项；路由与入口 3 项；加载与状态 10 项（只读草稿、非教师不读、发布版本/错课丢弃、加载、空、网络重试、ROLE_FORBIDDEN、COURSE_FORBIDDEN、换课迟到）；选中联动 5 项（详情↔编辑、保存成功/失败、删除成功/失败）；未保存确认 7 项；连边 3 项（新建、成环拒绝、修订冲突刷新及失败）；审查补充 8 项 |
| `src/frontend/src/api/graph.ts`（**扩围**） | `DraftGraphApi.getDraft(cid)`、`DRAFT_GRAPH_API_KEY`、`createDraftGraphApi` |
| `src/frontend/src/main.ts`、`views/CoursesView.vue`（**扩围**） | 注册页面并注入草稿 API；课程页只对课程内教师显示「编辑课程图谱（草稿）」 |
| `src/frontend/src/components/NodeEditor.vue`（**扩围**，H07 文件） | 仅加 `defineExpose({ dirty })` 一行，供页面判断未保存修改 |
| `docs/decisions.md`、`docs/architecture.md`、`docs/tasks.md` | ADR-067、前端节一行、H14 节 |

## 行为要点

1. **只取草稿、仅课程教师**：路由只放行教师账号；页面在 `my_role !== 'teacher'` 时不读图；读图 `ROLE_FORBIDDEN` 也按非教师；响应不是本课草稿（`graph_version` 非 null 或 `course_id` 不符）即丢弃。
2. **画布同步**：草稿写入课程 store，画布 = `useRelationEditor().canvasData` → `useGraphFilters`。H07 保存/删除、H08 连边成功时写回 store，失败时 store 不变，所以「成功才改画布」由既有编辑器保证，本页不另存副本。
3. **刷新**：编辑器 `refreshNeeded` → `refresh()`，保留当前画布；失败显示提示和「重新刷新」。在途时 store 被写回则丢弃响应并重拉（审查发现的中等问题）。
4. **未保存确认**：换节点或关闭面板 → 页内确认（放弃并切换 / 继续编辑）；节点面板 `v-show` 常驻，切页签不丢修改；「编辑关系」页签下画布点击只用于点选起止点。

## 验证

仓库根目录执行（`npm --prefix src/frontend ci` 后）：

| 步骤 | 命令 | 结果 |
| --- | --- | --- |
| 任务验证 | `npm --prefix src/frontend run type-check && npm --prefix src/frontend run test -- --run ../../tests/frontend/h14.test.ts` | type-check exit 0；42 passed |
| 前端全量 | `npm --prefix src/frontend run test -- --run` | 17 files，587 passed |
| 构建 | `npm --prefix src/frontend run build` | exit 0（仅既有 chunk 体积警告） |
| 门禁 | `PATH=$S/venv/bin:$S/tools/node_modules/.bin:$PATH ./scripts/verify.sh`（`$S` 为 scratchpad；venv 按 `src/contracts/toolchain.txt` **锁定版本**安装，未锁版本的 datamodel-code-generator 0.83 会让生成物比对失败；npm 装 openapi-typescript@7.4.4、typescript@5.9.3） | `PASS contracts gate`、`Scaffold verification passed.` |
| 空白 | `git diff --check` | exit 0 |

## 独立审查（并行子任务）

- 25 处篡改 20 处被检出。未检出 5 处：M11、M12 为等价篡改；M8/M24（换课确认）、M17（刷新迟到）已补用例；M23（取课程后迟到检查）由 store 作用域兜底。
- 问题与处置：①中：刷新在途时写入被旧快照覆盖 → 已修并加用例；②删除后无提示 → 页面级提示；③被拒时强制离开被确认拦住、停在空白页 → 强制离开旁路 + 上下文清空转错误态（旁路本身属纵深防御：上下文清空后面板卸载，dirty 已为 false，故对应篡改不被检出）；④刷新删掉当前节点时静默丢修改 → 提示；⑤确认框无说明、无焦点 → 已补；⑥常驻面板与详情各读一次同一知识点 → 接受，写入 ADR 后果。每项修复都先加失败用例再改实现，并对新修复做了反向篡改（刷新重拉、上下文清空两处均检出）。

## 风险与下一步

- **仅假 API 验证**：后端尚无 `/relations` 路由（H08 已记录），真实环境里「编辑关系」页签的写请求会 404；节点编辑与草稿读取的后端路由已存在但未联调。
- 离开本页不清空课程 store 的草稿图；以后若有页面直接读 `store.graph`，需先按角色重新加载（ADR-067 后果）。
- ADR-067 已由 ArvinHan 2026-09-27 签收。K05 教师主线 E2E 可把本页作为编辑入口。
