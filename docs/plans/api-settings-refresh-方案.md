# API 设置页改造技术方案（可交付给 Codex 实施）

> 目标分支：`codex/api-settings`（当前 HEAD `827ca31`）
> 文档状态：方案 + 已撤销的实现要点（本文档不含任何生效代码改动）
> 编写日期：2026-10-01
> 相关文件：`src/frontend/src/views/ApiSettings.vue`、`src/frontend/src/api/apiSettings.ts`、
> `src/backend/app/api/api_settings.py`、`src/backend/app/services/api_settings.py`

---

## 1. 需求（用户原话拆解）

| # | 需求 | 验收要点 |
| --- | --- | --- |
| R1 | 两个 API 能**单独测试** | 两块互不阻塞：A 在测时 B 仍可点；状态、结果互不串台 |
| R2 | 测试结果放**小窗口** | 弹层显示：成功/失败、**往返延迟 ms**、HTTP 状态、使用的模型、失败原因 |
| R3 | **换配色**，不要"AI 味" | 去掉青蓝 `#1c6e8c` + 浅蓝灰 `#f5f7f9` 组合；本次用户选定 **暖纸墨色**，范围**仅本页** |
| R4 | 不写死厂商，模型可选 | 文案去掉 `DeepSeek`/`通义`；模型名不再预置 `deepseek-chat`、`text-embedding-v4` |
| R5 | 聊天模型**从 API 自动识别**并以下拉选择 | `GET {base}/models` 拉取 → 下拉/可输入；失败可手动填写 |
| R6 | 向量模型同理 | 同一机制；向量模型名从列表中筛出，仍允许手动输入 |

补充确认（用户已选）：
- 配色：**A 暖纸墨色**；作用范围：**只改 API 设置页**（不影响其它页面）。
- 模型选项：**自动识别为主 + 常用服务商快捷预设为辅**（预设只填 `base_url`，不写死模型名）。

---

## 2. 现状分析（`827ca31`）

后端 `services/api_settings.py`：

- `FIELDS` 含 10 个键，`SECRETS = {LLM_API_KEY, EMBEDDING_API_KEY}`（DPAPI 加密落盘，永不回显）。
- `DEFAULTS` **写死了厂商与模型**：`LLM_BASE_URL=https://api.deepseek.com/v1`、`LLM_CHAT_MODEL=deepseek-chat`、
  `EMBEDDING_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1`、`EMBEDDING_MODEL=text-embedding-v4`。
- `validate_config`：字段白名单；`EMBEDDING_DIMENSIONS` 必须为 1024；`*_BASE_URL` 必须 **https**。
- `save_config`：`DEFAULTS | read_config()` 合并；`*_API_KEY` 为空则跳过（保留旧值）；在线模式必须有 key 与模型名。
- `test_settings(body)`：只做一次请求，**失败 raise ValueError**（接口层再转 400），**不返回延迟**，成功只回
  `{"message": "连接成功"}`；向量维度硬校验 1024。
- 没有"列出模型"能力。

后端 `api/api_settings.py`：`GET ""`、`PUT ""`、`POST "/test"`（`teacher_account` 依赖，学生 403，未登录 401）。

前端 `views/ApiSettings.vue`：

- 单文件 80 行；两个 `<fieldset>`；**共用一个 `busy` / `message` / `failed`** → 点一个测试另一个也被禁用；
  结果只有页面顶部一行文字，无延迟、无弹窗。
- `legend` 与按钮文案硬编码"大模型 · DeepSeek""向量模型 · 通义"；模型名是普通 `<input>`，无候选列表。
- `<style scoped>` 依赖全局令牌（青蓝主色）。

前端 `api/apiSettings.ts`：`read/save/test` 三个方法，`test` 只期望 `{message}`。

---

## 3. 目标接口契约

### 3.1 新增：列出可用模型

```
POST /api/v1/api-settings/models      （教师权限）
body: { kind: "llm" | "embedding", LLM_BASE_URL?, LLM_API_KEY?, EMBEDDING_BASE_URL?, EMBEDDING_API_KEY? }
```

