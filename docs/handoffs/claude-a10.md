# A10：整理已有成果导入顺序与任务映射

- **task_id**：A10（`docs/atomic-task-plan.md` / `docs/atomic-tasks.json`）
- **状态**：DONE。第 2 节的决定（PLAN-D04a～d、S03-1、N1～N5、ID-1～4）由 ArvinHan 于 2026-09-23 按「建议」一栏全部签收，记为 **ADR-016**，关闭 PLAN-D04；PLAN-D05 只是引用，仍待产品负责人
- **review_status**：ready_for_review（以交付提交为准，提交前不生效）
- **worktree / 分支**：`.claude/worktrees/quirky-dijkstra-eca5de`，分支 `claude/a10-integration-map`，base `6881ffe`（= 合入 PR #13 后的 `origin/main`）
- **head_commit**：随交付提交入库（`git log -1 -- docs/handoffs/claude-a10.md` 可查）
- **类型**：仅文档任务。没有合并、提交或改动任何其他分支与 worktree；所有试跑都在临时副本中进行

## 一、范围与交付物

| 文件 | 内容 |
| --- | --- |
| `docs/reviews/branch-integration-map.md`（新建） | 结论、15 项待签收决定、批 0～6、92 个文件逐一处置、分支任务编号去向、原子清单缺口、风险、核对证据 |
| `docs/tasks.md` | A10 认领行（插在 A05 一节之后，避开 PR #16 在文件末尾追加的位置）；PLAN-D04 行关闭；「待确认决策」新增 D-08 |
| `docs/decisions.md` | **范围扩展**：新增 ADR-016（AGENTS.md §6 要求已确认选择入 ADR，同 A02 的先例）；ADR-004「需要人拍板」第 2 条加一处指针 |
| `docs/handoffs/claude-a10.md` | 本文件 |

A10 的白名单只有任务板与映射文件。除了记录签收结果的 ADR-016，所有需要改规格、ADR 正文、清单或脚本的事项都写成批次，由各批的执行人完成。

## 二、输入与核对依据

- 两个 worktree 的成果：`740adb` @ `978671e` 已完整包含 `ff30e0` @ `6ccbe5e` 与 `209be9` @ `bef9b91`，因此只需比对 `740adb` 相对共同基线 `05d214c` 的 92 个文件。
- main 的已签收决定：ADR-004、009～014，以及 A02～A07 的交接中「交 A10」的移交项（文本块标签统一、ADR-005/006 加注、`not_covered_reason`、`.env.example` 分段归属、`event_tickets` 入命名基线、重新向量化命令补登、A05 清单缺口）。这些移交项在映射中都有落点。
- 在途工作：PR #14（B05）、#15（B01）、#16（FIX-R01/R02），以及 Codex A08 未提交的 `specs/learning-path.md`。
- 仓库外：S2 方案 docx（只读转文本），用来核对截止日期。

## 三、主要发现

1. **建议 main 为基线、按批检出文件**，不做整枝合并：main 与 `740adb` 双方都改过的文件有 10 个，而且 `740adb` 带着已被 main 否决或取代的内容。
2. **钩子方向相反**：`209be9` 的 `block-dangerous.sh` 刻意设计成解析失败即放行，main 的 HOOK-01 验收要求无法解析即拒绝，因此不导入。
3. **契约批次不能原样搬入**：`740adb` 副本补齐生成物后门禁 exit 0；叠到 main 副本上 exit 1。原因有三：`SourceChunk` 未统一；说明行被误判为违规；测试夹具要求 A08、A09 的两份规格。修法写在批 1。
4. **命名冲突 5 处**（N1～N5），另有 wire 契约的 `document_id` 与 A04 规格的 `material_id` 不一致。
5. **编号冲突**：S-06 重号、M0-06 重号、M1-05 含义不同、分支 D-04～D-08 与 main 编号体系不同（ID-1～4）。
6. **进度**：S2 §4.2 写明提交截止为 10-08，main 任务板没有记录；今天处在 M1 窗口，main 尚无运行时代码。
7. **清单缺口**：G-1～G-6，其中参赛材料与合规（G-4）完全没有承接任务。

## 四、实际运行的命令与结果

