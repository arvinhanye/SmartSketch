# 正式模式业务闭环验收（真实 DeepSeek + 百炼向量，隔离安装）——交 DeepSeek harness

```text
from: Claude
to: DeepSeek harness
date: 2026-10-09
code: 本地分支 claude/release-launcher-merge（未推送）；候选镜像 ghcr.io/arvinhanye/smartsketch-{backend,frontend}:rc-43939b7
installation: 隔离安装 id 74694b2cb256134c，网站 http://127.0.0.1:18080（同源 /api/v1），4 个容器 healthy；不要重启 Docker Desktop，不要 down、不要删卷
budget: 生成模型（抽取+问答，不含 embedding）累计不超过 1,000,000 token——用户批准的硬上限；到 800,000 就停下写报告
previous: docs/handoffs/deepseek-formal-embedding-network-20261009.md、docs/handoffs/deepseek-formal-embedding-baseline-20261009.md
paid_calls_by_claude: 0（Claude 只发过 5 次短向量请求，其中 4 次超时）
```

## 1. 目的

验证**要交付的软件在正式模式下能不能用**：个人模型 API（DeepSeek）+ 在线向量（阿里云百炼 `text-embedding-v4`，1024 维）+ 真实启动器装出来的容器。你只**验证和记录**，发现问题交回 Claude 修，**不改产品代码**。

## 2. 先决条件（缺一就停，不要开始）

1. **用户已确认网络稳定**（用户会在对话里告诉你）。向量路径此前在 09:32–09:33、09:48–09:53 通，09:45、09:57 不通，是出口在切换。
2. **凭据只通过环境变量交给你**，由用户在你的 shell 里设置，**不要写进任何文件、命令行参数、日志或报告**：
   - `FORMAL_TEACHER_USERNAME` / `FORMAL_TEACHER_PASSWORD`：向导里创建的首位教师（用户的一次性测试账号）；
   - `FORMAL_DEEPSEEK_KEY`：用户的 DeepSeek key（只用于给学生账号保存个人模型配置）。
   缺任何一项：停下，告诉用户。
3. 教师账号的个人模型配置已由用户在网页里保存。用 `GET /api/v1/me/model-config` 确认 `configured=true`、`runtime_mode=personal`（响应只含 `key_hint`，不含密钥）。

## 3. 网络门禁（每个会花钱或耗时的步骤之前）

每次上传、发布、提问**之前**先跑上一份报告 §4 第 2 步的单次向量请求（容器内、产品自己的客户端、不打印密钥）：

- `ok … seconds=…`（< 3 秒）→ 才能开始这一步；
- 否则**等待**：每 30 秒重测一次，**连续 3 次 ok** 才放行；最多等 20 分钟，仍不放行就停下，报告"网络未稳定"，不要硬上传。
- 步骤**执行中**出现向量类失败（任务 `failed` 且原因是向量/`LLM_UNAVAILABLE`/连接类，或问答返回服务错误）：**如实记录，不要掩盖，也不要降级**。每个步骤最多**重做 1 次**（会再消耗 token，计入预算）；两次都失败就停止并报告。

## 4. 用量核算（每步之后都做）

只读查询，容器内 SQLite 以只读方式打开：

```bash
docker exec -i smartsketch-74694b2cb256134c-api-1 python - <<'PY'
import sqlite3
db = sqlite3.connect("file:/data/smartsketch.sqlite3?mode=ro", uri=True)
print(db.execute("SELECT purpose, COUNT(*), COALESCE(SUM(usage_input),0), COALESCE(SUM(usage_output),0) FROM model_calls GROUP BY purpose").fetchall())
PY
```

生成类用量 = 所有 `purpose <> 'embedding'` 的 `usage_input + usage_output`。**≥ 800,000 就停**；任何一步开始前，预估这一步不会越过 1,000,000。启动时的累计应为 0。服务端默认的任务/日预算（500000 / 5000000）仍然生效，但安装的 `.env` 无法加更低的熔断，所以靠你核算。

## 5. 验收步骤与判定

材料：`datasets/demo/ch3-stack-queue.md`（约 11.5 KiB，仓库自带，可公开）。教师用网页或 API 均可；**真实页面要走一遍**（浏览器操作并截图关键页），其余用 API 取证。

