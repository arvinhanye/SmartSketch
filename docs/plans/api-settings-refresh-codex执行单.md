# Codex 执行单：API 设置页改造（暖纸墨色 · 独立测试小窗口 · 模型自动识别）

> 仓库分支：`codex/api-settings`（基线 `827ca31`）
> 本执行单是**唯一需求来源**，照做即可；不需要读全仓库、不需要跑全量测试。
> 详细设计说明见同目录 `api-settings-refresh-方案.md`（**只在有疑问时**再翻，不要通读）。

---

## 0. 一句话目标

API 设置页改成：两块接口（大模型 / 向量）**各自独立测试**，结果落在**各自的小窗口**并显示**往返延迟与成败**；
模型名**不再预置**，由 `GET {base}/models` **自动识别**后交给用户从下拉选择（也允许手填）；
本页配色改为**暖纸墨色**（不影响其它页面）。

---

## 1. 允许读取的文件（只读这些，读完就动手）

| 文件 | 目的 |
| --- | --- |
| `src/backend/app/services/api_settings.py` | 要改的主体 |
| `src/backend/app/api/api_settings.py` | 加接口 |
| `src/frontend/src/api/apiSettings.ts` | 客户端类型 |
| `src/frontend/src/views/ApiSettings.vue` | 重构页面 |
| `src/frontend/src/components/AuthLayout.vue` | **只看** `<style scoped>` 里如何用 CSS 变量与栅格（照抄风格，别改它） |
| `.claude/rules/frontend.md` | 前端约定 |

**不要**做的事：全仓库检索、读 `docs/` 下的长文档、读 `specs/*`、读 `tests/` 下与本次无关的用例、读 `dist/`、读 `node_modules/`。

---

## 2. 硬性禁令（省 token 的关键）

1. **禁止**运行：`./scripts/verify.sh`、任何 `npm run test`（不带文件过滤）、`playwright`/e2e、`docker`、`reembed.py`、任何迁移脚本。
2. **禁止**为了"确认环境"去调用真实服务商的 API（不消耗用户额度）。检查只允许离线单测与一次已启动服务上的 smoke。
3. **禁止**新增超过 2 个测试文件；前端只允许 1 个新测试文件、断言 ≤ 4 条。
4. **禁止**大面积重排既有代码：只动第 3 节列出的文件与函数，不顺手重构、不改其它页面样式、不动 `styles.css` 全局令牌。
5. **禁止**改 `save_for_active_space` 的"换向量模型需离线迁移"门禁。
6. 每次命令的输出只看**最后 30 行**，不要打印整个 HTML 快照或整份文件。
7. 不写 ADR、不改 `docs/architecture.md`、不生成多余文档；最后只写**一份 10 行以内**的交接文件（见 §7）。
8. 不 `git commit`、不 `git push`（用户自己决定）。

---

## 3. 任务分解（按顺序做，每步做完立刻做该步的验收）

### T1 后端：配置语义（`src/backend/app/services/api_settings.py`）

- `FIELDS` 增加 `LLM_PROVIDER_LABEL`、`EMBEDDING_PROVIDER_LABEL`。
- `DEFAULTS` **清空所有厂商与模型名**：

```python
DEFAULTS = {
    "LLM_MODE": "demo", "LLM_BASE_URL": "", "LLM_CHAT_MODEL": "", "LLM_EXTRACTION_MODEL": "",
    "LLM_PROVIDER_LABEL": "",
    "EMBEDDING_MODE": "demo", "EMBEDDING_BASE_URL": "", "EMBEDDING_MODEL": "",
    "EMBEDDING_DIMENSIONS": 1024, "EMBEDDING_PROVIDER_LABEL": "",
}
```

- 新增 `KEEP_WHEN_BLANK`，`save_config` 合并时**空字符串跳过**（密钥留空＝保留、模型留空＝保持原选择）：

```python
KEEP_WHEN_BLANK = {"LLM_CHAT_MODEL", "LLM_EXTRACTION_MODEL", "EMBEDDING_MODEL",
                   "LLM_PROVIDER_LABEL", "EMBEDDING_PROVIDER_LABEL", *SECRETS}
```

- 地址校验：`https` 一律放行；`http` **仅**允许本机/内网（`127.0.0.1`、`localhost`、`::1`、`192.168.*`、`10.*`），
  否则仍报 `API 地址必须为 HTTPS；本机地址可用 HTTP`。
- 在线模式的模型非空校验放宽：允许"先存地址与密钥、模型稍后再选"。

