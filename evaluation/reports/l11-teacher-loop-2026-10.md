# L11-6 真实模型教师流程测量（2026-10-03）

> **状态：四次抽取与两次发布全部实测完成（4/4 + 2/2）。** 真实模型 DeepSeek `deepseek-flash`（教师个人配置，ADR-080）+ 阿里云百炼 `text-embedding-v4` 在线向量（部署者配置，ADR-081）。**累计计费 token 越过交接约定的 60 万止损线，已由用户明确授权继续**（见第 6 节）。原始 AI 输出（未做任何人工编辑）已导出到 `evaluation/raw/l11/`，供 L16 人工判定准确率。

## 1. 测试条件

| 项 | 取值 |
| --- | --- |
| 日期 | 2026-10-03（America/New_York），抽取窗口 14:12:40Z – 14:25:21Z |
| 代码 | `fc2ad94`（计划 A 审查修复版本，含 ADR-082/ADR-083） |
| 机器 | Intel Core i7-9750H（12 逻辑核）、16 GB 内存、macOS 26.6.2（与旧基线同机） |
| 网络 | 本机直连 `api.deepseek.com` 与 `dashscope.aliyuncs.com`，两者本次均可达 |
| 启动方式 | `scripts/start.sh --no-open`（`LLM_MODE=personal`，`runtime_mode=personal` 已核对）；API 8001、前端 5174、Neo4j 7688 |
| 大模型 | 请求 `deepseek-flash`（教师个人配置，先在「模型 API 设置」测试连接 731 毫秒后保存） |
| 向量 | `EMBEDDING_MODE=online`、`text-embedding-v4`、1024 维、每批 10 条 |
| 并发与重试 | `LLM_MAX_CONCURRENCY=4`、`TASK_CHUNK_MAX_ATTEMPTS=2`、`LLM_CHAT_TIMEOUT_SECONDS=15` |
| 资料 | `datasets/contest/`（两门课各一章，Markdown 为源，PDF 由 Chrome 无头打印） |
| 课程组织 | **每份资料一门独立课程**（同章两种格式同课会产生大量同名知识点，见 L11 观察 R05） |
| 测量工具 | `evaluation/measure_web_flow.py extract`（经 HTTP 上传并轮询任务快照） |

计时边界：发出上传请求 → 任务快照 `stage = awaiting_review`。

资料规模：

| 资料 | 字节 | 字数/页数 | 块数 | 正文提取字符数 |
| --- | --- | --- | --- | --- |
| course1 数据结构 · Markdown | 11779 | 4773 字 | 16 | 5819 |
| course1 数据结构 · PDF | 391115 | 5 页 | 16 | 8130 |
| course2 操作系统 · Markdown | 8767 | 3187 字 | 16 | 3783 |
| course2 操作系统 · PDF | 368606 | 4 页 | 16 | 5579 |

## 2. 四次抽取结果

| 资料 | 总耗时 | 实体阶段 | 关系阶段 | 抽取阶段整体 | 非模型阶段 | 调用数 | repair | 输入 | 输出 | **计费** | 知识点 | 关系 | 关系种类 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| course1 · MD | **83.97 秒** | 25.10 秒 | 39.87 秒 | 71.58 秒 | 12.39 秒 | 33 | 2 | 28358 | 58616 | **86974** | 75 | 66 | 4 |
| course1 · PDF | **200.37 秒** | 89.70 秒 | 85.68 秒 | 197.40 秒 | 2.97 秒 | 49 | 13 | 49654 | 142534 | **192188** | 71 | 24 | 3 |
| course2 · MD | **75.51 秒** | 34.66 秒 | 33.47 秒 | 74.47 秒 | 1.04 秒 | 34 | 3 | 25481 | 52761 | **78242** | 71 | 55 | 4 |
| course2 · PDF | **162.54 秒** | 82.37 秒 | 62.05 秒 | 159.03 秒 | 3.51 秒 | 39 | 5 | 32506 | 89077 | **121583** | 74 | 25 | 3 |
| 合计 | — | — | — | — | — | 155 | 23 | 135999 | 342988 | **478987** | — | — | — |

