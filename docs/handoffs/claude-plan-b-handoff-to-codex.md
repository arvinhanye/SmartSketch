# 计划 B（L11–L15）进度与移交 Codex

```text
from: Claude
to: Codex
date: 2026-10-03
worktree: /Users/arvinhan/SmartSketch/.claude/worktrees/smartsketch-plan-a-fixes-e70a34
branch: claude/smartsketch-plan-a-fixes-e70a34
base: d766f40（计划 A 审查修复版本）
head: 交接提交（代码 HEAD 56610d4）
uncommitted: 无
sprint branch: claude/smartsketch-contest-sprint-77644f 停在 5a34fec（L11-7）；L12～L14 共 16 个提交尚未快进过去
plan: docs/superpowers/plans/2026-10-03-contest-sprint-b-functional-loop.md
budget: 619217 / 5000000 token（本会话未调用真实模型，未增加）
```

## 0. 交给 Codex 的三件事（用户 2026-10-03 指定）

1. **复审 L12～L14 的 16 个提交**：范围 `5a34fec..56610d4`（`5a34fec` 是 L11-7，冲刺分支当前停在这里）。

   ```bash
   git log --oneline 5a34fec..56610d4
   git diff 5a34fec 56610d4
   ```

   - 逐任务的设计取舍与验证见 `claude-l12.md`、`claude-l13.md`、`claude-l14.md`，复审重点见本文 §3。
   - 复审意见写入 `docs/handoffs/codex-<task>.md` 或 `docs/reviews/`。
   - **先修 §2 的门禁失败**：演示端到端 `student.spec.ts`，是 L14-3 推荐序号放进按钮引起的回归，根因与建议修法见 §2。修完后完整重跑门禁。
   - 复审通过且 DeepSeek 的 L11-7 复测合并后，再快进冲刺分支。

2. **需要向量模型或真实模型的测试仍交 DeepSeek harness**：凡是要调用阿里云百炼向量（发布期向量化、问答检索的真实向量）或真实生成模型的验证，Codex 都**不在本地运行**，而是写交接稿交给 DeepSeek harness。
   - 交接稿写清：命令、预算停止线、需要记录的指标。
   - 写法参照 `claude-l11-6-deepseek-handoff.md`、`claude-l11-7-deepseek-retest.md`。
   - 本地只用演示模型、本机假供应商（`scripts/fake_provider.py`）和一次性 Neo4j。
   - 目前在途或待交的有三项：
     - L11-7 PDF 续行修复的真实模型复测（已交，结果未到）；
     - L15-6 Step 4 两门课问答抽样；
     - 下面第 3 项调高上限后的实测。

3. **调高问答输出上限（用户已决定调高）**：`ANSWER_MAX_OUTPUT_TOKENS`（`src/backend/app/services/qa/generate.py:116`）当前为 1024。这一项关闭 ADR-068 待决 1，并取代计划 A 交接里「上限不变、待人工决定」的状态。
   - 已有数据（L02 真实模型，`evaluation/reports/l02-baseline-2026-10.md` §4.4、`deepseek-plan-a-verification.md`）：
     - 比较类问题「栈和队列有什么区别？」的输出正好撞上 1024 被截断，可确定性复现；
     - 同批未截断回答输出 246～858 token；
     - 五题完整耗时最大 6.12 秒（含截断那题），赛题时限 15 秒。
   - 建议做法（Claude 起草、未实施，由 Codex 定稿）：
     - 先在 `docs/decisions.md` 新增 ADR-086（背景、决定、后果、回滚），并同步 `specs/grounded-qa.md`「生成输出上限」一行，以及 ADR-068 决定 5、ADR-082 决定 2 中「1024 不变」的表述。
     - 再按 TDD 改常量：先写断言新值的失败测试，再改 `generate.py`。
     - 建议值 2048：按上面的耗时推算，仍在 15 秒内；ADR-082 决定 3 的统一截止时刻兜底超时；截断仍按 ADR-082 决定 2 判为 `LLM_UNAVAILABLE`/`truncated`，不放松出处校验、不加重试。
     - 后果：单题输出费用上限约翻倍，长回答的完整耗时上升。
   - 相关测试：`tests/backend/test_j05.py:261` 用常量比较，会自动跟随；`tests/backend/test_demo_mode.py:386` 与 `scripts/fake_provider.py:56` 里有字面量 1024，需逐一核对是否应跟随。
   - 改完后的真实模型实测（15 秒内是否稳定完成、比较类问题是否不再截断、费用）按第 2 项交 DeepSeek harness，不在本地跑。

## 1. 进度总览

