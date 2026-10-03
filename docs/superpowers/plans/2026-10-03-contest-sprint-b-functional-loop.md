# 冲刺计划 B：教师与学生功能闭环（L11–L15）实施计划

> **执行方式**：沿用本会话逐任务执行（用户已确认，不再重选）。每个子任务按「失败测试 → 确认红 → 最小实现 → 确认绿 → 记录 / 原子提交 / 交接」推进，步骤用 `- [ ]` 跟踪。
> **状态**：规划待确认（2026-10-03）。用户确认前不改业务代码、契约或迁移，也不调用真实模型。

**Goal**：在修复后的计划 A 基线上，把教师「上传 → 进度 → 草稿 → 修正 → 发布」和学生「浏览 → 来源 → 掌握 → 路径 → 提问 → 定位」两条闭环在真实页面走通。每一步都要有可复跑的测试和页面证据。

**Architecture**：不重构分层，也不重写渲染器。全部改动落在已有的组件、组合式逻辑、适配层、服务和仓储上。唯一的共享边界变化是 `SourceRef` 与 `Citation` 增加可选字段 `document_name`，先改规格和契约，再重新生成 DTO。个人模式的端到端测试用本机 OpenAI 兼容假供应商：它包装现有演示模型，经 `MODEL_ENDPOINT_ALLOW_PRIVATE` 放行。

**Tech Stack**：Vue 3 + TypeScript + Vite + AntV G6 5.1.1；FastAPI + Pydantic；SQLite + Neo4j 5.26；pytest、vitest、Playwright（Chrome 可执行文件）。

**Spec**：
- 已签收设计：`docs/superpowers/specs/2026-10-02-contest-sprint-design.md`（§1 两条闭环、§6 前端闭环修复、§7 L11–L19、§8 测试策略）。
- 计划 A：`docs/superpowers/plans/2026-10-02-contest-sprint-a-personal-model-api.md`，以及修复后的 ADR-080、ADR-081、ADR-082。
- 相关规格：`specs/grounded-qa.md`、`specs/course-knowledge-graph.md`、`specs/learning-path.md`、`specs/teacher-review-publish.md`、`specs/identity-access.md`。
- 参考（只读）：Codex 审查 R01–R13 `/Users/arvinhan/.codex/worktrees/e92f/SmartSketch/docs/reviews/codex-product-readiness-2026-10-02.md`；赛题边界 `/Users/arvinhan/.codex/worktrees/e92f/SmartSketch/docs/reviews/codex-contest-scope-2026-10-02.md`。早期未签收的建议一律以已签收设计为准。

## 全局约束

- 关系类型只有 `CONTAINS`、`PREREQUISITE`、`RELATED_TO`、`EXAMPLE_OF`；`PREREQUISITE` 必须保持 DAG，新增前先做环检测。
- 学生端只做「学生提问、AI 回答」。不做自动出题、练习、批改、错题库、成绩。契约里的 `generateStudyMaterial`（`POST /courses/{cid}/kp/{kid}/material`）没有实现，本计划不碰。
- 个人生成凭据由各用户自己配置。没有配置时明确引导，绝不借用其他用户或全站的 key。系统级在线向量、根密钥与基础设施由部署者维护（ADR-080/081）。
- 必须保留计划 A 修复后的语义：
  - 配置身份按 `revision` 比较；
  - 截断回答报 `LLM_UNAVAILABLE`/`truncated`；
  - 问答全程一个截止时刻；
  - 供应商鉴权失败时任务终止；
  - 前端状态按会话与代际校验；
  - 共享向量调用写入 `model_calls`。
- 文档格式优先验收文本型 PDF 与 Markdown；DOCX、TXT 保留不删。
- 前端分层：`views/` 是页面，`components/` 放可复用 UI，`composables/` 放状态，`api/` 只封装 HTTP，图数据转换在 `graph/`。后端单向依赖：`api → schemas → services → repositories`。
- 不安装或升级依赖，不重置服务数据。真实模型联调只在确认预算后进行，并逐次登记台账。
- 每个任务跑最小相关测试与基础门禁 `PYTHON=.venv/bin/python PATH="$PWD/.venv/bin:$PATH" ./scripts/verify.sh`；每个阶段结束跑 `full`、`integration` 与端到端。PASS、SKIP、FAIL 分列报告，SKIP 不算 PASS。

---

## 0. 当前真实基线（前置门禁证据）

| 项 | 值 |
| --- | --- |
| 实际工作区 | `/Users/arvinhan/SmartSketch/.claude/worktrees/smartsketch-plan-a-fixes-e70a34` |
| 分支 | `claude/smartsketch-plan-a-fixes-e70a34`。已快进合回 `claude/smartsketch-contest-sprint-77644f`，两个分支 HEAD 相同 |
| 计划 B 基线 | `d766f40`（代码 HEAD `959331e`，其后只有文档提交）。**不用**旧的 `e86f4b9`，也不用停在 `6ff8a8d` 的主检出 |
| 未提交文件 | 无（写本计划前两个工作树都干净） |
| 门禁（代码 `959331e`） | 见下 |
| 调用台账 | 累计计费 140230 / 5000000 token（L02 抽取 101054 + V1 问答 16101 + V2 23075）。计划 A 修复与本次规划都没有产生真实模型调用 |

门禁明细（代码 `959331e`）：
- 基础档 PASS。
- 后端 full：3725 passed、27 skipped（已登记），PASS。
- 前端 full：811 passed；type-check 与 build 通过。
- 集成用例：393 passed、4 skipped（已登记），PASS。
- 图库后端用例：44 passed，PASS。
- 端到端：首次因缺根目录 `@playwright/test` 失败（环境原因）。补齐依赖后单独运行 `scripts/e2e.sh`，2 passed（演示模型）。
- `verify.sh integration` 同一次运行没有整体 exit 0。完整记录见 `docs/handoffs/claude-plan-a-review-fixes-2026-10-03.md`。

**前置阻断**：没有业务失败。端到端那次失败属于环境问题，已经补齐并补跑通过。

**前置但未满足的条件**（不能写成已满足）：
1. 冲刺环境的 SQLite 还没执行迁移 016。`scripts/start-demo.sh` 启动时会先备份，再自动迁移（第 194 行），所以 B0 首次启动时就会完成。
2. 个人模式（`LLM_MODE=personal`）还没有自动化端到端测试，现有两个端到端用的是演示模型。它由 L11-2、L11-3 补上。
3. 中文文本型 PDF 从未经过网页链路。现有端到端里的 PDF 是英文正文（`tests/e2e/fixtures.ts:29`），L11 首次验证。
4. 修复后的版本还没有在真实模型上复测抽取、问答质量与耗时。

## 1. 现状核对：复用、补验收、需改动

逐项读过源码和测试后得出下表。「复用/验收」表示功能已实现，只需在 L11/L15 的端到端里覆盖。

