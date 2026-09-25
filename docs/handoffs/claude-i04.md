# Claude 交接：I04 四项评分和结构化理由

- `task_id`: I04
- `review_status`: ready_for_review（待 PR 审查/合并）
- `worktree`: `/home/user/wt-i04-ranking`，分支 `claude/i04-ranking`
- `base_commit`: `f0814cc`（第五批认领提交）
- 依赖：I03（`services/learning/eligible.py`，#219 已合入）、F05（经 I03 间接使用）、B06 配置（`app.config.Settings.recommend_weights`，已在 main）。
- 依据：`specs/learning-path.md` §1、§3、§4，LP-2/3/4/5/6/7/13/14/15；`docs/decisions.md` ADR-014 决定 1、修订 1 决定 5/6；ADR-017 决定 4；`src/contracts/api.v1.yaml` 的 `RecommendFactors`、`RecommendWeightedFactors`、`RecommendReasonFacts`、`Recommendation`；`docs/handoffs/claude-i03.md`。

## 交付物

| 文件 | 内容 |
| --- | --- |
| `src/backend/app/services/learning/ranking.py` | 新增。纯函数 `rank_candidates`、`chapter_ranks`；值对象 `RecommendWeights`、`KnowledgePointAttributes`、`Chapter`、`Factors`、`ReasonFacts`、`RankedCandidate`；异常 `RankingIntegrityError`、`CandidateMismatchError`、`InvalidWeightsError`；常量 `FACTOR_ORDER`。只依赖标准库与 I03 |
| `tests/backend/test_i04.py` | 新增。115 个用例（含 30 个随机 DAG 与定义式解锁数暴力解对拍、15 个随机理由一致性用例） |
| `docs/tasks.md` | 只改「2026-09-25 第五批并行（Claude）」I04 那一张表的状态与证据列 |

未改 `eligible.py`、`config.py`、契约真源、规格、架构与其他共享文件。

## 接口（给 I05）

```python
from app.services.learning.eligible import build_prerequisite_graph, eligible_set
from app.services.learning.ranking import (
    Chapter, KnowledgePointAttributes, RecommendWeights, rank_candidates,
    RankingIntegrityError, CandidateMismatchError,
)

weights = RecommendWeights.from_sequence(settings.recommend_weights)   # 启动时建一次
graph = build_prerequisite_graph(nodes, edges)
candidates = eligible_set(graph, mastered)
ranked = rank_candidates(graph, candidates, mastered, attributes, chapters, weights)
# -> tuple[RankedCandidate, ...]，全部候选，已排序；I05 取 ranked[:limit]，total_eligible = len(ranked)
```

- `candidates` 必须**恰好**是 `eligible_set(graph, mastered)`（顺序不限）；少给、多给、重复都抛 `CandidateMismatchError`。原因：§3 规定 `u` 的分母按**全部**候选算，只传截断后的子集会算错。函数内部会用 I03 重算一次核对（O(V+E)），`mastered` 越出 V 仍抛 I03 的 `ProgressOutsideGraphError`。
- `attributes`：每个 V 节点恰好一条 `KnowledgePointAttributes(kp_id, name, chapter_id=None, importance=None, difficulty=None)`；`None` 表示属性缺失，取中性值 0.5（决定 5）。
- `chapters`：绑定版本的全部章节 `Chapter(chapter_id, parent_id, order, name)`，可为空。`C` 按全部章节计（含没有知识点的章节）。
- `weights`：必须是 `RecommendWeights`（传元组抛 `TypeError`）。构造时按 §1 校验：有限、非负、非布尔、至少一项为正、`|和−1| ≤ 1e-9`（与 `config._check_rules` 同一个 `math.isclose(sum, 1, rel_tol=0, abs_tol=1e-9)` 判据，两处不会出现一处接受一处拒绝）；通过后原样使用，不除以总和。不合法抛 `InvalidWeightsError`。**全零权重**：按 LP-5 启动即被 `config` 拒绝；本类作为防御同样拒绝。
- 返回的 `RankedCandidate` 字段与契约 `Recommendation` 一一对应，只缺 `graph_version`（响应级字段，由 I05 填）：`kp_id`、`name`、`unlock_count`、`factors`、`weighted`（`Factors(unlock, importance, chapter_order, ease)`，`as_dict()` 按 `FACTOR_ORDER` 输出，键名即契约键名）、`score`、`reason`、`reason_facts`（`primary_factor`、`chapter_id`、`chapter_name`、`chapter_rank`、`importance`、`centrality`、`difficulty`）。全部 frozen，不改输入。
- 空结果当且仅当 `M = V`（I05 据此给 `state=all_mastered`）。

