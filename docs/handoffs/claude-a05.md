# A05：定义课程成员与本地身份边界

- **task_id**：A05（`docs/atomic-task-plan.md` / `docs/atomic-tasks.json`）
- **状态**：DONE。决定方向由 ArvinHan 于 2026-09-23 在会话中逐项选定，书面条文同日签收，记为 **ADR-013**；D-03 关闭
- **review_status**：ready_for_review
- **worktree**：`/Users/arvinhan/Desktop/SmartSketch/.claude/worktrees/a05-aa1561`
- **分支 / base_commit**：`claude/a05-identity-access` / `931361d`（= `origin/main`）
- **head_commit**：本文件与三个文档随同一个交付提交入库（`git log -1 -- docs/handoffs/claude-a05.md` 可查），review 的固定基线取该提交
- **类型**：仅文档任务，无代码、无依赖变更、无合并、无网络调用

## 一、范围与交付物

| 文件 | 改动 |
| --- | --- |
| `specs/identity-access.md` | **新建**。账号与登录（§1）、访问令牌与调用者身份（§2）、课程成员（§3）、授权判定顺序、错误语义与逐操作访问矩阵（§4，33 行）、SSE 事件票据（§5）、配置项（§6）、契约改动清单（§7）、验收 IAM-1～25（§8） |
| `docs/decisions.md` | 新增 ADR-013（背景、4 组方案对比、7 条决定、后果、已知限制、推翻条件），标「待签收」；未改其他 ADR |
| `docs/tasks.md` | **范围扩展**：D-03 行标注 ADR-013 待签收；新增 A05 认领行、决定摘要、后续项与 ADR 编号说明 |
| `docs/handoffs/claude-a05.md` | 本文件 |

**范围扩展说明**：清单给 A05 的文件锁只有 `specs/identity-access.md` 与 `docs/decisions.md`。任务板与交接是 AGENTS.md §5 的完成要求，与 A01/A02 同样处理。
**有意未碰**：
- `docs/architecture.md`：A04 正持有文件锁（`a04-f5f479` 认领行）。
- `src/contracts/`：真源尚未进入 main，契约改动按 §7 交给 B08/B09/B10。
- `.env.example`、`docs/integrations.md`：属 A07 的文件范围，A07 正在另一 worktree 进行。

除此之外未触碰 `src/`、`scripts/`、`AGENTS.md`、`.claude/`、`docs/atomic-tasks.json`，也未改任何其他 worktree。

## 二、裁定内容（签收人 ArvinHan，2026-09-23）

| 问题 | 决定 | 用户选择 |
| --- | --- | --- |
| 登录方式（D-03） | 本地账号：用户名 + 口令，慢哈希；HS256 JWT，8 小时，无刷新令牌；无注册端点，账号由命令行管理；演示账号由种子脚本创建，口令只从 `SEED_DEMO_PASSWORD` 读 | 「本地账号 + 预置演示账号」 |
| 角色粒度 | `users.role` 为账号类型，只管默认首页与能否建课；课程内授权只看 `course_members.role`，每次回查；令牌 `role` 仅作前端提示 | 「账号类型 + 课程内角色」 |
| 学生入课 | 教师按用户名添加学生；协作教师只由命令行管理 | 「教师按用户名添加」 |
| 教师可否用问答 | 否；进度、推荐、问答仅学生成员 | 用户在第二部分确认 |
| SSE 鉴权 | 一次性不透明票据存 SQLite，连接时原子核销并复查成员关系 | 用户在第三部分确认 |
| ADR 编号 | 取 013，012 预留给 A04 改号 | 「ADR-013，给 A04 留 012」 |

**本任务在已选方向内定稿的细节**（均写入规格，随 ADR-013 一并签收）：
- 判定顺序：身份 → 定位课程 → 成员 → 角色 → 发布状态 → 子资源作用域。
- 课程级非成员返回 403、任务级非成员返回 404（理由见规格 §4.1）；不存在的 `cid` 也返回 403。
- 登录失败统一返回 401；限流计数对不存在的用户名同样生效。
- 令牌只存 `sessionStorage`。
- 学生只在课程曾发布后才看到该课。
- 重复添加成员幂等返回，不改角色。
- 学生被移除后数据保留。

