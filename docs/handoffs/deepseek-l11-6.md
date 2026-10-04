# L11-6 真实模型教师流程测量

```text
task_id: L11-6（计划 B：docs/superpowers/plans/2026-10-03-contest-sprint-b-functional-loop.md）
review_status: ready_for_review
worktree: /Users/arvinhan/SmartSketch/.claude/worktrees/smartsketch-contest-sprint-77644f
branch: claude/smartsketch-contest-sprint-77644f（仅本地提交，未推送）
base_commit: fc2ad94
head_commit: 本任务提交
author: DeepSeek harness
根据: docs/handoffs/claude-l11-6-deepseek-handoff.md
changed_files:
  - evaluation/reports/l11-teacher-loop-2026-10.md（新增，本次主交付）
  - evaluation/raw/l11/course1-md-draft.json、course1-pdf-draft.json、course2-md-draft.json、course2-pdf-draft.json（新增，未编辑的原始 AI 输出，供 L16 人工判定）
  - docs/tasks.md（L11 行的状态与 L11-6 结果行）
  - docs/handoffs/deepseek-l11-6.md（本文件）
```

## 交付

四次抽取（两门课 × Markdown/PDF）+ 两次发布全部完成，**没有失败、没有停止项**。未改任何业务代码、测试、契约、迁移或脚本。

| 资料 | 总耗时 | 计费 token | 知识点 | 关系 / 种类 | 孤立节点 |
| --- | --- | --- | --- | --- | --- |
| course1 · Markdown | 83.97 秒 | 86974 | 75 | 66 / 4 | 3 |
| course1 · PDF | 200.37 秒 | 192188 | 71 | 24 / 3 | 37 |
| course2 · Markdown | 75.51 秒 | 78242 | 71 | 55 / 4 | 3 |
| course2 · PDF | 162.54 秒 | 121583 | 74 | 25 / 3 | 39 |

- 四次任务均 `stage = awaiting_review`、`progress = 0.95`、`error_code = null`，无失败块，无 `status != 'ok'` 的调用；`exit=0`（`measure_web_flow.py extract`）。
- 赛题指标：知识点 ≥20 **达到**（75/71/71/74）；关系 ≥3 种 **达到**（4/3/4/3）；抽取 ≤60 秒 **四份全部未达到**（差 24.0 / 140.4 / 15.5 / 102.5 秒）。准确率未判定，原始输出已导出。
- 发布：course1-MD HTTP 200 / 11.21 秒 / v1（75 节点 66 边）；course2-MD HTTP 200 / 6.58 秒 / v1（71 节点 55 边）；无 `PUBLISH_BLOCKED`。
- **ADR-082 决定 6（向量记账）首次真实通过**：两门课各 10 行 `purpose='embedding'`、`status=ok`，`request_id` 为 `publish:<version_id>` 且与 `graph_versions.version_id` 逐字符一致（`01M4124TTXYE98SBV93PATDZCZ`、`01M41255Q0VRWZHGY4T45KTMSD`），`course_id` 已填、`user_id`/`task_id` 为 NULL、`max_output_tokens=0`。上一轮报告过的「发布期向量未记账」缺口已不存在。
- **ADR-083（部首形近字）核对通过**：两份 PDF 共 32 个文本块逐字符扫描，康熙部首区与部首补充区字符数为 **0**。

## 迁移 016 核对

- `migrate.log`：`Applied migrations: 016`；`schema_migrations` 16 条；`user_model_configs.revision` 列已存在；Neo4j 向量索引 online。
- 备份落点是**数据库同级的 `src/backend/storage/backups/`**，不是交接写的仓根 `backups/`（`repositories/sqlite.py:151` 用 `path.parent / "backups"`）。文件 `src/backend/storage/backups/20261003T141139848603Z-before-016.sqlite`：`PRAGMA integrity_check = ok`、含 15 条迁移（迁移前状态）、1 行用户配置。**这是交接描述的落点偏差，不是缺陷。**

## 用量与预算（越线已获授权）

- 本次生成模型计费 **478987** token（输入 135999 + 输出 342988）；另有 `embedding` 20 行、输入 11884 token（按 ADR-082 决定 6 单独列出，不计入生成预算）。
- **冲刺累计 140230 + 478987 = 619217 / 5000000（约 12.4%）。**
- **越线说明（重要）**：交接约定「累计超过 60 万就停止」。跑完第 3 份后累计 497634，但实测 PDF 成本是 Markdown 的 1.6～2.2 倍（192188、121583 对 86974、78242），而交接的估算假设是「一份约 10 万」——第 4 份必然把累计推过 60 万。我把该测算连同三个选项交回用户，**用户明确选择「继续跑完第 4 次（授权越过 60 万止损线）」**，随后完成第 4 份。授权与越线在报告第 7 节同时登记。
- 向量费用归部署者，不占生成模型预算。
- **台账登记位置**：计划 B 的 L11-6 原本写「Modify: `docs/handoffs/claude-l11.md`（追加台账）」，但本次交接第 7 节只列了三项交付物，且 `docs/handoffs/README.md` 规定 `claude-*.md` 只由 Claude 写入。因此**未改 `claude-l11.md`**，台账记在本文件与报告第 7 节；请 Claude 在 `claude-l11.md` 追加本次 478987 token 与累计 619217。`docs/tasks.md` 的 L11 行与结果行已按 AGENTS.md §5.1 更新。