## 实现要点（均按规格）

1. **解锁数**：`|{v∈V\M : (k,v)∈E 且 Pred(v)\M = {k}}|`，不是出度；随机对拍用"`Eligible(M∪{k}) − Eligible(M) − {k}`"的定义式暴力解核对。
2. **零分母**：全部候选 `unlock_count` 为 0 时 `u=0`（不当 1）；`N≤1` 中心度 0；`C=1` 且属于该章 `c=1`；无章节 `c=0`。
3. **章节秩**：章节森林前序遍历，每层按 `(order, chapter_id UTF-8 字节)` 升序（LP-15：`1,1.1,2,2.1`）。
4. **求和**：`weighted.x = w_x × x`，`score = ((wu+wi)+wc)+we`；测试以 `==` 与 `float.hex()` 逐位比较，并用 `0.1/0.2/0.3/0.4` 这组求和顺序敏感的权重确认是固定顺序。
5. **排序键**：`(-score, 无章节标志, chapter_rank, kp_id UTF-8 字节)`，无章节视为 `+∞`；用未舍入分数比较，测试含"分数只差 1 ulp、章节更靠后仍排前"。
6. **理由**：只由结构化事实按模板生成，模块不导入任何模型/网络/配置模块（AST 测试）。`primary_factor` 取加权贡献最大者，同贡献按 `unlock → importance → chapter_order → ease`。模板：
   - 全部加权分量为 0：`当前无可直接解锁的后继；此点的直接前置均已掌握`（§4 原文）；
   - `unlock`：`完成该点可立即解锁 {unlock_count} 个知识点（解锁度 {u:.4f}）`（LP-13：`u=1` 时写的是真实个数）；
   - `importance`：`该点的主要推荐依据是重要度（重要度 {importance:.4f}，中心度 {centrality:.4f}）`；
   - `chapter_order`：`该点所在章节「{name}」在课程章节顺序中排第 {r+1} 位（共 {C} 个章节，章节顺序 {c:.4f}）`；
   - `ease`：`该点的主要推荐依据是易学度（难度 {difficulty:.4f}，易学度 {e:.4f}）`。
   选 `unlock` 模板时 `weighted.unlock>0`，故 `unlock_count>0`，不会在计数为 0 时声称可解锁（随机测试断言）。
7. **完整性错误** `RankingIntegrityError(kind, ids)`：`malformed`（名称非字符串、`chapter_id` 为空串等）、`attributes_mismatch`（属性与 V 不一一对应）、`invalid_number`（`importance/difficulty` 非有限、越界、布尔或非数值）、`unknown_chapter`（知识点引用不存在的章节）、`chapter_tree`（章节字段非法、`order` 非 ≥0 整数、重复 ID、父章节不存在、成环/自指）。`ids` 只进服务端日志。

## 验证（实际结果）

环境：会话 scratchpad 内共享 venv（未安装任何新包），每次运行换新的 `PYTHONPYCACHEPREFIX`，`-p no:cacheprovider`。

| 步骤 | 命令 | 结果 |
| --- | --- | --- |
| 红 | `PYTHONPATH=$PWD/src/backend $V/bin/python -m pytest tests/backend/test_i04.py -q -p no:cacheprovider`（只有测试） | 收集错误 `ModuleNotFoundError: No module named 'app.services.learning.ranking'`，exit 2 |
| 绿 | 同上 | 115 passed，exit 0 |
| 后端全量 | `... -m pytest tests/backend -q -p no:cacheprovider` | 1791 passed，1 warning（既有），exit 0（main 基线 1676 + 本任务 115） |
| 契约/工具 | `PATH=$V/bin:<b15-tools>/node_modules/.bin:$PATH ... -m pytest tests/contracts tests/tooling -q` | 305 passed，exit 0（与基线一致）。注：首次运行未把 venv 的 `bin` 放进 `PATH`，3 例因找不到 `datamodel-codegen` 失败，属环境问题，补 PATH 后全过 |
| 门禁 | `PATH=$V/bin:<b15-tools>/node_modules/.bin:$PATH ./scripts/verify.sh` | `PASS contracts gate`、`Scaffold verification passed.`，exit 0 |
| 空白 | `git add -N . && git diff --check` | exit 0 |
| 计划原命令 | `python3 -m pytest tests/backend/test_i04.py -q`（系统 python3） | `No module named pytest`；环境问题，与 I03 交接记录同类 |

