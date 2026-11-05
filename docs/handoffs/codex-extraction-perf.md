# EXTRACT-PERF-01：图谱生成性能

- 日期：2026-11-05；负责人：Codex；状态：IN_PROGRESS。
- 分支：`codex/extraction-perf`；worktree：`/Users/arvinhan/.codex/worktrees/extraction-perf/SmartSketch-main`。
- 基线：`ad63341`。OPT-05 仍未提交，按 Claude 交接 §1 独立工作，未修改发布向量化文件，未带走源工作区任何 OPT-05/OPT-02 改动。
- 无付费模型调用、依赖变化、迁移、提示词/API/SSE/状态机变更；只本地提交，不推送、不开 PR、不合并。

## 已交付与决定

1. `evaluation/measure_extraction_perf.py`：真实 API（TestClient）、真实 worker、隔离 SQLite/Neo4j、原 `scripts/fake_provider.py` 的 loopback HTTP；每次调用固定 8 秒。记录单元/模型调用时间、阶段交接、persist steps 与逐查询完整消费耗时；同图库的新课程可冷暖对照。默认不发布。
2. 用户确认保守去屏障：实体队列优先；只有剩余块全失败仍不超阈值时才让已就绪小节填空。共用一个池；所有成员结束后过滤成功块，保留原文档顺序、ID 和模型输入。检查点成功提交后才满足依赖；早完成关系不使进度跳过块区间。
3. 新增 13 项确定性交错测试，覆盖取消、早停、接管、失租、凭据撤销、401、429、熔断、调用记账和失败/跨节同名输入。旧实现 9 项预期红、4 项保护绿；当前与原 E12 合计 57 passed。新增凭据用例曾存在测试自身的启动顺序竞态，改为事件控制撤销发生点，原错误原因/调用数/检查点断言全部保留；修正用例在旧实现再次预期失败。
4. 用户已批准将默认 `LLM_MAX_CONCURRENCY` 改为 8，保留环境变量覆盖；配置独立于调度提交，当前等待调度门禁完成后落地。

## 实测证据与边界

详表：[性能报告](../../evaluation/reports/extraction-perf-2026-11.md)，原始脱敏证据在 `evaluation/raw/extraction-perf/`。
材料为自编 `ch3-stack-queue.md`；16 块、16 小节、31 次 HTTP（16 实体＋15 关系）、0 repair。
所有已完成对照均为 64 知识点、71 业务关系，归一化图 SHA-256 相同：
`10e6daa4a44c8c92db353b50390d5c4e48c43bf9733f818890f01e8845e37ce2`。

| 秒 | 优化前，并发4暖轮 | 保守调度，并发4暖轮 | 保守调度，并发8实验暖轮 |
| --- | ---: | ---: | ---: |
| extracting | 65.450 | 64.752 | 33.429 |
| merging | 0.010 | 0.005 | 0.008 |
| persisting | 8.599 | 5.567 | 9.303 |
| 上传至待审核 | 76.157 | 72.491 | 44.871 |

- 并发8实验冷轮 58.901秒，抽取33.324秒、持久化23.393秒。只证明固定延迟假供应商下的结构性结果，不证明真实模型≤60秒或准确率。
- 去屏障在均匀8秒样例中只观察到约0.70秒抽取差值、约0.16秒调用交叠；不把图库波动算成调度收益。慢尾块重叠由事件测试证明，未用理论值冒充实测秒数。
- 冷轮变化大：原首轮96.238秒；恢复后的冷轮162.804秒，因图库尝试超时释放后退避约30秒并接管续跑，不能选掉这一轮。细分记录保留两次persist尝试。
- 阶段连续推进，同一租约，无每阶段2秒轮询。约2秒是刻意从空闲轮询后开始上传的初次排队。
- 图库15条Cypher已批量写入，主要时间在查询请求与完整结果消费，非SQLite锁/纯Python；冷暖缓存及同机其他Docker/测试负载影响明显。尚未证明一个可安全改变结果不变的图库修法，不调大截止/租约掩盖超时。
- 发布：OPT-05未提交，本轮暂缓向量化改动及当前发布计时；历史L02为21.17秒，不混入生成。
- JSON模式已开启；假模型0 repair；历史首因记录不足，不放宽解析/证据校验来“减少修复”。P2仅离线调用数对比，不改默认分块、思考或提示词。

## 验证与复核

- `PYTHONPATH=src/backend .venv/bin/python -m pytest tests/backend/test_extraction_perf_scheduler.py tests/backend/test_e12.py -q -p no:cacheprovider`：57 passed。
- `PYTHONPATH=src/backend .venv/bin/python -m pytest tests/tooling/test_extraction_perf.py tests/tooling/test_l11_fake_provider.py -q -p no:cacheprovider`：25 passed。
- 独立只读复核：指定调度/测试/规格/决定四文件未发现阻塞问题；独立13项通过，旧实现内存对照的overlap用例预期失败。
- `./scripts/verify.sh`：basic已通过。首次环境未把`.venv/bin`放入PATH导致pytest缺失；修正PATH后重跑通过，未安装依赖。
- `scripts/verify/backend.sh full`：4270 passed、27 个登记 skipped、gate PASS（1400.59 秒）。中断前未完成的门禁不作为通过证据。
- `git diff --check`、契约及提示词无差异检查通过。未修改Neo4j写入生产逻辑；图库实测使用真实隔离Neo4j，不冒充完整integration门禁。
- 稳定日志：`.demo/extraction-perf/logs/`（Git忽略）。中断后的旧`/private/tmp`目录已不可用，只有已复制原始证据仍可复核。

## 提交、待办与恢复

- `570155b`：认领与原交接/prompt，未夹带OPT-05。
- `7c886ca`：测量工具、工具测试、初始报告和基线证据。
- 调度、并发默认值提交待各自门禁通过后补入。
- 待用户/上游：OPT-05完成并提交后确定接续基线，再实施发布向量化；真实复测需另行确认供应商与预算；P2方案需质量对照和用户决定。
- 下一步：先读本文件最新门禁记录；完成默认8配置独立提交，补最终测量/验证。不要把本次假模型数据写成真实准确率签收或技术冻结。
- 回滚：分别撤销调度或默认值提交即可；数据结构/检查点格式未变，无数据迁移回滚。显式设置`LLM_MAX_CONCURRENCY=4`可恢复原配置并发上限。
