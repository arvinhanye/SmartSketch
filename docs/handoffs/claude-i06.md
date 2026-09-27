# 交接：I06 实现掌握标记与推荐 UI

- **任务**：原子清单 I06「实现掌握标记与推荐 UI」（依赖 I05、H11；验收原文「失败撤销乐观标记；切课后旧推荐不覆盖；理由与服务分量一致」）
- **负责人 / 日期**：ArvinHan（Claude），2026-09-27
- **工作区**：worktree `/Users/arvinhan/Desktop/SmartSketch/.worktrees/impl-i06`，分支 `claude/impl-i06`（主仓与其他 worktree 未改动）
- **决策**：ADR-075（`docs/decisions.md`）；任务登记见 `docs/tasks.md`「2026-09-27 I06 掌握标记与推荐 UI」

## 1. 交付物

绝对路径（均在 worktree 内）：

| 文件 | 状态 | 说明 |
| --- | --- | --- |
| `/Users/arvinhan/Desktop/SmartSketch/.worktrees/impl-i06/src/frontend/src/composables/useLearning.ts` | 新建（锁内） | 掌握标记 + 推荐的学生页组合式：乐观写入/回滚、单一在途写入、课程作用域与序号隔离、版本绑定、空态与错误判定、推荐事实展示的纯函数 |
| `.../src/frontend/src/components/Recommendations.vue` | 新建（锁内） | 推荐列表组件：服务端 `reason` 与 `reason_facts`/`weighted` 原样展示、`all_mastered` 空态、加载/失败重试、选中项高亮 |
| `.../tests/frontend/i06.test.ts` | 新建（锁内） | 39 个用例（API 封装、纯函数、组件、组合式与页面） |
| `.../src/frontend/src/api/progress.ts` | 新建（必需扩围） | `createProgressApi(client)`：`GET`/`PUT /api/v1/courses/{cid}/progress` |
| `.../src/frontend/src/api/recommend.ts` | 新建（必需扩围） | `createRecommendApi(client)`：`GET /api/v1/courses/{cid}/recommend` |
| `.../src/frontend/src/views/StudentGraphView.vue` | 小改（必需扩围） | 注入/接线学习接口；画布改用落好状态的图；掌握标记区与推荐区（不可写时无任何可点击入口） |
| `.../src/frontend/src/main.ts` | 小改（必需扩围） | 注入 `PROGRESS_API_KEY`、`RECOMMEND_API_KEY` |
| `.../src/frontend/src/graph/lifecycle.ts` | 小改（必需扩围） | `CanvasElementState` 追加 `mastered`/`learning`/`notStarted`/`recommended` 与样式（颜色只在这一处定义） |
| `.../tests/frontend/h05.test.ts` | 1 个断言扩围 | H05 用「状态名集合完全相等」钉住 `buildGraphOptions` 的 `state` 表，追加四个学习状态后同步扩充该断言（仅测试断言，无实现改动）；H10 亦有同类先例 |
| `.../docs/decisions.md` | 追加 | ADR-075（I06 的写入、版本绑定、理由展示口径） |
| `.../docs/tasks.md` | 追加 | 本任务小节与验收证据 |
| `.../docs/handoffs/claude-i06.md` | 新建 | 本文件 |

未改动：`src/contracts/**`（契约真源与生成物零改动）、后端代码、其它 composable/API 文件、`package.json`（未新增依赖）。

## 2. 接口 / 数据变更

**契约与后端：零变更**（照 `src/contracts/api.v1.yaml` 与 `specs/learning-path.md` 实现）。

新增导出签名：

