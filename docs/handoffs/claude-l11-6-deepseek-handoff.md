# L11-6 真实模型教师流程测量：交接给 DeepSeek harness

```text
task_ids: L11-6（计划 B：docs/superpowers/plans/2026-10-03-contest-sprint-b-functional-loop.md）
review_status: handoff（Claude 未执行；由 DeepSeek harness 认领）
worktree: /Users/arvinhan/SmartSketch/.claude/worktrees/smartsketch-contest-sprint-77644f
branch: claude/smartsketch-contest-sprint-77644f（已快进到本交接所在提交；未推送）
base_commit: 本交接所在提交
author: Claude（Opus 5.5），2026-10-03
```

## 1. 目标与边界

用**真实模型**（DeepSeek `deepseek-flash`，教师个人配置）和**阿里云百炼在线向量**（`text-embedding-v4`，部署者配置），走一遍计划 B 的教师流程，取得赛题指标的实测值。接线已由假供应商端到端证明（`tests/e2e/personal.spec.ts` 3 passed），这里只测**真实质量与耗时**，两类证据分开写。

| 要回答的问题 | 写到哪里 |
| --- | --- |
| 两门课 × 两种格式（文本型 PDF、Markdown），各自从上传到「待审核」的耗时 | `evaluation/reports/l11-teacher-loop-2026-10.md`（新建） |
| 每份资料的块数、模型调用数、输入/输出 usage、实体阶段与关系阶段的耗时 | 同上 |
| 知识点数、关系种类与数量（赛题：≥20 个知识点、≥3 种关系） | 同上 |
| 未经修改的原始 AI 输出（供 L16 人工判定准确率） | `evaluation/raw/l11/<课程>-<格式>-draft.json` |
| 发布耗时与向量调用记账（ADR-082 决定 6 修复后首次真实验证） | 同上报告 |

**不在范围内**（发现问题只记录，不修）：不改业务代码、测试、契约、迁移、脚本；不编辑草稿图（教师修正后的图不算原始准确率）；不推送、不合并；不做问答抽样（那是 L15-6 Step 4，另行交接）。

## 2. 开工前必读与检查

必读：`AGENTS.md`；计划 B 的第 0、9 节与 L11-6；`docs/handoffs/claude-plan-a-review-fixes-2026-10-03.md`（修复后的语义）；`evaluation/reports/l02-baseline-2026-10.md`（旧基线，用于对比）；ADR-082、ADR-083（`docs/decisions.md`）。

```bash
cd /Users/arvinhan/SmartSketch/.claude/worktrees/smartsketch-contest-sprint-77644f
git status --short && git log --oneline -1   # 期望干净，HEAD 为本交接所在提交
nc -z -G 8 dashscope.aliyuncs.com 443 && echo "向量可达"
nc -z -G 8 api.deepseek.com 443 && echo "大模型可达"
docker ps --format '{{.Names}} {{.Ports}}' | grep 7688          # 冲刺 Neo4j
lsof -nP -iTCP:8001 -iTCP:5174 -sTCP:LISTEN                      # 期望无输出
```

任一服务不可达就停止，在交接里写明，不反复重试。

## 3. 共同规则

- **迁移 016**：冲刺库尚未执行。第一次 `scripts/start.sh --no-open` 会先备份再迁移（`scripts/start-demo.sh:194`）；核对 `.demo/logs/migrate.log` 含 `016`，`backups/` 下有 `*-before-016.sqlite`，写进交接。迁移失败就停止。
- **密钥**：`.env` 里的 key 不得打印、写入日志、截图或提交。教师的 DeepSeek key 只在内存里读出后填进设置页（做法同 `docs/handoffs/deepseek-plan-a-verification.md` V2）。
- **端口**：只用 8001、5174、7688，不碰主检出的 8000、5173、7687。同一时刻只运行一套服务，用中断信号停止自己启动的进程。
- **止损**：单次上传超过 10 分钟仍未到终态、或任一 HTTP 请求 60 秒无响应，就停下记录现象。
- **预算**：冲刺累计 140230 / 5000000 计费 token（截至 2026-10-03，计划 A 修复与计划 B 的 L11-1～L11-5 均未调用真实模型）。本交接预计 30～45 万 token（旧基线一份 Markdown 抽取约 10 万）。**累计超过 60 万就停止**，交回用户。每份资料跑完立刻登记一次累计。

## 4. 步骤

资料在 `datasets/contest/`（清单 `manifest.json`，全部自编）：

| 课程 | Markdown | PDF |
| --- | --- | --- |
| 数据结构 第 3 章 栈与队列 | `course1-ds-ch3/ch3-stack-queue.md`（4773 字） | `course1-ds-ch3/ch3-stack-queue.pdf`（5 页） |
| 操作系统 第 2 章 进程与线程 | `course2-os-ch2/ch2-process-thread.md`（3187 字） | `course2-os-ch2/ch2-process-thread.pdf`（4 页） |

