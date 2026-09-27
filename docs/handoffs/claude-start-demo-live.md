# Claude 交接：一键启动的真实模型开关（DEMO-02）

- review_status: ready_for_review
- 分支：`claude/real-model-setup-zxgnka`，base `main@62eb8c7`
- 决定：无新 ADR（沿用 D-02a/ADR-027 主用模型、ADR-076 演示向量；只给 DEMO-01 脚本加开关）

## 背景

用户在网页里找不到「API 接入」选项。原因：模型密钥按设计只在服务端 `.env`（AGENTS.md §4），而 `scripts/start-demo.sh` 无论 `.env` 写什么都强制 `LLM_MODE=demo`，所以一键启动后上传 PDF 用的是规则演示模型。

## 交付物

| 文件 | 内容 |
| --- | --- |
| `scripts/start-demo.sh` | 新增 `--live`：检查主用四项 → `LLM_MODE=live`；向量用 `.env` 的 online/local，否则 demo（阈值 0.58）；macOS 未设 `SSL_CERT_FILE` 时用 certifi；不导入演示课程；结束信息打印当前模型 |
| `docs/runbook.md` | §2 新增「一键启动，真实大模型」 |

## 验证（云端 Linux 容器）

- `bash -n scripts/start-demo.sh` 通过；`--help` 显示新用法。
- `.env` 的 `LLM_API_KEY` 为空时 `scripts/start-demo.sh --live --no-open` 退出 1：「--live 需要在 .env 填写 LLM_API_KEY…」。
- 假密钥 + 不可达 `LLM_BASE_URL=https://127.0.0.1:9` 时全流程启动，结束信息为「模型：真实大模型 deepseek-flash…；向量：demo」；经前端代理登录 `demo_teacher`、建课、`POST /courses/{cid}/documents` 上传 Markdown 得 202，worker 日志出现 `model call failed … role=primary model=deepseek-flash error_class=connection`，即上传→抽取走真实模型客户端。未发任何付费调用。
- `load_settings` 以 `LLM_MODE=live`、`EMBEDDING_MODE=demo` 通过校验，工厂返回 `CompatibleModelClient` 与 `DemoEmbeddingClient`。

## 风险与下一步

- 未在 macOS 上实跑，也未用真实密钥跑通一份资料（付费，需用户在 Mac 上执行）。
- 网页里仍看不出当前模型模式；若需要，要先在 `src/contracts/` 加字段再做前端显示。
