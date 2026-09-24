# A07：落实模型配置形状与预算决策入口

- **task_id**：A07（`docs/atomic-task-plan.md` / `docs/atomic-tasks.json`）
- **状态**：DONE（形状已定；取值待 D-02a～f 签收）。三节设计（变量清单与类型、主备切换矩阵、预算/签收入口/启动校验）由 ArvinHan 于 2026-09-23 在会话中逐节确认；**所有真实取值未签收**，按验收要求保留未签收标记，本轮不写 ADR
- **review_status**：ready_for_review（以交付提交为准，提交前不生效）
- **worktree**：`/Users/arvinhan/Desktop/SmartSketch/.claude/worktrees/a07-297f68`
- **分支 / base**：`claude/a07-model-config`，**叠在** `claude/a06-worker-lease` 之上 / base `ab04053`（A06 的 PR #6、A03 的 PR #5 均未合并；A03/A06 把 6 个任务变量的登记交给 A07，用户选择叠放以便引用的 ADR-010/011 在分支内存在）。worktree 最初的分支 `claude/a07-297f68` 没有提交，未删除
- **head_commit**：本文件与三个文档随同一个交付提交入库（`git log -1 -- docs/handoffs/claude-a07.md` 可查）。内容指纹：`git diff ab04053 <该提交> -- .env.example docs/integrations.md docs/tasks.md | shasum -a 256` 前 16 位 `2b4642bbdd75fc04`
- **类型**：仅文档任务，无代码、无依赖变更、无合并；网络仅用于只读核对两项向量模型的公开资料

## 一、范围与交付物

| 文件 | 改动 |
| --- | --- |
| `.env.example` | 按组加注释；新增模式开关、备用四项、调用约束七项、预算两项、向量五项、任务处理六项，共 38 个变量；所有密钥为空 |
| `docs/integrations.md` | 「运行时环境变量」改为分组表（类型与约束 / 样例 / 用途 / 状态），加状态词表与名称来源；新增「模型接入规则（A07）」：主备切换矩阵、单次调用耗时上界、预算、模型版本与向量空间、启动校验（B06）、待签收取值（D-02a～f）；「计划集成」补向量模型一行并指向上述小节 |
| `docs/tasks.md` | **范围扩展**：D-02 行改为指向签收入口；A07 认领行（DONE）及决定、后续项两条 |
| `docs/handoffs/claude-a07.md` | 本文件 |

**范围扩展说明**：清单给 A07 的文件锁是 `docs/integrations.md` 与 `.env.example`。`docs/tasks.md` 的认领行是 AGENTS.md §2 的要求；D-02 行不改的话，负责人从任务看板找不到签收入口。未触碰 `docs/decisions.md`、`docs/architecture.md`、`specs/`、`src/`、`scripts/`、`tests/`，未改其他 worktree。

## 二、形状决定（ArvinHan 于 2026-09-23 在会话中确认）

| 问题 | 决定 | 否决项与理由 |
| --- | --- | --- |
| 配置载体 | 平铺环境变量、按前缀分组，沿用 `740adb` M0-05 的模型段命名 | 按用途分模型档案：变量翻倍，S2 未要求不同提示词用不同模型；YAML 路由文件：违反 AGENTS §4「配置只能从环境变量读取」 |
| 无密钥开发 | 显式 `LLM_MODE=fake\|live`、`EMBEDDING_MODE=fake\|online\|local`；`APP_ENV=production` 禁止 fake | 「基址为空即 fake」：生产漏配时会静默走 fake |
| 问答超时 | 单独的首字超时与问答链路整体上限（改写 + 生成） | 共用 60 秒非流式超时：学生要等 60 秒才切备用，违反 ≤ 15 秒 |
| 主备切换 | 每次调用先试主用；熔断器负责粘住备用；熔断状态在进程内存 | 会话级粘住：需要额外状态，且与熔断重复 |
| 鉴权失败 | 不重试、不切备用，`LLM_UNAVAILABLE` + `details.reason = "auth"` | 切备用：掩盖配置错误，费用悄悄转到备用账号 |
| 流式问答 | 首字前可切备用；出字后不切，走 A09 撤回 | — |
| 向量 | 永不跨模型切换；在线与本地只能在部署时换，并须重新向量化 | 运行时兜底：不同模型的向量不在同一空间 |
| 预算单位 | token 软上限（任务 + 每日），`0` 不发请求，无「不限」写法 | 人民币：要为主/备/向量各配输入输出单价，价格一变预算就失真 |
| 预算范围 | 只计 LLM 调用；向量调用只记录 | — |
| 超预算 | 走所在环节既有失败路径（失败块 / 候选送审 / 问答报错），不新增任务状态；提议新码 `BUDGET_EXCEEDED` | 新增任务状态：牵动 A03 转换表 |
| 模型版本 | 模型 ID 字符串即版本；`model_calls` 另记响应 `model`；向量空间 = 模型 + 维度 | 单设版本变量：多数兼容供应商没有独立的版本参数 |

## 三、验收对照（A07 验收矩阵）

| 验收条款 | 落点 |
| --- | --- |
| 配置名 / 类型 | `docs/integrations.md`「运行时环境变量」38 行，每行有类型与约束；`.env.example` 逐项一致（核对脚本第 1～3 组） |
| 切换矩阵 | 「主备切换矩阵」11 种情形 × 重试 / 切备用 / 计熔断 / 结果 |
| embedding 维度 | `EMBEDDING_DIMENSIONS` 行、「模型版本与向量空间」、D-02c（已核对两种候选模型的维度） |
| 模型版本 | 「模型版本与向量空间」 |
| 超时 / 限并发 | 「调用约束」七项，以及单次调用耗时上界公式 |
| 预算 | 「预算」两项变量 + 计量、软上限、范围、被拒路径、错误码 |
| 真实值由负责人确认、不写密钥 | D-02a～f 全部「未签收」；所有 `*_API_KEY` 为空且状态「本机填写」（脚本第 3、7 组） |
| 人工决策保留未签收标记 | 状态列「占位（D-02x）」；D-02 表状态列（脚本第 4、7 组，负例 N6、N9） |

