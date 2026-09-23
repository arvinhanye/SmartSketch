# A03：定义任务生命周期和取消协议

- **task_id**：A03（`docs/atomic-task-plan.md` / `docs/atomic-tasks.json`）
- **状态**：DONE。决定已由 ArvinHan 于 2026-09-23 在会话中逐项选择并签收，记为 **ADR-010**；PLAN-D03 部分关闭（队列 / 租约 / 重试仍归 A06）
- **review_status**：ready_for_review
- **worktree**：`/Users/arvinhan/Desktop/SmartSketch/.claude/worktrees/a03-d430b9`
- **分支 / base**：`claude/a03-task-lifecycle` / base `931361d`（`origin/main`，已含 A02 的 PR #2）
- **head_commit**：本文件与五个文档随同一个交付提交入库（`git log -1 -- docs/handoffs/claude-a03.md` 可查），review 的固定基线取该提交。内容指纹：`git diff 931361d <该提交> -- docs/architecture.md docs/decisions.md docs/tasks.md specs/course-knowledge-graph.md specs/task-processing.md | shasum -a 256` 前 16 位 `86bc2c29f35c7da9`
- **类型**：仅文档任务，无代码、无依赖变更、无合并、无网络调用

## 一、范围与交付物

| 文件 | 改动 |
| --- | --- |
| `specs/task-processing.md` | **新建**。状态属性表；转换表 T1～T9 与禁止转换；C08 迁移事件词表；不变量 I1～I7；处理完成与审核完成；取消矩阵与竞争裁决；部分失败；失败码；SSE 关流与重连；§8 留给 A06；验收 TASK-1～19；契约缺口清单 |
| `docs/decisions.md` | **范围扩展**：新增 ADR-010（背景/方案对比/决定/后果/推翻条件/签收）；ADR-004 编号表下加一行指针（ADR-005/006 已由 A03 复核） |
| `specs/course-knowledge-graph.md` | **范围扩展**：验收 2 把「任一非终态可转 `failed` 或 `cancelled`」收窄为 T8/T9 的来源，并指向新规格 |
| `docs/architecture.md` | **范围扩展**：三处「归 A03 / A03 复核」占位改为指向新规格；SSE 任务流的终止规则补「`awaiting_review` 后关流」 |
| `docs/tasks.md` | A03 认领行（DONE）、PLAN-D03 部分关闭、A03 决定与后续项两条 |
| `docs/handoffs/claude-a03.md` | 本文件 |

**范围扩展说明**：清单给 A03 的文件锁只有 `specs/task-processing.md`。AGENTS.md §6 要求已确认选择写入 ADR；`course-knowledge-graph.md` 验收 2 与新转换表直接冲突；`architecture.md` 有三处写着「归 A03」的占位。用户在本轮选择「规格 + ADR-010 + 同步引用」，扩展已写入认领行。未触碰 `src/`、`scripts/`、`tests/`、`.env.example`、`docs/integrations.md`、`docs/atomic-tasks.json`，未改其他 worktree。`architecture.md` 的 `ErrorCode` 行刻意未改：新码只是提议，真源未加之前改它会使 A02 的逐值核对失败。

## 二、裁定内容（签收人 ArvinHan，2026-09-23）

| 问题 | 决定 |
| --- | --- |
| 处理完成 vs 审核完成 | `awaiting_review` = 处理完成：worker 不再触碰，不可取消（409 `processing_finished`），不会 `failed`，SSE 推送后服务端关流。`completed` = 审核完成：发布成功时，在切换发布指针的同一 SQLite 事务内推进该课程中草稿已含在快照内的全部 `awaiting_review` 任务（**第二轮更正**：该谓词与「全部驳回仍转 `completed`」矛盾，已改为「T6 提交序号 ≤ 快照任务水位」，见第九节）；发布失败、回滚不改任务状态 |
| 取消边界 | `queued` 由 API 直接转 `cancelled`；`parsing`/`extracting`/`merging` 置 `cancel_requested`，worker 在阶段边界与 `extracting` 块间检查点转 `cancelled`；`merging → persisting` 是最后取消点；`persisting` 取消得 409 `persisting_uninterruptible`。竞争由同一行的比较并交换裁决 |
| 取消响应 | 受理一律 HTTP 200 + `Task` 快照（含真实 `stage` 与 `cancel_requested`）；重复取消幂等、不推新事件；终态取消 409 `already_terminal`（ADR-006 第 4 条不变） |
| 部分失败 | 只在 `extracting`；`TASK_MAX_FAILED_CHUNK_RATIO` 默认 0.2、取值 `[0, 1)`；失败比例 ≤ 阈值继续并逐块记录定位，否则 `failed`；允许结论确定后提前失败；不阻塞发布 |
| 重连 | 前端 `api/` 封装管理：出错即关闭、重新申领令牌再建连，退避后降级轮询；不依赖 `EventSource` 自动重连，不用 `Last-Event-ID` |
| 再处理 | 终态不可复活，一律新任务新 `task_id`；入口交 C06/C07 |

