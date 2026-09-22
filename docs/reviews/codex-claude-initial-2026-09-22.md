# Claude 首轮架构与契约审查

日期：2026-09-22。结论：**存在合并前必须修正的契约冲突与验证缺口，暂不建议直接叠加两个分支。** 本次审查覆盖架构/契约/相关规格/门禁，不是两个分支所有 hook、Docker 脚本的完整代码审查。

基线：main `05d214c`；契约分支 `6ccbe5e`；协作分支 `bef9b91`。对应本地工作区审查前均干净。下面路径可在各自 worktree 直接打开；行号绑定上述提交。

## R01 P1 先统一唯一契约源再启动消费者

- 位置：`/Users/arvinhan/Desktop/SmartSketch/.claude/worktrees/tech-plan-review-improvements-ff30e0/src/contracts/README.md:13`；`/Users/arvinhan/Desktop/SmartSketch/.claude/worktrees/multi-agent-contract-format-209be9/docs/decisions/ADR-004-contract-single-source-of-truth.md:15-23`。
- 触发：合并两个分支或让前后端分别按照各自分支开工。一方规定手写 YAML 为唯一源；另一方要求手写 Pydantic 并禁止手改生成物。
- 影响：团队会维护互相覆盖的 DTO、路径和生成物；M0-04 的 DONE 与 TODO 也互相矛盾。两个 ADR-004 的含义不同，按编号引用有歧义。
- 最小修复：协调人选一条生成方向、重新分配冲突 ADR 编号、明确 API 前缀；逐项迁移已有 YAML 的路径/字段到选定真源，增加前后端一致性测试。不是删除已有成果后重做。
- 验收：只有一个可编辑机器真源；生成两次字节一致；漂移检查失败时退出非 0。

## R02 P1 缺关键依赖时契约检查成功退出

- 位置：`/Users/arvinhan/Desktop/SmartSketch/.claude/worktrees/tech-plan-review-improvements-ff30e0/scripts/check_contracts.py:50-55`。
- 复现：在该 worktree 运行 `./scripts/verify.sh`，实际输出 `SKIP contract checks: PyYAML not installed`，随后 `Scaffold verification passed.`，退出码 0。
- 影响：当前环境没有解析任何 YAML，也没有校验引用与枚举；损坏的已冻结契约仍可越过所谓门禁。与“已包含该校验”表述不一致。
- 最小修复：锁定测试依赖；契约存在且进入实现阶段后，缺依赖应失败。若保留仅骨架模式，必须显式传参并输出非完整验收标记。
- 验收：缺依赖、损坏 YAML、坏 `$ref`、非法枚举分别返回非 0；正常契约通过。

## R03 P1 将来源硬约束变成可校验的响应结构

- 位置：`/Users/arvinhan/Desktop/SmartSketch/.claude/worktrees/tech-plan-review-improvements-ff30e0/src/contracts/api.v1.yaml:1103-1118`、`:1583-1603`、`:1612-1625`。
- 触发：后端按 schema 返回 `{"status":"answered","answer":"结论","citations":[]}`；或 Citation 只有 index/chunk_id/document_id/text，省略页码和章节。
- 静态证据：ChatResponse 的 citations 没有按 status 限制的 minItems；SourceRef/Citation 的 required 不含任何定位字段，page/section_path 还接受 null。描述文字说有引用不构成 schema 约束。
- 影响：生成客户端及结构校验会把无依据、不可定位的答案当成合格响应；违反 ADR-003 和来源定位验收。
- 最小修复：按 answered / not_covered 分支约束引用数量；定位字段要求正页码或非空章节/稳定原文位置；服务层继续验证来源确属同课程同发布版本，不能仅靠 schema。
- 验收：上述两个负例被拒；真实引用通过；跨课程/跨版本引用被服务层拒；全部引用失效时输出未覆盖终态。
- 验证边界：本轮为静态检查，未运行完整 schema validator（当前运行库缺相关依赖）。

## R04 P2 问答事件容许空载荷且最终正文的协议不完整

- 位置：`/Users/arvinhan/Desktop/SmartSketch/.claude/worktrees/tech-plan-review-improvements-ff30e0/src/contracts/api.v1.yaml:1635-1656`；同目录 `events.v1.md` 第 3 节。
- 触发：发送 `{}` 作为 meta/delta/done；或复制文档中的 not_covered done 示例，发送 answer 字段。
- 影响：ChatEvent 没有 required、没有按事件类型区分的结构；文档使用 answer 但 schema 没有该属性。自动生成类型难以消费最终替换正文；流式内容引用全部失效时缺明确撤回/替换约定。
- 最小修复：给每种事件独立 payload，定义顺序与异常终止、最终正文/引用/状态；未通过引用校验的前端文本明确为临时状态，done 统一替换或清除。
- 验收：空事件拒绝，任意网络分片可解析；未知引用全失效后页面不留下无依据完成答案。

## R05 P2 同一分支的任务状态规格尚未同步

- 位置：`/Users/arvinhan/Desktop/SmartSketch/.claude/worktrees/multi-agent-contract-format-209be9/specs/course-knowledge-graph.md:22` 对比同 worktree `docs/architecture.md:47`。
- 触发：测试 Agent 按规格编写用例，worker Agent 按架构实现。规格缺 persisting 与 cancelled，架构则要求两者。
- 影响：取消/入库阶段出现未知状态、终态处理及测试不一致；review 等待与任务 completed 的触发者也未定清楚。
- 最小修复：统一状态转换表及终态集合，说明 queued/运行中取消和 awaiting_review 的处理主体；同步 REST、SSE、前端和测试。
- 验收：每条合法与非法转换都有测试；任何终态重连立即返回终态并关闭。

## 其他边界

- 主目录只有 scaffold，因此未发现可供运行审查的业务服务；上述问题不是声称已在线发生的事故。
- 协作分支 frontend/backend 验证脚本在检测到初始化后仍是提示占位，应在骨架任务中改成真实检查，防止未来假绿。
- 课程授权、快照与向量版本隔离、DAG 并发、缓存来源身份与成本熔断列入待实现设计，不当作已存在的代码缺陷。
- Compose、dev-up/down、危险命令 hook 的完整审查尚未覆盖；自动审查状态文件明确保留这个范围。

## 实际运行命令

分别以 main、两个目标 worktree 为 cwd 执行 `./scripts/verify.sh`。三者 exit 0；main 仅结构 PASS；契约分支契约 SKIP；协作分支 backend/frontend/contracts SKIP。还运行了 `git status --short`、`git worktree list --porcelain`、`git diff --stat main...<branch>` 和逐行源码读取。尝试加载 YAML validator 失败，记录为验证缺口，未安装新依赖。
