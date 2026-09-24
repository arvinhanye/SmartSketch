# A06：定义 worker 租约和幂等机制

- **task_id**：A06（`docs/atomic-task-plan.md` / `docs/atomic-tasks.json`）
- **状态**：DONE。决定已由 ArvinHan 于 2026-09-23 在会话中逐项选择并签收，记为 **ADR-011**；与 ADR-010 一起使 **PLAN-D03 全部关闭**
- **review_status**：ready_for_review
- **worktree**：`/Users/arvinhan/Desktop/SmartSketch/.claude/worktrees/a03-d430b9`
- **分支 / base**：`claude/a06-worker-lease`，**叠在** `claude/a03-task-lifecycle` 之上 / base `6345ce1`（A03 的 PR #5 尚未合并；A06 依赖 A03，且要写的 §8 只存在于 A03 分支）
- **head_commit**：本文件与四个文档随同一个交付提交入库（`git log -1 -- docs/handoffs/claude-a06.md` 可查），review 的固定基线取该提交。内容指纹：`git diff 6345ce1 <该提交> -- docs/architecture.md docs/decisions.md docs/tasks.md specs/task-processing.md | shasum -a 256` 前 16 位 `09bc765c49e32934`
- **类型**：仅文档任务，无代码、无依赖变更、无合并、无网络调用

## 一、范围与交付物

| 文件 | 改动 |
| --- | --- |
| `specs/task-processing.md` | §8 由占位改为正文：8.1 部署边界、8.2 领取/租约/续约/防旧写/本地截止/回收/接管、8.3 三层重试与耗尽码、8.4 各阶段检查点与幂等、8.5 课程写锁、8.6 中间产物保留、8.7 迁移备份与回滚、8.8 配置、8.9 验收 LEASE-1～17。§1～§7 中「归 A06 / 由 A06 定」的指针改为指向 §8 具体小节，§6「由 A06 定」一行填为耗尽码，范围表删去已决的两行，契约缺口 B08 行加 `TASK_ATTEMPTS_EXHAUSTED`。**转换表与不变量未改**（A03 核对 74 项回归通过） |
| `docs/decisions.md` | 新增 ADR-011；ADR-004 编号表下的指针行补一句「A06 对 ADR-006 的补充见 ADR-011」 |
| `docs/architecture.md` | **范围扩展**：目录表 workers 行写明「同机独立进程、经 SQLite 租约领取」；核心数据模型 SQLite 列表加 `TaskChunkCheckpoint`、`CourseLock`、`ModelCall`；数据流第 1 步补「经租约领取」 |
| `docs/tasks.md` | A06 认领行（DONE）、PLAN-D03 改为已关闭、A06 决定与后续项两条 |
| `docs/handoffs/claude-a06.md` | 本文件 |

**范围扩展说明**：清单给 A06 的文件锁是 `specs/task-processing.md` 与 `docs/decisions.md`。`architecture.md` 的数据模型与目录表若不同步，C01 建表时会缺三张表的指引；用户在本轮选择「规格 + ADR-011 + 同步架构」，扩展已写入认领行。未触碰 `src/`、`scripts/`、`tests/`、`.env.example`、`docs/integrations.md`、`docs/atomic-tasks.json`，未改其他 worktree。

## 二、裁定内容（签收人 ArvinHan，2026-09-23）

| 问题 | 决定 |
| --- | --- |
| 部署边界 | API 与 worker 为同机不同进程，共用 SQLite（WAL + `busy_timeout`）；`WORKER_PROCESSES` 默认 1；**不支持**跨机器、网络文件系统上的 SQLite、第二个队列 |
| 接管后续跑 | 块级检查点：`extracting` 按块续跑；`parsing`/`merging` 从阶段开头重跑；`persisting` 整段重跑，靠确定性 ID + 单个 Neo4j 事务 `MERGE` |
| 阶段级临时故障 | 存储不可用、模型熔断：主动释放租约并退避 30 秒 × 2^(attempt−1) 后重排，计入同一任务尝试上限 |

会话中由用户逐项选择的是以上三项与交付范围；四节设计（进程边界与租约、三层重试与失败码、各阶段幂等与课程写锁与中间产物、迁移备份与回滚）由用户逐节确认。租约 60 秒、块 2 次、任务 3 次、保留 7 天等默认值，以及 `TASK_ATTEMPTS_EXHAUSTED` 的命名，是本任务在已确认方向内定稿的细节，均可通过环境变量或 B08 调整。

**设计问答中的一处更正**：第二个问题（续跑粒度）的选项里我说 `merging`「便宜且确定」，不准确——E10 的重复裁决与定义归并也调用模型。已在设计第 3 节向用户说明，§8.4 改为 `merging` 重跑、模型结果靠 E 组的调用缓存避免重复计费。

## 三、验收对照（A06 验收矩阵）

| 验收条款 | 落点 | 结果 |
| --- | --- | --- |
| 明确单机/多进程边界 | §8.1（支持 / 不支持 / 时间基准）；ADR-011 决定 1；推翻条件 1、2 | 满足 |
| 重试上限 | §8.3 三层表、主动释放、正常退出、不重试集合、耗尽码；§8.8 默认值；LEASE-6、7、9、11 | 满足 |
| 去重 | §8.2 令牌防旧写与本地截止；§8.4 确定性 ID、块检查点、`MERGE`、`model_calls` 去重；LEASE-1、2、3、4、17 | 满足 |
| 迁移前有备份 / 回滚说明 | §8.7 六条；ADR-011 决定 8；LEASE-13、14、15 | 满足 |
| 输出「原子领取、超时接管、阶段重试规则」 | §8.2 领取条件与单语句领取、回收与接管；§8.3 | 满足 |
| 不改变 A03 的转换表与不变量 | §8 开头声明；回收与释放均映射到 T8/T9 或同阶段操作；A03 核对 74 项回归 ALL PASS | 满足 |
| 人工决策保留未签收标记 | 本轮决定已签收；未决事项（发布侧持锁时机→A04、缓存键→E 组、变量登记→A07、新错误码→B08、熔断状态接口→E04）均写明去向 | 满足 |

