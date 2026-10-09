# 正式模式失败路径验收（最终候选镜像 rc-8a33ab9，隔离安装）——交 DeepSeek harness

```text
from: Claude
to: DeepSeek harness
date: 2026-10-09
code: 本地分支 claude/release-launcher-merge（未推送）；候选镜像 rc-8a33ab9（后端 sha256:c6e2ca0d…、前端 sha256:a66a9d9e…，均 ghcr 公开；清单 packaging/release-manifest.rc-8a33ab9.json）
installation: 隔离安装 id 15196dda63d257d1，Phase=READY，网站 http://127.0.0.1:8080（同源 /api/v1）
containers: smartsketch-15196dda63d257d1-{api,worker,web,neo4j}-1（另有 launcher 周期性起的 …-probe-run-* 临时容器，属正常）
install dir (launcher 的 HOME 被重定向): /private/tmp/claude-501/-Users-arvinhan-SmartSketch--claude-worktrees-smartsketch-frontend-ux-672666/e5ef6382-476e-4370-af0b-f5470ea7d918/scratchpad/p4/home/Library/Application Support/SmartSketch/
launcher package: …/scratchpad/p4/pkg/SmartSketch-rc-8a33ab9-darwin-amd64/（只用于 M9，见该节）
budget: 本安装内生成类（抽取+问答，不含 embedding）累计 ≤ 400,000 token 硬上限，到 300,000 就停下写报告；此前旧安装已用约 116,000，用户总上限 1,000,000
previous: docs/handoffs/deepseek-formal-loop-20261009.md（正常路径已通过，LOOP: PARTIAL，非阻塞观察已分诊）
paid_calls_by_claude: 0
```

## 1. 目的

正常路径已验证。本轮验**出问题时软件的行为**：数据会不会坏、用户看到的提示是否清楚、能不能恢复。你只验证和记录，**不改产品代码**；发现问题交回 Claude。

## 2. 先决条件（缺一就停）

1. 用户确认网络稳定（用户会在对话里告诉你）。
2. 凭据只通过环境变量，由用户在你的 shell 里设置，**不写进任何文件、命令行参数、日志、报告、截图**：
   - `FORMAL_TEACHER_USERNAME` / `FORMAL_TEACHER_PASSWORD`：用户在**这次新向导**里创建的一次性教师账号（与上一轮的旧安装不同）；
   - `FORMAL_DEEPSEEK_KEY`：用户的 DeepSeek key。
3. 这个新安装里**还没有任何模型配置**。你用 `PUT /api/v1/me/model-config`（请求体只在内存）给教师账号保存：`base_url=https://api.deepseek.com`、`model=deepseek-flash`、`api_key` 取 `FORMAL_DEEPSEEK_KEY`；用 `GET` 确认 `configured=true`、只回 `key_hint`。学生账号同理（学生由你注册，口令用 `secrets.token_urlsafe` 生成，只放内存/一个 `0600` 的临时文件，结束即删）。

## 3. 网络门禁与用量核算

- **网络门禁**：每个会花 token 或耗时的步骤之前，在 API 容器里用产品自己的向量客户端发 1 次短请求（沿用 `docs/handoffs/deepseek-formal-embedding-network-20261009.md` §4 第 2 步的脚本，不打印密钥）。`ok`（< 3 秒）才开始；否则每 30 秒重测，连续 3 次 ok 放行，最多等 20 分钟，仍不通就停下报告。
- **用量核算**：每步之后只读查询本安装的 `model_calls`：

```bash
docker exec -i smartsketch-15196dda63d257d1-api-1 python - <<'PY'
import sqlite3
db = sqlite3.connect("file:/data/smartsketch.sqlite3?mode=ro", uri=True)
print(db.execute("SELECT purpose, COUNT(*), COALESCE(SUM(usage_input),0), COALESCE(SUM(usage_output),0), SUM(status='error') FROM model_calls GROUP BY purpose").fetchall())
PY
```

  生成类用量 = `purpose <> 'embedding'` 的 `usage_input + usage_output`。**≥ 300,000 就停**；每步开始前预估不会越过 400,000。

## 4. 准备步骤（S1，一次）