「非模型阶段」= 总耗时 −（首条模型调用 `created_at` → 末条 `finished_at`），含排队、解析、分块、融合与入库。

- 四次任务全部 `stage = awaiting_review`、`progress = 0.95`、`error_code = null`，**没有失败块，也没有 `status != 'ok'` 的调用**。
- 关系明细：course1-MD `CONTAINS` 30 / `RELATED_TO` 27 / `EXAMPLE_OF` 7 / `PREREQUISITE` 2；course1-PDF `CONTAINS` 16 / `RELATED_TO` 3 / `EXAMPLE_OF` 5（无 `PREREQUISITE`）；course2-MD `CONTAINS` 28 / `RELATED_TO` 20 / `PREREQUISITE` 5 / `EXAMPLE_OF` 2；course2-PDF `RELATED_TO` 13 / `CONTAINS` 11 / `EXAMPLE_OF` 1（无 `PREREQUISITE`）。
- 知识点类型（course1-MD）`concept` 27 / `theorem` 16 / `method` 16 / `example` 11 / `formula` 5。
- 孤立节点数：course1-MD **3**、course1-PDF **37**、course2-MD 3、course2-PDF **39**（见第 5 节）。
- 原始草稿快照（`evaluation/raw/l11/`，未经任何人工编辑，供 L16 判定准确率）：

  | 文件 | 字节 | sha256（前 12 位） |
  | --- | --- | --- |
  | `course1-md-draft.json` | 60825 | `c454cb79d537` |
  | `course1-pdf-draft.json` | 38634 | `833113c521e1` |
  | `course2-md-draft.json` | 52879 | `5bfcaa70ea28` |
  | `course2-pdf-draft.json` | 38631 | `c1427455fa82` |

## 3. 赛题指标

| 指标 | 目标 | 实测 | 判定 |
| --- | --- | --- | --- |
| 知识点数 ≥ 20 | ≥ 20 | 75 / 71 / 71 / 74 | **达到**（四份全部） |
| 关系种类 ≥ 3 | ≥ 3 | 4 / 3 / 4 / 3 | **达到**（四份全部，PDF 两份恰为 3 种） |
| 抽取 ≤ 60 秒 | ≤ 60 秒 | 83.97 / 200.37 / 75.51 / 162.54 | **四份全部未达到**；MD 差 16～24 秒，PDF 差 103～140 秒 |
| 准确率 ≥ 70% | ≥ 70% | **未判定** | 不在本次范围；原始输出已导出，待 L16 人工判定 |

不缩小资料、不用缓存：四次都是新课程、新上传，首次处理。

## 4. 与旧基线的对比

| 项 | 旧基线（2026-10-02，`52aa4db`） | 本次 course1-MD | 差异条件 |
| --- | --- | --- | --- |
| 资料 | `datasets/demo/ch3-stack-queue.md`，5819 字符、16 块 | `datasets/contest/course1-ds-ch3/ch3-stack-queue.md`，5819 字符、16 块 | 块数与字符数相同，正文为参赛版重写 |
| 总耗时 | 141.72 秒 | 83.97 秒 | **快 57.75 秒**；同机、同模型、同并发 |
| 知识点 / 关系 | 82 / 73 | 75 / 66 | 略少（正文不同） |
| 计费 token | 101054 | 86974 | 少 14080 |
| 调用数 | 34（16 实体 + 15 关系 + 3 repair） | 33（16 + 15 + 2） | repair 少 1 次 |

结论：**耗时与费用都优于旧基线**，但 83.97 秒仍高于 60 秒目标。两点需要更正旧基线的判断：

1. **「入库阶段 45.7 秒」这一旧观察本次不再成立，且改善明显。** 非模型阶段（排队、解析、分块、融合、入库 = 总耗时减去模型调用跨度）本次为 course1-MD 12.39 秒、course1-PDF 2.97 秒、course2-MD 1.04 秒、course2-PDF 3.51 秒，而旧基线是约 45.7 秒。旧基线把它列为「与模型无关、值得在 L16 先看」的头号嫌疑，现在总耗时里几乎只剩模型调用时间——**四份资料的总耗时差异基本由模型调用决定**（实体 + 关系 + repair）。
2. `PREREQUISITE` 数量偏少仍然成立，且在 PDF 路径上更严重（见 5.2）。

