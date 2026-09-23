# 功能规格：身份、课程成员与访问边界

- **状态**：DRAFT（本文决定已由 ArvinHan 于 2026-09-23 签收，见 ADR-013）
- **负责人**：产品/协调 Agent 维护；后端、前端、测试 Agent 共同消费
- **关联任务**：A05；消费方 B03、B08、B09、B10、C02、C03、C04、C07、C10、C11、C12、F07、G06、H01、I02、J07、K06、K09
- **规范地位**：本文是**访问矩阵与身份规则的唯一规范表述**。`src/contracts/errors.v1.md` 对 `UNAUTHENTICATED`、`COURSE_FORBIDDEN`、`ROLE_FORBIDDEN` 的说明，以及 OpenAPI 各操作的 `summary` 里「（教师）」「（学生）」字样，都以本文为准；不一致时回改契约，不改本文。取值与大小写以 `docs/architecture.md`「API 前缀与 wire 枚举」为准。

## 范围

本文确定：账号与登录方式、访问令牌、调用者身份的唯一来源、课程成员模型、授权判定顺序与错误语义、全部端点的访问矩阵、SSE 事件票据。

本文**不**确定（写明去向，避免被当作已决）：

| 事项 | 去向 |
| --- | --- |
| 学生读取的是哪个发布版本、请求内如何绑定 `version_id` | A04 |
| 教师读草稿还是读发布版的参数形态 | A04 / B11 |
| `kp/{kid}/material`（学习材料加分项）的放行规则 | O01；未批准前不实现，本文不放行 |
| 进度写入时 `kp_id` 是否属于本课程已发布版本 | A08 / I02 |
| 新增环境变量登记到 `.env.example` 与 `docs/integrations.md` | A07 或 C03（见 §6） |
| 口令哈希库、JWT 库的选型与版本锁 | C03 |

**明确不做**（不扩展生产 SSO）：单点登录、OAuth/OIDC、LDAP、开放注册、邮箱找回或自助改密、多因素认证、刷新令牌、服务端注销与令牌黑名单、管理后台界面。

## 术语

- **账号类型**：`users.role ∈ {teacher, student}`。只决定两件事：登录后的默认首页，以及能否新建课程。**不参与任何课程内授权。**
- **课程内角色**：`course_members.role ∈ {teacher, student}`。课程内一切授权只看它，每次请求回查数据库。
- **成员**：在 `course_members` 中存在 `(course_id, user_id)` 行的用户。
- **调用者身份**：服务端从已验证的访问令牌（或已核销的事件票据）得到的 `user_id`。**这是唯一来源。**
- **访问令牌**：`POST /api/v1/auth/login` 签发的 JWT，放在 `Authorization: Bearer` 头里。
- **事件票据**：为订阅某一个任务的 SSE 单独申领、一次性、≤60 秒的不透明随机串（§5）。

## 1. 账号与登录

### 1.1 账号数据

表 `users`（ADR-008 命名基线已含）：

| 字段 | 约束 |
| --- | --- |
| `id` | 随机不透明字符串（如 UUID），不得用自增整数，避免被枚举 |
| `username` | 3～32 位，字符集 `[a-z0-9_.-]`；入库前转小写，唯一 |
| `password_hash` | 慢哈希结果（§1.4），不存明文 |
| `role` | 账号类型，`teacher` 或 `student`；MVP 不支持修改 |
| `created_at` | 创建时间 |
| `disabled_at` | 非空即已停用；停用不删除行，以保住进度、问答、编辑日志的外键 |

### 1.2 账号来源

- **没有注册端点。** 契约中不得出现创建用户的操作。
- 账号由后端命令行创建、停用、启用、重置口令；协作教师也由命令行加入课程（§3.3）。
- 演示账号由幂等种子脚本创建：至少一个教师账号、两个学生账号（两个学生用于演示进度互不可见；用户名建议 `demo_teacher`、`demo_student`、`demo_student2`，K09 可调整）。
  - 口令读环境变量 `SEED_DEMO_PASSWORD`；**未设置时脚本非 0 退出**，不得回退到写在仓库里的默认口令。
  - 重跑不重复创建、不重置已有账号的口令。