## 四、实际运行的命令与结果

均在 worktree 根目录执行。

| 命令 | 结果 |
| --- | --- |
| `git switch -c claude/a07-model-config claude/a06-worker-lease` | 切到新分支，HEAD `ab04053`；执行前工作区干净，本地与 `origin/claude/a06-worker-lease` 同为 `ab04053` |
| `textutil -convert txt` 转换 S2 方案 docx（输出在 scratchpad） | 读取 §3.1、§5.1.3、§6.1、§6.4.6、§6.6 的模型、向量、性能、成本相关原文 |
| 只读核对外部资料 | 阿里云百炼向量化文档（alibabacloud.com/help/zh/model-studio/embedding；help.aliyun.com 连接被拒，用的是国际站中文页）：`text-embedding-v4` 维度可选 2048/1536/1024（默认）/768/512/256/128/64、每请求至多 10 条、每条至多 8192 token、兼容接口支持 `dimensions`。Hugging Face `BAAI/bge-small-zh-v1.5` 的 `config.json`：`hidden_size` 512、`max_position_embeddings` 512 |
| `python3 check_a07.py . 740adb.env.example`（附录 A；第二个参数由 `git show origin/claude/worktree-contract-conflicts-740adb:.env.example` 导出） | **344/344 PASS**，exit 0 |
| `python3 neg_a07.py . <scratchpad>`（附录 B） | N1～N11 共 11 个篡改副本均 exit 1，每个都命中对应检查：**ALL DETECTED** |
| `./scripts/verify.sh` | exit 0（「block-dangerous hook tests passed.」「Scaffold verification passed.」） |
| `git diff --check` | exit 0 |

**未运行 / 未验证**：
- 没有任何实现和运行时测试，本任务的规则是 B06/E03/E04/E07 的验收契约。
- 没有调用任何付费模型。
- DeepSeek / 通义千问的模型 ID 与价格未核对（D-02a/b/d 已标注）。
- 未跑 A03/A06 的核对脚本。它们不在本仓库，而本任务也未改 `specs/` 与 `docs/decisions.md`。

## 五、接口 / 数据 / 配置变更

- **配置**：新增 26 个环境变量名，均向后兼容：main 原有的 12 个名称与取值不变，新增项都有样例值。取值非法时拒绝启动（B06 实现）。
- **契约**：无改动。提议新增 `ErrorCode.BUDGET_EXCEEDED`（D-02f），由 B08 落契约。`EXTRACTION_INCOMPLETE` 仍是 ADR-010 的提议码。
- **数据**：无迁移。预算读取 ADR-011 已规划的 `model_calls`，要求记录请求模型 ID、响应 `model` 字段和 usage。

## 六、未完成 / 风险

- **分支叠放**：本分支基于未合并的 A06（PR #6）和 A03（PR #5）。若它们在合并前修改 §8.8 默认值或阈值，需要变基后重跑附录 A；负例 N3、N11 证明漂移会被检出。
- **与 `740adb` 的文本冲突**：两边都改了 `.env.example` 和 `docs/integrations.md`。A10 导入时，模型与任务段取本分支，`STORAGE_DIR`、`NEO4J_DATABASE`、Neo4j 容器变量和「本地依赖环境」一节取 `740adb`。变量名已对齐，不存在语义冲突。
- **样例值未经验证**：按样例值，单次非流式调用的最坏耗时约 6 分钟（主备各 3 次 × 60 秒），会拉长 A03 的取消生效时延，D-02e 签收时要确认。并发 4 与 S2 估算的 8 路不一致，对 50 秒构图目标的影响待实测。
- **软上限可超出**：最多超出「并发数 × 单次调用 token」。token 总量不区分输入、输出单价，只能当作安全上限用。
- **熔断状态不跨进程**：`WORKER_PROCESSES > 1` 时，每个进程各自摸索熔断，故障期间会多出一些失败调用。默认 1 个进程时没有影响。
- **别名漂移**：供应商的自动升级别名会让缓存漏失效，D-02a 签收时须注明所选 ID 是否为别名。
- **本地向量截断**：`bge-small-zh-v1.5` 最长 512 token，S2 的约 1500 字分块会被截断。选 `local` 前必须先定截断或分块策略（D-02c）。
- **ADR 编号**：签收时取当时 `docs/decisions.md` 的下一个空闲编号。A04、A05 在并行 worktree 中也可能占用 012 及以后的编号。

## 七、下一位 Agent 的首个动作

1. **负责人**：在 `docs/integrations.md`「待签收取值（D-02）」逐项签收，写 ADR，再把状态列改为「已签收」并同步 `.env.example`。签收前 fake 模式的实现可以先做。
2. **B06**：按「启动校验」和各表的类型约束写 `config.py`，负例至少覆盖非法端口、预算为负、维度为 0、备用只填一部分、生产环境下用 fake、首字超时 ≥ 整体上限。
3. **E04**：把切换矩阵逐行转成测试，fake 适配器要能注入 429、5xx、超时、401、坏 JSON，并上报模拟 usage。
4. **B08**：加 `BUDGET_EXCEEDED`，并确定它的 HTTP 状态。

## 八、回滚

本任务只改文档，不涉及持久层或依赖。
- **未提交时**：`git restore .env.example docs/integrations.md docs/tasks.md`，再删除本文件。
- **已提交时**：`git revert <交付提交>`。

不影响其他 worktree 和分支。

## 九、Codex 审查修复（A07-R01）