请求逻辑：
1. 取地址与密钥：**请求体里刚填的优先，其次已保存的**；
2. `base_url` 规范化：去掉尾部 `/`；**path 为空时自动补 `/v1`**；
3. `GET {base}/models`，`Authorization: Bearer <key>`，`timeout=20s`，`perf_counter()` 计时；
4. 解析兼容两种返回：
   - OpenAI 风格 `{"data":[{"id":"..."}]}`
   - Ollama 风格 `{"models":[{"name":"..."}]}`（也兼容 `data` 为 `{"models":[...]}` 的包裹）
5. `kind=embedding` 时优先保留名字含 `embed|bge|gte|m3e|text-similarity|rerank` 的项，全空则保留原列表。

响应（**失败也返回 200**，由页面小窗口展示原因）：

```json
{ "kind": "llm", "ok": true, "models": ["..."], "count": 12,
  "latency_ms": 321.5, "provider": "api.deepseek.com", "error": null }
```

错误分支的 `error` 文案：`请先填写 API 地址` / `请先填写 API Key` /
`服务商返回 HTTP 401，请核对密钥、地区、模型与额度` / `连接失败，请检查网络、API 地址与证书` /
`服务商响应不是 JSON，请确认 API 地址` / `该地址未返回任何模型名称，请手动输入模型名`。

### 3.2 改写：连接测试

```
POST /api/v1/api-settings/test        （教师权限）
body: { kind: "llm" | "embedding", ...同上，另含 *_CHAT_MODEL / *_MODEL }
```

- 请求体：`llm` → `POST {base}/chat/completions`，`{model, messages:[{role:user,content:"Reply OK"}], max_tokens:5}`；
  `embedding` → `POST {base}/embeddings`，`{model, input:["连接测试"], dimensions:1024}`。
- 模型取值优先级：**请求里填的 → 已保存的 → （llm 专用回退）`LLM_EXTRACTION_MODEL`**；
  都为空时返回 `请先获取并选择一个模型，或手动填写模型名`（不再静默用默认模型）。
- 响应（**不抛 400 当失败**）：

```json
{ "kind": "llm", "ok": true, "latency_ms": 480.5, "http_status": null,
  "detail": { "model": "deepseek-chat" }, "provider": "api.deepseek.com", "error": null }
```

- `embedding` 成功时 `detail.dimensions = len(data[0].embedding)`（**不再硬编码 1024 校验**，维度以实际返回为准并展示）；
- `llm` 成功时 `detail.model` 取服务商回显的 `choices[0].model`，便于确认实际路由到的模型；
- 只有 `kind` 非法（非 `llm|embedding`）才返回 400 `VALIDATION_ERROR`。

---

## 4. 前端改造设计

### 4.1 组件拆分

```
src/frontend/src/
├─ api/apiSettings.ts                     # 扩展类型与方法（见 4.4）
├─ components/ConnectionResultDialog.vue  # 新增：结果小窗口
└─ views/ApiSettings.vue                  # 重构：两块独立 + 模型下拉 + 服务商预设 + 暖纸墨色
```

`ConnectionResultDialog.vue`（props：`open / title / pending / elapsed / result`，emit：`close`）：

- 用 `<Teleport to="body">` 渲染遮罩 + 面板（宽度约 `22rem`，比页面窄，符合"小窗口"）；
- 内容：状态（`测试中…` / `连接成功` / `连接失败`）、**往返延迟**（等宽字体，pending 时显示已耗时秒数）、
  接口主机名、使用模型、向量维度（有则显示）、HTTP 状态（有则显示）、失败原因（红框）、
  脚注"延迟为本机进程到服务商的完整往返时间；测试只发送一次最小请求"；
- 关闭方式：关闭按钮、点击遮罩、ESC；`role="dialog" aria-modal="true"`。

### 4.2 页面状态机（关键：两块完全独立）

```ts
const testing = reactive({ llm: false, embedding: false })          // 各自 pending
const results = reactive<{ llm: ConnectionResult | null; embedding: ConnectionResult | null }>(...)
const dialog  = reactive({ kind: null as 'llm' | 'embedding' | null, elapsed: 0 })
const discovery = reactive({
  llm:       { models: [] as string[], count: 0, done: false, error: '', latency: null, busy: false },
  embedding: { models: [] as string[], count: 0, done: false, error: '', latency: null, busy: false },
})
const dialogPending = computed(() => dialog.kind !== null && testing[dialog.kind])
const dialogResult  = computed(() => (dialog.kind ? results[dialog.kind] : null))
const dialogTitle   = computed(() => (dialog.kind === 'embedding' ? '向量模型接口' : '大模型接口'))
```