### 1.3 登录

`POST /api/v1/auth/login`，请求 `{username, password}`，成功返回 `LoginResponse`（`access_token`、`token_type: bearer`、`expires_in`、`user`）。

1. `username` 转小写后查找。
2. 用户不存在、已停用、口令错误，三种情况返回**完全相同**的 401 `UNAUTHENTICATED`（状态码、错误码、`message` 一致）。用户不存在时仍对一个固定的假哈希执行一次校验，使耗时相近，防止按响应时间探测用户名。
3. **失败限流**：同一用户名（转小写后）连续失败 5 次，之后 60 秒内对该用户名的登录一律返回 429 `RATE_LIMITED`，不再校验口令；成功登录清零计数。
   - 计数放在 API 进程内存，以用户名字符串为键，**对不存在的用户名同样计数**，否则「会被限流」本身就泄露了用户名是否存在。计数表要有容量上限（例如最多 1 万个键，按最久未用淘汰）。
   - 多进程部署时各进程分别计数，只是缓解手段，不作为安全保证。
4. 登录请求与响应中的口令、令牌不得写入日志。

### 1.4 口令存储

- 用 argon2id（首选）或 bcrypt 慢哈希，库与参数由 C03 选定并锁版本。
- 口令长度 8～128 个字符。若选 bcrypt，超过 72 字节的口令必须拒绝，**不得静默截断**。

## 2. 访问令牌与调用者身份

### 2.1 令牌格式

- JWT，算法**固定** HS256；校验时拒绝 `alg: none` 及任何其他算法。
- 载荷只有 `sub`（用户 `id`）、`role`（账号类型）、`iat`、`exp` 四项，缺任何一项即视为无效令牌。
- `role` 只供前端决定默认首页，**服务端不得据此做任何授权**（契约 `bearerAuth` 的说明随 B08 改为这层意思）。
- 密钥读环境变量 `AUTH_JWT_SECRET`，至少 32 字节；缺失或过短时服务**拒绝启动**，不得回退到默认密钥。
- 有效期读 `AUTH_ACCESS_TOKEN_TTL_SECONDS`，默认 28800（8 小时）。无刷新令牌，过期后重新登录。

### 2.2 每次请求的身份校验

1. 取 `Authorization: Bearer <jwt>`；缺失、签名不符、算法不符、过期 → 401。
2. 按 `sub` 回查 `users`；不存在或 `disabled_at` 非空 → 401。
3. 通过后，本次请求的调用者身份就是这个 `user_id`，账号类型取数据库中的 `users.role`，不取令牌里的 `role`。

因为每次都回查，命令行停用账号后该用户的**下一次请求**即被拒绝，不需要令牌黑名单。注销只由前端丢弃令牌完成。

### 2.3 不可信输入：禁止仅相信请求中的 user_id

- 服务端**不得**从请求体、查询参数、路径或任何自定义请求头（如 `X-User-Id`、`X-Role`）读取「调用者是谁」或「调用者是什么角色」。
- 契约中作用于调用者本人数据的请求 schema（进度、问答等）**不得**定义表示调用者的 `user_id` 字段；运行时客户端即使多传了这类字段，也只能被忽略，不得影响写入对象。
- 进度、问答记录、编辑日志、成员 `added_by` 等写入的 `user_id` 一律取自调用者身份。
- 成员管理中的用户名或 `uid` 表示**被操作的对象**，不是调用者身份，不受本条限制，但同样要经 §4 授权。

### 2.4 前端持有令牌

- 令牌与 `LoginResponse.user` 只存 `sessionStorage`，不存 `localStorage`，不写 Cookie。这样同一浏览器的不同标签页可以分别登录教师与学生账号，便于演示对照。
- 前端不解析 JWT 做授权判断。路由守卫只用 `user.role` 选默认首页，用 `Course.my_role` 选课程视图；这些都只是界面引导，不当作后端鉴权（B03 验收）。
- 收到 401 清除令牌并跳登录页；收到 `COURSE_FORBIDDEN` 回课程列表（`errors.v1.md` 已约定）。

## 3. 课程成员

### 3.1 数据

表 `course_members`（ADR-008 命名基线已含）：

