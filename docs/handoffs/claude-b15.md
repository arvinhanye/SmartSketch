# Claude 交接：B15 建立前端 HTTP 客户端

- `task_id`: B15
- `review_status`: ready_for_review
- `worktree`: `/home/user/wt-b15-http-client`（分支 `claude/b15-http-client`）
- `base_commit`: `9116315`（第三批认领提交）
- `head_commit`: 见本分支提交（未 push：本会话 GitHub 写权限被拒，由协调方推送并开 PR）
- 父任务：M0-02。`docs/tasks.md` 第 68 行 M0-02 仍写「B15 待 B14」，本任务未改该行，由协调方在集成时更新。

## 交付物

| 文件 | 内容 |
| --- | --- |
| `src/frontend/src/api/http.ts`（新增） | 类型化 HTTP 客户端 `createHttpClient`、路径构造 `apiPath`、错误类层次 |
| `tests/frontend/b15.test.ts`（新增） | 23 个用例（含 1 个纯类型用例），全部用注入的假 fetch，不发真实网络 |
| `docs/handoffs/claude-b15.md`（新增） | 本文件 |
| `docs/tasks.md` | 仅第三批 B15 行的状态与证据列 |

未改 `package.json`、锁文件、配置、store、router、`main.ts`；无新依赖。

## API 形状

```ts
const http = createHttpClient({
  fetch?,              // 默认 globalThis.fetch；测试注入
  baseUrl?,            // API 源，默认 '' 即同源
  getAccessToken?,     // () => string | null | undefined，每次请求读取
  onUnauthenticated?,  // (error: ApiError | InvalidResponseError) => void，非公开接口 401 时调用
  timeoutMs?,          // 默认 30_000，覆盖发起到读完响应体
})

const scope = useCourseStore().beginRequest()
const graph = await http.request('get', '/api/v1/courses/{cid}/graph', {
  params: { cid: scope.courseId },           // 按模板占位符编码替换
  query: { relation_types: ['PREREQUISITE'] }, // 契约 query 类型；数组重复键
  signal: scope.signal,                       // 与超时合并后传给 fetch
})                                            // 类型为 GraphExchange
if (store.setGraph(scope, graph)) { /* … */ }
```

- **路径**：`ApiPath` = 契约 `paths` 中 `/api/v1/...` 的键（`/health` 不经本客户端）。`apiPath(template, params)` 逐段 `encodeURIComponent`，拒绝缺失、空串、`.`、`..`（防止浏览器归一化到别的资源）。`/api/v1` 字面值只在 `API_PREFIX` 出现一次。
- **类型推导**：方法限于该路径在契约中声明的；`params` 的键取模板占位符、值类型取契约（路径级与操作级参数合并，如 `members/{uid}` 的 `uid` 只声明在 `delete` 上）；`query`/`body` 取操作定义，`multipart/form-data` 映射为 `FormData`；返回值为 2xx 的 `application/json` 体，204 为 `undefined`。
- **请求**：总带 `Accept: application/json`（问答 `chat` 因此走 JSON 模式）；JSON 体带 `Content-Type: application/json`；`FormData` 不设 `Content-Type`。
- **认证**：令牌只进 `Authorization: Bearer`。契约 `security: []` 的 `/api/v1/auth/login` 不带令牌、401 不触发回调（口令错误不是会话失效）。
- **错误**（均继承 `HttpClientError`，可按 `kind` 或 `instanceof` 分支）：

| 类 | `kind` | 何时 | 字段 |
| --- | --- | --- | --- |
| `ApiError` | `api` | 错误体符合契约 `Error`（`code` 在 `ErrorCode` 闭集内、`message` 为字符串、`details` 缺省或为对象） | `status`、`code`、`message`、`details`、`retryAfterSeconds` |
| `InvalidResponseError` | `invalid_response` | 错误体不是 JSON 或不符合 `Error`；2xx（非 204/205）体为空或不是 JSON | `status` |
| `NetworkError` | `network` | fetch 拒绝或读体中断，且非本客户端中止 | `cause` |
| `TimeoutError` | `timeout` | 超时（含读体阶段） | `timeoutMs` |
| `AbortedError` | `aborted` | 外部 signal 中止（用户取消、切课），含调用前已中止（此时不发请求） | `cause` |

## 决定与理由

- **不依赖 `AbortSignal.any`**：自建 `AbortController`，外部 signal 的 `abort` 事件转发过来，计时器触发时置超时标记再中止；结束时清计时器并移除监听，不泄漏。先发生者决定错误类型。
- **读体阶段也受超时/取消约束**：`readText` 与 signal 竞速，避免响应头到达后体卡住时请求永不结束。
- **ErrorCode 运行时副本**：契约生成物只有类型，校验错误体需要值列表。`http.ts` 内的 `ERROR_CODES` 用 `satisfies readonly ErrorCode[]` 加反向 `Exclude` 断言与契约双向一致——契约增删码时 `type-check` 失败，须同步。
- **401 回调异常不覆盖原错误**：回调抛出时经 `queueMicrotask` 异步上报，调用方仍收到原 401 错误。
- **401 与错误体无关**：非 JSON 的 401（如网关）同样调用回调，按规格「收到 401 清除令牌」。

## 实际验证（Node v22.22.2，Linux）