用上一轮同一份材料 `datasets/demo/ch3-stack-queue.md`：教师创建课程 → 上传 → 到「待审核」→ 发布 v1；学生注册 → 教师加入课程 → 学生保存个人模型配置。记录耗时和用量，作为后面各项的**基线**（上一轮：114 秒，71 点/62 边，约 96k token）。S1 完成后才能做 M3、M7、M8。

## 5. 验收项与判定

每项给出：做法、预期、**实测**、结论（`正确` / `缺陷` / `规格未定义`）。判"缺陷"时必须引用规格或契约出处（`specs/*.md`、`src/contracts/`、`docs/decisions.md`）；规格没写的，判"规格未定义"并交 Claude，不要自己定。

| # | 场景 | 做法 | 预期（核心） | 必须 |
| --- | --- | --- | --- | --- |
| M1 | **处理中 worker 被强杀后恢复** | 再传一份文档（不同文件名），任务进入 `extracting` 且 `model_calls` 已有 ≥ 5 次调用时，`docker kill smartsketch-15196dda63d257d1-worker-1`（SIGKILL）。观察容器是否被重启策略拉起；等租约过期（`TASK_LEASE_SECONDS=60`）后任务的走向 | 任务**不会被误标为完成**；租约到期后被重新领取并走到「待审核」，或以**明确的失败原因**终止；**没有重复或残缺的草稿节点**（对比 S1 的节点/关系数量级）；课程仍可发布；记录恢复耗时和额外 token | 是 |
| M2 | **取消处理中任务** | 再传一份文档，在 `extracting` 阶段 `POST /tasks/{tid}/cancel`；之后再传同一份文件 | 状态变为已取消，`cancel_requested` 语义符合 `specs/task-processing.md`；取消的任务**没有任何节点进入草稿**；重新上传能正常处理；页面按钮/提示一致 | 是 |
| M3 | **API 容器被杀时的前端表现** | 学生在问答页提问并在流式输出中，`docker kill smartsketch-15196dda63d257d1-api-1`；再在空闲时杀一次 | 页面显示"本次回答未完成"类的**可读错误并保留问题、可重试**，不是白屏/无限转圈；API 被重启策略拉起后（记录耗时）再提问成功；数据（账号、课程、版本、进度）不丢 | 是 |
| M4 | **会话失效** | 在浏览器里把 `sessionStorage` 的会话令牌改成无效值后刷新/操作；再测"令牌过期"的真实路径（若可构造） | 接口 401；页面回到登录页并给出"登录已失效/未登录"提示，**不白屏**，不泄露令牌；重新登录后能继续 | 是 |
| M5 | **上传边界** | 不支持的扩展名（`.exe`/`.pptx`）；空文件；内容与扩展名不符（把文本改名 `.pdf`）；超过上限的文件（先 `GET /courses/{cid}/upload-policy` 取 `limit_bytes`，造 `limit+1` 字节的 `.md`） | 都返回契约里的明确错误（本地校验或 `FILE_TOO_LARGE`/`UNSUPPORTED_FORMAT`），页面文案可读，**没有创建任务**，没有残留文档记录 | 是 |
| M6 | **向量密钥无效** | 教师「模型 API 设置」的**向量**区块，用明显无效的字符串（`invalid-key-0000`，不是任何真实密钥）点"测试连接"（**只测试，不要点保存**） | 提示"密钥被拒绝/检查配置"类错误，不回显服务端原文；已有向量配置不被改动（`GET /me/embedding-config` 前后一致） | 是 |
| M7 | **发布冲突与回滚** | 教师改一个知识点名称（草稿）后，**同时**发两次 `POST /courses/{cid}/publish`；再 `POST /versions/1/rollback` | 只有一次成功生成新版本，另一次得到忙/冲突类错误且无副作用；版本号连续不重复；回滚是"前滚为新版本"（见 `specs/teacher-review-publish.md`），学生看到的内容与预期一致 | 是 |
| M8 | **权限与课程隔离** | 教师再建第二门课；学生（非成员）读该课图谱/问答；学生用教师专有接口（上传、审核、发布、加成员、改草稿）；教师访问另一教师不存在——如无第二位教师则跳过该子项并写明 | 一律 403/404（按契约），**不泄露课程是否存在以外的信息**；学生看不到草稿、看不到第二门课 | 是 |
| M9 | **启动器在 Docker 不可用时的提示** | **不要动正在运行的安装**。另建一个临时目录作 `HOME`，用包里的 `bin/smartsketch-launcher` 分别：(a) `PATH=/usr/bin:/bin`（找不到 docker）；(b) 让 docker CLI 存在但守护进程不可达（用 `docker --config <临时目录> context create bogus --docker host=unix:///nonexistent`，并在 `<临时目录>/config.json` 里设 `currentContext`，把 `DOCKER_CONFIG=<临时目录>` 传给启动器，临时目录不得是用户的 `~/.docker`） | 启动器给出**明确的中文提示**（安装/打开 Docker Desktop），退出码非 0，**不崩溃、不写入用户原来的安装目录、不影响正在运行的安装** | 是 |
| M10 | **容器级快速恢复** | 依次 `docker restart` 的整体健康：`api`+`worker` 已在上一轮测过，这里测 `neo4j` 单独 `docker restart` | 重启期间 API 对图谱读返回可读的服务错误而不是崩溃；neo4j 恢复后无需人工干预即可读写；已发布图谱仍一致 | 否 |
| O1 | **端口冲突（需用户在向导页点一下）** | 你在本机开一个占用 8081 的哑监听（`python3 -m http.server 8081 --bind 127.0.0.1`）并通知用户；用户在向导标签页点"确认更换端口"，先填 8081，再填一个空闲端口 | 8081：明确的"端口被占用"类提示，启动器**不杀占用者**，原安装不受影响；空闲端口：数据保留、账号可登录 | 否（需用户配合） |
| O2 | **真实数据备份/恢复（尽力而为）** | 用 `compose.release.yaml` 的 `offline-tools`（`backup`/`restore`，`network_mode: none`）对**这个安装**做一次备份并恢复到暂存卷，用 `probe` 校验 | 备份成功、摘要可核对、恢复只写暂存卷；**不切换、不覆盖正在运行的卷** | 否（若需要启动器令牌或会改动运行中的卷就停，写明原因） |