- **task_id**：A07-R01 修复
- **状态**：DONE。修复方案由 ArvinHan 于 2026-09-23 在会话中选择并签收，记为 **ADR-011 修订 2**（决定 12）
- **review_status**：ready_for_review
- **worktree / 分支**：`.claude/worktrees/a04-f5f479`，分支 `claude/a07-r01-fix`，base `8340b1e`（= 合入 PR #11 后的 `origin/main`）
- **审查报告**：主目录 `docs/reviews/codex-claude-a05-a07-2026-09-23-0804z.md`（目标提交 `af9ff7d`，尚未入库）

**核对结论**：成立。沿用的去重键「任务 + 块 + 用途 + 尝试序号」在同一块尝试内对 L1 重试、备用调用、E05 修复取值相同，按键去重会吞掉真实用量；问答调用无任务 ID，键无从定义。另有一处报告未提及：断线或超时时供应商侧已产生的用量拿不到，「收到响应才记录」会让这类调用完全漏计。

| 选择（用户签收） | 否决 | 落点 |
| --- | --- | --- |
| 每次实际调用一个 `call_id`，发请求前预写，未收到响应按「输入估算 + 声明的输出上限」计入；问答以 `request_id` 归属 | 确定性复合键；只加 `call_id`、收到响应才记录 | `docs/integrations.md`「预算」计量/软上限/任务预算/每日预算与新增「调用记录（`model_calls`）」；`specs/task-processing.md` §8.4「计费不重复」、LEASE-17、LEASE-24～27；`docs/decisions.md` ADR-011 修订 2 |

**验证**：

```text
./scripts/verify.sh                          exit 0
git add … && git diff --cached --check       exit 0
python3 check_a07.py .（附录 A）              329/329 PASS（main 基线 328/328；多出的一项是新增「见「调用记录」」引用检查）
python3 check_a06.py 第二版 . api.v1.yaml     ALL PASS（LEASE 编号连续到 27）
A04 核对脚本                                 ALL PASS
python3 check_a07r01.py .（附录 C）           正例 exit 0，17 项 ALL PASS
  N1 任务预算改回旧键                         exit 1
  N2 删去「预写失败则不发请求」               exit 1
  N3 删除 LEASE-26                           exit 1
  N4 字段表删去 request_id                    exit 1
```

专项脚本首跑有 2 项 FAIL，是脚本自身问题：`integrations.md` 有两个 `### 预算` 标题（变量表与规则），脚本切到了前一个；改为按「`### 预算` 紧接 `- **计量**`」定位后通过，文档未因此改动。四个负例在修正后重跑，各只命中目标断言。

**遗留**：估算值通常明显高于真实用量，断线频繁时预算会提前触顶（有意的保守方向）；`purpose` 的枚举由 E03 定；尚无实现或自动化测试。

**下一步**：请 Codex 按本轮提交复核 A07-R01。

## 十、Codex 复审修复（FIX-R01）

- **task_id**：FIX-R01 修复（Codex REVIEW-09）
- **状态**：DONE。方向由 ArvinHan 于 2026-09-23 在会话中选定（按错误类型区分），记为 **ADR-011 修订 3**（决定 13）；书面条文（含下列推导细则）由 ArvinHan 于 2026-09-23 签收
- **review_status**：ready_for_review（以交付提交为准，提交前不生效）
- **worktree / 分支**：`.claude/worktrees/quirky-dijkstra-eca5de`，分支 `claude/fix-r01-r02`，base `1a47eb2`（= 合入 PR #12 后的 `origin/main`）
- **head_commit**：随交付提交入库（`git log -1 -- docs/handoffs/claude-a07.md` 可查）。内容指纹：`git diff 1a47eb2 <该提交> -- docs/integrations.md specs/task-processing.md specs/teacher-review-publish.md docs/decisions.md docs/architecture.md | shasum -a 256` 前 16 位 `7efe9ef5a417f8a2`（与 FIX-R02 同批，五个文件合算；含签收行）
- **审查报告**：主目录 `docs/reviews/codex-claude-a04-fixes-1012b6f-2026-09-23-1215z.md`（目标提交 `1012b6f`，尚未入库）
- **同批**：FIX-R02 见 `docs/handoffs/claude-a04.md` 第十一节；两项共用本文件附录 D、E 的核对与负例脚本

**核对结论**：成立。修订 2 只在「未收到响应、停在 `sent`」时估算，已回写但不带 usage 的调用按 0 计。部分 OpenAI 兼容供应商在流式响应中默认不返回 usage，这类真实调用会从预算中消失。

| 选择（用户签收） | 否决 | 落点 |
| --- | --- | --- |
| 缺 usage 时按错误类型区分：生成前被拒（`400/401/403/404/413/422/429`）计 0；其余（成功、`408`、`5xx`、流中途断开、响应无法解析）按「输入估算 + 输出上限」计 | 一律按估算（报告的最小修复）：任务预算跨尝试不清零，限流期间每次 `429` 都按上限扣，会把可用性故障变成预算失败。成功响应按本地计数实际输出：暂不采纳，先靠流式请求 usage 减少缺失 | `docs/integrations.md`「预算」计量条，「调用记录」第 2、4 条与新增第 5 条，字段表三行，计费量一行，D-02a/b 两行；`specs/task-processing.md` §8.4「计费不重复」、LEASE-28～30；`docs/decisions.md` ADR-011 修订 3 与两处指针 |

**由方向推导、未单独询问的细则**（已随书面条文签收）：

1. 「生成前被拒」名单取 `400`、`401`、`403`、`404`、`413`、`422`、`429`；`408` 与 `5xx` 不在名单内，因为无法确认供应商是否已开始生成。
2. 错误响应若带 usage，按 usage 计，不按 0 或估算。
3. E03 在流式请求中请求 usage（`stream_options.include_usage`）；D-02a/b 签收时注明供应商是否返回 usage。
4. `usage_estimated` 仍为派生字段，规则改为「usage 为空且不属于生成前被拒」，不新增存储列。

