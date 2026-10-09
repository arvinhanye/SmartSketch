# Codex 交接：R1 提交截止实施与后续验证修复

- 日期：2026-10-08；任务 `R1-PERSIST-DEADLINE`、`R1-DEADLINE-VERIFY-REPAIR`。
- 工作区：`/Users/arvinhan/.codex/worktrees/0cf7/SmartSketch`，保留受管 detached HEAD；产品最新修复提交 `2ea6319`；测试证明 `b89844b`、门禁修复 `b7e84a1`。
- 用户已确认七任务计划，并要求修复后续 NOOP、F13、E2E 失败；最新授权在门禁通过后推送并开 PR，不授权合并/部署/技术冻结。
- 当前：核心产品及后续三类失败已修复并验证；最终代码 `f9c54553` 整次 integration exit 0，限定 worker COMMIT 围栏可用性风险 CLOSED；草稿 PR #324 已创建。全项目 stage_c_status OPEN、technical_freeze NOT_PERFORMED 不变。

## 交付、接口与配置

- 专用 `PersistTransport` 同线程同步门面、每尝试独占 Runner/AsyncDriver；固定图截止、公开 Session.cancel、共享退出预算；退出 SQLite 围栏后才等待网络资源清理。
- SQLite 连接/BEGIN 的剩余预算、双令牌最终围栏、同连接 T6；提交不确定保持令牌并不做 T6/内联重放。
- 接管与 failed 撤销经 DraftWriteGuard 排序，无贡献也不提前清标记；确认撤销提交与资源退出后清标记（ADR-072 修订）。
- 两个已生效环境变量：`TASK_PERSIST_COMMIT_TIMEOUT_SECONDS` 默认 2、上限 3；`TASK_PERSIST_CLEANUP_TIMEOUT_SECONDS` 默认 1、上限 5。无公共 API/DTO/事件、DDL/迁移、依赖升级。
- 最终审查两项 Important 已 RED→GREEN：DNS 启动错误稳定脱敏归重试连接故障；T6 结局读回同时匹配 persisted attempt，拒绝误认回滚后的接管者同序号完成。
- 当前修复不改上述产品行为或预算：代理区分 FIN 和真实 RST，`client_disconnected` 只由真实 client socket 的 EOF/reset 设置（不以代理自己关闭作证）；保留 FIN-only `client_eof` 和分别时间戳。集成脚本把所选 `PYTHON` 传给两种 E2E，尊重显式 `E2E_PYTHON` 覆盖。演示/K09 fixture 补齐专用异步工厂，保留全部业务断言及同步图入口。

## 已验证证据（不拼接成整次通过）

日志/XML/源码 manifest 位于 `/Users/arvinhan/.codex/worktrees/0cf7/SmartSketch/.superpowers/sdd/2026-10-08-worker-persist-deadline/`；真实逐次计时追加在 `/private/tmp/smartsketch-r1-network-evidence.jsonl`，带 fixture run_id、预算及产品/测试 SHA256，不含认证或正文。

| 验证 | 当前已观察结局 |
| --- | --- |
| 上轮定向 | 283 passed；仅定向证据 |
| 上轮旧网络矩阵 | 64 passed；不代替增强恢复及整次门禁 |
| 上轮整次 integration | FAILED：backend 3 failed/3997 passed/27 登记 skip；integration 5 failed/457 passed/4 登记 skip；E2E 未起跑 |
| 本轮工具 RED | 真实 SO_LINGER RST 事件遗漏、隐式解释器未传递（2 failed/1 passed） |
| 本轮工具 GREEN | 25 passed（代理/K11 全部） |
| 本轮隔离业务 RED | 34 F13/R1 passed；4 demo/K09 failed（缺专用工厂） |
| 本轮隔离业务 GREEN | 38 passed，零 skip；新自有实例就绪 31.041s、真实 async 连接 0.032s、健康 COMMIT 0.004s |
| 本轮完整定向 | 304 passed，零 skip；1 个既有 Starlette 弃用警告 |

