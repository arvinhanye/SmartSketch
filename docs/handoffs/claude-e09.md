# Claude 交接：E09 实现向量候选分层

- 任务：E09（GitHub issue #89），依赖 E07 #217、E08 #240（均已合入 main）。
- 分支：`claude/e09-vector-tiers`，基线为第八批认领提交 `bdcf165`。
- 负责人：ArvinHan（Claude 子代理）。
- 日期：2026-09-25 ～ 2026-09-26。

## 交付物

| 文件 | 说明 |
| --- | --- |
| `src/backend/app/services/fusion/candidates.py` | 新增。纯函数：阈值校验、余弦相似度、单对分层、单课程单空间两两分层 |
| `tests/backend/test_e09.py` | 新增。94 个用例（首版 84，接口变更后 94） |
| `docs/handoffs/claude-e09.md` | 本文件 |
| `docs/tasks.md` | 只改第八批 E09 行的状态与证据列 |

`fusion/__init__.py` 未改：它只有一行模块说明、不做导出，调用方直接 `from app.services.fusion.candidates import ...` 即可，无需导出。其说明里「E09 待实现」的措辞留给后续改该文件的任务顺手更新（非功能性）。

## 接口（给 E10 / E12）

```python
from app.services.fusion.candidates import (
    TierThresholds, VectorEntry, tier_vector_candidates, classify_similarity, cosine_similarity,
    CandidateTier, VectorIsolationError,
)

t = TierThresholds(auto_merge=0.92, review=0.80)          # 数值仅示例，D-08 未签收，必须由调用方给出
tiers = tier_vector_candidates(
    [VectorEntry("kp_1", "c1", v1), VectorEntry("kp_2", "c1", v2)],   # v1/v2 为 E07 的 EmbeddedVector
    course_id="c1", space=adapter.space, thresholds=t,
)
tiers.auto_merge / tiers.review                             # tuple[VectorCandidate, ...]
tiers.kept_count                                             # int，保留组配对数（不返回配对）
tiers.total_pairs                                            # = len(auto_merge) + len(review) + kept_count = n(n-1)/2
tiers.candidates()                                           # 前两组合并，按 (left_id, right_id) 升序
```

- `TierThresholds(*, auto_merge, review)`：仅关键字、无默认值、frozen。
- `VectorEntry(entity_id, course_id, vector: EmbeddedVector)`：ID 为非空白 `str`；向量不进 `repr`。
- `VectorCandidate(left_id, right_id, similarity, tier)`：`left_id < right_id`，`tier` 为 `CandidateTier` 且不能是 `keep`（`ValueError`）。
- `CandidateTier` wire 值：`auto_merge`、`review`、`keep`（`keep` 只作为 `classify_similarity` 的返回值）。
- `VectorTiers(course_id, space, thresholds, auto_merge, review, kept_count)`：回显上下文；`kept_count` 为非负 `int`（`bool`、负数拒绝）；三组互斥，计数之和 `total_pairs` = C(n, 2)。
- **接口变更（PR #250 审查意见，用户确认）**：首版的 `keep` 元组与 `all_pairs()` 已删除，改为 `kept_count` 与 `candidates()`；新增 `total_pairs` 属性。
- `VectorIsolationError` 是 `ValueError` 子类。

## 关键决定

1. **边界等号**：每组含下界、不含上界。`相似度 ≥ auto_merge` → 自动合并；`review ≤ 相似度 < auto_merge` → 需裁决；`相似度 < review` → 保留。浮点直接比较，不做舍入或容差。写在模块文档字符串，测试用 `math.nextafter` 覆盖两条阈值的等于与紧贴其下，并有测试断言文档字符串写明该规则。与 ADR-010「≤ 阈值含等号」、E08「≥ 3/5」一致：达到阈值即进入该组。
2. **阈值合法性**：两项均为有限 `int`/`float`（`bool` 拒绝，`TypeError`）；NaN/±inf 拒绝；取值 `[0, 1]`；且 `review < auto_merge` 严格小于（相等时裁决组为空区间，视为配置错误）。均 `ValueError`。
3. **阈值无默认值**：规格（`specs/course-knowledge-graph.md`「节点融合阈值……由 M1 设计时补入」、`specs/teacher-review-publish.md` 待细化）与 `docs/integrations.md` 均未给数值，`docs/tasks.md` D-08 未签收，因此作为必填参数；未新增环境变量。
4. **课程与空间隔离**：调用方必须显式给出 `course_id` 与 `space`；任一条目课程不同或向量空间不同，整体拒绝（`VectorIsolationError`），不做部分分层、不静默丢弃；只传一条外来条目也拒绝。同一空间标签下维度不一致、向量长度与 `dimensions` 不符、非有限值、全零向量均 `ValueError`。草稿可见性 V 过滤仍由调用方（F02）先做。
5. **相似度**：余弦，`math.fsum` 求点积与范数，截断到 `[-1, 1]`；`values` 逐值相同时恰为 1.0（朴素计算对 `(0.1, 0.1)` 得 0.9999999999999998，会让 `auto_merge = 1` 时相同向量掉到裁决组；有专门测试）。
6. **保留组只计数**：逐对计算余弦，保留对只累加 `kept_count`、不创建 `VectorCandidate`。复杂度：时间 O(n²·d)（n 实体数、d 维度，面向单课程规模）；额外内存 O(n·d + k)，k 为自动合并与需裁决两组配对数，不再与 n² 成正比。测试用计数替身包装 `VectorCandidate`，断言构造次数等于前两组配对数。
7. **不接收 E08 名称候选**：规格未定两者如何合流，本模块只看向量（见待决 1）。