**验证**：

```text
./scripts/verify.sh                               exit 0
git diff --check                                  exit 0
python3 check_fix.py .（附录 D）                  修改前 38 FAIL / exit 1；修改后 40 项 ALL PASS / exit 0
python3 neg_fix.py . <scratch>（附录 E）          6 个篡改副本全部 exit 1，各只命中目标断言
python3 check_a07.py . 740adb.env.example（附录 A）修改前 345/345，修改后 347/347 PASS
python3 check_a07r01.py .（附录 C）               ALL PASS
python3 check_a06.py . api.v1.yaml（A06 第二版）   ALL PASS
check_a04.py（A04 第二版）                        修改前 2 项 FAIL；签收后 3 项，新增 1 项为脚本边界问题（见下）
```

- `check_a07` 多出的 2 项来自脚本第 114 行，它逐个核对「见「…」」引用的小节是否存在。本轮新增了「见「调用记录」第 5 条」「见「主备切换矩阵」」两处引用，两个小节都存在。
- `check_a04` 的 2 项 FAIL 在修改前就有，属于脚本过时，不是文档缺陷：「远端任何分支均未使用 ADR-012」是 A04 撰写时的撞号预检，ADR-012 现已合入 main；「PUB 编号为 1..34」写死了上限，A06 修复加了 PUB-35，本轮又加了 PUB-36～38。
- 签收后 `check_a04` 新增的 1 项是「ADR-012 修订 1 存在且已签收」：脚本第 85 行统计「`### ADR-012 修订 1` 到 `## ADR-013` 之间的签收行恰好 1 条」，假定修订 1 是 ADR-012 的最后一个小节。修订 2 排在它之后，签收后该范围内有 2 条。按「修订 1 到修订 2」截取复核，两个修订各恰好 1 条签收行。
- 专项脚本首轮有两个负例（N2 删名单中的 `429`、N5 写入核对改回只比维度）未被检出，原因是脚本的问题：`429` 在同一行后半句还出现一次，「空间标识」在同一条目的后半句也出现。两条断言改为只截取名单本身与「F 组写入前」这一分句后，6 个负例全部检出。文档没有因此改动。
- 全仓库搜索「无 usage 记 0」等旧表述，只剩 ADR 修订史中的引用。

**遗留**：估算通常高于真实用量；若所选供应商都不返回 usage，每次调用按输出上限计，预算会明显提前触顶，D-02a/b/d 签收时要一并考虑。仍没有实现或自动化测试。

**下一步**：请 Codex 按交付提交复核 FIX-R01；修复另开一轮。

## 附录 A：`check_a07.py`（核对脚本全文）

```python
#!/usr/bin/env python3
"""A07 核对：.env.example ↔ integrations.md ↔ specs/task-processing.md ↔ 740adb 命名。

用法：check_a07.py <repo_root> [<740adb .env.example 路径>]
任一项 FAIL 则 exit 1。
"""
import re
import sys
from pathlib import Path

root = Path(sys.argv[1])
adb_env = Path(sys.argv[2]) if len(sys.argv) > 2 else None
results = []


def check(name, ok, detail=""):
    results.append((name, bool(ok), detail))


env_text = (root / ".env.example").read_text(encoding="utf-8")
env = {}
for line in env_text.splitlines():
    line = line.strip()
    if not line or line.startswith("#"):
        continue
    k, _, v = line.partition("=")
    check(f"env 行格式 {k}", re.fullmatch(r"[A-Z][A-Z0-9_]*", k), line)
    check(f"env 无重复 {k}", k not in env)
    env[k] = v

integ = (root / "docs/integrations.md").read_text(encoding="utf-8")
sec = integ.split("## 运行时环境变量", 1)[1].split("\n## ", 1)[0]
rows = {}
for line in sec.splitlines():
    m = re.match(r"^\| `([A-Z][A-Z0-9_]*)` \| (.*)$", line)
    if not m:
        continue
    cells = [c.strip() for c in m.group(2).rstrip("|").split(" | ")]
    check(f"表行列数 {m.group(1)}", len(cells) == 4, line)
    check(f"表无重复 {m.group(1)}", m.group(1) not in rows)
    rows[m.group(1)] = cells  # 类型, 样例, 用途, 状态

# 1. 变量集合一致
check("集合：env 中每个变量都在表中", set(env) <= set(rows), sorted(set(env) - set(rows)))
check("集合：表中每个变量都在 env 中", set(rows) <= set(env), sorted(set(rows) - set(env)))

# 2. 样例列 == env 值
for k, cells in rows.items():
    if k not in env:
        continue
    sample = cells[1]
    want = "" if sample == "空" else sample.strip("`")
    check(f"样例一致 {k}", want == env[k], f"表={sample!r} env={env[k]!r}")

# 3. 密钥：类型为密钥 ⇔ 状态本机填写；API_KEY 在 env 中必须为空
for k, cells in rows.items():
    is_secret = cells[0].startswith("密钥")
    check(f"密钥状态 {k}", is_secret == (cells[3] == "本机填写"), cells)
    if k.endswith("_API_KEY"):
        check(f"密钥为空 {k}", env.get(k) == "", env.get(k))
        check(f"密钥类型 {k}", is_secret, cells[0])