## 四、实际运行的命令与结果

```text
./scripts/verify.sh        改动前 exit 0；改动后 exit 0
git diff --check           改动前 exit 0；改动后 exit 0；行尾空白 grep exit 1（无）；占位 grep exit 1（无）
python3 check_a06.py . <978671e api.v1.yaml>      45 项 ALL PASS，exit 0
python3 negatives_a06.py <scratch> <worktree>     9 个篡改副本全部 exit 1、无崩溃，逐条报出（见下）
python3 check_a03.py . <978671e api.v1.yaml>      74 项 ALL PASS（A03 回归）
python3 negatives.py <scratch> <worktree>         A03 的 12 个负例全部 exit 1（回归）
python3 check_a02.py docs/architecture.md <978671e api.v1.yaml>   ALL PASS（A02 枚举表回归）
```

A06 负例：

| 篡改 | 被检出的项 |
| --- | --- |
| M1 领取条件放入 `awaiting_review` | 可领取条件只含 queued 与处理中阶段 |
| M2 §8.8 `TASK_MAX_ATTEMPTS` 默认改 5 | 默认值与 §8.3、ADR-011 不一致 |
| M3 删去迁移前备份一条 | 迁移前备份与回滚 |
| M4 §6 恢复「由 A06 定」 | 未决指针残留；`TASK_ATTEMPTS_EXHAUSTED` 未提议；缺口核实 |
| M5 把存储不可用列入不重试 | 不重试集合与阶段级临时故障相交 |
| M6 删除 LEASE-9 | 编号断档；实现方标注 |
| M7 架构数据模型漏 `CourseLock` | SQLite 数据模型缺新表 |
| M8 ADR-011 退避公式改为 60 秒 | 退避公式不一致 |
| M9 耗尽码改为未提议的 `WORKER_LOST` | §8 用到未存在也未提议的错误码 |

**核对脚本自身的修正**（均先发现、再修、再重跑）：

1. `MERGE` 被「反引号内大写词即错误码」规则误报，加入排除列表（与已排除的 `RETURNING` 同类）。
2. 第一次跑负例时 **M7 未被检出**：数据模型那一行后半句又点名了 `CourseLock`，整行搜索会命中。改为只检查句号前的表名列表后，M7 被检出。这是核对脚本的真漏洞，不是文档问题。
3. M9 的锚点写错（§8.3 表格里没有「报」字），修正锚点后重跑。
4. **A03 核对脚本改了一行**：原检查「PLAN-D03 标为部分关闭」写死了 A03 时刻的状态，A06 把它正式改为已关闭，该项放宽为「部分关闭或已关闭」。`docs/handoffs/claude-a03.md` 附录中的 A03 脚本未随之改动（那是 A03 交付时的版本）；A03 负例 N5 现报 1 项而非 2 项，因为架构文档多了两处指向规格的引用，「残留占位」一项仍检出。

脚本不入库（`tests/` 归测试 Agent），A06 两个脚本全文附在本文件附录。

## 五、接口 / 数据 / 配置变更

无运行时变更，无契约文件改动。受本决定约束的未来变更：

1. **B08**：`ErrorCode` 增加 `TASK_ATTEMPTS_EXHAUSTED`，与 ADR-010 的四个提议码同批；进入真源后同步 `architecture.md` 的 `ErrorCode` 行。
2. **SQLite 内部模型**（不上 wire）：任务行六个租约字段；`task_chunk_checkpoints`、`course_locks`、`model_calls` 三张表；T6 提交序号与快照水位（A03 已定）。由 C01/C06/C09/E04/E12/G02 的迁移创建，均须遵守 §8.7。
3. **配置**：`WORKER_PROCESSES`、`TASK_LEASE_SECONDS`、`TASK_MAX_ATTEMPTS`、`TASK_CHUNK_MAX_ATTEMPTS`、`TASK_ARTIFACT_RETENTION_DAYS`，登记归 A07。

## 六、未完成 / 风险

- **分支叠放**：本分支基于未合并的 A03（PR #5）。若 PR #5 在合并前再改 `specs/task-processing.md`（例如 Codex 复核 `6345ce1` 又提出问题），本分支需要变基或合并 A03 分支后重跑三套核对。
- **SQLite 写争用未实测**：心跳续约、块检查点、进度上报都写同一个库；多 worker 时 `busy_timeout` 是否够用只能在 C09/K04 实测，按推翻条件 2 处理。
- **单个 Neo4j 事务的规模未实测**：一份资料的草稿能否在一个事务内写完取决于资料规模，按推翻条件 3 处理。
- **`merging` 重跑的计费依赖 E 组缓存**：缓存未实现前，接管后的 `merging` 会重新调用裁决模型。
- **本地截止规则依赖同机单调时钟**：这是不支持跨机器的原因之一；K08 编排容器时 API 与 worker 必须同机、共享数据卷。
- **`persisting` 可见窗口**：Neo4j 提交与 T6 之间崩溃时，草稿短暂可见而任务未到 `awaiting_review`；最终失败由清理撤销，但窗口内教师可能看到这些节点。
- **未验证**：本节没有任何实现或自动化测试；LEASE-1～17 是 C01/C09/C10/E04/E12/F13/G04 的验收契约。

## 七、下一位 Agent 的首个动作

1. 请 Codex 按固定提交审查本轮四个已跟踪文件与本交接；若 A03 的 `6345ce1` 复核结论先出，先处理它再审本分支。
2. **C09**（依赖 C06、C08、A06）、**C01**（依赖 B06、A04、A06）的 A06 前置已满足，但各自还缺其他依赖。
3. **A04** 认领时须引用 §8.5 课程写锁，决定发布侧何时持锁。