会话中只由用户逐项选择的是前三行的方向（完成语义、部分失败策略、`persisting` 不可取消）与交付范围；四节设计（转换表、取消协议、部分失败与失败码、SSE 与重连）由用户逐节确认。失败码的具体命名、409 `reason` 取值、重连退避数字是本任务在已确认方向内定稿的细节。

## 三、验收对照（A03 验收矩阵）

| 验收条款 | 落点 | 结果 |
| --- | --- | --- |
| 区分处理完成和人工审核完成 | 术语；§1 类别列；§2 T6/T7；§3；TASK-1、2、12、18 | 满足 |
| 部分失败 | §5 判定/计数/呈现；§6 失败码；TASK-9、10、13 | 满足 |
| 取消请求 / 取消完成 | 术语（标志位 vs 终态）；§4 矩阵；I5；TASK-3、4 | 满足 |
| 重复取消 | §4 矩阵「重复取消」行与终态行；TASK-5 | 满足 |
| 重连 | §7「重连」；TASK-11 | 满足 |
| 取消竞争语义 | §4「竞争裁决」五种情形；TASK-6、7、8 | 满足 |
| 人工决策保留未签收标记 | 本轮决定已签收，签收行齐全；未决事项（A06 §8、SSE 令牌、串行化、再处理入口、阈值登记、4 个错误码）均写明「不裁定」并指定去向 | 满足 |

## 四、实际运行的命令与结果

```text
./scripts/verify.sh        改动前 exit 0；改动后 exit 0（Scaffold verification passed）
git diff --check           改动前 exit 0；改动后 exit 0
grep -n -E "TBD|TODO|待补充|XXX" specs/task-processing.md
                           exit 1（无占位残留）
python3 check_a03.py . <740adb 978671e 的 api.v1.yaml>
                           exit 0：62 项 PASS —— ALL PASS
python3 negatives.py <scratch> <worktree>
                           7 个篡改副本全部 exit 1、无崩溃，各自逐条报出（见下）
```

负例（每个都在独立副本上只改一处）：

| 篡改 | 被检出的项 |
| --- | --- |
| N1 允许 `awaiting_review → cancelled` | §1 取消列不一致、禁止转换与转换表相交、`stage_done`/`checkpoint` 前置不一致、验收 2 的 cancelled 来源不一致 |
| N2 验收 2 回退为「任一非终态可转」 | failed 来源、cancelled 来源、旧表述残留 |
| N3 §1 把 `persisting` 标为不可失败 | 「可转 failed」列与 T9 不一致 |
| N4 删除 TASK-5 | 编号断档、实现方标注、「重复取消」落点缺失 |
| N5 `architecture.md` 恢复「归 A03」 | 残留占位、未指向新规格 |
| N6 事件 `persisted` 前置写成 `merging` | `persisted` 前置 ≠ T6 起点 |
| N7 提议码与现有码 `LLM_UNAVAILABLE` 重名 | 提议码与现有表相交、与真源相交 |

YAML 由 `git show 978671e:src/contracts/api.v1.yaml` 导出到会话 scratch 目录。第一版核对脚本用「禁止列表至少 6 条」作门槛，正例因此误报 FAIL；改为枚举全部 58 个非法状态对并逐一确认被「回退 / 跳级 / 终态外转 / 显式列出」覆盖后重跑，上面是修正后的结果。核对脚本不入库（`tests/` 归测试 Agent，且 main 尚无 YAML），全文附在本文件附录。

## 五、接口 / 数据 / 配置变更

无运行时变更，无契约文件改动（main 尚无 `api.v1.yaml`）。受本决定约束、须先改真源再生成的未来变更（规格末尾「契约缺口」表是完整清单）：

1. **B10**：`Task` 增加 `cancel_requested`；`TaskCounts` 增加 `chunks_failed`；`Task` 增加 `failed_chunks`；`stage = failed` ⇔ `error` 非空（S07-R09）；取消端点 200/409 描述；`TaskStage` 描述改为指向本规格；`events.v1.md` §2 转换表改为指针、§2 关流规则与 §4 重连按规格 §7 改写。核对脚本最后 5 项已确认这些缺口在 `978671e` 真源中确实存在。
2. **B08**：`ErrorCode` 增加 `DOCUMENT_UNREADABLE`、`EXTRACTION_INCOMPLETE`、`STORAGE_UNAVAILABLE`、`INTERNAL_ERROR`，同一次提交更新 `architecture.md` 的 `ErrorCode` 行。
3. **A07**：`TASK_MAX_FAILED_CHUNK_RATIO` 登记到 `.env.example` 与 `docs/integrations.md`。

## 六、未完成 / 风险