# 4. 状态词表 + D-02 引用存在
d02 = set(re.findall(r"^\| (D-02[a-z]) \|", integ, re.M))
check("D-02 表含 a～f", d02 == {f"D-02{c}" for c in "abcdef"}, sorted(d02))
allowed = re.compile(r"^(已约定|本机填写|A07 定形|已签收（ADR-01[01]）|占位（D-02[a-f]）|占位（D-02[a-f]；.*）|已约定；取值待 D-02[a-f]|已约定（取值集合为 A07 定形）|A07 定形；.*D-02[a-f])$")
for k, cells in rows.items():
    check(f"状态词表 {k}", allowed.match(cells[3]), cells[3])
    for ref in re.findall(r"D-02[a-z]", cells[3]):
        check(f"D-02 引用存在 {k}→{ref}", ref in d02)

# 5. 任务六项对 specs/task-processing.md §8.8 与 §5
spec = (root / "specs/task-processing.md").read_text(encoding="utf-8")
s88 = spec.split("### 8.8 配置", 1)[1].split("\n### ", 1)[0]
spec_rows = {}
for line in s88.splitlines():
    m = re.match(r"^\| `([A-Z_]+)` \| ([^|]+) \| ([^|]+) \|$", line)
    if m:
        spec_rows[m.group(1)] = (m.group(2).strip(), m.group(3).strip())
check("§8.8 恰五项", len(spec_rows) == 5, sorted(spec_rows))
for k, (typ, default) in spec_rows.items():
    check(f"§8.8 默认 {k}", env.get(k) == default, f"spec={default} env={env.get(k)}")
    lower = re.search(r"≥ (\d+)", typ).group(1)
    check(f"§8.8 下界 {k}", k in rows and f"≥ {lower}" in rows[k][0], rows.get(k))
check("§5 阈值默认 0.2", "`TASK_MAX_FAILED_CHUNK_RATIO`，来自环境变量，默认 `0.2`，取值 `[0, 1)`" in spec)
check("阈值 env=0.2", env.get("TASK_MAX_FAILED_CHUNK_RATIO") == "0.2")
check("阈值区间一致", "TASK_MAX_FAILED_CHUNK_RATIO" in rows and "`[0, 1)`" in rows["TASK_MAX_FAILED_CHUNK_RATIO"][0])

# 6. 沿用 740adb 模型段命名
if adb_env:
    adb = [l.split("=", 1)[0] for l in adb_env.read_text(encoding="utf-8").splitlines()
           if re.match(r"^(LLM|EMBEDDING)_", l)]
    check("740adb 模型变量 ≥ 15", len(adb) >= 15, adb)
    for k in adb:
        check(f"沿用 740adb 名 {k}", k in env)

# 7. A07 验收矩阵：维度、模型版本、超时、限并发、预算、切换矩阵、签收入口
for label, needle in [
    ("embedding 维度", "`EMBEDDING_DIMENSIONS`"),
    ("模型版本", "### 模型版本与向量空间"),
    ("超时", "`LLM_REQUEST_TIMEOUT_SECONDS`"),
    ("限并发", "`LLM_MAX_CONCURRENCY`"),
    ("预算", "### 预算\n\n- **计量**"),
    ("切换矩阵", "### 主备切换矩阵"),
    ("签收入口", "### 待签收取值（D-02）"),
    ("启动校验", "### 启动校验（B06）"),
]:
    check(f"验收：{label}", needle in integ)
for c in "abcdef":
    row = re.search(rf"^\| D-02{c} \|.*\| 未签收[^|]*\|$", integ, re.M)
    check(f"D-02{c} 保留未签收标记", row)

# 8. 章内交叉引用的小节都存在
for ref in re.findall(r"见「([^」]+)」", integ):
    heads = re.findall(r"^#{2,3} (.+)$", integ, re.M)
    check(f"引用小节存在「{ref}」", any(h.startswith(ref) for h in heads), ref)

# 9. tasks.md D-02 行指向签收入口
tasks = (root / "docs/tasks.md").read_text(encoding="utf-8")
check("tasks D-02 指向入口", re.search(r"^\| D-02 \|.*「待签收取值（D-02）」", tasks, re.M))

fails = [r for r in results if not r[1]]
for name, ok, detail in results:
    if not ok:
        print(f"FAIL {name} :: {detail}")
print(f"{len(results) - len(fails)}/{len(results)} PASS")
sys.exit(1 if fails else 0)
```

## 附录 B：`neg_a07.py`（负例脚本全文）

需要与 `check_a07.py`、`740adb.env.example` 放在同一目录（第二个参数）。

```python
import shutil, subprocess, sys, re
from pathlib import Path
src = Path(sys.argv[1]); S = Path(sys.argv[2]); adb = S / "740adb.env.example"
files = [".env.example", "docs/integrations.md", "docs/tasks.md", "specs/task-processing.md"]
def mk(name, edits):
    d = S / "neg" / name
    if d.exists(): shutil.rmtree(d)
    for f in files:
        (d / f).parent.mkdir(parents=True, exist_ok=True); shutil.copy(src / f, d / f)
    for f, old, new in edits:
        p = d / f; t = p.read_text(encoding="utf-8")
        assert t.count(old) >= 1, (name, old); p.write_text(t.replace(old, new), encoding="utf-8")
    return d
