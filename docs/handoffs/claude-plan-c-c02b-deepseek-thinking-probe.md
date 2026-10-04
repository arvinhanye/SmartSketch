# C02 方案 B 前置 交 DeepSeek harness：思考控制参数探测

```text
from: Claude
to: DeepSeek harness
date: 2026-10-04
code: claude/plan-c-reliability（本交接所在提交；工具 evaluation/probe_thinking.py）
budget: 用户 2026-10-04 批准——本次探测上限 5000 token（输入 + 输出，含推理）；最坏情况 5 个变体共 4110
paid_calls_by_claude: 0
```

## 1. 目的

C03-1 实测：抽取输出 80% 是推理，两次关系调用的 4096 输出全部是推理，导致截断与 repair（`docs/reviews/claude-deepseek-c02-4-c03-1.md`）。用户已决定进入方案 B（思考控制）。不同供应商关闭思考的字段不同，**先用真实供应商确认哪个字段被接受、是否真的降低推理**，Claude 再据此写 ADR 与实现。不猜参数。

## 2. 环境

- 在用户指定的 checkout 运行，代码为本分支最新提交。**不需要**启动 API、worker 或 Neo4j，也不读写数据库。
- 供应商与模型：与学生 / 教师个人配置相同的 DeepSeek 接口与模型 `deepseek-flash`。base URL 与密钥由用户提供：
  - base URL 写进命令参数；
  - **密钥只放环境变量 `PROBE_KEY`**，不得出现在命令行、日志、报告或提交里；跑完 `unset PROBE_KEY`。
- 只允许 https 地址；不加 `--allow-http`。

## 3. 命令（只跑一次，不重试）

```bash
mkdir -p evaluation/raw/c02b
PROBE_KEY=<由用户提供，不写进命令历史> \
python evaluation/probe_thinking.py --base-url https://<供应商地址>/v1 --model deepseek-flash \
    --key-env PROBE_KEY --cap 5000 --max-tokens 512 > evaluation/raw/c02b/probe.jsonl
echo "exit $?"
```

- 默认依次探测 5 个变体：
  - `baseline`（不加字段，对照）；
  - `thinking_disabled`（`thinking: {"type": "disabled"}`）；
  - `enable_thinking_false`（`enable_thinking: false`）；
  - `chat_template_enable_thinking_false`（`chat_template_kwargs: {"enable_thinking": false}`）；
  - `reasoning_effort_low`（`reasoning_effort: "low"`）。
- 工具每次发出前按最坏情况检查上限；超出即停，退出码 3，照实记录，不补跑。
- 被拒的变体（400 等）是**有效结果**（说明该字段不被接受），不是故障。

## 4. 交付

1. `evaluation/raw/c02b/probe.jsonl`：工具原样输出。只含状态、错误码与类型、usage、字数、耗时；不含密钥，也不含供应商错误原文。
2. `evaluation/reports/c02b-thinking-probe.md`：
   - 逐变体表：是否被接受、HTTP 状态 / 错误码、输入 / 输出 / 推理 token、推理字数、可见字数、`finish_reason`、耗时；
   - 结论：哪个字段被接受且推理明显下降（推理 token 或推理字数接近 0，同时输出 token 显著下降）；若都无效，照实写「未找到有效字段」；
   - 可见回答是否仍是合规 JSON（只看格式，不评质量）。
3. **预算**：本次调用直连供应商，**不会进入 `model_calls`**，请把工具汇总里的 `tokens_used` 手工记入台账：
   - 系统计费口径：开跑前 743806（记录口径 731690）；
   - 跑完后 = 开跑前 + `tokens_used`；
   - 写进报告与 `docs/handoffs/deepseek-c02b-probe.md`。
4. `docs/handoffs/deepseek-c02b-probe.md`：命令（密钥打码）、退出码、实际用量与限制。

## 5. 判读要点（不是通过标准）

- 单次请求、很短的提示，只回答「字段是否生效」，不代表抽取或问答质量，也不代表长输出时的推理比例。
- 若 `baseline` 本身推理就很少（短提示下模型可能不思考），照实写；Claude 会据此判断是否需要用更长的提示再探一次（另报预算）。
