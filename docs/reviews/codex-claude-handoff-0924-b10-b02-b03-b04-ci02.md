# HANDOFF-0924 固定范围审查：B10、B02、B03/B04、CI-02

- 审查者：Codex；日期：2026-09-24。
- 固定范围：B10 `f00a3e8..bb48429`；B02 `9d2437e..3fedd4e`；B03/B04 `3fedd4e..06f33aa`；CI-02 `06f33aa..025cbee`。均为已并入 main 的 first-parent 范围。
- 依据：`docs/handoffs/claude-handoff-codex-2026-09-24.md` §3、相应 Claude 交接、`specs/task-processing.md`、`specs/identity-access.md`、`docs/claude-review-workflow.md`。只审这些固定范围，不把结论扩展到旧的 S-07 待审路径或未来消费者。

## 结论与范围

| 范围 | 结论 | 证据与仍未验证部分 |
| --- | --- | --- |
| B10 | 未发现新增 P1/P2；Claude 的 R01～R04 在 JSON Schema 与已入库的生成物层均有覆盖。`FixedStageProgress` 的 `if/then` 被 Pydantic/TS 生成器忽略属已明示边界，C08 必须保证运行时进度，不把生成模型当成唯一检查。 | `test_b10.py` 45 passed；`verify.sh`（24 项门禁负例、B08 5、B09 5、B10 45）exit 0；`gen-contracts.sh --check` exit 0。C10/C11 运行时尚未实现，无法验证其消费方式。 |
| B02 | macOS 上外层测试、嵌套 `npm test` 失败/零用例探针均通过；未发现新增 P1/P2。 | 全量前端 30 passed（含 B02 5）、type-check 与 build exit 0；Windows 原生环境未提供，`npm.cmd` 分支未实跑，因此**Windows 验证缺口保留**，不写成跨平台通过。 |
| B03/B04 | 未发现新增 P1/P2。路由守卫只做界面引导，真实授权仍以后端为准；B03-R01 的 `inject(routeLocationKey, null)` 是兼容 B02 无路由挂载的已知 P3；B04 槽位可直接赋值的已知 P3 保留给消费方。 | 同一全量前端运行中 B03 13、B04 12 passed；`vue-tsc` 与生产构建 exit 0。真实登录、课程路由接线与网络取消尚属 H13/H01/B15。 |
| CI-02 | 未发现静默跳过或吞失败退出码；三 job 无 `continue-on-error` / `|| true`，各命令串行直出。 | YAML 解析得 scaffold/frontend/backend；`bash -n` 通过；前端零用例探针 exit 1，后端缺文件探针 exit 4；前端 30 passed + build，后端以 `PYTHONPATH=src/backend` 运行 58 passed。此后端运行不是 CI 的 `pip install -e` 完整复刻（为避免生成未忽略的 egg-info）；GitHub 托管 Python 3.12/Node 24 结果按 CI 记录核对，不以本机 3.11/26 冒充。 |

## B10 关键核对

- `Task` 为 `TaskActive` / `TaskCompleted` / `TaskFailed` / `TaskCancelled` 的 `oneOf`，`stage` 判别；`TaskFailed.error` 必填，非失败分支只可为 null 或缺省。生成 Pydantic `Task` 的正负例由 B10 回归直接导入验证；TS 联合类型保留分支收窄。
- `queued=0`、`awaiting_review=0.95` 在 JSON Schema 的 `FixedStageProgress` 有约束；生成的 `FixedStageProgress` 是空类/TS `unknown`，需由 C08 与后续序列化路径执行。`completed=1`、`cancelled ⇒ cancel_requested=true` 在生成类型中保留。
- 409 `TaskNotCancellableError.details` 将 `persisting_uninterruptible`、`processing_finished`、`already_terminal` 与实际 `stage` 关联；任务流的票据申领、Bearer 覆盖、404 隐藏非成员、处理结束关流与重连描述与 ADR-010/013 对应。R05～R08 为 Claude 已记录的非阻塞 P3，未在本轮重复立项。

## 执行记录与限制

- 运行：`PATH=/private/tmp/smartsketch-c08-venv/bin:$PATH python -m pytest tests/contracts/test_b10.py -q` → 45 passed；`PATH=... ./scripts/verify.sh` → exit 0；`PATH=... ./scripts/gen-contracts.sh --check` → exit 0。
- 运行：`npm --prefix src/frontend run type-check`、`npm --prefix src/frontend run test -- --run`、`npm --prefix src/frontend run build` → exit 0，30 passed；`PYTHONPATH=src/backend ... python -m pytest tests/backend -q` → 58 passed。
- 五个固定范围的 `git diff <base>..<head> --check` 均 exit 0。第一次用 zsh 变量拆分提交对失败，改用明确提交对重跑后通过；失败的循环未被当作审查结果。
- 本轮未运行 Windows。初次 Vitest 运行因隔离 worktree 临时缓存写权限 `EPERM`，在获准写入后重跑成功；初次后端运行缺 `app` 导入路径，补 `PYTHONPATH` 后成功。两项环境失败均未算测试通过。
- 未修改 Claude 原文件。后续若需关闭 Windows 缺口，应在 Windows runner/机器复跑 B02 嵌套命令；本报告不授权合并任何新 PR。