E, I, T = ".env.example", "docs/integrations.md", "docs/tasks.md"
cases = {
 "N1 删 env 变量": [(E, "LLM_CHAT_TIMEOUT_SECONDS=15\n", "")],
 "N2 env 样例漂移": [(E, "LLM_MAX_RETRIES=2", "LLM_MAX_RETRIES=3")],
 "N3 租约默认与规格不符(两处同改)": [(E, "TASK_LEASE_SECONDS=60", "TASK_LEASE_SECONDS=30"), (I, "| `TASK_LEASE_SECONDS` | 整数 ≥ 15 | `60` |", "| `TASK_LEASE_SECONDS` | 整数 ≥ 15 | `30` |")],
 "N4 密钥入库": [(E, "LLM_API_KEY=\n", "LLM_API_KEY=sk-test\n")],
 "N5 删 D-02c 行": [(I, "| D-02c |", "| X-02c |")],
 "N6 冒称已签收 ADR-012": [(I, "| 占位（D-02d） |", "| 已签收（ADR-012） |")],
 "N7 删模型版本小节": [(I, "### 模型版本与向量空间", "### 模型说明")],
 "N8 改名偏离 740adb(两处同改)": [(E, "LLM_FALLBACK_CHAT_MODEL=", "LLM_BACKUP_CHAT_MODEL="), (I, "`LLM_FALLBACK_CHAT_MODEL` |", "`LLM_BACKUP_CHAT_MODEL` |")],
 "N9 D-02e 去掉未签收": [(I, "| 见「调用约束」 | 未签收 |", "| 见「调用约束」 | 已签收 |")],
 "N10 tasks D-02 行回退": [(T, "签收入口见 `docs/integrations.md`「待签收取值（D-02）」", "签收入口待定")],
 "N11 阈值区间改闭区间": [(I, "| 数值，取值 `[0, 1)` |", "| 数值，取值 `[0, 1]` |")],
}
bad = 0
for name, edits in cases.items():
    d = mk(name.split()[0], edits)
    r = subprocess.run([sys.executable, str(S / "check_a07.py"), str(d), str(adb)], capture_output=True, text=True)
    first = next((l for l in r.stdout.splitlines() if l.startswith("FAIL")), "")[:110]
    print(f"{'OK ' if r.returncode == 1 else 'MISS'} {name} exit={r.returncode} :: {first}")
    if r.returncode != 1 or r.stderr: bad += 1; print(r.stderr[-500:])
print("ALL DETECTED" if bad == 0 else f"{bad} NOT DETECTED")
sys.exit(1 if bad else 0)
```

## 附录 C：`check_a07r01.py`（A07-R01 修复核对）

用法：`python3 check_a07r01.py <仓库根目录>`。

```python
"""A07-R01 修复核对：check_a07r01.py <repo_root>；任一 FAIL 则 exit 1。"""
import re, sys
from pathlib import Path
root = Path(sys.argv[1])
tp = (root / "specs/task-processing.md").read_text(encoding="utf-8")
integ = (root / "docs/integrations.md").read_text(encoding="utf-8")
dec = (root / "docs/decisions.md").read_text(encoding="utf-8")
fails = []
def ok(c, m):
    print(("PASS " if c else "FAIL ") + m)
    if not c: fails.append(m)
bill = next((l for l in tp.splitlines() if l.startswith("**计费不重复**")), "")
ok("`call_id`" in bill and "预写失败则不发请求" in bill, "§8.4 计费不重复：以 call_id 去重、预写失败不发请求")
ok("未收到响应的调用按「输入估算 + 声明的输出上限」计入" in bill, "§8.4：未收到响应按估算计入")
ok("键为「任务 + 块" not in bill, "§8.4：旧复合键不再作为去重键")
K = "### 预算\n\n- **计量**"  # 文中有两个「### 预算」：前者是变量表，这里要的是规则小节
budget = ("- **计量**" + integ.split(K, 1)[1]).split("\n### ", 1)[0] if K in integ else ""
task_b = next((l for l in budget.splitlines() if l.startswith("- **任务预算**")), "")
ok("按 `call_id` 去重" in task_b and "（任务 + 块 + 用途 + 尝试序号）" not in task_b, "预算：任务预算按 call_id 去重")
daily = next((l for l in budget.splitlines() if l.startswith("- **每日预算**")), "")
ok("无任务 ID 的问答调用" in daily, "预算：每日预算覆盖无任务 ID 的问答调用")
rec = integ.split("### 调用记录（`model_calls`）", 1)[1].split("\n### ", 1)[0] if "### 调用记录（`model_calls`）" in integ else ""
for f in ("call_id", "request_id", "input_tokens_est", "max_output_tokens", "usage_estimated", "provider_role", "is_repair"):
    ok(f"`{f}`" in rec, f"调用记录字段表含 {f}")
ok("声明输出 token 上限" in rec, "调用记录：E03 必须声明输出上限")
ids = {int(n) for n in re.findall(r"\*\*LEASE-(\d+)\*\*", tp)}
ok({24, 25, 26, 27} <= ids and ids == set(range(1, max(ids) + 1)), f"LEASE-24～27 存在且编号连续（最大 {max(ids)}）")
l24 = next((l for l in tp.splitlines() if "**LEASE-24**" in l), "")
ok("A07-R01" in l24 and "估算" in l24, "LEASE-24 为 A07-R01 回归")
l26 = next((l for l in tp.splitlines() if "**LEASE-26**" in l), "")
ok("`request_id`" in l26 and "不计入任何任务预算" in l26, "LEASE-26 覆盖无任务 ID 的问答调用")
r2 = dec.split("### ADR-011 修订 2", 1)[1].split("## ADR-012", 1)[0] if "### ADR-011 修订 2" in dec else ""
ok(bool(r2) and "**签收**：ArvinHan 2026-09-23" in r2, "ADR-011 修订 2 存在、位于 ADR-012 前且已签收")
print(f"\nRESULT: {'ALL PASS' if not fails else str(len(fails)) + ' FAIL'}"); sys.exit(1 if fails else 0)
```

## 附录 D：`check_fix.py`（FIX-R01/R02 修复核对）

用法：`python3 check_fix.py <仓库根目录>`。

```python
"""FIX-R01/R02 修复核对：check_fix.py <repo_root>；任一 FAIL 则 exit 1。"""
import re, sys
from pathlib import Path
root = Path(sys.argv[1])
rd = lambda p: (root / p).read_text(encoding="utf-8")
integ, tp, pub, dec, arch = (rd("docs/integrations.md"), rd("specs/task-processing.md"),
                             rd("specs/teacher-review-publish.md"), rd("docs/decisions.md"),
                             rd("docs/architecture.md"))