旧 F13 错误日志含旧端口 Connection refused／DDL 第一句失败；本轮已核实旧 fixture 不存在。新单实例实测 F13/R1 全绿，未更改其业务断言或放宽截止。上轮 backend gate 堆栈仍走旧启动分支，之前用进程耗时推断导入最终修复的判断撤销；当前整次门禁在全部源码修改后重新启动。

## 已执行命令与最终收尾

统一测试解释器 `/private/tmp/smartsketch-r1-repair-venv/bin/python`：只装项目声明测试版本，通过只读 .pth 使用应用锁定依赖；未修改应用 venv。Playwright 浏览器在 `/private/tmp/smartsketch-r1-repair-playwright`，node_modules 沿现有锁文件；根目录 .env 不存在，未读取/复制本机 .env。

- `P tests/tooling/test_worker_bolt_proxy.py tests/tooling/test_k11.py -q -p no:cacheprovider`（P 为上述 Python，配 `PYTHONPATH=$PWD/src/backend`、`PYTHONDONTWRITEBYTECODE=1`、`PYTEST_DISABLE_PLUGIN_AUTOLOAD=1`）。
- 本轮隔离业务 wrapper `/private/tmp/smartsketch-r1-repair-live.py` 自建带随机所有权标签实例，退出只删除该 ID；先设置各历史图库 fixture 前缀，再运行 F13/R1/demo/K09 四文件，实测 38 passed。
- 全部 65 个真实网络用例已通过（185.67s、零 skip），日志 `repair-network.log` / XML；默认围栏 ≤3s、上限 ≤4s，退出 ≤配置+1s，未改阈值。两条迟到实验分别要求真实取消后服务器提交并验证接管/failed 清理，旧图守卫等待另有确定性案例，不能混同。
- 当前整次命令：`PATH="/Users/arvinhan/.docker/bin:/opt/anaconda3/bin:$PATH" PYTHON=/private/tmp/smartsketch-r1-repair-venv/bin/python PLAYWRIGHT_BROWSERS_PATH=/private/tmp/smartsketch-r1-repair-playwright PYTHONDONTWRITEBYTECODE=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTEST_ADDOPTS="-p no:cacheprovider" ./scripts/verify.sh integration`；最终成功日志 `repair-full-final.log`，整次 exit 0；使用既有端口覆盖 59598/59599/59600/59601/59602。此前失败日志均保留，不拼接部分通过。
- 下一首步：核对证据/源码 manifest，文档收尾后跑 basic，创建用户已授权的修复 PR；不自动合并/部署/冻结。

## 风险、边界与回滚

仅针对 worker 网络 COMMIT 无界占 SQLite 围栏的风险准入。DNS 默认执行器退出、一般 worker 进程停机、其他图入口、宿主进程暂停/存储故障不在硬实时保证内；健康本机上的测量不可外推。原四项中严重程度发现与教师锁残留窗口不纳入本轮。

停止 worker 后恢复 `e111315` 无数据迁移，但网络无界提交等待重新 OPEN；不撤销核心 R1 围栏、不做破坏性 reset。测试脚本/代理修复可单独回退，回退 EOF-only 观察和不传解释器会重新引入验证失败。保留所有失败日志和当前 worktree；容器/代理只清理自己创建且所有权已核对的对象。

## 执行裁决（按记录顺序，含代价）