| 命令 | 结果 |
| --- | --- |
| `npm --prefix src/frontend ci --no-audit --no-fund` | exit 0 |
| 实现前 `npm --prefix src/frontend run test -- --run ../../tests/frontend/b15.test.ts`（RED） | exit 1，`Failed to resolve import "../../src/frontend/src/api/http"` |
| `npm --prefix src/frontend run type-check && npm --prefix src/frontend run test -- --run ../../tests/frontend/b15.test.ts` | exit 0，1 file / 23 passed |
| `npm --prefix src/frontend run test -- --run`（全量） | exit 0，4 files / 53 passed |
| `npm --prefix src/frontend run build` | exit 0 |
| `PATH=<venv>/bin:$PATH ./scripts/verify.sh` | exit 1：`test_b14.py` 2 例失败，原因是本机缺 `openapi-typescript`；未改动的基线 `9116315` 上同样失败，与本任务无关 |
| 同上，另把临时装在会话 scratchpad（仓库外）的 `openapi-typescript@7.4.4` 加入 PATH | exit 0（`PASS contracts gate`、`Scaffold verification passed.`），生成物无漂移 |
| `git diff --check`（新文件 `git add -N` 后） | exit 0 |
| `git status` | 仅本任务文件；`node_modules`、`dist` 被忽略，未提交 |

类型用例：`@ts-expect-error` 覆盖契约外路径、`/health`、缺路径参数、路径不支持的方法、契约外查询参数；并断言 `getGraph` 返回 `GraphExchange`、`removeMember` 返回 `undefined`。`type-check` 通过即说明这些错误确实被类型系统拦截。

反向篡改（改前 `cp` 备份，跑 B15 测试后恢复并 `cmp` 一致）：

| 篡改 | 结果 |
| --- | --- |
| 不把 signal 传给 fetch | 4 failed（外部中止、超时、覆盖超时、B04 切课联动） |
| 401 不调用回调 | 2 failed |
| 超时与取消混为 `AbortedError` | 3 failed（超时、覆盖超时、读体超时） |
| 错误体不解析，一律 `InvalidResponseError` | 4 failed |
| 令牌进 URL 查询串 | 3 failed |
| 登录 401 也调用回调 | 1 failed |
| 路径参数不编码 | 1 failed |

## 接口、配置与风险

- 无 REST/SSE 契约、数据模型、依赖或环境变量变化。
- SSE（任务进度 `events`、问答流）不经本客户端；其票据走查询串是契约规定的 `eventTicket`，不是访问令牌。
- 调用方必须把 `scope.signal` 传进来，网络层取消才生效；晚到响应仍需经 store 的 `setGraph`/`commit` 丢弃。
- 模块级没有单例：`createHttpClient` 需在应用入口创建并注入（H13 接线），否则令牌与 401 回调都为空。

## 待决（未自行拍板，均为保守可逆实现）

1. **API 源地址**：`baseUrl` 默认同源 `''`。开发时前端（Vite）与后端（:8000）不同源，需要 Vite 代理 `/api` 或 `VITE_API_BASE_URL` 环境变量——都要改配置/`.env.example`/`docs/integrations.md`，不在本任务文件锁内。
2. **默认超时 30 秒**：问答 JSON 模式或上传大文件可能更久；目前由调用方按请求传 `timeoutMs`。是否按端点设默认值待定。
3. **2xx 空体**：除 204/205 外视为 `InvalidResponseError`，不以 `undefined` 冒充数据。若后端某些 200/202 允许空体，需要在契约里改为 204 或放宽。
4. **未知错误码**：契约称 `ErrorCode` 为闭集，因此不在枚举内的 `code` 归为 `InvalidResponseError`（HTTP 状态仍保留）。若后端先于前端加码，前端会显示通用错误而非具体提示。
5. **`Retry-After`**：只解析整数秒；HTTP 日期形式返回 `undefined`。
6. **公开接口清单**：`PUBLIC_PATHS` 手写 `/api/v1/auth/login`，对应契约 `security: []`；生成的 `.d.ts` 不含 `security`，契约新增公开接口时需同步。
7. **契约观察**：`/api/v1/courses/{cid}/members/{uid}` 的 `uid` 声明在操作级而非路径级，生成类型的路径级 `parameters.path` 只有 `cid`。客户端已按模板占位符合并两处，无需改契约；记录供后端知悉。
8. **M0-02 行**：`docs/tasks.md` 第 68 行「B15 待 B14」已过时，请协调方更新。

## 下一步

- **H13**：在 `main.ts` 创建客户端，`getAccessToken` 读 `sessionStorage` 中的令牌，`onUnauthenticated` 清会话、重置课程上下文（B04-R01）并导航到登录页；登录用 `http.request('post', '/api/v1/auth/login', { body })`，401 以 `ApiError.code === 'UNAUTHENTICATED'` 提示口令错误。
- **H01/H02 等 composables**：通过注入（provide/inject 或参数）拿到客户端，`beginRequest()` 后把 `scope.signal` 和 `params: { cid: scope.courseId }` 交给 `request`，结果经 store 提交；按 `error.kind` 区分 `aborted`（静默）、`timeout`/`network`（可重试提示）、`api`（按 `code` 走 `errors.v1.md` 的前端处理）。
- `COURSE_FORBIDDEN` 回课程列表不在客户端内处理，由调用方或 H13 的全局处理决定。