| # | 步骤 | 通过条件 | 必须通过 |
| --- | --- | --- | --- |
| R1 | 教师登录；「模型 API 设置」显示已配置（只见末 4 位）；网页上对已存配置点"测试连接"（1 次） | 登录成功；测试成功；页面无密钥回显 | 是 |
| R2 | 创建课程；上传示例章节；订阅/观察任务进度到「待审核」 | 阶段按 解析→抽取→融合→持久化→待审核 推进；**不是编造的百分比**；记录总耗时与每阶段耗时 | 是 |
| R3 | 图谱质量抽样 | 记录知识点数、关系数、关系类型分布、孤立点数；**抽样 10 个知识点 + 10 条关系**，逐条判断对错并写错误类型；`PREREQUISITE` 无环 | 是（给数据，不设硬阈值；抽样准确率低于 70% 要明确标红） |
| R4 | 审核队列 → 发布 v1 | 发布成功，学生可见版本为 v1；记录耗时 | 是 |
| R5 | 草稿/发布隔离：教师改一个知识点名称（草稿） | 学生看到的仍是 v1 原名 | 是 |
| R6 | 学生：用你生成的一次性随机口令注册学生账号（口令只在内存/环境变量，不落盘不打印）；**未保存模型配置前**上传/提问被拦 | 提问返回 `MODEL_CONFIG_REQUIRED`（409）并在页面给出"去设置"引导 | 是 |
| R7 | 教师把学生加入课程；学生用 `PUT /api/v1/me/model-config` 保存个人配置（`base_url`、`model` 与教师一致，`api_key` 取 `FORMAL_DEEPSEEK_KEY`，请求体只在内存） | 保存成功，`GET` 只回 `key_hint` | 是 |
| R8 | 学生浏览已发布图谱；标记 2 个知识点掌握状态 | 服务端确认后才显示成功；推荐刷新且理由来自服务端；刷新页面后进度仍在 | 是 |
| R9 | 学生问答：**4 个课内问题 + 1 个课外问题** | 课内：`answered` 且每条有来源（文件/页或章节），来源可点开看原文；课外：`not_covered`、0 引用，界面是"资料未覆盖"而不是错误；记录每问**总耗时**和首字耗时（产品验收口径 15 秒） | 是 |
| R10 | 无效密钥路径：用**明显无效的字符串**（如 `invalid-key-0000`，不是任何真实密钥）对学生账号做一次"测试连接" | 被拒绝，页面文案是"密钥被拒绝/检查配置"，不泄露服务端原文 | 否 |
| R11 | 持久化：`docker restart` 该安装的 api、worker 两个容器（只这两个） | 重启后账号、课程、发布版本、学生进度都还在；登录仍可用 | 是 |
| R12 | 日志卫生：`docker logs`（四个容器）里搜 `sk-`、`Bearer`、以及你知道的**密钥末 4 位之外**的任何疑似密钥模式 | 不得出现密钥、口令；只报告"有/无"和行数，**不要把命中内容贴进报告** | 是 |

要点：
- 所有页面走查按**电脑端**（1440×900）；手机端不在本轮范围。
- 发现界面上让人困惑的地方（文案、引导、错误提示）记入报告"观察"一节，**不要修**。
- 不要碰向导页面与启动器（它们不在本任务范围）。

## 6. 边界

- 不改产品代码、测试、契约、迁移、启动器、`.env.example`、默认配置；不提交、不推送、不合并、不发布。
- `LLM_MODE=personal`、`EMBEDDING_MODE=online` 不得改；不得降级成 `demo`/`fake`/`local`；不得换供应商/模型/向量地址。
- 不读、不打印、不复制安装目录里的 `.env`；不把任何密钥或口令写进报告、日志、命令行、截图（截图前确认没有明文密钥框）。
- 不动其他 Docker 资源（卷 `smartsketch-a678…_*`、`smartsketch-d3e4…_*`、`smartsketch-e98c…_app-data`、`smartsketch-main_*`、开发 Neo4j），不重启 Docker Desktop，不 `down -v`。
- 出现 `auth` 类错误：停止并报告，不重试、不尝试别的密钥。

## 7. 停止条件

- 生成类用量 ≥ 800,000；
- 网络门禁等待满 20 分钟仍未放行；
- 同一步骤两次失败；
- `auth` 类错误；
- 发现需要修改产品才能继续（先记录，再停）。

## 8. 交付物

写 `docs/handoffs/deepseek-formal-loop-20261009.md`（先落在 worktree，再同步一份到主仓 `docs/handoffs/`）。**第一行**是 `LOOP: PASS`、`LOOP: PARTIAL` 或 `LOOP: FAIL`：

- `PASS`：所有"必须通过"的行都通过；
- `PARTIAL`：必须通过的行都通过，但有非阻塞问题（R10 或抽样质量偏低等），写明；
- `FAIL`：任一"必须通过"的行失败。

其后依次是：

1. 汇总表（R1–R12 各一行：结果、证据位置、耗时）；
2. 用量表（每步前后的生成类累计、embedding 请求次数、最终累计）；
3. R2 的阶段耗时；R3 的抽样明细和错误类型；R9 的 5 问明细（问题、状态、引用数、总耗时、首字耗时）；
4. 失败与重做记录（含网络门禁等待了多久、哪一步被向量失败打断）；
5. 观察（体验问题、文案、你认为需要 Claude 或用户决定的事）；
6. 密钥与边界声明（未读/未打印/未改动）。

## 9. 之后

`LOOP: PASS/PARTIAL` → Claude 处理报告里的问题，再做装包前的修复批次（向导指引、登录页滚动条等已登记）。`LOOP: FAIL` → Claude 先修失败项，再让你复测相关行。
