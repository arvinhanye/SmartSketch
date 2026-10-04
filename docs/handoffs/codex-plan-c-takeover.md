# Codex 计划 C 接手交接

> **2026-10-04 最新状态覆盖（88f9f6f接手）**：原“下一轮测量”已经完成，不按本文旧步骤重跑。详见 `docs/handoffs/codex-plan-c-real-closeout.md` 与 `docs/reviews/codex-plan-c-88f9f6f-closeout.md`；最新生成844451/批准900000、余55549，向量12005另计。本轮两项Minor已修（72f7430、a6b19b7）。stage_c_status仍OPEN（准确率未签收），浏览器首字/v3开启完整基线/MD补测与冻结交用户。以下保留的是上一轮历史记录；旧预算与OPEN Minor状态不再代表当前，不能据其再发付费请求。

```text
date: 2026-10-04
task: C-TAKEOVER / ADR-090 本地收尾 / C06 本地技术门禁
worktree: /Users/arvinhan/.codex/worktrees/plan-c-takeover/SmartSketch
branch: codex/plan-c-takeover
source: /Users/arvinhan/SmartSketch/.claude/worktrees/smartsketch-plan-a-fixes-e70a34
source_head: 082323a5647abda22d013faeee6e4de4731babec
base_of_plan_c: ec1291a
paid_generation_calls: 0
paid_embedding_calls: 0
stage_c_status: OPEN（新真实测量已接手；人工准确率未签收）
```

## 已接手与交付

原Claude16文件未提交方案B已在独立工区按SHA-256核对接入；原工作区HEAD/dirty改动未回退或提交，真实.env与数据库未复制。旧附加PlanB工区有实测数据且基线旧，保留原样；新工区只使用临时测试SQLite与一次性Neo4j、本机假供应商。

- 个人关闭思考开关贯通配置、连接测试、QA改写/答案、抽取/repair；关闭不追加字段，向量不变。
- 迁移018默认false、任务快照及revision缓存；精确修正017测试，并补旧库升级/流式guardrails回归。
- 修复同轮测量达到cap后续跑仍先发一题的问题；题前+题后检查，缺失估算不发新题。
- 前端教师/学生开关保存/刷新闭环，开启后的PDF/MD抽取与学生问答端到端测试。
- 架构、runbook、tasks、审查报告与下一轮DeepSeek准备交接。

本地代码提交：`cb3055c`（后端/契约/迁移/架构），`39de10a`（预算预检修复），`3d13a80`（前端开关）；其他提交见下方冻结记录。不推送不合并。

## 验证命令与实际结果

- 已复现：`test_c02_reasoning.py::test_migration_017_adds_nullable_reasoning_columns` 1 failed（018取代最后迁移）；修正后 `tests/backend/test_c02_reasoning.py tests/backend/test_c02b_disable_thinking.py` **22 passed**。
- 测量续跑回归两例先RED；最小修复后 `tests/tooling/test_c01_measure.py test_c02_c03_measure.py test_c02b_probe.py test_c04_accuracy.py` **54 passed**。
- 项目Python/PATH下 `pytest tests/contracts -q -p no:cacheprovider` **296 passed**。首次PATH遗漏导致3failed/293passed，已纠正，不算通过。
- `./scripts/verify/frontend.sh full` **37文件/913passed**，type-check/build exit0。既有弃用、jsdom环境/大chunk等提示保留，无依赖升级。

最终稳定代码树 `./scripts/verify.sh integration` **exit0**（先完成basic/full，再完成integration与两种E2E）：

| 项 | PASS | 登记SKIP | FAIL |
| --- | ---: | ---: | ---: |
| backend + tooling | 3862 | 27 | 0 |
| frontend（37文件） | 913 | 0 | 0 |
| integration | 393 | 4 | 0 |
| backend-live | 44 | 0 | 0 |
| 演示闭环E2E | 2 | 0 | 0 |
| 个人API本机假供应商E2E | 4 | 0 | 0 |