## 5. 本次新发现（只记录，未修）

### 5.1 PDF 路径的成本与耗时约为 Markdown 的 2～2.4 倍，且大量触发 repair

| 对比对 | 总耗时 | 计费 token | repair 次数 |
| --- | --- | --- | --- |
| course1 MD → PDF | 83.97 → 200.37（**2.4 倍**） | 86974 → 192188（**2.2 倍**） | 2 → 13 |
| course2 MD → PDF | 75.51 → 162.54（**2.2 倍**） | 78242 → 121583（**1.6 倍**） | 3 → 5 |

- PDF 提取出的正文字符数更多（course1 8130 vs 5819），但**更大的成本来自 repair**：course1-PDF 的 `repair` 用了 13 次调用、14575 输入 + 49011 输出 token，接近该份资料总输出的三分之一。repair 是「模型输出不合规后的修复」，说明 PDF 侧喂给模型的文本（页眉页脚重复、换行破碎，见首块前 70 字里「第3章 栈与队列」重复出现）更容易让抽取输出不合规。
- 这直接解释了为什么本次预算会越线：交接按「一份约 10 万 token」估算，而 PDF 两份实际是 19.2 万与 12.2 万。

### 5.2 PDF 两份都抽取不出 `PREREQUISITE`，孤立节点近半

- course1-PDF：71 个知识点里 **37 个孤立**（`isolated_count`），只有 3 种关系，没有 `PREREQUISITE`。
- course2-PDF：74 个知识点里 **39 个孤立**，同样没有 `PREREQUISITE`。
- 两份 PDF 的关系数（24、25）只有对应 Markdown（66、55）的约 40%。学习路径推荐依赖前置关系，PDF 路径目前产出的图谱不适合生成路径。
- 与 5.1 同源的可能性较高（PDF 文本破碎 → 关系阶段输入质量差 → 输出不合规被 repair 或在容错中被丢弃），但本次只做测量，未做归因验证。

### 5.3 ADR-083（部首形近字）在真实 PDF 上核对通过

对两份 PDF 的全部 32 个文本块做逐字符扫描，**康熙部首区（U+2F00–U+2FD5）与部首补充区（U+2E80–U+2EF3）字符数为 0**；正文为正常简体中文。ADR-083 的 `pdf/2` 归一化在真实 Chrome 打印的中文 PDF 上确实生效。

### 5.4 迁移 016 的备份落点与交接描述不同（文档问题，非缺陷）

交接写「`backups/` 下有 `*-before-016.sqlite`」。实际落点是**数据库同级的 `src/backend/storage/backups/`**（`repositories/sqlite.py:151` 用 `path.parent / "backups"`），仓根没有 `backups/` 目录。本次备份文件 `src/backend/storage/backups/20261003T141139848603Z-before-016.sqlite`：`PRAGMA integrity_check = ok`、含 15 条迁移（迁移前状态）、1 行用户配置。迁移本身正常：`migrate.log` 为 `Applied migrations: 016`，`schema_migrations` 16 条，`user_model_configs.revision` 列已存在。

## 6. 发布与向量记账（ADR-082 决定 6 的首次真实验证）

只对两门课的 Markdown 课程各发布一次：

| 课程 | HTTP | 耗时 | 版本 | 节点/边 | 排除项 |
| --- | --- | --- | --- | --- | --- |
| course1-MD（`4f325420…`） | 200 | **11.21 秒** | v1 | 75 / 66 | 全 0 |
| course2-MD（`777c327ca1a247cea7ae36a69ec4a106`） | 200 | **6.58 秒** | v1 | 71 / 55 | 全 0 |

没有 `PUBLISH_BLOCKED`，未改任何图谱内容。

**记账核对（D2 修复的首次真实证据）**——`SELECT request_id, status, count(*), sum(usage_input) FROM model_calls WHERE purpose='embedding' AND course_id=<cid>`：