| 能力 | 现状（文件） | 结论 |
| --- | --- | --- |
| 建课、加学生（按用户名） | `CoursesView.vue`、`MembersView.vue`；`teacher.spec.ts` 已覆盖 | 复用/验收 |
| 个人 API 状态与引导 | `ModelSettingsView.vue`、`MaterialsView.vue`、`ChatView.vue`（L10 + N03–N05） | 复用/验收 |
| 上传、进度 SSE、取消、失败后重传、刷新恢复 | `useMaterials.ts`：加载即 `list` 并按文档 `subscribe`（406–543 行）；`h02.test.ts` | 复用/验收；鉴权与凭据失败文案已在 N02 补上 |
| 草稿编辑：节点增删改、关系增删、成环拒绝 | `useNodeEditor.ts`、`useRelationEditor.ts`、`TeacherGraphView.vue`；`teacher.spec.ts` 覆盖成环 | 复用/验收 |
| 草稿与发布版区分 | `TeacherGraphView.vue:171-174` 有「草稿」标识；学生只读发布版（ADR-063） | 验收：发布后再改草稿，学生看到的仍是旧版 |
| 发布阻断原因 | `useVersions.ts:24` 只给一句通用文案；后端 409 `details.reasons[]` 已有（`snapshot.py:140-170`，契约 `PublishBlocked*Reason`） | **改动**（L11-4） |
| 图谱来源 | `KnowledgeDetail.vue` 已展示位置与片段，但两个图谱页都没传 `documentNames`，也没处理 `@locate-source`（`StudentGraphView.vue:261`、`TeacherGraphView.vue:260`）；`SourceRef` 没有文件名 | **改动**（L12） |
| 问答引用 | `ChatView.vue` 右栏显示片段与位置；`Citation` 没有文件名 | **改动**（L12） |
| 画布可读性 | `lifecycle.ts:115` `autoFit: 'view'` 整图缩放；`CanvasGraph` 没有 `getZoom`/`zoomTo`/`focusElement`（G6 5.1.1 提供，`graph.d.ts:919/957/965`） | **改动**（L13-1） |
| 搜索 | `useGraphFilters.ts:139-148` 只按名称过滤隐藏，不定位、不选中 | **改动**（L13-2） |
| 问答 → 图谱 | `ChatView.vue` 的 `openKnowledgePoint` 只显示提示；全仓库没有代码消费 `?kp=` | **改动**（L13-4） |
| 掌握 → 推荐刷新 | `useLearning.ts` 的 `write` 之后刷新推荐 | 复用/验收 |
| 路径可视化与解释 | 只有 `mastered`/`learning`/`recommended` 状态色（`lifecycle.ts`）；推荐列表展示服务端分量，缺省 0.5 的难度/重要度原样显示（`Recommendations.vue:70-80`，`ranking.py:38`） | **改动**（L14） |
| 侧栏按课程内角色 | `App.vue` 的 `courseNav` 按全局 `role`；课程 store 没有 `myRole` | **改动**（L15-1） |
| 课程概览阶段与下一步 | `CoursesView.vue:86-130` 只有一组链接，没有阶段与下一步 | **改动**（L15-2） |
| 入课空态 | `CoursesView.vue:146` 只说「教师将你加入课程…」 | **改动**（L15-3） |
| 跨课隔离 | 后端各接口已有课程隔离测试（C/I/J 组） | 复用；L12 新增字段须补负例（L15-4） |

## 2. 覆盖矩阵（需求 → 任务 → 证据）

| 需求 / R 项 / 赛题指标 | 任务 | 回归测试 | 页面证据 |
| --- | --- | --- | --- |
| 教师闭环（设计 §1），R13 | L11-1、L11-2、L11-3 | `tests/e2e/personal.spec.ts`「教师 PDF+MD 闭环」 | 端到端截图与 trace |
| 两种格式各一次网页流程 | L11-1、L11-3 | 同上，两次上传 | 同上 |
| 节点/关系增删改、成环拒绝、删除后一致 | L11-3 | 同上；`teacher.spec.ts` 保留 | 同上 |
| 发布阻断原因可见 | L11-4 | `tests/frontend/l11.test.ts` | 端到端：构造悬空关系后发布 |
| 未配置、鉴权失败、预算/超时、取消、刷新恢复 | L11-2、L11-3、L11-5 | `personal.spec.ts`「供应商拒绝密钥」；`h02.test.ts` | 同上 |
| 草稿不影响发布版 | L11-3 | `personal.spec.ts` 断言学生仍见旧定义 | 同上 |
| ≥20 知识点、≥3 种关系、抽取 ≤60 秒（待实测） | L11-6 | 真实模型测量报告 | `evaluation/reports/l11-teacher-loop-2026-10.md` |
| R04 来源文件名、位置、片段 | L12-1 至 L12-4 | `tests/backend/test_l12.py`、`tests/frontend/l12.test.ts`、`personal.spec.ts` | 教师/学生 × 图谱/问答 四个入口 |
| 跨课来源负例 | L12-2、L15-4 | `test_l12.py::test_document_name_never_crosses_courses` | — |
| R06 可读视口、详情栏收起、高级筛选折叠、搜索定位 | L13-1 至 L13-3 | `tests/frontend/l13.test.ts` | `personal.spec.ts`：20+ 节点读到 `data-zoom` |
| R08 问答 → 图谱选中 | L13-4 | `l13.test.ts`；`personal.spec.ts` | 端到端：点问答知识点后图谱选中 |
| R11 掌握 → 推荐 → 路径解释 | L14-1 至 L14-4 | `tests/frontend/l14.test.ts`（确定性 DAG） | `personal.spec.ts` |
| R09 课程内角色侧栏 | L15-1 | `tests/frontend/l15.test.ts` | 混合角色账号走查 |
| R07 概览阶段与下一步；R10 入课空态 | L15-2、L15-3 | `l15.test.ts` | 端到端 |
| 两课程隔离、恶意文本 | L15-4、L15-5 | `tests/backend/test_l15_isolation.py`、`l15.test.ts` | 两课程端到端 |
| 计划 A 的 D/N 回归不退化 | L15-6 | `test_n01_n06`、`test_d1`、`test_d2`、`test_d3`、`test_e12`（N02 段）、`test_n07_n08`、`n03-n05.test.ts`、`chat-send-lock.test.ts`、`d1-d3.test.ts` | full/integration |
| 完整问答 ≤15 秒、准确率 ≥70%（待实测） | 交 L16 | — | 第 9 节 L16 交接清单 |

## 3. 顺序、文件所有权与工时

严格按下面的顺序执行。L12、L13、L14 会改动同一批图谱与问答文件，**不并行**。

```
B0 → L11-1 → L11-2 → L11-3 → L11-4 → L11-5 → (L11-6 真实模型，需预算确认)
   → L12-1 → L12-2 → L12-3 → L12-4
   → L13-1 → L13-2 → L13-3 → L13-4 → L13-5
   → L14-1 → L14-2 → L14-3 → L14-4
   → L15-1 → L15-2 → L15-3 → L15-4 → L15-5 → L15-6
```

| 共享文件 | 依次修改它的任务 |
| --- | --- |
| `src/frontend/src/views/StudentGraphView.vue` | L12-3 → L13-3 → L13-4 → L14-2/L14-3 |
| `src/frontend/src/views/TeacherGraphView.vue` | L12-3 → L13-3 |
| `src/frontend/src/views/ChatView.vue` | L12-3 → L13-4 |
| `src/frontend/src/graph/lifecycle.ts` | L13-1 → L14-2 |
| `src/frontend/src/components/GraphCanvas.vue` | L13-1 → L13-4 |
| `src/frontend/src/App.vue`、`stores/course.ts` | 只有 L15-1（以计划 A 的会话/代际修复为前置） |
| `src/contracts/api.v1.yaml` | 只有 L12-1 |
| `tests/e2e/personal.spec.ts` | L11-3 建立，L12-4、L13-5、L14-4、L15-6 依次追加 |

工时（小时）按纯开发计。真实模型、网络和图库的不确定性单列；可压缩项不能删掉核心能力。

| 任务组 | 正常 | 保守上界 | 依赖 | 可压缩 |
| --- | --- | --- | --- | --- |
| B0 | 0.3 | 0.5 | — | — |
| L11 | 8 | 14 | B0 | L11-4 文案细节；L11-5 已有覆盖的部分只做验收 |
| L12 | 5 | 8 | L11-3 | 超长片段的折叠样式 |
| L13 | 6 | 10 | L12 | 布局切换、动画、高级筛选的视觉 |
| L14 | 5 | 8 | L13 | 叙述文案润色；图例样式 |
| L15 | 6 | 10 | L14 | 概览视觉层级 |
| **合计** | **约 30** | **约 50** | | |
| 不确定性 | 真实模型抽取每份资料约 2～5 分钟，供应商可能限流或波动；本机到北京向量接口曾经时通时断；一次性 Neo4j 启动约 1～3 分钟 | | | |

**止损**：
- L11-3 是第一个硬关口。它跑不通就只修阻断，不开始 L12。
- 剩余工时少于 30 小时时，保留来源查看、可读视口与搜索定位、问答跳转、路径高亮与解释、课程内角色侧栏；压缩 L13-3 的视觉、L14 的叙述润色、L15-2 的视觉层级。
- 若连核心也保不住，向用户提一条带证据的取舍建议，不自行改变个人 API、问答或学习导航的方向。

---

## B0：基线确认与冲刺环境迁移

**Files**：无代码改动。记录写入 `docs/tasks.md` 与 `docs/handoffs/claude-l11.md`。