## 八、回滚

仅文档改动，无持久层与依赖变更。提交后首选 `git revert <A06 交付提交>`。提交前手工恢复：

```text
git -C <本 worktree> checkout 6345ce1 -- docs/architecture.md docs/decisions.md docs/tasks.md specs/task-processing.md
rm <本 worktree>/docs/handoffs/claude-a06.md
```

不要使用 reset 或 stash 清理；stash 栈与其他 worktree 共享。

## 九、第二轮：Codex 审查修复（A06-R01 / A06-R02）

- **task_id**：A06-R01/R02 修复
- **状态**：DONE。修复方案由 ArvinHan 于 2026-09-23 在会话中选择并签收，记为 **ADR-011 修订 1**（决定 9～11）
- **review_status**：ready_for_review
- **worktree / 分支**：`.claude/worktrees/a04-f5f479`，分支 `claude/a06-r01-r02-fix`，base `50a15c9`（= 合入 PR #10 后的 `origin/main`）
- **审查报告**：主目录 `docs/reviews/codex-claude-a03fix-a06-ab04053-2026-09-23-0649z.md`（目标提交 `ab04053`，尚未入库）

**核对结论**：两条均成立，根因相同：`persisting` 先提交 Neo4j、后做 SQLite T6，内容在 T6 前与失败清理完成前都已可见。报告未提及的连带影响：教师读草稿不持锁，崩溃窗口内可看到或编辑未 T6 任务的内容；该任务无 T6 提交序号、本应在任务水位外，其内容却会进入 A04 发布快照（违反 A03 §3）。

| 选择（用户签收） | 否决 | 落点 |
| --- | --- | --- |
| 按任务记录贡献（`contrib_tasks`、`contrib_manual`、来源关联带 `task_id`），可见性由 SQLite 有效任务集合 V 决定；清理按贡献撤销 | 隔离暂存区后原子提升；有待清理任务时阻断读取与发布 | `specs/task-processing.md` I6、§8.4、LEASE-12、LEASE-18～23；`docs/decisions.md` ADR-011 修订 1；`specs/teacher-review-publish.md` V2、V3、PUB-35；`docs/architecture.md` 数据流第 2 步 |

**范围扩展**：`specs/teacher-review-publish.md` 的 V2 一句、V3 可见性前提与 PUB-35（A04 条文）、`docs/architecture.md` 数据流一句。原因：A04 发布读取草稿，若不同步写明「只取可见元素」，发布会成为唯一绕过可见性规则的读取方。

**验证**：

```text
./scripts/verify.sh                          exit 0
git add … && git diff --cached --check       exit 0
python3 check_a06.py（第一版）  .  api.v1.yaml
    修复前基线（origin/main 50a15c9）       exit 1：§8 错误码 ['COURSE_BUSY']
    本轮修订后                              exit 1：§8 错误码 ['COURSE_BUSY', 'RELATED_TO']
python3 check_a06.py（第二版，见附录 C）      正例 exit 0，55 项 ALL PASS
  N1 清理改回按创建标记删除                  exit 1
  N2 删去仓储必填参数                        exit 1
  N3 删除 LEASE-19                          exit 1
  N4 删去 A04 V3 可见性前提                  exit 1
A04 核对脚本（PUB 范围 1～35）               exit 0，ALL PASS
```

第一版的两项 FAIL 均为脚本启发式误报，不是规格缺陷：`COURSE_BUSY` 是 A04 提议的错误码（写在 A04 V10，PR #7 合并时在 §8.5 加注引入，main 基线即已失败）；`RELATED_TO` 是关系类型（本轮「已知限制」引用 ADR-009 降级）。第二版把关系类型排除在错误码之外，并承认 A04 V10 提议的错误码，其余断言与第一版相同，另加 11 项修订 1 断言。

**遗留**：
- 已知限制（写入 §8.4）：失败任务对他任务 AI 边的 ADR-009 降级不撤销；教师删除的关系可能被未提交任务以同一 ID 重新写出（归节点加锁待细化）。
- 草稿查询多一个必填参数 V，F02 的仓储接口随之变化；尚无实现或自动化测试。

**下一步**：请 Codex 按本轮提交复核 A06-R01/R02；修复另开一轮。

## 附录 A：`check_a06.py`（核对脚本全文）

用法：`python3 check_a06.py <repo 根目录> <api.v1.yaml>`；依赖 PyYAML。YAML 取自 `git show 978671e:src/contracts/api.v1.yaml`。A03 的检查不在此重复，另跑 `docs/handoffs/claude-a03.md` 附录的 `check_a03.py` 作回归（PLAN-D03 一项按第四节第 4 条放宽）。