| 任务 | 状态 | 交接 | 说明 |
| --- | --- | --- | --- |
| L11 | 功能完成；L11-7 真实模型复测**待 DeepSeek** | `claude-l11.md`、`claude-l11-6-deepseek-handoff.md`、`deepseek-l11-6.md`、`claude-l11-7-deepseek-retest.md` | 两门课资料、假供应商、个人模式端到端、发布阻断原因、PDF 续行修复（ADR-084）。L11-7 复测结果未到，到后先合并再快进冲刺分支 |
| L12 | DONE（待复审） | `claude-l12.md` | `document_name`（ADR-085）、`SourceViewer`、四入口 |
| L13 | DONE（待复审） | `claude-l13.md` | 可读视口、搜索定位、高级筛选折叠、问答 → 图谱选中 |
| L14 | DONE（待复审） | `claude-l14.md` | 学习路径纯函数、画布高亮与序号、推荐解释「未标注」、视口修复 |
| L15 | **未开始实现，移交 Codex** | 本文 §4 | 已有设计决定与前端测试草稿 |

## 2. 门禁与验证状态

- **L11 阶段门禁**（`fc2ad94`）：后端 1 failed（`test_shell_multibyte_vars`，`4ee7b52` 已修，单测通过），其余全部通过；同一次运行未整体 exit 0。
- **L13 门禁**：开跑后为避免 L14 改动混入而中止，**未完成**。
- **L13+L14 合并门禁（代码 HEAD `56610d4`，`verify.sh integration`，独立端口）：整体 exit 1，有 1 项端到端失败，交 Codex 修复。**

  | 阶段 | 结果 |
  | --- | --- |
  | 契约 / 基础档 | PASS |
  | 后端 full | PASS：3772 passed / 27 skipped（已登记） |
  | 前端（integration） | PASS：34 文件 874 passed |
  | 集成用例 | PASS：393 passed / 4 skipped（已登记） |
  | 图库后端（backend-live） | PASS：44 passed |
  | 演示端到端 | **FAIL**：`student.spec.ts` 1 failed、`teacher.spec.ts` 1 passed（证据 `.e2e/20261003-124107`） |
  | 个人模式端到端 | PASS：3 passed（`.e2e/20261003-124333`） |

  门禁日志在 Claude 会话 scratchpad，不入库；端到端证据在工作区 `.e2e/`（不提交）。

- **待修失败（L14-3 引入的回归，交 Codex）**：`tests/e2e/student.spec.ts:60`

  ```text
  Locator: [data-test=sg-mastery-target]
  Expected substring: "1."
  Received string:    " 知识点：栈 · 当前：未开始"
  ```

  - 根因：L14-3（`5d171e4`）把序号 `<span data-test="rc-order">1.</span>` 放进了推荐按钮 `rc-select-*` 内部。演示用例读取按钮文字后取第一个空白前的词当知识点名称，结果取到「1.」。
  - 建议修法：把序号移到按钮外（`<span data-test="rc-order" aria-hidden="true">` 放在按钮前面，`<ol>` 已提供列表语义）。这样按钮文字和可访问名都只剩知识点名称；同时在 `tests/frontend/l14.test.ts`「列表：顶部路径行、每项序号、「排序参考」」里加断言 `rc-select-C` 的文字等于「知识点C」，先确认红。
  - Claude 已在本地验证这个修法：新增断言先红，改后 `l14` 与 `i06` 共 60 passed、type-check 通过。按用户要求已撤回，未提交，端到端未重跑。
  - 另一种修法是改端到端：按 `data-kp-id` 找目标，或直接读 `rc-select` 的名称；但上面的修法也改善了读屏体验，更推荐。
  - 修完重跑：

    ```bash
    E2E_API_PORT=18100 E2E_WEB_PORT=15273 E2E_NEO4J_PORT=17788 E2E_PROVIDER_PORT=18990 PYTHON=.venv/bin/python PATH="$PWD/.venv/bin:$PATH" PLAYWRIGHT_CHROMIUM_EXECUTABLE="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" scripts/e2e.sh tests/e2e/student.spec.ts tests/e2e/teacher.spec.ts
    ```

    然后跑 `personal.spec.ts`（`E2E_LLM_MODE=personal`）。`personal.spec.ts` 用的是 `items.first().locator('[data-test=rc-order]')`，序号移到按钮外仍在同一个 `li` 内，预计不受影响。

- **门禁可信度说明**：这次门禁运行期间，Claude 在工作区短暂改过 `src/backend/app/services/qa/generate.py`（上限临时改为 2048），随后已撤回，没有提交。
  - 后端 full 的用例数 3772 = 3761 + `test_l12` 8 + `test_l14_reason` 3，说明当时新建的临时测试文件没有被收集；
  - 但集成用例阶段是否读到了临时值无法排除。问答集成用例不依赖具体上限值，影响很小。
  - 稳妥起见，修完上面的失败后请**完整重跑一次 `verify.sh integration`** 作为最终门禁：