- 点"测试连接"：仅置 `testing[kind] = true`、打开对应 `dialog.kind`、`setInterval(100ms)` 刷新已耗时；
  拿到响应后清 interval，`dialog` 保持打开显示结果 → **另一个接口全程不受影响**。
- 测试成功后，若该块还没有模型列表，顺带触发一次 `discover(kind)` 补齐下拉。

### 4.3 模型下拉与"合法输入"

- 候选来源：`list = [...new Set([当前值, 已保存值, 接口识别结果])]`；
- 控件：`<input :list="datalistId">` + `<datalist>` —— 既能下拉选择，也能直接输入任意模型名
  （覆盖 `/models` 不支持、私有网关改名等情况）；
- 每块一个「获取模型列表」按钮；结果提示：`识别到 N 个模型（321 ms），可直接下拉选择或手动输入其他名称`；
- 常用服务商**只填地址**的预设胶囊（模型名一律来自识别）：

| 标签 | base_url |
| --- | --- |
| DeepSeek | `https://api.deepseek.com/v1` |
| 阿里云百炼（通义） | `https://dashscope.aliyuncs.com/compatible-mode/v1` |
| OpenAI | `https://api.openai.com/v1` |
| 月之暗面 Kimi | `https://api.moonshot.cn/v1` |
| 智谱 GLM | `https://open.bigmodel.cn/api/paas/v4` |
| 硅基流动 SiliconFlow | `https://api.siliconflow.cn/v1` |
| 本地 Ollama | `http://127.0.0.1:11434/v1` |

> Ollama 是 http：需要后端放行**本机地址的 http**（见 5.3）。

### 4.4 `apiSettings.ts` 类型

```ts
export interface ApiSettings { /* 原字段 + LLM_PROVIDER_LABEL + EMBEDDING_PROVIDER_LABEL */ }
export interface ConnectionResult {
  kind: string; ok: boolean; latency_ms: number | null; http_status: number | null
  detail: { model?: string; dimensions?: number }; provider: string; error: string | null
}
export interface ModelDiscovery {
  kind: string; ok: boolean; models: string[]; count: number
  latency_ms: number | null; provider: string; error: string | null
}
// client 增加 models(body, kind) -> POST /models
// 三个响应都是固定形状，用 request<T>() 泛型返回，不再假设 { message }
// AbortSignal.timeout(25000) → 30000（后端 timeout=20s，前端要留余量）
```

### 4.5 保存语义（重要，避免误清空）

- 前端只提交**非空**的 `*_MODEL` / `*_PROVIDER_LABEL` / `*_API_KEY`（密钥留空＝保留）；
- 后端 `save_config` 对 `KEEP_WHEN_BLANK = {LLM_CHAT_MODEL, LLM_EXTRACTION_MODEL, EMBEDDING_MODEL,
  LLM_PROVIDER_LABEL, EMBEDDING_PROVIDER_LABEL, LLM_API_KEY, EMBEDDING_API_KEY}` 的**空字符串跳过合并**；
- 允许"先存地址与密钥、模型稍后再选"：在线模式的模型非空校验放宽（缺失只提示，不阻断保存）。

---

## 5. 后端改造要点

### 5.1 去掉预置厂商/模型

```python
DEFAULTS = {
  "LLM_MODE": "demo", "LLM_BASE_URL": "", "LLM_CHAT_MODEL": "", "LLM_EXTRACTION_MODEL": "",
  "LLM_PROVIDER_LABEL": "",
  "EMBEDDING_MODE": "demo", "EMBEDDING_BASE_URL": "", "EMBEDDING_MODEL": "",
  "EMBEDDING_DIMENSIONS": 1024, "EMBEDDING_PROVIDER_LABEL": "",
}
```

`FIELDS` 同步加入两个 `*_PROVIDER_LABEL`。老配置文件里的旧模型名会在页面回显，由用户自行改选（不强制迁移）。

### 5.2 新增函数（放在 `services/api_settings.py`）

```python
TIMEOUT_SECONDS = 20

def _api_base(value):          # rstrip("/")；path 为空则补 "/v1"
def _call_json(url, key, payload=None):   # Bearer + POST/GET + perf_counter 计时；异常转中文 ValueError
def extract_model_ids(body):   # 兼容 data[].id / models[].name / 纯字符串数组；去重保序
def _looks_like_embedding(name)
def _resolve(kind, body):      # 请求优先 → 已保存；返回 (prefix, base_url, key)
def list_models(kind, body):   # → {"ok", "models", "count", "latency_ms", "provider", "error"}，不抛错
def test_connection(body):     # → {"ok", "latency_ms", "http_status", "detail", "provider", "error"}，不抛错
```

