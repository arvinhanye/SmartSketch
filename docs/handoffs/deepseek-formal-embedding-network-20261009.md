# 正式模式向量网络：故障定位与恢复验证（阿里云百炼从容器不可达 → 已恢复）

```text
from: DeepSeek harness
to: Claude（接手 formal-mode 闭环）
date: 2026-10-09
repo: /Users/arvinhan/SmartSketch/.claude/worktrees/smartsketch-frontend-ux-672666 @ claude/release-launcher-merge
task: docs/handoffs/claude-formal-embedding-network-deepseek-handoff.md
installation: 隔离安装 id 74694b2cb256134c（4 容器均 healthy，未重启、未 down、未删卷）
向量请求用量: 8 次成功中的 7 次 + 1 次偶发 connection 失败 = 8 次（预算 20 次）
对话/抽取 token: 0
auth 类错误: 0
密钥/口令/令牌泄漏: 0（全程未打印任何密钥；报告只含状态码、错误类别、耗时、端口、维度、主机名）
产品代码/启动器/默认配置改动: 0
```

## 0. 结论摘要

- **原因落在宿主机出站路径（TCP 层），不在容器、不在 Docker 网络配置、不在 DNS/TLS/密钥。**
- **用户在本任务进行中调整了本机网络环境**（约 09:29–09:31），调整后宿主与容器去往 `dashscope.aliyuncs.com` 的路径**同时恢复**。
- 恢复后以产品自身客户端与配置实测：向量调用成功、维度 1024、耗时 0.57–0.69 秒，**连续可用**（仅 1 次偶发 `connection` 失败，见 §1.7）。
- 正式模式配置未被改动：`LLM_MODE=personal`、`EMBEDDING_MODE=online`、`text-embedding-v4`、1024 维、基址 `https://dashscope.aliyuncs.com/compatible-mode/v1`。
- **向量路径已可用于继续正式模式闭环**；业务闭环（上传→审核→发布→问答）本任务未跑，留给 Claude。

## 1. 逐项测量表

时间：宿主 `-0400`（UTC−4）。全部为只读测量。

地址记号：下表用 **A–D** 指代 `dashscope.aliyuncs.com` 当次解析出的 4 个地址（每行都标注了对应关系，与宿主、容器两侧一致）。为降低报告的网络指纹，不展开字面地址。

### 1.1 调整前：宿主 → `dashscope.aliyuncs.com`（按 4 个解析地址，`-G 6`）

```bash
nc -z -G 6 -v <地址> 443      # <地址> 逐个取当次解析出的 4 个地址
```

| 目标 | 输出 | 耗时 | 结论 |
| --- | --- | --- | --- |
| 地址 A | `connectx ... failed: Operation timed out` | 6.14s | 不通 |
| 地址 B | `connectx ... failed: Operation timed out` | 6.65s | 不通 |
| 地址 C | `connectx ... failed: Operation timed out` | 6.08s | 不通 |
| 地址 D | `connectx ... failed: Operation timed out` | 6.08s | 不通 |

域名级复测（`2026-10-09T09:28:50-0400`）连续 3 次全部超时，每次约 32 秒（nc 对多地址逐个尝试）：

| 次数 | 输出 | 耗时 |
| --- | --- | --- |
| 1 | `connectx to dashscope.aliyuncs.com port 443 (tcp) failed: Operation timed out` | 32.28s |
| 2 | 同上 | 32.08s |
| 3 | 同上 | 32.30s |

### 1.2 调整前：宿主 → 对照主机（同一时间窗）

| 目标 | 输出 | 耗时 | 结论 |
| --- | --- | --- | --- |
| `api.deepseek.com:443` | `succeeded!` | 0.47s | 通 |
| `www.apple.com:443` | `succeeded!` | 0.73s | 通 |
| `registry.npmjs.org:443` | `succeeded!` | 1.58s | 通 |
| `github.com:443` | `succeeded!` | 0.69s | 通 |

**关键对照**：同一时刻这 4 个其他主机全部可达，唯阿里云 4 个地址全超时 → 不是"本机整体断网"，是去往阿里云这条**具体路径**被挡。

### 1.3 调整前：DNS 与容器侧事实