| 字段 | 约束 |
| --- | --- |
| `course_id` | 外键 → `courses` |
| `user_id` | 外键 → `users` |
| `role` | 课程内角色，`teacher` 或 `student` |
| `added_by` | 执行添加的用户 `id`；命令行添加时为空 |
| `created_at` | 加入时间 |

主键 `(course_id, user_id)`：同一用户在同一课程只有一个角色；在不同课程的角色互不影响。

### 3.2 约束

1. **学生账号只能做学生成员。** 写入 `role = teacher` 的成员行时，服务层必须确认该用户账号类型为 `teacher`，否则拒绝（C02 验收）。教师账号可以在别的课程做学生成员，比如旁听或预览学生视角。
2. **新建课程**：只有账号类型为 `teacher` 的用户可以新建；课程行与「创建者为 `teacher` 成员」的成员行在**同一事务**写入（C04 验收）。
3. `courses.teacher_id` 记录创建者，只用于展示，**不参与授权**；课程内教师权限只看成员行。
4. 每门课程至少有一个教师成员。MVP 不开放任何删除或降级教师成员的 API，因此这条不变量只需在命令行工具里守住。

### 3.3 成员管理

| 操作 | 规则 |
| --- | --- |
| 列出成员 | 课程教师成员可用；返回 `user_id`、`username`、`role`、`created_at` |
| 添加学生 | 课程教师成员按用户名添加，新成员角色固定为 `student`。用户名不存在或账号已停用 → 404 `NOT_FOUND`。**已是成员（任意角色）→ 200 返回现有成员行，不改角色**；新加入 → 201 |
| 移除成员 | 课程教师成员可用，只能移除**学生**成员 → 204。目标是教师成员（包括自己）→ 403 `ROLE_FORBIDDEN`，成员关系不变；目标不是成员 → 404 `NOT_FOUND` |
| 协作教师 | MVP 只能通过命令行加入或移除，API 不提供 |

学生被移除后，其进度与问答记录**保留**但不可访问；重新加入后恢复可见。

## 4. 授权判定

### 4.1 判定顺序

每个受保护的请求按以下顺序判定，**先失败者决定响应**：

1. **身份**：按 §2.2 → 失败 401 `UNAUTHENTICATED`。
2. **定位课程**：路径带 `cid` 时取 `cid`；路径只有 `tid` 时按任务回查其 `course_id`，任务不存在 → 404 `NOT_FOUND`。
3. **成员关系**：查 `(course_id, 调用者)` 的成员行。
   - 不是成员，或 `cid` 对应的课程根本不存在：路径带 `cid` 时返回 403 `COURSE_FORBIDDEN`；按 `tid` 定位时返回 404 `NOT_FOUND`，与任务不存在无法区分，响应中不含任何任务快照字段。
4. **课程内角色**：矩阵要求的角色与成员行的 `role` 不符 → 403 `ROLE_FORBIDDEN`。
5. **发布状态**：学生成员访问从未发布过的课程 → 404 `GRAPH_NOT_PUBLISHED`。
6. **子资源作用域**：`kid`、`rid`、`version` 等一律在该 `course_id` 范围内查找（仓储层强制），查不到 → 404 `NOT_FOUND`。

不走上述流程的只有两类：`POST /courses` 在第 1 步之后只检查账号类型（非 `teacher` → 403 `ROLE_FORBIDDEN`）；`GET /courses` 在第 1 步之后按 §4.4 过滤，不会返回 403。

**为什么课程级给 403，任务级给 404**：非成员拿到课程 ID 有正当途径，比如被移出课程后打开旧链接，此时明确提示「无权限，回课程列表」对用户更有用；课程 ID 是随机串，不存在的课程也同样返回 403，所以 403 不会泄露课程是否存在。非成员则没有任何正当途径拿到 `tid`，返回 404 不给探测任务是否存在的机会（A03 TASK-19）。

### 4.2 错误语义汇总