```text
git merge-base --is-ancestor <ff30e0|209be9> 740adb           两者均包含
python3 survey_a10.py > a10_survey.tsv（附录 A）              92 行；重跑输出与首跑逐字节一致
python3 gen_filemap.py a10_survey.tsv（附录 B）               92/92 有处置；导入 56，待决 13，不导入 12，随任务导入 6，逐段合并 3，部分导入 2
740adb 副本 ./scripts/verify.sh                               exit 1（缺 python/、typescript/ 生成物）
740adb 副本 gen-contracts.sh 后 --check / verify.sh           exit 0 / exit 0（21 项负向测试通过）
main 副本 + 批 1 文件，生成后 scripts/verify/contracts.sh      exit 1：命名 6 处；负向测试 4/21
ADR-001～003 分支正文与 main 去空白比较                       一致
python3 check_a10.py .（附录 C）                              首跑 2 FAIL（均为脚本问题，见下）；修正后 ALL PASS
python3 neg_a10.py . <scratch>（附录 D）                      8 个篡改副本全部 exit 1，各只命中目标断言
./scripts/verify.sh                                           exit 0
git diff --check                                              exit 0
python3 docs/reviews/validate_atomic_plan.py                  exit 0（脚本写死主目录路径，校验的是主目录的清单；本任务未改清单）
```

- 自查修正：初稿建议「批 2～4 可以并行」，但批 1、3、4 都改 `docs/architecture.md` 模块表中相邻的几行，同时开 PR 会冲突，已改为依次合入；逐文件表同步写明模块表 contracts 行归批 1。修正后第 4 节与生成脚本输出逐行一致。
- `check_a10.py` 首跑的 2 项失败都是脚本的问题：合计一行用中文逗号分隔，正则把「，待决」当成了键名；S-06 改号检查取错了列（取成了「签收人」，应为「建议」）。修正后通过，映射文件没有因此改动。
- 试跑的环境注意：生成器 `datamodel-codegen` 在独立 venv，门禁依赖（`jsonschema`、`openapi-spec-validator`）在 conda 的 `python3`。把整个 venv 放到 PATH 前面会让门禁换用 venv 的解释器，从而报缺依赖；只把 `datamodel-codegen` 一个命令加进 PATH 即可。批 1 已写明。

## 五、接口 / 数据 / 配置变更

无实现变更。ADR-016 已签收改名（`Chunk`、`Document`、`model_calls`、`GraphVersion`），但现行文档要等批 1、批 5 才改；在此之前新写的文档与代码按 ADR-016 命名。

## 六、未完成 / 风险

- 决定已签收，批次可按 ADR-016 决定 4 的顺序开始：批 0 → 1 → 3 → 4 → 5 → 6，批 2 并行；批 4 另需 B05 合入；批 1、3、4 都改架构模块表与 README 目录树，须依次合入。
- Codex 的 B01/B05 在途，批 4 须等 B05 合入；映射按 PR 当前内容写成，若 PR 变动需复核重叠的 3 个文件。
- 在 A08、A09 合入之前，批 1 的命名扫描不含两份规格，门禁因此变弱；须在它们合入时加回，并用负例证明。
- 在批 1、批 5 执行前，现行文档中的 `SourceChunk`、`Material`、`material_id` 与 ADR-016 决定 6 不一致。

## 七、下一位 Agent 的首个动作

1. 协调 Agent 执行批 0，第一件事是按 ADR-004 映射改写 B08～B14、O02、O05 的文件白名单，并为缺口 G-1～G-6 补登编号。
2. 批 0 合入后，后端 Agent 执行批 1（N1 已签收）。
3. 批 2 可由 F01 随时认领执行。
4. 请 Codex 审查本 PR 的映射与 ADR-016。

## 八、回滚

删除 `docs/reviews/branch-integration-map.md`、本文件与 `docs/decisions.md` 末尾的 ADR-016，定向恢复 ADR-004 的指针一行，以及 `docs/tasks.md` 中的 A10 一节、PLAN-D04 行与 D-08 行。不涉及迁移、依赖或其他分支。

## 九、签收与编号