| 项 | 命令 | 输出 | 结论 |
| --- | --- | --- | --- |
| 宿主 DNS | `dig +short dashscope.aliyuncs.com` | CNAME `gtm-cn-rt54j1mlg03.dashscope.aliyuncs.com.` → 4 个 IP | DNS 正常 |
| 容器 DNS | 容器内 `socket.gethostbyname_ex` | 同 4 个阿里云地址，解析正常 | DNS 正常，与宿主一致 |
| 容器 TLS | 容器内 `ssl.create_default_context().wrap_socket` | 调整前后对比见 §1.5 | TLS 层本身无问题 |
| Docker 守护进程代理 | `docker info` | `HTTP Proxy/HTTPS Proxy = http.docker.internal:3128`、`No Proxy = hubproxy.docker.internal` | 仅守护进程用，与容器业务流量无关 |
| 容器代理环境变量 | `env \| grep -i proxy` | **无任何代理变量** | 产品容器不读代理 |
| 系统代理（调整前） | `scutil --proxy` | 仅 `FTPPassive : 1`（无 HTTP/HTTPS 代理） | 本机未启用系统代理 |

### 1.4 调整后：宿主 → 阿里云（恢复验证，共 6 次）

```bash
nc -z -G 8 -v dashscope.aliyuncs.com 443
```

| 批次 | 时间 | 输出 | 耗时 |
| --- | --- | --- | --- |
| 按 IP（4 个） | 09:32:29 | 4/4 `succeeded!` | 0.08 / 0.07 / 0.08 / 0.07s |
| 域名 ×3 | 09:33:08 | 3/3 `succeeded!` | 0.09 / 0.10 / 0.10s |
| 域名 ×3（收尾复测） | 09:33:37 | 3/3 `succeeded!` | 0.15 / 0.10 / 0.09s |

从 32 秒超时变为 0.1 秒级成功，且**跨 3 个时间点稳定**。

### 1.5 调整后：容器 → 阿里云（TCP + 产品同款 TLS）

TCP（容器内 `socket.create_connection`，`timeout=6`）：

| 目标 | 输出 | 耗时 |
| --- | --- | --- |
| 地址 A | OK | 0.13s |
| 地址 B | OK | 0.05s |
| 地址 C | OK | 0.06s |
| 地址 D | OK | 0.05s |

TLS（容器内，复刻产品口径：`ssl.create_default_context()` + `wrap_socket(server_hostname='dashscope.aliyuncs.com')`）：

```text
CA 文件: /usr/lib/ssl/cert.pem | 证书数: 150
地址 A    TLS OK TLSv1.3 TLS_AES_256_GCM_SHA384 notAfter=Nov  2 08:06:18 2026 GMT 0.13s
地址 B    TLS OK TLSv1.3 TLS_AES_256_GCM_SHA384 notAfter=Nov  2 08:06:18 2026 GMT 0.13s
地址 C    TLS OK TLSv1.3 TLS_AES_256_GCM_SHA384 notAfter=Nov  2 08:06:18 2026 GMT 0.14s
地址 D    TLS OK TLSv1.3 TLS_AES_256_GCM_SHA384 notAfter=Nov  2 08:06:18 2026 GMT 0.13s
```

4/4 握手成功、证书链校验通过（**未**使用 `verify_mode=CERT_NONE`，未降低校验）。

### 1.6 调整后：产品自身视角（容器内，读取容器 `EMBEDDING_*`，不打印密钥）

配置回显（非敏感字段）：`mode=online model=text-embedding-v4 dims=1024 base=https://dashscope.aliyuncs.com/compatible-mode/v1`。

调用方式：容器内 `sys.path` 指向 `/app/src/backend`，用产品自己的 `load_settings` / `build_embedding_client` / `EmbeddingRequest`，文本为一条课程短句。

| 次序 | 时间 | 结果 | 维度 | 耗时 |
| --- | --- | --- | --- | --- |
| 1 | 09:32:5x | `ok model=text-embedding-v4 dimensions=1024` | 1024 | 0.62s |
| 2 | 09:33:15 | ok | 1024 | 0.60s |
| 3 | 09:33:15 | ok | 1024 | 0.69s |
| 4 | 09:33:15 | ok | 1024 | 0.61s |
| 5 | 09:33:41 | **FAIL class=connection** | — | — |
| 6 | 09:33:53 | `ok model=text-embedding-v4 dimensions=1024` | 1024 | 0.58s |
| 7 | 09:33:53 | ok | 1024 | 0.57s |
| 8 | 09:33:53 | ok | 1024 | 0.57s |

