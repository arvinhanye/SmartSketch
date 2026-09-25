# Claude 交接：E08 实现名称归一和重复候选

- `task_id`: E08（issue #88；已 push 分支，未开 PR、未改 issue，由协调方统一处理）
- `review_status`: ready_for_review（待 PR 审查/合并）
- 分支：`claude/e08-name-normalize`
- `base_commit`: `6c50d2c`（第六批认领提交）；`head`：本交接所在提交
- 依赖：E05（`services/ai/entities.py`，#236 已合入）。本任务不导入 E05，只接收名称字符串；E05 的 `EntityCandidate.name` 可直接放进 `NameEntry`。
- 依据：`docs/atomic-task-plan.md` E08 行；`docs/tasks.md`「2026-09-25 第六批并行（Claude）」E08 验收；`docs/decisions.md` ADR-011 修订 1（草稿可见性，融合候选按 V 过滤）；`specs/teacher-review-publish.md`（合并时名称并入 `aliases`、`merged_from`）。

## 交付物

| 文件 | 内容 |
| --- | --- |
| `src/backend/app/services/fusion/__init__.py` | 新增。包说明，一行 docstring，无导出 |
| `src/backend/app/services/fusion/normalize.py` | 新增。纯函数 `normalize_name`、`find_duplicate_candidates`；frozen dataclass `NormalizedName`、`NameEntry`、`DuplicateCandidate`；枚举 `CandidateReason`；常量 `CONTAINMENT_MIN_CHARS`、`CONTAINMENT_MIN_RATIO`。只依赖标准库（`unicodedata`、`fractions` 等） |
| `tests/backend/test_e08.py` | 新增。137 个用例（成功、边界、失败路径、误合并反例、输入顺序无关、纯函数 AST 检查） |
| `docs/tasks.md` | 只改第六批 E08 那一张表的状态与证据列 |

未改 E05、契约真源、规格、架构或其他共享文件。

## 接口（给 E09 / E10）

```python
from app.services.fusion.normalize import (
    NameEntry, find_duplicate_candidates, normalize_name, CandidateReason,
)

n = normalize_name("栈（Stack）")            # NormalizedName(key="栈", aliases=("stack",))
n.keys                                       # ("栈", "stack")，主键在前

found = find_duplicate_candidates([
    NameEntry("kp_1", "栈", "后进先出的线性表"),   # definition 可选，只随行，不参与计算
    NameEntry("kp_2", "栈（Stack）"),
])
# -> (DuplicateCandidate(left_id="kp_1", right_id="kp_2", reason=CandidateReason.SAME_KEY, matched_key="栈"),)
```

- `NameEntry(entity_id, name, definition=None)`：`entity_id` 为非空白 `str`、一次调用内唯一（由调用方给定，E12 可用块内序号或草稿 `kp_id`）；`name` 必须 `str`；`definition` 为 `str | None`，不进 `repr`。
- `DuplicateCandidate(left_id, right_id, reason, matched_key)`：`left_id < right_id`（码点序，等同 UTF-8 字节序），构造时校验；`reason` 必须是 `CandidateReason`。
- `CandidateReason`（wire 值 lower_snake）：`same_key`、`alias`、`containment`，按此优先级，每对只报最强的一个。
- 返回 `tuple[DuplicateCandidate, ...]`，按 `(left_id, right_id)` 升序、无重复、无自配对，与输入顺序无关。空输入或单条输入返回 `()`。
- **课程隔离**：本模块不认识课程，只处理传入的一个集合。调用方（E10/E12）必须只传同一课程、且已按草稿可见性 V 过滤的实体（ADR-011 修订 1，F02 必填 V）；混传会产生跨课程候选，属调用方错误。
- **只列候选，不合并**：所有三类候选（包括 `same_key`）都交 E09/E10 决定；E08 不产生任何合并结论。

## 行为规则

归一键（`normalize_name`）顺序：

1. 非 `str` → `TypeError`（`None`、`bytes`、数字、布尔、列表）。
2. NFKC（全角字母数字、全角空格、全角括号/逗号/分号/冒号折成半角）。
3. 删除 Unicode `Cf` 格式字符（零宽空格、ZWJ、BOM、U+2060）。
4. 只把 ASCII `A`–`Z` 转小写；希腊/西里尔字母保留大小写（Σ≠σ、Δ≠δ，数学含义不同）。
5. 圆括号（NFKC 后的 `(`、`)`）按顶层组分类：
   - 公式组：`(` 紧贴 ASCII 字母/数字、且组内全 ASCII（`O(n)`、`f（x）`、`x2(t)`）→ 原样留在键里；
   - 别名组：名称末尾连续的括号组 → 从主名去掉，内容作别名（「栈（Stack）」「先进先出(FIFO)」「JIT（即时编译）」）；
   - 注释组：开头或中间的括号组 → 从主名去掉、不产生别名（「图（Graph）的遍历」→「图的遍历」，Graph 只注释「图」）；
   - 括号不配对 → 不拆分，括号作普通字符；嵌套只看顶层，内层括号留在别名文本里。
