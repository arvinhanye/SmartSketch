RECHECK: PARTIAL

# 正式模式第二轮复核报告（rc-e3b04b5，隔离安装 abbd7b041fd3b514）

```text
from: DeepSeek harness
to: Claude
date: 2026-10-09
task: docs/handoffs/claude-formal-recheck-deepseek-handoff.md
previous: docs/handoffs/deepseek-formal-failures-20261009.md（FAILPATHS: FAIL）
fixes: docs/handoffs/claude-formal-failpath-fixes.md（ADR-095）
installation: abbd7b041fd3b514（Phase=READY，WebPort=8080，Release rc-e3b04b5，EMBEDDING_DIMENSIONS=1024）
判定: RECHECK: PARTIAL —— R1–R4 全部「正确」，O1/O2 未完成（见 §4）
生成类用量: 66,448 / 80,000 停止线 / 100,000 硬上限（未越线）
auth 类真实错误: 0
密钥泄漏: 0
改动: 未改产品代码/测试/契约/迁移/启动器/默认配置；未提交未推送
```

## 1. 汇总表

| # | 场景 | 结论 | 证据 | 耗时 |
| --- | --- | --- | --- | --- |
| 准备 S1 | 最小材料建课→上传→待审核→发布 v1 | `正确` | 材料 7,431 字节（原章前 74 行，到 `3.3.5` 结束）；待审核 **68s**；发布 v1 **13.9s**（57 点/54 边）；embedding 8 次 0 错误 | ~90s |
| **R1** | 上传超限 | **`正确`**（上一轮缺陷已修） | `limit+1` → **413 + `application/json` + `FILE_TOO_LARGE`**「文件超过上限 52428800 字节」`details.limit_bytes=52428800`；60MB → **413 + JSON + `FILE_TOO_LARGE`**「文件超过上传上限，请压缩或拆分后重试」`limit_bytes=52428800`；三条本地校验仍 `415 UNSUPPORTED_FORMAT`（extension/empty/content_mismatch）；**materials 仍 1、tasks 仍 1**（无残留）；浏览器选超限文件 → 页面「文件大小 50.0 MiB 超过 50 MiB 上限，请压缩或拆分后上传。」，**请求未发出** | ~3 min |
| **R2** | 超长提问 | **`正确`**（上一轮 `规格未定义` 已修） | 2001 字 → **422 `VALIDATION_ERROR`**（`fields: question / string_too_long`，0.06s）；200000 字 → **422 同上**（0.11s，不再 503）；**`model_calls` 前后无新增**（总数保持 31）；前端 `textarea maxLength=2000`，粘贴 3000 字后 `value.length=2000` | ~2 min |
| **R3** | 登录页滚动条 | **`正确`** | 1440×900 / 1440×780 / 1280×720 / 1100×650：**无任何 `overflow-y:auto/scroll` 且溢出的元素**；`.auth-layout__form` scrollH=clientH=519；1280×600：该元素 scrollH 519 > clientH 476（允许滚动）且 **`scrollbar-width: none`** | ~1 min |
| **R4** | 发布主路径回归 | **`正确`** | 改名 → 单次发布 **v2**（5.5s）；回滚 → **v3 `kind=rollback`**（7.8s）；版本 `[(3,'rollback'), (2,'publish'), (1,'publish')]`；学生 `graph_version=3` 并看到**改名前的旧名**；**`graph_versions` 无 `failed` 行**（3/3 committed） | ~1 min |
| O1 | 端口冲突（可选） | **未完成** | p6 控制会话过期（control.json 13:49 生成，操作时刻 14:04 > 20 分钟），`/control/exchange` 返回 403 AUTH；**8082 占用者存活、安装 `WebPort=8080` 未变、`:8080` 仍 200**（无副作用） | — |
| O2 | 备份/恢复（可选） | **未完成** | 同 O1 的会话前提；且 `BACKUP_DIR` 由启动器运行时注入，不能绕过启动器直跑 `offline-tools` | — |

## 2. 用量表（每一步后即时核算）

| 步骤 | 生成类累计 | 说明 |
| --- | --- | --- |
| 起点 | 0 | 全新安装 |
| 网络门禁 | 0 | 1 次向量请求，不计生成类 |
| **S1 上传后** | **66,448** | extract_entities 11 次 25,895 + extract_relations 10 次 34,661 + repair 2 次 5,892 |
| S1 发布后 | 66,448 | 发布只做向量化（embedding 8 次），**未新增生成类** |
| R1 后 | 66,448 | 零消耗 |
| R3 后 | 66,448 | 零消耗 |
| R2 后 | 66,448 | 422 校验不触发模型（`model_calls` 总数保持 31） |
| R4 后（最终） | **66,448** | 发布/回滚只做向量化 |

最终分布：

| purpose | 调用 | token | 错误 |
| --- | --- | --- | --- |
| extract_entities | 11 | 25,895 | 0 |
| extract_relations | 10 | 34,661 | 0 |
| repair | 2 | 5,892 | 0 |
| **生成类合计** | **23** | **66,448** | **0** |
| embedding（不计入） | 9 | 4,718 | 0 |

**未越过 80,000 停止线**；本轮 `model_calls` **全程 0 错误**（上一轮同规模材料的 embedding 错误率为 5/35）。

## 3. 缺陷复核结论