## 验证（实际结果）

环境：会话 scratchpad 内新建 venv（`python3 -m venv <scratchpad>/e09venv && <venv>/bin/pip install -q -e './src/backend[test]'`，安装成功，Python 3.13.5），运行时 `PYTHONPATH=<worktree>/src/backend`。

| 步骤 | 命令 | 结果 |
| --- | --- | --- |
| 红 | `<venv>/bin/python -m pytest tests/backend/test_e09.py -q`（只有测试） | 收集错误 `ModuleNotFoundError: No module named 'app.services.fusion.candidates'` |
| 绿 | 同上 | 83 passed；补「朴素浮点不为 1」用例后 **84 passed** |
| 后端全量 | `<venv>/bin/python -m pytest tests/backend -q` | **2605 passed**，1 warning（既有），322.62s；其中 E09 84 个，未单独跑不含 E09 的基线 |
| 门禁 | `./scripts/verify.sh` | `PASS contracts gate`、`Scaffold verification passed.`，exit 0（改完 `docs/tasks.md` 后复跑仍 exit 0） |
| 空白 | `git add -N . && git diff --check` | exit 0（含 `docs/tasks.md` 与本文件） |

### 接口变更（保留组只计数）后复验

| 步骤 | 命令 | 结果 |
| --- | --- | --- |
| 红 | 先只改测试，`<venv>/bin/python -m pytest tests/backend/test_e09.py -q` | 12 failed / 82 passed（缺 `kept_count`、`candidates()`、`total_pairs`，`keep` 层仍可构造候选，文档字符串无 `kept_count`） |
| 绿 | 同上 | **94 passed** |
| 后端全量 | `<venv>/bin/python -m pytest tests/backend -q` | **2615 passed**，1 warning（既有）；比首版 2605 多 10，即 E09 新增用例数 |
| 门禁 | `./scripts/verify.sh` | `PASS contracts gate`、`Scaffold verification passed.`，exit 0 |
| 空白 | `git add -N . && git diff --check` | exit 0 |

反向篡改（同样备份、逐一篡改、`cmp` 恢复）：自动阈值 `>=`→`>` 4 failed；裁决阈值 `>=`→`>` 5 failed；去课程校验 3 failed；去空间校验 2 failed；`kept_count` 不累加 4 failed；允许 `keep` 层候选 1 failed；允许负 `kept_count` 1 failed；去「逐值相同恰为 1.0」1 failed；不按 ID 排序 2 failed；保留对也构造 `VectorCandidate`（物化）1 failed。10 处均检出。

### 反向篡改（备份模块，逐一单独篡改后跑 `test_e09.py`，结束 `cp` 恢复并 `cmp` 一致）

| 篡改 | 结果 |
| --- | --- |
| M1 自动阈值 `>=` 改 `>` | 3 failed |
| M2 裁决阈值 `>=` 改 `>` | 3 failed |
| M3 去掉课程校验 | 3 failed |
| M4 去掉向量空间校验 | 2 failed |
| M5 阈值顺序允许相等 | 2 failed |
| M6 阈值下界放宽到 -1 | 2 failed |
| M7 去掉「逐值相同恰为 1.0」 | 首轮 0 failed（未检出）→ 补 `(0.1, 0.1)` 用例后 1 failed |
| M8 去掉重复 ID 检查 | 1 failed |
| M9 不按 ID 排序 | 3 failed |
| M10 `cosine_similarity` 去掉空间校验 | 1 failed |
| M11 去掉阈值有限性检查 | 3 failed |

## 风险 / 待决 / 下一步

- **待决 1（交 E10/E12/协调方）**：E08 名称候选（`same_key`/`alias`/`containment`）与 E09 向量分层如何合流，规格未定。E08 交接建议名称候选至少进入裁决组、不直接自动合并；可选做法：(a) E12 把名称候选并入裁决组，向量 `keep` 不能把名称候选降为保留；(b) 名称候选只作为向量分层的加权。需规格或 ADR 定稿后由 E10/E12 实现，本模块无需改动。
- **待决 2（D-08，技术负责人）**：`auto_merge` 与 `review` 初始取值未签收；取值依赖 D-02c 向量模型（不同模型余弦分布差异大），建议在 K 组评测集上定。签收后在 `docs/integrations.md` 登记是否作为环境变量，由 E12 注入。
- **待决 3（E10/E12）**：「自动合并」组仍须遵守教师加锁节点不被覆盖（`specs/teacher-review-publish.md`）；本模块不认识加锁状态，调用方须先排除加锁节点或在合并时跳过。

## 回滚

只撤销本任务自有变更：删除 `src/backend/app/services/fusion/candidates.py`、`tests/backend/test_e09.py`、本文件，并把 `docs/tasks.md` E09 行恢复为 `IN PROGRESS` / `待补`（或 `git revert <本任务提交>`）。无持久层、依赖或契约变更。