- [ ] **Step 1**：确认两个工作树 HEAD 都是 `d766f40` 且干净：`git -C <冲刺工作区> log --oneline -1 && git -C <冲刺工作区> status --short`。
- [ ] **Step 2**：在冲刺工作区用正式入口启动：`scripts/start.sh --no-open`。脚本会自动备份并执行迁移 016（`scripts/start-demo.sh:194`）。核对 `.demo/logs/migrate.log` 含 `016`，备份 `backups/*-before-016.sqlite` 存在，`GET /api/v1/me/model-config` 返回 `runtime_mode=personal`。
- [ ] **Step 3**：记录基线（HEAD、迁移结果、台账 140230），在任务板把 L11 改为 IN_PROGRESS。

---

## L11：教师闭环

### L11-1 自编代表性资料（两门课，两种格式）

**Files**：
- Create: `datasets/contest/course1-ds-ch3/ch3-stack-queue.md`（复制 `datasets/demo/ch3-stack-queue.md`，11779 字节，自编）
- Create: `datasets/contest/course2-os-ch2/ch2-process-thread.md`（新写一章「操作系统 第 2 章 进程与线程」，约 8000～12000 字，覆盖 ≥20 个概念、先修/包含/相关/示例四种关系的语料）
- Create: `scripts/build-contest-pdfs.sh`（Markdown → 带标题样式的 HTML → Chrome 无头 `--print-to-pdf`）
- Create: `datasets/contest/manifest.json`（每份资料的路径、sha256、字数、页数、来源声明「项目自编」）
- Test: `tests/backend/test_l11_datasets.py`

**Interfaces**：
- Produces：`datasets/contest/*/*.pdf` 两份文本型 PDF，以及清单 `manifest.json`。
- Consumes：`app.services.parsers.pdf.extract_pdf`、`app.services.parsers.pdf_headings`（只读调用，验证可解析）。

- [ ] **Step 1：写失败测试**

```python
# tests/backend/test_l11_datasets.py
"""L11：比赛自编资料可被现有解析器读出中文、页码与标题（不经模型）。"""
import hashlib, json
from pathlib import Path
import pytest
# worker 实际使用的分派表（src/backend/app/workers/parse_task.py:154）：pdf 走 提取 → 页眉页脚清洗 → 标题分节
from app.workers.parse_task import _PARSERS

ROOT = Path(__file__).resolve().parents[2] / "datasets" / "contest"
MANIFEST = json.loads((ROOT / "manifest.json").read_text(encoding="utf-8"))

@pytest.mark.parametrize("item", MANIFEST["documents"], ids=lambda d: d["path"])
def test_manifest_hash_matches(item):
    assert hashlib.sha256((ROOT / item["path"]).read_bytes()).hexdigest() == item["sha256"]

@pytest.mark.parametrize("item", [d for d in MANIFEST["documents"] if d["path"].endswith(".pdf")], ids=lambda d: d["path"])
def test_text_pdf_parses_to_chinese_with_pages_and_sections(item):
    doc = _PARSERS["pdf"]((ROOT / item["path"]).read_bytes())
    text = "".join(block.text for block in doc.blocks)
    assert "栈" in text or "进程" in text
    assert "(cid:" not in text
    assert {block.locator.page for block in doc.blocks} >= {1, 2}
    assert any(block.locator.section_titles for block in doc.blocks)   # 标题被识别为章节

@pytest.mark.parametrize("item", [d for d in MANIFEST["documents"] if d["path"].endswith(".md")], ids=lambda d: d["path"])
def test_markdown_parses_with_sections(item):
    doc = _PARSERS["markdown"]((ROOT / item["path"]).read_bytes())
    assert len(doc.blocks) >= 20 and all(block.locator.section_titles for block in doc.blocks[1:])
```

- [ ] **Step 2：确认红**。运行 `PYTHONPATH=src/backend .venv/bin/python -m pytest tests/backend/test_l11_datasets.py -q`，预期 FAIL：`manifest.json` 不存在。
- [ ] **Step 3：实现**。写第二门课的 Markdown；写脚本：

```bash
#!/usr/bin/env bash
# scripts/build-contest-pdfs.sh：把 datasets/contest 下的 Markdown 打印成文本型 PDF（Chrome 无头，不新增依赖）
set -euo pipefail
cd "$(dirname "$0")/.."
chrome="${CHROME:-/Applications/Google Chrome.app/Contents/MacOS/Google Chrome}"
for md in datasets/contest/*/*.md; do
  html="${md%.md}.print.html"; pdf="${md%.md}.pdf"
  .venv/bin/python - "$md" "$html" <<'PY'
import html, re, sys
src, out = sys.argv[1], sys.argv[2]
lines = open(src, encoding="utf-8").read().splitlines()
body = []
for line in lines:
    m = re.match(r"^(#{1,3})\s+(.*)", line)
    if m:
        body.append(f"<h{len(m.group(1))}>{html.escape(m.group(2))}</h{len(m.group(1))}>")
    elif line.strip():
        body.append(f"<p>{html.escape(line)}</p>")
open(out, "w", encoding="utf-8").write(
    "<!doctype html><meta charset='utf-8'><style>body{font-family:'PingFang SC',sans-serif;font-size:12pt}"
    "h1{font-size:20pt}h2{font-size:16pt}h3{font-size:14pt}</style>" + "\n".join(body))
PY
  "$chrome" --headless=new --disable-gpu --no-pdf-header-footer --print-to-pdf="$pdf" "file://$PWD/$html"
  rm -f "$html"
done
```

  运行后生成 PDF，计算 sha256、字数和页数，写入 `manifest.json`。
- [ ] **Step 4：确认绿**。同上命令 PASS。若出现 `(cid:` 或 `no_text`，说明 PDF 解析有阻断，转入 L11 阻断修复（先写复现测试），不改资料去迁就解析器。
- [ ] **Step 5：提交**。`feat(datasets): L11 比赛自编两门课资料与文本型 PDF 生成脚本`。

### L11-2 本机 OpenAI 兼容假供应商（个人模式接线用）

**Files**：
- Create: `scripts/fake_provider.py`：用标准库 `http.server` 包装 `app.services.ai.demo.DemoModelClient`，实现 `POST /v1/chat/completions`（`stream` 为 true 或 false 都支持）
- Test: `tests/tooling/test_l11_fake_provider.py`

**Interfaces**：
- Produces：`python scripts/fake_provider.py --port 18900`。
  - `Authorization: Bearer sk-fake-good` 返回演示输出；`Bearer sk-fake-bad` 返回 401。
  - 请求头 `X-Fake-Delay: <秒>` 让响应先等待（用于超时用例）。
- Consumes：`DemoModelClient`（`src/backend/app/services/ai/demo.py:647`，继承 `FakeModelClient.complete`/`.stream`，`fake.py:206/222`）。`demo_respond` 按 `ModelRequest.purpose` 分派（`demo.py:619`），而 HTTP 请求不带用途，所以假供应商用 `infer_purpose(prompt)` 从提示词推断。判别标记已核对：`<<资料` 对应 `answer_with_context`（`prompts/answer_with_context.yaml`）；`demo._TABLE_MARK`「实体表（JSON…」对应 `extract_relations`；`demo._KNOWN_MARK`「已抽取知识点（JSON…」对应 `extract_entities_gleaning`；「知识点 A：」对应 `judge_duplicate`；「原文定义」对应 `summarize_definition`；含对话历史段（`prompts/rewrite_query.yaml`）的对应 `rewrite_query`；其余对应 `extract_entities`。

- [ ] **Step 1：写失败测试**

```python
# tests/tooling/test_l11_fake_provider.py
import json, subprocess, sys, time, urllib.request, urllib.error
from pathlib import Path
import pytest
ROOT = Path(__file__).resolve().parents[2]

@pytest.fixture
def provider():
    proc = subprocess.Popen([sys.executable, str(ROOT / "scripts/fake_provider.py"), "--port", "18911"],
                            env={"PYTHONPATH": str(ROOT / "src/backend")})
    for _ in range(50):
        try:
            urllib.request.urlopen("http://127.0.0.1:18911/health", timeout=0.2); break
        except OSError:
            time.sleep(0.1)
    yield "http://127.0.0.1:18911/v1"
    proc.terminate(); proc.wait(5)

def _post(base, key, body):
    req = urllib.request.Request(base + "/chat/completions", json.dumps(body).encode(),
                                 {"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
    return urllib.request.urlopen(req, timeout=5)

def test_good_key_returns_compatible_completion(provider):
    reply = json.loads(_post(provider, "sk-fake-good", {"model": "fake", "max_tokens": 8,
                             "messages": [{"role": "user", "content": "ping"}]}).read())
    assert reply["choices"][0]["finish_reason"] in ("stop", "length") and "usage" in reply

def test_bad_key_is_401(provider):
    with pytest.raises(urllib.error.HTTPError) as caught:
        _post(provider, "sk-fake-bad", {"model": "fake", "max_tokens": 8, "messages": [{"role": "user", "content": "x"}]})
    assert caught.value.code == 401
```