- **T7 的正确性依赖未定机制**：同一课程 `persisting` 提交与发布快照必须串行，否则一个任务的草稿可能一半在快照内。规格只写了不变量，机制归 A04/A06；G04 实现前必须先有它。
- **重连依赖尚不存在的端点**：§7 要求出错后重新申领 SSE 令牌，但签发端点（S07-R07）还没有契约。B10/A05 补上之前，C12 只能实现轮询降级。
- **阈值 0.2 没有实测依据**：是经验默认值。K04 或试用若发现阈值内缺漏严重，按 ADR-010 推翻条件 2 重开。
- **`persisting` 不可取消的代价未测**：若该阶段实测耗时很长，教师会等很久。按推翻条件 3 重开。
- **`Document.parse_status` 跟随哪个任务**：一份资料被再处理后会有多个任务；`parse_status` 应反映最新任务还是其他规则，未定，交 C06/C07。
- **ADR-005/006 不在 main**：它们在 `740adb`/`209be9`。本轮只在 ADR-004 编号表下加指针，A10 导入时须在两条文首加注指向 ADR-010。
- **合并提示**：`740adb` 的 `specs/course-knowledge-graph.md` 改写过验收 2，A10 合并时会冲突，以本轮版本（含 A02 与 A03 的收窄）为准；`740adb` 的 `docs/tasks.md` 结构不同，按 A02 交接的「main 的 PLAN-D 行在前」处理。
- **未验证**：本规格没有任何实现或自动化测试；TASK-1～19 是 C08/C10/C11/C12/E12/F13/G04 等任务的验收契约，不是已通过的测试。

## 七、下一位 Agent 的首个动作

1. 请 Codex 按上方指纹（或提交后的固定提交）审查本轮五个已跟踪文件与本交接；修复另开一轮。
2. **A06**（依赖 A03）现可认领：在 `specs/task-processing.md` §8 补租约、接管、重试上限与幂等；不得改动 §1～§7，确需改动先修订 ADR-010。
3. **B10**（依赖 B08、A03）：B08 验收后认领，按第五节第 1 条先改 `api.v1.yaml` 再生成。C08 依赖 A03 + B10，B10 之后可开工。

## 八、回滚

仅文档改动，无持久层与依赖变更。提交后首选 `git revert <A03 交付提交>`。若需在提交前手工恢复，只还原本任务的四个已跟踪文件并删除两个新文件：

```text
git -C <本 worktree> checkout 931361d -- docs/architecture.md docs/decisions.md docs/tasks.md specs/course-knowledge-graph.md
git -C <本 worktree> rm --cached --quiet specs/task-processing.md   # 撤销 intent-to-add
rm <本 worktree>/specs/task-processing.md <本 worktree>/docs/handoffs/claude-a03.md
```

不要使用 reset 或 stash 清理；stash 栈与其他 worktree 共享。

## 九、第二轮：Codex 审查修复（A03-R01 / A03-R02）

- **review_status**：ready_for_review
- **审查报告**：主目录 `docs/reviews/codex-claude-a03-ci01-s07-2026-09-23-0606z.md`（目标提交 `2049129`）。本轮只处理其中 A03 的两条 P2；CI-01 与 S-07 部分无新问题，未涉及
- **base / head**：base `2049129`；head 为本轮交付提交（`git log -1 -- docs/handoffs/claude-a03.md` 可查）。内容指纹：`git diff 2049129 <该提交> -- docs/architecture.md docs/decisions.md docs/tasks.md specs/course-knowledge-graph.md specs/task-processing.md | shasum -a 256` 前 16 位 `93bf51951869d60f`
- **结论**：两条均复核属实，按审查建议修复；ADR-010 的决定方向不变，只澄清措辞

| 问题 | 复核 | 修复 |
| --- | --- | --- |
| **A03-R01** SSE 在 `awaiting_review` 关流后，原订阅者收不到 `done`；而验收 2 写「全部可通过 SSE 观察」、架构表与规格 §7 写终态事件「恰好一次」 | 属实。按生命周期理解，这些措辞与关流规则冲突，实现方可能为满足旧验收保留长连接 | 规格 §7 新增「覆盖范围」：任务 SSE 只覆盖处理阶段；「恰好一次」改为按连接的「每个连接恰好以一条结束事件收尾」；终态行拆为「处理中进入 `failed`/`cancelled`」与「建连时已终态」；写明 `completed` 的观察方式（任务查询、课程发布状态），将来如需实时推送须另定课程级事件流。同步验收 2、架构 SSE 行、ADR-010 决定 1 与「后果」、契约缺口表中 `events.v1.md` 第 4 条。新增 **TASK-20**（订阅先于发布） |
| **A03-R02** T7 与 ADR-010 决定 2 写「只推进草稿已含在快照中的任务」（按内容成员资格），§3 却要求「全部驳回仍转 `completed`」 | 属实。按前者，内容全被驳回的任务永远停在 `awaiting_review` | 按审查建议统一为**任务水位**：T6 在提交事务内分配课程内严格递增的提交序号；建快照时（与 `persisting` 串行）读取最大序号作为水位并随版本元数据保存；T7 推进 `stage = awaiting_review AND 序号 ≤ 水位` 的全部任务，不看内容。T7、§3、ADR-010 决定 2 与方案表、TASK-2、架构映射行、任务板摘要使用同一谓词。新增 **TASK-21**（全部驳回）、**TASK-22**（水位竞争：读水位后、切指针前完成 T6 的任务不推进） |

