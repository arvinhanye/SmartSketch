# C02b 思考控制参数探测

```text
task_id: C02b（依据 docs/handoffs/claude-plan-c-c02b-deepseek-thinking-probe.md）
review_status: ready_for_review
worktree: /Users/arvinhan/SmartSketch/.claude/worktrees/smartsketch-plan-a-fixes-e70a34
branch: claude/plan-c-reliability（仅本地提交，未推送、未合并、未改业务代码）
base_commit: ef39f98
head_commit: 本任务提交
author: DeepSeek harness
changed_files:
  - evaluation/reports/c02b-thinking-probe.md（新增）
  - evaluation/raw/c02b/probe.jsonl（新增，真实结果）
  - evaluation/raw/c02b/probe-attempt1-no-cert.jsonl（新增，第一次运行的全 URLError 输出，保留备查）
  - docs/handoffs/deepseek-c02b-probe.md（本文件）
```

## 结论一句话

**唯一有效字段是 `thinking: {"type": "disabled"}`**，其余四个字段（`enable_thinking: false`、`chat_template_kwargs.enable_thinking: false`、`reasoning_effort: "low"`，以及 baseline 对照）**都被静默忽略**——HTTP 200、无报错、行为与对照完全一致。

`thinking_disabled` 的效果是全面翻转，不是程度差异：

| 指标 | baseline（及其余无效变体） | `thinking_disabled` |
| --- | --- | --- |
| 推理字数 / 推理 token | 1121 / 512（无效变体 1077～1692） | **0 / null** |
| 输出 token | 512 = 上限，**截断** | **49** |
| 可见内容 | **0 字** | **121 字** |
| `finish_reason` | `length` | **`stop`** |
| 耗时 | 2598～2895 ms | **513 ms** |
| 输入 token | 96 | **70** |

**给 Claude 实现时的两条输入**：
1. 有效字段就是 `thinking: {"type": "disabled"}`；`enable_thinking` / `chat_template_kwargs` / `reasoning_effort` 在本供应商上无效，不要用。
2. **输入 token 也降了 26**（同一条提示词），所以预算与耗时估算不能只按输出折算。

另外，**baseline 本身就是 C02-1 推断的最小复现**：96 token 的短提示 + 512 上限，模型把全部 512 输出 token 花在推理上、可见内容 0 字、`finish_reason = length`。与 C03-1 在真实链路上看到的「输出 80% 是推理 → 截断 → repair」同源。

## 命令与退出码

```bash
export SSL_CERT_FILE="$(.venv/bin/python -c 'import certifi; print(certifi.where())')"
export PROBE_KEY="$(从 .env 按行读出 LLM_API_KEY，不回显)"
.venv/bin/python evaluation/probe_thinking.py --base-url https://api.deepseek.com \
    --model deepseek-flash --key-env PROBE_KEY --cap 5000 --max-tokens 512 \
    > evaluation/raw/c02b/probe.jsonl
# exit 0；summary: tokens_used=2551, cap=5000, stopped=null
unset PROBE_KEY
```

base URL 用 `https://api.deepseek.com`（工具拼 `/chat/completions`），与应用个人配置里保存的地址一致。密钥只在环境变量里，未进命令行、日志、报告或提交。

## 第一次运行失败（环境缺陷，已按用户确认后重跑一次）

按交接原样运行（未设 `SSL_CERT_FILE`）时 **5 个变体全部 URLError**：`http_status = null`、耗时 33～86 ms、**实际到达供应商的请求 0 个**。

根因（纯 TLS 握手复现，无模型调用）：本机 python.org Python 的默认信任库验证失败——`CERTIFICATE_VERIFY_FAILED: self-signed certificate in certificate chain`；同一句柄换用 certifi 的 CA 即握手成功（TLSv1.3）。这是 `claude-l09-handoff.md` 第 4 节记录的同一个坑。

**要报告的缺陷（未修，需 Claude 决定）**：`evaluation/probe_thinking.py` **完全没有证书兜底**（无 `SSL_CERT_FILE` / `certifi` / `ssl` 处理）。后果不只是「跑不起来」——它会把 5 次连接失败**静默写成 5 行 `accepted: false` 的记录**，任何人按交接原样跑都会误以为「所有字段都不被接受」。`scripts/check-embedding.py` 在 L09 就是为同一个坑加了 certifi 兜底，建议 `probe_thinking.py` 照做。

交接写「只跑一次，不重试」；我把情况（实际 0 token、未触及上限、失败发生在建立连接阶段而非供应商拒绝）连同选项交回用户，**用户明确选择带 `SSL_CERT_FILE` 重跑一次**后执行。第一次的输出保留在 `probe-attempt1-no-cert.jsonl`，未删除。

## 预算

| 项 | 值 |
| --- | --- |
| 开跑前系统计费口径 | 743806（记录口径 731690） |
| 第 1 次运行实际 | **0**（请求未发出；工具预估的 4110 不是用量） |
| 第 2 次运行实际 | **2551** |
| **跑完后系统计费口径** | **746357 / 5000000** |

本次调用直连供应商，**未进入 `model_calls`**，故按交接要求手工记入台账（上面的数字即台账更新值）。

## 未验证 / 限制

- **未判定可见回答是否合规 JSON**：工具只记录 `content_chars`（121），**不输出正文、也没有导出选项**（源码中 `content` 仅用于计数）。能确定的是 `finish_reason = stop`（正常结束，未被截断）。要判定格式需再发一次同变体请求并把正文落盘，约 50 token，**未做**，等用户决定。
- 单次请求、短提示、512 上限：只回答「字段是否生效」，**不代表**抽取或问答质量，也不代表长输出时的推理比例。
- **未测 `thinking_disabled` 在真实抽取/问答提示下的质量与耗时**（那是方案 B 实现后的复测）。
- 未探测交接之外的候选字段。
- 供应商是否长期支持该字段、是否影响单价，不在本次范围。

## api_and_data_changes

无。未启服务、未读写数据库、未改业务代码；本轮只有 5 次直连供应商的探测请求。测量 checkout 里 `.env` 与 `src/backend/storage/` 仍是上一轮同步进来的未跟踪文件（Git 忽略），本轮未改动。

## rollback

回退本提交（报告 + 两份 probe 输出 + 本文件）。

## next_action

1. **Claude 据此写 ADR 与实现**：字段取 `thinking: {"type": "disabled"}`；注意输入 token 也下降，估算口径要一起改。
2. **是否补测格式合规**（约 50 token）由用户决定。
3. **建议修 `probe_thinking.py` 的证书兜底**（照 `check-embedding.py`），否则该工具在本机默认用法下会产出误导性结果。
4. 推送与合并待用户授权。
