# Codex 交接：R1 提交传输截止补充设计

- 日期：2026-10-08；任务 `R1-PERSIST-DEADLINE-DESIGN`。
- 工作区：`/Users/arvinhan/.codex/worktrees/0cf7/SmartSketch`。
- 产品代码基线：`e111315ffabdc5ce980afdf525b8321ef572dc8e`，本轮未改产品代码。
- 状态：补充书面设计待用户评审；未实施、未跑新网络故障实验、发布准入 OPEN。
- 用户授权：「是，按首选方向编写补充设计」。只批准设计阶段，不外推为实施/PR/合并授权。

## 交付与关键决定

- 规格 `docs/superpowers/specs/2026-10-08-worker-persist-deadline-design.md`；同步 `docs/architecture.md`、`specs/task-processing.md`、原 R1 设计 §7、`docs/decisions.md` 候选 ADR-092、`docs/integrations.md` 候选环境项及 `docs/tasks.md`。
- 保留双租约、SQLite 最终围栏与同连接 T6；worker 专用同步门面驱动独占异步 loop/pool，使用公开取消，不改其他图入口或依赖。
- 图尝试绝对截止不因续约/分步应答重置；候选提交默认 2 s、最大 3 s，清理默认 1 s、最大 5 s。默认围栏 ≤3 s 为真实故障准入阈值，不是已验证结果。
- 取消不证明服务器未提交；SQLite 围栏先退出，网络等待型清理在外；无后台提交、跨线程 Session 操作或无界 finally。
- 发现必须处理的恢复排序：旧服务器 COMMIT 可迟到，无贡献预读不能提前清 failed 任务的清理标记；拟改为在课程锁与同一 DraftWriteGuard 后幂等撤销，确认提交再清标记。仅扩展必要 R1 恢复入口，不修其他四项中严重程度问题。
- 文档自审纠正 ADR-091 旧回滚段“当前只有文档”与其本地已实施状态的矛盾；既有核心回退仍暴露 R1，补充回退至 `e111315` 仅重新暴露可用性风险。

## API、数据与配置

本轮无 API/DTO/契约、数据/迁移、依赖或运行配置改动。两个环境预算只登记候选，尚不写入 Settings/`.env.example`；值和详细方案待书面批准。真实密钥、用户 `.env`、业务库和模型请求均未触及。

## 验证记录

- `git diff --check`：exit 0。
- 设计自审：8 个 docs/specs 文件，17 条本地链接全部可解析；新规格代码围栏配对、无未填占位；状态/预算/作用域核对通过，产品/配置文件未变。
- `PATH="/opt/anaconda3/bin:$PATH" PYTHONDONTWRITEBYTECODE=1 PYTEST_ADDOPTS="-p no:cacheprovider" ./scripts/verify.sh`：实际 exit 0；契约测试 237 passed（3/6/5/45/125/53）、门禁负向测试 25 项通过，契约真源/生成物一致，Scaffold verification passed。
- 门禁日志 `/private/tmp/smartsketch-ocr-46o1tbcy/r1-deadline-design-verify.log`；设计文件/链接/状态/哈希记录 `/private/tmp/smartsketch-ocr-46o1tbcy/r1-deadline-design-check.json`。
- 本轮没有新产品、网络故障或 full/integration 测试；不能引用旧 214/34 通过证明补充方案已实施或风险关闭。

## 未完成项与下一动作

请用户评审补充规格，尤其预算、单事务 loop/pool 代价和 failed 清理快路径修订；获批后才编写实施计划，随后确认计划/执行方式。实施需要真实 TCP 黑洞/NOOP/断连/丢应答/迟到结局及退出故障，逐次量化全库写者等待和资源退出，保留已有 R1 回归并跑整次完整 integration。

任务状态不因为设计交付变为风险 CLOSED。当前可开 Draft 供评审的判断不升级为合并/发布许可；本轮不创建 PR、不推送、不合并、不冻结。

## 回滚

本轮仅文档，可独立回退设计文档提交，无业务操作需要恢复。未来补充代码停止 worker 后恢复 `e111315` 无需数据库回滚，但恢复无界提交等待，必须重新 OPEN；不得移除 R1 核心围栏或删除故障测试掩盖失败。