- [ ] **Step 2：确认红**。运行 `PYTHONPATH=src/backend .venv/bin/python -m pytest tests/tooling/test_l11_fake_provider.py -q`，预期 FAIL：脚本不存在。
- [ ] **Step 3：实现**。用 `infer_purpose` 推断用途，构造 `ModelRequest(purpose, model, messages, max_output_tokens)` 交给 `DemoModelClient`，再按 OpenAI 格式写回（流式按 `data: {...}\n\n` 输出，最后发 `[DONE]`）。另提供 `/health`。只监听 `127.0.0.1`。同一个测试文件追加纯函数用例 `test_infer_purpose_matches_prompt_marks`：对上述七种提示片段各断言一次推断结果（直接 `import scripts/fake_provider.py` 中的 `infer_purpose`）。
- [ ] **Step 4：确认绿**，然后提交：`test(tooling): L11 本机 OpenAI 兼容假供应商`。

### L11-3 个人模式端到端：教师 PDF + Markdown 闭环

**Files**：
- Modify: `scripts/e2e.sh`。`E2E_LLM_MODE=personal` 时：
  - 启动 `scripts/fake_provider.py`；
  - 导出 `MODEL_CREDENTIAL_KEY`（测试专用的随机 32 字节）、`MODEL_ENDPOINT_ALLOW_PRIVATE=1`、`E2E_PROVIDER_URL`；
  - 默认模式仍是 demo，现有两个用例不变。
- Create: `tests/e2e/personal.spec.ts`
- Modify: `scripts/verify/integration.sh`。在现有 `scripts/e2e.sh` 之后追加一次 `E2E_LLM_MODE=personal scripts/e2e.sh personal.spec.ts`。`e2e.sh` 已把参数透传给 `npx playwright test "$@"`（第 104 行），可以按用例过滤，无需改动。现有两个演示用例要排除 `personal.spec.ts`：在默认调用里传 `teacher.spec.ts student.spec.ts`。

**Interfaces**：
- Consumes（页面上已有的 `data-test`）：`course-create`、`members-link`、`member-add`、`material-file-input`、`mc-base-url`、`mc-model`、`mc-api-key`、`mc-form`、`tg-*`、`model-config-required`、`chat-send`。实施时先用 `grep -rn 'data-test="' src/frontend/src` 核对实际名字，再写选择器。
- Produces：`personal.spec.ts` 的两个用例名，后续任务在其中追加断言：
  - 「教师 PDF+MD 闭环：配置 API → 上传 → 进度 → 草稿修正 → 发布 → 学生可见」
  - 「供应商拒绝密钥：任务终止并引导检查配置」

- [ ] **Step 1：写失败用例**。第一个用例逐步断言：
  1. 教师在设置页填写假供应商地址与 `sk-fake-good`，测试连接成功，然后保存。
  2. 建课并按用户名加入学生。
  3. 先后上传 `datasets/contest/course1-ds-ch3/` 下的 PDF 与 Markdown；进度从排队推进到待审核；刷新页面后进度仍然恢复。
  4. 草稿里新增一个节点、修改定义、删除一个节点，删除后与它相连的关系也消失。
  5. 新增一条会成环的先修关系，被拒绝并显示原因。
  6. 发布。
  7. 学生没配置时看到引导；配置后能看到已发布图谱并得到带出处的回答。
  8. 教师再改草稿里某个定义；学生刷新后看到的仍是发布版的旧定义。

  第二个用例：教师用 `sk-fake-bad` 保存后上传，任务失败，显示「模型服务拒绝了你的 API 密钥…模型 API 设置」。
- [ ] **Step 2：确认红**。运行 `PYTHON=.venv/bin/python PATH="$PWD/.venv/bin:$PATH" PLAYWRIGHT_CHROMIUM_EXECUTABLE="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" E2E_LLM_MODE=personal scripts/e2e.sh personal.spec.ts`。预期 FAIL：`e2e.sh` 还不支持 personal 模式。
- [ ] **Step 3：最小实现**。只改 `e2e.sh` 和接线。走查中发现的阻断，每个都先补后端或前端的复现测试，再修，并单独提交。
- [ ] **Step 4：确认绿**。两个用例都 PASS；把运行目录 `.e2e/<时间戳>/` 和 trace 路径记入交接。
- [ ] **Step 5：提交**：`test(e2e): L11 个人模式教师闭环与鉴权失败端到端`。

### L11-4 发布阻断原因可见

**Files**：
- Modify: `src/frontend/src/composables/useVersions.ts`（第 24 行附近）
- Modify: `src/frontend/src/components/VersionPanel.vue`
- Test: `tests/frontend/l11.test.ts`

**Interfaces**：
- Consumes：`ApiError.details.reasons: Array<{kind: 'cycle', cycle: string[]} | {kind: 'dangling_endpoint'|'invalid_source_ref'|'empty_graph'|'invalid_lineage', relation_id?, kp_id?, chunk_id?}>`（契约 `PublishBlockedDetails`）。
- Produces：`export function blockedReasonLines(reasons: unknown, names: ReadonlyMap<string, string>): string[]`（放在 `useVersions.ts`）。

- [ ] **Step 1：写失败测试**

```ts
// tests/frontend/l11.test.ts
import { describe, expect, it } from 'vitest'
import { blockedReasonLines } from '../../src/frontend/src/composables/useVersions'

describe('L11 发布阻断原因', () => {
  const names = new Map([['a', '栈'], ['b', '队列']])
  it('成环按知识点名称列出环路', () => {
    expect(blockedReasonLines([{ kind: 'cycle', cycle: ['a', 'b', 'a'] }], names))
      .toEqual(['先修关系成环：栈 → 队列 → 栈'])
  })
  it('悬空关系、来源失效、空图、谱系异常各有固定文案；未知名称退回 ID', () => {
    expect(blockedReasonLines([
      { kind: 'dangling_endpoint', relation_id: 'r1' }, { kind: 'invalid_source_ref', kp_id: 'x' },
      { kind: 'empty_graph' }, { kind: 'invalid_lineage', kp_id: 'a' },
    ], names)).toEqual([
      '关系 r1 的端点已不存在', '知识点 x 的来源无法定位', '图谱为空，没有可发布的知识点', '知识点 栈 的合并谱系异常',
    ])
  })
  it('结构不符时返回空数组，不抛错、不回显服务端 message', () => {
    expect(blockedReasonLines('oops', names)).toEqual([])
  })
})
```

- [ ] **Step 2：确认红**。运行 `cd src/frontend && npx vitest run ../../tests/frontend/l11.test.ts`，预期 FAIL：函数未导出。
- [ ] **Step 3：实现**。实现该函数；`VersionPanel` 收到 `PUBLISH_BLOCKED` 时，在通用文案下用 `<ul data-test="publish-blocked-reasons">` 列出各条原因。名称取自课程 store 当前草稿图。
- [ ] **Step 4：确认绿**；跑 `npm run type-check`；提交：`fix(frontend): L11 发布阻断按原因列出`。

### L11-5 失败路径验收补齐

现有 `h02.test.ts` 已覆盖失败文案、重传和取消，`useMaterials` 已覆盖刷新恢复。本任务只补缺口，不重写。

**Files**：
- Test: `tests/frontend/h02.test.ts`（追加）
- Test: `tests/e2e/personal.spec.ts`（追加）

- [ ] **Step 1：写失败测试**。
  - `h02.test.ts` 追加两条：`BUDGET_EXCEEDED` 显示「模型调用预算已用尽」；`LLM_UNAVAILABLE` + `reason=timeout` 显示通用的模型不可用文案，不出现「模型 API 设置」引导（超时不是凭据问题）。
  - `personal.spec.ts` 追加：任务处理中点击取消，任务转为已取消；用同一文件重新上传成功。