| 情形 | 响应 |
| --- | --- |
| 缺令牌、签名或算法不符、过期、用户不存在或已停用 | 401 `UNAUTHENTICATED` |
| 登录口令错误、用户名不存在或账号已停用 | 401 `UNAUTHENTICATED`（与上一行同形） |
| 登录连续失败达到上限 | 429 `RATE_LIMITED` |
| 路径带 `cid`，调用者不是成员，或课程不存在 | 403 `COURSE_FORBIDDEN` |
| 是成员但课程内角色不符；学生账号新建课程；移除教师成员 | 403 `ROLE_FORBIDDEN` |
| 学生成员访问从未发布的课程 | 404 `GRAPH_NOT_PUBLISHED` |
| 按 `tid` 定位，任务不存在或调用者不是其课程成员 | 404 `NOT_FOUND` |
| 子资源不在该课程内；添加成员时用户名不存在或账号已停用 | 404 `NOT_FOUND` |
| 事件票据缺失、无效、过期、已用、与任务不符 | 401 `UNAUTHENTICATED` |

不新增错误码；以上错误码均已在 `ErrorCode` 中。

### 4.3 访问矩阵

记号：✓ 放行；COURSE = 403 `COURSE_FORBIDDEN`；ROLE = 403 `ROLE_FORBIDDEN`；404 = 404 `NOT_FOUND`；「未发布 404」= 学生成员访问从未发布的课程时 404 `GRAPH_NOT_PUBLISHED`。「非成员」指已登录但不是该课成员。学生成员的读取一律只读已发布版本（具体版本绑定归 A04）。带 * 的是本文新增、需 B09/B10 补进契约的操作。每行对应契约中的一个操作，C03 可直接据此写参数化测试。

| operationId | 方法与路径 | 匿名 | 非成员 | 学生成员 | 教师成员 |
| --- | --- | --- | --- | --- | --- |
| `getHealth` | `GET /health` | ✓ | ✓ | ✓ | ✓ |
| `login` | `POST /api/v1/auth/login` | ✓ | ✓ | ✓ | ✓ |
| `listCourses` | `GET /api/v1/courses` | 401 | ✓（§4.4 过滤） | ✓（§4.4 过滤） | ✓（§4.4 过滤） |
| `createCourse` | `POST /api/v1/courses` | 401 | 账号类型 `teacher` 才放行，否则 ROLE | — | — |
| `getCourse` | `GET /api/v1/courses/{cid}` | 401 | COURSE | ✓（未发布 404） | ✓ |
| `listMembers` * | `GET /api/v1/courses/{cid}/members` | 401 | COURSE | ROLE | ✓ |
| `addMember` * | `POST /api/v1/courses/{cid}/members` | 401 | COURSE | ROLE | ✓（§3.3） |
| `removeMember` * | `DELETE /api/v1/courses/{cid}/members/{uid}` | 401 | COURSE | ROLE | ✓（仅学生成员） |
| `listDocuments` | `GET /api/v1/courses/{cid}/documents` | 401 | COURSE | ROLE | ✓ |
| `uploadDocument` | `POST /api/v1/courses/{cid}/documents` | 401 | COURSE | ROLE | ✓ |
| `getTask` | `GET /api/v1/tasks/{tid}` | 401 | 404 | ROLE | ✓ |
| `issueEventTicket` * | `POST /api/v1/tasks/{tid}/event-ticket` | 401 | 404 | ROLE | ✓ |
| `streamTaskEvents` | `GET /api/v1/tasks/{tid}/events` | 401（票据，§5） | 404 | ROLE | ✓ |
| `cancelTask` | `POST /api/v1/tasks/{tid}/cancel` | 401 | 404 | ROLE | ✓ |
| `getGraph` | `GET /api/v1/courses/{cid}/graph` | 401 | COURSE | ✓ 只读已发布（未发布 404） | ✓ |
| `listKnowledgePoints` | `GET /api/v1/courses/{cid}/kp` | 401 | COURSE | ✓ 只读已发布（未发布 404） | ✓ |
| `createKnowledgePoint` | `POST /api/v1/courses/{cid}/kp` | 401 | COURSE | ROLE | ✓ |
| `getKnowledgePoint` | `GET /api/v1/courses/{cid}/kp/{kid}` | 401 | COURSE | ✓ 只读已发布（未发布 404） | ✓ |
| `updateKnowledgePoint` | `PATCH /api/v1/courses/{cid}/kp/{kid}` | 401 | COURSE | ROLE | ✓ |
| `deleteKnowledgePoint` | `DELETE /api/v1/courses/{cid}/kp/{kid}` | 401 | COURSE | ROLE | ✓ |
| `mergeKnowledgePoints` | `POST /api/v1/courses/{cid}/kp/merge` | 401 | COURSE | ROLE | ✓ |
| `generateStudyMaterial` | `POST /api/v1/courses/{cid}/kp/{kid}/material` | 按 O01 另定；未批准前不实现 | | | |
| `createRelation` | `POST /api/v1/courses/{cid}/relations` | 401 | COURSE | ROLE | ✓ |
| `updateRelation` | `PATCH /api/v1/courses/{cid}/relations/{rid}` | 401 | COURSE | ROLE | ✓ |
| `deleteRelation` | `DELETE /api/v1/courses/{cid}/relations/{rid}` | 401 | COURSE | ROLE | ✓ |
| `getReviewQueue` | `GET /api/v1/courses/{cid}/review` | 401 | COURSE | ROLE | ✓ |
| `publishGraph` | `POST /api/v1/courses/{cid}/publish` | 401 | COURSE | ROLE | ✓ |
| `listVersions` | `GET /api/v1/courses/{cid}/versions` | 401 | COURSE | ROLE | ✓ |
| `rollbackVersion` | `POST /api/v1/courses/{cid}/versions/{version}/rollback` | 401 | COURSE | ROLE | ✓ |
| `getProgress` | `GET /api/v1/courses/{cid}/progress` | 401 | COURSE | ✓ 仅本人（未发布 404） | ROLE |
| `updateProgress` | `PUT /api/v1/courses/{cid}/progress` | 401 | COURSE | ✓ 仅本人（未发布 404） | ROLE |
| `getRecommendations` | `GET /api/v1/courses/{cid}/recommend` | 401 | COURSE | ✓ 仅本人（未发布 404） | ROLE |
| `chat` | `POST /api/v1/courses/{cid}/chat` | 401 | COURSE | ✓（未发布 404） | ROLE |