**本轮改动文件**：`specs/task-processing.md`（T7、§3、§7、验收矩阵、`events.v1.md` 差异与缺口行）、`specs/course-knowledge-graph.md`（验收 2）、`docs/architecture.md`（SSE 任务行、映射表「S2 完成」行）、`docs/decisions.md`（ADR-010 条首修订说明、方案表一行、决定 1、决定 2、「后果」中 `events.v1.md` 一条）、`docs/tasks.md`（修复轮次行、A03 摘要措辞、修复说明一条）、本文件（第一轮第二节一处更正标记、本节、附录换为新版脚本）。

**实际运行的命令与结果**：

```text
python3 check_a03.py . <978671e api.v1.yaml>   先红：新增 11 项 FAIL（原 62 项 PASS），exit 1
                                              修复后：一处漏改被 grep 发现（architecture.md 映射行仍写「推进快照内的任务」），
                                              补第 12 项检查，先红后改；最终 74 项 ALL PASS，exit 0
python3 negatives.py <scratch> <worktree>     12 个篡改副本全部 exit 1、无崩溃；新增 N8～N12 各自命中对应 R01/R02 检查
python3 check_a02.py docs/architecture.md <978671e api.v1.yaml>
                                              ALL PASS（本轮改了 architecture.md，回归 A02 的枚举表核对）
./scripts/verify.sh                           exit 0
git diff --check                              exit 0；新文件行尾空白 grep exit 1（无）
```

核对脚本本轮有两处放宽，均属措辞层面、不降低检查力度：旧检查项「architecture.md 含 `awaiting_review` 后关流字样」改为「SSE 任务行同时含 `awaiting_review` 与关流」；R02 的 ADR 检查只看决定 2 本身（修订说明为交代改动而引用旧谓词）。TASK 编号检查改为集合相等，因为 TASK-20～22 追加在「边界路径」末尾，已有编号不重排，以免破坏交接、PR 与任务板中的 TASK-13～19 引用。

**未验证 / 风险**：

- 任务水位需要一个实现侧字段（T6 提交序号）与版本元数据字段（水位），均不上 wire；列名与迁移由 C06/G04 定。水位读取必须与 `persisting` 提交串行，机制仍归 A04/A06，TASK-22 在该机制存在前无法实现。
- 规格仍无实现或自动化测试；TASK-20～22 与 TASK-1～19 一样是后续任务的验收契约。
- 审查报告指出核对脚本未入库、不计为可独立复验的自动化测试——本轮维持不入库（`tests/` 归测试 Agent），脚本全文仍附在附录。

**回滚**：仅文档改动。提交后首选 `git revert <本轮提交>`；提交前只还原本轮六个文件：`git -C <本 worktree> checkout 2049129 -- docs/architecture.md docs/decisions.md docs/tasks.md specs/course-knowledge-graph.md specs/task-processing.md docs/handoffs/claude-a03.md`。不用 reset 或 stash。

**下一步**：请 Codex 按本轮固定提交复核 A03-R01/R02 两条；修复另开一轮。

## 附录 A：`check_a03.py`（核对脚本全文，第二轮版本）

用法：`python3 check_a03.py <repo 根目录> <api.v1.yaml>`；依赖 PyYAML。YAML 取自 `git show 978671e:src/contracts/api.v1.yaml`。第一轮的 62 项检查全部保留，第二轮新增 12 项（R01 六项、R02 六项）。