```bash
E2E_API_PORT=18100 E2E_WEB_PORT=15273 E2E_NEO4J_PORT=17788 E2E_PROVIDER_PORT=18990 VERIFY_NEO4J_PORT=17789 \
PYTHON=.venv/bin/python PATH="$PWD/.venv/bin:$PATH" \
PLAYWRIGHT_CHROMIUM_EXECUTABLE="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" \
./scripts/verify.sh integration
```

- 逐任务已验证（均为本工作区实测；全量结果以上表为准）：
  - 前端：`l12` 11、`l13` 10、`l13-kp-link` 8、`l14` 21 passed，`h04/h05/h11/i06` 回归通过，type-check exit 0。最近一次前端全量是 L12 后的 835 passed，L13/L14 之后**未跑全量**。
  - 后端：`test_l12` 8、`test_l14_reason` 3、`test_i04`+`test_i05` 154 passed。最近一次后端全量是 L11-7 后的 3761 passed / 27 skipped。
  - 个人模式端到端 3 passed（`.e2e/20261003-120719`）。视口修复（`09349d3`）之后只以加截图的运行复核过 exit 0，未单独留存纯净运行。
- 端口说明：另一会话占用默认端口，本工作区一律用上面的独立端口。

## 3. 本轮发现、已修的问题（复审重点）

1. **G6 5.1.1 每次 `render()` 都按 `autoFit` 整图适配**：掌握状态、选中、路径高亮引起的更新会把视口拉回整图，L13 的聚焦也受影响。修法是首次渲染后 `setOptions({ autoFit: undefined })`，尺寸变化与切换布局仍显式 `fitView`（`src/frontend/src/graph/lifecycle.ts`）。副作用：新版本重载图谱时不自动整图适配。
2. 画布尺寸变化后重新聚焦回入口节点：现在记住最近一次请求聚焦的知识点。
3. 服务端推荐理由句把缺失属性的中性值 0.5 写成测量值：`ranking._reason` 在属性缺失时写「未标注，按中性值 0.5 计」（`specs/learning-path.md` §4.1）。
4. 测试期望随行为更新：`h05`/`i06` 的画布样式键清单；`i06` 页面状态断言滤掉路径状态；`i06` 中 0.5 难度展示；D06 三例（L11-7）。请确认这些更新是行为变化而不是掩盖缺陷。

## 4. L15 交接（未实现）

计划原文见 plan 文件「L15」节。以下是 Claude 已做的设计决定，Codex 可以采纳或改动，改动请在你的交接里说明。

### L15-1 侧栏按课程内角色

- 路由守卫已允许教师账号进入学生路由（`/graph`、`/chat`、`/materials` 都是 `anyAccountRole`），只需改侧栏。
- 计划：`stores/course.ts` 加 `myRole` 与 `setRole(scope, role)`（经 `commit` 防旧响应），`selectCourse` 时重置。
- `App.vue` 按 `courseId` 用 `beginRequest()` 作用域调用 `COURSES_API_KEY.get(cid)` 写 `myRole`。`courseNav` 按 `myRole` 给入口，未知时只显示「课程概览」。
- **会话变化时必须清空角色**（同一课程换号时 `selectCourse` 同 ID 不会重置，否则会残留上一个账号的角色）。建议在 `accessToken` 变化时 `selectCourse(null)` 再重新读取。
- 未注入 `COURSES_API_KEY` 的外壳测试（b02、n03-n05 等）要能退化。

### L15-2 课程概览：阶段与下一步

- `Course.kp_count` 是**已发布**知识点数，不能判断草稿是否为空。草稿函数因此改为按 `status`、`published_version` 与可选的资料数 `materialCount`（来自 `MATERIALS_API_KEY.list`，未注入时为 null）判断。
- 签名草案：`courseNextStep({ myRole, status, publishedVersion, materialCount }, needsConfig)`。
- 阶段 `needs_config | no_material | drafting | waiting_publish | published | waiting_teacher`；动作比计划多一个 `review`，因为发布在审核页。
- 教师的分支：

  | 条件 | 阶段 | 动作 |
  | --- | --- | --- |
  | 未发布且未配置 | `needs_config` | `settings` |
  | 未发布、资料 0 | `no_material` | `materials` |
  | 未发布、有资料 | `drafting` | `review` |
  | 未发布、资料数未知 | `drafting` | `materials` |
  | `revising` | `waiting_publish` | `review`（文案带「第 N 版」） |
  | 已发布 | `published` | `teacherGraph`（文案带「第 N 版」） |

- 学生的分支：

  | 条件 | 阶段 | 动作 |
  | --- | --- | --- |
  | 未发布 | `waiting_teacher` | 无 |
  | 已发布、未配置 | `published` | `studentGraph`（文案提示提问前需配置） |
  | 已发布、已配置 | `published` | `studentGraph` |

