# A02：统一路径前缀和领域枚举

- **task_id**：A02（`docs/atomic-task-plan.md` / `docs/atomic-tasks.json`）
- **状态**：DONE。决定已由 ArvinHan 于 2026-09-22 在会话中逐项选择并签收，记为 **ADR-009**；PLAN-D01 至此全部关闭
- **review_status**：ready_for_review
- **worktree**：`/Users/arvinhan/Desktop/SmartSketch/.claude/worktrees/adoring-sinoussi-709263`
- **分支 / base**：`claude/a02-start-4064b7` / base `bfa236c`
- **head_commit**：本文件与四个文档随同一个交付提交入库（`git log -1 -- docs/handoffs/claude-a02.md` 可查），review 的固定基线取该提交。内容指纹：`git diff bfa236c <该提交> -- docs/architecture.md docs/decisions.md docs/tasks.md specs/course-knowledge-graph.md | shasum -a 256` 前 16 位 `da3e81763e33d579`
- **类型**：仅文档任务，无代码、无依赖变更、无合并、无网络调用

## 一、范围与交付物

| 文件 | 改动 |
| --- | --- |
| `docs/architecture.md` | 新增「API 前缀与 wire 枚举（A02 / ADR-009）」：前缀规则、大小写规则、wire 枚举表（12 个具名枚举 + 内联枚举 + 两路 SSE 事件名）、「文档用语 → wire 值」映射；数据流第 2、5 步补成环分流与 wire 值指针 |
| `specs/course-knowledge-graph.md` | 关系字段补 `status`、`source`；新增「前置关系成环处理」（参与边、可降级边、四行分流表、5 步降级算法、DAG-1～11 验收）；验收 2 补 `persisting`/`cancelled`；验收 4 区分人工与自动；「待细化」记录契约缺口 |
| `docs/decisions.md` | **范围扩展**：新增 ADR-009（背景/方案对比/决定/后果/推翻条件/签收）；ADR-004 前缀说明下加一行指针，ADR-004 其余正文未改 |
| `docs/tasks.md` | A02 认领行（DONE）、PLAN-D01 改为已关闭、A01 说明同步、A02 决定与后续项两条 |
| `docs/handoffs/claude-a02.md` | 本文件 |

**范围扩展说明**：清单给 A02 的文件锁只有规格与架构两份。AGENTS.md §6 要求「已确认选择写入 `docs/decisions.md`」，用户在本轮直接签收，因此新增 ADR-009。扩展已写入任务板认领行。未触碰 `src/`、`scripts/`、`AGENTS.md`、`.claude/rules/`、`docs/atomic-tasks.json`，也未改任何其他 worktree。

## 二、裁定内容（签收人 ArvinHan，2026-09-22）

| 问题 | 决定 |
| --- | --- |
| API 前缀 | `/api/v1`，唯一例外 `GET /health`；S2 的 `/api/...` 是缩写。ADR-004 端点表不改 |
| 大小写 | 只有 `ErrorCode`、`RelationType` 用 UPPER_SNAKE；其余 wire 枚举（含 SSE 事件名、判别字段）一律 lower_snake |
| 未覆盖 | `NOT_COVERED` 是共同契约中的概念名；wire 为 HTTP 200 + `status: "not_covered"` + `reason` + `citations: []`。AGENTS.md / ADR-003 / 角色规则措辞不改，由映射表对照 |
| 任务状态 | `TaskStage` 9 值含 `persisting`、`cancelled`；终态 `completed`/`failed`/`cancelled`；转换与取消语义归 A03 |
| 成环 | 人工编辑 → 409 `CYCLE_DETECTED`，不自动修复；自动候选 → 环上未经教师确认的 `ai` 边（`status ∈ {draft, low_confidence}`）中置信度最低者（并列取 `id` 最小）降为 `RELATED_TO` + `low_confidence` 送审，逐环重复，任务继续；环上无可降级边 → 任务 `failed`；发布时有环 → 409 `PUBLISH_BLOCKED` |

实施细化（用户确认的方向内、由本任务定稿）：`Relation` 没有 `locked` 字段，所以「受保护的边」定义为 `source = manual` 或 `status = approved`；`status = rejected` 的边不参与环检测；自动候选自环按 S2 在规则校验阶段删除，不走降级。

## 三、验收对照（A02 验收矩阵）

| 验收条款 | 落点 | 结果 |
| --- | --- | --- |
| API 前缀与 wire 枚举表 | `docs/architecture.md`「API 前缀与 wire 枚举」 | 满足；对 `740adb` `978671e` 真源逐值核对 ALL PASS（见第四节） |
| 同步 `persisting` | 枚举表 `TaskStage`；规格验收 2；映射表「入库中」 | 满足 |
| 同步 `cancelled` | 同上；映射表「已取消 → `cancelled`（双 l）」；大小写规则禁止 `canceled` | 满足 |
| 同步「未覆盖」大小写 | 大小写规则 + 映射表第一行；数据流第 5 步；ADR-009 决定 3 | 满足 |
| 人工编辑造环与自动候选降级区别明确 | 规格「前置关系成环处理」分流表 + 降级算法 + DAG-1～11（成功 2 / 边界 7 / 失败 2） | 满足 |
| 人工决策保留未签收标记 | 本轮决定已由用户签收；文档中签收状态与签收行齐全；未签收的遗留项（B11 字段、`SourceChunk`/`Chunk`）均写明「不裁定」并指定去向 | 满足 |

