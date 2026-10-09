# 正式模式闭环：向量服务（阿里云百炼）从容器内连不上，交 DeepSeek harness 定位

```text
from: Claude
to: DeepSeek harness
date: 2026-10-09
code: 本地分支 claude/release-launcher-merge @ 43939b7（未推送；启动器分支已合入当前 main）
installation: 隔离安装 id 74694b2cb256134c，镜像 rc-43939b7（ghcr 摘要见 packaging/release-manifest.rc-43939b7.json）
budget: 生成模型（DeepSeek 对话/抽取）调用 0 次、0 token；向量请求最多 20 次，每次一个很短的文本，且只用来定位网络问题
paid_calls_by_claude: 0
```

## 1. 背景与目标

正在对**要交付的正式模式软件**做闭环验收：真实启动器 + 安装向导 + 个人模型 API（DeepSeek）+ 在线向量（阿里云百炼 `text-embedding-v4`，1024 维）。用户已在向导里填好向量服务、在网页里保存了自己的 DeepSeek API，软件已启动、4 个容器健康。

**问题**：上传资料后，处理流水线的向量阶段会调用百炼向量接口；从 Docker 容器里到百炼的网络不通，向量调用必然超时。用户事先就预料到网络环境会有这个问题，要求出现时交给你处理。

**你的目标**：定位这条网络路径为什么不通，给出**有证据的**原因分类和可选方案；能在环境层面（不改产品代码）恢复的，给出用户可执行的确切步骤。**不要自行改产品代码、启动器、默认配置，也不要换向量供应商或改写向量地址来绕过**（见第 5 节）。

## 2. Claude 已测到的事实（均为只读测量，未使用任何密钥）

在 API 容器 `smartsketch-74694b2cb256134c-api-1` 里用 Python 标准库测：

| 目标 | 结果 |
| --- | --- |
| `api.deepseek.com` | DNS 解析 `3.173.21.63`，TCP 443 **0.46 秒连通** |
| `dashscope.aliyuncs.com` DNS | 0.3 秒解析成功，返回 `39.96.198.249`、`39.96.213.166`、`8.140.217.18`、`8.152.159.24` 等 |
| `dashscope.aliyuncs.com` TCP 443 | `39.96.198.249` **8 秒超时**；`39.96.213.166` **8 秒超时**（其余两个地址未单独测） |
| 第一次整体测试 | `socket.create_connection` 对该主机总共等了 **80.3 秒后超时**（按多个地址各 10 秒顺序尝试） |
| Docker Desktop 代理设置 | `docker info`：`HTTPProxy/HTTPSProxy = http.docker.internal:3128`，`NoProxy = hubproxy.docker.internal` |
| 容器内代理环境变量 | API 容器里**没有** `HTTP(S)_PROXY`/`NO_PROXY`；`/etc/resolv.conf` 是 Docker 生成的 |
| 镜像拉取 | 经守护进程从 ghcr 匿名拉取成功（守护进程走了上面的代理） |

**结论（尚未证实的推断）**：DNS 正常、TCP 到阿里云（中国大陆）IP 超时，而境外的 DeepSeek 直连正常。容器的出站流量没有走 Docker Desktop 的代理，直连阿里云的这条路径被网络环境挡住。**这只是线索，需要你用对照实验确认或推翻。**

## 3. 还没测的（你来补）

1. **宿主机（Mac）到 `dashscope.aliyuncs.com:443`** 是否通：如 `nc -z -G 8 dashscope.aliyuncs.com 443`。Claude 的沙箱 shell 无法访问外网，没法测宿主。
2. **经 Docker 代理**：`curl -x http://http.docker.internal:3128 -sS -o /dev/null -w '%{http_code} %{time_total}\n' https://dashscope.aliyuncs.com`（只看握手/HTTP 状态，不带密钥，401/404 都说明链路通）。分别从一个临时容器和宿主测。
3. **同一时间段重复测**：区分"持续被挡"和"偶发慢"；至少 3 次，记录每次时间。
4. **其余两个地址**与 `8.140.217.18`、`8.152.159.24` 的 TCP 结果。
5. **产品自身视角**：在 API 容器里用容器环境里的 `EMBEDDING_*` 发 **1 个**很短文本的向量请求（读取 `os.environ`，**绝不打印密钥**，只输出 HTTP 状态/错误类别/耗时/维度）。对照 `scripts/check-embedding.py` 的口径（成功 `ok model=… dimensions=… seconds=…`；失败按 `auth` / `connection` / `timeout` / `invalid_request` 分类）。
6. **用户是否使用系统代理/VPN/特殊路由**：只描述现象与你能从系统设置里读到的（`scutil --proxy`、Docker Desktop 的网络/代理设置页），**不要修改**；需要用户操作的，写成步骤交给用户。