- Task 4: Ruling: old lost-COMMIT-ack test now expects LOST with retained token — approved unknown-outcome policy replaces immediate release — reclaim waits for final DB expiry. All dedicated transaction failure branches defer cleanup, including business errors, avoiding inline network compensation.
- Task 5: Ruling: cycle business errors retain immediate cleanup after confirmed pre-COMMIT unwind, but only via the new bounded async cleanup — preserves F13 business contract without synchronous compensation — cost is an additional bounded attempt before returning failed. This narrows Task 4 blanket business-error deferral.
- Task 5: Ruling: pull F13 dedicated-factory adaptation forward from Task 6 — Task 5 requires real F13 green before commit, and 11 observed failures are missing-factory fixtures — no product fallback, all business assertions retained.
- Task 6: Ruling: backend and integration contain same pytest module basenames — execute their suites in separate processes as existing full/integration gates do — combined single-process selections would fail collection, not product behavior.
- Task 7 preflight: Ruling: install locked test dependencies while Task 6 network verification runs — independent ignored runtime artifacts, no shared product edits — source or lockfile changes remain forbidden.
- Final: Ruling: DNS resolver executor join is outside fence deadline guarantee — the documented pre-fence DNS boundary remains, cancellation does not bound stalled system resolver shutdown — cost if wrong: hostname outages can delay worker return/shutdown even though no SQLite fence is held; operational hostname/process-shutdown hard bounds remain OPEN/out of this repair.
- Final: Ruling: non-worker graph entry points and general process shutdown remain unchanged — approved bounded worker persist/cleanup scope — cost if wrong: those entry points retain existing unbounded driver behavior.
- Final: Ruling: process suspension/unhealthy local SQLite/storage are not hard realtime guarantees — thresholds concern live local execution — cost if wrong: host/storage stalls exceed measured margin.
- Final: Ruling: one reviewer dispatched before final runtime gates completed — all product code and drafted Task 6 tests reviewed read-only; final fix pass and actual gates are verification, not another review — cost if wrong: subsequent harness/document changes have no independent review.
- Task 6: Ruling: strengthen late experiment to exercise both takeover and failed cleanup after independently observed physical late commits — closes single-experiment recovery evidence gap without product changes — cost if wrong: one additional 5-repeat container-pause experiment increases runtime and host-sensitive coverage.
- Ruling: retract previous claim that the old whole backend gate loaded final fixes — traceback exercised the old startup branch and same-sequence bug; elapsed-time inference was insufficient — cost of the earlier mistake: invalid final-gate attribution. Final gate will start after all source edits and must exit 0 as one command.
- Ruling: expand Task 6 fixture adaptation to demo/K09 — final whole integration identified additional worker consumers missing the dedicated dependency — cost if wrong: extra test fixture edits, not a product sync fallback or assertion change.
- Ruling: treat actual TCP FIN and RST as physical client disconnect, keep their timestamps distinct — unread NOOP bytes can cause reset and the old EOF-only observer missed it — cost if wrong: misclassified evidence; the real SO_LINGER regression proves RST and no proxy-local close is counted.

本次截止最终审查未报告 Minor；先前核心 R1 审查暂缓的两个心跳调用者故障测试仍属先前范围，不因本轮修复自动完成。

## 当前新网络证明

- 产品 SHA256（六个关键产品文件拼接）`cfabf52f722b` 前缀；记录带完整 SHA256 与测试 SHA256，每个 fixture run_id 独立分组。
- 默认 2s：30 个围栏记录，最大围栏 2.010052s、独立写者等待 2.098800s；上限 3s：5 次，最大围栏 3.003443s、写等待 3.009332s。均满足 3s/4s 原阈值。
- 共享退出预算 1s：5 次，最大整次退出实验 1.042527s；5s：5 次，最大 5.041602s；额外 0.1s 压缩实验 5 次，最大 0.145754s。未逐层重置或放宽阈值。
- 物理迟到结局：takeover 3/5、failed_cleanup 5/5 次实际提交发生在客户端取消后；两路均收敛。另有真实旧事务图守卫阻塞清理案例，不混称为物理取消实验。
- 当前产品副本变异去掉 deadline/cancel/cleanup guard 均 RED（分别 10.35/0.37/4.82s）；从不修改正常产品包。

## Task 6 结束与整次门禁重跑

`task-done` 已执行原命名选择（顺序两个自有实例，34+65 共 99 passed、零 skip），日志 `task-6-tests.log`；提交范围 `21d01d0..b7e84a1`。

