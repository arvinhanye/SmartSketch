# Codex 交接：邀请码、悬停性能与行为保持重构

- 日期：2026-11-05；状态：实施中。
- 分支：`codex/invite-hover-refactor`，起点 `445bfc9`（包含界面改版 `ef5e297` 与本轮 Claude 交接）。工作区起始干净；只本地提交，不推送、PR、合并或发布。
- 顺序与范围：GRAPH-HOVER-01 → INVITE-01 → REFACTOR-01，遵循用户明确批准的交接稿；不新增/升级依赖、不改图谱主题色与已有 data-test。

## 基线

| 命令 | 实际结果 | 耗时 |
| --- | --- | --- |
| `npm --prefix src/frontend run type-check` | exit 0 | 23.63s |
| `cd src/frontend && npx vitest --run` | 78 文件、1311 passed；exit 0 | 38.39s |
| `cd src/frontend && npx vite build` | exit 0 | 3.06s |
| `PATH="$PWD/.venv/bin:$PATH" ./scripts/verify.sh` | basic/契约门禁 exit 0 | 223.93s |

完整日志与机读摘要：`/private/tmp/smartsketch-invite-hover-20261105/`。运行时 Node v26.4.0、Python 3.11.9。Docker Desktop 启动后用 `PATH="$HOME/.docker/bin:$PATH" scripts/start-demo.sh --no-open` 启动既有演示环境；模型与向量均 demo，无付费模型请求。

## GRAPH-HOVER-01

- RED：`npm --prefix src/frontend test -- --run ../../tests/frontend/graph-enhancer.test.ts --reporter=dot`，39 条中 14 failed/25 passed；尚未改生产代码时复现停留阈值、重复状态、兜底、数据替换、销毁与异步覆盖问题。
- 原语义断言保留，FakeEnhancedGraph 增加按元素累计状态；状态批次另用于确认差分。
- 优化前真实演示图 64 节点+71 边，1440×900，普通/预览各 10 次移入+移出。使用真实 G6 `Graph.prototype.setElementState` 包裹同步计时、PerformanceObserver 长任务；通过 G6 事件派发做确定性重复，**不是物理鼠标轨迹测量**。
- 普通：20 次均 135 元素，同步 32.2–47.8ms，未记录 >50ms 长任务；预览：20 次均 135 元素，32.2–45.9ms，未记录 >50ms 长任务。详细数组 `hover-metrics.json`；本次未复现历史 63ms 上限，不把历史数值当成本机新基线。
- GREEN：三组定向（graph-enhancer、graph-lifecycle-enhance、graph-canvas-enhanced）3 文件/77 passed；全量前端78 文件/1326 passed，type-check与basic exit0。
- 第1/2项优化后：普通完整进出33.3–58.7ms（135元素，2次>50ms长任务），预览32.6–43.7ms（134元素，无长任务）。快速划过10次零写入，相邻切换10次均20元素、8.5–15.8ms。**全进出目标尚未全部达到；用户已明确选择保留现有淡化，仅交付第1/2项并记录该限制，继续A/C。**
- 首轮优化后采样与baseline环境不一致（basic仍运行且临时开启Vite轮询监听），普通33.4–70.4ms、预览46.3–194.4ms；原始值保留在`after_during_basic`，不作为同环境前后对比。关闭轮询、待测试完成后采集上述`after_idle`，没有删除不利观测。
- 临时探针与index入口已撤回；最终type-check、build、basic均exit0；当前状态写入与停留测试通过不代表全进出性能已解决。

## INVITE-01

未实施。用户已决：允许入未发布课程，提示“教师发布后可见”；保留原列表可见性，已发布课程成功后刷新并高亮。

## REFACTOR-01

只读审计进行中；实施与分类提交须在 A 完成后。

## 未完成与下一步

完成 B 定向与浏览器复测、全量前端/basic，记录提交；按已确认的未发布课程规则及契约→生成→ADR/规格→迁移020→后端→前端顺序实施 A，再进行 C。
