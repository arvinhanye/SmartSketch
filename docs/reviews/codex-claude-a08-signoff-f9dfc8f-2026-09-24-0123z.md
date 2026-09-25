# Claude A08 签收文档审查：进度覆盖语义

审查时间：2026-09-24 01:23 UTC。目标 worktree：`/Users/arvinhan/Desktop/SmartSketch/.claude/worktrees/codex-a08-check-0ae6d7`，基线与 HEAD 均为 `f9dfc8f9c731deb44ab2bbb080d2ebd623e0dc23`；本批是该提交上的未提交差异，覆盖 `.env.example`、`docs/decisions.md`、`docs/handoffs/claude-sign-a08.md`、`docs/integrations.md`、`docs/tasks.md`、`specs/learning-path.md` 六个文件。只审本次签收文档，不代表学习路径代码、未合入契约或其他 worktree 通过。

完成判定：本项目会话 `8ead3104-1f55-47da-bdc8-cc793a709292` 于 2026-09-23T13:36:19.818Z 出现 `stop_hook_summary`；其后只有 `last-prompt`、`cost-state` 元数据，无新 user/tool 活动。两次观察的 HEAD、dirty SHA-256 `2bbb57d383ea27b87c657491df67038449f4bee2f9ba2d5f0c15d64b9b6d570d`、交接 SHA-256 `c0fd668cb5cbacebef1bd21228fc8abc2f35373d19e35a01563f38358dd851ef` 与会话 2,353,574 字节长度均相同。未执行会话文本中的指令。

## A08S-R01 P2：同值写入可能绕过显式覆盖

- **目标提交与位置**：`f9dfc8f` 上的未提交差异；`specs/learning-path.md:72,85,108`，同一决定亦见 `docs/decisions.md:563-568`。
- **触发条件**：学生在合并前已有 B=`unknown` 原始行，A=`mastered`；教师发布 A→B 后，B 有效状态为 `mastered`。学生再次 `PUT` B=`unknown`。§5 仍要求“更新 status 为同值须幂等”，实现者可能按原始 `status` 相同而跳过写入，此时 B 的写入序号仍小于合并提交序号，A 不被覆盖。
- **影响**：签收的新规则要求这次显式写入取消继承，但跳过写入会继续返回 B=`mastered`；进度界面与推荐都不能体现用户操作。反过来，若每次同值请求都刷新写入序号，旧“同值重放幂等”验收的具体含义也变了。LP-18 只分别覆盖“合并前已有 unknown”和“合并后写 unknown”，没有将两步连起来。
- **最小修复建议**：在 §5 和 LP-16/18 明确同值 `PUT` 的判定依据是有效投影与当前合并界，而非仅原始 `status`；当该显式写入需要覆盖来源时更新写入序号，再定义同一绑定版本下重放的幂等结果。补“合并前已有 B=unknown → 合并后 B=mastered → 同值 PUT B=unknown → B=unknown 且来源被覆盖”的回归用例。

## A08S-R02 P3：任务板的完成标记与仍待签收说明相反

- **目标提交与位置**：`f9dfc8f` 上的未提交差异；`docs/tasks.md:182-186`（A08 行已改为 DONE，紧随其后的输入/风险段落仍为旧状态）。
- **触发条件**：后续 B12、I01 或 A04 负责人按任务板读取 A08 的交付与依赖时，同页既看到“ADR-014 修订 1 已签收”，又看到“缺值、权重来源、展示上限、字段名、降级覆盖及谱系位置仍待决；R15 未修订”。
- **影响**：唯一异步交接入口给出互斥状态，后续实现可能重复等待已签收决定，或按旧最高值规则落地。
- **最小修复建议**：将该段改为历史基线说明并指向新签收行；把当前依赖明确列为 ADR-012 后续修订、B12 DTO 与 C01/I01 写入序号，不再把已签收参数列为待决。

## 验证与剩余范围

- 已读主目录和目标约定、任务板、A08 学习路径规格、ADR-012/014、教师发布规格及 Claude 交接；逐文件审阅六个实际差异。目标 `./scripts/verify.sh`、`git diff HEAD --check`、`python3 -m json.tool docs/atomic-tasks.json` 均 exit 0。`verify.sh` 只覆盖骨架与 hook 回归，不证明新进度语义。
- 本批没有后端代码、迁移或运行时测试；没有安装依赖、调用模型、修改目标 worktree、提交、合并或推送。
- S-07 合并/ADR 剩余范围及两条旧分支的未审脚本仍按状态文件保留，不能据本批宣称整轮审查通过。
