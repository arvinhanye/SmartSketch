# 交接：取消演示模式、配置门槛与旧课程重新处理（api-settings gate）

- 日期：2026-10-01
- 分支：`feat/api-settings-page`（HEAD `12bd4f6`，另有上一轮"恢复集成/暖色主题"的未提交改动，见 §3）
- 状态：**功能代码已完成，定向测试与构建通过；实机端到端验证未跑完**（被启动脚本问题挡住，见 §4）
- 下一位接手者首个动作：先解决 §4 的启动脚本问题，再跑 §5 的 5 项实机验证

---

## 1. 本轮任务与已完成内容

任务：API 设置页面与使用门槛改造——面向普通用户，必须配置真实 API 才能使用，不再提供演示模式；旧演示数据不得当作在线数据；文案全部改成用户视角。

### 1.1 页面顶部三行文字已删除

`src/frontend/src/views/ApiSettings.vue` 顶部只保留 `<h2>API 设置</h2>`，删除了：

1. 「当前生效：大模型 在线 · 向量 演示」（原 `statusLine`）
2. 「设置由本机所有课程共用。密钥留空表示保留已保存的密钥，保存后重启软件生效。」
3. 「外部服务要求 HTTPS，本机地址可用 HTTP。先选服务商或填写地址，再获取模型列表并选择模型。」

同时删掉了 `statusLine` 计算属性与对应的 `runtime.llmMode/embeddingMode`（不再有"演示"字样）。这三段文字没有被挪到别处。

### 1.2 取消演示模式（后端真改，不只是删页面文字）

| 位置 | 改动 |
| --- | --- |
| `services/api_settings.py` `save_config` | 强制 `LLM_MODE = "live"`；`EMBEDDING_MODE` 为 demo/fake/空时改为 `"online"`；不再接受演示取值 |
| 同上 `require_complete()`（新增） | 保存入口的完整性校验：六个必需项（大模型地址/Key/模型 + 向量地址/Key/模型）缺一即 400「请选择大模型和向量模型，并填写对应的 API Key。」 |
| 同上 `settings_ready(settings)`（新增） | 本进程是否具备使用条件：`LLM_MODE == "live"` 且 `EMBEDDING_MODE in (online, local)` 且配置齐全 |
| 同上 `missing_requirements()`（新增） | 按用户能看懂的字段名列出缺什么（如「大模型 API Key」「向量模型」） |
| 同上 `config_status(active)`（新增） | 返回 `ready / configured / restart_needed / missing / active`；**只要进程仍在用演示实现，`ready` 即为 false**（即使配置文件已填好），并在 `missing` 里说明"完成设置后重启软件" |
| `api/api_settings.py` | 新增 `GET /api/v1/api-settings/status`；`PUT` 不再返回技术味的 `message`（改为前端按 `restart_needed` 提示） |
| `api/chat.py` | `chat_service()` 先查 `settings_ready`，不通过则抛 `ChatFailure("API_NOT_CONFIGURED")` → **503 +「请先完成 API 设置，再使用智能问答」**，不落回演示模型 |
| `services/qa/chat.py` | 新增失败码 `API_NOT_CONFIGURED` 与其中文文案 |
| `workers/runner.py` | worker 启动**不再**因未配置而崩溃（否则软件起不来）；改为在 `step()` 里调用新增的 `fail_pending_without_api()`：领到任务即以 `API_NOT_CONFIGURED` 置为 failed，不产出任何内容 |
| `config.py` | 未改动（上一轮已恢复 `SMARTSKETCH_API_CONFIG` 加载） |

**保存后生效语义**：本机启动时读一次设置，所以保存成功一律提示「设置已保存，请重启软件后使用。」——由后端 `config_status().restart_needed`（比较配置文件 mtime 与进程启动时间，见 `services/startup_clock.py`）判定，**不再显示虚假的"无需重启"**。

### 1.3 旧演示课程：不当作在线数据，明确的"重新处理资料"