契约/basic、type-check、build均通过；最终日志 `/private/tmp/plan-c-final-integration.log`。演示运行 `.e2e/20261004-004337`，个人模式 `.e2e/20261004-004442`，每次新SQLite/存储与一次性Neo4j；未使用真实模型/业务库。门禁后仅保存提交与文档收尾，代码树未改变。


最终整次门禁命令（在本交接worktree执行，无.env，选择五个空闲独立端口）：

```bash
env -u VERIFY_NEO4J_URI -u VERIFY_NEO4J_USER -u VERIFY_NEO4J_PASSWORD \
    -u LLM_MODE -u EMBEDDING_MODE -u E2E_NEO4J_URI -u E2E_LLM_MODE -u E2E_EMBEDDING_MODE \
    PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$PWD/src/backend" PYTHON=.venv/bin/python \
    PATH="$PWD/.venv/bin:$PWD/node_modules/.bin:$PATH" \
    E2E_API_PORT=18600 E2E_WEB_PORT=15773 E2E_NEO4J_PORT=18288 E2E_PROVIDER_PORT=19490 VERIFY_NEO4J_PORT=18289 \
    PLAYWRIGHT_CHROMIUM_EXECUTABLE='/Applications/Google Chrome.app/Contents/MacOS/Google Chrome' \
    ./scripts/verify.sh integration
```

日志：`/private/tmp/plan-c-final-integration.log`，定向 `/private/tmp/plan-c-focused.log`、`plan-c-budget-red.log`、`plan-c-budget-green.log`、`plan-c-contract-tests.log`、`plan-c-front-full.log`。日志为本机临时证据，不作为提交的构建产物。初次integration复审后主动中止exit130，最终从头重跑，初次不计PASS。

依赖复用现有.venv/node_modules，未重新安装或升级依赖；PYTHONPATH显式新代码，禁Python缓存。这里的“从零”是新SQLite/存储和一次性图库，不是重装操作系统/下载全部依赖。门禁演示与个人假供应商，不证明真实供应商性能。

## 接口/数据/配置与回滚

契约可选disable_thinking；迁移018两列非空0/1；DTO由既有生成器生成且漂移门禁通过。无新增系统配置/依赖。架构和ADR-090说明省略/测试/快照/cache语义。

各代码提交可独立revert。回退018前代码先停指定API/worker，按018注释删除两列及迁移记录或恢复before-018备份；不要只删除迁移记录。备份恢复会丢后续写入，先保存当前库并经人工决定。不在真实测量库实施本轮迁移/回滚。仅关闭开关不追溯改旧任务快照，等结束或走原取消流程。

## 上一轮未完成项及首个动作（历史；当前见文首新交接）

1. 用户已选择**本地收尾后再确认真实测量预算**；本轮不自动花旧余量。下一轮先确认预算/环境/最新台账，再按 `codex-plan-c-deepseek-next-round.md` 测course2 PDF，决定course1和13题问答。
2. 真PDF91.34秒仍>60，QA旧新轮仅首题冷启动超时、未完成13题；旧8.15秒/15.6秒两段空档未归因。下轮阶段日志需解释，不凭猜测并发重构。
3. C04当前三份与新开关快照各自人工判断，实体/关系≥70%；辅助判断标claude-assist。
4. 两项Minor：错误usage_reasoning未保存（总计费不受影响）；长出处切换继承展开态。见报告与tasks C-MINOR-01/02。
5. 旧工作区凭据留项由数据持有人处理；本轮不读取内容、不迁移到新工区、不改旧实测数据。
6. 真实技术冻结待上述指标/签收；九类参赛材料及视觉重设计继续排除。

生成系统计费累计746357/5000000（含未知估算12116+直连probe手工2551），旧批准803168余56811，向量11946另计；报告中reasoning_tokens=null不是0，probe单短请求不替代质量/性能验收。

审查 `docs/reviews/codex-plan-c-takeover.md`；测量准备 `docs/handoffs/codex-plan-c-deepseek-next-round.md`。原Claude交接及原始DeepSeek证据均保留。

最终已验代码提交：`646c95309b9e8e817ba5544ed4019ccda252fa8d`；后续仅文档收尾。本交接所在文档提交可用 `git log -1` 获取。