**教师成员不开放** `progress`、`recommend`、`chat`（ArvinHan 2026-09-23 确认），也就是教师不能在问答里预先检验效果；日后放开只改这三行。

### 4.4 课程列表可见性

`GET /api/v1/courses` 返回调用者是成员的课程，但**学生成员身份的课程只在曾经发布过之后才出现**（`published_version` 非空）。每项带 `my_role`（调用者在该课的课程内角色）。前端据此决定打开教师视图还是学生视图：教师账号在别的课里的学生成员身份，会进入学生视图。

## 5. SSE 事件票据

浏览器原生 `EventSource` 不能设置请求头，所以任务进度流不能用 Bearer 头鉴权。常规访问令牌**绝不**放进 URL；改用一次性票据（Codex S07-R07，A03 移交）。

### 5.1 申领

`POST /api/v1/tasks/{tid}/event-ticket`，Bearer 鉴权，授权同其他任务操作（该任务所在课程的教师成员）。返回 200 `{ticket, expires_in}`：

- `ticket`：至少 128 位的密码学随机数，URL 安全编码。
- `expires_in`：秒，固定为 60，不可配置到更长。
- 服务端只存 `sha256(ticket)`，不存明文。表 `event_tickets(ticket_hash 主键, user_id, task_id, expires_at, used_at, created_at)`；申领时顺带删除过期超过 1 小时的旧行。

### 5.2 连接

`GET /api/v1/tasks/{tid}/events?ticket=<ticket>`，该操作在契约中**覆盖全局 `bearerAuth`**，改用查询参数方案。