- 新增 `services/course_intelligence.py`：
  - `course_vector_status(settings, course_id)`：读已提交版本的 `embedding_space`（`repositories/versions.current_version`）。`fake/...` → 演示向量；与当前配置不一致 → 空间不同；未发布 → 未发布。任一命中即 `needs_reprocess=true`，文案 `这门课程需要重新处理资料后才能使用智能功能。`
  - `reprocess_course(settings, course_id)`：读取已上传的原文件，走既有 `upload_material` 重新排队（保留资料与图谱），返回 `(task_ids, 资料总数)`
- 新增路由（`api/materials.py` 的 `intelligence_router`，已注册到 `main.py`）：
  - `GET /api/v1/courses/{cid}/intelligence`（教师/本课成员）
  - `POST /api/v1/courses/{cid}/reprocess` → 202 `{task_ids, count}`；无资料 409 `NO_MATERIALS`；文件丢失 409 `REPROCESS_UNAVAILABLE`
- 前端：`api/courses.ts` 增 `intelligence?/reprocess?`（不在生成的契约里，用带令牌的 `fetch` 直连，避免改契约）；`views/CoursesView.vue` 在当前课程卡片内显示提示 + 「重新处理资料」按钮，提交后提示"进度可在「教学资料」中查看"
- **没有**修改数据库里的模型名或维度标记；**没有**自动上传内容、没有执行迁移、没有触发重新向量化
- 注意：演示向量空间是 `fake/<维度>`，真实空间是 `real/<模型>/<维度>`，属性名按空间哈希（`repositories/graph_migrations.vector_property`）。旧数据不会被当成新空间的向量

### 1.4 未完成配置时的引导（登录/退出/设置仍可用）

- 新增 `composables/useConfigStatus.ts`：`refreshConfigStatus(token, force)`（5 秒缓存）、`apiConfigured()`（读不到状态时不拦人）、`requiresConfiguredApi(routeName)`，豁免名单 `['api-settings', 'root', 'register']`
- `router/index.ts` 守卫：教师且目标是需配置的页面且未就绪 → `{ name: 'api-settings', query: { notice: '请先完成 API 设置' } }`；**学生不拦**（学生无权进设置页）
- `main.ts`：`bindConfigStatusToken(() => session.accessToken)`
- `ApiSettings.vue`：进页面时显示 URL 上的 `notice`；保存成功后 `refreshConfigStatus(token, true)` 重新判定并提示重启

### 1.5 文案清理（去开发者表述）

- 密钥状态：`请输入 API Key` / `已保存，留空可保留`
- 按钮：`获取可用模型`；失败文案：`无法获取模型，请检查地址和 API Key，或手动填写模型名称。`
- 向量维度移入 `<details>`「高级设置」，说明只有一句「通常保持默认值即可。」+ 「!」帮助按钮（上一轮已做）
- 设备状态行改为 `当前使用：<模型> · <维度> 维` / `新设置：…`；待处理提示改为「新设置已保存。请在课程页点「重新处理资料」，处理完成后才会使用新的向量。」
- 后端错误按状态码给可照做的提示（401/403 密钥、404 地址或模型、429 额度、5xx 稍后重试、其他被拒绝），不再出现「服务商返回 HTTP …，请核对密钥、地区、模型与额度」「响应缺少 choices」「embeddings/chat-completions」等表述；向量长度不一致改为「该模型返回 N 维，与选择的 M 维不一致，请改选它支持的维度。」
- 页面不再出现：演示、迁移、索引、pending、worker、配置字段、响应结构

---

## 2. 关键决定（接手者不要推翻，除非有意改产品）

