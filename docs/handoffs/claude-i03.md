# Claude 交接：I03 可学集合纯函数

- `task_id`: I03（GitHub issue #126）
- `review_status`: ready_for_review（待 PR 审查/合并）
- `worktree`: `/Users/arvinhan/Desktop/SmartSketch/.claude/worktrees/i03-eligible-set`，分支 `claude/i03-eligible-set`
- `base_commit`: `36670a3`（认领提交 `54b37d8`）
- 依赖：A08（`specs/learning-path.md`，已签收）、F05（`services/graph/dag.py`，已在 main）。
- 依据：`specs/learning-path.md` §1、§2、§4、LP-1/2/3/7/11/12；`docs/decisions.md` ADR-014「后果」（I03 接收已投影的掌握集合）与修订 1；`docs/handoffs/claude-f05.md`（I03 用 `find_cycle` 做输入防御）；`docs/handoffs/claude-b12.md`（完整性错误暂用 500 `INTERNAL_ERROR`，只含 `diagnostic_id`）。

## 交付物

| 文件 | 内容 |
| --- | --- |
| `src/backend/app/services/learning/__init__.py` | 新增。`services/learning/` 包原先不存在，只有一行包说明，不做重导出。I04/I05/O03 会在此包内新增文件 |
| `src/backend/app/services/learning/eligible.py` | 新增。`build_prerequisite_graph`、`eligible_set`、`PrerequisiteGraph`、`GraphIntegrityError`、`ProgressOutsideGraphError`；纯函数，只依赖标准库与 F05 `find_cycle` |
| `tests/backend/test_i03.py` | 新增。80 个用例（含 40 个随机 DAG 与定义式暴力解对拍，8 个畸形输入参数化） |
| `docs/tasks.md` | 只改「2026-09-25 第二批并行（Claude）」I03 那一张表的状态与证据列 |

未改 `dag.py`、`pyproject.toml`、`docs/architecture.md`、`scripts/verify.sh`、契约真源与其他共享文件。

## 接口（给 I04、I05、O03）

```python
from app.services.learning.eligible import (
    GraphIntegrityError, PrerequisiteGraph, ProgressOutsideGraphError,
    build_prerequisite_graph, eligible_set,
)

graph = build_prerequisite_graph(nodes, edges)   # -> PrerequisiteGraph（冻结，可复用）
candidates = eligible_set(graph, mastered)        # -> tuple[str, ...]
```

- `nodes`：绑定发布版 V 的全部 `kp_id`；`edges`：只含该版本 `PREREQUISITE` 边 `(from_id, to_id)`，`from_id` 是 `to_id` 的直接前置。其他三类关系不传。任意可迭代对象均可（可只遍历一次），不会被修改。
- `mastered`：**已投影**的掌握集合 `M = {k∈V | projected_status(k)=mastered}`（ADR-014「后果」：I03 接收已投影的掌握集合）。`learning` 不算掌握、合并继承、覆盖规则、dormant 与脏行过滤都由调用方（I01/I05 的投影）在调用前完成。函数只读一次，复制成私有 `frozenset`，不修改传入对象（出错时也不改）。
- 返回：`{k ∈ V \ M | Pred(k) ⊆ M}`，只看直接前置；按 `kp_id` 的 **UTF-8 字节序升序**排列（与规格中 `kp_id` 平局键用同一序）。此顺序只为确定性，与输入顺序、重复项无关；**评分排序 `(-score, chapter_rank, kp_id)` 归 I04**。
- 返回空元组当且仅当 `M = V`（I05 据此给 `state=all_mastered`）；DAG 上只要 `M ≠ V` 就至少有一个候选，随机对拍测试断言了这一点，也断言了候选之间没有先修边。
- `PrerequisiteGraph` 字段：`nodes: frozenset[str]`、`edges: frozenset[Edge]`（已去重）、`predecessors`（只读 `MappingProxyType`，每个节点→直接前置 `frozenset`，根为空集）。I04 算 `unlock_count`/中心度时可直接复用，不必重复校验。`eligible_set` 只接受 `build_prerequisite_graph` 产出的对象（否则 `TypeError`）。

## 关键决定（均按规格，未自定语义）

1. **图错误一律抛 `GraphIntegrityError`**（§1：“重复 ID、自环、悬空端点、环……属于已提交版完整性故障……不输出部分推荐”；“重复边去重；自环、悬空端点、环均为图错误，不静默修复”；§4：`V=∅` 是完整性错误而非正常空态）。`kind` 取值与固定检查顺序：`malformed`（ID 非字符串/空串/无法编码为 UTF-8，边不是二元组）→ `empty_graph` → `duplicate_node` → `dangling_edge` → `self_loop` → `cycle`，报告第一个失败项。`ids`：前三类以外按 UTF-8 字节序列出涉事 ID；`cycle` 直接用 F05 `find_cycle` 的闭合路径（旋转到最小 ID，测试断言与 `find_cycle` 输出相等）；`empty_graph`、`malformed` 为 `()`。
2. **外课 ID**：
   - 出现在**边**上 = 悬空端点 → `GraphIntegrityError(kind="dangling_edge")`。
   - 出现在 **`mastered`** 中 → `ProgressOutsideGraphError(ids=...)`，不静默忽略。依据 §1“纯函数只接受 `projected_status` 的键集 ⊆ V；原始进度中的历史、外课或脏 ID 在调用前由 §5 的仓储边界处理”。这属于调用方违反前置条件，与“已提交版完整性故障”分成两个异常类，便于 I05 日志区分；两者都是 `ValueError` 子类。
