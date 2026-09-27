# K04 全链路阶段性能测量 —— Claude 接手交接

- 基线：`main@9c66dcf` + 合并 kongsc 的 `codex/k04-benchmark-pipeline@4ad2574`（PR #296，保留原提交）。
- 接手时的缺口：问答部分写于 J07 合入前，只能用 JSON 测完整响应、无首字时间（目标 3 s 无法对照）；报告缺问答模型；测试只有 1 例（假模型能抽出实体）。

## 交付

- `evaluation/benchmark_pipeline.py`：问答改为 SSE（`sse_events` 解析器；首字 = 首个 `delta` 到达，完成 = `done`/`error` 到达；记录结局、错误码、`request_id`、按 `request_id` 的 token）；报告新增 `chat_model`、`qa_first_token_ms`（p50/p95）、`qa_outcomes`，注记说明口径与数据库前提。worker 测量部分沿用 kongsc 的实现（已核对 `persist_graph` 阶段函数签名、枚举值与表结构）。
- `tests/backend/test_k04.py`：新增 12 例——固定输入稳定且约 2 万字、百分位插值与空值、队列/token SQL 在真实迁移表结构上可执行、报告字段（机器/模型/并发/样本数/p50/p95、目标与实测分列、假模型注记、incomplete）、本地 HTTP 服务上的 SSE 计时/错误/无终态、付费与未准备运行在做任何工作前退出。
- `evaluation/README.md` §9 使用说明。

## 验证（本机实测）

- `PYTHONPATH=$PWD/src/backend .venv/bin/python -m pytest tests/backend/test_k04.py -q` → 13 passed。
- 反向篡改 8 处：首字被后续 delta 覆盖、去 live 付费守卫、百分位位置、Accept 改 JSON、去并发字段、去问答付费守卫、丢错误码 → 均判红；去 `:ping` 跳过分支 → 存活，为等价变异（该行本就不匹配 `event:`/`data:`）。
- 后端全量与 `verify.sh` 同 `docs/handoffs/claude-j10.md`。

## 未做 / 风险

- **未在真实服务上跑过**：需要 Neo4j、存储、已上传的 fixture 与已发布课程；live 模型与问答样本会产生费用，须按 D-02 另行确认后再跑，报告落到 `evaluation/reports/`。
- worker 测量通过 `unittest.mock.patch` 包装 `persist_graph` 的阶段函数；若 F13 改为别的调用方式，测量会静默缺阶段（`complete=false` 会暴露）。
- 首字时间包含网络与 SSE 缓冲；服务端口径可对照 J10 `chat_logs.first_delta_latency_ms`。