**验收（离线，≤ 20 秒）**：

```bash
python -m unittest tests.test_api_settings          # 见 T4 更新后的用例
```

### T2 后端：能力与接口（同文件新增函数 + `api/api_settings.py`）

新增常量与辅助：

```python
TIMEOUT_SECONDS = 20
LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1", "[::1]"}

def _is_local_host(name): ...                 # 见方案 §5.3
def _api_base(value):                         # rstrip("/")；path 为空则补 "/v1"
def _call_json(url, key, payload=None):       # Bearer；POST/GET；perf_counter 计时；异常转中文 ValueError
def extract_model_ids(body):                  # data[].id / models[].name / 字符串数组；去重保序
def _looks_like_embedding(name):              # embed|bge|gte|m3e|text-similarity|rerank
def _resolve(kind, body):                     # 请求里刚填的优先 → 已保存的；返回 (prefix, base_url, key)
```

新增两个对外的"永不抛错（除参数错）"函数：

```python
def list_models(kind, body):
    # 返回 {"kind","ok","models","count","latency_ms","provider","error"}；失败填 error，HTTP 仍为 200
    # kind == "embedding" 时按关键字收敛模型列表，收敛后为空则保留原列表

def test_connection(body):
    # 返回 {"kind","ok","latency_ms","http_status","detail","provider","error"}
    # llm: POST {base}/chat/completions  {model, messages:[{role:user,content:"Reply OK"}], max_tokens:5}
    #      detail.model = choices[0].model or 请求的 model；缺 choices → error "响应缺少 choices…"
    # embedding: POST {base}/embeddings {model, input:["连接测试"], dimensions:1024}
    #      detail.dimensions = len(data[0].embedding)；缺向量 → error "响应缺少向量数据…"
    # 模型取值：请求体 → 已保存 → (llm) LLM_EXTRACTION_MODEL；全空 → "请先获取并选择一个模型，或手动填写模型名"
```

异常 → 文案映射（这是小窗口里失败原因的唯一来源，照抄）：

| 异常 | 文案 |
| --- | --- |
| `HTTPError` | `服务商返回 HTTP {code}，请核对密钥、地区、模型与额度` |
| `URLError` / `TimeoutError` / `OSError` | `连接失败，请检查网络、API 地址与证书` |
| `JSONDecodeError` / `UnicodeDecodeError` | `服务商响应不是 JSON，请确认 API 地址` |

接口层：

```python
@router.post("/models")
def available_models(body: dict):
    return list_models(body.get("kind", "llm"), body)

@router.post("/test")
def connection_test(body: dict):
    try:
        return test_connection(body)
    except ValueError as exc:      # 只有 kind 非法才会走到这里
        return JSONResponse(status_code=400, content={"code": "VALIDATION_ERROR", "message": str(exc)})
```

**验收**：`python -m unittest tests.test_api_settings`（T4 会补用例）。

### T3 前端：客户端 + 结果小窗口

`src/frontend/src/api/apiSettings.ts`：

- 接口类型加 `LLM_PROVIDER_LABEL`、`EMBEDDING_PROVIDER_LABEL`；新增：

```ts
export interface ConnectionResult {
  kind: string; ok: boolean; latency_ms: number | null; http_status: number | null
  detail: { model?: string; dimensions?: number }; provider: string; error: string | null
}
export interface ModelDiscovery {
  kind: string; ok: boolean; models: string[]; count: number
  latency_ms: number | null; provider: string; error: string | null
}
```

- `request<T>()` 泛型化；`test()` 返回 `ConnectionResult`；新增 `models(body, kind)` → `POST /models`；
  超时 `AbortSignal.timeout(30000)`。

新增 `src/frontend/src/components/ConnectionResultDialog.vue`（**完整细节按此实现**）：

- props：`open: boolean`、`title: string`、`pending: boolean`、`elapsed: number`、`result: ConnectionResult | null`；emit：`close`。
- `<Teleport to="body">` + 遮罩（点遮罩/ESC/关闭按钮都能关）；`role="dialog" aria-modal="true"`；宽 `min(100%, 22rem)`。
- 内容顺序：标题「{title}测试结果」→ 状态（`测试中…` / `连接成功` / `连接失败`）→
  事实表（**往返延迟**：pending 显示 `elapsed/1000` 秒，否则 `{latency_ms} ms`；接口地址＝`provider`；使用模型＝`detail.model`；
  有 `detail.dimensions` 才显示向量维度；有 `http_status` 才显示 HTTP 状态）→ 失败原因（`result.error`，仅失败时显示）→
  脚注「延迟为本机进程到服务商的完整往返时间；测试只发送一次最小请求。」