## 四、实际运行的命令与结果

```text
./scripts/verify.sh        改动前 exit 0；改动后 exit 0（Scaffold verification passed）
git diff --check           改动前 exit 0；改动后 exit 0
python3 check_a02.py docs/architecture.md <740adb 978671e 的 api.v1.yaml>
                           exit 0：12 个具名枚举逐值逐序一致、大小写规则、7 项判别/内联值、
                           22 路径 / 29 操作前缀、CYCLE_DETECTED 与 PUBLISH_BLOCKED 存在 —— ALL PASS
python3 check_a02.py docs/architecture.md <ff30e0 6ccbe5e 的 api.v1.yaml>
                           exit 1（预期负例）：缺 NotCoveredReason、无判别联合 const、21 条 /api/ 前缀违规
python3 check_a02.py docs/architecture.md <740adb YAML 副本，把 TaskStage 的 cancelled 改成 CANCELLED>
                           exit 1（预期负例）：取值不一致 + 大小写违规，均被逐条报出
```

YAML 通过 `git show 978671e:src/contracts/api.v1.yaml` / `git show 6ccbe5e:...` 导出到会话 scratch 目录，未改动任何 worktree。核对脚本不入库（`tests/` 归测试 Agent，且 main 尚无 YAML）；全文附在本文件附录，可复现。第一版脚本在负例上以 `KeyError` 崩溃退出，虽然也是非 0，但不能证明逐条报错，已改为缺失即记失败后重跑，上面是修正后的结果。

## 五、接口 / 数据 / 配置变更

无运行时变更，无契约文件改动（main 尚无 `api.v1.yaml`）。受本决定约束的未来变更：

1. `api.v1.yaml` 导入 main（A10）时，枚举必须与架构文档表逐值一致。现 `740adb` 版本已一致，无需改动。
2. **B11**：`Relation` 须新增字段记录降级原类型与环路，先改 YAML 再生成。F13（`persisting` 阶段）依赖它。
3. F05（DAG 纯函数）须能返回环路，并能按 ADR-009 规则选出待降级边；F06（人工写入）只用前者。

## 六、未完成 / 风险

- **契约缺口（B11）**：降级边目前没有结构化字段向教师解释来源，审核体验依赖 B11 补字段。
- **`740adb` 文档笔误**：`src/contracts/README.md` 写 `not_covered_reason`，YAML 字段是 `reason`；随 A10 导入或 B13 修正。
- **ADR-005 字面冲突**：`740adb` ADR-005 第 1 条把「前置关系成环被拒」列为 `persisting` 失败原因，现被 ADR-009 收窄为「环上无可降级边」。A10 导入 ADR-005 时须加注指向 ADR-009。
- **ADR-008 复核**：与本条一致；唯一差异是 Neo4j 文本块标签 `SourceChunk`（main 架构）与 `Chunk`（ADR-008），非 wire 枚举，未裁定，交 A10。
- **合并提示**：`740adb` 的 `specs/course-knowledge-graph.md` 已有验收 7～10 且改写了验收 2；本轮把成环验收单独编号为 DAG-1～11，避免与其序号冲突，但验收 2、4 两行在 A10 合并时会有文本冲突，按本轮版本（含 A02 分流）为准。
- **未验证**：降级算法只有规格与验收用例，没有实现或自动化测试（属 F05/F13）；规格中的端点路径以 `740adb` 真源为准，main 尚无真源。

## 七、下一位 Agent 的首个动作

1. 请 Codex 按固定指纹审查本轮四个已跟踪文件与本交接；修复另开一轮。
2. **A03**（任务生命周期与取消协议）依赖 A02，现可认领；ADR-009 已把 9 个 `TaskStage` 值定死，A03 只定转换与竞争语义。
3. B11 认领时先处理第五节第 2 条的字段缺口。

## 八、回滚

仅文档改动，无持久层与依赖变更。首选 `git revert <A02 交付提交>`。若需在提交前的工作区状态下手工恢复，只还原本任务的四个文件并删除本文件：

```text
git -C <本 worktree> checkout bfa236c -- docs/architecture.md docs/decisions.md docs/tasks.md specs/course-knowledge-graph.md
rm <本 worktree>/docs/handoffs/claude-a02.md
```

不要使用 reset 或 stash 清理；stash 栈与其他 worktree 共享。

## 附录：`check_a02.py`（核对脚本全文）

用法：`python3 check_a02.py <architecture.md> <api.v1.yaml>`；依赖 PyYAML。