1. **完整性校验只在用户保存入口**（`save_for_active_space → require_complete`）。`save_config` 保持宽松，方便工具、脚本与分步保存；`require_complete` 里"首次配置"时把 `EMBEDDING_TARGET_MODEL` 视为已选向量模型。
2. **首次配置引导**：`save_config` 在 `EMBEDDING_MODEL` 为空而 `EMBEDDING_TARGET_MODEL` 有值时，把目标直接作为启用配置（装好重启即可用）；已经有运行时模型时目标只作"待重新处理"。
3. **页面不能直接改写运行中的向量模型/维度**：`save_for_active_space` 拒绝 `EMBEDDING_MODEL`/`EMBEDDING_DIMENSIONS`，提示走「新设置」。
4. **向量空间不一致不再让服务起不来**：原 `validate_embedding_space()` 保持不变（有测试依赖），新增 `check_embedding_space_change()` 返回用户可读说明；`main.py` lifespan 与 `workers/runner.check_startup` 都改用它，只记日志 + 在 `application.state.embedding_space_notice` 留说明。理由：用户必须能打开软件去"重新处理资料"。
5. **worker 永不因未配置而崩溃**：只在处理任务时把该任务置失败。

---

## 3. 改动文件清单

### 3.1 本轮（演示模式/门槛/旧课程/文案）

后端：
- `src/backend/app/services/api_settings.py`（模式、完整性、状态、旧错误文案）
- `src/backend/app/services/course_intelligence.py`（**新增**）
- `src/backend/app/services/startup_clock.py`（**新增**，进程启动时刻）
- `src/backend/app/services/startup.py`（新增 `check_embedding_space_change`）
- `src/backend/app/services/qa/chat.py`（`API_NOT_CONFIGURED`）
- `src/backend/app/api/api_settings.py`（`/status`，去掉技术味 message）
- `src/backend/app/api/chat.py`（未配置即 503）
- `src/backend/app/api/materials.py`（`intelligence_router` 两个端点）
- `src/backend/app/main.py`（注册新路由；lifespan 改用软门禁）
- `src/backend/app/workers/runner.py`（worker 不崩；`fail_pending_without_api`）

前端：
- `src/frontend/src/composables/useConfigStatus.ts`（**新增**）
- `src/frontend/src/router/index.ts`（配置守卫）
- `src/frontend/src/main.ts`（注入令牌读取）
- `src/frontend/src/views/ApiSettings.vue`（删三行、重启提示、文案）
- `src/frontend/src/views/CoursesView.vue`（旧课程提示 + 重新处理）
- `src/frontend/src/api/courses.ts`（`intelligence`/`reprocess`）
- `src/frontend/src/api/apiSettings.ts`（`status()` 与类型）

测试：
- `tests/test_api_settings.py`（28 → 29 项，见 §5）
- `tests/frontend/api-settings.test.ts`（12 项）
- `tests/frontend/i06.test.ts`（「已掌握」描边色断言从 `#52c41a` 改为暖色 `#3f6157`）

发行目录（已同步）：
- `app/src/backend/app/**`：上述后端文件（逐个哈希校验一致）
- `app/web/**`：`index-BKeFOcuk.js` + `index-DHGP-aH1.css`（`index.html` 已引用；旧产物已删）

### 3.2 上一轮已恢复、**尚未提交**的集成与主题（承接上一份进度）

`App.vue`（API 设置入口与选中态）、`router/index.ts`（`/api-settings` 路由 + 教师限制）、`main.py`/`config.py`（注册 + 读取已保存配置）、`styles.css`（暖纸墨色令牌 + `.page`/`.surface-card` 公共类）、`graph/theme.ts`（新增）、`graph/adapter.ts`、`graph/lifecycle.ts`、`AuthLayout.vue`、`LoginView.vue`、`CoursesView.vue`、`MaterialsView.vue`、`MembersView.vue`、`ReviewView.vue`、`ChatView.vue`、`StudentGraphView.vue`、`TeacherGraphView.vue`、`StudentHome.vue`、`TeacherHome.vue`、`ChatMarkdown.vue`、`GraphCanvas.vue`、`GraphToolbar.vue`、`KnowledgeCards.vue`、`KnowledgeDetail.vue`、`NodeEditor.vue`、`Recommendations.vue`、`RelationEditor.vue`、`VersionPanel.vue`、`useRelationEditor.ts`。

> 当前 `git status` 共 50 个条目（含上一轮），**全部未提交**。没有 `git reset`、没有切分支、没有推送。

