# 计划 A 未完成项检查：交接给 DeepSeek harness

```text
task_ids: V1（L02 问答基线补测）、V2（L10 真实页面走查）、V3（业务改动后的完整门禁与端到端）
review_status: handoff（Claude 未执行；由 DeepSeek harness 认领）
worktree: /Users/arvinhan/SmartSketch/.claude/worktrees/smartsketch-contest-sprint-77644f
branch: claude/smartsketch-contest-sprint-77644f（草稿 PR arvinhanye/SmartSketch#317）
base_commit: 本交接所在提交
author: Claude（Opus 5.5），2026-10-03
```

## 1. 目标与边界

这三项都是**验证**，不是开发。目标是给 PR #317 补上目前缺的真实证据：

| 编号 | 要回答的问题 | 结果写到哪里 |
| --- | --- | --- |
| V1 | 真实问答的完整耗时与首字耗时是多少？发布时的真实向量化能否走通？ | 追加到 `evaluation/reports/l02-baseline-2026-10.md` |
| V2 | personal 模式下，设置页、上传、提问、清除配置在真实浏览器里是否按设计工作？ | 你的交接文件 |
| V3 | L03–L10 的业务改动之后，完整门禁（含端到端）是否仍然通过？ | 你的交接文件 |

**不在范围内**（发现问题只记录，不修）：

- 不改任何业务代码、测试、契约、迁移或启动脚本。验证中发现缺陷，写清复现步骤与证据，交回用户决定。
- 不修「向量服务不可达时问答挂数分钟」这个已知风险（`docs/reviews/claude-deepseek-l09-2026-10-03.md` 第 3 节），它已安排到计划 B/C。V1 测量时遇到它，按第 3 节的止损规则处理。
- 不编辑 PR 标题或说明，不推送，不合并。

## 2. 开工前必读与检查

必读：`AGENTS.md`；`docs/handoffs/claude-l02.md`、`claude-l10.md`、`deepseek-l09.md`；`docs/reviews/claude-deepseek-l09-2026-10-03.md`；计划 `docs/superpowers/plans/2026-10-02-contest-sprint-a-personal-model-api.md` 的 Task 2 Step 7–8 与 Task 10 Step 9；`evaluation/reports/l02-baseline-2026-10.md`。

```bash
cd /Users/arvinhan/SmartSketch/.claude/worktrees/smartsketch-contest-sprint-77644f
git status --short                     # 期望干净
nc -z -G 8 dashscope.aliyuncs.com 443 && echo "向量可达"
nc -z -G 8 api.deepseek.com 443 && echo "大模型可达"
docker ps --format '{{.Names}} {{.Ports}}' | grep 7688
lsof -nP -iTCP:8001 -iTCP:5174 -sTCP:LISTEN   # 期望无输出（端口空闲）
```

**向量不可达就停止 V1、V2**，只做 V3，并在交接里写明。这条网络路径 2026-10-03 时通时断：DeepSeek 运行 L09 时可达，Claude 复核时不可达。

## 3. 共同规则

- 环境坑同 `docs/handoffs/claude-l09-handoff.md` 第 4 节：用 `.venv/bin/python`；端到端要设 `PLAYWRIGHT_CHROMIUM_EXECUTABLE`；端口 8001/5174/7688，不碰主检出的 8000/5173/7687。
- `.env` 里的 key 不得打印、写入日志、截图或提交。需要用到时用 Python 按行读取，只在内存里使用。
- 同一时刻只运行一套服务。启动脚本用中断信号停止（脚本自带清理），只停自己启动的进程。
- **止损**：任何一次请求超过 60 秒没有响应，就停下记录现象，不重复刷请求；向量调用当前没有截止时间，网络不通时会挂数分钟。
- 预算：冲刺累计约 101076 / 5000000 计费 token。V1 约数千 token；V2 用小文件上传约数万 token。每次真实调用后在交接里登记。

## 4. V1：L02 问答基线补测（`--live` 模式）

用 `--live` 测量，与抽取基线同一模式、同一账号，结果可比。本地库里保留着抽取基线的课程：`2ace598581f349ec9943dea90bc7fdf1`（任务 `205f9311572846b8bc192ff1f67e244f`，草稿 82 个知识点、73 条关系）。

1. 启动：`scripts/start-demo.sh --live --no-open`（另一个终端运行），等 `curl -s http://127.0.0.1:8001/health` 返回 ok。
2. 发布并计时：以 `demo_teacher`（口令 `smartsketch-demo`）登录，`POST /api/v1/courses/2ace598581f349ec9943dea90bc7fdf1/publish`，记录 HTTP 状态与耗时。
   - 返回 409 `PUBLISH_BLOCKED` 时，把 `details.reasons` 原样写进交接，**不要自行改图谱**，停止 V1 并交回用户。
   - 发布会向量化全部文本块与知识点，这是在线向量在真实链路上的第一次使用；记录发布耗时，再用 `sqlite3 src/backend/storage/smartsketch.sqlite3 "SELECT purpose, count(*), sum(usage_input) FROM model_calls WHERE course_id='2ace598581f349ec9943dea90bc7fdf1' AND task_id IS NULL GROUP BY purpose;"` 看有无向量调用记录（向量调用可能不经过调用记录，以实际为准）。