```python
"""A02 验收核对：architecture.md 的 wire 枚举表 vs 740adb 978671e 的 api.v1.yaml。

用法：python3 check_a02.py <architecture.md> <api.v1.yaml>
退出码：0 全部一致；1 有不一致（逐条打印）。
"""
import re
import sys

import yaml

arch_path, yaml_path = sys.argv[1], sys.argv[2]
arch = open(arch_path, encoding="utf-8").read()
spec = yaml.safe_load(open(yaml_path, encoding="utf-8"))
schemas = spec["components"]["schemas"]
failures = []

# 1. 只取「wire 枚举表」一节，逐行解析 schema 名与反引号内取值
section = arch.split("### wire 枚举表", 1)[1].split("SSE 事件名", 1)[0]
table = {}
for line in section.splitlines():
    m = re.match(r"\| `(\w+)` \| (.+?) \| (UPPER|lower) \|", line)
    if m:
        table[m.group(1)] = (re.findall(r"`([^`]+)`", m.group(2)), m.group(3))

yaml_enums = {k: v["enum"] for k, v in schemas.items() if isinstance(v, dict) and "enum" in v}
for name in sorted(set(yaml_enums) | set(table)):
    if name not in table:
        failures.append(f"YAML 有、表中缺：{name}")
    elif name not in yaml_enums:
        failures.append(f"表中有、YAML 缺：{name}")
    elif table[name][0] != yaml_enums[name]:
        failures.append(f"{name} 取值/顺序不一致：表 {table[name][0]} ≠ YAML {yaml_enums[name]}")
    else:
        print(f"PASS enum {name}: {len(yaml_enums[name])} 值")

# 2. 大小写规则：只有 ErrorCode / RelationType 为 UPPER，其余 lower_snake
upper_ok = {"ErrorCode", "RelationType"}
for name, values in yaml_enums.items():
    for v in values:
        if name in upper_ok:
            ok = re.fullmatch(r"[A-Z][A-Z0-9_]*", v)
        else:
            ok = re.fullmatch(r"[a-z][a-z0-9_]*", v)
        if not ok:
            failures.append(f"大小写违规：{name}.{v}")
    declared = table.get(name, (None, None))[1]
    expect = "UPPER" if name in upper_ok else "lower"
    if declared and declared != expect:
        failures.append(f"表中 {name} 标注 {declared}，规则要求 {expect}")
print("PASS 大小写规则" if not any("大小写" in f or "标注" in f for f in failures) else "FAIL 大小写规则")

# 3. 判别联合 const 值与内联枚举
def dig(*keys):
    cur = schemas
    for k in keys:
        if not isinstance(cur, dict) or k not in cur:
            return None
        cur = cur[k]
    return cur


def const(name, prop):
    node = dig(name, "properties", prop)
    return node.get("const") if isinstance(node, dict) else None

inline = {
    "ChatAnswered.status": (const("ChatAnswered", "status"), "answered"),
    "ChatNotCovered.status": (const("ChatNotCovered", "status"), "not_covered"),
    "ChatNotCovered 原因字段名": ("reason" if dig("ChatNotCovered", "properties", "reason") else None, "reason"),
    "ChatTurn.role": (dig("ChatTurn", "properties", "role", "enum"), ["user", "assistant"]),
    "LoginResponse.token_type": (dig("LoginResponse", "properties", "token_type", "enum"), ["bearer"]),
}
health = spec["paths"]["/health"]["get"]["responses"]["200"]["content"]["application/json"]["schema"]
inline["/health status"] = (health["properties"]["status"]["enum"], ["ok"])
chat_events = [const(n, "event") for n in ("ChatMetaEvent", "ChatDeltaEvent", "ChatDoneEvent", "ChatErrorEvent")]
inline["问答 SSE data.event"] = (chat_events, ["meta", "delta", "done", "error"])
for label, (got, want) in inline.items():
    if got != want:
        failures.append(f"{label}：YAML {got} ≠ 表 {want}")
    else:
        print(f"PASS {label}")

# 4. 路径前缀：除 /health 外全部以 /api/v1/ 开头
paths = list(spec["paths"])
bad = [p for p in paths if p != "/health" and not p.startswith("/api/v1/")]
ops = sum(1 for p in spec["paths"].values() for m in p if m in {"get", "post", "put", "patch", "delete"})
if bad:
    failures.append(f"前缀违规：{bad}")
else:
    print(f"PASS 前缀：{len(paths)} 路径 / {ops} 操作，除 /health 外均为 /api/v1/")

# 5. 成环分流依赖的错误码存在
for code in ("CYCLE_DETECTED", "PUBLISH_BLOCKED"):
    if code not in yaml_enums["ErrorCode"]:
        failures.append(f"ErrorCode 缺 {code}")
print("PASS 成环分流所需错误码存在" if not any("ErrorCode 缺" in f for f in failures) else "FAIL 错误码")

if failures:
    print("\n".join(["", "FAILURES:"] + failures))
    sys.exit(1)
print("\nALL PASS")
```