```ts
// api/progress.ts
export type ProgressEntry / ProgressResponse / ProgressUpdate / ProgressInheritedSource / MasteryStatus
export interface ProgressApi {
  get(cid: string, control?: RequestControl): Promise<ProgressResponse>
  update(cid: string, updates: readonly ProgressUpdate[], control?: RequestControl): Promise<ProgressResponse>
}
export const PROGRESS_API_KEY: InjectionKey<ProgressApi>
export function createProgressApi(client: HttpClient): ProgressApi   // 空批次本地抛 RangeError，不发请求

// api/recommend.ts
export type RecommendResponse / RecommendListResponse / RecommendAllMasteredResponse /
            Recommendation / RecommendFactors / RecommendWeightedFactors / RecommendReasonFacts
export interface RecommendApi { get(cid, query?: RecommendQuery, control?): Promise<RecommendResponse> }
export const RECOMMEND_API_KEY: InjectionKey<RecommendApi>
export function createRecommendApi(client: HttpClient): RecommendApi  // limit 越界本地抛 RangeError

// composables/useLearning.ts
export type LearningStatus = 'idle' | 'loading' | 'not_student' | 'unpublished' | 'ready' | 'error'
export interface LearningNotice { tone: 'success' | 'info' | 'error'; text: string }
export interface ReasonFactRow { key: string; label: string; value: string }
export const MASTERY_LABELS: Readonly<Record<MasteryStatus, string>>
export const PRIMARY_FACTOR_LABELS: Readonly<Record<RecommendReasonFacts['primary_factor'], string>>
export function masteryElementStates(status: MasteryStatus, recommended: boolean): CanvasElementState[]
export function applyLearningStates(graph: GraphCanvasData, entries: ReadonlyMap<string, ProgressEntry>,
                                    recommendedIds: ReadonlySet<string>): GraphCanvasData   // 纯函数，不改输入
export function formatFactor(value: number): string            // 仅展示舍入（4 位小数）
export function reasonFactRows(item: Recommendation): ReasonFactRow[]
export function weightedFactRows(item: Recommendation): ReasonFactRow[]
export function isProgressResponse(value: unknown): value is ProgressResponse
export function isRecommendResponse(value: unknown): value is RecommendResponse
export function hasNotInPublishedVersion(cause: ApiError): boolean
export interface UseLearningOptions {
  progressApi: ProgressApi | null            // 与 recommendApi 任一为 null ⇒ 功能整体不启用（不发请求）
  recommendApi: RecommendApi | null
  courseId: MaybeRefOrGetter<string | null>
  graphVersion: MaybeRefOrGetter<number | null>   // null ⇒ 不读也不写
  ready: MaybeRefOrGetter<boolean>                // 通常是 useStudentGraph().status === 'ready'
  graph?: MaybeRefOrGetter<GraphCanvasData | null> // 筛选后的可见图；提供时组合式给出 learningGraph
  onCourseForbidden?: () => void
  onVersionStale?: () => void                     // 显示版本与服务端不一致 ⇒ 页面重载图谱
}
export function useLearning(options: UseLearningOptions): {
  status, error, retryable,
  entries, recommend, recommendState, recommendations, totalEligible, recommendedIds,
  learningGraph,                        // 落好掌握状态色与推荐高亮的可见图（未启用时原样返回输入）
  recommendError, recommendLoading, busyKpId, notice, versionStale, boundVersion,
  statusOf(kpId): MasteryStatus, isSaving(kpId): boolean,
  setMastery(kpId, status): Promise<void>, reload(): Promise<void>, refreshRecommend(): Promise<void>,
}
```

**页面注入契约（`StudentGraphView.vue`）**：`PROGRESS_API_KEY` 与 `RECOMMEND_API_KEY` 优先注入，缺失时用 `HTTP_CLIENT_KEY` 构造，两者都缺 ⇒ `learningEnabled = false`（不读进度/推荐、不渲染标记与推荐区、`learningGraph` 原样返回筛选结果）。这保证既有 H11 注入集下页面行为不变（`h11.test.ts` 46 passed 未受影响）。

**PUT 请求体的口径（需签收）**：契约的 `updateProgress` 请求体是 `additionalProperties: false` 的 `ProgressUpdate[]`，该操作 `query` 为 `never`，后端 `write_progress` 无版本参数——**验收条目 5 的字面要求（请求带 `graph_version`）与契约冲突**。实现按契约：`PUT` 只发 `[{kp_id, status}]`，版本绑定改为「只在已显示版本上写 + 每条响应 `graph_version` 比对 + 422 `not_in_published_version` 撤销并重读」（ADR-075 决定 2），并有专门用例钉住请求体**不含**自造字段。