- [ ] **Step 2：确认红**。若这几条已经是绿色，说明行为早已存在：记为「验收已覆盖」，不为凑红修改实现。
- [ ] **Step 3/4**：只修真实缺口，然后提交：`test: L11 失败路径验收`。

### L11-6 真实模型教师流程测量（需用户确认预算后执行）

**Files**：
- Create: `evaluation/reports/l11-teacher-loop-2026-10.md`
- Modify: `docs/handoffs/claude-l11.md`（追加台账）

- [ ] **Step 1**：核对授权与额度：累计 140230 / 5000000。本次预计约 25～45 万 token（两门课 × 两种格式各抽取一次，另加约 10 题问答）。用户确认后才执行。
- [ ] **Step 2**：在隔离的冲刺库中，通过网页或 `evaluation/measure_web_flow.py extract --base-url http://127.0.0.1:8001 --username demo_teacher --password-env DEMO_TEACHER_PASSWORD --course-name <名> --file <路径>` 分别处理 PDF 与 Markdown。记录：
  - 资料规模（字数、页数、块数）；
  - 分阶段耗时（排队、解析、抽取、入库）；
  - `model_calls` 的调用数与 usage；
  - 知识点数与关系种类；
  - 原始 AI 输出快照，供 L16 人工判定（教师修正后的图不算原始准确率）。
- [ ] **Step 3**：报告分列「假供应商接线证据」和「真实模型质量与耗时」。抽取若超过 60 秒，照实写出差距。
- [ ] **Step 4**：更新台账后提交：`docs(eval): L11 真实模型教师流程测量`。

---

## L12：来源可查看（R04）

### L12-1 规格与契约：`document_name`

**Files**：
- Modify: `src/contracts/api.v1.yaml`：`SourceRef.properties` 与 `Citation.properties` 都增加：

```yaml
        document_name:
          type: string
          minLength: 1
          maxLength: 255
          description: "资料文件名（课程内资料的原始文件名）；资料已删除或不可读时省略，客户端显示「资料不可用」。仅来自同一课程（ADR-084）。"
```

- Modify: `specs/grounded-qa.md` 的 Q4 `citations` 行，加入「`document_name` 由服务端按同课程资料填写」。
- Modify: `specs/course-knowledge-graph.md`，在知识点详情来源一节写入同一规则。
- Modify: `docs/decisions.md`，新增 ADR-084「来源文件名的可选字段与课程隔离」。
- Regenerate: `PATH="$PWD/.venv/bin:$PATH" ./scripts/gen-contracts.sh`
- Test: `tests/contracts/`（既有门禁）

- [ ] **Step 1：确认红**。在 `tests/contracts/test_b08.py` 追加断言：`SourceRef` 与 `Citation` 都有可选的 `document_name`，且 `maxLength` 为 255。运行 `.venv/bin/python -m pytest tests/contracts/test_b08.py -q`，预期 FAIL。
- [ ] **Step 2：实现**。改 YAML（说明文字含冒号时必须加双引号，计划 A 在这里踩过坑），然后重新生成。
- [ ] **Step 3：确认绿**。运行 `PATH="$PWD/.venv/bin:$PATH" ./scripts/verify.sh` 应 exit 0；跑前端 `npm run type-check`。
- [ ] **Step 4：提交**：`docs(contracts): L12 SourceRef/Citation 增加可选 document_name`。

### L12-2 后端填写文件名（课程隔离）

**Files**：
- Modify: `src/backend/app/repositories/materials.py`，增加：

```python
def material_names(sqlite_url: str, *, course_id: str, material_ids: Iterable[str]) -> dict[str, str]:
    """同一课程内资料 ID → 原始文件名；他课或已删除的 ID 不出现在结果里。"""
    ids = sorted(set(material_ids))
    if not ids:
        return {}
    marks = ",".join("?" * len(ids))
    with connect(sqlite_url) as database:
        rows = database.execute(
            f"SELECT id, filename FROM materials WHERE course_id = ? AND id IN ({marks})", (course_id, *ids)
        ).fetchall()
    return {row[0]: row[1] for row in rows}
```

- Modify: `src/backend/app/services/graph/read.py`。`_evidence_refs` 构造完成后，按 `material_names` 给 `SourceRef` 加 `document_name`；查不到就省略。
- Modify: `src/backend/app/services/qa/citations.py`。`Evidence` 增加 `document_name: str | None = None`，`citation()` 有值时输出该字段。
- Modify: `src/backend/app/services/qa/chat.py`。构造 `Evidence` 前，用 `material_names(self.settings.SQLITE_URL, course_id=version.course_id, material_ids={c.document_id for c in context.chunks})` 查名；查询失败只记 WARNING，省略文件名，不中断回答。
- Test: `tests/backend/test_l12.py`

- [ ] **Step 1：写失败测试**。用例名与断言如下：
  - `test_kp_detail_sources_carry_document_name`：同课资料的来源带文件名。
  - `test_citations_carry_document_name`：`CitationStream` 中 `Evidence(document_name="ch3.pdf")` 的引用输出带 `document_name`。
  - `test_document_name_never_crosses_courses`：课程 B 的资料 ID 出现在课程 A 的查询里时，结果为空。
  - `test_deleted_material_omits_name`：资料删除后省略文件名，来源仍然返回。
  - `test_name_lookup_failure_does_not_break_answer`：查名抛出 `sqlite3.OperationalError` 时回答照常 answered，只是没有文件名。
- [ ] **Step 2：确认红**。运行 `PYTHONPATH=src/backend .venv/bin/python -m pytest tests/backend/test_l12.py -q`。
- [ ] **Step 3：实现**上述三处改动。
- [ ] **Step 4：确认绿**，并跑 `tests/backend/test_j06.py tests/backend/test_d1.py tests/backend/test_g0*.py` 确认不退化；然后提交：`feat(backend): L12 来源与引用带同课资料文件名`。

### L12-3 前端：四个入口都能查看出处

**Files**：
- Create: `src/frontend/src/components/SourceViewer.vue`。展示：文件名（缺失时显示「资料不可用」）、页码或章节（Markdown 没有页码时只显示章节）、原文片段。片段超过 600 字时先折叠，可展开；片段用文本插值渲染，绝不用 `v-html`。
- Modify: `src/frontend/src/composables/useKnowledgeDetail.ts`。`SourceView` 增加 `documentName?: string`，由 `toKnowledgeDetailView` 从 `document_name` 映射。
- Modify: `src/frontend/src/components/KnowledgeDetail.vue`。`documentLabel` 优先用 `source.documentName`。
- Modify: `src/frontend/src/views/StudentGraphView.vue`、`TeacherGraphView.vue`。处理 `@locate-source`：把 `SourceLocation` 与对应的 `SourceView` 交给 `SourceViewer`，在详情面板内展开，可关闭。
- Modify: `src/frontend/src/views/ChatView.vue`。`sourceLine` 前面加上 `citation.document_name ?? '资料不可用'`；`Citation` 类型（`useChat.ts:8`）增加可选的 `document_name`。
- Test: `tests/frontend/l12.test.ts`

**Interfaces**：
- Consumes：L12-1 生成的 `components['schemas']['SourceRef']['document_name']`、`Citation['document_name']`。
- Produces：`SourceViewer` 的 props `{ source: SourceView | Citation-like; location: SourceLocation | null }` 与事件 `close`；`data-test`：`source-viewer`、`sv-document`、`sv-location`、`sv-excerpt`、`sv-expand`。

- [ ] **Step 1：写失败测试**（组件与页面级）：
  1. PDF 来源显示「ch3.pdf · 第 2 页」；Markdown 来源显示「ch3.md · 第 3 章 > 3.1 栈」。
  2. 缺少文件名时显示「资料不可用」，不显示资料 ID 冒充文件名。
  3. 超长片段先折叠，展开后显示全文。
  4. 片段里的 `<img src=x onerror=alert(1)>` 按纯文本显示，DOM 中没有 `img` 元素。
  5. 学生图谱页点「来源」后打开 `source-viewer`。
  6. 教师图谱页同上。
  7. 问答右栏显示文件名。
- [ ] **Step 2：确认红**。运行 `cd src/frontend && npx vitest run ../../tests/frontend/l12.test.ts`。
- [ ] **Step 3：实现**。
- [ ] **Step 4：确认绿**。跑 `npx vitest run ../../tests/frontend/h06.test.ts ../../tests/frontend/h11.test.ts ../../tests/frontend/h14.test.ts ../../tests/frontend/redesign-chat.test.ts` 确认不退化，再跑 `npm run type-check`；然后提交：`feat(frontend): L12 图谱与问答来源可查看`。

