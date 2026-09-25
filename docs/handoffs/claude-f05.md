# Claude 交接：F05 DAG 环检测纯函数

- `task_id`: F05（GitHub issue #97）
- `review_status`: ready_for_review
- `worktree`: `/Users/arvinhan/Desktop/SmartSketch/.claude/worktrees/f05-dag-cycle`，分支 `claude/f05-dag-cycle`
- `base_commit`: `8eeac3b`（认领提交 `38ef62d`）
- 依赖：B11（环路字段 `x-closed-cycle: true`）已在 main。
- 依据：`docs/atomic-task-plan.md` F05 行；`specs/course-knowledge-graph.md`「前置关系成环处理」DAG-1～DAG-11；`specs/teacher-review-publish.md` `PUBLISH_BLOCKED` 的 `cycle`；`docs/handoffs/codex-b11.md` 第 23 行（首尾同 ID 由服务层保证）。

## 交付物

| 文件 | 内容 |
| --- | --- |
| `src/backend/app/services/graph/__init__.py` | 新增。`services/graph/` 包原先不存在，只有一行包说明，不做重导出 |
| `src/backend/app/services/graph/dag.py` | 新增。`find_cycle`、`check_candidates`、`CycleCheck`、`UnknownNodeError`；纯函数，不接触数据库、不做 I/O |
| `tests/backend/test_f05.py` | 新增。73 个用例（含 40 个随机图对拍参数化） |
| `docs/tasks.md` | 只改「2026-09-25 并行批次（Claude）」F05 那一张表的状态与证据列 |

未改 `docs/architecture.md`、`docs/integrations.md`、`scripts/verify.sh`、`pyproject.toml`、契约真源与其他共享文件。

## 接口（给 F06、F13、G04、I03）

```python
from app.services.graph.dag import CycleCheck, UnknownNodeError, check_candidates, find_cycle

find_cycle(nodes, edges) -> tuple[str, ...] | None
check_candidates(nodes, edges, candidates) -> CycleCheck   # CycleCheck(ok, cycle, edge)，冻结 dataclass
```

- `nodes`：本课程知识点 ID（非空字符串）。`edges`、`candidates`：`(from_id, to_id)` 二元组，`from_id` 是 `to_id` 的前置。三者都接受任意可迭代对象（可只遍历一次），不会被修改；重复项按集合处理。
- **调用方负责选边**：只传本课程 `type = PREREQUISITE` 且 `status ≠ rejected` 的边（规格「参与环检测的边」）。改类型、改端点、反转、从 `rejected` 恢复、合并后重接：先把旧形态从 `edges` 去掉，再把新形态作为候选传入。
- **课程隔离**：边端点不在 `nodes` 中时抛 `UnknownNodeError`（`ValueError` 子类，信息含该 ID），不会把外课 ID 静默当成新节点。ID 非字符串或边不是二元组时抛 `TypeError`；空 ID 或边长度不为 2 时抛 `ValueError`。
- **环路径格式**：闭合、首尾同 ID、至少两项，除首尾外不重复。自环为 `("A", "A")`。可直接转 `list` 填入 `CYCLE_DETECTED.details.cycle`、`PublishBlockedCycleReason.cycle`，满足 B11 的 `x-closed-cycle: true` 不变量。F13 与 G04 仍按 B11 交接要求在服务层断言首尾相等。

## 关键决定

1. **两个入口**：`check_candidates` 用于教师编辑（F06，`CYCLE_DETECTED`），`find_cycle` 用于全图复检（G04 发布前 `PUBLISH_BLOCKED`、I03 输入防御）。F13 的 ADR-009 自动降级要求「按边 `id` 升序 DFS」并按置信度选边，需要边 ID 与置信度，本函数只处理 `(from_id, to_id)`，不实现降级循环；F13 可自写，也可在每轮降级后调用 `find_cycle` 确认已无环。
2. **确定性规则**（结果只取决于节点、边、候选的集合，与输入顺序和重复无关）：
   - `find_cycle`：DFS 起点按 ID 升序，后继按 ID 升序，返回第一个找到的环，并旋转为从环上字典序最小的 ID 开始。
   - `check_candidates`：先对既有边做 `find_cycle`。若已有环（草稿违反不变量，对应 DAG-10），返回 `CycleCheck(ok=False, cycle=该环, edge=None)`，不把责任推给候选边。否则按 `(from_id, to_id)` 升序逐条加入候选边，报告第一条闭合环的候选边，以及经过它的**最短**环 `(u, v, …, u)`，从候选边起点开始（DAG-1：新建 A→B，得 `[A, B, C, A]`）。等长路径之间按 BFS 升序展开的先后决定。与既有边相同的候选边直接跳过。
