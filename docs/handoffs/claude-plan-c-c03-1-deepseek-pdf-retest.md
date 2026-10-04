# C03-1 交 DeepSeek harness：修复后 PDF 真实抽取复测（先 course2）

```text
from: Claude
to: DeepSeek harness
date: 2026-10-03
code: claude/plan-c-reliability（本交接所在提交；解析器 pdf/2,cleanup/1,headings/2；迁移 017）
supersedes: docs/handoffs/claude-l11-7-deepseek-retest.md（旧预算起点 619217 已过时，未执行）
budget: 用户 2026-10-03 批准——只跑 course2 PDF 一份，生成 token 单份止损 110000；跑完累计不超过 803168
paid_calls_by_claude: 0
```

## 1. 目的与边界

L11-6 发现 PDF 路径成本高、repair 多、抽不出 `PREREQUISITE`、近半节点孤立。根因是 PDF 解析一行一块、句子被换行切断，已用 ADR-084（`headings/2`）修复，但还没有真实模型证据。本轮**只跑较小的 course2 PDF 一次**，看修复是否生效、实际花多少：

| 指标 | L11-6 course2 · PDF（修复前） | L11-6 course2 · Markdown（参照） |
| --- | --- | --- |
| 上传 → 待审核 | 162.54 秒 | 75.51 秒 |
| 调用数（repair） | 39（5） | 34（3） |
| 计费 token | 121583 | 78242 |
| 知识点 / 关系 / 关系种类 | 74 / 25 / 3（无 `PREREQUISITE`） | 71 / 55 / 4（`PREREQUISITE` 5） |
| 孤立节点 | 39 | 3 |

- **course1 PDF 本轮不跑**：用户要求先看 course2 的实际消耗，再决定是否追加。
- 不重测 Markdown；不改代码、测试、提示词；不编辑草稿；不推送、不合并。

## 2. 环境与开工检查（由用户安排测量 checkout；不要自行同步或清库）

```bash
git log --oneline -1                                   # 本分支最新提交
PYTHONPATH=src/backend .venv/bin/python -c "from app.workers.parse_task import PDF_PARSER_VERSION as v; print(v)"
# 期望 pdf/2,cleanup/1,headings/2；不是就停止
sqlite3 "file:<库路径>?mode=ro" "SELECT COALESCE(SUM(usage_input+usage_output),0) FROM model_calls WHERE purpose <> 'embedding' AND usage_input IS NOT NULL"
```

- 第三条是开跑前的生成累计。若 C02-4 已先跑完，应为 648168 + C02-4 本轮生成量（且不超过 693168）。把实际值写进报告。
- **任务级硬止损**：启动 worker 时设置 `LLM_TASK_TOKEN_BUDGET=110000`。只对本次运行生效，不要改 `.env`。超过后后续调用在发出前被拒，任务按 `EXTRACTION_INCOMPLETE` / `BUDGET_EXCEEDED` 结束。
  - 这是软上限：在途调用照常完成，实际最多超出「并发数 × 单次调用」。照实记录，不重跑。
- 必须重启 API 与 worker，确保装的是本分支代码；迁移 017 若尚未执行会在启动时执行（自动备份到 `src/backend/storage/backups/`）。
- 口令只放环境变量 `MEASURE_PASSWORD`；日志、报告、命令行都不得出现密钥或口令。

## 3. 步骤

```bash
python evaluation/measure_web_flow.py extract --base-url http://127.0.0.1:<api端口> \
    --username demo_teacher --password-env MEASURE_PASSWORD \
    --course-name "C03-1 复测 操作系统 PDF" --file datasets/contest/course2-os-ch2/ch2-process-thread.pdf \
    --max-seconds 900 | tee evaluation/raw/c03/course2-pdf-extract.json
python evaluation/measure_web_flow.py audit-task --db <库路径> --task-id <上一步输出的 task_id> \
    --client-elapsed-seconds <上一步的 elapsed_seconds> > evaluation/raw/c03/course2-pdf-task-audit.json
```

到达待审核后，在发布或任何编辑之前导出原始草稿，写入 `evaluation/raw/l11/course2-pdf-draft-headings2.json`（与 L11-6 同样的 `GET /courses/{cid}/graph` 原文，不改动）。**本轮不发布**，所以不产生发布期向量调用。

## 4. 停止条件

- 任务级预算拒绝（`LLM_TASK_TOKEN_BUDGET=110000`）；
- 900 秒未到终态；
- 出现 `auth` / 配置类失败（不重试，报告）；
- 开跑前累计与预期不符。

## 5. 交付

1. `evaluation/raw/c03/`：`extract` 输出与 `audit-task` 输出。
2. `evaluation/raw/l11/course2-pdf-draft-headings2.json`：原始草稿。
3. `evaluation/reports/l11-teacher-loop-2026-10.md` 追加一节「C03-1 修复后复测（course2 PDF）」，不改原有各节：
   - 对照 §1 表：总耗时、实体 / 关系 / repair 各阶段跨度、调用数、计费 token；
   - 知识点 / 关系数与种类、是否出现 `PREREQUISITE`、孤立节点数；
   - 块数（应约 24）；
   - 预算：本轮生成 / 向量分账与累计。
   - 「解析 + 知识抽取」耗时按赛题口径写真实值，不剔除 AI 调用时间。
4. `docs/handoffs/deepseek-c03-1.md`：命令、实际停止原因、预算、偏差与限制。

## 6. 判读要点（不是通过标准）

- 有先修依据才应出现 `PREREQUISITE`。没有出现时照实写，不为凑关系数量要求改提示词。
- 若计费明显低于 110000 且质量接近 Markdown，course1 PDF 是否追加由用户决定，预计会接近 L11-6 course1 Markdown 的量级。