- ArvinHan 于 2026-09-23 在会话中回复「按建议全部签收」，覆盖第 2 节 PLAN-D04a～d、S03-1、N1～N5、ID-1～4 的「建议」一栏。
- ADR 编号取 **016**：另一个会话在 `.claude/worktrees/a09-dev-environment-check-8e5e93` 的 `claude-a09-env-check.md`（未提交）中已计划 A09 使用 ADR-015。把 015 留给它，避免撞号；做法同 A04 避开 A03 改用 012。已核对全部本地与远端分支，均未使用 ADR-015、ADR-016。

## 十、第二轮：Codex 审查修复（A10-R01 / A10-R02）

- **task_id**：A10-R01/R02 修复（Codex REVIEW-13），A1～A10 收尾的一部分
- **状态**：DONE；ADR-016 修订 1 **待 ArvinHan 签收**（按审查的最小修复建议落实，不改变决定 1～6 的方向）
- **review_status**：ready_for_review（以交付提交为准）
- **worktree / 分支**：`.claude/worktrees/wrap-a10-fix`，分支 `claude/a10-r01-r02-fix`，base `37da669`（PR #18 的头）。另开 PR 而不改 #18，因为 PR #22（批 0、批 1）叠在 #18 之上
- **审查报告**：主目录 `docs/reviews/codex-claude-a10-37da669-2026-09-23-1403z.md`（尚未入库）

| 问题 | 修改 |
| --- | --- |
| **A10-R01**（P2）批 1 把已合入的 `learning-path.md` 移出命名门禁 | 第 3 节批 1 第 ④ 项改为按执行时 main 中实际存在的规格确定扫描集合：`learning-path.md` 保留，`grounded-qa.md` 待 A09 合入后加回，每份加回都用错误命名负例证明；第 7 节风险 2、6 同步。PR #22 的 `scripts/check_contracts.py` 已含 `learning-path.md`，实际门禁未受影响，本修复让映射与之一致 |
| **A10-R02**（P2）批 5 拟原样导入与现行状态机相反的 ADR-005/006 | 批 5 与第 4 节两行改为以 **SUPERSEDED** 历史记录导入：首段与索引写明被 ADR-010/011 取代（成环失败另见 ADR-009），不得作现行依据，现行规范为 `specs/task-processing.md`；逐行写明各自与现行规范相反的条文 |

`docs/decisions.md` 在 ADR-016 之后新增「ADR-016 修订 1」；任务板追加一节，并登记「批 1 补」（A09 合入后加回 `grounded-qa.md`）。

**验证**（本 worktree，脚本在会话草稿区，未入库）：

```text
python3 check_a10r.py .（修改前）       10 FAIL / exit 1
python3 check_a10r.py .（修改后）       ALL PASS / exit 0
python3 neg_a10r.py . <scratch>        5 个篡改副本全部 exit 1，各自命中目标断言
python3 check_a10.py .（附录 C 原脚本）  修改前、后均 ALL PASS（92 个文件逐行、批次单一边界、签收人等原有断言未被破坏）
./scripts/verify.sh                     exit 0
git diff --check                        exit 0
```

**合并**：本 PR 含 #18 的提交，应在 #18 之后合入；与 #22 只在 `docs/tasks.md` 文末有文本冲突（#22 相对 #18 只改了该文件），保留双方即可。

## 附录 A：`survey_a10.py`（文件普查）

用法：在仓库根目录运行：`python3 survey_a10.py > a10_survey.tsv`。

