# 正式模式闭环：向量路径"上传前门禁"复测（交 DeepSeek harness）

```text
from: Claude
to: DeepSeek harness
date: 2026-10-09
code: 本地分支 claude/release-launcher-merge（未推送）
installation: 隔离安装 id 74694b2cb256134c（4 容器 healthy；不要重启、不要 down、不要删卷）
previous: docs/handoffs/deepseek-formal-embedding-network-20261009.md（你上一份报告，结论：宿主 TCP 出站路径是故障边界）
budget: 向量请求最多 10 次（每次一条很短的文本）；生成模型（DeepSeek）调用 0 次、0 token
paid_calls_by_claude: 0
```

## 1. 为什么要这份交接

你上一份报告测到向量路径在用户调整网络出口后恢复（09:32–09:33 全通）。但 Claude 在 **09:45** 复测时，容器到阿里云 4 个 IP 又全部 5 秒超时，产品自身客户端向量请求 `FAIL class=timeout`（60 秒）——路径**不稳定**。用户说网络由他来处理，需要向量测试时由你来跑。

业务闭环（上传 → 抽取 → 融合 → 持久化 → 审核 → 发布 → 学生问答）里，处理流水线和问答都会调用向量接口，产品**没有重试**，一次 `connection`/`timeout` 就会让任务或问答失败。所以 Claude 在上传前需要一个**明确的通过/不通过结论**，而不是单次成功。

## 2. 你要做的（只读 + 最多 10 次向量请求）

用户通知"网络已处理"后执行（Claude 会在对话里把时间告诉你；若没有通知，先不要执行）。命令需要 PATH 含 `/Applications/Docker.app/Contents/Resources/bin`。

**步骤 A：TCP 对照（不用密钥，不计向量次数）**
- 宿主：`nc -z -G 8 -v dashscope.aliyuncs.com 443` 连续 3 次；
- 容器：在 `smartsketch-74694b2cb256134c-api-1` 内用 Python 标准库对 `dashscope.aliyuncs.com` 解析出的全部地址各做一次 `create_connection(..., timeout=5)`，记录每个地址的结果与耗时；
- 对照：`api.deepseek.com:443` 从宿主和容器各一次。

**步骤 B：产品自身客户端的向量请求，共 3 次，间隔约 20 秒**
沿用你上一份报告 §4 第 2 步的脚本（读取容器环境里的 `EMBEDDING_*`，**不打印密钥**，只输出 `ok model=… dimensions=… seconds=…` 或 `FAIL class=… seconds=…`）。

**步骤 C：稳定性探测，仅 TCP（不发向量请求）**
从 API 容器对阿里云解析出的**第一个地址**，每 15 秒做一次 `create_connection(timeout=5)`，持续 5 分钟（约 20 次），记录每次 `ok`/`timeout` 与耗时，最后给出成功率与最长连续失败次数。

## 3. 判定（请照此给结论，不要放宽）

| 项 | 通过条件 |
| --- | --- |
| A | 宿主 3/3 成功；容器全部地址成功；对照主机成功 |
| B | 3/3 为 `ok`，维度 1024，耗时均 < 3 秒 |
| C | 成功率 ≥ 95%，且**没有连续 2 次及以上失败** |

三项全部满足 → `GATE: PASS`；任何一项不满足 → `GATE: FAIL`，并写出是哪一项、实测数值。**不要**因为"偶发"就判通过：产品没有重试，偶发失败在业务闭环里就是任务失败。

## 4. 边界

- 不改产品代码、测试、契约、迁移、启动器、`.env.example`、默认配置；不提交、不推送、不合并、不发布。
- `LLM_MODE=personal`、`EMBEDDING_MODE=online`、`text-embedding-v4`、1024 维、基址不得改；不得降级成 `demo`/`fake`/`local`。
- 不读、不打印、不复制安装目录里 `.env` 的任何内容；报告里只含状态、错误类别、耗时、维度、主机名。
- 不要修改用户的系统网络设置或 Docker Desktop 设置；需要用户做的事写成步骤。
- 出现 `auth` 类错误：停止并报告，不重试。
- 不要动其他 Docker 资源，不要重启 Docker Desktop，不要 `down -v`。

## 5. 交付物

写 `docs/handoffs/deepseek-formal-embedding-baseline-20261009.md`（同样先落在 worktree，再同步一份到主仓 `docs/handoffs/`）。**第一行必须是 `GATE: PASS` 或 `GATE: FAIL`**，其后是：

1. 步骤 A/B/C 的原始记录表（时间、命令、输出、耗时；失败也写）；
2. 步骤 C 的成功率与最长连续失败；
3. 若 FAIL：失败发生的时间点、与用户通知时间的关系，以及给用户的下一步建议（不要自行实施）；
4. 向量请求累计次数，以及"未读/未打印密钥"的声明。

## 6. 之后

`GATE: PASS` → Claude 立即开始业务闭环：用仓库示例章节 `datasets/demo/ch3-stack-queue.md`（约 11.5 KiB）上传 → 抽取 → 审核 → 发布 → 学生问答。Claude 会按 `model_calls` 累计用量，在 100 万 token 上限前停下。
`GATE: FAIL` → Claude 不上传资料，等待用户处理网络后重新交接。
