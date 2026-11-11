# MAIN-INTEGRATE-01：主线整合与旧分支清理

- 状态 DONE；Codex，2026-11-11。用户授权整合需要的分支至 main、清理无用旧分支，覆盖历史任务仅本地、不推送的限制。
- 基线 main `99e169a`；整合提交 `6bbcf14`；[PR #343](https://github.com/arvinhanye/SmartSketch/pull/343) 已合并为 `1dbd272`，#342 随之合并。主检出 `/Users/arvinhan/Desktop/SmartSketch-main` 已切回 main；随后仅补本次收尾文档。

## 交付与关键处理

1. OPT-01～06 已在 #341；本轮引入图谱查找、快捷键与视图记忆（#342，源 `983dcba`），以及抽取性能分支 `e8c20bd`。
2. 抽取 `_Dispatcher`、`_run` 迁入 `workers/extraction/dispatch.py`，与性能分支原实现 AST 2/2 一致；默认并发在 `extraction/types.py` 与应用配置改为 8，保留环境覆盖。公开入口可执行 AST 不变。
3. 测试使用 OPT-03 的共享 db_url 夹具，monkeypatch 指向 OPT-06 拆分后的实际模块；原断言保留。性能测量探针同步到 dispatch，源码身份覆盖五个 extraction 模块。新增真实 worker 观测回归先以 units=0 失败，修正后通过。
4. 保留 OPT-01 归档结构；ADR-011 两条性能补充写入正文卷并更新索引，原归档正文逐字保留。测试索引新增两个后端文件。
5. #342 原 CI run `42970189875`：个人模式首项刷新后推荐列表按新增 URL 选中恢复行为正常折叠，旧用例等待可见导致 1 failed / 3 passed。用例现验证 URL 保留选中 ID，点击已有展开按钮，再继续原推荐/掌握状态断言；不使用 force、不放宽超时、不改产品语义。

## 验证证据

- 定向抽取、E12、测量工具、测试索引：73 passed，38.97 秒，exit 0。重叠用例在旧调度上预期失败；测量观测回归先红后绿。
- 整合代码 `6bbcf14` 的 [CI](https://github.com/arvinhanye/SmartSketch/actions/runs/42973148562) 与 [跨平台检查](https://github.com/arvinhanye/SmartSketch/actions/runs/42973148432) 合计 9 项 SUCCESS：后端/工具 4293 passed / 27 登记 skip，前端 83 文件 / 1414 passed，Neo4j 集成 463 passed / 4 登记 skip，图库专项 44 passed，教师/学生 E2E 2 passed，个人模式 E2E 4 passed。类型检查、构建、启动器 macOS/Intel Mac/Linux/Windows 与浏览器检查通过。
- 本地命令：`PATH="$PWD/.venv/bin:$PATH" PYTHON="$PWD/.venv/bin/python" E2E_PYTHON="$PWD/.venv/bin/python" GOCACHE=/tmp/smartsketch-main-integration-go-cache PLAYWRIGHT_CHROMIUM_EXECUTABLE='/Applications/Google Chrome.app/Contents/MacOS/Google Chrome' ./scripts/verify.sh integration`。
- 本地契约/启动器通过；后端 4293 passed / 27 登记 skip（620.87 秒），前端 1414 passed，Neo4j 463 passed / 4 登记 skip（669.86 秒），图库专项 44 passed。随后 E2E 入口因新 worktree 漏接根目录 node_modules、缺 @playwright/test 而失败，整条命令 exit 1，保留原日志。
- 接回主检出已有根目录依赖（未安装/升级）后：`scripts/e2e.sh tests/e2e/teacher.spec.ts tests/e2e/student.spec.ts` → 2 passed（1.2 分钟）、exit 0；`E2E_LLM_MODE=personal scripts/e2e.sh tests/e2e/personal.spec.ts` → 4 passed（1.9 分钟）、exit 0；均使用上述绝对 E2E_PYTHON 与本机 Chrome。未重跑已通过的长门禁，不将分项补验冒充整条脚本 exit 0。
- 前端自审使用 open-code-review-delegate：18 个可审文件全部读取，排除的文档/测试另按规格与验收核对；没有调用外部付费审查模型。`git diff --check`、源码 AST 对照、契约/提示词零差异检查通过。

## 清理、保护与恢复

- 详见 [逐分支审计](../reviews/branch-cleanup-20261111.md)：原远端 195→16，原本地 20→1；本次临时分支另已删除。保留 main 与 15 个尚含未确认独有内容的历史远端分叉；不把落后提交数当成无用证据。
- 重复 PR #337/#339/#340 关闭，#342/#343 合并，开放 PR 为零。远端删除先 dry-run，采用逐 SHA lease 与 atomic push；未强推 main。
- 完整 bundle（8,731,810 bytes，校验通过）、原始引用清单、删除日志及本地红/绿验证日志，位于主检出 `.demo/branch-cleanup-20261111/`，未提交仓库。
- 主检出原来的 tasks.md 追加段落与两份未跟踪抽取交接稿已逐字核实进入 main；额外保存于 stash `5410571383d83078f79843c5575d9879d0419d21`，三文件字节校验通过。其他工作区的文件、依赖、配置和数据保留，只将清洁检出转为 detached HEAD。
- 恢复旧引用：已合入 main 的提交按审计 SHA 建分支；需恢复未被 main 包含的旧引用时，从上述 bundle fetch 对应 `refs/remotes/origin/<branch>` 到新的恢复分支。不要直接用旧 tasks.md 覆盖当前归档看板。

## 接口、数据与剩余边界

无新增 API、迁移、依赖或付费模型调用。默认并发 8 可通过 `LLM_MAX_CONCURRENCY=4` 恢复旧上限；调度检查点格式不变。真实模型准确率/耗时尚未验收，图库持久化与发布向量化仍 OPEN；既有窄屏/读屏等验收限制不因合并而关闭。

本任务无需进一步人工决策。若继续处理保留的历史分叉，先逐项判断哪些独有行为仍适用于当前产品，再单独验收；不整体覆盖现有实现。
