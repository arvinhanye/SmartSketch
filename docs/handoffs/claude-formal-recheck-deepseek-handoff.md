# 正式模式第二轮复核（修复批次 2，候选镜像 rc-e3b04b5，隔离安装）——交 DeepSeek harness

```text
from: Claude
to: DeepSeek harness
date: 2026-10-09
previous: docs/handoffs/deepseek-formal-failures-20261009.md（FAILPATHS: FAIL）
fixes: docs/handoffs/claude-formal-failpath-fixes.md（ADR-095）
code: 本地分支 claude/release-launcher-merge（提交 fbe176c、e3b04b5，未推送分支）
images: 后端 ghcr.io/arvinhanye/smartsketch-backend@sha256:362953d27589d35af42097f9d31168e9c4c2da7b91c55370cac319f4011b5bc5
        前端 ghcr.io/arvinhanye/smartsketch-frontend@sha256:e0d64e481338b1c8497db8925888256f6e0c735aaf2efc3c6a38117957d4c9fb
        清单 packaging/release-manifest.rc-e3b04b5.json
installation: 隔离安装 id abbd7b041fd3b514，Phase=READY，网站 http://127.0.0.1:8080（同源 /api/v1），向量维度 1024
containers: smartsketch-abbd7b041fd3b514-{api,worker,web,neo4j}-1（launcher 周期性起的 …-probe-run-* 属正常）
install dir (launcher 的 HOME 被重定向): /private/tmp/claude-501/-Users-arvinhan-SmartSketch--claude-worktrees-smartsketch-frontend-ux-672666/e5ef6382-476e-4370-af0b-f5470ea7d918/scratchpad/p6/home/Library/Application Support/SmartSketch
launcher package: …/scratchpad/p6/pkg/SmartSketch-rc-e3b04b5-darwin-amd64/
budget: 本安装内生成类（抽取+问答，不含 embedding）累计 ≤ 100,000 token 硬上限，**到 80,000 就停下写报告**。用户 100 万总上限已用约 675,000（116k + 105k + 454k），剩余只有约 325,000。
paid_calls_by_claude: 0
```

## 1. 目的

只复核上一轮判缺陷或规格未定义的几项是否修好，不重跑已经 `正确` 的项（M1–M4、M6、M8、M10、M11 不再测）。

## 2. 先决条件与硬规矩

1. 用户确认网络稳定。
2. 凭据只通过环境变量，由用户在你的 shell 里设置，不写进任何文件、命令行参数、日志、报告、截图：`FORMAL_TEACHER_USERNAME` / `FORMAL_TEACHER_PASSWORD`（用户在这次新向导里创建的教师账号）、`FORMAL_DEEPSEEK_KEY`。新安装还没有模型配置：你用 `PUT /api/v1/me/model-config` 给教师和学生账号保存（`base_url=https://api.deepseek.com`、`model=deepseek-flash`），请求体只在内存。
3. **每一步结束后立刻**重算用量，不是步骤开始前。上一轮越过 400k 上限就是因为只在步骤前核算。核算命令（容器名已换）：

```bash
docker exec -i smartsketch-abbd7b041fd3b514-api-1 python - <<'PY'
import sqlite3
db = sqlite3.connect("file:/data/smartsketch.sqlite3?mode=ro", uri=True)
print(db.execute("SELECT purpose, COUNT(*), COALESCE(SUM(usage_input),0), COALESCE(SUM(usage_output),0), SUM(status='error') FROM model_calls GROUP BY purpose").fetchall())
PY
```

生成类 = `purpose <> 'embedding'` 的 `usage_input + usage_output`。**≥ 80,000 立即停**；预估下一步会越过 100,000 也不要做。
4. 每个会花 token 的步骤之前先跑向量网络门禁（沿用 `docs/handoffs/deepseek-formal-embedding-network-20261009.md` §4 第 2 步）。

## 3. 准备（S1，最小化）

**不要用整章材料**（整章抽取约 106k token，会吃掉整个预算）。从 `datasets/demo/ch3-stack-queue.md` 取**前约 8 KB**（保持在章节边界处截断）另存为 `/tmp` 下的临时 `.md`，教师建课程 → 上传 → 到「待审核」→ 发布 v1；学生注册 → 教师加入课程。记录抽取 token、耗时、发布耗时。若这一步已超过 50,000 token，立刻停并报告。

## 4. 验收项

每项给出做法、预期、**实测**、结论（`正确` / `缺陷` / `规格未定义`）。判缺陷必须引用规格或契约出处。

