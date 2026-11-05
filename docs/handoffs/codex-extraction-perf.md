# EXTRACT-PERF-01：图谱生成性能

- 日期：2026-11-05；负责人：Codex；状态：生成代码已交付，P1-3后续范围待确认，P1-5用户已决定延期。
- 分支：`codex/extraction-perf`；worktree：`/Users/arvinhan/.codex/worktrees/extraction-perf/SmartSketch-main`。
- 基线：`ad63341`。OPT-05 仍未提交，按 Claude 交接 §1 独立工作，未修改发布向量化文件，未带走源工作区任何 OPT-05/OPT-02 改动。
- 无付费模型调用、依赖变化、迁移、提示词/API/SSE/状态机变更；只本地提交，不推送、不开 PR、不合并。

## 已交付与决定

1. `evaluation/measure_extraction_perf.py`：真实 API（TestClient）、真实 worker、隔离 SQLite/Neo4j、原 `scripts/fake_provider.py` 的 loopback HTTP；每次调用固定 8 秒。记录单元/模型调用时间、阶段交接、persist steps 与逐查询完整消费耗时；同图库的新课程可冷暖对照。默认不发布。
2. 用户确认保守去屏障：实体队列优先；只有剩余块全失败仍不超阈值时才让已就绪小节填空。共用一个池；所有成员结束后过滤成功块，保留原文档顺序、ID 和模型输入。检查点成功提交后才满足依赖；早完成关系不使进度跳过块区间。
3. 新增 13 项确定性交错测试，覆盖取消、早停、接管、失租、凭据撤销、401、429、熔断、调用记账和失败/跨节同名输入。旧实现 9 项预期红、4 项保护绿；当前与原 E12 合计 57 passed。新增凭据用例曾存在测试自身的启动顺序竞态，改为事件控制撤销发生点，原错误原因/调用数/检查点断言全部保留；修正用例在旧实现再次预期失败。
4. 用户已批准并已落地默认 `LLM_MAX_CONCURRENCY=8`，保留环境变量覆盖；配置独立于调度提交。实际请求池测试在旧默认下1红/覆盖2绿；改后与调度/E12共59 PASS。同步配置、worker缺省值、示例、集成说明和ADR；完整门禁结果见下方。
5. 用户已确认本轮先交付生成提速；发布向量化登记后续待办，等OPT-05提交后接续，不在旧基线上混改发布文件。

## 实测证据与边界

详表：[性能报告](../../evaluation/reports/extraction-perf-2026-11.md)，原始脱敏证据在 `evaluation/raw/extraction-perf/`。
材料为自编 `ch3-stack-queue.md`；16 块、16 小节、31 次 HTTP（16 实体＋15 关系）、0 repair。
所有已完成对照均为 64 知识点、71 业务关系，归一化图 SHA-256 相同：
`10e6daa4a44c8c92db353b50390d5c4e48c43bf9733f818890f01e8845e37ce2`。

| 秒 | 优化前，并发4暖轮 | 保守调度，并发4暖轮 | 默认8冷轮 | 默认8暖轮 |
| --- | ---: | ---: | ---: | ---: |
| extracting | 65.450 | 64.752 | 33.167 | 32.952 |
| merging | 0.010 | 0.005 | 0.007 | 0.011 |
| persisting | 8.599 | 5.567 | 17.092 | 6.130 |
| 上传至待审核 | 76.157 | 72.491 | 52.388 | 41.172 |

