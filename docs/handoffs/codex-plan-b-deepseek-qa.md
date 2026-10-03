# 计划 B L15 与 2048 问答实测交接（DeepSeek harness）

状态：待接手，Codex 未调用真实生成模型或线上向量。基线 c85ee53；运行必须使用 codex/plan-b-takeover 的最终修复版本，先记录 git rev-parse HEAD 与 git diff --stat。不在仍为 5a34fec 的冲刺工作树直接测 2048；不要合并/快进/推送，先由用户安排测量代码与数据的同步。

## 先核对

读 AGENTS.md、ADR-082/086、claude-l11-7-deepseek-retest.md、Codex 接手交接。L11-7 PDF 复测仍待报告，本任务不重复抽取，不改旧实测结果。使用已有两门 Markdown 发布课程；禁止清现有数据库。个人模式 real LLM 和部署者在线向量是测量范围；不把假供应商结果当准确率或延迟证明。

最后已知生成计费累计 619217 / 5000000 token；L11-7 可能已增加，先查最新台账，登记 starting_total。用户批准调高上限不等于批准无限新增测量；确认本轮预算后开跑。建议本轮增量硬止损 80000、累计上限 min(starting_total+80000,5000000)。预计一次 10 题，不额外抽取、不自动重试；到停止线或单次 HTTP 60 秒无响应即停止。供应商 usage 缺失时记录未知，不报零；在线向量单独记调用和 usage/费用，不混入生成预算（ADR-082）。密钥/密码只读本地环境，不打印、不提交，不把凭据填到示例命令。

## 运行前检查与命令

在用户准备的测量 checkout 执行（下面 cwd 替换为实际测量目录）：

```bash
git status --short
git rev-parse HEAD
PYTHONPATH="$PWD/src/backend" .venv/bin/python -c 'from app.services.qa.generate import ANSWER_MAX_OUTPUT_TOKENS; assert ANSWER_MAX_OUTPUT_TOKENS == 2048; print(ANSWER_MAX_OUTPUT_TOKENS)'
scripts/start.sh --no-open
```

重启自己启动的 API/worker，沿用独立端口 8001/5174/7688；已有服务先核对归属，不停别人的进程。确认 runtime_mode=personal、教师与学生各自配置、EMBEDDING_MODE=online、问答链路时限=15 秒。复用已有合法课程成员和发布课程，不为本任务重新抽取或重向量化。若需要真实发布向量，先核对既有课程快照与 user 决策再执行，单列预算。

准备两份逐行问题文本（每课 5 题）：
- 数据结构：什么是栈；栈和队列有什么区别；顺序栈入栈需要检查什么；循环队列如何判断空与满；今天天气怎么样。
- 操作系统：什么是进程；进程和线程有什么区别；进程有哪些基本状态；PCB 保存哪些信息；怎么制作红烧肉。

```bash
PYTHONPATH="$PWD/src/backend" .venv/bin/python evaluation/measure_web_flow.py ask \
  --base-url http://127.0.0.1:8001 --username demo_student --password-env MEASURE_PASSWORD \
  --course-id "$COURSE1_ID" --questions "$COURSE1_QUESTIONS_FILE"
# 对 COURSE2_ID/COURSE2_QUESTIONS_FILE 同样执行
```

该脚本输出的是 HTTP 结局摘要，exit 0 不表示所有问题成功；它不输出 request_id/正文/文件名。为每题保存完整脱敏 HTTP 响应，并根据同一 request_id 查询 chat_logs/model_calls；用 SQL 与响应关联，而不是只看退出码。首字耗时从真实 SSE 或 first_delta_latency_ms 读取，JSON 到达时间不算首字。批量前后比较需使用相同模型、问题、课程发布版；1024 采用旧 L02 记录作参考并注明条件差异，如要求严格 A/B 再单独申请预算，不改交付分支常量。

```sql
SELECT request_id, course_id, outcome, reason, error_code, error_reason,
       truncated, invalidation_subtype, latency_ms, first_delta_latency_ms, citations_json
FROM chat_logs WHERE created_at >= :started_at ORDER BY created_at;
SELECT request_id, purpose, status, max_output_tokens, usage_input, usage_output, latency_ms
FROM model_calls WHERE created_at >= :started_at ORDER BY created_at;
```

## 必须输出

写 evaluation/reports/l15-qa-2048-real.md 和 docs/handoffs/deepseek-l15-qa-2048.md：命令/版本/实际退出码；两课各 5 题的完整耗时、首字耗时、终态 answered/not_covered/truncated/timeout/upstream/auth、来源文件名与页码/章节、graph_version、输入输出 usage、费用和累计。问答证据只来自本课；课外问题是否 not_covered；比较类题是否在 2048 内完整结束；逐题检查每个结论的出处，不因增加上限放宽校验。15 秒是否达标按实际完整耗时判定，不从 1024 耗时推断。

单列 D2 在线向量：问答 request_id 同 chat_logs，publish:<version_id> 单列发布，缓存命中不应新增行。单列历史 L11 抽取超过 60 秒与准确率尚待人工评估，不宣称赛题全达标。最终停止本人服务，登记新的 token 总量。只提交测量报告与脱敏证据，业务代码不改，不推送不合并。首个动作：拿到 L11-7 最新报告和预算累计，确认测量 checkout 已包含本轮修复。