```python
"""A10 文件普查：survey_a10.py > a10_survey.tsv（在仓库根目录运行）。
每行：状态 \t 路径 \t 来源分支 \t main 是否改过 \t main 是否有 \t 与在途 PR 重叠。"""
import subprocess
def g(*a): return subprocess.run(["git", *a], capture_output=True, text=True).stdout
B = "claude/worktree-contract-conflicts-740adb"; base = "05d214c"; main = "origin/main"
short = {"831b6dd":"209be9","7761c90":"209be9","07285ca":"209be9","39560b7":"209be9","efecd8b":"209be9","bef9b91":"209be9",
         "9f3a1d7":"ff30e0","6ccbe5e":"ff30e0","2fbf325":"740adb-merge","1bc63ad":"740adb","8865686":"740adb","978671e":"740adb"}
main_changed = set(g("diff","--name-only","-z",base,main).split("\0"))
main_files = set(g("ls-tree","-r","-z","--name-only",main).split("\0"))
pr = {}
for ref in ("origin/codex/b01-vue-scaffold","origin/codex/b05-fastapi-health-github"):
    for f in g("diff","--name-only","-z",main+"..."+ref).split("\0"):
        if f: pr.setdefault(f, []).append(ref.split("/")[2][:3])
lines = [l for l in g("diff","--name-status","-z",base,B).split("\0") if l]
it = iter(lines)
for st in it:
    f = next(it)
    commits = g("log","--format=%h",base+".."+B,"--",f).split()
    origins = sorted({short.get(c, c) for c in commits})
    print("\t".join([st, f, ",".join(origins), "main改" if f in main_changed else "-", "main有" if f in main_files else "main无", ",".join(pr.get(f, []))]))
```

## 附录 B：`gen_filemap.py`（逐文件处置表生成）

用法：`python3 gen_filemap.py a10_survey.tsv`；任一文件没有匹配规则即退出。

