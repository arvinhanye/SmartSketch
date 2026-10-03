# L06 个人模型配置接口

```text
task_id: L06
review_status: ready_for_review
worktree: /Users/arvinhan/SmartSketch/.claude/worktrees/smartsketch-contest-sprint-77644f
base_commit: 0e228bd
head_commit: 本任务提交
changed_files:
  - src/backend/app/services/model_configs.py（新增）
  - src/backend/app/api/model_config.py（新增）
  - src/backend/app/main.py（路由、测试限流器、可注入的出站传输）
  - tests/backend/test_l06.py（新增 20 例）
  - docs/tasks.md、docs/handoffs/claude-l06.md
```

## 交付

- `GET/PUT/DELETE /api/v1/me/model-config` 与 `POST /api/v1/me/model-config/test`，只作用于当前登录用户，路径与请求体都不能指定他人（请求体多余字段 422）。
- 读取只返回 `runtime_mode`、`configured`、地址、模型名、密钥末 4 位、版本号、更新时间与最近测试结果；未配置时只返回前两项。
- 保存：地址先经出站校验（失败返回 422 及机读原因）；首次保存或改地址必须带密钥；密钥只允许可见 ASCII。服务端未配置根密钥时写入返回 503（`credential_store_disabled`）。
- 测试连接：发 1 次输出上限为 1 token 的对话请求，只返回成败、错误分类与耗时，不回显供应商响应；地址未通过出站校验时返回 `blocked_address` 且不发请求；每用户每分钟 5 次，超出 429 并带 `Retry-After`；测试已存配置时记录结果。

## verification

| 命令 | 结果 |
| --- | --- |
| `pytest tests/backend/test_l06.py` | 先 1 失败 19 错误（模块不存在）；实现后 20 passed |
| 真实 DeepSeek（`run_test` + `GuardedTransport`，`https://api.deepseek.com`、`deepseek-flash`） | 正确密钥 `ok=True`，1888 毫秒；无效密钥 `error_class=auth`，2003 毫秒 |
| 后端全量 `pytest tests/backend tests/tooling`（含 L05、L06） | exit 0，3623 通过、27 跳过 |
| `./scripts/verify.sh` | exit 0（基础档） |

## 用量

两次测试连接各输出上限 1 token，不计入 `model_calls`；累计计费 token 仍按 101054 记（另加约数十 token 的测试请求）。

## unverified

- 浏览器页面调用：在 L10 走查。
- 测试连接对流式接口无关；只验证了非流式对话。

## api_and_data_changes

运行中的 API 新增契约里的四个操作（契约已在 L03 定义）。无数据迁移。

## rollback

回退本提交。

## next_action

L07（上传绑定与 worker 按任务取工具包）。
