# Claude A01 与 S-07 本地脚本审查（2026-09-23 01:36 UTC）

## 范围与结论

- A01 文档交付：`adoring-sinoussi-709263`，固定交付提交 `88ea517`，交接修订后的稳定 HEAD `6c19f258729c4e9b2390d2e79bf2869e3aade87f`。会话末尾为 `2026-09-22T14:50:30.401Z` 的 `stop_hook_summary`，其后无新 user/tool 活动；HEAD、dirty diff、交接指纹两次观察一致。审阅 `docs/decisions.md`、`docs/architecture.md`、`docs/tasks.md`、两个交接文件。本批未发现 A01 文档范围的新缺陷；22 条路径 / 29 个操作与 S-07 的 YAML 逐项吻合。ADR-004 仍为未签收提议，不等于已获批准。
- S-07 续审批次：`worktree-contract-conflicts-740adb`，目标 HEAD `8865686f202f367db7d67e4e16bec19f5841939a`，两次观察 HEAD、dirty diff、交接指纹稳定。本批审阅 Compose、本地开发脚本、危险命令 hook、verify 分发与四个子脚本。发现以下三项新问题；此前 R01–R11 仍按原报告跟踪，**没有重复立项**。合并冲突余项和部分生成物/文档一致性尚待审，不宣称整分支通过。

## 新问题

### S07-R12 P2：hook 对常见包装命令漏检

- **目标提交与位置**：`8865686`，`.claude/hooks/block-dangerous.sh:70-84`，尤其 `:73` 的 `CMD_POS` 与 `:83` 的匹配。
- **触发条件**：PreToolUse 输入 `bash -c "rm -rf build"` 或 `env rm -rf build`。两者可执行相同的 `rm -rf`，但该 hook 没有输出 block JSON；直接 `rm -rf build` 与 `echo ok && rm -rf build` 则正确拦截。只把字符串作为 JSON 输入 hook，**未执行这些命令**。
- **影响**：注释 `:94-96` 声称保住 `bash -c` 覆盖，与实测相反；协作工作区护栏可在常见命令包装形式下失效。它虽声明不是安全边界，但与“拦截破坏性命令”的实际用途不符。
- **最小修复**：对 `bash/sh -c` 与 `env`/`sudo` 等包装命令解析其后待执行部分再复用现有模式；或收窄承诺、在上游增加范围校验。增加上述输入及普通文本/引号误报的回归用例。

### S07-R13 P2：`unhealthy` 被启动脚本当作健康

- **目标提交与位置**：`8865686`，`scripts/dev-up.sh:17-22`，尤其 `:20` 的 `*healthy*`。
- **触发条件**：Compose 的 Health 字段为 `unhealthy`。纯字符串分支实测：`healthy => accepted`、`unhealthy => accepted`、`starting => waiting`。
- **影响**：脚本提前结束最多 180 秒的等待并运行 APOC 检查；暂时不健康、仍可能恢复的容器被过早判定，启动流程可能失败，诊断也误称健康就绪。未启动容器，实际 Compose 输出格式尚未集成验证。
- **最小修复**：解析 JSON 的 `Health` 精确值，只有等于 `healthy` 才退出轮询；为 `unhealthy`、`starting`、缺字段各加纯函数/模拟输出测试。

### S07-R14 P2：前后端初始化后占位门禁仍返回成功

- **目标提交与位置**：`8865686`，`scripts/verify/backend.sh:6-17`、`scripts/verify/frontend.sh:6-17`；汇总在 `scripts/verify.sh:17-27`。
- **触发条件**：新增 `src/backend/pyproject.toml` 或 `src/frontend/package.json` 后，相应测试命令仍是注释。隔离临时目录中各放一个最小标记文件，分别运行子脚本，二者打印“门禁仍是占位实现”却均 `exit 0`。
- **影响**：M0-02/M0-03 一旦初始化，`verify.sh` 会把未运行的 type-check/pytest 等计为成功并输出 `All verification checks passed.`；构建或测试失败可被漏掉。当前 S-07 分支尚无两个标记文件，所以这是后续触发缺陷，不是声称本轮已跑过这些测试。
- **最小修复**：初始化标记存在但真实命令未启用时返回非零；与对应骨架任务同批替换占位命令，并加一个临时 fixture 断言“有标记但无测试命令”不得成功。

## 验证与剩余边界

```text
A01: ./scripts/verify.sh                         exit 0，Scaffold verification passed
A01: git diff --check 05d214c..6c19f25         exit 0
A01: YAML 路径/方法与 ADR-004 迁移表集合比较       22 路径、29 操作，missing=[]，extra=[]
S-07: bash -n 本批所有 shell 脚本                 exit 0
S-07: hook JSON 输入四个分支                      直接/&& 拦截；bash -c/env 漏检
S-07: health 值纯字符串分支                      unhealthy 被 accepted
S-07: 临时目录前后端占位门禁                     两者 exit 0
S-07: git diff --check 05d214c..8865686        exit 0
```

系统默认 `python3` 缺 PyYAML，映射比较首次未运行；改用本机已有 `/opt/anaconda3/bin/python3` 后完成比较，未安装依赖。没有执行 `dev-up`、`dev-down`、容器命令或付费模型调用，没有改动 Claude worktree。

待审：S-07 双亲合并冲突消解的剩余范围、生成物目录和未覆盖的 ADR/规格一致性；A01 的人工 PLAN-D01 签收与 PLAN-D04 集成基线仍待负责人决定。S07-R06 的生成物缺失假绿已在前一报告指出；M0-09 交接中“该分支 verify 现为 exit 1”的叙述不能替代修复后的重新验证。