`_call_json` 的异常映射（这是"失败原因"文案的唯一来源）：

| 异常 | error 文案 |
| --- | --- |
| `HTTPError` | `服务商返回 HTTP {code}，请核对密钥、地区、模型与额度` |
| `URLError/TimeoutError/OSError` | `连接失败，请检查网络、API 地址与证书` |
| `JSONDecodeError/UnicodeDecodeError` | `服务商响应不是 JSON，请确认 API 地址` |

### 5.3 地址校验放宽（本机）

```python
LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1", "[::1]"}
def _is_local_host(name):  # 另放行 192.168.* / 10.*
# 规则：https 一律允许；http 仅允许本机/内网，避免密钥明文出境
```

### 5.4 接口层

```python
@router.post("/models")
def available_models(body: dict):
    return list_models(body.get("kind", "llm"), body)      # 失败也在 200 里给原因

@router.post("/test")
def connection_test(body: dict):
    try:
        return test_connection(body)                       # 结构化结果
    except ValueError as exc:                              # 仅 kind 非法
        return JSONResponse(status_code=400, content={"code": "VALIDATION_ERROR", "message": str(exc)})
```

---

## 6. 视觉方案：暖纸墨色（仅本页）

在 `ApiSettings.vue` 的 `.api-settings` 上用 **scoped 变量覆盖**，不改 `styles.css` 全局令牌（满足"只改这一页"）：

| 令牌 | 值 | 用途 |
| --- | --- | --- |
| `--paper` | `#faf8f4` | 页面底 |
| `--panel` | `#fffdfa` | 卡片面 |
| `--line` | `#e6e0d6` | 边框 |
| `--line-soft` | `#ece6dc` | 分隔线/虚线 |
| `--ink` | `#23201c` | 正文 |
| `--ink-muted` | `#8b8175` | 说明文字 |
| `--accent` | `#9c4a34`（hover `#7f3a27`，soft `#f6ece7`） | 主按钮、链接、聚焦 |
| `--pine` | `#3f6157` | 状态强调（如"当前生效"） |
| `--warn-bg/-line/-ink` | `#fdf7e8` / `#e9d8ac` / `#8a6a1f` | 获取失败提示 |

其它要求：主按钮用砖红实底白字；次要按钮白底细边；服务商快捷项做**胶囊小按钮**；
弹窗使用同一套纸色，避免"AI 味"的青蓝渐变与大圆角发光。

---

## 7. 涉及文件清单

| 文件 | 动作 |
| --- | --- |
| `src/backend/app/services/api_settings.py` | 改：DEFAULTS 清空、新增 6 个函数、放开本机 http、空值保留、结构化测试 |
| `src/backend/app/api/api_settings.py` | 改：新增 `/models`，`/test` 返回结构化结果 |
| `src/frontend/src/api/apiSettings.ts` | 改：新增两个结果类型与 `models()`，`test()` 返回类型 |
| `src/frontend/src/components/ConnectionResultDialog.vue` | 新增：结果小窗口 |
| `src/frontend/src/views/ApiSettings.vue` | 重构：两块独立、模型下拉、服务商预设、暖纸墨色 |
| `tests/test_api_settings.py` | 改：补模型解析、延迟字段、HTTP/超时分类、空值保留、本机 http 用例 |
| `tests/smoke_api_settings.py` | 改：补 `/models`、结构化 `/test`、未知 kind 400 |
| `tests/frontend/api-settings.test.ts` | 新增：两块独立、弹窗延迟、模型候选、无预置厂商名 |
| `src/frontend/vitest.config.ts` | 改（本地环境）：为 `@vue/test-utils` / `pinia` / `vue-router` 加显式别名 |
| `app/src/backend/...`、`app/web/*` | 原型发行目录：同步后端源码与重新构建的前端产物 |

> `vitest.config.ts` 的别名是本地检出布局导致的**既有问题**：`tests/frontend` 在前端包之外，
> 本机跑任何前端用例都会 `Failed to resolve import "@vue/test-utils"/"pinia"/"vue-router"`（连 `h13.test.ts`
> 也失败）。修法：`resolve.alias` 指向 `./node_modules/<pkg>/dist/...` 的 ESM 产物。

