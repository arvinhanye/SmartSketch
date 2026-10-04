# C02-4 交 DeepSeek harness：问答提示词 v3 与推理埋点真实复测

```text
from: Claude
to: DeepSeek harness
date: 2026-10-03
code: claude/plan-c-reliability（本交接所在提交；包含 ADR-089 推理埋点、迁移 017、answer_with_context v3）
budget: 用户 2026-10-03 批准——本轮生成 token 增量止损 45000；跑完累计不超过 693168（起点 648168）
paid_calls_by_claude: 0
```

## 1. 目的

C02-1 离线诊断（`evaluation/reports/c02-qa-diagnosis.md`）推断：真实模型的不可见推理吃掉 2048 输出预算，并把可见回答推迟到生成末尾，导致比较题截断、首字 3～9 秒。本轮用真实模型回答三个问题：

1. 供应商是否返回推理内容或推理 token。新列 `model_calls.usage_reasoning`、`reasoning_chars`、`first_reasoning_ms`、`first_content_ms` 是否有值；推理占输出的比例是多少。
2. 提示词 v3（直接作答、比较题逐点对照、通常不超过 300 字）下，比较题「栈和队列有什么区别」重复 3 次的结局。
3. 首字三列口径：服务端首个 delta、客户端 SSE 首个 delta、首次推理与首次可见内容。

**不是**严格 A/B：v2 基线（L15 十题）与本轮的时间、网络、供应商状态都不同，报告里只做对照，不下因果结论。

## 2. 环境（由用户安排；不要自行同步或清库）

- **代码**：本分支最新提交，在用户指定的测量 checkout。启动后迁移 017 自动执行（执行前自动备份到 `src/backend/storage/backups/*-before-017.sqlite`）。
- **数据**：沿用 L11-6 / L15 的两门已发布课程：
  - 数据结构 `4f32542066b44f4890cb6f6d765971ed`（v1）；
  - 操作系统 `777c327ca1a247cea7ae36a69ec4a106`（v1）。
  - 学生 `demo_student`，个人模型配置 `deepseek-flash`（ADR-080）。
- **不要**改代码、调高上限、开启重试、切换学生模型；不要在日志、报告或命令行里出现密钥或口令（口令只放环境变量 `MEASURE_PASSWORD`）。

开跑前核对（任一不符即停）：

```bash
PYTHONPATH=src/backend .venv/bin/python -c 'from app.services.qa.generate import ANSWER_MAX_OUTPUT_TOKENS as m, ANSWER_PROMPT_VERSION as v; assert (m, v) == (2048, 3); print(m, v)'
sqlite3 "file:<库路径>?mode=ro" "SELECT filename FROM schema_migrations ORDER BY version DESC LIMIT 1"   # 017_model_call_reasoning.sql
sqlite3 "file:<库路径>?mode=ro" "SELECT COALESCE(SUM(usage_input+usage_output),0) FROM model_calls WHERE purpose <> 'embedding' AND usage_input IS NOT NULL"
```

第三条（当前生成累计）必须为 648168。若更大，说明此后另有调用：停下报告，不要开跑。

## 3. 题目与次数

- `c02-course1.txt`（数据结构，5 题，与 L15 相同）：什么是栈 / 栈和队列有什么区别 / 顺序栈入栈需要检查什么 / 循环队列如何判断空与满 / 今天天气怎么样
- `c02-course2.txt`（操作系统，5 题，与 L15 相同）：什么是进程 / 进程和线程有什么区别 / 进程有哪些基本状态 / PCB 保存哪些信息 / 怎么制作红烧肉
- `c02-repeat.txt`（数据结构）：栈和队列有什么区别（3 行，重复 3 次）

共 13 次提问，其中 2 题课外问题预期 `not_covered`、无生成调用。

## 4. 命令（同一轮共用一个起点，止损按整轮累计）

```bash
export ROUND=$(date -u +%Y-%m-%dT%H:%M:%S.000Z)
for part in course1:4f32542066b44f4890cb6f6d765971ed course2:777c327ca1a247cea7ae36a69ec4a106 repeat:4f32542066b44f4890cb6f6d765971ed; do
  name=${part%%:*}; cid=${part#*:}
  python evaluation/measure_web_flow.py ask --base-url http://127.0.0.1:<api端口> --username demo_student \
      --password-env MEASURE_PASSWORD --course-id "$cid" --questions "c02-${name}.txt" --stream \
      --out evaluation/raw/c02/${name}.jsonl --audit-db <库路径> --cap 45000 --round-started-at "$ROUND" || break
done
python evaluation/measure_web_flow.py audit --db <库路径> --since "$ROUND" --until "$(date -u +%Y-%m-%dT%H:%M:%S.000Z)" > evaluation/raw/c02/audit-window.json
cat evaluation/raw/c02/course1.jsonl evaluation/raw/c02/course2.jsonl evaluation/raw/c02/repeat.jsonl > evaluation/raw/c02/all.jsonl
python evaluation/measure_web_flow.py audit --db <库路径> --records evaluation/raw/c02/all.jsonl > evaluation/raw/c02/audit-records.json
```

- 退出码 3 表示因止损、usage 未知或拿不到响应而停止。`|| break` 保证不再开下一组；照实记录，不重跑。
- 退出码 0 只表示跑完，**不表示都答成功**；以汇总里的 `counts` / `all_answered` 为准。

## 5. 停止条件（任一满足即停，不重试）

- 本轮生成 token 达到 45000（工具每题后自动检查）；
- 出现 usage 未知的生成调用；
- 单题拿不到响应或超过 60 秒；
- 开跑前生成累计不是 648168。

## 6. 交付

1. `evaluation/raw/c02/`：三份逐题 JSONL、两份 `audit` 输出。其中有回答正文与引用，**不得含任何凭据**。
2. `evaluation/reports/c02-qa-v3-real.md`：
   - 逐题表：结局（`outcome` / `error_code` / `error_reason`）、输入 / 输出 / 推理 token、推理字数、首次推理、首次可见内容、服务端首个 delta、客户端 SSE 首个 delta、完整响应、引用数、可见回答字数。
   - 比较题 3 次重复的结局。
   - 首字与完整响应的 p50 / p95 / 最大值，注明分母与最近秩法。
   - 推理是否被供应商返回；推理 token 占输出的比例。
   - 与 L15（v2）对照，注明不是严格 A/B。
   - 预算：本轮生成 / 向量分账，以及跑完后的累计。
3. `docs/handoffs/deepseek-c02-4.md`：命令、实际停止原因、预算、偏差与限制。

## 7. 判读要点（供报告参考，不是通过标准）

- 若推理列为空：供应商未返回推理信息，C02-1 的推断仍未证实；报告如实写「未观测到」，不要据此否定或确认。
- 若推理 token 占比高且首次可见内容接近生成末尾：支持推断，后续是否做「思考控制」（方案 B）由用户决定。
- 比较题 3 次里只要仍有截断，就照实写；不放宽出处校验，不把截断正文当回答。
