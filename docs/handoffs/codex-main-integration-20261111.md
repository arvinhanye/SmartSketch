# MAIN-INTEGRATE-01：主线整合与旧分支清理

- 状态：IN_PROGRESS；负责人 Codex；2026-11-11。
- 用户授权：将需要的分支内容整合至 main，并清理无用旧分支；覆盖历史任务仅本地、不推送的限制。
- 起点：main/origin/main `99e169a`；原检出在 `codex/opt-05-backend-layering@99c1f01`，有未提交任务段落和两份未跟踪抽取交接稿，未覆盖。
- 隔离工作区：`/Users/arvinhan/.codex/worktrees/main-integration-20261111/SmartSketch-main`，分支 `codex/main-integration-20261111`。

## 整合

1. OPT-01～06 已随 #341 进入 main，无需重复引入。
2. 图谱查找 #342，源 `983dcba`，已经包含 main；保留原规格及已记录的浏览器/读屏验收限制。
3. 抽取性能分支 `e8c20bd`：保留共享池调度、默认并发 8、测量工具及原始证据；真实模型准确率/耗时尚未验收，图库优化及发布向量化仍 OPEN。
4. 解决 OPT-06 拆分冲突：`_Dispatcher`、`_run` 迁入 `workers/extraction/dispatch.py`，AST 与性能分支原实现 2/2 一致；默认值在 `extraction/types.py` 更新，旧公开导出保留。
5. 性能测试适配 OPT-03 共享 `db_url` 夹具及拆分模块中的 monkeypatch 位置；保留原断言。
6. 测量探针也必须绑定实际 `dispatch` 模块，源码身份覆盖全部五个 extraction 模块。新增真实 worker 回归先失败（units=0），修正后与原用例共同通过。
7. 保留 OPT-01 归档布局，将 ADR-011 两条性能补充写入正文卷并同步索引；测试索引补入两个后端测试文件。

## 已验证

- 原共享池重叠用例在主线旧调度上预期失败（global chunk barrier）；迁移后通过。
- 抽取/E12/测量工具/测试索引定向：73 passed，38.97 秒，exit 0。
- `git diff --check`：通过。
- 完整 integration 门禁正在执行，结果待补；不以定向测试替代完整门禁。
- 前端代码自审采用 open-code-review-delegate：18 个可审文件全部读取；其 8 个默认排除的文档/测试另按规格和验收核对。未运行外部付费审查模型。

## 分支清理

- 初始远端 195 个分支、本地 20 个分支；逐引用记录见 [分支审计](../reviews/branch-cleanup-20261111.md)。
- 已关闭重复 PR #337/#339/#340：前者与 main 文件树一致，后两者提交已由 #341 集成。
- 已原子删除 178 个远端旧引用，dry-run 与实际 push 均 exit 0；逐分支 SHA lease 保护，远端复核剩余 17。
- 删除依据为已合并、补丁等价、或被保留分支完整包含；保留旧 UI/Windows/级联删除等未确认独有工作，不将“落后”当成“无用”。
- 完整 Git bundle（8,731,810 bytes，校验通过）和原引用/操作日志保存在主检出 `.demo/branch-cleanup-20261111/`，未提交仓库。

## 接口、数据、风险与回滚

- 本轮不新增 API、迁移、依赖或付费模型调用；继承性能分支默认并发 8，可显式设置 `LLM_MAX_CONCURRENCY=4` 恢复原上限。
- 已清理 16 个本地旧分支；其干净 worktree 转为 detached HEAD，目录、依赖、本地环境和数据全部保留。原脏检出与待整合分支暂留。
- 已合并分支可用审计表中的 SHA 恢复；需恢复未被 main 包含的历史引用时，先从本地 bundle fetch 对应 refs/remotes/origin/<branch>。
- #342 原 CI run `42970189875` 的失败：个人模式首条 E2E 在刷新后等待推荐项可见，但新增 URL 恢复选中状态使推荐正常折叠；实际 3 passed / 1 failed。补充验证 URL 中的选中 ID，点击原有推荐展开按钮后继续原断言，无 force、超时放宽或产品语义改动。
- 下一步：完成 integration 门禁、提交/推送整合结果、更新本地 main 与最终清理记录。