第二轮整次日志为 `repair-full-isolated.log`（历史失败；最新整次通过见下节），原运行（新选择五个互异回环端口，使用现有环境覆盖，不操作默认端口占用者）。前一 `repair-full-integration.log` 的实际整次 exit 1 保留：backend 4003 passed/27 登记 skip，frontend 934/type-check/build PASS，但图库绑定默认 17689 失败，E2E 尚未执行；这不是整次通过。源码 manifest 验证自当前最终整次启动后 15 个代码/测试文件内容未变。


## 最终验收结论与项目状态（2026-10-08）

- 最终受测代码 `f9c54553`，PR 包含从 `bdb89c46` 起的核心 R1 与截止补充完整提交链；产品审查修复 `2ea6319`、网络测试/夹具 `b89844b`、解释器 `b7e84a1`、同名路径身份 `f9c5455`。文档收尾不改产品/测试/脚本源码；16 文件 manifest 已逐文件匹配。
- 最终 `./scripts/verify.sh integration` 整次 **exit 0**：backend+tooling **4003 passed / 27 既有登记 skip**；frontend **934 passed**（38 文件）+type-check/build；integration **462 passed / 4 既有登记 skip**；backend-live **44 passed**；演示 E2E **2 passed**；个人本机假供应商 E2E **4 passed**。无失败/错误或新 skip，原阈值、业务断言、锁文件未放宽/升级。
- 先前第二轮个人模式失败并非解释器仍未修复：路径首项从 `kp_63b0…` 正确更新为同名 `kp_80b7…`，原 E2E 错误要求文字必须不同。只读 trace 与推荐/掌握 200 证明身份转换；断言改为文字+真实解锁目标 ID 变化、取消掌握后完整恢复，并保留推荐身份、刷新、学生隔离。该修复独立 4 项 E2E GREEN，最终整次 4 项再 GREEN，无产品推荐行为变化。
- 最终真实网络 run `7de6155b7906…`：默认 30 个围栏测量，最大围栏 **2.001980s**、独立写者 **2.115376s**；3s 上限 5 次，最大围栏 **3.001610s**、写者 **3.029492s**。共享退出 1/5s 各 5 次，最大 **1.046460/5.151670s**；0.1s 压缩 5 次最大 0.456033s。均在原配置+1s / 围栏3或4s阈值内。
- 两路物理迟到实验各 5 次，takeover **4/5**、failed_cleanup **4/5** 观察实际取消后的服务端提交，均收敛；旧图事务持守卫实验单独通过。4 个当前源码自有 run 共 **292 行**计时；逐 run 最大值而非平均值导出，机器校验全部原阈值。
- **CLOSED 范围**：worker 网络 COMMIT 无界占用 SQLite 最终围栏。DNS 执行器退出、非 worker 图入口、一般进程停机、宿主暂停/磁盘异常不在硬实时保证内；既有四项中严重程度发现/教师锁残留窗口与两个心跳故障测试未改。本风险关闭不是全项目冻结或跨库原子性证明。
- 用户最新开 PR 授权已写入任务板/ADR-092；远程默认分支已查为 `main`，核对祖先基线后新建 `codex/` 分支，不复用已合入主线的前端 #321～#323 分支；保留外部受管工作区、全部历史失败与证据，不强推、合并或部署。

### 可追溯证据

导出目录：`/private/tmp/smartsketch-r1-deadline-evidence-20261008/`。4 份 `whole-*.xml` 是最终整次门禁临时报告删除前只读保存，另外 `attempt2-whole-*.xml` 保留前次失败中的阶段报告。

| 文件 | SHA256 |
| --- | --- |
| `repair-full-final.log` | `641372dc429aed479cccaff6305e22dd184ad624b23de0f8db32a182fa45261e` |
| `repair-source-manifest-final.json` | `ed85be4362337334f7515170739b8cbf6699a23b43bfa58600a89bf54da8a7ea` |
| `verification-summary.json` | `203ca6cd59ba1afe535ed3792a47950f2b4f6939830232f0054bab4a24be0f83` |
| `network-evidence.jsonl` | `f84d17478a5660dfd41e69989803c71eee9d48a8bb54367b27a4a9fa22d85075` |

