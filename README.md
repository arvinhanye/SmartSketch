# SmartSketch / 智绘学途

面向高校课程的 AIGC 知识图谱智能构建与学习导航系统。教师上传课程资料后审核并发布图谱；学生通过 2D 图谱、掌握进度、可解释路径和带出处问答完成学习导航。

> 当前阶段：**项目协作与应用骨架已建立，业务实现尚未开始。**

## 技术方向

- Web：Vue 3、TypeScript、Vite、AntV G6
- API：Python、FastAPI、SSE
- 数据：Neo4j（图谱/向量）、SQLite（业务/任务）
- AI：OpenAI 兼容的大模型接口；供应商与模型通过环境变量配置

## 目录

```text
.
├── AGENTS.md                 # Codex / Claude 共同工作契约
├── CLAUDE.md                 # Claude 补充规则
├── .claude/                  # Claude 团队规则与 hooks
├── .codex/                   # Codex Desktop 管理的本地配置目录
├── .mcp.json                 # 无密钥的团队 MCP 清单
├── docs/                     # 产品、架构、ADR、任务、交接
├── specs/                    # 功能规格与验收标准
├── scripts/verify.sh         # 唯一基础质量验证入口
└── src/
    ├── frontend/             # Vue 应用
    ├── backend/app/          # FastAPI 分层应用
    └── contracts/            # 前后端共享 API / 事件契约
```

`.codex/` 由 Codex Desktop 管理，本仓库不手动生成或提交其本地状态。

## 协作方式

1. 先阅读 [AGENTS.md](AGENTS.md) 与 [任务看板](docs/tasks.md)。
2. 在任务看板认领任务，并以 `specs/` 的验收条件为准实现。
3. 修改共享接口、数据模型或范围时，同步更新架构文档或 ADR。
4. 完成后运行：`./scripts/verify.sh`。
5. 写入 `docs/handoffs/<agent>-<task>.md`，再交由下一个 Agent 接续。

GitHub Actions 的 [CI 工作流](.github/workflows/ci.yml) 在 push、pull request 和手动触发时运行当前骨架校验。前后端测试命令尚未建立，CI 通过暂不表示应用构建或业务测试通过；扩展范围见 [架构说明](docs/architecture.md#持续集成当前骨架阶段)。

## 本地配置

复制 `.env.example` 为 `.env` 后填入本机配置。`.env`、`.claude/settings.local.json` 和 Codex 本地状态均不提交。当前不需要任何密钥即可运行基础校验。
