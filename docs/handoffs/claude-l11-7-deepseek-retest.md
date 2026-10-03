# L11-7 PDF 段落合并后的真实模型复测：交接给 DeepSeek harness

```text
task_ids: L11-7 复测（计划 B；ADR-084）
review_status: handoff（Claude 未执行；由 DeepSeek harness 认领）
worktree: /Users/arvinhan/SmartSketch/.claude/worktrees/smartsketch-contest-sprint-77644f
branch: claude/smartsketch-contest-sprint-77644f（已快进到本交接所在提交；未推送）
base_commit: 本交接所在提交
author: Claude（Opus 5.5），2026-10-03
```

## 1. 目标与边界

你在 L11-6（`8e79adf`，报告 `evaluation/reports/l11-teacher-loop-2026-10.md`）发现 PDF 路径成本高、repair 多、抽不出 `PREREQUISITE`、近半节点孤立。根因已离线定位并修复：PDF 解析一行一块、句子被换行切断（ADR-084，解析器 `headings/2`）。修复后同章 PDF 的块数与 Markdown 相当（38 对 37、24 对 24），块内没有换行。

本次**只复测两份 PDF**，回答修复是否在真实模型上生效：

| 问题 | 对比 L11-6 |
| --- | --- |
| 总耗时、实体阶段、关系阶段 | 200.37 秒 / 162.54 秒 |
| 调用数与 repair 次数 | 49（repair 13）/ 39（repair 5） |
| 计费 token | 192188 / 121583 |
| 关系种类与数量，是否出现 `PREREQUISITE` | 3 种 24 条、无前置 / 3 种 25 条、无前置 |
| 孤立节点数 | 37 / 39 |

结果**追加**到 `evaluation/reports/l11-teacher-loop-2026-10.md` 新的一节（「L11-7 复测」），不改原有各节；原始草稿另存为 `evaluation/raw/l11/course1-pdf-draft-headings2.json`、`course2-pdf-draft-headings2.json`。

**不在范围内**：Markdown 不受这次修改影响，不重测；不改代码、测试、契约、脚本；不编辑草稿；不推送、不合并；不做问答抽样。

## 2. 开工检查

```bash
cd /Users/arvinhan/SmartSketch/.claude/worktrees/smartsketch-contest-sprint-77644f
git status --short && git log --oneline -1          # 期望干净，HEAD 为本交接所在提交
PYTHONPATH=src/backend .venv/bin/python -c "from app.workers.parse_task import PDF_PARSER_VERSION as v; print(v)"
# 期望输出 pdf/2,cleanup/1,headings/2；不是就停止（说明代码不是修复版本）
nc -z -G 8 api.deepseek.com 443 && echo "大模型可达"
nc -z -G 8 dashscope.aliyuncs.com 443 && echo "向量可达"
lsof -nP -iTCP:8001 -iTCP:5174 -sTCP:LISTEN          # 期望无输出
```

**重启服务是必须的**：已在运行的 worker 进程装的是旧解析器。

## 3. 共同规则

沿用 `docs/handoffs/claude-l11-6-deepseek-handoff.md` 第 3 节（密钥不落盘、端口 8001/5174/7688、止损 10 分钟 / 60 秒）。两点更新：

- 迁移 016 已在 L11-6 执行，本次启动不应再有新迁移；若 `migrate.log` 出现新的迁移版本，停止并报告。备份位置是 `src/backend/storage/backups/`（L11-6 交接里写的仓根 `backups/` 有误）。
- **预算**：累计 619217 / 5000000（L11-6 后）。本次两份 PDF 预计 15～25 万 token（修复后应接近 Markdown 的约 8～9 万一份）。**累计超过 85 万就停止**，交回用户。

## 4. 步骤

1. `scripts/start.sh --no-open`，确认 `runtime_mode = personal`；教师 `demo_teacher` 的个人配置在 L11-6 已保存，先在设置页「测试连接」确认仍可用（不重新保存，除非测试失败）。
2. 两份 PDF 各建一门**新课程**，各跑一次：

   ```bash
   MEASURE_PASSWORD=<从环境读出，不写进命令历史> \
   .venv/bin/python evaluation/measure_web_flow.py extract --base-url http://127.0.0.1:8001 \
     --username demo_teacher --password-env MEASURE_PASSWORD \
     --course-name "L11-7 复测 数据结构 PDF" --file datasets/contest/course1-ds-ch3/ch3-stack-queue.pdf --max-seconds 900
   ```

   第二份为 `datasets/contest/course2-os-ch2/ch2-process-thread.pdf`。
3. 每次到「待审核」后立刻导出原始草稿（`GET /api/v1/courses/<cid>/graph`），按第 1 节文件名保存；统计知识点数、按 `type` 的关系数、孤立节点数（与 L11-6 同口径）。
4. 调用汇总与块数用 L11-6 交接第 4 节第 5 步的 SQL；另核对这两个任务的资料修订解析器版本：

   ```sql
   SELECT r.parser_version FROM material_revisions r JOIN task_revisions t ON r.revision_id = t.revision_id
   WHERE t.task_id = '<task_id>';
   ```

   期望包含 `headings/2`。
5. 不发布（L11-6 已验证发布与向量记账）。停止服务，登记累计 token。

## 5. 报告要求（追加的「L11-7 复测」一节）

- 两份 PDF 的复测结果表，与 L11-6 的 PDF 结果逐项对照（第 1 节表格的各项），并列出对应 Markdown 的 L11-6 数值作参照。
- 明确结论：repair 是否下降、`PREREQUISITE` 是否出现、孤立节点是否减少、成本与耗时是否接近 Markdown。没有改善或变差都照实写，并给出证据路径。
- 赛题指标逐项更新（≥20 知识点、≥3 种关系、抽取 ≤60 秒）。
- 用量：本次计费 token 与新累计。

## 6. 你的交接文件

`docs/handoffs/deepseek-l11-7-retest.md`：命令与退出码、两次抽取结果、解析器版本核对、累计 token、发现的问题与证据路径。只提交报告追加部分、两份原始草稿 JSON 与交接文件。