```python
"""A06 验收核对：specs/task-processing.md §8 的内部一致性，以及与 §1～§7、ADR-011、架构文档、任务板的一致性。

用法：python3 check_a06.py <repo 根目录> <740adb 978671e 的 api.v1.yaml>
退出码：0 全部一致；1 有不一致（逐条打印）。依赖 PyYAML。
A03 的检查不在此重复，另跑 check_a03.py 作回归。
"""
import re
import sys
from pathlib import Path

import yaml

root, yaml_path = Path(sys.argv[1]), sys.argv[2]
spec = (root / "specs/task-processing.md").read_text(encoding="utf-8")
arch = (root / "docs/architecture.md").read_text(encoding="utf-8")
adr = (root / "docs/decisions.md").read_text(encoding="utf-8")
tasks = (root / "docs/tasks.md").read_text(encoding="utf-8")
schemas = yaml.safe_load(open(yaml_path, encoding="utf-8"))["components"]["schemas"]
failures = []


def check(ok, label):
    print(("PASS " if ok else "FAIL ") + label)
    if not ok:
        failures.append(label)


def section(text, start, end=None):
    body = text.split(start, 1)[1] if start in text else ""
    return body.split(end, 1)[0] if end and end in body else body


def norm(t):
    return re.sub(r"\s+", "", t)


PROCESSING = {"parsing", "extracting", "merging", "persisting"}
sec8 = section(spec, "## 8. 租约、重试与幂等", "## 验收矩阵")
before8 = spec.split("## 8. 租约、重试与幂等", 1)[0]
subs = {n: section(sec8, f"### 8.{n} ", f"### 8.{n + 1} ") for n in range(1, 10)}
adr11 = section(adr, "## ADR-011")

# ---------- 结构与占位 ----------
check(all(subs[n] for n in subs), "§8.1～§8.9 九个小节齐全")
check("A06 待补" not in spec and "本节由 A06 填写" not in spec, "§8 占位已替换")
check(not re.search(r"归 A06|由 A06 定|A06（补入|A06/E 组|A04/A06", before8), "§1～§7 不再有「归 A06 / 由 A06 定」一类未决指针")
check("ADR-011" in spec.split("\n", 5)[2], "规格状态行指向 ADR-011")

# ---------- 验收条款落点 ----------
s81, s82, s83, s84, s85, s86, s87, s88, s89 = (subs[n] for n in range(1, 10))
check("跨机器" in s81 and "网络文件系统" in s81 and "WORKER_PROCESSES" in s81 and "**不支持**" in s81, "单机/多进程边界：支持与不支持均写明")
check("TASK_CHUNK_MAX_ATTEMPTS" in s83 and "TASK_MAX_ATTEMPTS" in s83 and "L1" in s83 and "L2" in s83 and "L3" in s83, "重试上限：三层与上限变量")
check("model_calls" in s84 and "去重" in s84 and "MERGE" in s84 and "确定性" in s84, "去重：确定性 ID、MERGE、计费去重")
check("VACUUM INTO" in s87 and "integrity_check" in s87 and "回滚" in s87 and "停机迁移" in s87, "迁移前备份与回滚")

# ---------- 领取条件与回收只涉及合法阶段 ----------
cond = re.search(r"\*\*可领取条件\*\*.+", s82)
cond = cond.group(0) if cond else ""
claim_sets = [set(re.findall(r"([a-z_]+)", m)) for m in re.findall(r"stage ∈ \{([^}]+)\}", cond)]
claim_stages = set(re.findall(r"stage = ([a-z_]+)", cond)) | set().union(*claim_sets) if claim_sets else set()
check(claim_stages == {"queued"} | PROCESSING, f"可领取条件只含 queued 与处理中阶段 {sorted(claim_stages)}")
check("cancel_requested = false" in cond and "attempt < TASK_MAX_ATTEMPTS" in cond and "not_before" in cond, "可领取条件含取消、尝试上限与退避守卫")
reap = re.search(r"\*\*回收\*\*.+", s82)
reap_sets = [set(re.findall(r"([a-z_]+)", m)) for m in re.findall(r"stage ∈ \{([^}]+)\}", reap.group(0) if reap else "")]
check(reap_sets and reap_sets[0] == PROCESSING, "回收只作用于处理中阶段")
check("T8" in s82 and "T9" in s82 and "stage ≠ persisting" in s82, "回收动作映射到 T8/T9，且写明取消不会落在 persisting")
check("I1" in sec8.split("### 8.1", 1)[0] and "不改变" in sec8.split("### 8.1", 1)[0], "§8 声明不改变 §1～§7 转换表与不变量")

# ---------- 配置：默认值在 §8.8、正文与 ADR-011 一致 ----------
cfg = dict(re.findall(r"\| `([A-Z_]+)` \| [^|]+ \| (\d+) \|", s88))
check(set(cfg) == {"WORKER_PROCESSES", "TASK_LEASE_SECONDS", "TASK_MAX_ATTEMPTS", "TASK_CHUNK_MAX_ATTEMPTS", "TASK_ARTIFACT_RETENTION_DAYS"}, f"§8.8 列出五个变量 {sorted(cfg)}")
mentioned = set(re.findall(r"`?(WORKER_PROCESSES|TASK_[A-Z_]+)`?", sec8)) - {"TASK_ATTEMPTS_EXHAUSTED", "TASK_MAX_FAILED_CHUNK_RATIO"}
check(mentioned <= set(cfg), f"§8 正文提到的变量都在 §8.8 {sorted(mentioned - set(cfg))}")
check(all(v in adr11 for v in cfg), "ADR-011 列出全部五个变量")
expect = {
    "WORKER_PROCESSES": [(s81, r"默认 (\d+)"), (adr11, r"`WORKER_PROCESSES` 默认 (\d+)")],
    "TASK_MAX_ATTEMPTS": [(s83, r"`TASK_MAX_ATTEMPTS`，默认 (\d+)"), (adr11, r"L3 任务，默认 (\d+)")],
    "TASK_CHUNK_MAX_ATTEMPTS": [(s83, r"`TASK_CHUNK_MAX_ATTEMPTS`，默认 (\d+)"), (adr11, r"L2 块，默认 (\d+)")],
    "TASK_LEASE_SECONDS": [(adr11, r"`L` 默认 (\d+) 秒")],
    "TASK_ARTIFACT_RETENTION_DAYS": [(s86, r"默认 (\d+)"), (adr11, r"保留 (\d+) 天")],
}
for var, places in expect.items():
    got = [re.search(pat, txt).group(1) if re.search(pat, txt) else None for txt, pat in places]
    check(all(g == cfg.get(var) for g in got), f"{var} 默认值一致：§8.8={cfg.get(var)}，其他处={got}")
check(norm("30 秒 × 2^(attempt − 1)") in norm(s83) and norm("30 秒 × 2^(attempt−1)") in norm(adr11), "退避公式在 §8.3 与 ADR-011 一致")

# ---------- 错误码 ----------
retryable = {"STORAGE_UNAVAILABLE", "LLM_UNAVAILABLE"}
no_retry = re.search(r"\*\*不重试、直接 T9 的错误\*\*：(.+)", s83)
no_retry = set(re.findall(r"`([A-Z_]+)`", no_retry.group(1))) if no_retry else set()
check(no_retry and not (no_retry & retryable), f"不重试集合与阶段级临时故障不相交 {sorted(no_retry)}")
code_row = re.search(r"\| `ErrorCode` \| (.+?) \| UPPER \|", arch)
arch_codes = set(re.findall(r"`([A-Z_]+)`", code_row.group(1))) if code_row else set()
sec6 = section(spec, "## 6. 失败码", "## 7.")
proposed = {re.search(r"\| `([A-Z_]+)` \|", l).group(1) for l in sec6.splitlines() if "提议新增" in l and re.search(r"\| `([A-Z_]+)` \|", l)}
codes8 = set(re.findall(r"`([A-Z][A-Z_]{3,})`", sec8)) - {"WORKER_PROCESSES", "RETURNING", "MERGE"} - {c for c in re.findall(r"`([A-Z][A-Z_]{3,})`", sec8) if c.startswith("TASK_") and c != "TASK_ATTEMPTS_EXHAUSTED"}
check(codes8 <= arch_codes | proposed, f"§8 用到的错误码都已存在或已在 §6 提议 {sorted(codes8 - arch_codes - proposed)}")
check("TASK_ATTEMPTS_EXHAUSTED" in proposed and "TASK_ATTEMPTS_EXHAUSTED" not in schemas["ErrorCode"]["enum"], "TASK_ATTEMPTS_EXHAUSTED 在 §6 提议且真源尚无（缺口真实）")
gap = section(spec, "## 交给后续任务的契约缺口")
check("TASK_ATTEMPTS_EXHAUSTED" in gap, "契约缺口表的 B08 行含 TASK_ATTEMPTS_EXHAUSTED")

# ---------- 验收 LEASE-n ----------
ids = [int(n) for n in re.findall(r"\*\*LEASE-(\d+)\*\*", s89)]
check(sorted(ids) == list(range(1, len(ids) + 1)) and len(set(ids)) == len(ids) and len(ids) >= 10, f"LEASE 编号无重复且覆盖 1～{len(ids)}")
cats = re.split(r"- (成功路径|边界路径|失败路径)\n", s89)
counts = {cats[i]: len(re.findall(r"\*\*LEASE-", cats[i + 1])) for i in range(1, len(cats) - 1, 2)}
check(all(counts.get(c, 0) >= 1 for c in ("成功路径", "边界路径", "失败路径")), f"成功/边界/失败各至少一例 {counts}")
check(all(re.search(r"\*\*LEASE-\d+\*\*（[A-Z0-9、 ]+）", l) for l in s89.splitlines() if "**LEASE-" in l), "每条 LEASE 标注实现方")
for kw, label in [("同时领取", "并发领取"), ("旧令牌", "旧令牌拒写"), ("熔断", "熔断重排"), ("尝试耗尽", "尝试耗尽"),
                  ("已请求取消", "过期且已请求取消"), ("清理", "persisting 清理"), ("迁移", "迁移拒绝"), ("integrity_check", "备份完整性"),
                  ("恢复演练", "恢复演练"), ("课程写锁", "课程写锁")]:
    check(kw in s89, f"LEASE 覆盖：{label}")

# ---------- 跨文档 ----------
check(bool(adr11) and "**签收**：ArvinHan 2026-09-23" in adr11 and adr.index("## ADR-010") < adr.index("## ADR-011"), "ADR-011 存在、有签收行、位于 ADR-010 之后")
plan = tasks.split("PLAN-D03", 1)[1].split("\n", 1)[0] if "PLAN-D03" in tasks else ""
check("已关闭" in plan and "ADR-011" in plan, "PLAN-D03 已关闭并引用 ADR-011")
check(re.search(r"\| A06 \| [^|]+ \| 定义 worker 租约和幂等机制", tasks) is not None, "任务板有 A06 认领行")
wrow = next((l for l in arch.splitlines() if l.startswith("| `src/backend/app/workers/`")), "")
check("独立进程" in wrow and "§8" in wrow, "architecture workers 行写明独立进程并指向 §8")
model = next((l for l in arch.splitlines() if l.startswith("- SQLite：")), "").split("。", 1)[0]  # 只看表名列表，不看后半句的说明
check(all(t in model for t in ("TaskChunkCheckpoint", "CourseLock", "ModelCall")), "architecture SQLite 数据模型列出新表")
check("A04" in s85 and "何时" in s85, "课程写锁把发布侧持锁时机留给 A04")

if failures:
    print("\n".join(["", "FAILURES:"] + failures))
    sys.exit(1)
print("\nALL PASS")
```