| 上一轮缺陷 | 本轮结果 | 依据 |
| --- | --- | --- |
| D1（R1）超限返回 nginx 413 HTML | **已修复** | 超限路径现返回 `application/json` + `FILE_TOO_LARGE` + `details.limit_bytes`，且前端本地拦截（请求未发出）；60MB 也由 JSON 兜底返回 |
| D2（M7）发布路径 P8 `EmbeddingBatchError` | 本轮按交接稿要求**只测单次发布主路径**（不并发）→ `正确`，且 `graph_versions` 无 `failed` 行 | 并发缺陷是否修复**未在本轮复测**（交接稿 §1 明确不重跑 M7，R4 只要求主路径回归） |
| D3（M9）守护进程不可达误报"已启动" | **本轮未复测**（交接稿 R1–R4 未包含 M9；属启动器路径，需另建隔离 HOME 场景） | — |
| C2 超长提问 503（上一轮记为`规格未定义`） | **已修复** | `ChatRequest.question` 现为 `maxLength=2000`，超长返回 422 且不触发任何模型/向量调用；前端同步 `maxlength=2000` |

## 4. 未完成项与原因

- **O1 端口冲突**：交接稿要求"重新生成控制会话"（用 p6 HOME 再运行一次启动器）。实测 p6 启动器实例（PID 27803）自 13:49 起已运行，其 `control.json` 的 20 分钟会话窗口在操作时刻（14:04）已过期，`/control/exchange` 与向导操作均返回 `AUTH: 启动控制会话已失效，请重新双击启动。`。**未执行任何端口切换**：8082 占用者存活、`installation.json` 的 `WebPort` 仍为 8080、`:8080` 仍返回 200（零副作用）。
- **O2 备份/恢复**：同会话前提；且按交接稿要求不得绕过启动器直跑 `offline-tools`（`BACKUP_DIR` 由启动器注入，安装 `.env` 中不存在）。
- **未采用"空闲端口"分支的理由**：更换端口需**先停止本安装的服务**并重装容器，而当前没有用户备份支撑；在无用户明确指示下承担该风险不划算。若要补验，请在会话有效期内由用户操作，我只读记录。

## 5. 观察

1. **回归结果干净**：本轮 `model_calls` 23 次生成调用、9 次 embedding，**错误 0**（上一轮同规模材料出现 5 次 embedding 错误）。与上一轮相比，向量链路的稳定性明显更好。
2. **发布路径只做向量化**：v1/v2/rollback 三次发布均**未产生生成类 token**，只新增 embedding 调用——与上一轮观察一致，可用于预算规划。
3. **前端与服务端校验一致**：`ChatRequest.question` 的 2000 字上限在服务端 schema（`maxLength`）与前端 `textarea maxlength` 两处一致，且超长请求在前端根本不发出（R1 同款行为）。
4. **`/chat` 仅限学生角色**：本轮以教师身份调用 `/chat` 得到 `403 ROLE_FORBIDDEN`（课程问答为学生学习面）。这不是缺陷，但值得在 QA 用例设计时注意（我最初用教师账号跑 R2 因此需要改为学生身份）。
5. **启动器会话 20 分钟**是可选验收项的主要障碍：O1/O2 都依赖它，而每轮验收的准备（凭据、S1、R1–R4）通常已超过该窗口。建议后续把依赖控制会话的验收项放在最前面，或由用户在验收当天重新双击启动器。
6. **`graph_versions` 无 failed 行**：3 条记录全为 `committed`（v1 publish / v2 publish / v3 rollback），与上一轮 R1 场景下的 `state=failed` 形成对照。

## 6. 密钥与边界声明

- **未读、未打印、未复制**安装目录 `.env` 的任何内容；报告、日志、命令行中不含任何明文密钥/口令/令牌（仅出现 `key_hint` 末 4 位 `061f`）。
- 教师凭据经一次性文件进入内存后即删；学生口令由 `secrets.token_urlsafe` 生成，仅存 0600 临时文件。
- 未改产品代码、测试、契约、迁移、启动器、`.env.example`、默认配置；`LLM_MODE=personal`、`EMBEDDING_MODE=online` 未改；未降级为 `demo`/`fake`/`local`。
- **只动本安装**（`smartsketch-abbd7b041fd3b514-*`）：本轮仅做 API 调用、浏览器加载与 DOM 测量，**未 kill/restart 任何容器**。
- **未碰其他安装**：`15196dda…`、`06177e36…`、`74694b2c…` 容器均处于停止状态（未启动）；`a678…`/`d3e4…`/`e98c…`/`main` 卷、开发 Neo4j **未触碰**；**未碰用户真实 HOME 下的安装目录**（未运行任何 `start-macos.command`，未向 `~/Library/Application Support/SmartSketch` 写入或修改）。
- 未重启 Docker Desktop，未 `down -v`，未删卷。
- 本任务的"写入"仅限：本报告；`/tmp` 下的临时取证文件；用于 O1 的哑监听 `127.0.0.1:8082`（已确认无副作用并已停止）。

## 7. 给 Claude 的下一步

1. R1–R4 全部`正确`，可推进 §8 的推送/PR/CI/发布流程。
2. 若要补齐 **O1/O2**：请在启动器启动后 **20 分钟内**通知我，或直接由你/用户操作、我只读记录结果。
3. **D2（并发发布下的 P8）与 D3（守护进程探测）本轮未复测**——交接稿未要求，但它们仍是上一轮判定的缺陷；如需关闭，请在下一轮显式列入。
