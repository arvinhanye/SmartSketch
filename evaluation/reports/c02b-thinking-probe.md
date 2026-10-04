# C02b 思考控制参数探测（2026-10-04）

> **状态：完成。找到一个有效字段：`thinking: {"type": "disabled"}`。** 真实供应商 DeepSeek `deepseek-flash`，5 个变体各 1 次请求，`--max-tokens 512`、cap 5000。第一次运行因本机证书问题**一个请求都没发出去**（见第 5 节），经用户确认后带 `SSL_CERT_FILE` 重跑一次；下面第 2 节是重跑的真实结果。

## 1. 命令与版本

```bash
# 测量 checkout：claude/plan-c-reliability（HEAD ef39f98，工作区干净）
mkdir -p evaluation/raw/c02b
export SSL_CERT_FILE="$(.venv/bin/python -c 'import certifi; print(certifi.where())')"
export PROBE_KEY="$(从 .env 按行读出 LLM_API_KEY，不回显)"      # 密钥只在环境变量里
.venv/bin/python evaluation/probe_thinking.py --base-url https://api.deepseek.com \
    --model deepseek-flash --key-env PROBE_KEY --cap 5000 --max-tokens 512 \
    > evaluation/raw/c02b/probe.jsonl
# exit 0
unset PROBE_KEY
```

- base URL 用 `https://api.deepseek.com`（工具在其后拼 `/chat/completions`）——**与应用个人配置里保存的地址完全一致**，所以探测的是应用实际会打的那条路径。
- 只允许 https，未加 `--allow-http`；密钥未出现在命令行、日志、报告或提交里。

## 2. 逐变体结果

提示词是一条抽取指令（要求只输出 `{"entities": [{"name": …, "type": …}]}` 的 JSON），输入估算约 96 token。

| 变体 | 附加字段 | 被接受 | HTTP | 输入 | 输出 | 推理 token | 推理字数 | 可见字数 | `finish_reason` | 耗时 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `baseline` | 无（对照） | ✓ | 200 | 96 | **512**（撞顶） | 512 | 1121 | **0** | `length` | 2895 ms |
| **`thinking_disabled`** | `thinking:{"type":"disabled"}` | ✓ | 200 | **70** | **49** | **null** | **0** | **121** | **`stop`** | **513 ms** |
| `enable_thinking_false` | `enable_thinking:false` | ✓ | 200 | 96 | **512**（撞顶） | 512 | 1692 | **0** | `length` | 2766 ms |
| `chat_template_enable_thinking_false` | `chat_template_kwargs:{"enable_thinking":false}` | ✓ | 200 | 96 | **512**（撞顶） | 512 | 1657 | **0** | `length` | 2685 ms |
| `reasoning_effort_low` | `reasoning_effort:"low"` | ✓ | 200 | 96 | **512**（撞顶） | 512 | 1077 | **0** | `length` | 2598 ms |

没有变体被拒（无 400/422），因此**「被接受」不能区分有效与否，只有效果能**。

## 3. 结论

**唯一有效字段是 `thinking: {"type": "disabled"}`。** 它与其余四个变体的差别是全面的，不是程度差异：

| 指标 | baseline（及其余三个无效变体） | `thinking_disabled` | 变化 |
| --- | --- | --- | --- |
| 推理字数 | 1121（无效变体 1077～1692） | **0** | 归零 |
| 推理 token | 512 | **null**（未返回） | 归零 |
| 输出 token | 512 = 上限，**被截断** | **49** | −90% |
| 可见内容 | **0 字**（全被推理吃掉） | **121 字** | 从无到有 |
| `finish_reason` | `length`（截断） | **`stop`**（正常结束） | — |
| 耗时 | 2598～2895 ms | **513 ms** | 快约 5 倍 |
| 输入 token | 96 | **70** | −26（见下） |

补充观察：

1. **输入 token 也少了 26**（96 → 70）。同一段提示词，只有附加字段不同，说明关闭思考后请求体本身不同（很可能不再注入推理相关的模板/前缀）。实现时应以「输入 + 输出都显著下降」记账，不要只按输出估算。
2. **baseline 本身就是 C02-1 推断的最小复现**：一条 96 token 的短提示、512 上限，模型把**全部 512 个输出 token 花在推理上**，可见内容 0 字、`finish_reason = length`。这与 C03-1 在真实抽取链路上观察到的「输出 80% 是推理、两次关系调用 4096 输出全是推理 → 截断 → repair」是同一现象，只是这次被压缩到一个请求里。
3. `enable_thinking: false`、`chat_template_kwargs.enable_thinking: false`、`reasoning_effort: "low"` 三个字段**被静默忽略**：HTTP 200、无报错、行为与 baseline 无差别。这正是交接要避免的「猜参数」——它们在语法上都被接受，只有实测能看出无效。