6. 别名组内容按 `,`、`;`、`、` 切分；去掉前缀标记「又称/也称/亦称/简称/俗称/或称」（可带 `:`），以及必须带 `:` 的「英文全称/英文缩写/英文名/英文/全称/缩写」；去掉后为空则保留原文。「即」不是标记（「即时编译」）。
7. 空白：只有两侧都是 ASCII 字母/数字时留一个空格（「hash table」≠「hashtable」），其余删除（「二叉　树」=「二叉树」、「C 语言」=「c语言」、「B + 树」=「b+树」）。
8. 主名为空而有别名项（「（栈）」「(Stack)(栈)」）→ 第一项作主键；都为空（`""`、`"（ ）"`、`"​"`）→ `ValueError`。别名去重、去掉等于主键的项、码点升序。

重复候选（`find_duplicate_candidates`）：

| 原因 | 条件 | `matched_key` |
| --- | --- | --- |
| `same_key` | 主键完全相同（**只有**此时才是同键候选） | 主键 |
| `alias` | 主键不同，但一方主键/别名与另一方主键/别名相同（含共享别名） | 共享键中码点最小者 |
| `containment` | 主键不同、无共享键，较短主键是较长主键的**前缀**，且：较短主键有效字符（Unicode L*/N*）≥ 2；有效字符比 短/长 ≥ 3/5（含等号，用 `Fraction` 精确比较）；前缀末字符与长键下一字符不同时为 ASCII 字母/数字 | 较短主键 |

包含规则的理由与反例：

- **最短 2 个有效字符**：单字名（「栈」「树」「图」「C」「C++」只有 1 个有效字符）不参与包含候选，避免单字包含泛滥。
- **比例 ≥ 3/5**：挡住短通名被长名称包含（「排序/排序算法」2/4、「二叉树/二叉树的遍历」3/6 不列）；恰 3/5 列（「二叉树/二叉树遍历」「KMP/KMP算法」）。
- **只认前缀**：中英文名词短语中心语在后，前加修饰语通常是下位概念（「平衡二叉树」「单链表」「堆排序」「单源最短路径」「balanced binary tree」都不是短名的重复），后补「算法/法/问题」通常仍是同一概念（「快速排序/快速排序算法」「动态规划/动态规划法」「Dijkstra/Dijkstra算法」）。后缀/中间包含与语义近似交给 E09 向量候选。
- **拉丁串边界**：「Java/JavaScript」「hash table/hash tables」「k2/k23」不列。
- 定义不参与归一与候选（同名异定义仍 `same_key`；异名同定义不列）：定义相似度属于 E09/E10。

失败路径：`entries` 中非 `NameEntry`（含直接传字符串、元组、`None`）→ `TypeError`；`entity_id` 重复 → `ValueError`；任一名称归一后为空 → `ValueError`。错误信息不含名称或定义。

## 验证（实际结果）

环境：会话 scratchpad 内 venv（`python3 -m venv <scratchpad>/venv && <venv>/bin/pip install -e "src/backend[test]" 'datamodel-code-generator==0.26.3'`，安装成功），运行时 `PYTHONPATH=<worktree>/src/backend`、每次新的 `PYTHONPYCACHEPREFIX=<scratchpad>/pyc-*`、`-p no:cacheprovider`。