| 课程 | `request_id` | 行数 | `status` | 输入 token |
| --- | --- | --- | --- | --- |
| course1-MD | `publish:01M4124TTXYE98SBV93PATDZCZ` | 10 | `ok` | 7272 |
| course2-MD | `publish:01M41255Q0VRWZHGY4T45KTMSD` | 10 | `ok` | 4612 |

- `request_id` 的后缀与 `graph_versions.version_id` **逐字符相同**（`01M4124TTXYE98SBV93PATDZCZ` / `01M41255Q0VRWZHGY4T45KTMSD`），归属正确。
- 归属字段：`course_id` 已填，`user_id` 与 `task_id` 均为 NULL，`max_output_tokens = 0`，与 ADR-082 决定 6 一致。
- **结论：ADR-082 决定 6 在真实链路上验证通过。** 上一轮（计划 A 验证）报告过的「发布期向量调用未记账」缺口已不存在。
- 每门课 10 行 = 75/71 个知识点 + 16 个文本块按每批 10 条切分，数量与资料规模相符。

## 7. 用量

- 本次生成模型计费：**478987** token（输入 135999 + 输出 342988）。
- 向量（另计，按 ADR-082 决定 6 不计入生成模型预算）：`embedding` 20 行、输入 11884 token。
- **冲刺累计计费：140230 + 478987 = 619217 / 5000000**（约 12.4%）。
- **越线说明**：交接约定「累计超过 60 万就停止」。跑完第 3 份后累计 497634，但实测 PDF 成本是 Markdown 的 1.6～2.2 倍（192188、121583 vs 86974、78242），第 4 份预计会把累计推到 60 万以上；**已就此向用户说明并取得明确授权后继续**，第 4 份实际使累计达到 619217。授权与越线均在此登记。

## 8. 复现

```bash
scripts/start.sh --no-open                       # personal 模式；首次会先备份再执行迁移 016
# 在「模型 API 设置」保存教师自己的 DeepSeek 配置（先测试连接）
for spec in "数据结构 MD:datasets/contest/course1-ds-ch3/ch3-stack-queue.md" \
            "数据结构 PDF:datasets/contest/course1-ds-ch3/ch3-stack-queue.pdf" \
            "操作系统 MD:datasets/contest/course2-os-ch2/ch2-process-thread.md" \
            "操作系统 PDF:datasets/contest/course2-os-ch2/ch2-process-thread.pdf"; do
  name="${spec%%:*}"; file="${spec#*:}"
  MEASURE_PASSWORD=<演示口令> .venv/bin/python evaluation/measure_web_flow.py extract \
    --base-url http://127.0.0.1:8001 --username demo_teacher --password-env MEASURE_PASSWORD \
    --course-name "L11 实测 ${name}" --file "$file" --max-seconds 900
done
# 每次抽取后、人工编辑之前导出原始草稿：
#   GET /api/v1/courses/<cid>/graph  →  evaluation/raw/l11/<course>-<md|pdf>-draft.json
# 发布两门课的 Markdown 课程：
#   POST /api/v1/courses/<cid>/publish
sqlite3 src/backend/storage/smartsketch.sqlite3 \
  "SELECT purpose, count(*), sum(usage_input), sum(usage_output) FROM model_calls WHERE task_id='<TASK_ID>' GROUP BY purpose;"
sqlite3 src/backend/storage/smartsketch.sqlite3 \
  "SELECT request_id, status, count(*), sum(usage_input) FROM model_calls WHERE purpose='embedding' AND course_id='<CID>' GROUP BY request_id, status;"
```

本次四门课程的 ID（供后续 L15/L16 复用）：

| 资料 | course_id | task_id |
| --- | --- | --- |
| course1 · MD | `4f32542066b44f4890cb6f6d765971ed` | `978392cc455c4bc68c9fcb1cfeaa7c45` |
| course1 · PDF | `242a2f6b052e4c7a8466058800f77bc6` | `cd0a403f299a4377b208bff20db2017d` |
| course2 · MD | `777c327ca1a247cea7ae36a69ec4a106` | `dd8b20ae95b947c6acdbe9564803e65e` |
| course2 · PDF | `0803219bb56f478abea46e138c3d26d1` | `51202fb520b74530930fdd03e468474b` |