## 三、验收对照（A05 验收矩阵）

| 验收条款 | 落点 | 结果 |
| --- | --- | --- |
| 明确演示角色或账号模式 | 规格 §1；ADR-013 决定 1 与方案对比第 1 组 | 满足：本地账号 + 预置演示账号，否决纯演示角色 |
| 禁止仅相信请求 user_id | 规格 §2.2、§2.3；IAM-14（请求体与 `X-User-Id` 冒用）、IAM-15（篡改令牌）、IAM-25（契约无调用者 `user_id`） | 满足；已核实契约现有请求 schema 均无 `user_id`（脚本第 4 组） |
| 不扩展生产 SSO | 规格「范围」的「明确不做」清单；ADR-013 推翻条件 1 | 满足 |
| 身份、成员、角色访问矩阵 | 规格 §3、§4.3：契约 29 个操作 + 新增 4 个，逐行给出匿名 / 非成员 / 学生成员 / 教师成员的结果 | 满足；脚本逐操作核对方法、路径与 `operationId` |
| 人工决策保留未签收标记 | 交付时 ADR-013 首末行、规格状态行均为「待签收」，任务板 A05 为 IN PROGRESS、D-03 未关闭；ArvinHan 审阅后于 2026-09-23 签收，四处同步改为已签收 | 满足；签收前后脚本第 6 组各跑一次，均与当时状态一致（见第四节） |

**源文档对照**：

| 源 | 要点 | 本任务的对应 |
| --- | --- | --- |
| S2 表 2.1 | 教师、学生、助教三类角色 | 教师、学生落为两层角色；助教不设独立角色，用「教师账号做课程教师成员（命令行）」覆盖 |
| S2 表 6.2 | `users(id, username, password_hash, role)`、`courses_members(course_id, user_id, role)` | 原样保留，并补 `created_at`、`disabled_at`、`added_by` |
| S2 表 6.5 | `/api/auth/login` 登录并返回角色 | 保留；前缀按 ADR-009 为 `/api/v1` |
| S2 §7.1.1 | 登录后按角色进入教师端或学生端 | 账号类型决定默认首页；课程视图按 `my_role` |
| 契约 `740adb` `978671e` | 全局 `Role`、JWT 含 `sub` 与 `role`、学生看到全部已发布课程 | 前两者保留但令牌 `role` 降为提示；第三者改为按成员关系过滤（交 B09） |
| A03 `specs/task-processing.md`（`claude/a06-worker-lease`） | 「SSE 一次性令牌的签发端点与作用域 → B10 / A05」；TASK-19 | 规格 §5、IAM-18、IAM-22 |
| Codex S07-R07 | 最小修复：签发端点、带时效与任务作用域的响应模型、事件操作声明查询参数并覆盖全局 bearer；集成测试需覆盖「普通 Bearer query 被拒、任务限定票据可连接且不能读其他任务」 | 规格 §5.1、§5.2、§7 的 B08/B10 行；IAM-6、IAM-22 |

## 四、实际运行的命令与结果