```python
"""A03 验收核对：specs/task-processing.md 的内部一致性、与其他文档及 740adb 真源的一致性。

用法：python3 check_a03.py <repo 根目录> <740adb 978671e 的 api.v1.yaml>
退出码：0 全部一致；1 有不一致（逐条打印）。依赖 PyYAML。
"""
import re
import sys
from pathlib import Path

import yaml

root, yaml_path = Path(sys.argv[1]), sys.argv[2]
spec = (root / "specs/task-processing.md").read_text(encoding="utf-8")
ckg = (root / "specs/course-knowledge-graph.md").read_text(encoding="utf-8")
arch = (root / "docs/architecture.md").read_text(encoding="utf-8")
adr = (root / "docs/decisions.md").read_text(encoding="utf-8")
tasks = (root / "docs/tasks.md").read_text(encoding="utf-8")
contract = yaml.safe_load(open(yaml_path, encoding="utf-8"))
schemas = contract["components"]["schemas"]
failures = []


def check(ok, label):
    print(("PASS " if ok else "FAIL ") + label)
    if not ok:
        failures.append(label)


def section(text, start, end=None):
    body = text.split(start, 1)[1] if start in text else ""
    return body.split(end, 1)[0] if end and end in body else body


CHAIN = ["queued", "parsing", "extracting", "merging", "persisting", "awaiting_review", "completed"]
TERMINAL = {"completed", "failed", "cancelled"}


def expand_range(a, b):
    return set(CHAIN[CHAIN.index(a): CHAIN.index(b) + 1])


def names(cell):
    return re.findall(r"`([a-z_]+)`", cell)


# ---------- 1. 状态属性表 ----------
attr = {}
for line in section(spec, "## 1. 状态属性", "## 2.").splitlines():
    m = re.match(r"\| `([a-z_]+)` \| ([^|]+) \| ([^|]+) \| ([^|]+) \| ([^|]+) \|", line)
    if m:
        attr[m.group(1)] = {
            "cancel": m.group(3).strip(),
            "can_fail": m.group(4).strip(),
            "closes": "是" in m.group(5),
        }

arch_row = re.search(r"\| `TaskStage` \| (.+?) \| lower \|", arch)
arch_stages = names(arch_row.group(1)) if arch_row else []
check(arch_stages and list(attr) == arch_stages, f"§1 状态集合与架构 TaskStage 逐值逐序一致（{len(attr)} 值）")
check(schemas["TaskStage"]["enum"] == list(attr), "§1 状态集合与 740adb 真源 TaskStage 一致")

# ---------- 2. 转换表 ----------
edges = {}
for line in section(spec, "## 2. 转换表", "**禁止的转换**").splitlines():
    m = re.match(r"\| (T\d+) \| (.+?) \| ", line)
    if not m:
        continue
    for pair in m.group(2).split("，"):
        left, right = pair.split("→")
        dst = names(right)[0]
        srcs = names(left) or ["<none>"]
        for src in srcs:
            edges.setdefault((src, dst), []).append(m.group(1))
allowed = set(edges)
check(len({t for ts in edges.values() for t in ts}) == 9, "转换表 T1～T9 齐全")
check(all((a, b) in allowed for a, b in zip(CHAIN, CHAIN[1:])), "主链 queued→…→completed 每一步都在转换表中")
check(not any(src in TERMINAL for src, _ in allowed), "终态没有出边")

fail_src = {s for s, d in allowed if d == "failed"}
cancel_src = {s for s, d in allowed if d == "cancelled"}
check(fail_src == {s for s, a in attr.items() if a["can_fail"] == "是"}, f"§1「可转 failed」列与 T9 起点一致 {sorted(fail_src)}")
cancel_ok = {s for s, a in attr.items() if "直接转" in a["cancel"] or "置标志" in a["cancel"]}
check(cancel_src == cancel_ok, f"§1「取消请求的结果」列与 T3/T8 起点一致 {sorted(cancel_src)}")
check({s for s, a in attr.items() if a["cancel"] == "409"} == set(attr) - cancel_ok, "其余状态的取消结果均为 409")
check({s for s, a in attr.items() if a["closes"]} == TERMINAL | {"awaiting_review"}, "推送后关流 = 三个终态 + awaiting_review")

forbidden_text = section(spec, "**禁止的转换**", "### 迁移事件")
forbidden = set(re.findall(r"`([a-z_]+) → ([a-z_]+)`", forbidden_text))
has_class = {k: k in forbidden_text for k in ("回退", "跳级", "终态再转")}
check(all(has_class.values()), f"禁止列表含三类规则 {has_class}")
uncovered, non_allowed = [], 0
for a in attr:
    for b in attr:
        if a == b or (a, b) in allowed:
            continue
        non_allowed += 1
        covered = (
            a in TERMINAL
            or (a, b) in forbidden
            or (a in CHAIN and b in CHAIN and CHAIN.index(b) != CHAIN.index(a) + 1)
        )
        if not covered:
            uncovered.append(f"{a}→{b}")
check(not uncovered, f"全部 {non_allowed} 个非法状态对均被禁止规则覆盖 {uncovered}")
check(not (forbidden & allowed), "禁止的转换与转换表无交集")
for f in [("awaiting_review", "failed"), ("awaiting_review", "cancelled"), ("persisting", "cancelled"), ("queued", "failed")]:
    check(f in forbidden, f"禁止列表含 {f[0]} → {f[1]}")

# 每个非终态都能到达某个终态
graph = {}
for s, d in allowed:
    graph.setdefault(s, set()).add(d)
for s in set(attr) - TERMINAL:
    seen, stack = set(), [s]
    while stack:
        cur = stack.pop()
        for n in graph.get(cur, ()):
            if n not in seen:
                seen.add(n)
                stack.append(n)
    check(bool(seen & TERMINAL), f"{s} 可达终态")

# ---------- 迁移事件表与转换表一致 ----------
events = {}
for line in section(spec, "### 迁移事件", "### 不变量").splitlines():
    m = re.match(r"\| `([a-z_]+)(?:\([a-z]+\))?` \| [^|]+ \| ([^|]+) \|", line)
    if m:
        cell = m.group(2)
        rng = re.search(r"`([a-z_]+)`～`([a-z_]+)`", cell)
        events[m.group(1)] = expand_range(*rng.groups()) if rng else set(names(cell))
check(events.get("claim") == {s for s, d in allowed if d == "parsing"}, "事件 claim 前置 = T2 起点")
check(events.get("persisted") == {s for s, d in allowed if d == "awaiting_review"}, "事件 persisted 前置 = T6 起点")
check(events.get("published") == {s for s, d in allowed if d == "completed"}, "事件 published 前置 = T7 起点")
check(events.get("fail") == fail_src, "事件 fail 前置 = T9 起点")
check(events.get("stage_done") == events.get("checkpoint") == cancel_src - {"queued"}, "stage_done / checkpoint 前置 = T8 起点")

# ---------- 取消矩阵 ----------
cancel_sec = section(spec, "## 4. 取消协议", "## 5.")
reasons = set(re.findall(r'reason: "([a-z_]+)"', cancel_sec))
check(reasons == {"persisting_uninterruptible", "processing_finished", "already_terminal"}, f"409 reason 三种且 lower_snake {sorted(reasons)}")
check("重复取消" in cancel_sec and "幂等" in cancel_sec, "取消矩阵覆盖重复取消（幂等）")
check("stage = merging AND cancel_requested = false" in cancel_sec, "竞争裁决写明 T5 的比较并交换条件")

# ---------- 部分失败与失败码 ----------
pf = section(spec, "## 5. 部分失败", "## 6.")
check("TASK_MAX_FAILED_CHUNK_RATIO" in pf and "`0.2`" in pf and "`[0, 1)`" in pf, "阈值变量、默认值与取值范围")
check("≤ 阈值" in pf and "含等号" in pf, "阈值边界写明含等号")
code_row = re.search(r"\| `ErrorCode` \| (.+?) \| UPPER \|", arch)
arch_codes = set(re.findall(r"`([A-Z_]+)`", code_row.group(1))) if code_row else set()
check(arch_codes == set(schemas["ErrorCode"]["enum"]), f"架构 ErrorCode 表与真源一致（{len(arch_codes)} 值，本轮未改）")
codes_sec = section(spec, "## 6. 失败码", "## 7.")
new_codes, old_codes = set(), set()
for line in codes_sec.splitlines():
    code = re.search(r"\| `([A-Z_]+)` \|", line)
    if code:
        (new_codes if "提议新增" in line else old_codes).add(code.group(1))
check(old_codes <= arch_codes, f"沿用的失败码都在架构 ErrorCode 表中 {sorted(old_codes)}")
check(new_codes and not (new_codes & arch_codes), f"提议新增码不在现有表中 {sorted(new_codes)}")
check(all(re.fullmatch(r"[A-Z][A-Z0-9_]*", c) for c in new_codes), "提议新增码为 UPPER_SNAKE")
check(not (new_codes & set(schemas["ErrorCode"]["enum"])), "提议新增码确实不在 740adb 真源（缺口真实）")

# ---------- SSE 与重连 ----------
sse = section(spec, "## 7. SSE", "## 8.")
check("不依赖 `EventSource` 自动重连" in sse and "Last-Event-ID" in sse, "重连：不依赖自动重连、不用 Last-Event-ID")
check("**进入 `awaiting_review`**" in sse and "**服务端关流**" in sse, "SSE 表写明 awaiting_review 关流")

# ---------- 验收矩阵 ----------
acc = section(spec, "## 验收矩阵", "## 交给后续任务")
ids = [int(n) for n in re.findall(r"\*\*TASK-(\d+)\*\*", acc)]
check(sorted(ids) == list(range(1, len(ids) + 1)) and len(set(ids)) == len(ids), f"TASK 编号无重复且覆盖 1～{len(ids)}")
cats = re.split(r"- (成功路径|边界路径|失败路径)\n", acc)
counts = {cats[i]: len(re.findall(r"\*\*TASK-", cats[i + 1])) for i in range(1, len(cats) - 1, 2)}
check(all(counts.get(c, 0) >= 1 for c in ("成功路径", "边界路径", "失败路径")), f"成功/边界/失败各至少一例 {counts}")
check(all(re.search(r"\*\*TASK-\d+\*\*（[A-Z0-9、 组]+）", l) for l in acc.splitlines() if "**TASK-" in l), "每条 TASK 标注实现方")

# ---------- A03 验收条款逐条落点 ----------
clauses = {
    "区分处理完成和人工审核完成": "## 3. 处理完成与审核完成" in spec and "**处理完成**" in spec and "**审核完成**" in spec,
    "部分失败": "## 5. 部分失败" in spec and re.search(r"TASK-(9|10|13)", acc) is not None,
    "取消请求 / 取消完成": "**取消请求**" in spec and "**取消完成**" in spec,
    "重复取消": re.search(r"\*\*TASK-\d+\*\*（[^）]+）重复取消", acc) is not None,
    "重连": re.search(r"\*\*TASK-\d+\*\*（[^）]+）重连", acc) is not None and "**重连**" in sse,
}
for k, v in clauses.items():
    check(v, f"A03 验收条款落点：{k}")

# ---------- 跨文档 ----------
acc2 = re.search(r"^2\. 每次上传返回任务 ID.+$", ckg, re.M)
acc2 = acc2.group(0) if acc2 else ""
f_rng = re.search(r"`failed` 只能从 `([a-z_]+)`～`([a-z_]+)` 转入", acc2)
c_rng = re.search(r"`cancelled` 只能从 `([a-z_]+)`～`([a-z_]+)` 转入", acc2)
check(bool(f_rng) and expand_range(*f_rng.groups()) == fail_src, "course-knowledge-graph 验收 2 的 failed 来源 = T9")
check(bool(c_rng) and expand_range(*c_rng.groups()) == cancel_src, "course-knowledge-graph 验收 2 的 cancelled 来源 = T3/T8")
check("任一非终态可转" not in acc2 and "specs/task-processing.md" in acc2, "验收 2 旧表述已移除并指向新规格")
check("归 A03" not in arch and "A03 复核" not in arch, "architecture.md 无「归 A03 / A03 复核」残留占位")
check(arch.count("specs/task-processing.md") >= 2, "architecture.md 指向新规格")
sse_row = next((l for l in arch.splitlines() if l.startswith("| 任务进度 `GET /api/v1/tasks/{tid}/events`")), "")
check("awaiting_review" in sse_row and "关流" in sse_row, "architecture.md SSE 任务行同步 awaiting_review 关流")
adr10 = section(adr, "## ADR-010")
check(bool(adr10) and "**签收**：ArvinHan 2026-09-23" in adr10, "ADR-010 存在且有签收行")
check("## ADR-010" in adr and adr.index("## ADR-009") < adr.index("## ADR-010"), "ADR-010 位于 ADR-009 之后")
check(re.search(r"\| A03 \| [^|]+ \| 定义任务生命周期和取消协议", tasks) is not None, "任务板有 A03 认领行")
check("PLAN-D03" in tasks and "部分关闭" in tasks.split("PLAN-D03", 1)[1].split("\n", 1)[0], "PLAN-D03 标为部分关闭")

# ---------- Codex A03-R01：SSE 只覆盖处理阶段，按连接表述 ----------
sse_task_row = next((l for l in arch.splitlines() if l.startswith("| 任务进度 `GET /api/v1/tasks/{tid}/events`")), "")
check("全部可通过 SSE 观察" not in acc2 and "处理阶段" in acc2, "R01 验收 2 把 SSE 观察范围限定为处理阶段")
check("GET /api/v1/tasks/{tid}" in acc2 or "任务查询" in acc2, "R01 验收 2 写明 completed 的观察方式")
check("恰好一次" not in sse_task_row and "每个连接" in sse_task_row, "R01 架构 SSE 任务行按连接表述，不再写生命周期级「恰好一次」")
check("恰好一次" not in sse and "每个连接恰好以一条结束事件收尾" in sse, "R01 规格 §7 按连接定义结束事件")
check(re.search(r"\*\*TASK-\d+\*\*（[^）]+）订阅先于发布", acc) is not None, "R01 验收含「订阅先于发布」时序用例")
adr10_d1 = re.search(r"  1\. \*\*`awaiting_review` = 处理完成\*\*.+", adr10)
check(bool(adr10_d1) and "只覆盖处理阶段" in adr10_d1.group(0), "R01 ADR-010 决定 1 写明任务 SSE 只覆盖处理阶段")

# ---------- Codex A03-R02：发布推进谓词统一为任务水位 ----------
t7_row = next((l for l in spec.splitlines() if l.startswith("| T7 |")), "")
sec3 = section(spec, "## 3. 处理完成与审核完成", "## 4.")
adr10_d2 = re.search(r"  2\. \*\*`completed` = 审核完成\*\*.+", adr10)
check("含在本次发布快照" not in t7_row and "任务水位" in t7_row, "R02 T7 用任务水位谓词，不按内容成员资格")
check("任务水位" in sec3 and "草稿在发布快照生成前已提交" not in sec3, "R02 §3 定义任务水位并移除旧谓词")
check(bool(adr10_d2) and "任务水位" in adr10_d2.group(0) and "草稿已含在本次快照内" not in adr10_d2.group(0), "R02 ADR-010 决定 2 用同一谓词")
map_row = next((l for l in arch.splitlines() if l.startswith("| S2「完成」")), "")
check("推进快照内" not in map_row and "任务水位" in map_row, "R02 架构「文档用语 → wire 值」映射行用同一谓词")
task2 = re.search(r"\*\*TASK-2\*\*.+", acc)
check(bool(task2) and "任务水位" in task2.group(0), "R02 TASK-2 用同一谓词")
check(re.search(r"\*\*TASK-\d+\*\*（[^）]+）全部驳回", acc) is not None, "R02 验收含「全部驳回仍 completed」回归用例")

# ---------- 列出的契约缺口在真源中确实存在 ----------
check("cancel_requested" in schemas["TaskEvent"]["properties"], "真源 TaskEvent 已有 cancel_requested")
check("cancel_requested" not in schemas["Task"]["properties"], "缺口真实：真源 Task 无 cancel_requested")
check("chunks_failed" not in schemas["TaskCounts"]["properties"], "缺口真实：真源 TaskCounts 无 chunks_failed")
check("failed_chunks" not in schemas["Task"]["properties"], "缺口真实：真源 Task 无 failed_chunks")
cancel_200 = contract["paths"]["/api/v1/tasks/{tid}/cancel"]["post"]["responses"]["200"]["description"]
check("已转入 cancelled" in cancel_200, "缺口真实：真源取消 200 描述仍为「已转入 cancelled」")

if failures:
    print("\n".join(["", "FAILURES:"] + failures))
    sys.exit(1)
print("\nALL PASS")
```

