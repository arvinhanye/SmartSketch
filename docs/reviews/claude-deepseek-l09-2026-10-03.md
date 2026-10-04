# Claude 复核：DeepSeek harness 的 L09（`ea9484c`）

- 日期：2026-10-03；复核者：Claude；对象：`ea9484c feat: L09 在线向量、拒绝 local 向量、正式启动入口`（交接 `docs/handoffs/deepseek-l09.md`，依据 `docs/handoffs/claude-l09-handoff.md`）。
- 结论：**通过**。改动在交接允许的范围内，代码与测试符合计划 Task 9 与交接；另记一项与本提交无关、但影响问答时延验收的既有风险（见第 3 节）。

## 1. 逐项核对

| 项 | 结果 |
| --- | --- |
| 改动范围 | 11 个文件，均在交接第 8 节列出的范围内；规格第 11 节补记两行属文档补充，可接受 |
| `config.py` | 与交接 6.2 一致：`local` 在配置校验即拒绝并指出 `EMBEDDING_MODE` |
| `test_l09.py` | 与交接 6.1 逐字一致 |
| `test_b06.py` | 三处与交接 6.3 一致，未删用例；`test_e07`、`test_demo_mode` 未改，理由成立 |
| `check-embedding.py` | 与交接 6.4 修正版逐字一致 |
| `start-demo.sh --personal` | 根密钥补齐位于 `.env` 导入循环之前（交接第 5 节第 2 条）；缺任一变量即中文报错退出，不落到演示模型或演示向量 |
| 三处偏离 | 互斥改为显式 `if`（`set -e` 下更稳）、帮助文本行号随新增一行调整、`--live` 分支保留 `local` 交给配置校验拒绝——理由都成立 |

## 2. 独立复跑（本机，2026-10-03）

| 命令 | 结果 |
| --- | --- |
| `pytest tests/backend/test_l09.py test_b06.py test_e07.py test_demo_mode.py` | 93 passed |
| `bash -n scripts/start-demo.sh scripts/start.sh` | 通过 |
| `scripts/start.sh --live` | 按预期退出：「--live 与 --personal 不能同时使用」 |
| `.venv/bin/python scripts/check-embedding.py` | **未成功**：本机到 `dashscope.aliyuncs.com:443` 再次 TCP 不通（`nc` 失败、连接停在 `SYN_SENT`），3 分钟后手动终止。DeepSeek 运行时同一命令 0.66 秒成功，说明该网络路径时通时断，不是代码问题 |

后端全量以 DeepSeek 的记录为准（3648 通过、27 跳过、0 失败）；本次只改配置校验一处与测试，未重跑全量。

## 3. 新发现的风险（既有代码，非本提交引入）

**向量服务不可达时，问答会挂到连接超时才失败，而不是在 15 秒内返回服务故障。**

- `services/qa/chat.py:115` 在准备阶段同步调用 `self.embedding.embed((query,))`，不带截止时间；截止检查在 `:136`，要等向量调用返回之后才执行。
- 向量客户端每次 HTTP 调用的超时是 `LLM_REQUEST_TIMEOUT_SECONDS`（60 秒），作用在每个地址的连接上；`dashscope.aliyuncs.com` 当前解析出 5 个地址，不可达时一次提问最长可能等约 5 分钟。
- 影响：问答「单次完整响应 ≤15 秒」的验收、以及「资料未覆盖与服务故障分开显示」的体验；学生会看到长时间无响应。
- 建议（未实施，需要单独认领）：给查询向量调用传入链路截止时间（与改写、生成共用 `deadline`），超时即按 `LLM_UNAVAILABLE` + `timeout` 返回；建连超时取「剩余时间」与单次超时中的较小值。先写复现测试（假传输模拟连接挂起），再改实现。适合放进计划 B 的 L15 边界回归或计划 C 的 L16。

## 4. 下一步

1. 推送 `ea9484c` 与本复核需用户授权。
2. L02 问答基线补测与 L10 真实页面走查都依赖向量网络路径稳定可达；当前不可达，需用户确认网络。
