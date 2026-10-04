# L03 ADR、规则与契约

```text
task_id: L03
review_status: ready_for_review
worktree: /Users/arvinhan/SmartSketch/.claude/worktrees/smartsketch-contest-sprint-77644f
base_commit: 7078812
head_commit: 本任务提交
changed_files:
  - docs/decisions.md（追加 ADR-080、ADR-081）
  - AGENTS.md（§4、§6 两处措辞）
  - docs/architecture.md（关键质量边界一条；wire 枚举表 ErrorCode 行）
  - docs/integrations.md（LLM_MODE、EMBEDDING_MODE、D-02c、启动校验三条；新增两个变量行）
  - .env.example（只加注释：personal 模式与 local 不支持的说明）
  - src/contracts/api.v1.yaml、src/contracts/errors.v1.md
  - src/contracts/v1/generated/（重新生成：openapi.json、python/models.py、typescript/openapi.d.ts、ChatEvent/TaskEvent schema）
  - src/backend/app/schemas/contracts.py（导出 6 个新模型）
  - src/frontend/src/api/{http,chatStream,taskEvents}.ts（错误码穷举清单加 MODEL_CONFIG_REQUIRED）
  - docs/superpowers/plans/2026-10-02-contest-sprint-a-personal-model-api.md（Task 4 Step 6 补一条）
  - docs/tasks.md、docs/handoffs/claude-l03.md
```

## 交付与关键决定

- ADR-080：`LLM_MODE=personal`、每用户一份 AES-256-GCM 加密配置（关联数据 `user_id`）、任务级密文快照与清除/终态语义、按「用户 + 配置版本」隔离的问答策略、按用户日预算、出站地址校验与钉 IP、规则调整与新增 `cryptography`。签收依据：用户 2026-10-02 同意规格第 11 节。
- ADR-081：系统级在线向量 `text-embedding-v4`/1024/10，`EMBEDDING_MODE=local` 配置校验即拒绝；D-02c 改为已签收。
- 契约：`getModelConfig`、`saveModelConfig`、`clearModelConfig`、`testModelConfig` 四个操作（tag `settings`）；`RuntimeMode`、`ModelConfig`、`ModelConfigLastTest`、`ModelConfigTestErrorClass`、`ModelConfigUpdate`、`ModelConfigTestRequest`、`ModelConfigTestResult`；`ErrorCode` 增加 `MODEL_CONFIG_REQUIRED`；`uploadDocument` 与 `chat` 各加 409。生成的 `ModelConfigUpdate` 为 `extra = forbid`，`api_key` 为 `SecretStr`。

## 计划之外的两处调整

1. 前端 `http.ts`、`chatStream.ts`、`taskEvents.ts` 各有一份带编译期穷举检查的错误码清单，新增错误码不同步会使类型检查失败，已一并补上；`docs/architecture.md` 的 wire 枚举表同步。
2. `.env.example` 的 `MODEL_CREDENTIAL_KEY`、`MODEL_ENDPOINT_ALLOW_PRIVATE` 两行挪到 L04：`tests/backend/test_b06.py::test_env_example_covers_every_setting` 要求变量与 `Settings` 字段一一对应，先加变量会让该用例失败（本任务首次运行即复现）。计划 Task 4 已补这一步。

## verification

| 命令 | 结果 |
| --- | --- |
| `./scripts/gen-contracts.sh` | 生成成功（datamodel-codegen、openapi-typescript 7.4.4） |
| `scripts/verify/contracts.sh` | exit 0 |
| `npm run type-check --prefix src/frontend` | exit 0 |
| `npm run test --prefix src/frontend -- --run --testTimeout 30000` | exit 0，25 个文件 772 用例通过 |
| 后端全量 `pytest tests/backend tests/tooling` | 首次 exit 1：`test_b06::test_env_example_covers_every_setting`（见上方调整 2）；调整后重跑 exit 0，3561 通过、27 跳过 |
| `./scripts/verify.sh` | exit 0（基础档） |

## unverified

运行中的 API 尚未实现这四个操作（L06）。契约先行是有意的；若后续发现有测试比对运行时 OpenAPI 与契约，会在 L06 一并通过。

## api_and_data_changes

契约新增如上；无数据迁移、无运行时代码变化（仅导出生成模型）。

## rollback

回退本提交即可；生成物随契约一起回退。

## next_action

L04：迁移 015、`services/credentials.py`、`repositories/model_configs.py`、设置字段与 `.env.example` 两行。