---

## 4. 未完成项与阻塞（接手者首要动作）

### 4.1 阻塞：便携启动脚本在"Neo4j 迁移"步骤失败

现象（`launcher/start.ps1` 运行到 `Run-Step 'neo4j-migrate'`）：

```
正在启动 Neo4j…
正在sqlite-migrate…
正在neo4j-migrate…
已停止 neo4j。
已停止智绘学途；课程数据仍保存在本机。
```

用启动器相同的环境手工执行同一条命令可复现：

```powershell
& <python> <root>\app\src\backend\portable_bootstrap.py -m app.repositories.graph_migrations
# GraphMigrationError: Neo4j migration connection failed
```

- 位置：`app/src/backend/app/repositories/graph_migrations.py:116`（`run_from_settings`）
- 判断：**Neo4j 端口已 LISTEN 但 bolt 尚未真正可用**（本次实测：端口 19:48:25 开始 LISTEN，日志 19:48:35 "Applied 12 repeatable…" 说明启动器那次其实连通了一次；之后再手工复现是连接被拒）。`Wait-Port 17687` 只等端口，不等 Neo4j "Started."。
- 与我的改动无关：`graph_migrations.py` 本轮未改；同一现象在本轮改动前的前几次重启中也偶发（当时成功）。
- 建议修法（二选一，都在启动脚本侧）：
  1. `Wait-Port` 之后增加"可连接性探测 + 重试"：用 `cypher-shell` 或一个 3 行的 Python 探针（`neo4j` 驱动 `verify_connectivity()`）最多重试 N 次/60 秒；或
  2. 读取 `logs/neo4j.log` 出现 `Started.` 再继续。
- 复现环境：Neo4j 5.26.31 位于 `%LOCALAPPDATA%\SmartSketch-Runtime\neo4j`；配置与数据在 `%LOCALAPPDATA%\SmartSketch-External`。

### 4.2 未跑的实机验证（脚本已写好，见 §5）

`api.log` 最近一次成功运行（19:27）里，以下两项**结果可疑**，需要重跑确认：

- `PUT /api/v1/api-settings`（故意提交不完整配置）当时返回 **200 而不是 400**——当时的服务进程仍是改动前的旧代码（`api.log` 显示 19:27:20 之后 API 退出），需要重启后复测。
- `POST /Courses/…/chat` 与 `GET …/intelligence` 返回 **403 COURSE_FORBIDDEN**，因为我用了错误的课程 ID（`demo-data-structures`）。真实课程 ID 从 `GET /api/v1/courses` 取（演示课程 `ch023…`，见 `import.log` 有 `023ccb97ae1742c6ac69a529d6f364d3`）。

### 4.3 已知未实现（如实报告，不要宣称已可用）

- **「重新处理资料」不会自动切换向量空间**：它只把原资料重新排队，产出新的**草稿**图谱；要真正启用新向量空间仍需发布新版本（发布时按当前配置生成向量），或走既有离线脚本 `scripts/reembed.py`。跨空间迁移本身**本轮没有实现**。
- 未做：把这两个新端点写进 `src/contracts/`（当前用前端直连 fetch 规避契约类型）；`docs/tasks.md` 的任务行与 `docs/decisions.md` 的 ADR（AGENTS.md §5 要求）；`docs/handoffs` 之外的文档更新。
- 未做：全量后端测试、e2e；未调用任何真实模型 API；未改数据库结构与数据。

---

## 5. 已运行的命令与实际结果