fails = []
def ok(c, m):
    print(("PASS " if c else "FAIL ") + m)
    if not c: fails.append(m)
def section(text, head, stop="\n### "):
    return text.split(head, 1)[1].split(stop, 1)[0] if head in text else ""
def line(text, prefix):
    return next((l for l in text.splitlines() if l.startswith(prefix)), "")
REJECT = ("400", "401", "403", "404", "413", "422", "429")

# ---------- FIX-R01：响应无 usage 的计费 ----------
budget = section(integ, "### 预算\n\n- **计量**")  # 文中有两个「### 预算」，这里取规则小节
meter = line("- **计量**" + budget, "- **计量**")
ok("记 0）" not in meter and "不含 usage 记 0" not in meter, "预算·计量：不再把无 usage 的响应记 0")
ok("生成前被拒" in meter and "估算" in meter, "预算·计量：区分生成前被拒与其余缺 usage 情形")
rec = section(integ, "### 调用记录（`model_calls`）")
ok(bool(rec), "调用记录小节存在")
bill = line(rec, "计费量")
ok("无 usage 记 0" not in bill, "调用记录·计费量：删去「无 usage 记 0」")
ok("生成前被拒" in bill and "input_tokens_est + max_output_tokens" in bill, "调用记录·计费量：三种情形齐全")
rej = line(rec, "5. **生成前被拒**")
rej_list = rej.split("HTTP ", 1)[-1].split("的错误响应", 1)[0]  # 只取名单本身，后文还会再提到 429
ok(all(f"`{c}`" in rej_list for c in REJECT), "调用记录：生成前被拒的 HTTP 状态码为 400/401/403/404/413/422/429")
ok("408" in rej and "5xx" in rej, "调用记录：明确 408 与 5xx 不属于生成前被拒")
ok("stream_options" in rec and "include_usage" in rec, "调用记录：E03 流式请求须请求 usage")
est_row = next((l for l in rec.splitlines() if l.startswith("| `usage_estimated`")), "")
ok("已回写" in est_row and "生成前被拒" in est_row, "字段表：usage_estimated 覆盖已回写但无 usage 的情形")
err_row = next((l for l in rec.splitlines() if "`error_class`" in l and l.startswith("|")), "")
ok("生成前被拒" in err_row, "字段表：error_class 标出生成前被拒类")
for d in ("D-02a", "D-02b"):
    row = next((l for l in integ.splitlines() if l.startswith(f"| {d} |")), "")
    ok("usage" in row, f"{d} 签收时注明供应商是否返回 usage")
ok("响应不含 usage 记 0" not in integ and "无 usage 记 0" not in integ, "integrations.md 全文无「记 0」旧规则残留")
b84 = line(tp, "**计费不重复**")
ok("未收到响应的调用按「输入估算 + 声明的输出上限」计入" in b84, "§8.4：保留未收到响应按估算计入（A07-R01 回归）")
ok("usage" in b84 and "生成前被拒" in b84 and "修订 3" in b84, "§8.4：补上收到响应但无 usage 的规则并指向修订 3")
lease = {int(n) for n in re.findall(r"\*\*LEASE-(\d+)\*\*", tp)}
ok({28, 29, 30} <= lease and lease == set(range(1, max(lease) + 1)), f"LEASE-28～30 存在且编号连续（最大 {max(lease)}）")
l = lambda n: next((x for x in tp.splitlines() if f"**LEASE-{n}**" in x), "")
ok("FIX-R01" in l(28) and "成功" in l(28) and "估算" in l(28), "LEASE-28：成功响应无 usage 按估算（FIX-R01 回归）")
ok("5xx" in l(29) and "估算" in l(29), "LEASE-29：错误响应（5xx）无 usage 按估算")
ok("429" in l(30) and "0" in l(30) and "带 usage" in l(30), "LEASE-30：429 无 usage 计 0，带 usage 的错误响应按 usage")
r2 = section(dec, "### ADR-011 修订 2", "\n## ADR-012")
r3 = section(dec, "### ADR-011 修订 3", "\n## ADR-012")
ok(bool(r3) and dec.index("### ADR-011 修订 3") < dec.index("## ADR-012："), "ADR-011 修订 3 存在且位于 ADR-012 之前")
ok("**签收**" in r3 and "FIX-R01" in r3, "ADR-011 修订 3 有签收行并注明来源")
ok("修订 3" in line(r2.split("- **决定**", 1)[-1].lstrip("：\n"), "  12."), "修订 2 决定 12 旁有指向修订 3 的注记")
head011 = section(dec, "## ADR-011：", "\n- **日期**")
ok("修订 3" in head011, "ADR-011 引言有修订 3 指针")