1. 用一条条件更新核销：`UPDATE event_tickets SET used_at = 现在 WHERE ticket_hash = ? AND task_id = ? AND used_at IS NULL AND expires_at > 现在`。影响 0 行（票据不存在、已用、过期、与路径 `tid` 不符）→ 401 `UNAUTHENTICATED`。
2. 核销成功后，以票据记录的 `user_id` 作为调用者身份，先确认账号未停用（否则 401），再**重新执行 §4.1 第 2～4 步**，结果同矩阵 `streamTaskEvents` 行：已不是该课程成员 → 404 `NOT_FOUND`，课程内角色已不是教师 → 403 `ROLE_FORBIDDEN`。全部通过才开流。
3. 查询参数中出现常规访问令牌（无论参数名是 `ticket` 还是 `token`）都不会通过第 1 步；此端点也不读取 `Authorization` 头。
4. 断线重连按 A03 约定：前端出错即关闭连接、重新申领票据、再建连；不依赖 `EventSource` 自动重连（自动重连会携带已用票据，必然 401）。

参数名用 `ticket` 而不是 `events.v1.md` §1 现写的 `token`，以免与 Bearer 令牌混淆；`events.v1.md` 的措辞由 B10 同批修改。

### 5.3 边界

- 开流后不再复查成员关系。教师在连接期间被移出课程，已打开的流继续到关流为止；A03 规定处理完成（`awaiting_review`）即关流，影响时长有限。
- 问答是 `fetch` 发起的 POST 流，可以正常带 `Authorization` 头，不使用票据。

## 6. 配置项

| 变量 | 必需 | 默认 | 说明 |
| --- | --- | --- | --- |
| `AUTH_JWT_SECRET` | 是 | 无 | ≥32 字节；缺失或过短则服务拒绝启动 |
| `AUTH_ACCESS_TOKEN_TTL_SECONDS` | 否 | 28800 | 访问令牌有效期 |
| `SEED_DEMO_PASSWORD` | 仅运行种子脚本时 | 无 | 演示账号口令；未设置则种子脚本非 0 退出 |

登录限流（5 次 / 60 秒）与票据有效期（60 秒）是固定常量，不做成配置。变量名只在此登记；写入 `.env.example`（仅变量名与无敏感示例值）与 `docs/integrations.md` 由 A07 或 C03 完成。

## 7. 契约改动清单（交 B08 / B09 / B10）

契约真源 `api.v1.yaml` 尚未进入 main（ADR-004，待 A10 导入），本任务不改契约。以下是本文对契约的全部要求，按 ADR-004 第 5 条「先改真源再生成」执行：

| 负责 | 改动 |
| --- | --- |
| B08（已完成） | `securitySchemes.bearerAuth` 的说明改为「`role` 仅作前端路由提示，服务端不据此授权」；所有继承 `bearerAuth` 的操作补 `401` 响应；新增 `eventTicket` 方案（`type: apiKey`、`in: query`、`name: ticket`） |
| B09（已完成） | `Course` 增加必填 `my_role`（`$ref: Role`）；`listCourses` 描述改为 §4.4；`login` 补 `429`；`getCourse` 的 `404` 说明加 `GRAPH_NOT_PUBLISHED`；新增 `listMembers`、`addMember`、`removeMember` 三个操作，`CourseMember`、`MemberAdd` 两个 schema，参数 `uid` |
| B10 | 新增 `issueEventTicket` 操作与 `EventTicket` schema（`ticket`、`expires_in`）；`streamTaskEvents` 声明 `security: [{eventTicket: []}]` 覆盖全局，并显式声明查询参数 `ticket`；`events.v1.md` §1 的 `token` 改为 `ticket` 并指向本文 §5；任务类操作的 `403` 说明改为仅 `ROLE_FORBIDDEN`，非成员走 `404` |

## 8. 验收

编号 IAM-*，括号内为承接实现与测试的任务。

- 成功路径
  - **IAM-1**（C03）演示教师用正确口令登录 → 200，`token_type = bearer`，令牌 `sub` 等于该用户 `id`；随后用该令牌 `GET /courses` → 200。
  - **IAM-2**（C04）教师新建课程 → 201，`my_role = teacher`；数据库中课程行与创建者的 `teacher` 成员行同时存在。人为让成员行写入失败 → 课程行也不存在。
  - **IAM-3**（C04 + 成员 API）教师按用户名添加学生 → 201。课程未发布时该学生 `GET /courses` 不含此课；发布后出现，且 `my_role = student`。
  - **IAM-4**（I02、J07、F07）学生成员读已发布图谱、写本人进度、提问 → 均 200；进度行的 `user_id` 等于令牌 `sub`。
  - **IAM-5**（C02、C03）教师账号 U 是课程 A 的教师成员、课程 B 的学生成员：U 在 A 编辑知识点 → 200；在 B 编辑 → 403 `ROLE_FORBIDDEN`；在 B 写进度 → 200。令牌中的 `role = teacher` 对 B 的判定没有影响。
  - **IAM-6**（C11、C12）教师申领票据后用它连接 → 开流，首条为任务当前快照。