## 4. 可见回答是否仍是合规 JSON

**未判定。** 工具只记录 `content_chars`（本次 121），**不输出正文，也没有任何导出正文的选项**（源码里 `content` 仅用于算长度）。因此从本探测的输出**无法**判断那段 121 字是否是合规 JSON。

能确定的是：`finish_reason = stop` 表示这次生成正常结束、没有被上限截断——这是四个被截断的变体做不到的。要判定格式合规，需再发一次同变体请求并把正文落盘，约 50 token；**未做**，等用户决定。

## 5. 第一次运行：全部 URLError（环境缺陷，不是供应商结果）

第一次按交接原样运行（未设 `SSL_CERT_FILE`）时，**5 个变体全部失败**：

| 字段 | 值 |
| --- | --- |
| `http_status` | `null`（从未建立连接） |
| `error_type` | `URLError` |
| 耗时 | 33～86 ms（立即失败，不是超时） |
| 实际到达供应商的请求 | **0** |

根因（已用纯 TLS 握手复现，不产生任何模型调用）：

| 检查 | 结果 |
| --- | --- |
| `probe_thinking.py` 是否处理证书 | **完全没有**（无 `SSL_CERT_FILE` / `certifi` / `ssl` 相关代码） |
| 默认 TLS 上下文握手 `api.deepseek.com:443` | **失败**：`CERTIFICATE_VERIFY_FAILED: self-signed certificate in certificate chain` |
| 用 certifi 的 CA 握手 | **成功**（TLSv1.3） |

这是本机已知的坑（`claude-l09-handoff.md` 第 4 节）：python.org 的 Python 在此机器上不用系统信任库，链里有自签证书。应用自己的启动脚本会设 `SSL_CERT_FILE`，所以应用侧一直正常；`probe_thinking.py` 没有这个兜底，于是**静默地把 5 次「连接失败」写成了 5 行看起来像结果的记录**。

**这是工具的缺陷，建议修**（不是我改的）：`scripts/check-embedding.py` 在 L09 就是为同一个坑加了 certifi 兜底，`probe_thinking.py` 应照做；否则任何人在本机直接跑，都会拿到 5 行 `accepted: false` 而误以为「所有字段都不被接受」。

第一次运行的实际花费是 **0 token**（TLS 握手未完成，请求没发出去）；工具汇总里的 `tokens_used: 4110` 是它按最坏情况做的**预估值**，不是用量。

## 6. 预算

| 项 | 值 |
| --- | --- |
| 交接给的开跑前系统计费口径 | 743806（记录口径 731690） |
| 第 1 次运行（无证书）实际 | **0**（请求未发出；工具预估 4110 不作数） |
| 第 2 次运行（带证书）实际 | **2551**（工具汇总 `tokens_used`） |
| **跑完后系统计费口径** | 743806 + 2551 = **746357 / 5000000** |

两次合计实际 2551，未触及本轮 5000 上限（`stopped: null`）。

## 7. 证据路径

| 内容 | 路径 |
| --- | --- |
| 真实结果（第 2 次运行） | `evaluation/raw/c02b/probe.jsonl` |
| 第 1 次运行原始输出（全 URLError，保留备查） | `evaluation/raw/c02b/probe-attempt1-no-cert.jsonl` |

两个文件都只含状态、错误类型、usage、字数与耗时，不含密钥，也不含供应商错误原文。

## 8. 限制与未验证

- **只回答「哪个字段生效」**：单次请求、短提示、512 上限，**不代表**抽取或问答的质量，也不代表长输出时的推理比例。
- **未验证 `thinking_disabled` 在长输出/真实抽取提示下的表现**：按 C03-1 的量级，关闭思考后输出预算的占用会显著下降，但实际质量与耗时要另测（Claude 的 ADR 与实现之后再定）。
- **未判定可见回答是否合规 JSON**（工具不输出正文，见第 4 节）。
- 未探测其它候选字段（如 `reasoning: {enabled: false}`、`thinking_budget: 0`）；本次只跑交接列出的 5 个变体。
- 供应商是否对 `thinking_disabled` 长期支持、以及是否影响计费单价，不在本次范围。