| 步骤 | 命令 | 结果 |
| --- | --- | --- |
| 红 | `<venv>/bin/python -m pytest tests/backend/test_e08.py -q -p no:cacheprovider`（只有测试） | 收集错误 `ModuleNotFoundError: No module named 'app.services.fusion'`，1 error |
| 首次绿 | 同上 | 1 failed / 135 passed：`JIT（即时编译）` 被公式规则当成公式组。据此把公式组收窄为「紧贴 ASCII 字母/数字且组内全 ASCII」，并补 `test_glued_group_with_non_ascii_content_is_alias_not_formula` |
| 绿 | 同上 | **137 passed** |
| 后端全量 | `<venv>/bin/python -m pytest tests/backend -q -p no:cacheprovider` | **2242 passed**，1 warning（既有） |
| 基线 | 同上加 `--ignore=tests/backend/test_e08.py` | 2105 passed，1 warning；新增 137 = 2242 − 2105 |
| 门禁 | `env PATH=<venv>/bin:… ./scripts/verify.sh` | `PASS contracts gate`、`Scaffold verification passed.`，exit 0 |
| 空白 | `git add -N . && git diff --check` | exit 0 |
| 计划原命令 | `python3 -m pytest tests/backend/test_e08.py -q`（系统 anaconda python3，无 PYTHONPATH） | `ModuleNotFoundError: No module named 'app'`；环境问题（系统解释器未安装本包），与 I03/I04 交接同类 |

### 反向篡改（脚本先备份模块，逐一单独篡改后跑 `test_e08.py`，结束恢复并 `cmp` 一致，exit 0）

| 篡改 | 结果 |
| --- | --- |
| T1 去掉 NFKC | 40 failed |
| T2 所有字母 `lower()`（含希腊） | 2 failed |
| T3 包含改为任意子串 | 5 failed |
| T4 去掉最短有效字符门槛 | 1 failed（「C/C++」；其余单字反例同时被比例挡住） |
| T5 去掉比例门槛 | 3 failed |
| T6 去掉拉丁串边界检查 | 3 failed |
| T7 别名优先于同键 | 1 failed |
| T8 不按 ID 排序 | 2 failed |
| T9 注释组也作别名 | 2 failed |
| T10 空白一律删除（无拉丁单词边界） | 8 failed |
| T11 不删格式字符 | 6 failed |

## 风险 / 待决 / 下一步

- **待决 1（非阻塞，交 E09/E10/协调方）**：包含候选只认前缀、阈值为最短 2 个有效字符与比例 3/5，均为本任务拟定（规格未给），未在评测集上调过。可能漏掉后缀式重复（如「经典快速排序」），预期由 E09 向量候选兜底；K02 评测后如需调整，改两个常量与前缀规则即可。
- **待决 2（非阻塞）**：公式组规则的已知代价：紧贴且组内全 ASCII 的「Stack(LIFO)」「TCP(Transmission Control Protocol)」按公式保留，不拆出别名（写成「Stack (LIFO)」或全角括号内含中文时正常拆分）。若需区分，可在 NFKC 前记录原文括号是否全角，另立规则。
- **待决 3（非阻塞）**：只处理圆括号；方括号、书名号、【】不拆分，作普通字符。连字符/破折号变体（`-`、`–`、`—`）、中点（`·`、`・`）未归一，「Floyd-Warshall」与「Floyd–Warshall」不同键（E09 向量可兜底）。
- **待决 4（非阻塞，交 E10/E12）**：`entity_id` 由调用方分配；E05 的 `EntityCandidate` 没有 ID。E12 编排时需约定草稿 `kp_id` 或块内临时 ID，以及合并后把被并名称写入 `aliases`（契约 `api.v1.yaml` 合并说明）。
- 风险：`find_duplicate_candidates` 为 O(n²) 对比较，面向单课程规模（数百～数千实体）；若单课程实体数远超此量级，需按主键/前缀建索引。
- 环境说明：会话 scratchpad 被同批其他 Claude 会话共用（venv 与脚本同目录，本会话的 `tamper.py` 已被另一会话覆盖）；共享 venv 的可编辑安装映射指向最后一次 `pip install -e` 的 worktree，所以本任务所有运行都显式设置 `PYTHONPATH=<worktree>/src/backend`。本 worktree 内留有被 `.gitignore` 忽略的 `.pytest_cache/`（`verify.sh` 内部 pytest 生成）、`tests/backend/__pycache__/`（系统 python3 运行生成）、`src/backend/smartsketch_backend.egg-info/`（可编辑安装生成）；递归删除被共享工作区保护钩子拦截，未删除，不影响提交。
- 下一步（E09）：在同一候选对类型上叠加向量相似度分层（自动/裁决/保留）；建议 E08 的 `same_key`/`alias` 对直接进入裁决组而非自动合并，`containment` 对进入裁决组或保留组，由 D-08 阈值决定。

## 回滚

只新增 3 个代码/测试文件与本交接，并改了任务板一行，无数据、依赖、配置或契约变更。回滚：`git revert <E08 提交>`，或删除 `src/backend/app/services/fusion/`、`tests/backend/test_e08.py`、本交接文件，并把任务板 E08 行恢复为 `IN PROGRESS`、证据「待补」。
