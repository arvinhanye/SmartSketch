# Claude 复核：计划 A 审查修复（D1–D3、N01–N08、§3.7）与计划 B 规划提交

- 日期：2026-10-03；复核者：Claude（冲刺工作树会话）；对象：`e86f4b9..34372c7`，共 11 个提交。代码提交 8 个（`0745ea6` `cc26d4c` `8e539a8` `a787b0b` `45dd86e` `f580b74` `29a10f6` `959331e`），文档提交 3 个（`dcb9cba` `d766f40` `34372c7`）。
- 来源：另一个 Claude 会话在工作树 `smartsketch-plan-a-fixes-e70a34` 完成，依据 Codex 审查 `/Users/arvinhan/.codex/worktrees/e92f/SmartSketch/docs/reviews/codex-claude-plan-a-2026-10-03.md`（未合并到本仓库），交接 `docs/handoffs/claude-plan-a-review-fixes-2026-10-03.md`。
- 结论：**通过，可推送**。没有发现阻断问题；一项低风险的可选改进见第 3 节。门禁结果见第 4 节。

## 1. 逐项审查

| 项 | 改动要点 | 审查结论 |
| --- | --- | --- |
| D3 出站总预算 | `compatible.exchange`：一次请求一个绝对截止时刻，覆盖解析、连接、TLS、发送、等待响应头与后续读取；看门狗到期关闭套接字；解析放在守护线程里限时等待 | 正确。原来每个地址各自 60 秒、5 个地址可累加到约 5 分钟的问题已消除 |
| 出站安全（L05 不退化） | `GuardedTransport` 先校验全部解析地址为公网，再只连接这些地址；连接后不重新解析；TLS 用原域名做 SNI 与证书校验，套接字交给 `http.client` 后不会重连 | 未放松：钉 IP、公网校验、TLS 校验、不跟随重定向均保持 |
| D3 问答链路 | 同一截止时刻贯穿改写、查询向量（`EmbeddingRequest.timeout_seconds`）、图检索（`read_deadline` 把剩余时间作为 Neo4j 事务超时）与上下文构建；每步前检查，到期即 `LLM_UNAVAILABLE`/`timeout` | 正确 |
| D1 截断分类 | 仅当 `finish_reason = length` 且出处校验不通过时抛 `TruncatedAnswer`，终态改为 `LLM_UNAVAILABLE`/`truncated`；正常结束且无依据的仍为 `not_covered`；契约、错误码说明、前端文案同步 | 正确，「资料未覆盖」与「生成故障」分开了。输出上限仍为 1024，见交接风险 1 |
| N01/N06 配置身份 | 迁移 016 增加可空 `revision` 并随机回填；每次保存生成新的 128 位随机值；问答缓存与测试结果落库都按 `revision` 比对 | 正确；迁移文件头有回滚语句 |
| N02 鉴权终止 | 实体/关系调用收到 401/403 不重试，阶段停止派发，之后完成的单元不写检查点，任务以 `LLM_UNAVAILABLE`/`auth` 终止；前端按原因提示 | 正确；`live` 模式同样适用（交接已注明） |
| N07/N08 | `/test` 各分支先确认凭据存储已启用；模型名统一去空白，空白或超长返回 422 | 正确 |
| D2 向量记账 | 发布与问答共用 `build_embedding_adapter`，仅 `online` 模式写 `model_calls`（`purpose = embedding`，不计入生成模型预算）；记账版适配器要求调用方声明归属 | 正确。已核对全部调用路径：发布在 `publish:<version_id>` 下、问答在请求 ID 下；回滚不重新向量化；离线脚本不用记账版 |
| N03–N05、§3.7 | 运行状态按登录会话与代际归属；设置页保存/测试/清除互斥并标明测试对象；问答发送期间锁住按钮、回车与重试 | 正确 |
| 文档 | ADR-082（决定 1–6）、`specs/grounded-qa.md` 修订、任务板两节、计划 B 规划（标明用户确认前不实施） | 与代码一致 |

每项都有先红后绿的仓库回归：后端 `test_d1`（11）、`test_d2`（10）、`test_d3`（12）、`test_n01_n06`（10）、`test_n07_n08`（7）及 `test_e12` 的 N02 段；前端 `n03-n05`（13）、`d1-d3`（3）、`chat-send-lock`（4）；集成 `test_d2_publish.py`。

## 2. 既有测试的断言变更

`test_j06.py`（截断尾句的新行为）、`test_j10.py`（最新迁移改为 016）、`test_l04.py`（`record_test` 新签名）、`tests/frontend/h02.test.ts`（凭据原因提示）。均为有意的行为变化，没有删除用例或放宽断言。

## 3. 可选改进（不阻断）

- `stores/runtime.ts` 用登录令牌本身作为会话标识 `owner`。它只在内存里、不持久化，而令牌本来就在 `sessionStorage`，所以不构成新的泄漏；若要更稳妥，可改用用户 ID 与登录时间组合。

## 4. 门禁（本工作树独立复跑，HEAD `34372c7`）

```bash
PYTHON=.venv/bin/python PATH="$PWD/.venv/bin:$PATH" \
PLAYWRIGHT_CHROMIUM_EXECUTABLE="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" \
  ./scripts/verify.sh integration     # → exit 0，一次跑完，未补跑
```

| 档位 | 结果 |
| --- | --- |
| 基础档与契约门禁 | PASS（OpenAPI 3.1.0，32 条路径 / 129 个 schema / 385 处 `$ref`，生成物与真源一致） |
| 后端全量 | 3725 passed、27 skipped |
| 前端全量 | 29 个文件 811 用例通过；类型检查与构建通过 |
| 集成（一次性 Neo4j） | 393 passed、4 skipped |
| 图库后端用例 | 44 passed |
| 端到端（教师、学生两条主线，演示模型） | 2 passed；运行目录 `.e2e/20261003-080426` |

日志 `.demo/logs/verify-integration-review10.log`（Git 忽略）。全程没有真实模型调用。