## 附录 B：`negatives_a06.py`（负例脚本全文）

用法：`python3 negatives_a06.py <scratch 目录（含 check_a06.py 与 api.v1.yaml）> <worktree>`。每个用例把四份文档复制到 `<scratch>/neg6/<编号>/` 后只改一处。

```python
import shutil, subprocess, sys
from pathlib import Path
sp, wt = Path(sys.argv[1]), Path(sys.argv[2])
files = ["specs/task-processing.md", "docs/architecture.md", "docs/decisions.md", "docs/tasks.md"]
cases = {
 "M1 领取条件放入 awaiting_review": ("specs/task-processing.md",
   "stage ∈ {parsing, extracting, merging, persisting} AND (lease_expires_at IS NULL OR lease_expires_at < 现在)))`",
   "stage ∈ {parsing, extracting, merging, persisting, awaiting_review} AND (lease_expires_at IS NULL OR lease_expires_at < 现在)))`"),
 "M2 §8.8 默认尝试次数与正文不符": ("specs/task-processing.md", "| `TASK_MAX_ATTEMPTS` | 整数，≥ 1 | 3 |", "| `TASK_MAX_ATTEMPTS` | 整数，≥ 1 | 5 |"),
 "M3 删去迁移前备份": ("specs/task-processing.md",
   "2. **迁移前备份**：执行 `VACUUM INTO '<数据目录>/backups/<UTC 时间>-before-<迁移号>.sqlite'`，再对副本执行 `PRAGMA integrity_check`，结果必须为 `ok`，否则中止迁移，原库不变。\n",
   ""),
 "M4 §6 恢复「由 A06 定」": ("specs/task-processing.md",
   "| 连续租约过期（崩溃、卡死）导致尝试耗尽 | 任意处理中阶段 | `TASK_ATTEMPTS_EXHAUSTED` | `attempts`、`stage` | **提议新增**（A06，§8.3） |",
   "| 租约接管或阶段重试耗尽 | 任意处理中阶段 | 由 A06 定 | — | 预留 |"),
 "M5 存储不可用列入不重试": ("specs/task-processing.md",
   "**不重试、直接 T9 的错误**：`DOCUMENT_UNREADABLE`、", "**不重试、直接 T9 的错误**：`STORAGE_UNAVAILABLE`、`DOCUMENT_UNREADABLE`、"),
 "M6 删除 LEASE-9": ("specs/task-processing.md", "**LEASE-9**", "**LEASE-X**"),
 "M7 架构数据模型漏 CourseLock": ("docs/architecture.md", "`TaskChunkCheckpoint`、`CourseLock`、`ModelCall`、`GraphVersion`", "`TaskChunkCheckpoint`、`ModelCall`、`GraphVersion`"),
 "M8 ADR-011 退避公式不一致": ("docs/decisions.md", "退避 30 秒 × 2^(attempt−1) 后重排", "退避 60 秒 × 2^(attempt−1) 后重排"),
 "M9 未知错误码": ("specs/task-processing.md", "| `TASK_ATTEMPTS_EXHAUSTED`（提议新增，交 B08） |", "| `WORKER_LOST`（提议新增，交 B08） |"),
}
for name, (rel, old, new) in cases.items():
    d = sp / "neg6" / name.split()[0]
    if d.exists(): shutil.rmtree(d)
    for f in files:
        (d / f).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(wt / f, d / f)
    text = (d / rel).read_text(encoding="utf-8")
    assert text.count(old) == 1, (name, old[:40])
    (d / rel).write_text(text.replace(old, new), encoding="utf-8")
    r = subprocess.run([sys.executable, str(sp / "check_a06.py"), str(d), str(sp / "api.v1.yaml")], capture_output=True, text=True)
    fails = [l[5:] for l in r.stdout.splitlines() if l.startswith("FAIL ")]
    print(f"{name}: exit={r.returncode} crashed={'Traceback' in r.stderr} fails={len(fails)}")
    for f in fails: print("    -", f)
