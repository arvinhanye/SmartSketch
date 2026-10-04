# C04 人工准确率签收入口（C-ACC-C，2026-10-04）

> **状态：用户已签收（2026-10-04，判定人 `arvin`），见第 5 节。** 本目录里的 `claude-assist` 判定是 Claude 的辅助参考，**不是人工验收，不能据此宣布准确率达标**。赛题硬指标以用户本人逐条判定为准（`evaluation/README.md` §6）。

## 1. 签收对象

计划 C 真实测量（DeepSeek，`deepseek-flash`，关闭思考，PDF 按二级标题分节）的两份草稿，全量检查（总体 ≤ 100，不抽样），种子 `20260926`。

| 课程 | run_id | 实体 | 关系 |
| --- | --- | ---: | ---: |
| course1（数据结构第 3 章） | `contest-course1-ds-ch3-pdf-headings2-thinking-off-2db2aff95ca2` | 76 | 61 |
| course2（操作系统第 2 章） | `contest-course2-os-ch2-pdf-headings2-thinking-off-9c6b8ce343b1` | 68 | 58 |

章节原文：`datasets/contest/course1-ds-ch3/ch3-stack-queue.md`、`datasets/contest/course2-os-ch2/ch2-process-thread.md`。

## 2. 文件

| 文件 | 说明 |
| --- | --- |
| `*-predictions.json`、`*-worksheet.md` | 原始预测与工作表，从测量区 `smartsketch-c03b-measure`（`88f9f6f`）的 `evaluation/raw/c04/` 原样复制，**未改动** |
| `*-judgments-user.json` | **已完成的用户签收记录**：`judge=arvin`，263 条判定已填；逐条复核后采纳辅助判定，非独立盲判（见 §5） |
| `*-worksheet-user.md` | **推荐的填写处**：工作表副本，填 ✓ / ✗ 后由 `evaluation/c04_signoff.py convert` 转成 `*-judgments-user.json` 与 `*-report-user.json` |
| `*-judgments-claude-assist.json` | Claude 辅助判定：`judge` 以 `claude-assist` 开头，`is_human_judgment: false`；每条都有依据（`notes`，判错写明 E/R 编号），存疑项列在 `needs_review` |

原始文件 SHA-256（与测量区逐字节一致）：

| 文件 | SHA-256 前 16 位 |
| --- | --- |
| `course1-pdf-h2-thinking-off-predictions.json` | `a94bb86cca66a4ca` |
| `course1-pdf-h2-thinking-off-worksheet.md` | `16a086202c6ebd3f` |
| `course2-pdf-h2-thinking-off-predictions.json` | `50fa5348ae0c24bd` |
| `course2-pdf-h2-thinking-off-worksheet.md` | `f11ebc136d8f22fd` |

## 3. 用户怎么签收

### 推荐：在工作表副本里填 ✓ / ✗

副本 `course1-pdf-h2-thinking-off-worksheet-user.md`、`course2-pdf-h2-thinking-off-worksheet-user.md` 已由用户填完。除「判定人」元信息、最后两列与新增说明外，数据列与原工作表相同。原工作表不动，作为证据。以下是填写流程说明，不是要求重做现有签收。

1. 在副本的 `- 判定人：` 后填你的名字（不能以 `claude-assist` 开头）。
2. 对照章节原文，按 `evaluation/README.md` §6.3 逐行填最后两列：
   - 「判定」填 `✓`（对）或 `✗`（错），也认 `√ ✔` 与 `× ✘`；
   - 判 `✗` 时「依据」必须写理由，最好带编号，如 `E3：应为 concept`、`R5：证据不支持`；
   - 只改这两列，单元格里不要用 `|`。
3. 转换并计算（可以随时运行，用来看还剩哪些没填）：

   ```bash
   .venv/bin/python evaluation/c04_signoff.py convert
   ```

   - 有没填、标记不认识、判 ✗ 没写依据、判定人不合格，或改动了其他列，以及重复行号 / ID、非七列数据行都会拒绝；**所选课程全部预检通过前，不写任何结果文件**；
   - 全部合格时写 `*-judgments-user.json`（覆盖该课程既有判定结果；请先备份）和 `*-report-user.json`，并打印两课的实体、关系准确率与结论；
   - 只转一门：加 `--course course1` 或 `--course course2`。

预检零写入只覆盖校验失败；通过校验后的磁盘写入并非跨文件事务，I/O 故障可能留下部分输出。已签收证据不应随意重转或覆盖。当前修复说明与最新阶段状态见 `docs/handoffs/codex-plan-c-acceptance-fixes.md`；Claude 交接 §3C / §6 的初始待签收措辞保留为历史，不作当前状态。

副本被误删时可用 `.venv/bin/python evaluation/c04_signoff.py init` 重新生成；已存在的副本不会被覆盖。

### 也可以直接编辑 JSON