- 计划要求「链接组不重复侧栏入口」。但 `h02/h09/h11/h12/h14` 与 `tests/e2e/teacher.spec.ts` 依赖现有的 `student-graph-link` 等链接，建议保留为次要列表，并在交接里说明。

### L15-3 入课空态

学生空态改为：「你还没有加入任何课程。请把你的用户名「{username}」告诉任课教师，由教师在课程的「成员」中添加你。」教师空态保持「可在下方创建第一门课程」（`h01.test.ts:169` 断言含「暂无课程」，需同步）。

### L15-4 跨课隔离（后端）

- 建议的夹具：复用 `tests/backend/test_f07.py` 的 `s`（含 `teacher`/`student`/`outsider`、`FakeReader`、`publish()`）以及 `test_l12.py` 的 `_material`。
- 计划覆盖的四类：
  - 他课学生读 `/kp/{kid}` 得 403，响应不含本课文件名；
  - 进度 `/progress` 与推荐 `/recommend` 他课 403；
  - 把 `outsider`（教师账号）加为本课学生后，`/graph` 只拿到发布版（`reader.calls` 的读者为 `student`），未发布时为 404，不泄露草稿；
  - 问答引用只含本课文件名：`test_l12.py::test_chat_citations_carry_the_same_course_document_name` 已覆盖。
- 若直接全绿，按计划记为「回归固化」。

### L15-5 恶意文本

- 已核对：前端所有组件都不使用 `v-html`，`ChatMarkdown` 只在 `final` 且引用存在时把 `[n]` 渲染为按钮。预计前端用例直接通过，属回归固化。
- 后端：`document_name` 超过 255 字符应被契约拒绝。可用 `test_f07.assert_schema`/`valid_schema` 校验 `SourceRef`、`Citation`。生成的 Pydantic 模型在 `src/contracts/v1/generated/python/models.py`，**不要手改生成物**。

### L15-6 两课程总验收

- `personal.spec.ts` 新增「两门课互不串课」。第二门课资料是 `datasets/contest/course2-os-ch2/`。
- 第二个学生用 `tests/e2e/api.ts` 的 `registerStudent`（L14-4 已加）。
- Step 3：列出计划 A 的 D/N 回归逐项结果。
- Step 4：真实模型问答抽样需要预算确认，并交 DeepSeek harness（见 §0 第 2 项）。

### 测试草稿

`docs/handoffs/claude-l15-draft-tests.txt`：L15-1/2/3/5 的前端用例草稿，**未运行**。它依赖尚不存在的 `myRole`、`courseNextStep` 和 `course-stage`/`course-next-action`。核对后改名为 `tests/frontend/l15.test.ts`，先确认红再实现。用 `.txt` 扩展名是为了不被 vitest 收集。

## 5. 未决事项

- **DeepSeek L11-7 复测**：等待提交。
  - 到达后：合并到本分支，再快进冲刺分支。
  - 复测可能仍在运行时，不要快进冲刺分支。
- **问答输出上限**：用户已决定调高，交 Codex 实施（见 §0 第 3 项），实测交 DeepSeek。
- **观察到但未修**：
  - 同章 PDF 与 Markdown 同时上传会产生大量同名知识点，推荐列表出现同名项（R05，跨任务融合不在本期）。
  - 抽取耗时四份都未达 60 秒（L16）。
  - 学习路径的解锁节点可能离焦点很远，视口只保证焦点可见。
- **评审建议（可选）**：运行时 store 用用户 ID 加登录时间识别会话，而不是令牌。

## 6. 接手须知

- 按 `AGENTS.md`：
  - 先在 `docs/tasks.md` 认领 L15；
  - 你的交接写 `docs/handoffs/codex-<task>.md`，不要改 Claude 的交接文件；
  - 不在 main 上提交、不推送、不合并。
- 命令：
  - 后端：`PYTHONPATH=$PWD/src/backend .venv/bin/python -m pytest <file> -q -p no:cacheprovider`
  - 前端：`cd src/frontend && npx vitest run ../../tests/frontend/<file>`、`npm run type-check`
  - 个人模式端到端：§2 的端口变量加上 `E2E_LLM_MODE=personal scripts/e2e.sh tests/e2e/personal.spec.ts`
  - 契约生成：`PATH="$PWD/.venv/bin:$PATH" ./scripts/gen-contracts.sh`
- 工作区约束：
  - 不得向其他工作树写文件；同步冲刺分支用 `git -C <sprint worktree> merge --ff-only`。
  - 钩子拦截含 `rm -rf` 的命令文本。
  - 中文前的 shell 变量要加花括号（`test_shell_multibyte_vars` 会检查）。