第 5 次是**偶发**：同一条命令紧接着连跑 3 次全部成功（第 6–8 次），且产品配置、环境变量、执行方式完全一致（两种执行方式的代理/证书变量均为空，已对照确认）。

标准脚本口径（`scripts/check-embedding.py` 原文，容器镜像内无 `scripts/` 目录，故按原文送入容器、仅将根路径解析改为 `/app`，脚本逻辑未改写）：

```text
ok model=text-embedding-v4 dimensions=1024 seconds=0.58   → exit 0
ok model=text-embedding-v4 dimensions=1024 seconds=0.57   → exit 0
ok model=text-embedding-v4 dimensions=1024 seconds=0.57   → exit 0
```

与 L09 基线（`2026-10-03`：`dimensions=1024 seconds=0.66`）一致。

### 1.7 调整后：经 Docker Desktop 代理（链路对照，不带密钥）

容器内（`http.docker.internal` 只在容器内注入）：

```text
https://dashscope.aliyuncs.com   HTTP=404 0.30s
https://api.deepseek.com         HTTP=401 0.34s
```

404/401 均为"链路通、仅路径/凭据未带"的预期状态。

宿主侧同一测试**不可执行**：

```text
curl: (5) Could not resolve proxy: http.docker.internal
HTTP=000 0.065754s
```

`http.docker.internal` 是 Docker Desktop 注入容器 DNS 的内部名，宿主机不解析——记录为环境事实，非故障。

### 1.8 调整后：候选入口与其他地址对照

宿主：

| 目标 | 输出 | 耗时 |
| --- | --- | --- |
| `dashscope.aliyuncs.com:443` | `succeeded!` | 0.11s |

产品配置实际使用的入口 `dashscope.aliyuncs.com` 已直连可用，**本次未发现需要更换入口**，故未进一步枚举同供应商的其他域名。

容器内 DNS（只记解析结果是否正常，不展开地址清单）：

```text
dashscope.aliyuncs.com → 解析成功（4 个地址，与宿主一致）
api.deepseek.com       → 解析成功（3 个地址）
```

### 1.9 用户系统网络状态（只读，未做任何修改）

| 项 | 命令 | 输出 |
| --- | --- | --- |
| 系统代理 | `scutil --proxy` | 仅 `ExceptionsList(*.local, 169.254/16)`、`FTPPassive:1`；**无 HTTP/HTTPS 代理** |
| 默认路由 | `route -n get default` | `interface en0`（网关地址已隐去） |
| 去阿里云路由 | `route -n get <阿里云地址>` | 与默认路由同接口 `en0`，**未走 utun** |
| en0 类型 | `networksetup -getairportnetwork en0` | 非 Wi-Fi 关联（该接口不是无线接口）——仅用于判断出站接口归属，不展开 |
| utun 接口 | `ifconfig` | utun0–utun7 均 `UP,POINTOPOINT,RUNNING`（存在隧道类接口；当前去阿里云的路由**未**经过它们） |

> 说明：以上仅陈述读到的现象，**未做任何修改**；恢复前后这些项都无可见变化。

## 2. 原因分类

| 层 | 判定 | 证据 | 性质 |
| --- | --- | --- | --- |
| DNS | **正常，排除** | 宿主与容器均解析出 4 个地址，两侧一致；调整前后解析结果不变 | 实测 |
| TCP 连接 | **故障层（已定位于此）** | 调整前宿主 4/4、容器 2/2 均 `Operation timed out`（容器 8 秒、宿主 6 秒）；调整后同一批地址 4/4 成功（0.05–0.15 秒） | 实测 |
| TLS | **正常，排除** | 恢复后容器内产品同款握手 4/4 成功，证书链在默认信任库（150 张 CA）下校验通过，`notAfter=2026-11-02` | 实测 |
| 代理 | **不是故障原因** | 容器无任何代理环境变量；`scutil --proxy` 未启用系统代理；Docker 守护进程代理只服务于镜像拉取。调整前后**都没变**，而故障消失了 → 代理不是变量 | 实测 |
| HTTP 状态 | **正常** | 经 Docker 代理 `dashscope`→404、`deepseek`→401（未带凭据的预期码）；产品实调直接返回向量 | 实测 |
| `auth` | **未出现（0 次）** | 全程 0 个鉴权类错误；密钥从未被打印 | 实测 |
| 故障层级在宿主而非容器 | **实测确认（推翻原推断）** | ①调整前**宿主**去阿里云同样 4/4 超时；②宿主网络一恢复，**同一容器、未重建、未改配置**立即恢复 → 宿主机出站路径是故障边界 | 实测 |
| "Docker 容器没走代理所以被挡" | **推断被推翻** | 宿主机没有系统代理却在调整后立刻可用，说明当时也不需要代理。原推断的隐含前提（"阿里云不通 → 容器出站被整体限制"）也站不住：调整前容器对 `api.deepseek.com` 一直是可达的（其解析地址与阿里云无关），说明容器出站并非整体被挡，只是去阿里云那条路径不通 | 实测反证 |
| 用户具体改了什么 | **未知（推断）** | 恢复前后系统代理、默认路由接口、DNS 均无可见变化；本任务无从读取该改动 | 推断，待用户确认 |