## 3. 验证命令与实测输出

全部在 worktree 根目录执行，显式检查 exit code（不经 `| tail`）。

```
$ npm --prefix src/frontend run type-check
> vue-tsc --noEmit -p tsconfig.json && vue-tsc --noEmit -p tsconfig.node.json
EXIT=0

$ npm --prefix src/frontend run test -- --run ../../tests/frontend/i06.test.ts
 ✓ ../../tests/frontend/i06.test.ts (39 tests) 2168ms
 Test Files  1 passed (1)
      Tests  39 passed (39)
EXIT=0

$ npm --prefix src/frontend run build
dist/assets/index-*.js  272.88 kB │ gzip: 92.32 kB
✓ built in 4.63s
EXIT=0
```

- 红灯（TDD 第一步，实现前）：
  ```
   FAIL  ../../tests/frontend/i06.test.ts
  Error: Failed to resolve import "../../src/frontend/src/api/progress" ... Does the file exist?
   Test Files  1 failed (1) / Tests  no tests
  EXIT=1
  ```
- 绿灯：`i06.test.ts` 39 passed（`EXIT=0`）；type-check、build 均 `EXIT=0`。
- 全量前端回归（`npm --prefix src/frontend run test -- --run`）：
  ```
   Test Files  1 failed | 19 passed (20)
        Tests  2 failed | 673 passed (675)
  EXIT=1
  ```
  两个失败都是本机已知 flake `tests/frontend/b02.test.ts`（用嵌套 vitest 进程验证退出码，默认 5s `testTimeout` 超时）；加长超时后全绿：
  ```
  $ npm --prefix src/frontend run test -- --run --testTimeout=30000
   Test Files  20 passed (20)
        Tests  675 passed (675)
  EXIT=0
  ```
- 本轮还同步扩围了 `tests/frontend/h05.test.ts` 的一个断言：H05 用「`options.node.state` 键集合完全相等」钉住 `buildGraphOptions`，I06 在同一张表追加四个学习状态后该断言必然失败（真实回归，非 flake），故把它扩充为包含 `mastered`/`learning`/`notStarted`/`recommended`（仅测试断言，无实现改动；H10 亦有修改 `h09.test.ts` 注入桩的同类先例）。

**过程中修掉的两个真实缺陷（先红后绿）**：
1. `useLearning` 的推荐响应版本不一致路径会形成「重载图 → 进度版本仍不一致 → 再次重载」的**死循环**（首次跑 i06 时整轮挂死、无输出）。修法：`stalePending` 闸门——版本不一致只请页面重载一次，直到某次读到的版本与显示版本一致才复位（ADR-075 决定 2⑤）。
2. `applyLearningStates` 的状态顺序错误（学习状态在后会被筛选/选中状态覆盖），改为「学习状态在前、筛选/选中在后」，并让用例钉住 `['mastered','selected']` 与 `['notStarted','recommended']`。

## 4. 反向篡改矩阵

方法：逐处篡改 → 跑定向用例 → 记录判红用例 → 复原（脚本 `/tmp/i06-tamper-check.py`、`/tmp/i06-tamper-extra.py`，复原后 `git status` 与篡改前一致）。

