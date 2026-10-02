# L02 网页链路真实基线（2026-10-02）

> **状态：抽取已实测；问答未测。** 问答与发布依赖在线向量服务，本机网络当前连不上北京地域的向量接口（见第 4 节），等该问题解决后补测并在本文件追加。本报告只有一次运行，不是多次取优。

## 1. 测试条件

| 项 | 取值 |
| --- | --- |
| 日期 | 2026-10-02（America/New_York），任务创建于 08:20:42Z |
| 代码 | `52aa4db`（业务代码与 `6ff8a8d` 相同） |
| 机器 | Intel Core i7-9750H（12 逻辑核）、16 GB 内存、macOS 26.6.2 |
| 网络 | 本机当前网络直连 `api.deepseek.com`（未经代理配置） |
| 启动方式 | `scripts/start-demo.sh --live --no-open`：API、worker、前端各一个进程；独立 SQLite 与 Neo4j（7688） |
| 大模型 | 请求 `deepseek-flash`，响应 `deepseek-flash`；`LLM_MODE=live`，无备用供应商 |
| 并发与重试 | `LLM_MAX_CONCURRENCY=4`、`LLM_MAX_RETRIES=2`、`TASK_CHUNK_MAX_ATTEMPTS=2` |
| 提示词 | `extract_entities` v2、`extract_relations` v2；未开补漏（E06），融合直通 |
| 资料 | `datasets/demo/ch3-stack-queue.md`（自编「数据结构 第 3 章 栈与队列」），Markdown，11779 字节、111 行、16 个文本块共 5819 字符 |
| 测量工具 | `evaluation/measure_web_flow.py extract`，经 HTTP 接口上传并每 0.5 秒轮询任务快照 |
| 首次处理 | 是。新建课程、新库，没有抽取缓存可命中 |

计时边界：发出上传请求 → 任务快照 `stage = awaiting_review`。含排队、解析、分块、抽取、直通融合与入库。

## 2. 抽取结果

**总耗时 141.72 秒，目标 ≤60 秒，未达标（超出约 82 秒）。**

| 阶段 | 起止（UTC） | 耗时 | 依据 |
| --- | --- | --- | --- |
| 排队、解析、分块 | 08:20:42.3 → 08:20:43.7 | 约 1.4 秒 | 任务 `created_at` 到第一条 `model_calls` |
| 抽取（实体 + 关系 + 修复） | 08:20:43.7 → 08:22:18.1 | 约 94.4 秒 | `model_calls` 首条创建到末条完成 |
| 直通融合与入库 | 08:22:18.1 → 08:23:03.8 | 约 45.7 秒 | 末条模型调用完成到任务 `updated_at` |

模型调用（`model_calls`，全部 `ok`）：

| 用途 | 次数 | 输入 token | 输出 token | 单次延迟 最小 / 平均 / 最大 |
| --- | --- | --- | --- | --- |
| `extract_entities` | 16 | 10293 | 29479 | 3.1 / 8.5 / 17.2 秒 |
| `extract_relations` | 15 | 16140 | 34545 | 4.7 / 10.5 / 20.3 秒 |
| `repair`（输出不合规后的修复） | 3 | 2454 | 8143 | 11.7 / 12.2 / 12.8 秒 |
| 合计 | 34 | 28887 | 72167 | — |

检查点：16 个块全部 `done`，16 个小节全部 `done`，没有失败块。

草稿图谱（教师接口 `GET /courses/{cid}/graph`，原始 AI 输出，未经人工修改）：

- 知识点 82 个：`concept` 36、`method` 15、`example` 13、`theorem` 12、`formula` 6。
- 关系 73 条、4 种类型：`CONTAINS` 40、`RELATED_TO` 20、`EXAMPLE_OF` 11、`PREREQUISITE` 2。

数量指标（≥20 个知识点、≥3 种关系）在这次运行中满足。**准确率本次没有人工判定**，不能据此声称 ≥70%；历史报告 `extraction-accuracy.md` 是另一条评测链路上的结果。

## 3. 对 60 秒目标的含义

1. 抽取阶段 94 秒里，34 次调用的延迟总和约 330 秒，并发 4 时的理论下限约 83 秒，与实测接近。提高并发是最直接的手段：两个阶段各自最慢的一次调用是 17 秒与 20 秒，加上 3 次约 12 秒的修复，并发足够时抽取阶段的下限在 40 至 50 秒。
2. **入库阶段 45.7 秒是之前没有记录过的开销**，与模型无关。82 个知识点和 73 条关系写入 Neo4j 用了这么久，值得在 L16 先看写入是否逐条往返。它不解决，仅靠提高并发到不了 60 秒。
3. 与 2026-09-26 的历史记录（约 329 秒，另一条脚本链路）相比，这次单次调用平均延迟从约 37 秒降到 9 至 10 秒。供应商响应速度在变，同一配置隔天重测可能有明显出入。
4. `PREREQUISITE` 只有 2 条。学习路径推荐依赖前置关系，这个数量对路径可视化偏少，L14 与 L16 需要关注。

## 4. 问答：未测及原因

- 发布与问答都要调用向量服务。配置的地址是北京地域 `https://dashscope.aliyuncs.com/compatible-mode/v1`。
- 本机到 `dashscope.aliyuncs.com:443` 的 TCP 连接超时（`nc -z -G 8` 与 `curl` 结果一致）；同一时刻 `api.deepseek.com`、`www.aliyun.com`、国际站 `dashscope-intl.aliyuncs.com` 均可达。
- 用现有 key 请求国际站地址返回鉴权失败，说明该 key 属于北京地域，不能直接换地址。
- 三次向量请求都没有成功返回，不产生计费。

## 5. 用量

- 本次计费 token：101054（输入 28887 + 输出 72167）。
- 冲刺累计计费 token：101054，上限 500 万。

## 6. 复现

```bash
scripts/start-demo.sh --live --no-open          # 需要 .env 的 LLM_API_KEY
MEASURE_PASSWORD=<演示口令> .venv/bin/python evaluation/measure_web_flow.py extract \
  --base-url http://127.0.0.1:8001 --username demo_teacher --password-env MEASURE_PASSWORD \
  --course-name "L02 基线" --file datasets/demo/ch3-stack-queue.md
sqlite3 src/backend/storage/smartsketch.sqlite3 \
  "SELECT purpose, count(*), sum(usage_input), sum(usage_output), max(latency_ms) FROM model_calls WHERE task_id='<TASK_ID>' GROUP BY purpose;"
```

本次的课程 `2ace598581f349ec9943dea90bc7fdf1`、任务 `205f9311572846b8bc192ff1f67e244f` 保留在冲刺工作区的本地库里，供后续发布与问答补测使用。