3. 加学生：`POST /api/v1/courses/2ace598581f349ec9943dea90bc7fdf1/members`，请求体 `{"username": "demo_student"}`。
4. 提问（问题文件按原计划，4 题课内、1 题课外）：

   ```bash
   printf '%s\n' "什么是栈？" "循环队列如何判断队满？" "栈和队列有什么区别？" "入栈操作的时间复杂度是多少？" "光合作用的原理是什么？" > .demo/logs/l02-questions.txt
   MEASURE_PASSWORD=smartsketch-demo .venv/bin/python evaluation/measure_web_flow.py ask \
     --base-url http://127.0.0.1:8001 --username demo_student --password-env MEASURE_PASSWORD \
     --course-id 2ace598581f349ec9943dea90bc7fdf1 --questions .demo/logs/l02-questions.txt | tee .demo/logs/l02-ask.jsonl
   sqlite3 -header -column src/backend/storage/smartsketch.sqlite3 \
     "SELECT question, outcome, reason, error_code, latency_ms, first_delta_latency_ms FROM chat_logs ORDER BY created_at DESC LIMIT 5;"
   ```

   期望：前 4 题 `answered` 且有引用；第 5 题 `not_covered`。每题如实记录完整耗时、服务端 `latency_ms` 与首字耗时；超过 15 秒或报错的照实写，不重跑挑好的。
5. 写报告：在 `evaluation/reports/l02-baseline-2026-10.md` 把开头的状态说明改为「抽取与问答均已实测」，第 4 节「问答：未测及原因」改为实测结果（条件、五题明细表、p50/最大值、与 15 秒目标的差距、首字耗时、发布耗时），第 5 节更新累计计费 token。保留原有抽取数据不动。
6. 停止服务（中断信号）。

## 5. V2：L10 真实页面走查（personal 模式）

按计划 Task 10 Step 9 的六步，用 `scripts/start.sh --no-open` 启动，在浏览器打开 `http://localhost:5174`。为节省费用，第 4 步上传 `tests/fixtures/documents/stack-queue-notes.md`（约 1 KB），不要用整章资料。

| 步 | 操作 | 期望 |
| --- | --- | --- |
| 1 | `demo_teacher` 登录 | 侧栏有「模型 API 设置」并带「未配置」标记；资料页显示引导、上传按钮禁用 |
| 2 | 设置页填 `https://api.deepseek.com`、`deepseek-flash`、key → 测试连接 → 保存 | 测试成功；保存后只显示 `••••` 加末 4 位；刷新后仍是脱敏状态，密钥框为空 |
| 3 | 浏览器开发者工具检查 Application → Storage 与 Network | 存储里没有 key；`GET /api/v1/me/model-config` 响应不含 key |
| 4 | 资料页上传小文件 | 任务推进到待审核 |
| 5 | `demo_student` 登录 → 问答页 → 保存自己的配置 → 提问 | 未配置时有引导；配置后得到带引用的回答（需该课程已发布且学生是成员；可用 V1 的课程，或先发布第 4 步的课程） |
| 6 | 教师清除配置 → 再上传 | 被拒并显示引导（409 `MODEL_CONFIG_REQUIRED`） |

**密钥输入**：第 2、5 步需要把 DeepSeek key 填进设置页。优先请用户本人在浏览器里输入；如果由你操作，key 只能从 `.env` 在内存中读取并直接填入密码框或经 `PUT /api/v1/me/model-config` 提交，不得出现在命令行、日志、截图或交接里。截图保存在 `.demo/`（Git 忽略），不入库。

每一步记录实际结果（含失败与截图文件名）。第 5 步的提问计入 V1 之外的问答用量，单独登记。

## 6. V3：业务改动后的完整门禁与端到端

PR #317 目前的端到端证据只来自 L01（业务改动之前）。在 V1、V2 之后（或网络不通时直接）运行：

```bash
PYTHON=.venv/bin/python PATH="$PWD/.venv/bin:$PATH" \
PLAYWRIGHT_CHROMIUM_EXECUTABLE="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" \
  ./scripts/verify.sh integration > .demo/logs/verify-integration-planA.log 2>&1; echo "integration=$?"
grep -E "passed|failed|PASS|FAIL|✓|✘" .demo/logs/verify-integration-planA.log | tail -20
```

- 这一档包含基础档、全量（后端、前端）、集成用例与教师/学生两条端到端，耗时约 25 分钟；需要 Docker。端到端用演示模型，不产生费用。
- `PATH` 前置 `.venv/bin` 是因为契约门禁硬编码 `python3`（见 `deepseek-l09.md`「环境与沙箱」第 2 条）。
- 任何失败：保留日志与 `.e2e/<时间>/` 证据，写清失败用例名与首个错误，不修改代码或测试。

## 7. 你的交付物

1. `docs/handoffs/deepseek-plan-a-verification.md`：字段同 `claude-l09-handoff.md` 文件头，外加 V1/V2/V3 各自的命令、实际结果、证据路径、用量与未验证项。不要编辑 `claude-*.md` 文件。
2. `evaluation/reports/l02-baseline-2026-10.md`（V1 完成时）。
3. `docs/tasks.md`：只改 L02、L10 两行的状态与验收证据，以及计划 A 一节下方追加一条 V3 结果。
4. 一个本地提交，提交信息注明作者是 DeepSeek harness；不推送。

## 8. 交回用户时要说明的事

- 三项各自是通过、失败还是因网络未做。
- V1 问答耗时是否满足 15 秒；不满足时差多少。
- V2 中与设计不符的现象（逐条，附复现步骤）。
- V3 的退出码与失败清单。
- 累计计费 token。