---

## 8. 验证方案

1. 后端单测（用内置 3.12 运行时）：`python -m unittest` 跑 `tests/test_api_settings.py`；覆盖
   模型列表解析（两种形状）、`latency_ms` 存在、401 分类、超时分类、空值保留、本机 http 放行、默认值不含模型名。
2. smoke（需服务在跑）：未登录 401 / 学生 403 / 教师读取 / `/models` 形状 / `/test` 形状 / 未知 kind 400 /
   空值保存不清空 / 向量切换迁移门禁。
3. 前端：`npm --prefix src/frontend run test -- --run api-settings`、
   `npm --prefix src/frontend run type-check`、`npm --prefix src/frontend run build`。
4. 实机：把 `src/frontend/dist` 覆盖到原型 `app/web/`，重启后用
   `demo_teacher / smartsketch-demo` 登录，打开 `/api-settings`，分别点两次「测试连接」，
   确认两个小窗口各自显示延迟与成败。

**测试用例设计要点（前端）**：`ConnectionResultDialog` 用 `<Teleport to="body">`，
断言要查 `document.querySelector('.dialog')`，不能用 `wrapper.get('.dialog')`。

---

## 9. 风险与回滚

| 风险 | 说明 | 缓解 |
| --- | --- | --- |
| 服务商不支持 `GET /models` | 部分私有网关/代理不实现 | `ok=false` + 可读原因，页面回退手动输入模型名 |
| 通义兼容模式的 `/models` 混合返回 | 聊天与向量同名同列 | `embedding` 侧按关键字收敛，仍允许手填 |
| 老配置回显旧模型名 | 用户之前存过 `deepseek-chat` | 页面不预置但回显，用户可改选，不强制迁移 |
| 向量切换门禁 | 换向量模型必须离线迁移 | 保留 `save_for_active_space` 现有拦截，不因本次改动放宽 |
| 测试消耗额度 | 每次测试发一次最小请求 | LLM 约 5 token、向量 1 条短文本；弹窗内明示 |
| 回滚 | 改动集中 5 个文件 | `git checkout -- <files>` 即可整体回滚；无数据迁移 |

---

## 10. 实施顺序建议

1. 后端 service：DEFAULTS/字段/校验 → `_call_json`/`extract_model_ids`/`list_models`/`test_connection`；
2. 后端 API：加 `/models`、改 `/test`；
3. 后端单测跑绿；
4. 前端 client 类型 → 结果弹窗 → 页面重构（配色最后做，便于对照）；
5. 前端单测 + `type-check` + `build`；
6. 同步 `app/src/backend` 与 `app/web`，重启原型做实机核对；
7. 更新 `docs/tasks.md`、`docs/handoffs/codex-*.md`（遵守 `AGENTS.md` 的完成标准）。

---

## 11. 环境相关备注（本次排查所得，实施时会用到）

- 原型发行目录的数据在 `%LOCALAPPDATA%\SmartSketch-External`；API 密钥文件由启动脚本指向
  `$data\api-settings.json`，可用 `launcher\api-settings.json` 覆盖（`SMARTSKETCH_API_CONFIG`）。
- 启动脚本依赖 `launcher\local-runtime.json` 的 `python/java/neo4j` 三个路径。本机
  `neo4j` 原指向 `C:/Users/asus/AppData/Local/SmartSketch-Runtime/neo4j-5.26.31`（**已不存在**），
  实际可用的是 `E:/作业/SmartSketch/.worktrees/windows-portable-login/dist/staging/SmartSketch/runtime/neo4j`
  （5.26.31 + APOC 齐备）。该行已修正，否则双击启动会报"未找到 NEO4J_HOME 指向的 Neo4j 5.26.31"。
- 本机 Shell 的 HTTPS 不可用（Windows Schannel `SEC_E_NO_CREDENTIALS`），git/curl 拉取 GitHub 会失败；
  需要用 Node 的 `https` 模块下载（本方案的回档与取源码就是这么做的）。
- Node 工具链在读写沙箱下会因 `spawn EPERM` 起不来（Vite 取真实路径需要子进程），跑 `vitest`/`build`
  需要在放宽的权限下执行。