| # | 篡改 | 判红用例（摘要） | 结果 |
| --- | --- | --- | --- |
| T1 | 失败不回滚乐观标记（删 `entries.value = previous`） | 网络失败完整回滚；4xx 通用失败回滚 | 判红（2） |
| T2 | 切课不校验请求序号（`current()` 去掉 `token === seq`） | — | **未判红（冗余防护）**：`store.commit` 的作用域代次校验同样拦截 |
| T2b | 切课隔离两层（序号 + `store.commit`）同时失效 | 切课后旧推荐不覆盖；切课后旧进度不覆盖；及 11 项页面用例 | 判红（13） |
| T3 | 推荐分数改为前端自算（`weighted` 求和） | 服务端 score 与加权分量不一致时原样展示 | 判红（1） |
| T4/T4b | 乐观标记不带绑定版本（`version` 守卫与「无绑定版本不写」被删，正确命中 `write`） | 无绑定发布版本时不读也不写 | 判红（1，修正锚点后） |
| T5 | 写入响应的发布版本不比对 | 版本不一致不套用到旧图并重载；组合式版本不一致不当作成功 | 判红（2） |
| T6 | 教师 403 不拦 | 教师角色（403 ROLE_FORBIDDEN）不给可点击入口 | 判红（1） |
| T7 | `all_mastered` 当成错误 | 全部掌握是空态不是错误 | 判红（1） |
| T8 | 连点不去重（DOM 层点击） | — | **未判红**：按钮 `disabled` 已阻止第二次点击生效；补组合式级用例后由 T8b 判红 |
| T8b | 连点不去重（直接调用 `setMastery`） | 同一节点在途写入时忽略后续调用（不依赖按钮禁用） | 判红（1） |
| T9 | 状态色硬编码（`masteryElementStates` 固定返回 `mastered`） | 状态映射纯函数；页面状态色与推荐高亮；及 5 项 | 判红（7） |
| T10 | 不做乐观更新（删 `entries.value = optimistic`） | 乐观标记在 PUT 返回前就显示；网络失败回滚 | 判红（2） |
| T11 | 422 `not_in_published_version` 不重读进度（`after='none'`） | 422 撤销乐观状态并重读进度与推荐 | 判红（1） |
| T12 | 完整性错误回显服务端 `message` | 只提示 `request_id`；判定顺序（完整性优先于 `all_mastered`） | 判红（2） |
| T13 | 进度响应形状不校验 | 缺 `entries` 视为异常 | 判红（1） |
| T14 | `PUT` 请求体自造 `graph_version` 字段 | PUT 请求体只有 `kp_id` 与 `status` | 判红（1） |
| T15 | 画布删掉掌握状态样式 | 画布为四个学习状态定义了样式 | 判红（1） |

**结论**：17 处篡改中 15 处判红；2 处单层变异未判红，均已查明原因并补强（T2 → T2b 双层同时失效判红 13 项；T8 → T8b 直接调用 `setMastery` 判红）。没有「测试无鉴别力」的残留。

## 5. 风险与待决

- **需 ArvinHan 签收（ADR-075）**：
  1. 验收条目 5 的「PUT 请求带 `graph_version`」按契约现状无法实现（请求体 `additionalProperties: false`、`query: never`、后端无版本参数），改为「只在已显示版本上读写 + 响应版本比对 + 422 重读」，且**不自造字段**。若要让服务端强制按客户端绑定版本写入，需先扩展契约（新增版本参数）并同步后端，属另开任务。
  2. 学习接口未同时注入时页面**静默**退回 H11 原状（不渲染标记与推荐）。
  3. 掌握标记为三态（未开始/学习中/已掌握）直接写 `MasteryStatus`，不引入第四种状态或「跳过先修但不声称掌握」的操作（`specs/learning-path.md` §2 的越序掌握即「直接标 mastered」）。
- **仅假 API 验证**：本轮未联调真实后端（I02/I05 已在 `main`，但 worktree 未起服务）；`PUT /progress` 的同值写入与继承覆盖语义、`not_in_published_version` 的 `details.graph_version`、完整性错误 500 的真实形状均按契约/后端源码实现，真实联调交 K06 学生主线 E2E。
- **未做**：推荐列表上限未在页面暴露（用服务端默认 10，页面读 `total_eligible` 提示截断）；`inherited_from[]` 未在 UI 展开（契约已具备）；掌握状态未同步到 H11 的卡片视图（`KnowledgeCards.vue` 是 H11 文件，未改动）；无真实浏览器冒烟（未起 G6 真实画布）。
- **已知代价**：客户端只能在响应阶段**事后**发现发布版本变化（契约限制）；弱网下乐观标记会短暂显示后回滚（有固定文案，回滚完整）。
- **下一步（K06 学生主线 E2E 依赖本任务）**：`main.ts` 已注入两个学习接口；K06 需在真实后端上验证「标掌握 → 推荐重算 → 版本变化 → 重新加载」的端到端路径，以及未发布/教师/完整性错误三条分支的真实响应码。