| 命令 | 结果 |
| --- | --- |
| `python tests/test_api_settings.py`（经 `tests/.tmp-api-settings` 临时配置目录） | **29 passed**（新增：保存入口完整性、运行字段不可从页面改写、`missing_requirements`、保存后 `restart_needed`、进程仍演示时 `ready=false`、能力表已登记/未登记、请求维度、固定维度不发 `dimensions`、返回长度不一致报错、`list_path` 不被当作未知字段） |
| `npm run type-check`（前端） | exit 0 |
| `npm run build`（前端） | exit 0 产物 `index-BKeFOcuk.js` / `index-DHGP-aH1.css` |
| `npm run test -- --run api-settings` | 12 passed |
| `npm run test -- --run i06` | 39 passed |
| `npm run test -- --run`（全量前端，25 文件） | 776 passed / 1 failed（`i06` 旧冷色断言）→ 修正后 i06 单跑全绿；**全量未重跑** |
| 门禁修复的手工验证 | 用与启动器相同环境手工起 API：`API 存活=True`、`health=200`、stderr 打出 `embedding space differs from existing data; reprocessing required`、`Application startup complete`——**证明门禁不再让 API 退出** |
| 路由注册验证 | `api_settings.router` 含 `/api/v1/api-settings/status`、`/capability`；`materials.intelligence_router` 含 `/api/v1/courses/{cid}/intelligence`、`/reprocess` |

### 待跑（服务起来后）

1. `GET /api/v1/api-settings/status`（教师）：期望 `ready=false`、`missing` 含「向量模型（完成设置后重启软件）」、`configured=true`
2. `PUT /api/v1/api-settings` 提交 `{"LLM_BASE_URL": "https://api.deepseek.com/v1"}`：期望 **400** +「请选择大模型和向量模型，并填写对应的 API Key。」
3. `GET /api/v1/api-settings`：教师 200 / 学生 403 / 未登录 401（**设置页始终可访问**）
4. `GET /api/v1/courses` 取真实课程 ID → `GET …/intelligence`：期望 `needs_reprocess=true`、`embedding_space="fake/1024"`
5. `POST …/chat`（未配好）：期望 **503 + `API_NOT_CONFIGURED` +「请先完成 API 设置，再使用智能问答」**，而不是演示回答

现成脚本：`%TEMP%\sk_verify_gate.js`（Node，用法 `node "%TEMP%\sk_verify_gate.js"`，环境变量 `SK_BASE` 可改地址）。

---

## 6. 当前机器状态（接手前请知悉）

- **Neo4j 正在运行**（17687 LISTEN，`%LOCALAPPDATA%\SmartSketch-External\logs\neo4j.log` 有 `Started.`）——是我为排障手工起的后台进程，不是启动器管理的；**API(18080) 与 worker 未运行**。
- 真实配置文件：`launcher/api-settings.json`（`LLM_MODE=live`、`EMBEDDING_MODE=demo`、`EMBEDDING_MODEL=text-embedding-v4`、密钥 DPAPI 加密）。**进程内**运行时配置由启动脚本的环境变量给（`LLM_MODE=demo`、`EMBEDDING_MODE=demo`，见 `start.ps1:149-150`），配置文件覆盖环境变量后为 `live/demo`——这正是 §1.2 中"进程仍演示 → ready=false"的真实场景。**未读取、未回显、未修改任何密钥。**
- 数据库（SQLite `%LOCALAPPDATA%\SmartSketch-External\smartsketch.sqlite3`）里记录的空间仍是 `smartsketch-demo-ngram-v1/1024`（演示向量），没有改过。**未执行迁移、未重新导入课程、未重建向量。**
- 启动（等 §4.1 修好后）：`launcher/start.ps1`；停止：`launcher/stop.ps1` 或 `停止智绘学途.cmd`。

---

## 7. 建议的接手顺序

1. 修 §4.1（启动脚本等 Neo4j 真正就绪），确保 `launcher/start.ps1` 能起全栈。
2. 跑 §5 的 5 项实机验证（脚本已就绪）；把结果补进本文件或新建 `codex-*.md`。
3. 决定产品细节：`require_complete` 是否允许"先只配大模型、后配向量"的分步保存（当前**不允许**，必须一次配齐六项）。
4. 若接受，把 §4.3 的"重新处理资料 → 发布后启用新空间"补成完整闭环（本轮的实现只到"重新排队生成草稿"）。
5. 提交前补 `docs/tasks.md` 任务行与 `docs/decisions.md` ADR（记录"不再提供演示模式"取代 ADR-076 的演示选择）。