1. 对照章节原文和工作表，按 `evaluation/README.md` §6.3（实体 E1～E5、关系 R1～R6）逐条判定，填进 `*-judgments-user.json`：
   - `judge` 填本人姓名，**不得**以 `claude-assist` 开头；
   - 每条填 `correct` 或 `incorrect`，判错在 `notes` 写明编号。
   - 可以参考辅助文件的依据，但每条须本人判断。未填完时 `judge-report` 会直接拒绝计算（`null` 不是合法判定），不会得出半截结论。
2. 计算硬指标：

   ```bash
   D=evaluation/raw/c04-signoff
   for s in course1 course2; do
     PYTHONPATH=src/backend .venv/bin/python evaluation/evaluate_extraction.py judge-report \
       --predictions $D/$s-pdf-h2-thinking-off-predictions.json \
       --judgments $D/$s-pdf-h2-thinking-off-judgments-user.json \
       --out $D/$s-pdf-h2-thinking-off-report-user.json
   done
   ```

   报告里 `is_human_judgment` 为 `true` 才算人工结论；任一准确率 < 70% 照实写「未达标」，不得换种子、放宽标准或剔除样本（§6.5）。
3. 对比本人判定与辅助判定的分歧（只读）：

   ```bash
   D=evaluation/raw/c04-signoff
   for s in course1 course2; do .venv/bin/python - "$D/$s-pdf-h2-thinking-off-judgments-user.json" \
     "$D/$s-pdf-h2-thinking-off-judgments-claude-assist.json" <<'PY'
   import json, sys
   u, a = (json.load(open(p, encoding="utf-8")) for p in sys.argv[1:])
   for kind in ("entities", "relations"):
       for i, v in u[kind].items():
           if v != a[kind][i]:
               print(kind, i, "user:", v, "assist:", a[kind][i], "|", a["notes"][i])
   PY
   done
   ```

## 4. 辅助判定的参考数（非人工验收）

由 `judge-report` 按辅助文件计算，报告标注「Claude 辅助判定（非人工验收）」。这里只列数字，**不作为达标结论**。

| 课程 | 实体判对 | 关系判对 | 存疑项 |
| --- | --- | --- | ---: |
| course1 | 64 / 76（84.21%） | 58 / 61（95.08%） | 7 |
| course2 | 61 / 68（89.71%） | 45 / 58（77.59%） | 6 |

- **course2 关系离 70% 只差 5 条**：45 → 40 即降到 68.97%。签收时请重点看该课关系，尤其 `needs_review` 里的两可项。
- 主要错误类型（辅助判定）：
  - course1 实体：类型（「后进先出」「先进先出」按 §3.1 应为 concept；复杂度结论标成 formula）、融合遗漏的重复（「栈/队列的应用」各出现 2～3 条）、章标题与导读概述混入。
  - course2 实体：小结里的目录式条目（「进程定义」「常见调度算法」「进程的创建与撤销」，定义为「本章介绍的内容」之类元描述）、两个知识点拼成一条（「创建态与终止态」）。
  - course2 关系：把本章小结的**叙述顺序或并列列举**抽成 `CONTAINS`（如「进程定义 → 进程切换」，共 8 条），以及证据不支持（「先来先服务 → 饥饿」「撤销进程 → 进程标识符」）。
- 判定规则的字面适用（请用户裁定）：E5 只在「另一条已判对」时才把后出现者判错。所以 course1「后进先出」（#3）因类型判错后，同义的「栈的后进先出特性」（#11）不触发重复，辅助判定按字面判对，已标存疑。

复现辅助数字（输出写到临时目录，不入库）：

```bash
D=evaluation/raw/c04-signoff
PYTHONPATH=src/backend .venv/bin/python evaluation/evaluate_extraction.py judge-report \
  --predictions $D/course2-pdf-h2-thinking-off-predictions.json \
  --judgments $D/course2-pdf-h2-thinking-off-judgments-claude-assist.json
```

## 5. 签收结果（2026-10-04）

用户 `arvin` 于 2026-10-04 在本机签收网页逐条复核两课全部 263 条（course1 76 实体 + 61 关系，course2 68 实体 + 58 关系），**采纳 Claude 辅助判定**：263/263 判定一致；35 条 ✗ 的依据中 30 条沿用辅助原文，5 条仅删去【请复核】标记。按用户确认如实记为「复核后采纳辅助判定」，不是独立盲判。

| 课程 | 实体 | 关系 | 实体数 | 结论 |
| --- | --- | --- | ---: | --- |
| course1 | 64 / 76（84.21%） | 58 / 61（95.08%） | 76 | 达标 |
| course2 | 61 / 68（89.71%） | 45 / 58（77.59%） | 68 | 达标 |

- 文件：`*-worksheet-user.md`（判定原件）、`*-judgments-user.json`、`*-report-user.json`（`is_human_judgment: true`）。
- 核对：判定 JSON 与工作表逐条一致；报告可由判定重算得到；原 predictions、工作表与辅助文件未改。
- 风险：course2 关系只比 70% 多 5 条；删去【请复核】的 5 条正是两可项（course1 #37、#42、#68、#70，course2 关系 #20），若评审改判，结论可能翻转。