- 配色用第四节令牌：面板 `#fffdfa`、边框 `#e6e0d6`、正文 `#23201c`、说明 `#8b8175`、
  成功 `#3f6157`、失败 `#9c4a34`、错误框 `#fbeee8`/`#e8c9bd`/`#8a3b26`。

### T4 前端：页面重构（`src/frontend/src/views/ApiSettings.vue`）

- 两块「大模型接口」「向量模型接口」，**各自独立**状态：

```ts
const testing = reactive({ llm: false, embedding: false })
const results = reactive<{ llm: ConnectionResult | null; embedding: ConnectionResult | null }>({ llm: null, embedding: null })
const dialog = reactive({ kind: null as 'llm' | 'embedding' | null, elapsed: 0 })
const discovery = reactive({
  llm:       { models: [] as string[], count: 0, done: false, error: '', latency: null, busy: false },
  embedding: { models: [] as string[], count: 0, done: false, error: '', latency: null, busy: false },
})
```

- 点「测试连接」：只置本块 `testing[kind]`、打开本块 `dialog.kind`、`setInterval(100ms)` 刷新 `dialog.elapsed`；
  响应到达后清 interval，弹窗保持显示结果。**另一块全程不受影响**。
- 模型控件：`<input :list="...">` + `<datalist>`，候选 = `当前值 ∪ 已保存值 ∪ 接口识别结果`；每块一个「获取模型列表」按钮；
  成功提示 `识别到 N 个模型（{latency} ms），可直接下拉选择或手动输入其他名称`；失败把 `error` 显示为黄色提示并仍允许手填。
- 服务商快捷胶囊（**只填地址**，绝不填模型名）：DeepSeek / 阿里云百炼（通义）/ OpenAI / 月之暗面 Kimi / 智谱 GLM /
  硅基流动 SiliconFlow / 本地 Ollama(`http://127.0.0.1:11434/v1`)。
- 文案去厂商化：标题「大模型接口」「向量模型接口」，按钮「测试连接」「获取模型列表」；厂商名只从用户填的服务名或主机名体现。
- 保存：只提交本页字段，`*_MODEL` / `*_PROVIDER_LABEL` / `*_API_KEY` 为空则**不发该键**；保留原「已保存，请重启软件」提示。
- 页面顶部保留：当前生效状态 + 「密钥留空表示保留已保存的密钥」+ 「外部服务要求 HTTPS，本机地址可用 HTTP」。

**配色（仅本页，scoped 覆盖变量，不改 `styles.css`）**：

```css
.api-settings{
  --paper:#faf8f4; --panel:#fffdfa; --line:#e6e0d6; --line-soft:#ece6dc;
  --ink:#23201c; --ink-muted:#8b8175;
  --accent:#9c4a34; --accent-hover:#7f3a27; --accent-soft:#f6ece7; --pine:#3f6157;
  --warn-bg:#fdf7e8; --warn-line:#e9d8ac; --warn-ink:#8a6a1f;
}
```

主按钮砖红实底白字；次要按钮白底细边；聚焦 `outline: 2px solid var(--accent-soft)`；
不要青蓝、不要渐变光晕、不要大圆角发光。

### T5 测试（**只做这些，多一条都不做**）

1. 更新 `tests/test_api_settings.py`：在已有用例基础上**只加 4 条**——
   `extract_model_ids` 两种形状、`list_models` 返回 `count` 与 `latency_ms`（`urlopen` 打桩）、
   空模型名保留旧值、`http://127.0.0.1` 放行而 `http://example.com` 拒绝。
   > 打桩方式：`patch.object(api_settings, "urlopen", return_value=FakeResponse(body))`。
   > 用例的临时目录要建在 `tests/.tmp-api-settings/`（沙箱下 `tempfile.mkdtemp` 的 0o700 目录不可写）。
2. 新增 `tests/frontend/api-settings.test.ts`：**仅 4 条断言**——
   三个模型输入初始为空（不预置厂商模型名）、点两块「获取模型列表」各发一次 `kind` 正确的请求、
   点第一块测试后弹窗出现且含延迟而第二块无弹窗、失败时弹窗显示 `401` 原因。
   > 弹窗是 `Teleport` 到 body 的，断言必须用 `document.querySelector('.dialog')`，不能用 `wrapper.get`。
   > `fetch` 用 `vi.stubGlobal` 打桩，**不要**真连网。
