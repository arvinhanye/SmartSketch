# 计划 B 第二阶段收尾交接

```text
task_id: B-CLOSEOUT
review_status: ready_for_review
status: 功能交付收尾完成；质量/性能验收有保留
worktree: /Users/arvinhan/.codex/worktrees/plan-b-takeover/SmartSketch
branch: codex/plan-b-takeover
base_commit: 96f3885af54cbc788cc6756c02779e63ae04187e
measurement_code_commit: 257750e185f43d547bf9045558d9adc4a183201d
head_commit: 本文件所在收尾提交
owner: Codex
```

## 交付文件

- `docs/reviews/codex-plan-b-96f3885-closeout.md`：真实测量审查、证据/统计问题、预算、验收矩阵、下一阶段顺序。
- `evaluation/raw/l15/codex-closeout-audit.json`：十题、额外尝试、19条脱敏调用及预算重算；补齐失败题关联。保留DeepSeek原始三文件。
- `docs/tasks.md`：L12/L13本地验收DONE；L15真实抽样已完成；L11代码实现完成但PDF真实复测OPEN；B-CLOSEOUT DONE；五项后续待办显式登记。
- `specs/grounded-qa.md`：2048实测已到，维持上限、校验和截止规则。
- `docs/superpowers/plans/2026-10-03-contest-sprint-b-functional-loop.md`：更新过时规划状态，保留原设计步骤，现时状态以看板为准。

没有接口、契约、业务代码、迁移、依赖或部署配置变更；没有新的真实模型/向量请求。原Codex dirty工作区与Claude工作区保留，未推送/合并/快进任何分支。

## 核验结果与限制

十题：7 answered、1 HTTP503/error/LLM_UNAVAILABLE/truncated、2正确not_covered；全部完整终态≤15秒，最大10.27秒。课程内7/8回答成功，不是抽取准确率。已回答首delta3028–9287ms、中位5020ms，0/7达到3秒，是服务端记录而非浏览器可见SSE延迟。七题引用与原始文本逐题核对一致，文档数据库归属均在本课。

2048仍截断比较题；额外尝试因Accept/传输方式不同及测量端中断，只说明观测结局不同，不作为严格重复性或1024/2048 A/B结论。供应商status=ok不等于应用回答通过校验。

本轮9生成调用18764+10187=28951 token（含额外尝试4606），累计648168/5000000；10向量59 token，累计11943，单列。本地summary的18调用/29007不是正式生成账本：字符串时间边界漏掉同秒3向量token，并混算两类usage；正确19调用，合计29010。正式DeepSeek报告的28951/59正确，测量脚本先修再用于后续硬止损。

L11-7未收到PDF headings/2真实复测；旧四份抽取75.51–200.37秒均超60秒；准确率未人工判定。上述项目留OPEN，不签成赛题全达标。

## 本轮验证与实际结果

当前worktree执行，不读取.env，不连接开发Neo4j：

```bash
env -u VERIFY_NEO4J_URI -u VERIFY_NEO4J_USER -u VERIFY_NEO4J_PASSWORD \
    -u LLM_MODE -u EMBEDDING_MODE PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH="$PWD/src/backend" PYTHON=.venv/bin/python \
    PATH="$PWD/.venv/bin:$PWD/node_modules/.bin:$PATH" ./scripts/verify.sh full
# exit0：后端3780 passed/27已登记skip，前端37文件901 passed，type-check/build/契约通过

env -u LLM_MODE -u EMBEDDING_MODE PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH="$PWD/src/backend" .venv/bin/python -m pytest \
    tests/backend/test_d1.py tests/backend/test_d2.py tests/backend/test_d3.py \
    tests/backend/test_l15.py tests/backend/test_l11_pdf_reflow.py -q -p no:cacheprovider
# exit0：56 passed

python3 /private/tmp/audit_plan_b_closeout.py
# exit0：十题+额外尝试、19调用、日志/HTTP/文档课程归属、usage与时间边界差异断言通过

git diff --check
# exit0

git diff --exit-code 96f3885 -- docs/handoffs/deepseek-l15-qa-2048.md \
    evaluation/raw/l15/question-evidence.json evaluation/reports/l15-qa-2048-real.md
# exit0：原始三文件未修改
```

本次日志：`/private/tmp/plan-b-closeout-full.log`、`/private/tmp/plan-b-closeout-targeted.log`。既有Starlette弃用、G6构建包大小及夹具Vue注入告警仍存在，无失败。不删测试、不改期望规避门禁。

本轮**未重跑integration/E2E**：仅文档与证据改动，且测量checkout已有真实运行数据。此前257750e的完整integration exit0在 `codex-plan-b-takeover.md`，不作为此次新跑结果。读库始终mode=ro/query_only，仅取白名单字段，不读凭据表。

无需数据库也可重算核验产物：

```bash
python3 - <<'PY'
import json, statistics
from pathlib import Path
x=json.loads(Path('evaluation/raw/l15/codex-closeout-audit.json').read_text())
q=x['questions']; c=x['model_calls']
assert len(q)==10 and len(c)==19
assert sum(r['usage_input']+r['usage_output'] for r in c if r['purpose']=='answer_with_context')==28951
assert sum(r['usage_input']+r['usage_output'] for r in c if r['purpose']=='embedding')==59
assert all(r['client_elapsed_seconds']<=15 for r in q)
f=[r['first_delta_latency_ms'] for r in q if r['outcome']=='answered']
assert len(f)==7 and all(t>3000 for t in f) and statistics.median(f)==5020
print('PASS: portable evidence calculations')
PY
```

## 下一位执行者首个动作

读本交接与收尾报告，在docs/tasks认领后续范围。建议L16–L19最小顺序（此清单不是实施或新增付费授权）：
1. 固定测量工具，单列真实SSE首字；离线复现比较题后优化短答案/上下文/分段时延，出处和15秒不放宽。付费测量仍交DeepSeek且先确认预算。
2. DeepSeek补L11-7，两份PDF各一次并核headings/2。最新已知生成累计648168；旧850000累计停止线余201832，整轮最高预估250000会越线，执行前核最新台账并确认预算，临界前停止，不自动调额。
3. 用未改写快照评估实体/关系准确率，诊断模型阶段；主线稳定后轻量美化、运行说明与参赛材料、干净部署/演示冻结。自动出题、3D、管理员统一生成模型配置仍不纳入。

推送、PR或合回目标分支待用户决定，当前保持本地分支和工作树。测量.env/SQLite已有运行证据，不自动清理；不停止共享Neo4j。

## 回滚

仅文档/证据提交，确认后用git revert回退本收尾提交，无数据库或代码迁移。保留96f3885原始证据；不删除运行数据来回滚。下一阶段预算/阈值/接口变更各自决定并提供回滚步骤。