## 4. 环境（隔离安装，不要碰其他东西）

- 隔离安装目录（launcher 的 `HOME` 被重定向，**不是**用户原来的 `~/Library/Application Support/SmartSketch`）：
  `/private/tmp/claude-501/-Users-arvinhan-SmartSketch--claude-worktrees-smartsketch-frontend-ux-672666/e5ef6382-476e-4370-af0b-f5470ea7d918/scratchpad/p3/home/Library/Application Support/SmartSketch/`
  其中的 `.env` 含用户的向量密钥与随机凭据：**不得 `cat`、打印、复制或写进任何报告**；需要时只用 `grep -c`/`wc` 之类判断键是否存在。
- 容器（compose 项目 `smartsketch-74694b2cb256134c`）：`…-api-1`、`…-worker-1`、`…-web-1`（`127.0.0.1:18080`）、`…-neo4j-1`。
- Docker 命令需要 PATH 含 `/Applications/Docker.app/Contents/Resources/bin`。
- **不要动**：用户的其他 Docker 资源（卷 `smartsketch-a678a6028b4ace39_*`、`smartsketch-d3e4bfc14a9401d2_*`、`smartsketch-e98c46682d6c2055_app-data`、`smartsketch-main_*`，开发用 Neo4j 等）。**不要**重启 Docker Desktop。
- 停止这次安装：用向导控制页的"停止服务"按钮，或 `docker compose -p smartsketch-74694b2cb256134c stop`；不要 `down -v`，不要删卷。

## 5. 边界（必须遵守）

- **正式模式必须保持 `LLM_MODE=personal`、`EMBEDDING_MODE=online`**；不得改成 `demo`/`fake`/`local` 来"让它跑通"。`docs/runbook.md` 与 ADR-081 明确：向量服务不可用时要报告，不静默降级。
- 不得改写向量地址、更换向量供应商或模型/维度；换供应商或加代理支持都会改变产品行为，只能在报告里作为**待用户决定的方案**列出，并引用 `docs/integrations.md` 里的出站校验规则（公网地址检查、DNS 固定、TLS 主机校验、禁止重定向、响应大小限制）。
- 不改产品代码、测试、契约、迁移、启动器、`.env.example`、默认配置；不提交、不推送、不合并、不发布。
- 不调用 DeepSeek 对话/抽取（0 token）。向量请求最多 20 次，仅用于定位网络。
- 报告、日志、命令行里不得出现任何密钥、口令、令牌；只记录状态码、错误类别、耗时、IP、维度。

## 6. 停止条件

- 出现 `auth`（密钥无效/过期）：**停止并报告**，不重试，不尝试其他密钥。
- 向量请求累计达 20 次。
- 需要修改产品行为、用户系统/网络设置才能继续：停止，把需要用户做的事写清楚。

## 7. 交付物

写 `docs/handoffs/deepseek-formal-embedding-network-20261009.md`，包含：

1. **逐项测量表**（第 3 节每项一行：命令、实际输出、耗时、结论），照实记录，失败也写。
2. **原因分类**：DNS / TCP / TLS / 代理 / HTTP 状态 / `auth` 中的哪一种，证据是什么，哪些是推断。
3. **方案清单**（不要自行实施）：每项写明——需要用户做什么或需要产品改什么、风险、是否违反上面的边界、预计效果。至少评估：Docker Desktop 网络/代理设置、宿主机代理/VPN 的分流规则、同一供应商的其他可达入口（只评估不采用）、产品增加受控出站代理支持（只评估）。
4. **给用户的可执行步骤**（如果环境层面能解决）：写成用户在终端或设置页能照做的步骤，并写明怎么验证修好了（预期输出）。
5. **未验证项**与**需要 Claude 或用户决定的事**。

## 8. 之后

向量路径恢复后，Claude 继续正式模式闭环：用仓库示例章节上传 → 审核 → 发布 → 学生问答，用量熔断 100 万 token。网络问题没解决之前，**不要**让用户上传资料（会白白失败并占用任务）。

另外，用户还提了几项**不属于本任务**的安装包待处理项（向导缺少填写指引、向导与软件内向量设置重复、登录页滚动条），已登记在 `docs/tasks.md`，请不要在本任务里处理。