3. `tests/smoke_api_settings.py`：只在已启动的服务上补 `/models` 与结构化 `/test` 的断言（若服务没在跑就跳过，别去启动它）。

**验收命令（就这三条，最多各跑一次）**：

```bash
python -m unittest tests.test_api_settings
npm --prefix src/frontend run test -- --run api-settings
npm --prefix src/frontend run type-check
```

- 只允许在**改完前端之后**跑一次 `npm --prefix src/frontend run build`（产物要给原型用）。
- 单测失败时：**只重跑失败的那一个用例**（`--run <文件名>` / `-k <用例名>`），不要把全量再跑一遍。
- 如果 `tests/frontend` 因解析不到 `@vue/test-utils`/`pinia`/`vue-router` 而整体失败（本地检出布局导致的既有问题，
  与本次改动无关）→ 在 `src/frontend/vitest.config.ts` 的 `resolve.alias` 里指向
  `./node_modules/<pkg>/dist/...` 的 ESM 产物即可，**不要**去改测试目录结构。

### T6 交付到原型（用户实际看的是这个）

```powershell
# 后端源码同步
Copy-Item SmartSketch_src\src\backend\app\services\api_settings.py app\src\backend\app\services\ -Force
Copy-Item SmartSketch_src\src\backend\app\api\api_settings.py      app\src\backend\app\api\      -Force
# 前端产物同步（先 build）
Copy-Item SmartSketch_src\src\frontend\dist\* app\web\ -Recurse -Force
```

同步后把 `app\web\assets` 里**不再被 `index.html` 引用的旧产物删掉**（只保留 `index.html` 引用的那份 + `esm-*.js`）。
原型重启后教师账号进入「API 设置」，两块各点一次「测试连接」，确认两个小窗口各自显示延迟。

> 启动方式：双击 `启动智绘学途.cmd`（若报找不到 Neo4j，检查 `launcher\local-runtime.json` 的 `neo4j` 路径）。
> **不要**为了验证去点真实服务商接口；用演示模式或让用户自己点。

---

## 4. 视觉令牌（唯一配色来源）

见 T4 的 CSS 变量表；页面文本与按钮一律引用变量，禁止散落硬编码色值（`#fff`/`#000` 除外）。

---

## 5. 完成标准（本次刻意精简，替代 AGENTS.md §5 的全量门禁）

1. T5 的三条命令全绿；`build` exit 0。
2. `git diff --stat` 只出现 §6 列出的文件；`git diff --check` 无空白错误。
3. 原型上两块能各自测试、小窗口显示延迟与成败。
4. 不在 `docs/tasks.md` 写长篇记录，只追加**最多 3 行**任务状态。

---

## 6. 允许改动的文件（超出即算越界）

```
src/backend/app/services/api_settings.py
src/backend/app/api/api_settings.py
src/frontend/src/api/apiSettings.ts
src/frontend/src/components/ConnectionResultDialog.vue   (新增)
src/frontend/src/views/ApiSettings.vue
tests/test_api_settings.py
tests/smoke_api_settings.py
tests/frontend/api-settings.test.ts                      (新增)
src/frontend/vitest.config.ts                            (仅在 T5 触发条件成立时)
docs/tasks.md                                            (最多 3 行)
docs/handoffs/codex-api-settings-refresh.md              (新增，≤10 行)
app/src/backend/**、app/web/**                            (仅 T6 从源码同步，不手改)
```

---

## 7. 交接文件模板（照抄填写，≤10 行）

```markdown
# codex-api-settings-refresh

输入：用户要求两块 API 独立测试 + 结果小窗口（延迟/成败）+ 模型自动识别与下拉 + 本页暖纸墨色。
输出：<改了哪些文件，一行一句>。
接口：新增 POST /api/v1/api-settings/models；POST /test 改为返回 {ok, latency_ms, detail, error}。
验证：<实际跑过的三条命令与结果>；build exit 0。
未做：<没做的测试/没验证的场景，明确写出来>。
风险：<例如服务商不支持 /models 时回退手动输入>。
```

---

## 8. 卡住时的处理

- `/models` 拉不到模型：**不要**反复改协议试错；确认 `_api_base` 是否补了 `/v1`，再确认是否 401；
  仍失败就把 `error` 文案透传到页面，手填模型名路径可用即算通过。
- 单测因环境（沙箱/权限/临时目录）失败：不要重试超过 2 次，记录到交接文件的"未做"里，继续后面的任务。
- 需要用户决策（例如配色、是否迁移向量）时停下来问，不要自行决定。