| # | 场景 | 做法 | 预期（核心） | 必须 |
| --- | --- | --- | --- | --- |
| R1 | **上传超限（上一轮 M5）** | `GET /courses/{cid}/upload-policy` 取 `max_bytes`；造 `max_bytes+1` 字节 `.md` 用 multipart POST `/courses/{cid}/documents`；再造 60 MB 文件 POST。另重测三条本地校验（`.exe`/空文件/内容不符）确认仍是 415 | `max_bytes+1`：**HTTP 413，`Content-Type: application/json`，`code=FILE_TOO_LARGE`，`details.limit_bytes` 等于 `max_bytes`，中文 `message`**，不是 nginx HTML；60 MB：同样是 JSON `FILE_TOO_LARGE`（由 nginx 兜底返回，`limit_bytes=52428800`）；三条本地校验仍 `415 UNSUPPORTED_FORMAT`；**没有创建任务、没有残留文档记录**；浏览器里选超限文件，页面给出可读中文提示 | 是 |
| R2 | **超长提问（上一轮 C2）** | 学生对已发布课程 `POST /courses/{cid}/chat`：2001 字、200,000 字各一次；再取 `GET`/页面确认问答输入框 `maxlength`；在浏览器里往输入框粘贴 3000 字，读 `value.length`；最后发一个**恰好 2000 字**的问题一次 | 2001 与 200,000 字：**HTTP 422 `VALIDATION_ERROR`**（不再是 503 `LLM_UNAVAILABLE`），**`model_calls` 前后无新增**；输入框 `maxlength=2000`，粘贴后长度 2000；2000 字问题被接受（任何终态均可，只要不是 422） | 是 |
| R3 | **登录页滚动条（用户反馈）** | 未登录打开 `http://127.0.0.1:8080/`，在视口 1440×900、1440×780、1280×720、1100×650、1280×600 下，用 DOM 找 `overflow-y` 为 `auto/scroll` 且 `scrollHeight > clientHeight` 的元素，并读 `.auth-layout__form` 的 `getComputedStyle(...).scrollbarWidth` | 前四个尺寸**没有**滚动容器；1280×600 允许滚动，但 `scrollbar-width` 为 `none` | 是 |
| R4 | **发布主路径回归** | 教师改一个知识点名称后再发布一次（单次，不并发），再回滚到 v1 | 发布成功生成新版本；回滚生成 `kind=rollback` 的新版本；学生按新版本看到名称；`graph_versions` 无 `failed` 行 | 是 |
| O1 | **端口冲突（需用户配合，可选）** | 先**重新生成控制会话**：在包目录里用 `HOME=<install dir 所在的 p6/home> PATH="/usr/bin:/bin:/usr/sbin:/sbin:/usr/local/bin:/Applications/Docker.app/Contents/Resources/bin" ./bin/smartsketch-launcher` 再运行一次（已有实例在运行，这是第二次调用，会重新打开控制页）；**绝对不要双击包里的 `start-macos.command`**，它没有重定向 HOME，会作用到用户真实安装目录。哑监听占 8082，通知用户在控制页确认更换端口，先 8082 再空闲端口 | 8082：明确的「端口被占用」提示，**不杀占用者**；空闲端口：数据保留、账号可登录 | 否 |
| O2 | **备份/恢复（可选，尽力而为）** | 同 O1 的控制会话前提。只通过启动器自己的备份入口做，**不要**绕过启动器直接跑 `offline-tools`（`BACKUP_DIR` 由启动器运行时注入） | 备份成功、摘要可核对；恢复只写暂存卷；不切换、不覆盖运行中的卷。需要的操作超出上述就停并写明原因 | 否 |

## 5. 边界

- 不改产品代码、测试、契约、迁移、启动器、`.env.example`、默认配置；不提交、不推送、不合并、不发布。
- `LLM_MODE=personal`、`EMBEDDING_MODE=online` 不得改；不得降级成 `demo`/`fake`/`local`。
- 不读、不打印、不复制安装目录里 `.env` 的任何内容；报告里不出现密钥、口令、令牌。
- **只动这个安装**（`smartsketch-abbd7b041fd3b514-*`）。其他安装（`15196dda…`、`06177e36…`、`74694b2c…` 容器均已停止，卷保留；`a678…`/`d3e4…`/`e98c…`/`main` 卷；开发 Neo4j；用户真实 HOME 下的安装目录）一律不碰。不重启 Docker Desktop，不 `down -v`，不删卷。
- 本 shell 外网受限：需要联网的检查在容器内做。

## 6. 停止条件

生成类 ≥ 80,000；网络门禁等待满 20 分钟；同一项两次得到相互矛盾的结果；出现 `auth` 类（真实配置被拒）错误；需要改产品才能继续；任何一步对其他安装或用户真实安装目录产生了影响（立刻停并报告）。

## 7. 交付物

写 `docs/handoffs/deepseek-formal-recheck-20261009.md`（先落在 worktree，再同步一份到主仓 `docs/handoffs/`）。**第一行**为 `RECHECK: PASS` / `PARTIAL` / `FAIL`：`PASS` = R1–R4 全部 `正确`；`PARTIAL` = R1–R4 无缺陷但 O1/O2 未完成；`FAIL` = 任一必须项为缺陷。

其后：1）汇总表（R1–R4、O1、O2：结论、证据、耗时）；2）**每一步后**的用量表（累计生成类 token）；3）每个缺陷的复现步骤与规格出处；4）观察；5）密钥与边界声明（含「未碰其他安装、未碰用户真实安装目录」）。

## 8. 之后

`PASS/PARTIAL` → Claude 推送并开启动器 PR、等 CI 变绿、合入 main、出 Mac Intel 与 Windows 的包。`FAIL` → Claude 先修再复测相关行。