```python
"""由 a10_survey.tsv 生成逐文件映射表：gen_filemap.py <survey.tsv>。每个文件必须有且只有一条处置。"""
import sys
from collections import Counter
from pathlib import Path

# 处置：导入 / 部分导入 / 逐段合并 / 随任务导入 / 待决 / 不导入
RULES = [
    # (前缀或完整路径, 处置, 批次或任务, 备注)
    (".claude/hooks/block-dangerous.sh", "不导入", "—", "main 的 HOOK-01 已取代；209be9 版解析失败即放行，与 HOOK-01 验收「无法解析即拒绝」相反。其「按命令位置匹配」可另立任务"),
    (".env.example", "部分导入", "批 2（F01）", "只取 `STORAGE_DIR`、`NEO4J_DATABASE` 与 Neo4j 容器 5 项；模型、预算、任务段以 main 为准（A07 已定）"),
    (".gitignore", "导入", "批 3", "datasets/raw、evaluation/reports、`*.pdf/*.docx/*.pptx` 忽略规则；main 自基线未改此文件"),
    ("AGENTS.md", "待决", "S03-1 → 批 5；角色路径 → 批 3", "写争用规则与任务板/ADR 路径随 S03-1；「分支与合并（提案）」由 PLAN-D04 签收结果取代"),
    ("CLAUDE.md", "待决", "S03-1 → 批 5", "只有一行随 S03-1 的 ADR 路径改动"),
    ("NOTICE", "导入", "批 3", "声明「尚未复制第三方源码」，给日后借用留登记位置"),
    ("README.md", "逐段合并", "批 3、批 4", "目录树只写实际已导入的目录；main 自基线只加了 2 行"),
    ("datasets/", "导入", "批 3", "K01 的输入；只放标注元数据，原始资料被忽略"),
    ("docker-compose.yml", "随任务导入", "批 2（F01）", "M0-05 当时 BLOCKED：APOC 未实测"),
    ("docs/architecture.md", "逐段合并", "批 1、3、4、5", "模块表 contracts 行与契约质量边界 → 批 1；prompts/evaluation 行 → 批 3；schemas 职责 → 批 4（三批改同一张表，须依次合入）；核心数据模型 → 批 5 按 N1～N5；状态机一行不导入（A03 已取代）"),
    ("docs/decisions.md", "待决", "S03-1 → 批 5", "分支上是「删除并拆目录」；拆分文件须以 main 已签收正文重建"),
    ("docs/decisions/ADR-001", "导入", "批 5", "正文与 main 一致（已逐字比对）"),
    ("docs/decisions/ADR-002", "导入", "批 5", "正文与 main 一致（已逐字比对）"),
    ("docs/decisions/ADR-003", "导入", "批 5", "正文与 main 一致（已逐字比对）"),
    ("docs/decisions/ADR-004", "不导入", "批 5 以 main 重建", "分支版是 740adb 的改判稿；main 的 A01 签收版更完整，以它为准"),
    ("docs/decisions/ADR-005", "导入", "批 5", "无签收行；文首加注指向 ADR-009（成环失败收窄）、ADR-010、ADR-011，不改原文"),
    ("docs/decisions/ADR-006", "导入", "批 5", "无签收行；结论已由 ADR-010 复核维持；文首加注指向 ADR-010、ADR-011"),
    ("docs/decisions/ADR-007", "待决", "PLAN-D05 → 批 6", "无签收行；学习材料加分项范围未拍板"),
    ("docs/decisions/ADR-008", "导入", "批 5", "须同时写入 N1～N5 命名对齐修订；否则与 ADR-011/012 已签收名称冲突"),
    ("docs/decisions/README.md", "导入", "批 5", "索引按 main 实际编号 001～014 重建"),
    ("docs/handoffs/claude-s01-", "导入", "批 1", "历史交接，随其成果入库，不改正文"),
    ("docs/handoffs/claude-s07-", "导入", "批 1", "同上"),
    ("docs/handoffs/claude-m0-04-", "导入", "批 1", "同上"),
    ("docs/handoffs/claude-m0-05-", "导入", "批 2", "同上"),
    ("docs/handoffs/claude-s04-", "导入", "批 3", "同上"),
    ("docs/handoffs/claude-m0-06-", "导入", "批 5", "同上；其中 M0-08 部分对应批 3"),
    ("docs/handoffs/claude-s03-", "导入", "批 5", "同上"),
    ("docs/handoffs/claude-s05-", "导入", "批 5", "只作记录：其钩子重写不导入"),
    ("docs/handoffs/claude-s06-scope", "导入", "批 6", "同上"),
    ("docs/handoffs/claude-s06-specs", "导入", "批 6", "任务号改记 S-08（ID-1）；文首加注，不改正文"),
    ("docs/integrations.md", "部分导入", "批 2（F01）", "「本地依赖环境」各节与存储、Neo4j 容器变量行；模型接入规则以 main 为准"),
    ("docs/product.md", "待决", "PLAN-D05 → 批 6", "学习材料、目标路径、多课程、性能指标属范围决定；学习材料行在分支上重复出现两次，需去重"),
    ("docs/references.md", "导入", "批 3", "把仓库与 S2 方案等仓库外权威文档挂钩"),
    ("docs/references/", "导入", "批 3", "团队自撰笔记；入库前去掉本机绝对路径（合规去标识化）"),
    ("docs/tasks.md", "不导入", "—", "分支把任务板拆成 M0～M4 文件，与 main 现行单文件任务板结构冲突；内容映射见第 5 节"),
    ("docs/tasks/open-questions.md", "不导入", "批 6 取 D-01 清单", "D-04→PLAN-D04、D-07→PLAN-D05、D-08 新增到 main；D-05、D-06 退役（ID-4）"),
    ("docs/tasks/", "不导入", "—", "被原子清单取代；未覆盖的 M3-02、M4-02～07 列入第 6 节缺口"),
    ("evaluation/", "导入", "批 3", "K01 的输入"),
    ("prompts/", "导入", "批 3", "E01 的输入"),
    ("scripts/_dev-common.sh", "随任务导入", "批 2（K07）", "先审后用（K07 验收：普通停止保留数据、删卷须确认）"),
    ("scripts/dev-down.sh", "随任务导入", "批 2（K07）", "同上"),
    ("scripts/dev-up.sh", "随任务导入", "批 2（F01、K07）", "同上"),
    ("scripts/check-apoc.sh", "随任务导入", "批 2（F01）", "APOC 实测是 F01 验收项"),
    ("scripts/check_contracts.py", "导入", "批 1", "需两处调整（见批 1）：命名扫描误报「不得使用」说明行；扫描清单含 main 尚无的两份规格"),
    ("scripts/gen-contracts.sh", "导入", "批 1", "`978671e` 已含 S07-R06 修复"),
    ("scripts/gen_contracts.py", "导入", "批 1", ""),
    ("scripts/verify.sh", "待决", "S03-1 → B07/K11", "分发器与 main 的 HOOK-01 回归测试一行冲突；批 1 只在 main 版加一行调用契约门禁"),
    ("scripts/verify/contracts.sh", "导入", "批 1", "生成物补齐后删去 `--allow-scaffold`"),
    ("scripts/verify/backend.sh", "待决", "S03-1 → B07/K11", "B05 合入后此脚本打印占位并 exit 0，是假绿，不能原样导入"),
    ("scripts/verify/", "待决", "S03-1 → B07/K11", "分发器的子脚本与必需文件清单"),
    ("specs/course-knowledge-graph.md", "逐段合并", "批 5、批 6", "节点字段 → 批 5；验收 7～10、关联任务 → 批 6（PLAN-D05）；验收 2 状态机不导入（A03 已改）"),
    ("specs/grounded-qa.md", "随任务导入", "A09", "作 A09 底稿（同 A04 以分支桩为底稿的做法）"),
    ("specs/learning-path.md", "不导入", "—", "A08（Codex，进行中）的新规格取代此桩"),
    ("specs/teacher-review-publish.md", "不导入", "—", "A04 已以此桩为底稿重写并签收"),
    ("src/backend/app/api/__init__.py", "不导入", "—", "Codex B05（PR #14）已新建同名文件"),
    ("src/backend/app/", "导入", "批 4", "须在 B05 合入之后"),
    ("src/contracts/README.md", "导入", "批 1", "`not_covered_reason` 改为 `reason`（A02 移交）"),
    ("src/contracts/v1/generated/", "导入", "批 1", "不取分支里不完整的 4 个文件，按真源重新生成（含 python/、typescript/）"),
    ("src/contracts/", "导入", "批 1", "ADR-004 真源及配套文档"),
    ("tests/contracts/", "导入", "批 1", "21 项门禁负向测试；夹具清单同 check_contracts 调整"),
    ("tests/", "导入", "批 4", "目录说明"),
]

def rule(path):
    for pre, *rest in RULES:
        if path == pre or path.startswith(pre):
            return rest
    raise SystemExit(f"无处置：{path}")

rows, counts = [], Counter()
for line in Path(sys.argv[1]).read_text(encoding="utf-8").splitlines():
    st, path, origin, main_changed, main_has, pr = line.split("\t")
    disp, where, note = rule(path)
    counts[disp] += 1
    main_state = {"main改": "main 也改过", "-": "main 未改" if main_has == "main有" else "main 无"}[main_changed]
    if pr:
        main_state += f"；与 PR {'/'.join('#15' if p == 'b01' else '#14' for p in pr.split(','))} 重叠"
    rows.append(f"| `{path}` | {st} | {origin} | {main_state} | {disp} | {where} | {note} |")
print("| 文件 | 状态 | 来源 | main 现状 | 处置 | 批次/任务 | 说明 |")
print("| --- | --- | --- | --- | --- | --- | --- |")
print("\n".join(rows))
print()
print("合计 " + str(sum(counts.values())) + " 个文件：" + "，".join(f"{k} {v}" for k, v in counts.most_common()) + "。")
```

## 附录 C：`check_a10.py`（A10 核对）

用法：`python3 check_a10.py <仓库根目录> [<映射文件>]`。

```python
"""A10 核对：check_a10.py <repo_root> [<map.md 路径>]；任一 FAIL 则 exit 1。

对照 A10 验收：不自动 merge；明确 ADR/S-06 编号冲突；每批最多一个功能边界；决策签收人。
另查：92 个文件逐一有且只有一行、处置取值合法、引用的批次/决定/原子任务都有定义、摘要数字与表一致。
"""
import json, re, subprocess, sys
from collections import Counter
from pathlib import Path

root = Path(sys.argv[1])
mp = Path(sys.argv[2]) if len(sys.argv) > 2 else root / "docs/reviews/branch-integration-map.md"
t = mp.read_text(encoding="utf-8")
fails = []
def ok(c, m):
    print(("PASS " if c else "FAIL ") + m)
    if not c: fails.append(m)
def sec(n):
    m = re.search(rf"^## {n} .*?$(.*?)(?=^## \d |\Z)", t, re.M | re.S)
    return m.group(1) if m else ""
def rows(s):
    return [[c.strip() for c in l.strip().strip("|").split(" | ")] for l in s.splitlines()
            if l.startswith("| ") and not l.startswith("| ---")][1:]

# 1. 文件全覆盖
files = subprocess.run(["git", "-C", str(root), "diff", "--name-only", "-z", "05d214c", "978671e"],
                       capture_output=True, text=True).stdout.split("\0")
files = [f for f in files if f]
fr = rows(sec(4))
listed = [r[0].strip("`") for r in fr]
ok(len(files) == 92, f"来源 diff 为 92 个文件（实际 {len(files)}）")
ok(Counter(listed) == Counter(files), f"第 4 节逐文件一行、不多不少（表 {len(listed)} 行）")
DISP = {"导入", "部分导入", "逐段合并", "随任务导入", "待决", "不导入"}
ok(all(r[4] in DISP for r in fr), "处置取值合法")
ok(all(r[5] for r in fr), "每行有批次/任务去向")
cnt = Counter(r[4] for r in fr)
m = re.search(r"合计 (\d+) 个文件：(.+?)。", sec(4))
claimed = dict((k, int(v)) for k, v in (x.rsplit(" ", 1) for x in m.group(2).split("，"))) if m else {}  # 中文逗号分隔
ok(bool(m) and int(m.group(1)) == len(fr) and claimed == dict(cnt), "第 4 节合计与表一致")
s1 = sec(1)
ok(all(f"{k} {v}" in s1 for k, v in cnt.items()), "第 1 节摘要数字与表一致")

# 2. 决定：编号定义、签收人、未签收声明
dr = rows(sec(2))
dec_ids = {re.sub(r"\*", "", r[0]) for r in dr}
ok(all(r[4] for r in dr), f"第 2 节每个决定都有签收人（{len(dr)} 项）")
for need in ("PLAN-D04a", "PLAN-D04b", "PLAN-D04c", "PLAN-D04d", "S03-1", "N1", "N2", "N3", "N4", "N5",
             "ID-1", "ID-2", "ID-3", "ID-4", "PLAN-D05"):
    ok(need in dec_ids, f"决定 {need} 已定义")
used = set(re.findall(r"\b(S03-1|N[1-5]|ID-[1-4]|PLAN-D0[45][a-d]?)\b", t))
ok(used <= dec_ids | {"PLAN-D04"}, f"引用的决定编号均已定义（未定义：{sorted(used - dec_ids - {'PLAN-D04'})}）")
head = t.split("\n## ")[0]
ok("**已签收**" in head and "ADR-016" in head and "PLAN-D05" in head, "文首写明已签收、ADR-016 与 PLAN-D05 仍待定")
dec = (root / "docs/decisions.md").read_text(encoding="utf-8")
a16 = dec.split("## ADR-016：", 1)[1] if "## ADR-016：" in dec else ""
ok(bool(a16) and "**签收**：ArvinHan 2026-09-23" in a16 and "关闭 PLAN-D04" in a16, "ADR-016 存在、已签收并关闭 PLAN-D04")
ok(all(k in a16 for k in ("`Chunk`", "`Document`", "`model_calls`", "`GraphVersion`", "S-08", "M0-11", "D-08")), "ADR-016 写明 N1～N4 命名与编号处置")
ok("## ADR-015" not in dec, "ADR-015 留给 A09，未被占用")
tb = (root / "docs/tasks.md").read_text(encoding="utf-8")
ok(re.search(r"^\| PLAN-D04 \|.*\*\*已关闭\*\*.*ADR-016", tb, re.M) is not None, "任务板 PLAN-D04 已关闭并指向 ADR-016")
ok(re.search(r"^\| D-08 \|", tb, re.M) is not None, "任务板待确认决策含 D-08")

# 3. 验收要点
ok("不对 `740adb` 做 `git merge`" in s1 and "不执行任何批次" in sec(3), "不自动 merge：结论与批次说明都写明")
id1 = next((r for r in dr if r[0].strip("*") == "ID-1"), [""] * 6)
ok("S-08" in id1[3] and "S-06" in id1[3], "S-06 重号：明确改记 S-08")  # 第 4 列是「建议」
ok("ADR-004" in t and "ADR-005" in sec(4) and "ADR-008" in sec(2), "ADR 编号：ADR-004 取 main、005～008 去向与命名修订明确")
br = rows(sec(3))
batches = {r[0].strip("*") for r in br}
ok({"0", "1", "2", "3", "4", "5", "6"} <= batches, "第 3 节批 0～6 齐全")
ok(all(r[1] and "；" not in r[1] and "、" not in r[1] for r in br), "每批只写一个功能边界")
ok(all(r[4] for r in br), "每批有执行人")
refs = set(re.findall(r"批 (\d)", t))
ok(refs <= batches, f"引用的批次均已定义（未定义：{sorted(refs - batches)}）")

# 4. 原子任务编号真实存在（缺口建议编号除外）
tasks = {x["id"] for x in json.loads((root / "docs/atomic-tasks.json").read_text(encoding="utf-8"))["tasks"]}
gap = sec(6)
proposed = set()
for g, a, b in re.findall(r"\b([A-Z])(\d{2})～(?:[A-Z])?(\d{2})\b", gap):
    proposed |= {f"{g}{i:02d}" for i in range(int(a), int(b) + 1)}
proposed |= set(re.findall(r"\b[A-Z]\d{2}\b", gap)) - tasks
body = t.replace(gap, "")
ids = set(re.findall(r"(?<![\w-])([A-O]\d{2})(?![\w-])", body))
for g, a, b in re.findall(r"(?<![\w-])([A-O])(\d{2})～(\d{2})(?![\w-])", body):
    ids |= {f"{g}{i:02d}" for i in range(int(a), int(b) + 1)}
ok(ids <= tasks, f"正文引用的原子任务均存在（不存在：{sorted(ids - tasks)}）")
ok(proposed and not (proposed & tasks), f"缺口建议编号不与现有任务撞号（{sorted(proposed)}）")

# 5. 关键事实
ok("10-08" in s1 and "§4.2" in s1, "截止日期与出处写明")
ok("4/21" in sec(8) and "exit 0" in sec(8), "试导入与分支门禁结果写明")

print(f"\nRESULT: {'ALL PASS' if not fails else str(len(fails)) + ' FAIL'}")
sys.exit(1 if fails else 0)
```

## 附录 D：`neg_a10.py`（A10 负例）

用法：`python3 neg_a10.py <仓库根目录> <临时目录>`，`check_a10.py` 须在临时目录中。

```python
"""A10 负例：neg_a10.py <repo_root> <scratch>。每个篡改副本都必须使 check_a10.py 非 0 退出。"""
import subprocess, sys
from pathlib import Path
root, S = Path(sys.argv[1]), Path(sys.argv[2])
src = (root / "docs/reviews/branch-integration-map.md").read_text(encoding="utf-8")
CASES = {
    "N1 删去一个文件行": ("| `NOTICE` |", "| `NOTICE-删` |"),
    "N2 某决定去掉签收人": ("| 技术负责人 | 批 1、批 5 |", "|  | 批 1、批 5 |"),
    "N3 摘要数字改错": ("导入 56，待决 13", "导入 57，待决 12"),
    "N4 引用不存在的原子任务": ("B07/K11 在真实前后端门禁出现时再定", "B07/K99 在真实前后端门禁出现时再定"),
    "N5 删去批 4 定义": ("| **4** | 后端分层与测试目录说明 |", "| **x** | 后端分层与测试目录说明 |"),
    "N6 一批写两个功能边界": ("| **3** | 资产与参考目录约定 |", "| **3** | 资产目录；参考文档 |"),
    "N7 删去 S-08 改号": ("改记 **S-08**（S-07 已被合并任务占用）", "另行编号"),
    "N8 签收状态改回草案": ("**已签收**。第 2 节", "草案。第 2 节"),
}
bad = 0
for name, (old, new) in CASES.items():
    assert src.count(old) >= 1, (name, old)
    f = S / f"neg_a10_{name.split()[0]}.md"
    f.write_text(src.replace(old, new, 1), encoding="utf-8")
    r = subprocess.run([sys.executable, str(S / "check_a10.py"), str(root), str(f)], capture_output=True, text=True)
    hits = [l[5:] for l in r.stdout.splitlines() if l.startswith("FAIL")]
    print(f"{name}: exit {r.returncode}；命中 {hits}")
    bad += r.returncode == 0
print("NEGATIVES:", "ALL DETECTED" if not bad else f"{bad} 未检出"); sys.exit(1 if bad else 0)
```