```text
./scripts/verify.sh        改动前 exit 0；改动后 exit 0（Scaffold verification passed）
git diff --check           改动前 exit 0；改动后 exit 0（新文件先 git add -N 纳入检查）
python3 check_a05.py specs/identity-access.md docs/decisions.md <740adb 978671e 的 api.v1.yaml>
                           exit 0：150 PASS / 0 FAIL —— ALL PASS
【签收前】
负例（均应 exit 1 且逐条报出）：
  1 删去矩阵 cancelTask 行                       exit 1，2 FAIL（缺行、行数不符）
  2 把 getKnowledgePoint 路径改成 /kps/{kid}     exit 1，1 FAIL（方法与路径不一致）
  3 规格里写入不存在的错误码 MEMBER_PROTECTED    exit 1，1 FAIL（错误码不在 ErrorCode）
  4 把 ADR-013 末行改为「已签收」                exit 1，1 FAIL（未签收标记丢失）
  5 把已有操作 chat 误标为新增                   exit 1，4 FAIL
  6 对 ff30e0 6ccbe5e 旧契约（/api/ 前缀）核对     exit 1，31 FAIL，无崩溃

【签收后】ADR-013 首末行、规格状态行、任务板改为已签收；脚本第 6 组改查「三处签收一致」
python3 check_a05.py ...（同上）                exit 0：150 PASS / 0 FAIL —— ALL PASS
  1、2、3、5、6 重跑                              均 exit 1，FAIL 数与签收前相同（2 / 1 / 1 / 4 / 31）
  4′ 把 ADR-013 末行改回「待签收」               exit 1，1 FAIL（签收标记不一致）
  4″ ADR 已签收但规格状态行仍写「待签收」         exit 1，1 FAIL（规格状态行未同步）
./scripts/verify.sh        exit 0
git diff --check           exit 0
```

- 环境：`/opt/anaconda3/bin/python3` 3.13.5，PyYAML 6.0.2。
- YAML 通过 `git show 978671e:src/contracts/api.v1.yaml` 与 `git show 6ccbe5e:...` 导出到会话 scratch 目录，未改动任何 worktree。
- 核对脚本不入库（`tests/` 归测试 Agent，且 main 尚无 YAML），全文附在本文件附录，可复现。
- **过程更正**：脚本第一版有两个缺陷，都已修正后重跑，上面是修正后的结果。
  - 把环境变量名误当成错误码，正例报了 1 个假 FAIL。
  - 负例 6 以 `KeyError` 崩溃退出。虽然也是非 0，但不能证明逐条报错。

## 五、接口 / 数据 / 配置变更

无运行时变更，无契约文件改动。受本决定约束的未来变更：

1. **契约**（规格 §7）：
   - B08：`bearerAuth` 说明改写；所有 Bearer 操作补 `401`；新增 `eventTicket` 安全方案。
   - B09：`Course.my_role`；`listCourses` 描述；`login` 补 `429`；成员三操作与两个 schema。
   - B10：`issueEventTicket` 与 `EventTicket`；`streamTaskEvents` 覆盖全局安全方案；`events.v1.md` 的 `token` 改为 `ticket`。
   - 落实后，ADR-004 端点表由 22 路径 / 29 操作变为 24 路径 / 33 操作。
2. **数据**：
   - `users` 增加 `created_at`、`disabled_at`。
   - `course_members` 增加 `added_by`、`created_at`，主键 `(course_id, user_id)`。
   - 新表 `event_tickets`。
3. **配置**：`AUTH_JWT_SECRET`（必需，≥32 字节）、`AUTH_ACCESS_TOKEN_TTL_SECONDS`（默认 28800）、`SEED_DEMO_PASSWORD`（仅种子脚本需要）。

## 六、未完成 / 风险 / open_questions

- **原子清单缺口**：以下事项在清单中均无承接任务，需协调 Agent 拆分编号：
  - 登录端点与令牌签发；
  - 账号命令行与演示种子；
  - 成员管理 API；
  - 成员管理页面；
  - 票据申领端点。

  ADR-004 把 `/auth/login` 交给 C03，但 C03 的文件范围只有 `api/dependencies.py` 与 `services/access.py`，装不下登录、口令与令牌签发。
- **ADR 编号协调（已落实）**：A04 的草稿原写 ADR-010，与 A03 撞号；本任务按用户安排把 012 留给 A04，A04 已在 PR #7 改用 ADR-012（`origin/claude/a04-f5f479` 上核实）。ADR-010～013 在 PR #5～#7 与本 PR 之间不重叠。
- **合并提示**：本分支基于 main `931361d`，不含 ADR-010～012。与 PR #5～#7 合并时，`docs/decisions.md`（都在文末追加）与 `docs/tasks.md`（都在认领节末尾追加）会出现文本冲突，按编号顺序保留各方内容即可。
- **命名基线**：`event_tickets` 须补登到 `docs/architecture.md` 的 SQLite 表清单。该文件现由 A04 持锁，交 A10。
- **`events.v1.md` 措辞**：§1 写的是 `?token=`，本任务定为 `?ticket=`，由 B10 同批修改。
- **已知限制**（规格与 ADR 已写明）：令牌被盗到期前有效；登录限流按进程计数；SSE 开流后不复查成员关系。