## 附录 B：`negatives.py`（负例脚本全文，第二轮版本）

用法：`python3 negatives.py <scratch 目录（含 check_a03.py 与 api.v1.yaml）> <worktree>`。每个用例把五份文档复制到 `<scratch>/neg/<编号>/` 后只改一处；N8～N12 为第二轮新增。

```python
import shutil, subprocess, sys
from pathlib import Path
sp, wt = Path(sys.argv[1]), Path(sys.argv[2])
files = ["specs/task-processing.md", "specs/course-knowledge-graph.md", "docs/architecture.md", "docs/decisions.md", "docs/tasks.md"]
cases = {
 "N1 awaiting_review 允许取消": ("specs/task-processing.md",
   "| T8 | `parsing` / `extracting` / `merging` → `cancelled`", "| T8 | `parsing` / `extracting` / `merging` / `awaiting_review` → `cancelled`"),
 "N2 验收 2 回退为旧表述": ("specs/course-knowledge-graph.md",
   "`failed` 只能从 `parsing`～`persisting` 转入，`cancelled` 只能从 `queued`～`merging` 转入", "任一非终态可转 `failed` 或 `cancelled`"),
 "N3 §1 persisting 标为不可失败": ("specs/task-processing.md",
   "| `persisting` | 处理中，**不可中断** | 409 | 是 |", "| `persisting` | 处理中，**不可中断** | 409 | 否 |"),
 "N4 删除 TASK-5 造成编号断档": ("specs/task-processing.md", "**TASK-5**", "**TASK-X**"),
 "N5 architecture 残留 A03 占位": ("docs/architecture.md",
   "状态转换语义不在本节，见 `specs/task-processing.md`（A03 / ADR-010）。", "状态转换语义不在本节，归 A03。"),
 "N6 事件 persisted 前置写错": ("specs/task-processing.md",
   "| `persisted` | worker | `persisting` | T6 |", "| `persisted` | worker | `merging` | T6 |"),
 "N7 提议码与现有码重名": ("specs/task-processing.md",
   "`STORAGE_UNAVAILABLE` | — | **提议新增** |", "`LLM_UNAVAILABLE` | — | **提议新增** |"),
    "N8 T7 退回按内容成员资格": ("specs/task-processing.md",
   "推进该课程中 T6 提交序号 ≤ 本次快照**任务水位**的全部 `awaiting_review` 任务，与其内容是否进入快照无关（§3）", "只推进草稿已含在本次发布快照中的任务"),
 "N9 验收 2 恢复「全部可通过 SSE 观察」": ("specs/course-knowledge-graph.md",
   "转换。处理阶段（直到 `awaiting_review`、`failed` 或 `cancelled`）可通过 SSE 观察；", "转换，全部可通过 SSE 观察；"),
 "N10 架构 SSE 行恢复生命周期级「恰好一次」": ("docs/architecture.md",
   "| 只覆盖处理阶段。每个连接恰好以一条结束事件收尾：", "| `done` / `error` / `cancelled` 互斥且恰好一次；"),
 "N11 删除全部驳回用例": ("specs/task-processing.md", "（G04）全部驳回：", "（G04）内容驳回："),
    "N12 架构映射行退回旧谓词": ("docs/architecture.md", "发布时按任务水位推进（含内容被全部驳回的任务）", "发布时推进快照内的任务"),
}
for name, (rel, old, new) in cases.items():
    d = sp / "neg" / name.split()[0]
    if d.exists(): shutil.rmtree(d)
    for f in files:
        (d / f).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(wt / f, d / f)
    text = (d / rel).read_text(encoding="utf-8")
    assert text.count(old) == 1, (name, old)
    (d / rel).write_text(text.replace(old, new), encoding="utf-8")
    r = subprocess.run([sys.executable, str(sp / "check_a03.py"), str(d), str(sp / "api.v1.yaml")], capture_output=True, text=True)
    fails = [l[5:] for l in r.stdout.splitlines() if l.startswith("FAIL ")]
    crashed = "Traceback" in r.stderr
    print(f"{name}: exit={r.returncode} crashed={crashed} fails={len(fails)}")
    for f in fails: print("    -", f)
```
