# Claude 交接：H06 知识点详情和来源浏览

- `task_id`: H06（`docs/atomic-tasks.json`「实现知识点详情和来源浏览」）
- `review_status`: ready_for_review
- 分支：`task/h06`（本地，未 push）；`base_commit`: `ddae1ed`（`main@0b8aa73` + 第九批认领）
- `head_commit`: 本交接所在提交
- 依赖：H04（`GraphCanvas` 的 `nodeClick(kpId)`）、F07（`getKnowledgePoint`，ADR-030）、H03（适配层节点只带 `kpId`，定义与来源由详情接口取）
- 决策：ADR-051（预分配编号）

## 交付物

| 文件 | 内容 |
| --- | --- |
| `src/frontend/src/components/KnowledgeDetail.vue`（文件锁） | 详情抽屉：props `kpId: string \| null`、`documentNames?`；事件 `locateSource(SourceLocation)`、`selectKnowledgePoint(kpId)`、`close`、`courseForbidden`。空/加载（`role=status`、`aria-busy`）/错误（`role=alert`，可重试时给重试按钮）/就绪四态；就绪后焦点移到标题；Esc 与关闭按钮发 `close`；标题、各小节有 `aria-labelledby`（ID 用 `useId()`，多实例不冲突）。全部文本插值渲染，无 `v-html` |
| `src/frontend/src/composables/useKnowledgeDetail.ts`（文件锁） | `toSourceView` / `toKnowledgeDetailView`（纯函数视图模型）、`highlightSegments`（字面量切分高亮）、`useKnowledgeDetail({ api, kpId, onCourseForbidden? })` → `{ status, detail, error, retryable, activeSourceKey, retry, locate }` |
| `tests/frontend/h06.test.ts`（文件锁） | 47 项：API 路径编码与令牌、来源视图（有效/无效页码、空白章节、身份不完整、重复键、不改输入）、高亮、迟到请求 10 项（快速切换、旧响应先到、迟到失败、A→B→A、切课、响应不符、卸载、取消选择、未选课程、COURSE_FORBIDDEN）、组件 18 项（四态、可访问名称、焦点、关系跳转、来源定位与 `aria-pressed`、未知资料名、丢弃计数、全部不可定位、高亮、XSS、404/未发布/网络重试、Esc 关闭、切换只显示最新、切换清除当前来源、HTTP 客户端回退） |
| `src/frontend/src/api/knowledgeDetail.ts`（**扩围**，新建） | 只封装 `GET /api/v1/courses/{cid}/kp/{kid}`；`KNOWLEDGE_DETAIL_API_KEY`、`createKnowledgeDetailApi`。按任务说明新建自己的文件，未改共享 API 文件 |
| `docs/decisions.md`（**扩围**） | 末尾追加 ADR-051 |

未改：`main.ts`（组件未注入专用 API 时用 `HTTP_CLIENT_KEY` 的会话客户端构造）、路由、页面、契约、`docs/tasks.md`。组件**未**接入任何路由页面（留给 H11）。

## 行为要点（ADR-051）

1. 来源只展示可定位的：`document_id`/`chunk_id` 非空且（页码为正整数 或 章节路径非空）；无效页码但章节有效时只显示章节。其余丢弃并提示「另有 N 条来源缺少页码和章节，未显示」；全部不可定位时提示且无定位按钮。不补页码/章节/原文；资料名缺失时显示「资料 <document_id>」。
2. 点击来源发出 `locateSource({ documentId, chunkId, page?, sectionPath? })`（缺的键不出现）并标记 `aria-pressed`；原文阅读器由页面实现。
3. 迟到隔离：序号 + 上一请求 `abort` + 课程作用域；`id`/`course_id` 与请求不符按数据异常不展示；课程变而选择不变回到空态；卸载即中止。
4. 错误文案固定，不回显服务端 message：`NOT_FOUND`「不存在或已被删除」、`GRAPH_NOT_PUBLISHED`「尚未发布」（均不可重试）；网络/超时「无法连接服务器」、5xx 与数据异常可重试；401「登录已失效」；`COURSE_FORBIDDEN` 发 `courseForbidden`。

## 验证