- 边界路径
  - **IAM-7**（C03）用 `Demo_Teacher` 登录与用 `demo_teacher` 登录结果相同。
  - **IAM-8**（成员 API）重复添加已是学生成员的用户 → 200，成员行不变；添加已是教师成员的用户 → 200，角色仍为 `teacher`。
  - **IAM-9**（C03）学生被移出课程后，用仍在有效期内的旧令牌访问该课 → 403 `COURSE_FORBIDDEN`；重新加入后原进度可见。
  - **IAM-10**（C03）命令行停用账号后，该账号用旧令牌的下一次请求 → 401；再登录 → 401，与口令错误同形。
  - **IAM-11**（C03、F07）学生成员访问从未发布的课程：`GET /courses/{cid}` → 404 `GRAPH_NOT_PUBLISHED`；调用教师端操作 → 403 `ROLE_FORBIDDEN`（角色判定先于发布状态）。
  - **IAM-12**（C03、I02、J07）教师成员调用 `progress`、`recommend`、`chat` → 403 `ROLE_FORBIDDEN`。
  - **IAM-13**（C11）票据申领 60 秒后才连接 → 401。
- 失败路径
  - **IAM-14**（I02、C03）学生 A 在 `PUT /progress` 请求体中夹带 `user_id = B`，或加请求头 `X-User-Id: B` → 只改动 A 的进度，B 的进度逐字节不变。
  - **IAM-15**（C03）篡改令牌载荷（`sub` 换成他人、`role` 改为 `teacher`）但沿用原签名 → 401；`alg: none` → 401；用别的密钥签名 → 401；已过期 → 401；不带令牌 → 401。
  - **IAM-16**（C03、C04）已登录的非成员访问 `GET /courses/{cid}` → 403 `COURSE_FORBIDDEN`；访问不存在的 `cid` → 同样 403，响应体结构相同。
  - **IAM-17**（F07、C03）课程 A 的教师用 `/courses/A/kp/{kid}` 读、改、删课程 B 的知识点 → 404 `NOT_FOUND`，B 的数据不变。
  - **IAM-18**（C10、C11，即 A03 TASK-19）课程 B 的教师对课程 A 的任务执行查询、取消、申领票据 → 均为 404 `NOT_FOUND`，响应体不含任何任务快照字段，与不存在的 `tid` 无法区分。
  - **IAM-19**（C04、成员 API）学生账号 `POST /courses` → 403 `ROLE_FORBIDDEN`；学生成员添加或移除成员 → 403 `ROLE_FORBIDDEN`。
  - **IAM-20**（成员 API）教师移除教师成员（包括移除自己）→ 403 `ROLE_FORBIDDEN`，成员关系不变。
  - **IAM-21**（C03）不存在的用户名与存在的用户名配错误口令 → 状态码、错误码、`message` 完全相同；两者连续失败 5 次后的第 6 次都返回 429。
  - **IAM-22**（C11）SSE：把访问令牌放进 `?ticket=` 或 `?token=` → 401；只带 `Authorization` 头不带票据 → 401；同一票据第二次连接 → 401；为任务 T1 申领的票据连接 T2 → 401；申领后、连接前该教师被移出课程 → 404。
  - **IAM-23**（C03）`AUTH_JWT_SECRET` 缺失或短于 32 字节 → 服务启动失败并非 0 退出，不以默认密钥运行。
  - **IAM-24**（C02）试图为学生账号写入 `role = teacher` 的成员行（包括经命令行）→ 拒绝，数据库无变化。
  - **IAM-25**（B09）契约中不存在任何创建用户的操作；任何请求 schema 都没有表示调用者身份的 `user_id` 字段。