```

## 附录 C：`check_a06.py` 第二版（修订 1 核对）

用法同附录 A：`python3 check_a06.py <仓库根目录> <api.v1.yaml>`；第二版另读 `specs/teacher-review-publish.md`。

```python
"""A06 验收核对：specs/task-processing.md §8 的内部一致性，以及与 §1～§7、ADR-011、架构文档、任务板的一致性。

用法：python3 check_a06.py <repo 根目录> <740adb 978671e 的 api.v1.yaml>
退出码：0 全部一致；1 有不一致（逐条打印）。依赖 PyYAML。
A03 的检查不在此重复，另跑 check_a03.py 作回归。
"""
import re
import sys
from pathlib import Path

import yaml

root, yaml_path = Path(sys.argv[1]), sys.argv[2]
spec = (root / "specs/task-processing.md").read_text(encoding="utf-8")
arch = (root / "docs/architecture.md").read_text(encoding="utf-8")
adr = (root / "docs/decisions.md").read_text(encoding="utf-8")
tasks = (root / "docs/tasks.md").read_text(encoding="utf-8")
schemas = yaml.safe_load(open(yaml_path, encoding="utf-8"))["components"]["schemas"]
failures = []


def check(ok, label):
    print(("PASS " if ok else "FAIL ") + label)
    if not ok:
        failures.append(label)


def section(text, start, end=None):
    body = text.split(start, 1)[1] if start in text else ""
    return body.split(end, 1)[0] if end and end in body else body


def norm(t):
    return re.sub(r"\s+", "", t)


PROCESSING = {"parsing", "extracting", "merging", "persisting"}
sec8 = section(spec, "## 8. 租约、重试与幂等", "## 验收矩阵")
before8 = spec.split("## 8. 租约、重试与幂等", 1)[0]
subs = {n: section(sec8, f"### 8.{n} ", f"### 8.{n + 1} ") for n in range(1, 10)}
adr11 = section(adr, "## ADR-011")

# ---------- 结构与占位 ----------
check(all(subs[n] for n in subs), "§8.1～§8.9 九个小节齐全")
check("A06 待补" not in spec and "本节由 A06 填写" not in spec, "§8 占位已替换")
check(not re.search(r"归 A06|由 A06 定|A06（补入|A06/E 组|A04/A06", before8), "§1～§7 不再有「归 A06 / 由 A06 定」一类未决指针")
check("ADR-011" in spec.split("\n", 5)[2], "规格状态行指向 ADR-011")