1. **启动**：`scripts/start.sh --no-open`，确认 `GET /api/v1/me/model-config` 的 `runtime_mode` 为 `personal`。
2. **教师配置**：用真实浏览器（或 Playwright 脚本）以 `demo_teacher` 登录，在「模型 API 设置」填写 `https://api.deepseek.com`、`deepseek-flash` 和 key，先「测试连接」再「保存」。截图（key 只显示末 4 位）。
3. **四次抽取**：每份资料建一门**独立课程**（同章两种格式放在一门课里会产生重复知识点，见交接第 6 节），各跑一次：

   ```bash
   MEASURE_PASSWORD=<从 .env 或你的环境读出，不写进命令历史> \
   .venv/bin/python evaluation/measure_web_flow.py extract --base-url http://127.0.0.1:8001 \
     --username demo_teacher --password-env MEASURE_PASSWORD \
     --course-name "L11 实测 数据结构 MD" --file datasets/contest/course1-ds-ch3/ch3-stack-queue.md --max-seconds 900
   ```

   PDF 与第二门课同理，课程名写清课程与格式。记录输出的那行 JSON（`elapsed_seconds` 即「收到上传 → 待审核」）。
4. **每次抽取后立刻导出原始草稿**（在任何人工编辑之前）：教师令牌调用 `GET /api/v1/courses/<cid>/graph`，原样保存为 `evaluation/raw/l11/<course1|course2>-<md|pdf>-draft.json`；从中统计知识点数、按 `type` 统计关系数。
5. **调用汇总**（用 `.env` 里的 `SQLITE_URL` 指向的库）：

   ```sql
   SELECT purpose, count(*), sum(usage_input), sum(usage_output),
          min(created_at), max(finished_at), round(avg(latency_ms))
   FROM model_calls WHERE task_id = '<task_id>' GROUP BY purpose;
   SELECT count(*) FROM chunks c JOIN task_revisions t ON c.revision_id = t.revision_id WHERE t.task_id = '<task_id>';
   ```

   实体阶段 = `extract_entities` 的最早 `created_at` 到最晚 `finished_at`；关系阶段同理取 `extract_relations`。若有 `status = 'error'` 的调用，按 `error_class` 列出。
6. **发布**（只对两门课的 Markdown 课程各发布一次，用于测发布与向量）：以教师身份 `POST /api/v1/courses/<cid>/publish`，记录 HTTP 状态与耗时。再查：

   ```sql
   SELECT request_id, status, count(*), sum(usage_input)
   FROM model_calls WHERE purpose = 'embedding' AND course_id = '<cid>' GROUP BY request_id, status;
   ```

   **期望**：出现 `request_id = 'publish:<version_id>'` 的行，`status = ok`（这是 D2 修复的首次真实验证）。若没有行或停在 `sent`，写进交接作为缺陷。409 `PUBLISH_BLOCKED` 时把 `details.reasons` 原样记录，不自行改图。
7. **停止服务**，登记累计 token。

## 5. 报告要求（`evaluation/reports/l11-teacher-loop-2026-10.md`）

- 测试条件：日期、机器、网络、模型、`LLM_MAX_CONCURRENCY`、`TASK_CHUNK_MAX_ATTEMPTS`、资料规模（字数/页数/块数）。
- 每份资料一行：耗时（总、实体阶段、关系阶段）、调用数、输入/输出 usage、知识点数、关系种类与数量、错误。
- 与旧基线对比（141.72 秒、82 点 / 73 边、101054 token），并写明差异条件。
- 赛题指标：≥20 知识点、≥3 种关系、抽取 ≤60 秒逐项写「达到 / 未达到（差距）」，**不缩小资料、不用缓存**。准确率不在本次判定，只说明原始输出已导出、待 L16 人工判定。
- 发布：耗时、向量调用行数与 usage、`request_id` 是否正确。
- 用量：本次计费 token 与新累计。

## 6. 已知事项（不是本次要修的）

- 同一章同时上传 PDF 与 Markdown 会抽出大量同名知识点（假供应商实测：审核队列「疑似重复」60 组）。跨任务融合按设计不在本期（R05），所以本次每份资料各用一门课。
- pdfminer 处理 Chrome 生成的 PDF 会打印大量 `Could not get FontBBox` 告警，不影响提取；worker 日志会变长。
- 首字耗时与问答完整耗时属于 L15-6 / L16，本次不测。

## 7. 你的交接文件

`docs/handoffs/deepseek-l11-6.md`：命令与退出码、四次抽取与两次发布的结果、迁移 016 核对、累计 token、发现的问题（复现步骤与证据路径），以及未完成或停止的原因。只提交报告、原始草稿 JSON 与交接文件；`.demo/`、截图与日志按现有 `.gitignore` 不提交。