仓库根（worktree）执行；`node_modules` 为指向主仓库的软链（未提交）。

| 步骤 | 命令 | 结果 |
| --- | --- | --- |
| 红灯 | `npm --prefix src/frontend run test -- --run ../../tests/frontend/h06.test.ts`（仅测试） | 无法解析 `api/knowledgeDetail`，`Tests no tests` |
| 绿灯 | 同上 | 47 passed |
| 类型检查 | `npm --prefix src/frontend run type-check` | exit 0（含 `tests/frontend`） |
| 前端全量 | `npm --prefix src/frontend run test -- --run` | 12 files，359 passed（基线 312 + 47）。首次运行 `b02` 一项因机器负载 5 s 超时失败，单独重跑 5 passed、全量重跑 359 passed |
| 构建 | `npm --prefix src/frontend run build` | exit 0（组件尚未被页面引用） |
| 门禁 | `env PATH=$S/venv/bin:$S/tools-f10/bin:$S/tools-f10/node_modules/.bin:/usr/bin:/bin ./scripts/verify.sh`（`$S` 为 scratchpad，工具目录含 `openapi-typescript`） | 通过（`PASS contracts gate`、`Scaffold verification passed.`） |
| 空白 | `git diff --check` | 通过 |

反向篡改 16 处（`$S/h06mut/run.py` 自动逐项篡改、跑 h06、还原并 `filecmp` 校验一致），全部使测试失败：

| # | 篡改 | 失败数 |
| --- | --- | --- |
| 1 | 写入前不比对请求序号 | 5 |
| 2 | 新选择不中止上一请求 | 3 |
| 3 | 不校验响应 `id`/`course_id` | 1 |
| 4 | 接受页码 0 | 3 |
| 5 | 接受空白章节 | 3 |
| 6 | 页码章节皆无也保留 | 10 |
| 7 | 卸载不中止请求 | 1 |
| 8 | 404 可重试 | 1 |
| 9 | 高亮取最短词 | 1 |
| 10 | 定位不标记当前来源 | 1 |
| 11 | 定义改 `v-html` | 1 |
| 12 | 不发 `courseForbidden` | 1 |
| 13 | 不提示丢弃条数 | 1 |
| 14 | 就绪不移焦点 | 1 |
| 15 | Esc 不关闭 | 1 |
| 16 | 未知资料名伪造成 `.pdf` 文件名 | 1 |

未测到的等价变异：切换节点时不清 `activeSourceKey`——来源键含 `chunk_id`，不同知识点的键本就不同；两个知识点共享同一块时才可见，仍保留重置。

## 接口 / 数据变更

无契约、后端、依赖或迁移变更。前端新增 `api/knowledgeDetail.ts` 与注入键 `KNOWLEDGE_DETAIL_API_KEY`。

## 风险

- 契约无资料名，页面需自行提供 `documentNames`（教师可用 `listDocuments`；学生目前没有可读资料名的接口）。
- 已发布版本来源无原文片段（ADR-033），学生端只能看到页码/章节。
- 画布不可键盘操作；详情抽屉可键盘操作，但从画布进入详情仍靠鼠标（H04 待决，H11 卡片视图承担）。

## 待决

1. 原文阅读器/定位跳转的落点（PDF 页跳转、Markdown 章节锚点）未定，本组件只发事件。
2. 学生端资料名来源：是否给学生开放资料名只读接口或在 `SourceRef` 加 `document_name`（需改契约）。
3. 默认视觉为占位，未经设计签收。

## 下一步

- H11（或图谱页任务）：`<GraphCanvas @node-click="id => selected = id" />` + `<KnowledgeDetail :kp-id="selected" :document-names="names" @select-knowledge-point="id => selected = id" @locate-source="openSource" @close="selected = null" @course-forbidden="回课程列表" />`；如需在 `main.ts` 统一注入，provide `KNOWLEDGE_DETAIL_API_KEY: createKnowledgeDetailApi(http)`。
- `docs/tasks.md` 证据由协调者汇总。

## 回滚

`git revert <本任务提交>`，或删除上表四个前端文件、`tests/frontend/h06.test.ts` 与 ADR-051；无数据迁移或依赖变更。