3. **图错误先于掌握集合错误**：`build_prerequisite_graph` 独立校验整图，`eligible_set` 再校验 `mastered`，所以图有环时无论 `M` 如何都报环。
4. **复用 F05**：环检测只调用 `find_cycle`，未重写。自环在调用前单独检出（规格把自环与环分列），悬空端点也先于 `find_cycle` 自行收集全部 ID，因此不会走到 F05 的 `UnknownNodeError`。
5. **复杂度**：校验与求候选 O(V + E)，另有 F05 建有序邻接的 O(E log E) 与结果排序 O(V log V)。全程迭代，10 万节点链条用例单独运行约 1.0 秒（`--durations` 实测 1.02s）。
6. **不做的事**：不做评分/排序/截断（I04、I05）、不读数据库、不做进度投影、不生成诊断 ID。

## I05 须知

- 两种异常都应映射为学生读路径的 500 完整性错误（B12：`LearningIntegrityError`，暂用 `INTERNAL_ERROR`，`details` 只含 `diagnostic_id`）。异常的 `kind`/`ids`/消息含内部 ID 与环路，**只能写服务端日志，不能进响应**（§1）。
- 调用前须把 `projected_status` 限制到 V 并只取 `mastered` 键，否则会触发 `ProgressOutsideGraphError`。

## 验证（实际结果）

环境：macOS，会话 scratchpad 内**本任务专用** venv（`python3 -m venv`，不继承 system site-packages），按 `src/backend/pyproject.toml` 固定版本安装运行依赖与 test extra；**未做 editable 安装**，运行时用绝对路径 `PYTHONPATH=$PWD/src/backend`。

| 步骤 | 命令 | 结果 |
| --- | --- | --- |
| 基线 | `PYTHONPATH=$PWD/src/backend <venv>/bin/python -m pytest tests/backend -q --ignore=tests/backend/test_i03.py` | 1002 passed，1 warning（既有），exit 0 |
| 红（只有测试） | `PYTHONPATH=$PWD/src/backend <venv>/bin/python -m pytest tests/backend/test_i03.py -q` | 收集错误 `ModuleNotFoundError: No module named 'app.services.learning'`，exit 2 |
| 红（桩函数抛 `NotImplementedError`） | 同上 | 79 failed，1 passed（“模块无 I/O 导入”检查对桩也成立），exit 1 |
| 绿 | 同上 | 80 passed，exit 0 |
| 全量 | `PYTHONPATH=$PWD/src/backend <venv>/bin/python -m pytest tests/backend -q` | 1082 passed，1 warning（既有），exit 0 |
| 计划原命令 | `python3 -m pytest tests/backend/test_i03.py -q`（系统 python3，无 PYTHONPATH） | 1 error（收集时找不到 `app`），exit 2。环境问题，与 F05/E01/D05 交接记录相同 |
| 计划原命令加路径 | `PYTHONPATH=$PWD/src/backend python3 -m pytest tests/backend/test_i03.py -q` | 80 passed，exit 0（本模块只用标准库） |
| 门禁 | `./scripts/verify.sh` | `PASS contracts gate`、`Scaffold verification passed.`，exit 0 |
| 空白 | `git diff --check`（先 `git add -N` 新文件） | exit 0 |

### 反向篡改（临时改实现，跑 `test_i03.py`，再从 scratchpad 备份恢复并用 `cmp` 确认与原文件一致，6 处均 `cmp` 通过）

| 篡改 | 结果 |
| --- | --- |
| M1 去掉 `node not in owned`（已掌握点仍当候选） | 36 failed |
| M2 “任一前置已掌握即可学”（`<=` 改为交集非空） | 19 failed |
| M3 静默忽略 `mastered` 中的外课 ID | 3 failed |
| M4 跳过环检测（`cycle = None`） | 3 failed |
| M5 结果不排序（按 `frozenset` 迭代序） | 28 failed（该次运行；具体数随字符串哈希随机化浮动，排序专用用例 `test_result_is_sorted_by_utf8_byte_order` 必然失败） |
| M6 去掉自环检查（自环落到 `cycle`） | 2 failed |

## 风险 / 待决 / 下一步

- **待决 1（非阻塞，交 I05/B08）**：`ProgressOutsideGraphError` 在读路径上应归为 500 完整性错误还是另一种内部错误，规格未单列；本任务只保证“抛错、不忽略”。按 §5，这种情况只会因投影实现有缺陷而出现（仓储已过滤脏行），建议 I05 同样映射为 500 并记诊断 ID。
- **待决 2（非阻塞，交 G04/F10）**：规格未规定发布快照的节点/边数据结构，本函数接收裸 `kp_id` 序列与 `(from_id, to_id)` 二元组。快照模型确定后由 I05 做适配，不改本函数。
- 计划中的验证命令 `python3 -m pytest tests/backend/test_i03.py -q` 在系统解释器上会收集失败（缺 `app`），需要装有后端包的环境或加 `PYTHONPATH=src/backend`。本任务不改 `docs/atomic-tasks.json`。
- 下一步：I04 基于 `PrerequisiteGraph.predecessors` 与 `eligible_set` 结果实现 `unlock_count`、四项分量与排序；I05 负责投影、调用与错误映射。

## 回滚

只新增 4 个文件并改了任务板一行，没有数据、依赖或配置变更。回滚：`git revert <I03 提交>`，或删除 `src/backend/app/services/learning/`、`tests/backend/test_i03.py`、本交接文件，并把任务板 I03 行恢复为 `IN PROGRESS`。若 I04/I05 已在 `services/learning/` 下新增文件，只删 `eligible.py`，保留 `__init__.py`。