建议顺序（先便宜后贵）：S1 → M5 → M6 → M8 → M3 → M7 → M4 → M9 → M10 → M2 → M1 → O1 → O2。

## 6. 边界

- 不改产品代码、测试、契约、迁移、启动器、`.env.example`、默认配置；不提交、不推送、不合并、不发布。
- `LLM_MODE=personal`、`EMBEDDING_MODE=online` 不得改；不得降级成 `demo`/`fake`/`local`。
- 不读、不打印、不复制安装目录里 `.env` 的任何内容；报告里不出现密钥/口令/令牌；截图前确认没有明文密钥。
- **只动这个安装**（`smartsketch-15196dda63d257d1-*`）。不动其他 Docker 资源：旧隔离安装（`smartsketch-74694b2cb256134c-*` 已停止，卷保留）、`smartsketch-a678…`/`d3e4…`/`e98c…`/`main` 的卷、开发 Neo4j。不重启 Docker Desktop，不 `down -v`，不删卷。
- `docker kill`/`docker restart` 仅限 M1、M3、M10 里指明的本安装容器。
- 本 shell 外网受限：需要联网的检查在容器内做（沿用上一轮做法）。

## 7. 停止条件

生成类 ≥ 300,000；网络门禁等待满 20 分钟；同一项两次得到相互矛盾的结果；出现 `auth` 类（真实配置被拒）错误；需要改产品才能继续；任何一步对**其他**安装或用户原安装目录产生了影响（立刻停并报告）。

## 8. 交付物

写 `docs/handoffs/deepseek-formal-failures-20261009.md`（先落在 worktree，再同步一份到主仓 `docs/handoffs/`）。**第一行**为 `FAILPATHS: PASS` / `PARTIAL` / `FAIL`：
- `PASS`：所有"必须"项结论为`正确`；
- `PARTIAL`：必须项无`缺陷`，但有`规格未定义`或可选项未完成；
- `FAIL`：任一必须项为`缺陷`。

其后：1）汇总表（M1–M10、O1、O2：结论、证据位置、耗时）；2）用量表（每步前后）；3）M1/M2 的恢复/取消时间线与节点数对比；4）每个`缺陷`/`规格未定义`的复现步骤与规格出处；5）观察；6）密钥与边界声明。

## 9. 之后

`PASS/PARTIAL` → Claude 处理缺陷与待定义项，然后启动器 PR 合入 main、CI 变绿、出包。`FAIL` → Claude 先修，再让你复测相关行。
