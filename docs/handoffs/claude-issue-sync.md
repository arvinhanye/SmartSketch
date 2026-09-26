# Claude 交接：可开工清单与 GitHub issue 同步（2026-09-26）

- 基线：`main@95d5c9a`（含 #256～#262）。分支 `claude/project-thread-yswyz2`。
- 交付物：`docs/tasks.md` 中 G01～G04、H03 状态改为已合入并注明 issue；新增“可开工清单与 issue 同步”一节。
- GitHub 操作：关闭 #92、#96、#98、#99、#105、#106、#107、#108、#109、#115、#140、#141（各附 PR 评论，标 `status:done`）；#100 标 `status:in-review`（F08 草稿 PR #263）；#110、#111 标 `status:in-progress`（G05、G06 主线进行中）。
- 可开工计算方法：`docs/atomic-tasks.json` 每个未关闭任务的 `depends_on` 全部对应已关闭 issue，且不在进行中集合（G05、G06、F08）。结果：G07、H04、F14、K08、K13。
- 验证：按 CI 装好锁定的契约工具后 `./scripts/verify.sh` exit 0（PASS contracts gate、Scaffold verification passed）；`git diff --check` 无输出。仅改文档，未跑前后端测试。
- 接口/数据变更：无。
- 风险：K13 需真实模型调用，需用户确认预算；F14 与 G05 同在版本/向量区域，开工前核对文件锁。
- 下一步：用户选定开工任务后由对应线程认领。