### L12-4 端到端证据：两种资料 × 教师/学生 × 图谱/问答

- [ ] **Step 1**：在 `personal.spec.ts` 第一个用例里追加：
  - 教师图谱：PDF 来源显示页码、Markdown 来源显示章节；
  - 学生图谱：同上；
  - 问答引用：显示文件名。
- [ ] **Step 2**：确认红（L12-3 之前跑这一步应 FAIL；若已合入则直接绿，并在交接中说明顺序）。
- [ ] **Step 3**：确认绿后提交：`test(e2e): L12 四入口来源证据`。

---

## L13：图谱可读、可选，问答能定位节点（R06、R08）

### L13-1 可读的初始视口与按节点聚焦

**Files**：
- Modify: `src/frontend/src/graph/lifecycle.ts`：
  - `CanvasGraph` 增加可选方法 `getZoom?(): number`、`zoomTo?(zoom: number): Promise<void>`、`focusElement?(id: string): Promise<void>`；
  - 新增常量 `READABLE_ZOOM = 0.7`；
  - 首次渲染完成并 `fitView` 之后，若 `getZoom() < READABLE_ZOOM`，就 `zoomTo(READABLE_ZOOM)`，再聚焦到第一个入度为 0 的节点（若有选中项则聚焦选中项）；
  - `GraphLifecycle` 增加 `focus(kpId: string): void`，内部调用 `focusElement(nodeElementId(kpId))`；
  - `onStatus` 回调额外带出当前缩放，供页面写 `data-zoom`。
- Modify: `src/frontend/src/components/GraphCanvas.vue`。暴露 `defineExpose({ focus })`，容器上加 `:data-zoom` 属性。
- Test: `tests/frontend/l13.test.ts`（用假的 `CanvasGraph` 工厂，参照 `tests/frontend/h04.test.ts` 的写法）

- [ ] **Step 1：写失败测试**
  1. 假图 `fitView` 后 `getZoom()` 返回 0.3：生命周期调用 `zoomTo(0.7)` 和一次 `focusElement`。
  2. `getZoom()` 返回 1.0：不调用 `zoomTo`。
  3. `focus('kp1')` 调用 `focusElement('kp:kp1')`（前缀以 `nodeElementId` 为准）。
  4. 假图不实现这些可选方法时不报错（兼容 H04 的测试替身）。
- [ ] **Step 2：确认红**。运行 `cd src/frontend && npx vitest run ../../tests/frontend/l13.test.ts`。
- [ ] **Step 3：实现**。
- [ ] **Step 4：确认绿**，并跑 `h04.test.ts h05.test.ts` 确认不退化；提交：`fix(graph): L13 初始视口不低于可读缩放并支持按节点聚焦`。

### L13-2 搜索后定位并选中

**Files**：
- Modify: `src/frontend/src/composables/useGraphFilters.ts`。新增 `locate(query: string): string | null`：在当前筛选可见的节点里按名称（规范化后）精确匹配优先、包含匹配其次，返回第一个 `kpId`，并 `select` 它。原有的过滤行为保留。
- Modify: `src/frontend/src/components/GraphToolbar.vue`。搜索框按 Enter 时触发 `locate` 事件；没有匹配时显示「未找到」。
- Modify: `StudentGraphView.vue`、`TeacherGraphView.vue`。收到 `locate` 后调用 `canvas.focus(kpId)`。
- Test: `tests/frontend/l13.test.ts`（追加）

- [ ] **Step 1：写失败测试**：精确匹配优先于包含匹配；被筛选隐藏的节点不参与匹配；没有匹配时返回 null 且不清空当前选中。
- [ ] **Step 2/3/4**：确认红 → 实现 → 确认绿；提交：`feat(graph): L13 搜索定位并选中`。

### L13-3 未选中时收起详情栏，高级筛选折叠

**Files**：
- Modify: `StudentGraphView.vue`。右栏在 `selected === null` 时不渲染详情容器，画布占满宽度；掌握提示移到画布上方的一行。
- Modify: `GraphToolbar.vue`。关系类型、状态、置信度等高级筛选放进 `<details data-test="gt-advanced">`，默认收起；搜索与布局切换保持常显。
- Test: `tests/frontend/l13.test.ts`（追加）

- [ ] **Step 1**：写失败测试：未选中时不存在 `.student-graph__aside`；选中后出现；`gt-advanced` 默认没有 `open` 属性。
- [ ] **Step 2/3/4**：确认红 → 实现 → 确认绿；跑 `h11.test.ts h05.test.ts` 确认不退化；提交：`fix(frontend): L13 详情栏按选中展开、高级筛选折叠`。

### L13-4 问答知识点跳转并在图谱中选中

**Files**：
- Modify: `src/frontend/src/views/ChatView.vue`。知识点按钮改为 `RouterLink`，目标是 `{ name: STUDENT_GRAPH_ROUTE, params: { cid }, query: { kp: id, v: String(entry.graphVersion) } }`。没有学生图谱路由时退回原来的提示。
- Modify: `src/frontend/src/views/StudentGraphView.vue`。监听 `route.query.kp`/`v`。图加载完成后：
  - 课程一致、`graphVersion === Number(v)` 且节点存在：`filters.select(kp)`，然后 `canvas.focus(kp)`；
  - 节点不在当前图中：提示「该知识点不在当前发布版本中」；
  - 版本不同但节点仍在：选中，并提示「回答基于第 v 版，当前为第 N 版」；
  - 切课后旧的 `kp` 作废。
  - 绝不跨课程查找同 ID 的节点。
- Test: `tests/frontend/l13.test.ts`（追加）

- [ ] **Step 1：写失败测试**。
  - 直接进入 `/courses/c1/graph?kp=a&v=2`，图版本为 2：`a` 被选中，`focus('a')` 被调用。
  - `?kp=gone`：显示「不在当前发布版本中」。
  - `?kp=a&v=1`、当前版本为 2：选中并提示版本差异。
  - 在图还没加载完时切换课程：旧课程的 `kp` 不在新课程里被选中。
  - 问答页的知识点按钮链接到带 `kp` 与 `v` 的地址。
- [ ] **Step 2/3/4**：确认红 → 实现 → 确认绿；提交：`feat(frontend): L13 问答知识点跳转图谱并选中`。

### L13-5 页面证据（20+ 节点）

- [ ] **Step 1**：在 `personal.spec.ts` 中断言：
  - 课程一发布后图谱节点 ≥20（以 `GET /graph` 的节点数为准）；
  - 画布容器 `data-zoom` ≥ 0.7；
  - 搜索「循环队列」后详情标题正确；
  - 刷新直达 `?kp=` 也能选中；
  - 从问答点知识点后，图谱选中同一节点。
- [ ] **Step 2**：确认绿后提交：`test(e2e): L13 可读视口、搜索与问答定位`。

---

## L14：掌握标记 → 推荐更新 → 看懂学习路径（R11）

### L14-1 学习路径纯函数（确定性 DAG）

**Files**：
- Create: `src/frontend/src/graph/learningPath.ts`
- Test: `tests/frontend/l14.test.ts`

**Interfaces**：
- Consumes：`GraphExchange['nodes']`、`GraphExchange['edges']`（只取 `type === 'PREREQUISITE'` 且状态不是 `rejected` 的边）；掌握表 `ReadonlyMap<string, 'mastered' | 'learning' | 'not_started'>`；推荐列表 `Recommendation[]`（顺序即服务端排序）。
- Produces：