**一句话**：这是**宿主级 TCP 出站路径**问题（去往阿里云的直连路径被挡），容器只是被动继承；不是容器网络配置、不是 DNS/TLS、不是密钥、不是产品问题。

## 3. 方案清单（均未由本任务实施；方案一为已发生的既有事实）

| # | 方案 | 谁需要做什么 / 产品需要改什么 | 风险 | 是否越过边界 | 预计效果 |
| --- | --- | --- | --- | --- | --- |
| 1 | **调整宿主网络出站路径**（已由用户完成） | 用户侧：保持/选择能直连阿里云的出口路径。无需产品改动 | 出口变化后可能复发；用户需自行判断用哪个出口 | 否（用户对自己机器操作） | **已验证**：向量调用 0.57–0.69 秒成功，连续可用 |
| 2 | **给容器加 Docker Desktop 代理环境变量** | 用户侧在 Docker Desktop 设置 `HTTP_PROXY/HTTPS_PROXY`，Compose 透传到容器 | 对**产品出站无用**：产品用标准库 `socket`+`http.client`（`services/ai/compatible.py`），**不读** 代理环境变量；仅能改善容器内调试工具（curl/pip） | 改环境不改产品，**但会误导为"已修复"** | 对产品向量调用**无效**；不推荐作为修复手段 |
| 3 | **宿主机加系统代理/透明代理/分流** | 用户侧配置系统代理或路由/分流规则 | 同样**对产品无效**（产品不读 `HTTPS_PROXY`，只被路由/透明代理影响）；透明代理还需处理 TLS 见证证书，反而可能引入校验失败 | 否（用户系统设置） | 只有在改变**路由**（非环境变量）时才对产品生效，效果等同方案 1 |
| 4 | **改用同一供应商的其他可达入口** | 需产品侧改 `EMBEDDING_BASE_URL` | 越界（规格：不得改写向量地址/供应商/模型/维度） | **是**（仅评估，不采用） | 本次未发现需要它：产品配置的入口 `dashscope.aliyuncs.com` 已直连可用（0.11 秒），无需枚举其他域名 |
| 5 | **产品增加受控出站代理支持** | 产品侧：`GuardedTransport` 增加按配置走 HTTP CONNECT 代理 | 改变产品网络行为；ADR-080 出站校验（公网地址、DNS 固定、TLS 主机校验、禁重定向、响应大小限制）需重新论证；新增配置项与文档 | **是**（仅评估，不采用） | 能让"必须经代理出网"的环境可用；本次**不需要**——直连已通 |
| 6 | **给向量调用加自动重试** | 产品侧：向量客户端目前**无重试**（`services/ai/embeddings.py` 无 retry 路径），一次 `connection` 失败即整任务失败 | 正式模式语义是"失败即报告"（ADR-081），加重试需定次数/退避与是否计入预算 | **是**（仅评估，不采用） | 可吸收本次观测到的偶发 `connection`（1/8，12.5%） |

## 4. 给用户的可执行步骤

**向量路径当前已可用，无需再修即可继续正式模式闭环。** 建议按以下顺序做：

1. **确认仍在可用的网络出口上**（别切回调整前的那个出口）。在终端执行：

   ```bash
   nc -z -G 8 -v dashscope.aliyuncs.com 443
   ```

   **预期输出**：`Connection to dashscope.aliyuncs.com port 443 [tcp/https] succeeded!`，耗时约 0.1 秒。
   若再次出现 `Operation timed out`（约 8 秒或更久），说明出口又挡住了，**不要上传资料**，先切回可用出口。