## verification

| 命令 | 结果 |
| --- | --- |
| `scripts/start.sh --no-open` | API 8001、前端 5174 就绪；`GET /api/v1/me/model-config` → `{"runtime_mode":"personal","configured":false}` |
| 教师配置（真实浏览器，Playwright） | 测试连接成功 731 毫秒 → 保存 → 状态脱敏（`••••`+末 4 位）、密钥框清空、侧栏「未配置」标记消失；截图 `.demo/l11-6/01-teacher-config-saved.png`（Git 忽略，key 未入截图） |
| `measure_web_flow.py extract` ×4 | 四次均 `exit=0`，`stage=awaiting_review`（见上表） |
| `GET /api/v1/courses/<cid>/graph` ×4 | 原始草稿已保存到 `evaluation/raw/l11/`（字节数与 sha256 见报告第 2 节） |
| `POST /api/v1/courses/<cid>/publish` ×2 | 均 HTTP 200，无阻断 |
| `model_calls` / `chunks` 汇总 | 155 次调用、23 次 repair、135999 输入 / 342988 输出；每份资料 16 个块 |
| 备份与迁移核对 | 见上节 |

## 发现的问题（只记录，未修）

1. **PDF 路径成本约为 Markdown 的 2～2.4 倍，且大量触发 repair**：course1-PDF 的 `repair` 达 13 次（14575 输入 + 49011 输出），接近该份总输出的三分之一；非模型阶段不是原因（见第 2 条）。
2. **旧基线的「入库 45.7 秒」已不成立**：本次非模型阶段只有 1.04～12.39 秒，总耗时几乎完全由模型调用决定。旧基线把它列为 L16 优化头号嫌疑，该判断需要更正。
3. **PDF 两份抽不出 `PREREQUISITE`，孤立节点近半**（37/71、39/74），关系数只有对应 Markdown 的约 40%。学习路径推荐依赖前置关系，PDF 路径产出的图谱目前不适合生成路径。与第 1 条可能同源（PDF 文本破碎 → 关系阶段输入质量差），本次未做归因验证。
4. **交接的备份落点描述有误**（见上节），建议后续把「`backups/`」改为「`src/backend/storage/backups/`」。

## unverified

- 准确率（≥70%）未判定：本次只导出原始输出，人工判定属 L16。
- 未对第 3 条做归因（例如逐块对比 PDF/MD 的块文本质量、统计关系输出不合规的具体种类）。
- PDF 两份、以及 course2 的课程**未发布**（按交接只发布两门课的 Markdown），因此没有 PDF 侧的向量记账数据。
- 首字与问答完整耗时属 L15-6/L16，本次未测。
- 端到端与门禁本次未重跑（属计划 B 的阶段门禁，不在 L11-6 范围）。

## api_and_data_changes

无。未改接口、契约、迁移或业务代码；本轮只做测量。副作用仅限冲刺工作区本地数据：新增四门课程（ID 见报告第 8 节）、四个 `awaiting_review` 任务、两份发布版本、一份迁移 016 的备份文件，以及 `demo_teacher` 的个人模型配置。

## rollback

回退本提交即可（报告 + 四个原始 JSON + `docs/tasks.md` 状态行 + 本文件）。迁移 016 已执行且不可逆（向前迁移），回滚方式见迁移文件头：停 API/worker 后用 `src/backend/storage/backups/20261003T141139848603Z-before-016.sqlite` 替换，或执行文件内的 `ROLLBACK` 语句。

## next_action

1. L15-6 Step 4 的问答抽样（另有交接），预计 4～8 万 token；执行前先核对累计 619217，**并注意 PDF 类资料的单份成本已实测为交接估算的约 2 倍**。
2. L16 人工判定准确率，用 `evaluation/raw/l11/` 的四份原始输出；同时更正「入库阶段是头号瓶颈」的旧判断，把优化目标对准模型调用数与 repair 次数（尤其 PDF 路径）。
3. 若要把抽取压到 60 秒以内，按本次数据应优先看 PDF 路径的 repair 次数（course1-PDF 49 次调用里有 13 次是 repair）。
4. 推送与合并待用户授权。