## 七、unverified

- 访问矩阵、票据协议与 IAM-1～25 只有规格和用例，没有实现或自动化测试，这些属 C02、C03、C04、C11、I02 等任务。
- 核对脚本只验证规格与契约**结构**一致：操作覆盖、路径、错误码闭集、编号、签收标记。它不证明授权逻辑本身正确。
- 未对 A04（PR #7）做内容核对，只核实了它的 ADR 编号。版本绑定已交给 A04，本规格未涉及其内容。

## 八、下一位 Agent 的首个动作

1. **协调 Agent**：为上面的清单缺口拆分并编号原子任务。
2. **Codex**：审查本范围（base `931361d`，本轮 4 个文件）；修复另开一轮。

## 附录：核对脚本 `check_a05.py`（签收后版本）

签收前版本只在第 6 组不同：检查 ADR-013 首行含「待签收」、末行为「签收：待签收」、规格状态行含「决定待签收」。

```python
"""A05 验收核对：specs/identity-access.md 与 ADR-013 对照 740adb 契约真源。

用法：python3 check_a05.py <spec.md> <decisions.md> <api.v1.yaml>
全部通过 exit 0；任一失败逐条报出并 exit 1。
"""
import re
import sys

import yaml

spec_path, adr_path, yaml_path = sys.argv[1:4]
spec = open(spec_path, encoding="utf-8").read()
adr = open(adr_path, encoding="utf-8").read()
api = yaml.safe_load(open(yaml_path, encoding="utf-8"))
fails = []


def check(cond, msg):
    print(("PASS " if cond else "FAIL ") + msg)
    if not cond:
        fails.append(msg)


# 1. 访问矩阵逐操作覆盖契约
ops = {}
for path, item in api["paths"].items():
    for method, op in item.items():
        if method == "parameters":
            continue
        ops[op["operationId"]] = (method.upper(), path)

matrix = spec[spec.index("### 4.3 访问矩阵"):spec.index("### 4.4")]
rows = re.findall(r"^\| `(\w+)`( \*)? \| `(\w+) ([^`]+)` \|", matrix, re.M)
seen = {}
for op_id, star, method, path in rows:
    check(op_id not in seen, f"矩阵 operationId 不重复：{op_id}")
    seen[op_id] = (method, path, bool(star))
for op_id, (method, path) in ops.items():
    got = seen.get(op_id)
    check(got is not None, f"契约操作在矩阵中有行：{op_id}")
    if got:
        check(got[:2] == (method, path), f"方法与路径一致：{op_id} 契约 {method} {path}，矩阵 {got[0]} {got[1]}")
        check(not got[2], f"契约已有操作未被标为新增：{op_id}")
new_ops = {k for k, v in seen.items() if v[2]}
check(new_ops == {"listMembers", "addMember", "removeMember", "issueEventTicket"},
      f"新增操作恰为 4 个：{sorted(new_ops)}")
check(set(seen) - new_ops == set(ops), f"矩阵无契约外的未标记操作（契约 {len(ops)} 个，矩阵 {len(seen)} 行）")
for op_id in new_ops:
    check(op_id not in ops, f"新增操作在契约中尚不存在：{op_id}")

# 2. 引用的错误码均在 ErrorCode 闭集内
codes = set(api["components"]["schemas"]["ErrorCode"]["enum"])
used = set(re.findall(r"`([A-Z][A-Z_]{3,})`", spec + adr[adr.index("## ADR-013"):]))
used = {u for u in used if u != "PREREQUISITE" and not u.startswith(("AUTH_", "SEED_"))}
check(used <= codes, f"规格与 ADR-013 引用的错误码均在契约 ErrorCode 中：多出 {sorted(used - codes)}")
for c in ["UNAUTHENTICATED", "COURSE_FORBIDDEN", "ROLE_FORBIDDEN", "NOT_FOUND", "GRAPH_NOT_PUBLISHED", "RATE_LIMITED"]:
    check(c in used, f"规格使用了错误码 {c}")

# 3. 角色取值与契约 Role 一致
check(api["components"]["schemas"]["Role"]["enum"] == ["teacher", "student"], "契约 Role = [teacher, student]")
check("`users.role ∈ {teacher, student}`" in spec and "`course_members.role ∈ {teacher, student}`" in spec,
      "规格两层角色取值与契约 Role 一致")

# 4. 规格对契约现状的陈述属实
with401 = sorted(k for k, (m, p) in ops.items()
                 if "401" in api["paths"][p][m.lower()].get("responses", {}))
check(with401 == ["listCourses", "login"], f"「只有 login、listCourses 声明了 401」属实：{with401}")
lr = api["components"]["schemas"]["LoginRequest"]
check(lr["required"] == ["username", "password"], "LoginRequest 为 username + password")
check("role" in api["components"]["securitySchemes"]["bearerAuth"]["description"], "bearerAuth 说明含 role")
ev = api["paths"].get("/api/v1/tasks/{tid}/events", {}).get("get")
check(ev is not None and "security" not in ev and not any(p.get("in") == "query" for p in ev.get("parameters", [])),
      "事件操作现继承全局 bearer、无查询参数（S07-R07 现状）")
check([p for p in api["paths"] if p.startswith("/api/v1/auth")] == ["/api/v1/auth/login"], "契约无注册类端点")
req_refs = set()
for path, item in api["paths"].items():
    for method, op in item.items():
        if method == "parameters":
            continue
        for media in op.get("requestBody", {}).get("content", {}).values():
            ref = media.get("schema", {}).get("$ref")
            if ref:
                req_refs.add(ref.split("/")[-1])
schemas = api["components"]["schemas"]
bad = [n for n in req_refs if "user_id" in schemas[n].get("properties", {})]
check(not bad, f"请求 schema 均无 user_id 字段（IAM-25 现状）：{bad}")
check("学生只返回已发布课程" in api["paths"].get("/api/v1/courses", {}).get("get", {}).get("description", ""),
      "listCourses 现描述为「学生只返回已发布课程」（ADR-013 背景 2 属实）")

# 5. 验收编号连续、不重复
ids = [int(x) for x in re.findall(r"\*\*IAM-(\d+)\*\*", spec)]
check(ids == list(range(1, len(ids) + 1)), f"IAM 编号连续且不重复：共 {len(ids)} 条")
sections = spec[spec.index("## 8. 验收"):]
for part in ["成功路径", "边界路径", "失败路径"]:
    check(part in sections, f"验收含{part}")

# 6. ADR 编号唯一、签收标记一致
nums = re.findall(r"^## ADR-(\d+)", adr, re.M)
check(len(nums) == len(set(nums)), f"decisions.md ADR 编号不重复：{nums}")
check(nums.count("013") == 1 and "012" not in nums, "本分支新增 ADR-013 且未占用预留的 012")
a13 = adr[adr.index("## ADR-013"):]
# 签收后：首行、末行、规格状态行三处须一致为已签收（签收前本组检查的是「待签收」）
check("已签收（ACCEPTED）" in a13.split("\n")[2] and a13.rstrip().endswith("- **签收**：ArvinHan 2026-09-23"),
      "ADR-013 签收标记一致（首行状态与末行签收）")
check("已由 ArvinHan 于 2026-09-23 签收" in spec.split("\n")[2], "规格状态行与 ADR-013 签收一致")

print()
print("ALL PASS" if not fails else f"{len(fails)} FAIL")
sys.exit(1 if fails else 0)
```