```ts
export type PathRole = 'mastered' | 'prereqMissing' | 'next' | 'unlocks' | 'dimmed'
export interface LearningPath {
  /** 推荐顺序：kpId → 1 起的序号（仅推荐项） */
  order: ReadonlyMap<string, number>
  /** 选中推荐项（或首个推荐项）时各节点的角色；未出现的节点为 dimmed */
  roles: ReadonlyMap<string, PathRole>
  /** 应高亮的先修边：relation id */
  edges: ReadonlySet<string>
  /** 「已掌握 → 下一步 → 之后解锁」的名称列表 */
  narrative: { mastered: string[]; next: string[]; unlocks: string[] }
}
export function buildLearningPath(
  nodes: ReadonlyArray<{ id: string; name: string }>,
  edges: ReadonlyArray<{ id: string; type: string; from_id: string; to_id: string; status?: string }>,
  mastery: ReadonlyMap<string, string>,
  recommendations: ReadonlyArray<{ kp_id: string }>,
  focus: string | null,
): LearningPath
```

  计算规则：
  - 焦点 `f`：取 `focus`；为空则取第一个推荐项；没有推荐项时为 null。
  - `f` 的直接前置：已掌握的标记 `mastered`，未掌握的标记 `prereqMissing`。`f` 自身标记 `next`。
  - `f` 的直接后继 `s`：只有 `s` 的**全部**前置在「已掌握 ∪ {f}」之内时才标记 `unlocks`。
  - 高亮的边：`f` 的入边，以及指向 `unlocks` 节点的出边。
  - 其余节点都是 `dimmed`。

- [ ] **Step 1：写失败测试**（确定性 DAG：A→C、B→C、C→D、C→E、E→F、G 孤立）：
  1. `test 无前置`：焦点 A，没有前置；`next=A`；A 的后继 C 还需要 B，所以 C 不在 unlocks 中。
  2. `test 多前置必须全部满足`：A 已掌握，焦点 B；C 的全部前置 {A, B} 都在「已掌握 ∪ {B}」之内，所以 C 是 unlocks；A 是 mastered。
  3. `test 分支`：A、B 已掌握，焦点 C；unlocks 是 D 和 E；F 不在其中（F 要先学 E）。
  4. `test 已全掌握或无推荐`：推荐为空、focus 为 null 时，roles 全为 dimmed，narrative 三项都是空数组。
  5. `test 取消掌握后重新计算`：A 从已掌握变成未掌握后，焦点 B 时 A 变为 prereqMissing，C 不再是 unlocks。
  6. `test 排除被拒边与非先修边`：`RELATED_TO` 和 `status: 'rejected'` 的边不参与计算。
  7. `test 推荐序号从 1 开始并保持服务端顺序`。
- [ ] **Step 2：确认红**。运行 `cd src/frontend && npx vitest run ../../tests/frontend/l14.test.ts`。
- [ ] **Step 3：实现**。纯函数，不依赖 Vue。
- [ ] **Step 4：确认绿**后提交：`feat(graph): L14 学习路径纯函数`。

### L14-2 画布高亮路径、序号与淡化

**Files**：
- Modify: `src/frontend/src/graph/lifecycle.ts`。节点状态增加 `pathPrereq`（未满足的前置）、`pathUnlock`、`dimmed`（`opacity: 0.25`）；边状态增加 `pathEdge`（加粗、紫色）与 `dimmed`。颜色只在这里定义。
- Modify: `src/frontend/src/composables/useLearning.ts`。`applyLearningStates` 改为接收 `LearningPath`：叠加角色状态；推荐项的节点标签前加序号「1. 」；边按 `edges` 叠加 `pathEdge`，其余边 `dimmed`。
- Modify: `StudentGraphView.vue`。点击某个推荐项或选中一个推荐节点时，把它作为 `focus`。
- Test: `tests/frontend/l14.test.ts`（追加）、`tests/frontend/i06.test.ts`（保持绿）

- [ ] **Step 1**：写失败测试：推荐第 1 项节点的标签以「1. 」开头；未满足的前置带 `pathPrereq`；无关节点带 `dimmed`；高亮的边带 `pathEdge`。
- [ ] **Step 2/3/4**：确认红 → 实现 → 确认绿；提交：`feat(frontend): L14 图谱高亮学习路径与推荐序号`。

### L14-3 推荐解释：先修事实优先，缺省值不冒充测量

**Files**：
- Modify: `src/frontend/src/components/Recommendations.vue`：
  - 列表顶部加一行 `data-test="rc-path-line"`：「已掌握：A、B → 下一步：C → 之后解锁：D、E」（来自 `narrative`）；
  - 每项显示序号；
  - 「评分明细」改名为「排序参考」，并且：`reason_facts.importance === 0.5` 或 `difficulty === 0.5` 时显示「未标注（按中性值 0.5 排序）」，不显示成测量值。
- Modify: `src/frontend/src/composables/useLearning.ts`。`reasonFactRows` 增加 `labelledDefault` 处理。
- Test: `tests/frontend/l14.test.ts`（追加）

- [ ] **Step 1**：写失败测试：路径行文本正确；importance 为 0.5 时显示「未标注」；为 0.8 时显示数值。
- [ ] **Step 2/3/4**：确认红 → 实现 → 确认绿；提交：`fix(frontend): L14 推荐解释以先修事实为主，缺省值标为未标注`。

### L14-4 端到端：掌握变化驱动推荐与高亮

- [ ] **Step 1**：在 `personal.spec.ts` 追加：
  - 学生把推荐第 1 项标为已掌握后，推荐列表变化，路径行更新；
  - 刷新后仍然保留；
  - 取消掌握后恢复原推荐；
  - 另一个学生账号看不到这条掌握记录。后端隔离已有 `test_i01.py`、`test_i02.py`，这里补页面证据。
- [ ] **Step 2**：确认绿后提交：`test(e2e): L14 掌握与路径联动`。

---

## L15：课程内角色、下一步引导、跨课隔离与总回归（R07、R09、R10）

### L15-1 侧栏按当前课程内角色

**Files**：
- Modify: `src/frontend/src/stores/course.ts`。增加 `myRole: Ref<'teacher' | 'student' | null>` 与 `setRole(scope: CourseRequestScope, role)`；`selectCourse` 时重置为 null。
- Modify: `src/frontend/src/App.vue`。`courseId` 变化时，用课程 store 的 `beginRequest()` 作用域调用 `coursesApi.get(cid)`（`api/courses.ts` 已有的 `get`），再 `setRole`。`courseNav` 改为按 `course.myRole` 选择入口；角色未知时只显示「课程概览」。会话变化沿用计划 A 的 `runtime.startSession` 时机。
- Test: `tests/frontend/l15.test.ts`

- [ ] **Step 1：写失败测试**（Review Focus「旧响应」）：
  1. 教师账号进入自己是学生的课程：侧栏显示「知识图谱与学习路径」「课程问答」，不显示「图谱编辑」。
  2. 进入自己是教师的课程：显示教师入口。
  3. 从课程 1 切到课程 2 时，课程 1 的 `get` 晚到，被丢弃。
  4. 退出时角色清空。
- [ ] **Step 2/3/4**：确认红 → 实现 → 确认绿；跑 `b03.test.ts h01.test.ts n03-n05.test.ts` 确认不退化；提交：`fix(frontend): L15 侧栏按课程内角色`。

### L15-2 课程概览：当前阶段与下一步

**Files**：
- Modify: `src/frontend/src/composables/useCourses.ts`。新增纯函数：

```ts
export type CourseStage = 'no_material' | 'drafting' | 'published' | 'waiting_publish'
export function courseNextStep(course: { myRole: 'teacher' | 'student'; kpCount: number; publishedVersion: number | null },
                               needsConfig: boolean): { stage: CourseStage; text: string; action: 'settings' | 'materials' | 'teacherGraph' | 'studentGraph' | 'chat' | null }
```

  规则：
  - 教师：`needsConfig` 时提示先配置模型 API；`kpCount === 0` 时去上传资料；有草稿未发布时去审核并发布；已发布时去「图谱编辑」继续维护（同时提示学生看到的是第 N 版）。
  - 学生：未发布时显示「等待教师发布图谱」，没有动作；已发布且 `needsConfig` 时可以浏览图谱，提问前需配置；已发布且已配置时去浏览图谱与学习路径。
- Modify: `src/frontend/src/views/CoursesView.vue`。当前课程区显示阶段与一个主按钮；链接组改为次要列表，不重复侧栏已有的入口。
- Test: `tests/frontend/l15.test.ts`（追加，覆盖每个分支）

- [ ] **Step 1/2/3/4**：失败测试 → 确认红 → 实现 → 确认绿；提交：`feat(frontend): L15 课程概览显示阶段与下一步`。

### L15-3 入课空态

**Files**：
- Modify: `CoursesView.vue:146`。学生空态改为：「你还没有加入任何课程。请把你的用户名「{username}」告诉任课教师，由教师在课程的「成员」中添加你。」用户名取自会话 store。
- Test: `tests/frontend/l15.test.ts`（追加）