2. **确认产品向量路径（决定性的那一步）**。需要 PATH 含 Docker：

   ```bash
   export PATH="/Applications/Docker.app/Contents/Resources/bin:$PATH"
   docker exec -i smartsketch-74694b2cb256134c-api-1 python - <<'PY'
   import os, sys, time
   sys.path.insert(0, "/app/src/backend")
   from app.config import load_settings, embedding_model_id
   from app.services.ai.client import EmbeddingRequest, ModelCallError
   from app.services.ai.factory import build_embedding_client
   s = load_settings(dict(os.environ))
   c = build_embedding_client(s)
   t = time.monotonic()
   try:
       r = c.embed(EmbeddingRequest(model=embedding_model_id(s), texts=("栈是后进先出的线性表",), dimensions=s.EMBEDDING_DIMENSIONS))
       print(f"ok model={r.model_responded or r.model_requested} dimensions={len(r.vectors[0])} seconds={time.monotonic()-t:.2f}")
   except ModelCallError as e:
       print(f"FAIL class={e.error_class.value} seconds={time.monotonic()-t:.2f}")
   PY
   ```

   **预期输出**：`ok model=text-embedding-v4 dimensions=1024 seconds=0.5~0.7`。
   - 若 `FAIL class=timeout`：出口又被挡（回到第 1 步）。
   - 若 `FAIL class=connection`：**先重跑一次**——本任务观测到偶发 `connection`（1/8），产品无重试。
   - 若 `FAIL class=auth`：**停止**，不要重试，按 §5 交人工处理（密钥问题不在本任务范围）。

3. **然后**再让 Claude 继续正式模式闭环（上传仓库示例章节 → 审核 → 发布 → 学生问答，100 万 token 熔断）。上传前建议先跑第 2 步确认仍是 `ok`。

4. **如果出口无法长期稳定**（例如必须频繁切换网络），再决定是否采纳 §3 的方案 5（产品加受控代理支持）或方案 6（加重试）——这两项都需要产品侧决策与文档更新，**不要**在闭环验收期间顺手改。

## 5. 未验证项与待决定事项

**未验证（不要当成已证实）**：

1. **用户具体改了什么网络设置**：只读到现象（恢复前后系统代理、默认路由接口、DNS 均无可见变化），未读 Docker Desktop 图形设置页内容。请用户补充一句改了什么，便于写进闭环记录。
2. **偶发 `connection` 失败的根因**：8 次中 1 次，样本太少，不能归因于链路/服务端/超时预算。产品自身**无重试**，该偶发会直接表现为任务失败。
3. **调整前的历史失败率**：网络已恢复，无法复测"必然超时"时代的失败分布。
4. **宿主经 Docker 代理的对照**：`http.docker.internal` 在宿主侧不解析，该对照只在容器内完成。
5. **业务闭环未跑**：本任务只验证到"向量调用可用"，未跑上传→审核→发布→问答；也未做端到端任务进度验证（按交接要求未让用户上传资料）。

**需要 Claude 或用户决定的事**：

1. **是否接受"正式模式依赖用户手动保持可用出口"**：若不可接受，则需产品侧方案（§3 方案 5/6），属产品决策而非环境修复。
2. **偶发失败要不要产品侧重试**：需要 ADR-081"失败即报告"语义下的取舍（重试次数、退避、是否计入 token/调用预算）。
3. **本报告的落盘位置**：写入 worktree `docs/handoffs/`（Claude 主场、可用于 PR）并同步一份到主仓 `docs/handoffs/`。未提交、未推送。
4. **闭环下一步的证据口径**：建议 Claude 在上传前先跑 §4 第 2 步，把 `ok ... seconds=` 那一行记为本次闭环的向量基线。

## 6. 遵守边界的声明

- 未改产品代码、测试、契约、迁移、启动器、`.env.example`、默认配置；未提交、未推送、未合并、未发布。
- 未改 `LLM_MODE=personal` / `EMBEDDING_MODE=online`；未改写向量地址、未换供应商/模型/维度。
- 未启用任何降级（`demo`/`fake`/`local`）。
- 未读、未打印、未复制 `.env` 中任何密钥；容器内只输出配置的**非敏感**字段。
- 未重启 Docker Desktop；未动其他 compose 项目的卷与容器；未 `down -v`、未删卷。
- 本任务仅使用只读测量命令；唯一的"写入"是这份报告文件。