# ---------- FIX-R02：向量迁移按实际存量 ----------
v12 = section(pub, "### V12 向量空间切换", "\n## ")
inv = line(v12, "- **单一空间不变式**")
ok("实际存储" in inv and "不可见" in inv, "V12 不变式：覆盖实际存储的全部对象，含不可见草稿")
ok("已到 `awaiting_review` / `completed` 的任务所产生的全部修订的文本块" not in v12, "V12 第 3 步：删去按任务状态推导的目标集合")
s3 = line(v12, "  3. ")
ok("实际存量" in s3 and "失败" in s3 and "中断" in s3, "V12 第 3 步：目标为 Neo4j 实际存量，含失败/中断任务留下的块")
s4 = line(v12, "  4. ")
ok("实际存量" in s4 and "0" in s4 and "不从任务状态推导" in s4, "V12 第 4 步：按实际存量核对缺新空间向量数为 0")
s6 = line(v12, "  6. ")
ok("缓存" in s6, "V12 第 6 步：一并清理旧空间的向量缓存")
cache = line(v12, "- **空间标识随向量走**")
ok("缓存键" in cache and "中间产物" in cache and "维度相同" in cache, "V12：缓存/中间产物带空间标识，写入按空间标识而非维度拒绝")
pubs = [int(n) for n in re.findall(r"\*\*PUB-(\d+)\*\*", pub)]
ok({36, 37, 38} <= set(pubs) and sorted(pubs) == list(range(1, max(pubs) + 1)), f"PUB-36～38 存在、编号连续不重复（最大 {max(pubs)}）")
p = lambda n: next((x for x in pub.splitlines() if f"**PUB-{n}**" in x), "")
ok("FIX-R02" in p(36) and "中断" in p(36) and "接管" in p(36), "PUB-36：中断任务留块后切换空间再接管（FIX-R02 回归）")
ok("核对" in p(37) and "不切换" in p(37), "PUB-37：存量中有漏算对象时第 4 步失败、不切换")
ok("缓存" in p(38) and "维度相同" in p(38), "PUB-38：同维度换模型时缓存不命中、旧空间写入被拒")
v10 = next((x for x in pub.splitlines() if x.startswith("| B06 / D09 / D10 / E07 / F03")), "")
ok("空间标识" in v10, "V10：E07/F03 实现依赖含空间标识")
emb = next((x for x in integ.splitlines() if x.startswith("- **向量空间标识**")), "")
emb_write = emb.split("F 组写入前", 1)[-1].split("；", 1)[0]  # 只取写入核对这一分句
ok("空间标识" in emb_write and "只比对维度" in emb_write and "缓存键" in emb, "integrations：写入按空间标识核对、缓存键含空间")
arow = next((x for x in arch.splitlines() if x.startswith("| 向量空间 |")), "")
ok("实际存量" in arow and "修订 2" in arow, "architecture：向量空间一行指向按实际存量迁移（修订 2）")
r12_1 = section(dec, "### ADR-012 修订 1", "\n## ADR-013")
r12_2 = section(dec, "### ADR-012 修订 2", "\n## ADR-013")
ok(bool(r12_2) and dec.index("### ADR-012 修订 2") < dec.index("## ADR-013："), "ADR-012 修订 2 存在且位于 ADR-013 之前")
ok("**签收**" in r12_2 and "FIX-R02" in r12_2, "ADR-012 修订 2 有签收行并注明来源")
ok("修订 2" in line(r12_1.split("- **决定**", 1)[-1].lstrip("：\n"), "  11."), "修订 1 决定 11 旁有指向修订 2 的注记")
head012 = section(dec, "## ADR-012：", "\n- **日期**")
ok("修订 2" in head012, "ADR-012 引言有修订 2 指针")

print(f"\nRESULT: {'ALL PASS' if not fails else str(len(fails)) + ' FAIL'} ({len(fails)} fail)")
sys.exit(1 if fails else 0)
```

## 附录 E：`neg_fix.py`（FIX-R01/R02 负例）

用法：`python3 neg_fix.py <仓库根目录> <临时目录>`，`check_fix.py` 须在临时目录中；每个篡改副本都必须使其非 0 退出。

```python
"""FIX-R01/R02 负例：neg_fix.py <repo_root> <scratch>。每个篡改副本都必须使 check_fix.py 非 0 退出。"""
import shutil, subprocess, sys
from pathlib import Path
src, S = Path(sys.argv[1]), Path(sys.argv[2])
FILES = ["docs/integrations.md", "specs/task-processing.md", "specs/teacher-review-publish.md",
         "docs/decisions.md", "docs/architecture.md"]
CASES = {
    "N1 计量改回「响应不含 usage 记 0」": ("docs/integrations.md",
        "响应是生成前被拒的错误且不带 usage 时计 0", "响应不含 usage 记 0）；响应是生成前被拒的错误且不带 usage 时计 0"),
    "N2 生成前被拒名单删去 429": ("docs/integrations.md", "、`422`、`429` 的错误响应", "、`422` 的错误响应"),
    "N3 V12 第 3 步改回按任务状态推导": ("specs/teacher-review-publish.md",
        "按新空间计算并写入 Neo4j 的**实际存量**：", "按新空间计算并写入：已到 `awaiting_review` / `completed` 的任务所产生的全部修订的文本块。"),
    "N4 删除 PUB-36": ("specs/teacher-review-publish.md", "  - **PUB-36**", "  - PUB-36 已删"),
    "N5 写入核对改回只比对维度": ("docs/integrations.md",
        "F 组写入前比对向量的空间标识与当前空间（维度相同的两个模型只比对维度无法区分）", "F 组写入前比对 Neo4j 索引维度"),
    "N6 删除 LEASE-30": ("specs/task-processing.md", "  - **LEASE-30**", "  - LEASE-30 已删"),
}
bad = 0
for name, (f, old, new) in CASES.items():
    d = S / "neg" / name.split()[0]
    shutil.rmtree(d, ignore_errors=True)
    for x in FILES:
        (d / x).parent.mkdir(parents=True, exist_ok=True); shutil.copy(src / x, d / x)
    t = (d / f).read_text(encoding="utf-8"); assert t.count(old) == 1, (name, t.count(old))
    (d / f).write_text(t.replace(old, new), encoding="utf-8")
    r = subprocess.run([sys.executable, str(S / "check_fix.py"), str(d)], capture_output=True, text=True)
    hits = [l[5:] for l in r.stdout.splitlines() if l.startswith("FAIL")]
    print(f"{name}: exit {r.returncode}；命中 {hits}")
    bad += r.returncode == 0
print("NEGATIVES:", "ALL DETECTED" if not bad else f"{bad} 未检出"); sys.exit(1 if bad else 0)
```