- [ ] **Step 1/2/3/4**：失败测试 → 确认红 → 实现 → 确认绿；提交：`fix(frontend): L15 入课空态说明用户名添加流程`。

### L15-4 跨课隔离回归（新增字段与跳转）

**Files**：
- Test: `tests/backend/test_l15_isolation.py`

- [ ] **Step 1：写测试**（Review Focus「跨课权限」）：
  - 课程 B 的学生读课程 A 的 `/kp/{kid}`：403 或 404，响应里没有课程 A 的文件名。
  - 课程 A 的问答引用只含课程 A 的 `document_name`。
  - 进度与推荐接口按课程隔离（复用 I01/I02 的构造方式）。
  - 教师 X 是课程 A 的教师、课程 B 的学生：在 B 读 `/graph` 只拿到发布版，不能读草稿。
- [ ] **Step 2**：运行。若已经全绿（隔离早已存在），记为「回归固化」；若有红，先修复再提交：`test(backend): L15 跨课隔离回归`。

### L15-5 恶意文本与来源不可信

**Files**：
- Test: `tests/frontend/l15.test.ts`（追加）、`tests/backend/test_l15_isolation.py`（追加）

- [ ] **Step 1**：写失败测试（Review Focus「来源缺失或不可信」）：
  - 资料片段与知识点定义里含 `<script>`、`javascript:` 链接、伪造的 `[1]` 标记：`SourceViewer`、`KnowledgeDetail` 和 `ChatMarkdown` 都按文本显示，不产生可执行节点；
  - 后端返回的 `document_name` 超过 255 字符时被契约拒绝（生成的 DTO 校验）。
- [ ] **Step 2/3/4**：确认红 → 修复 → 确认绿；提交：`test: L15 恶意文本与不可信来源`。

### L15-6 两课程内容与总验收

**Files**：
- Modify: `tests/e2e/personal.spec.ts`。新增用例「两门课互不串课」：
  - 第二门课（操作系统资料）由同一教师发布；
  - 学生只加入课程一时看不到课程二；
  - 加入两门课后切换：图谱、掌握、推荐、问答、来源各属各课；
  - 切课时旧问答回答不写入新课页面。
- Modify: `docs/tasks.md`、`docs/handoffs/claude-l15.md`

- [ ] **Step 1**：确认红 → 补齐 → 确认绿。
- [ ] **Step 2**：阶段门禁：

```bash
PYTHON=.venv/bin/python PATH="$PWD/.venv/bin:$PATH" PLAYWRIGHT_CHROMIUM_EXECUTABLE="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" ./scripts/verify.sh integration
git diff --check d766f40 HEAD
```

- [ ] **Step 3**：计划 A 的 D/N 回归逐项列出 PASS 或 FAIL（覆盖矩阵最后一行的测试文件）。
- [ ] **Step 4**：真实模型问答抽样（需预算确认）：两门课各 5 题（课内 4 题、课外 1 题），记录完整耗时、首字耗时、结局（answered / not_covered / truncated / timeout）与引用文件名。和假模型结果分表。
- [ ] **Step 5**：提交，并把交接交给 Codex 复审。

---

## 4. Review Focus → 正式测试任务

| Focus | 落点任务 | 测试 |
| --- | --- | --- |
| 旧响应 / 旧版本 | L13-4、L15-1 | `l13.test.ts`「图未加载时切课」「旧版本提示」；`l15.test.ts`「课程 1 的 get 晚到被丢弃」 |
| 跨课权限 | L12-2、L15-4 | `test_l12.py::test_document_name_never_crosses_courses`；`test_l15_isolation.py` |
| 来源缺失或不可信 | L12-3、L15-5 | `l12.test.ts`「资料不可用」「超长折叠」「片段按文本」；`l15.test.ts` 恶意文本 |
| 多前置与进度回退 | L14-1 | `l14.test.ts`「多前置必须全部满足」「取消掌握后重新计算」 |
| 上游超时、鉴权与任务失败 | L11-2、L11-3、L11-5 | `test_l11_fake_provider.py`；`personal.spec.ts`「供应商拒绝密钥」；`h02.test.ts` 超时与预算文案；后端 `test_d3.py`、`test_e12.py`（N02）保留在 full |

## 5. 验证纪律

- **每个任务**：跑该任务的测试文件、相邻的既有测试文件，以及基础档 `./scripts/verify.sh`。
- **每个阶段**（L11、L13、L15 结束时）：跑 `./scripts/verify.sh integration`（包含 full）。端到端包括现有两个演示用例和新增的 `personal.spec.ts`。
- **环境**：用本工作区克隆的 `.venv`、`node_modules`、`src/frontend/node_modules`；SQLite 隔离；Neo4j 用一次性容器（集成档用 17689，端到端用 17688），**不连**冲刺环境的 7688。
- **报告**：PASS、SKIP（逐项写原因）、FAIL 分列；环境限制与业务失败分开写；未验证的范围单列。
- **真实模型**：另表记录，注明模型、日期、资料规模、计时边界、调用数与 usage，并更新累计台账；不拿缓存或演示结果冒充真实指标。

## 6. 回滚与数据兼容

- **L12**：契约字段是可选的，旧客户端可以忽略；回滚即回退 L12 的提交并重新生成 DTO。没有迁移，不涉及 Neo4j。
- **L13、L14**：纯前端，回退对应提交即可。
- **L11-1**：新增资料与脚本，回退不影响已有数据。
- **L11-2、L11-3**：只影响测试工具，回退后端到端回到演示模式。
- **数据**：本计划不新增迁移。若实施中发现必须加迁移，先补 ADR 和回滚步骤，再提交给用户决定。

## 7. 预算台账

- 当前累计：140230 / 5000000 token。
- 计划内的真实调用：L11-6 预计 25～45 万 token；L15-6 Step 4 预计 4～8 万 token。合计约 30～53 万，执行后累计约 44～67 万 / 500 万。
- 每次运行前核对最新累计，运行后在 `docs/handoffs/claude-l11.md`、`claude-l15.md` 登记。共享向量用量现在按 ADR-082 决定 6 写入 `model_calls`（`purpose=embedding`），单独列出，不计入生成模型预算。

## 8. 完成后交给 Codex 的内容

- 固定 base：`d766f40`；head：L15-6 的提交。
- 证据：各子任务的 red/green 记录；阶段门禁日志路径；`personal.spec.ts` 的 trace 与截图目录；真实模型报告。
- 交接文件：`docs/handoffs/claude-l11.md` 至 `claude-l15.md`（每项包含交付物、验证、接口/数据变更、风险、下一步）。

## 9. 交给 L16 的清单（本计划只采集，不优化）

- 抽取分段耗时：排队、解析、分块、实体、关系、融合、入库，从 `processing_tasks` 时间戳和 `model_calls` 汇总。
- 每份资料的调用数、输入/输出 usage，以及向量调用数。
- 未经修改的原始 AI 输出快照（在发布和教师修正之前导出），供人工判定实体与关系准确率。
- 问答：完整耗时、首字耗时、结局分布（answered、not_covered、truncated、timeout），以及引用是否指向正确资料。
- 已知差距：历史抽取 141.72 秒，未达 60 秒；当前链路准确率尚无人工判定；`ANSWER_MAX_OUTPUT_TOKENS = 1024` 会让长的比较类回答被判截断。

## 10. 不在本计划内（只留接口与证据清单）

- L16：性能优化与准确率报告。
- L17：轻量美化（两条闭环验收后才开始）。
- L18：README、运行手册、九类材料。本计划各任务的截图与 trace 放在 `.e2e/` 与 `evaluation/reports/`，供 L18 取用。
- L19：冻结、干净环境复测与录像，预留时间缓冲。

## 11. 自查：规格覆盖缺口

- 设计 §6 的「模式标识（R01/R02）」已在计划 A 完成，本计划只在端到端里验收。
- R05（已有 AI 模块未完整接入默认 worker 链路）按设计只如实记录，本计划不接入补漏或融合。
- R12（文档与任务状态反映交付状态）属于 L18。每个子任务完成时同步更新任务板，作为过程证据。
- 赛题「九类材料」不在本计划；「60 秒 / 15 秒 / 70%」列为待实测指标，不承诺达标。