# ---------- 验收条款落点 ----------
s81, s82, s83, s84, s85, s86, s87, s88, s89 = (subs[n] for n in range(1, 10))
check("跨机器" in s81 and "网络文件系统" in s81 and "WORKER_PROCESSES" in s81 and "**不支持**" in s81, "单机/多进程边界：支持与不支持均写明")
check("TASK_CHUNK_MAX_ATTEMPTS" in s83 and "TASK_MAX_ATTEMPTS" in s83 and "L1" in s83 and "L2" in s83 and "L3" in s83, "重试上限：三层与上限变量")
check("model_calls" in s84 and "去重" in s84 and "MERGE" in s84 and "确定性" in s84, "去重：确定性 ID、MERGE、计费去重")
check("VACUUM INTO" in s87 and "integrity_check" in s87 and "回滚" in s87 and "停机迁移" in s87, "迁移前备份与回滚")

# ---------- 领取条件与回收只涉及合法阶段 ----------
cond = re.search(r"\*\*可领取条件\*\*.+", s82)
cond = cond.group(0) if cond else ""
claim_sets = [set(re.findall(r"([a-z_]+)", m)) for m in re.findall(r"stage ∈ \{([^}]+)\}", cond)]
claim_stages = set(re.findall(r"stage = ([a-z_]+)", cond)) | set().union(*claim_sets) if claim_sets else set()
check(claim_stages == {"queued"} | PROCESSING, f"可领取条件只含 queued 与处理中阶段 {sorted(claim_stages)}")
check("cancel_requested = false" in cond and "attempt < TASK_MAX_ATTEMPTS" in cond and "not_before" in cond, "可领取条件含取消、尝试上限与退避守卫")
reap = re.search(r"\*\*回收\*\*.+", s82)
reap_sets = [set(re.findall(r"([a-z_]+)", m)) for m in re.findall(r"stage ∈ \{([^}]+)\}", reap.group(0) if reap else "")]
check(reap_sets and reap_sets[0] == PROCESSING, "回收只作用于处理中阶段")
check("T8" in s82 and "T9" in s82 and "stage ≠ persisting" in s82, "回收动作映射到 T8/T9，且写明取消不会落在 persisting")
check("I1" in sec8.split("### 8.1", 1)[0] and "不改变" in sec8.split("### 8.1", 1)[0], "§8 声明不改变 §1～§7 转换表与不变量")

# ---------- 配置：默认值在 §8.8、正文与 ADR-011 一致 ----------
cfg = dict(re.findall(r"\| `([A-Z_]+)` \| [^|]+ \| (\d+) \|", s88))
check(set(cfg) == {"WORKER_PROCESSES", "TASK_LEASE_SECONDS", "TASK_MAX_ATTEMPTS", "TASK_CHUNK_MAX_ATTEMPTS", "TASK_ARTIFACT_RETENTION_DAYS"}, f"§8.8 列出五个变量 {sorted(cfg)}")
mentioned = set(re.findall(r"`?(WORKER_PROCESSES|TASK_[A-Z_]+)`?", sec8)) - {"TASK_ATTEMPTS_EXHAUSTED", "TASK_MAX_FAILED_CHUNK_RATIO"}
check(mentioned <= set(cfg), f"§8 正文提到的变量都在 §8.8 {sorted(mentioned - set(cfg))}")
check(all(v in adr11 for v in cfg), "ADR-011 列出全部五个变量")
expect = {
    "WORKER_PROCESSES": [(s81, r"默认 (\d+)"), (adr11, r"`WORKER_PROCESSES` 默认 (\d+)")],
    "TASK_MAX_ATTEMPTS": [(s83, r"`TASK_MAX_ATTEMPTS`，默认 (\d+)"), (adr11, r"L3 任务，默认 (\d+)")],
    "TASK_CHUNK_MAX_ATTEMPTS": [(s83, r"`TASK_CHUNK_MAX_ATTEMPTS`，默认 (\d+)"), (adr11, r"L2 块，默认 (\d+)")],
    "TASK_LEASE_SECONDS": [(adr11, r"`L` 默认 (\d+) 秒")],
    "TASK_ARTIFACT_RETENTION_DAYS": [(s86, r"默认 (\d+)"), (adr11, r"保留 (\d+) 天")],
}
for var, places in expect.items():
    got = [re.search(pat, txt).group(1) if re.search(pat, txt) else None for txt, pat in places]
    check(all(g == cfg.get(var) for g in got), f"{var} 默认值一致：§8.8={cfg.get(var)}，其他处={got}")
check(norm("30 秒 × 2^(attempt − 1)") in norm(s83) and norm("30 秒 × 2^(attempt−1)") in norm(adr11), "退避公式在 §8.3 与 ADR-011 一致")

# ---------- 错误码 ----------
retryable = {"STORAGE_UNAVAILABLE", "LLM_UNAVAILABLE"}
no_retry = re.search(r"\*\*不重试、直接 T9 的错误\*\*：(.+)", s83)
no_retry = set(re.findall(r"`([A-Z_]+)`", no_retry.group(1))) if no_retry else set()
check(no_retry and not (no_retry & retryable), f"不重试集合与阶段级临时故障不相交 {sorted(no_retry)}")
code_row = re.search(r"\| `ErrorCode` \| (.+?) \| UPPER \|", arch)
arch_codes = set(re.findall(r"`([A-Z_]+)`", code_row.group(1))) if code_row else set()
sec6 = section(spec, "## 6. 失败码", "## 7.")
proposed = {re.search(r"\| `([A-Z_]+)` \|", l).group(1) for l in sec6.splitlines() if "提议新增" in l and re.search(r"\| `([A-Z_]+)` \|", l)}
codes8 = set(re.findall(r"`([A-Z][A-Z_]{3,})`", sec8)) - {"WORKER_PROCESSES", "RETURNING", "MERGE"} - {c for c in re.findall(r"`([A-Z][A-Z_]{3,})`", sec8) if c.startswith("TASK_") and c != "TASK_ATTEMPTS_EXHAUSTED"}
# 第二版：关系类型不是错误码；A04 在 teacher-review-publish V10 提议的错误码也算已提议
trp = (root / "specs/teacher-review-publish.md").read_text(encoding="utf-8")
v10 = section(trp, "### V10 ", "### V11 ")
a04_proposed = {c for c in ("PUBLISH_IN_PROGRESS", "COURSE_BUSY") if c in v10}
codes8 = codes8 - set(schemas["RelationType"]["enum"])
check(codes8 <= arch_codes | proposed | a04_proposed, f"§8 用到的错误码都已存在或已在 §6 / A04 V10 提议 {sorted(codes8 - arch_codes - proposed - a04_proposed)}")
check("TASK_ATTEMPTS_EXHAUSTED" in proposed and "TASK_ATTEMPTS_EXHAUSTED" not in schemas["ErrorCode"]["enum"], "TASK_ATTEMPTS_EXHAUSTED 在 §6 提议且真源尚无（缺口真实）")
gap = section(spec, "## 交给后续任务的契约缺口")
check("TASK_ATTEMPTS_EXHAUSTED" in gap, "契约缺口表的 B08 行含 TASK_ATTEMPTS_EXHAUSTED")