- 配置落地后从应用缺省值读取8，两轮为52.388/41.172秒；此前显式8实验冷/暖轮58.901/44.871秒也完整保留。并发4→8同调度暖轮抽取减少31.800秒（49.1%）。只证明固定延迟假供应商下的结构性结果，不证明真实模型≤60秒或准确率。
- 去屏障在均匀8秒样例中只观察到约0.70秒抽取差值、约0.16秒调用交叠；不把图库波动算成调度收益。慢尾块重叠由事件测试证明，未用理论值冒充实测秒数。
- 冷轮变化大：原首轮96.238秒；恢复后的冷轮162.804秒，因图库尝试超时释放后退避约30秒并接管续跑，不能选掉这一轮。细分记录保留两次persist尝试。
- 阶段连续推进，同一租约，无每阶段2秒轮询。约2秒是刻意从空闲轮询后开始上传的初次排队。
- 图库15条Cypher已批量写入，主要时间在查询请求与完整结果消费，非SQLite锁/纯Python；冷暖缓存及同机其他Docker/测试负载影响明显。补充PROFILE诊断（零延迟假模型、独立证据，不混入8秒表）显示写入命中唯一索引、最大中间行数182，服务端首结果等待冷12.559/暖5.350秒。不能仅凭此认定纯查询编译，也未证明安全且有实际收益的图库修法；P1-3仅定位，未声称修复。不调大截止/租约掩盖超时。
- 发布：OPT-05未提交，用户明确允许本轮交付生成提速、发布后续做；当前未测未改，历史L02为21.17秒，不混入生成。
- JSON模式已开启；假模型0 repair；历史首因记录不足，不放宽解析/证据校验来“减少修复”。P2仅离线调用数对比，不改默认分块、思考或提示词。

## 验证与复核

- `PYTHONPATH=src/backend .venv/bin/python -m pytest tests/backend/test_extraction_perf_scheduler.py tests/backend/test_e12.py -q -p no:cacheprovider`：57 passed。
- `PYTHONPATH=src/backend .venv/bin/python -m pytest tests/tooling/test_extraction_perf.py tests/tooling/test_l11_fake_provider.py -q -p no:cacheprovider`：25 passed。
- 独立只读复核：指定调度/测试/规格/决定四文件未发现阻塞问题；独立13项通过，旧实现内存对照的overlap用例预期失败。
- `./scripts/verify.sh`：basic已通过。首次环境未把`.venv/bin`放入PATH导致pytest缺失；修正PATH后重跑通过，未安装依赖。
- `scripts/verify/backend.sh full`：4270 passed、27 个登记 skipped、gate PASS（1400.59 秒）。中断前未完成的门禁不作为通过证据。
- 默认8改动后：`scripts/verify/backend.sh full` 4272 passed、27登记skipped、gate PASS（1184.07秒）；`./scripts/verify.sh` 再次PASS；定向59 PASS（117.48秒）。
- 最终文档更新后再次运行 `./scripts/verify.sh`，contracts gate/scaffold均PASS；日志 `final-docs-basic.log`。所有本轮临时图库均已清理。
- `git diff --check`、契约及提示词无差异检查通过。未修改Neo4j写入生产逻辑；图库实测使用真实隔离Neo4j，不冒充完整integration门禁。
- 稳定日志：`.demo/extraction-perf/logs/`（Git忽略）。中断后的旧`/private/tmp`目录已不可用，只有已复制原始证据仍可复核。

## 提交、待办与恢复

- `570155b`：认领与原交接/prompt，未夹带OPT-05。
- `7c886ca`：测量工具、工具测试、初始报告和基线证据。
- `507f609`：保守共享池调度、回归、规格、冷暖测量证据。
- `efb866c`：默认8、环境覆盖回归、配置/ADR/规格及落地后冷暖证据。
- 后续：按用户决定，OPT-05完成并提交后确定接续基线，再实施发布向量化；真实复测需另行确认供应商与预算；P2方案需质量对照和用户决定。
- P1-3尚未修复：已向用户说明PROFILE定位结果，并询问转后续图库专项或继续深挖，等待选择。不要把本次假模型数据写成真实准确率签收或技术冻结；既有B-QUALITY-01/B-EVAL-01真实验收状态不变。
- 回滚：分别撤销调度或默认值提交即可；数据结构/检查点格式未变，无数据迁移回滚。显式设置`LLM_MAX_CONCURRENCY=4`可恢复原配置并发上限。
