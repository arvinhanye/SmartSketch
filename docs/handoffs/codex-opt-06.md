# OPT-06：四个大文件职责拆分

- task_id：OPT-06；负责人 Codex；状态 **DONE_LOCAL**（四项本地实现与验收完成，未推送/创建或合并远端 PR）。
- 用户决定：允许本地整合 OPT-03/05 后继续；**暂不推送或合并远端 PR**。
- 工作区：`/Users/arvinhan/.codex/worktrees/opt-06-responsibility-split/SmartSketch-main`；最终代码位于 `codex/opt-06b-extraction`。
- 原交接：审查分支 `claude/code-structure-review-handoff-49e73a` 的 `docs/handoffs/claude-code-structure-review-codex-handoff.md:86–90`。每个原候选文件独立 PR 范围，保留旧导入/导出，不改行为。

## 依赖核查与整合

2026-11-10 查询时：OPT-03 为本地 `36c1f92`，未找到对应远端分支或 PR；OPT-05 [PR #339](https://github.com/arvinhanye/SmartSketch/pull/339) 为 open / merged=false，head `99c1f01`，base `codex/opt-base-ad63341`；底座 [PR #338](https://github.com/arvinhanye/SmartSketch/pull/338) 同样未合并。整合前原目录 HEAD `99c1f01` 含 OPT-05、不含 OPT-03，不能直接满足原交接的远端合入前置条件。

收到用户允许本地整合的明确回复后，用原提交历史建立本地 merge `ec92026`（父提交 `36c1f92`、`99c1f01`）。仅 `docs/tasks.md` 文本冲突，保留双方任务记录；产品与测试路径没有冲突。OPT-03 祖先中的 `eca579c` 个人模式 E2E 辅助修复随之进入基线。文档准备提交为 `ffef748`。原目录 EXTRACT-PERF-01 的任务追加与两份未跟踪 Claude 交接保持原样。

整合后、任何产品改动前实际运行 `PATH="$PWD/.venv/bin:$PATH" GOCACHE="$PWD/.demo/opt-06/go-build-cache" ./scripts/verify.sh full`：**exit 0**；后端/工具测试 **4264 passed / 27 登记 skip**，前端 **82 文件 / 1375 passed**、type-check/build 通过，基础/契约及启动相关门禁通过。总耗时 1059.1 秒，日志 `baseline-full.log` / `.exit`。这不是 `integration` 模式验收，也不改变 OPT-02/05 原有未完成事项的状态。

## 独立交付范围

| 项 | 分支 | 未来 PR base | 本地实现提交 | 原文件行数 |
| --- | --- | --- | --- | --- |
| A 兼容客户端 | codex/opt-06a-compatible | codex/opt-06-base | 7cccaaa | 1074 → 423 |
| C 材料页逻辑 | codex/opt-06c-materials | codex/opt-06a-compatible | 936b41e | 843 → 547 |
| D 学生图谱页面 | codex/opt-06d-student-graph | codex/opt-06c-materials | 3974731 | 789 → 635 |
| B 抽取任务 | codex/opt-06b-extraction | codex/opt-06d-student-graph | 76d1fd7 | 1020 → 260 |

四项为叠加本地分支：未来 PR 应以上一分支为 base，避免把之前候选文件重复装入后续 PR。执行顺序 A → C → D → B：A 后端全量运行时只修改互不依赖的前端，后端/测试 298 个文件哈希未变；B 等 A 完成后才改。每项源码映射在 `docs/architecture.md`，具体交接为 `codex-opt-06a.md`、`codex-opt-06b.md`、`codex-opt-06c.md`、`codex-opt-06d.md`。

## 验证证据

| 范围 | 定向回归 | 完整门禁 / 结构证据 |
| --- | --- | --- |
| A | E03/E04/L05/C02b：413 passed | 后端 full 4264 passed / 27 skip，exit 0；44 定义 / 30 签名与对象身份核对通过 |
| C | H02：95 passed | 前端 full 82 文件 / 1375 passed、type-check/build exit 0；41 声明 / 14 导出不变，主函数体逐字相同 |
| D | H11/I06/L13/L14/workbench：135 passed | 前端 full 82 文件 / 1375 passed、type-check/build exit 0；81 声明不变，模板/样式逐字相同 |
| B | E12/demo/C02/K02：87 passed | 60 定义 / 47 签名及对象身份核对通过；后端 full 4264 passed / 27 登记 skip，exit 0 |
| 共用收尾 | 最终 `./scripts/verify.sh` | exit 0（223.7 秒）；最终 diff 检查通过，独立审查无可操作问题 |

浏览器：本机 Chrome、固定伪造课程/API，1440/1280/768/390 × 900，各一张概览和深链接详情截图；分隔条拖拽/键盘、窄屏抽屉/Esc、关闭还焦点、掌握写入/推荐刷新、列表/图谱和布局切换均通过，无 pageerror/横向溢出。初次两张宽屏概览差异来自缩略图异步绘制，补上“画布有实际像素”条件后，**8/8 图逐像素相同，布局和交互记录完全一致**。没有改产品等待逻辑。此为前端伪造 API 走查，不代替真实服务 E2E。

证据目录：`.superpowers/sdd/2026-11-10-opt-06-responsibility-split/`（本机忽略目录，保留日志、退出码、AST 审计、执行脚本、before/after 及 before-settled/after-settled 截图、visual-comparison-settled.json）。各分项交接列出实际命令。Python 3.11.9 / Node v26.4.0 / npm 11.17.0；无依赖安装升级、无真实付费模型调用。保留已有 Starlette/jsdom/测试警告及 bundle 大小提示，没有放宽断言、超时或跳过登记。

## 接口、回滚与后续

- 无 API/契约、数据库、配置默认值、提示词、界面文案或样式变更。仅内部职责搬移与源码映射更新；纯搬移复用现有行为测试和结构审计，不添加只验证文件布局的测试。
- 没有迁移；回滚代码时按独立实现提交逆序撤销相应范围即可，保留依赖整合历史。
- `codex/extraction-perf` 与 extract_task 有重叠，未纳入本轮；默认并发 4 与原阶段屏障保持。将来整合提速分支须基于新 extraction 模块移植并重新验证。
- 本地范围已完成，四个实现范围和最终验收记录可审查。远端 PR 创建/合并不在本轮授权内，未执行。

## 最终独立审查

独立 fresh-context reviewer 审查了 `ffef748` 至四项最终源码（B 当时为暂存状态），未发现 Critical/Important/Minor 可操作问题。检查涵盖 794 处 Python 全局读取、13 个模块的新进程导入、198 项类型注解解析，以及实际测试注入点和 Vue 生命周期；未重复长测试。完整报告与执行方范围裁定保存在 `final-review.md` 和 `progress.md`。

定义移动会改变 __module__/repr/新 pickle 的来源路径；未发现业务/持久化消费者依赖这些元数据。旧导入和对象再导出、实际类方法注入保持，未额外承诺任意重新赋值旧模块 helper 后的新模块动态转发。保留既有算法/UI；不把本轮 Chrome 固定 API 走查表述成真实模型或其他浏览器验收。

B 全量及共用门禁都自然结束、退出码 0 后才创建 B 实现提交；后续收尾只更新文档。B 门禁期间 304 个后端/测试文件哈希保持不变。代码、测试、契约、配置与依赖范围最终检查通过；执行日志按项目交接要求留在本机忽略目录。