# ---------- 验收 LEASE-n ----------
ids = [int(n) for n in re.findall(r"\*\*LEASE-(\d+)\*\*", s89)]
check(sorted(ids) == list(range(1, len(ids) + 1)) and len(set(ids)) == len(ids) and len(ids) >= 10, f"LEASE 编号无重复且覆盖 1～{len(ids)}")
cats = re.split(r"- (成功路径|边界路径|失败路径)\n", s89)
counts = {cats[i]: len(re.findall(r"\*\*LEASE-", cats[i + 1])) for i in range(1, len(cats) - 1, 2)}
check(all(counts.get(c, 0) >= 1 for c in ("成功路径", "边界路径", "失败路径")), f"成功/边界/失败各至少一例 {counts}")
check(all(re.search(r"\*\*LEASE-\d+\*\*（[A-Z0-9、 ]+）", l) for l in s89.splitlines() if "**LEASE-" in l), "每条 LEASE 标注实现方")
for kw, label in [("同时领取", "并发领取"), ("旧令牌", "旧令牌拒写"), ("熔断", "熔断重排"), ("尝试耗尽", "尝试耗尽"),
                  ("已请求取消", "过期且已请求取消"), ("清理", "persisting 清理"), ("迁移", "迁移拒绝"), ("integrity_check", "备份完整性"),
                  ("恢复演练", "恢复演练"), ("课程写锁", "课程写锁")]:
    check(kw in s89, f"LEASE 覆盖：{label}")

# ---------- 跨文档 ----------
check(bool(adr11) and "**签收**：ArvinHan 2026-09-23" in adr11 and adr.index("## ADR-010") < adr.index("## ADR-011"), "ADR-011 存在、有签收行、位于 ADR-010 之后")
plan = tasks.split("PLAN-D03", 1)[1].split("\n", 1)[0] if "PLAN-D03" in tasks else ""
check("已关闭" in plan and "ADR-011" in plan, "PLAN-D03 已关闭并引用 ADR-011")
check(re.search(r"\| A06 \| [^|]+ \| 定义 worker 租约和幂等机制", tasks) is not None, "任务板有 A06 认领行")
wrow = next((l for l in arch.splitlines() if l.startswith("| `src/backend/app/workers/`")), "")
check("独立进程" in wrow and "§8" in wrow, "architecture workers 行写明独立进程并指向 §8")
model = next((l for l in arch.splitlines() if l.startswith("- SQLite：")), "").split("。", 1)[0]  # 只看表名列表，不看后半句的说明
check(all(t in model for t in ("TaskChunkCheckpoint", "CourseLock", "ModelCall")), "architecture SQLite 数据模型列出新表")
check("A04" in s85 and "何时" in s85, "课程写锁把发布侧持锁时机留给 A04")

# ---------- 第二版：修订 1（Codex A06-R01/R02） ----------
i6 = next((l for l in spec.splitlines() if l.startswith("- **I6** ")), "")
check("一律不可见" in i6 and "不依赖清理" in i6, "R02：I6 由可见性保证、不依赖清理")
check("`contrib_tasks`" in s84 and "`contrib_manual`" in s84, "R01：§8.4 定义贡献字段")
check("先撤销本任务此前尝试留下的全部贡献" in s84, "R01：persisting 第 1 步先撤销旧贡献")
check("撤销 `created_by_task` 等于本任务" not in s84 and "再删除已无任何贡献" in s84, "R01：清理按贡献撤销，只删无贡献元素")
check("**有效任务集合 V**" in s84 and "缺少该参数的草稿查询被拒绝执行" in s84, "R02：有效任务集合 V 与仓储必填参数")
check(all(k in s84 for k in ("审核队列", "融合候选", "A04 发布")), "R02：可见性过滤覆盖审核、融合与发布")
l18 = next((l for l in s89.splitlines() if "**LEASE-18**" in l), "")
l19 = next((l for l in s89.splitlines() if "**LEASE-19**" in l), "")
check("A06-R01" in l18 and "复用" in l18, "R01 回归用例 LEASE-18")
check("A06-R02" in l19 and "cleanup_pending" in l19, "R02 回归用例 LEASE-19")
adr11r = section(adr, "### ADR-011 修订 1", "## ADR-012")
check(bool(adr11r) and "**签收**：ArvinHan 2026-09-23" in adr11r, "ADR-011 修订 1 存在、位于 ADR-012 之前且已签收")
v3 = section(trp, "### V3 ", "### V4 ")
check("**可见性前提**" in v3 and "**PUB-35**" in trp, "A04 V3 可见性前提与 PUB-35")

if failures:
    print("\n".join(["", "FAILURES:"] + failures))
    sys.exit(1)
print("\nALL PASS")
```