### 反向篡改（改前 `cp` 备份，跑 `test_i04.py`，恢复后 `cmp` 一致；每次新 `PYTHONPYCACHEPREFIX`）

| 篡改 | 结果 |
| --- | --- |
| T1 解锁数改用出度 | 24 failed |
| T2 同分时章节秩降序 | 1 failed |
| T3 去掉 `max_unlock=0` 零分母保护 | 32 failed（`ZeroDivisionError`） |
| T4 求和顺序改为 e→c→i→u | 2 failed |
| T5 只删"至少一项为正"检查 | 0 failed——全零权重和为 0，已被"和在 1±1e-9"检查拒绝，该检查在数学上冗余（与规格一致地保留） |
| T5b 删掉正数与和两项检查（全零权重被接受） | 3 failed |
| T6 排序前把分数舍入到 6 位 | 1 failed |
| T7 同分 `kp_id` 改为降序 | 2 failed |

全部恢复后 `cmp` 通过。

## 风险 / 待决 / 下一步

- **待决 1（非阻塞，交 I05/F10/G04）**：规格要求章节有 `parent_id` 形成树，但契约 `Chapter` 只有 `id/title/order`，发布快照的章节形状尚未定。本函数接收 `Chapter(chapter_id, parent_id, order, name)`；快照没有 `parent_id` 时 I05 传 `None`（全为根，退化为按 `(order, id)` 平铺）。是否在快照/契约中补 `parent_id` 需协调方决定。
- **待决 2（非阻塞）**：理由的文字模板由本任务拟定（§4 只给了解锁与全零两条示例）；契约 `Recommendation.example` 的 `reason` 写作 `该点重要度最高（…）`，本实现改为 `该点的主要推荐依据是重要度（…）`，因为该点未必是全体候选中重要度最高的。若需与示例逐字一致，请协调方拍板。
- **待决 3（非阻塞）**：全部加权分量为 0 时，§4 要求"说明当前无可直接解锁的后继；此点的直接前置均已掌握"，`primary_factor` 按同贡献顺序为 `unlock`，而此时 `unlock_count=0`。机读字段 `primary_factor=unlock` 与"无可解锁"并存是规格字面结果；前端不应仅凭 `primary_factor` 断言可解锁。合法权重下只在 `w_i=w_c=w_e=0` 且 `u=0` 等极端配置出现。
- **待决 4（非阻塞）**：任务板 A08 段交给 I04 的"启动时读取并校验权重"已由 B06 在 `app/config.py` 实现（`Settings.recommend_weights` 与 `_check_rules`）。本任务只在纯函数侧用 `RecommendWeights` 做同判据的防御校验，未改 `config.py`；I05 应在启动时 `RecommendWeights.from_sequence(settings.recommend_weights)` 一次。
- 风险：`RankedCandidate` 与契约生成的 Pydantic 模型之间的映射由 I05 完成；字段名已对齐契约，I05 需补 `graph_version`。
- 下一步（I05）：绑定版本 → 投影 `M`（ADR-017 决定 4）→ `build_prerequisite_graph` → `eligible_set` → 若空则 `all_mastered` → `rank_candidates` → 取前 `limit` 条、`total_eligible=len(ranked)`；`GraphIntegrityError`、`RankingIntegrityError`、`ProgressOutsideGraphError`、`CandidateMismatchError` 统一映射为 500 `INTERNAL_ERROR`（`details.request_id`），异常中的 ID 只进日志。

## 回滚

只新增 3 个文件并改了任务板一行，无数据、依赖或配置变更。回滚：`git revert <I04 提交>`，或删除 `src/backend/app/services/learning/ranking.py`、`tests/backend/test_i04.py`、本交接文件，并把任务板 I04 行恢复为 `IN PROGRESS`。
