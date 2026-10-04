# L11 教师闭环（计划 B）交接

```text
task_ids: L11-1～L11-5（L11-6 交 DeepSeek harness）
review_status: in_progress（阶段门禁待跑）
worktree: /Users/arvinhan/SmartSketch/.claude/worktrees/smartsketch-plan-a-fixes-e70a34
branch: claude/smartsketch-plan-a-fixes-e70a34（快进同步到 claude/smartsketch-contest-sprint-77644f）
base_commit: d766f40（计划 B 基线）
author: Claude
```

## 交付物与提交

| 子任务 | 提交 | 内容 | 证据 |
| --- | --- | --- | --- |
| B0 | — | 基线确认：两个工作树同为 `34372c7`、干净；迁移 016 留给首次 `start.sh` 自动完成（交接 harness 核对） | — |
| L11-1 | `44707e9` | `datasets/contest/` 两门课各一章（MD + Chrome 打印的文本型 PDF）与 `scripts/build-contest-pdfs.sh`；修复 PDF 部首形近字（ADR-083，`pdf/2`） | `test_l11_datasets.py` red → green；解析相关 1840 passed |
| L11-2 | `43c4f82`、`b00b66d` | `scripts/fake_provider.py`：包装演示模型的 OpenAI 兼容接口；`sk-fake-bad` 401、`sk-fake-slow` 慢速、`X-Fake-Delay` | `tests/tooling/test_l11_fake_provider.py` 13 passed |
| L11-3 | `6040360`、`c0c74eb` | 个人模式端到端；走查修复两个前端阻断：节点下拉框、以选中节点来源新建知识点 | `tests/frontend/l11.test.ts` red → green；`personal.spec.ts` |
| L11-4 | `7095e87` | 发布被拦时逐条列出原因（按需读草稿图取名称） | `l11.test.ts` red 4 → green |
| L11-5 | `b00b66d` | 处理中取消后重传端到端；预算与超时文案（已有覆盖） | `personal.spec.ts` 3 passed |
| L11-6 | 交接 | `docs/handoffs/claude-l11-6-deepseek-handoff.md` | 待 harness |

## 验证

- `E2E_LLM_MODE=personal scripts/e2e.sh tests/e2e/personal.spec.ts`（独立端口 18100/15273/17788/18990）：3 passed，日志 `.e2e/20261003-094304`。
- 前端全量 818 passed；`npm run type-check` exit 0。
- 阶段门禁（`verify.sh integration`）：见任务板更新。

## 接口与数据变更

- 前端：`NodeEditApi.create`；`useNodeCreator`、`NodeCreator.vue`；`useVersions` 新增 `blockedReasons` 与可选 `nodeNames`。没有契约变更（新建知识点接口早已存在）。
- 后端：PDF 解析器 `pdf/2`（ADR-083）。同一 PDF 重新上传会得到新修订，已有数据不变。
- 脚本：`e2e.sh` 支持 `E2E_LLM_MODE=personal`；集成门禁分别跑演示与个人模式端到端。

## 风险与观察

1. 同章两种格式都上传会产生大量同名知识点（R05，跨任务融合不在本期）。演示时建议一门课只放一种格式，或在审核队列合并。
2. 截图证据：129 个节点时画布整图缩成一条（R06，L13 修）；推荐理由直接显示缺省「难度 0.5000」（R11，L14 修）。
3. pdfminer 对 Chrome 生成的 PDF 打印大量 FontBBox 告警，不影响提取。
4. 另一会话在同时使用 17689 端口跑集成门禁；本会话端到端改用独立端口，避免冲突。

## 下一步

L11 阶段门禁 → L12 来源查看。