JSON 只含测试 run_id、计时、状态和源码 SHA，不含认证包；完整哈希清单 `evidence-hashes.json`。本机临时证据不代表远程 CI 结果；PR 的远程 CI/审阅仍需独立确认。

### 补充执行裁决（接续上文顺序）

- Ruling: use per-run isolated port overrides rather than reclaim defaults — avoids disrupting concurrent user services — cost if wrong: host port allocation can still race, so whole gate must actually pass.
- Ruling: compare path text plus actual unlock link IDs rather than require visible text inequality — independently extracted PDF/MD nodes may share names and the observed trace proves correct identity transition — cost if wrong: an incomplete identity snapshot could miss a stale path; keep changed recommendation ID, mastered disappearance, refresh, student isolation and full snapshot restoration assertions.
- Ruling: Task 7 completion rechecks actual final whole exit, four complete XML reports and unchanged source manifest, then runs final basic/diff checks — the entire successful integration command already ran against final f9c54553 source; subsequent edits are documentation only — cost if wrong: incomplete manifest could omit an unintended source change; also reject non-document Git changes and preserve original gate logs.
- Ruling: preserve ignored plan audit scratch after exporting evidence — externally managed workspace is retained for authorized PR iteration and logs survive interruptions — cost if wrong: local ignored artifacts consume disk; no runtime service is kept and no source cleanup is hidden.

## PR 交付

- 状态：[PR #324](https://github.com/arvinhanye/SmartSketch/pull/324) OPEN/DRAFT，`codex/r1-persist-deadline` → `main`；已附加当前任务。最终 basic 已通过；Task 7 结束证据校验/basic 已再次 exit 0，ledger 已记录 complete（`2ea6319..7d266ae`）；命令 `bash /private/tmp/smartsketch-r1-task7-verify.sh` 检查整次 exit、四份 XML、16 源码哈希并执行 basic/diff-check。
- 不合并/部署/冻结，远程 CI 与代码审阅继续独立把关。


### 主线整合边界（开 PR 前确认）

最新 `origin/main=2e6acef7bfdaaf7f9d931f2a2c3f66cbf2edb083`，实际共同祖先 `bdb89c46f9a4a9f10930675848abdd1b7af6edaf`。预检只生成 Git 对象，不改变工作树/索引或执行合并；两份冲突为 `docs/decisions.md`、`docs/tasks.md`，记录 `pr-merge-preflight.txt`。主线已使用 ADR-091/092 表示图谱工作台/教师向量，本分支的 worker ADR 编号需在后续主线整合时重编号并同步旧引用，保留所有决定。

**PR 将为草稿**：展示完整已验证修复，不宣称当前主线合并结果已验证。限定风险 CLOSED 仅针对受测分支；主线整合冲突、编号协调和合并结果门禁未完成。没有自动合并授权。前述无 wire/模型/依赖变化指本修复相对共同祖先，不否认主线独立合入的模型/迁移/UI 改动。

- Ruling: create a draft PR without merging newly advanced main into the verified repair tree — user asked for a PR, not unverified integration of unrelated UI/model/migration changes; preflight shows shared status-document conflicts and ADR identifier collisions — cost if wrong: draft is not directly mergeable and requires explicit main integration, identifier coordination and fresh merge-result gates before merge.
- 自有资源检查：最终门禁自建 `smartsketch-verify-neo4j-27956`、`smartsketch-e2e-neo4j-35300`、`smartsketch-e2e-neo4j-41641` 已不存在；默认端口占用者未动，工作区和临时证据保留。

- GitHub 开 PR 后实测：head `7d266ae7`、base `2e6acef7`，OPEN、isDraft=true、mergeable=CONFLICTING；四项 CI 当时 IN_PROGRESS。后续仅本交接/任务/决策的 PR 链接和状态提交，不将旧 head 的 CI 当新 head 成功。当前本地证据证明受测代码，不证明主线合并结果。