3. **不递归**：DFS 用显式栈加迭代器，BFS 用队列；10 万节点链条的测试约 0.9 秒，不受递归上限影响。
4. **复杂度**（V 节点，E 条不同既有边，k 条不同候选边）：建有序邻接 O(V + E log E)；`find_cycle` 在此之后 O(V + E)；每条候选一次 BFS O(V + E + k)。`check_candidates` 总计 O(V + E log E + k log k + k·(V + E + k)) 时间，O(V + E + k) 内存；单条候选为 O(V + E log E)。批量候选（合并重接）的 k 通常只是被合并点的度数；如果 k 很大，调用方应改用 `find_cycle` 对并集做一次 O(V + E) 检查（代价是得不到「是哪条候选边闭合的环」）。以上也写在模块 docstring 中。

## 验证（实际结果）

环境：macOS，系统 `python3` 3.13.5（anaconda，无 FastAPI 等后端依赖、未安装 `app` 包）；另在会话 scratchpad 建 venv（`--system-site-packages`），按 `src/backend/pyproject.toml` 固定版本安装运行依赖与 test extra，**未做 editable 安装**，用 `PYTHONPATH=src/backend` 让测试找到 `app`，工作区内没有 egg-info 残留。

| 步骤 | 命令 | 结果 |
| --- | --- | --- |
| 基线 | `PYTHONPATH=src/backend <venv>/bin/python -m pytest tests/backend -q --ignore=tests/backend/test_f05.py` | 720 passed，1 warning（既有），exit 0 |
| 红（只有测试） | `PYTHONPATH=src/backend <venv>/bin/python -m pytest tests/backend/test_f05.py -q` | 收集错误 `ModuleNotFoundError: No module named 'app.services.graph'`，exit 2 |
| 红（桩函数抛 `NotImplementedError`） | 同上 | 72 failed，exit 1 |
| 绿 | 同上 | 73 passed（多出的 1 个是篡改后补的旋转用例），exit 0 |
| 计划原命令 | `python3 -m pytest tests/backend/test_f05.py -q`（系统 python3，无 PYTHONPATH） | 1 error（`No module named 'app'`），exit 2。这是环境问题：系统解释器没有安装后端包，与 E01/D05 交接记录的情况相同 |
| 计划原命令加路径 | `PYTHONPATH=src/backend python3 -m pytest tests/backend/test_f05.py -q` | 73 passed，exit 0（本模块只用标准库） |
| 全量 | `PYTHONPATH=src/backend <venv>/bin/python -m pytest tests/backend -q` | 793 passed，1 warning（既有），exit 0 |
| 门禁 | `./scripts/verify.sh` | `Scaffold verification passed.`，exit 0 |
| 空白 | `git diff --check`（先 `git add -N` 新文件） | exit 0 |

### 反向篡改（临时改实现，跑 `test_f05.py`，再从 scratchpad 备份恢复，并用 `cmp` 确认与原文件一致）

| 篡改 | 结果 |
| --- | --- |
| M1 BFS 改为 DFS（`queue.popleft()` 改成 `queue.pop()`），不再保证最短环 | 1 failed（`test_candidate_cycle_is_shortest_through_candidate`） |
| M2 去掉旋转（`start = 0`） | **首轮 72 passed，漏检**：已有用例的 DFS 入环点恰好都是环上最小 ID。补 `test_find_cycle_rotates_when_dfs_enters_cycle_at_larger_id` 后：1 failed |
| M3 候选边不排序（`sorted` 改成 `list`） | 2 failed（输入顺序无关、多候选升序） |
| M4 跳过既有环预检 | 1 failed（`test_existing_cycle_is_reported_without_blaming_a_candidate`） |
| M5 DFS 不识别回边（`_GRAY` 判断失效） | 24 failed |

## 风险与下一步

- **F06**：在写入序列内先取课程写锁，读出当前可见草稿边（按 `specs/task-processing.md` 的有效任务集合 V 过滤，并只取参与环检测的边），再调用 `check_candidates`；`ok=False` 时返回 409 `CYCLE_DETECTED`，`details.cycle = list(result.cycle)`。`edge is None` 表示草稿本身已违反不变量，建议记日志并同样拒绝写入。
- **G04**：发布前对快照调用 `find_cycle`，非 `None` 时组装 `PublishBlockedCycleReason`。
- **I03**：可学集合纯函数遇到环时，可以用 `find_cycle` 给出可解释的错误。
- 待决（非阻塞）：规格没有规定一次报告多个环。当前每次只返回一个环；若产品需要一次列出全部环，另开任务扩展。
- 计划中的验证命令 `python3 -m pytest tests/backend/test_f05.py -q` 在本机系统解释器上会收集失败（缺 `app`），需要在装有后端包的环境中运行，或加 `PYTHONPATH=src/backend`。是否统一命令写法由协调方决定，本任务不改 `docs/atomic-tasks.json`。

## 回滚

只新增了 3 个文件并改了任务板一行，没有数据、依赖或配置变更。回滚方式：`git revert <F05 提交>`，或删除 `src/backend/app/services/graph/`、`tests/backend/test_f05.py`、本交接文件，并把任务板 F05 行恢复为 `IN PROGRESS`。
