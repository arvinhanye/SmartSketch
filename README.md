# SmartSketch / 智绘学途

面向高校课程的 AIGC 知识图谱智能构建与学习导航系统。教师上传课程资料后审核并发布图谱；学生通过 2D 图谱、掌握进度、可解释路径和带出处问答完成学习导航。

## 交付状态

> **当前候选版本：`rc-b59869d`（release candidate，不是稳定版）。** 安装包通过 [GitHub Releases](https://github.com/arvinhanye/SmartSketch/releases) 分发。该版本的 Release 目前是**草稿**，由维护者检查后才会公开；公开之前没有可下载的包，请以 Releases 页面的实际状态为准。

| 平台 | 状态 |
| --- | --- |
| Mac Intel（`darwin-amd64`） | 已在开发机上完整实测：安装向导、业务闭环、失败路径、干净安装 |
| Windows 11 x64（`windows-amd64`） | **仅交叉编译与静态检查，从未在 Windows 实机运行过** |
| Mac Apple Silicon、Windows ARM | 本期不提供 |

- 运行模式：正式模式，即用户自己的大模型 API（个人模型配置，服务端加密保存）加在线向量服务（默认阿里云百炼 `text-embedding-v4`，1024 维）。
- 安装包**没有代码签名和公证**：macOS 首次打开可能被 Gatekeeper 拦下，Windows 可能出现 SmartScreen 提示。处理办法见 [安装指南](docs/startup-guide.md)，不要全局关闭系统保护。
- 已验证：真实启动器与安装向导、隔离安装下的完整业务闭环、失败路径与复核、三个发布冒烟场景、最终安装包的干净安装、合并前 CI 全部通过。问答质量的逐句核对由 AI 完成，**不是人工签收**。
- 未验证：Safari、真实业务数据的备份与恢复、Windows 与 Apple Silicon 实机、代码签名。
- 已知待办与全部验收记录见 [任务看板](docs/tasks.md)。

## 功能

- 教师：创建课程，上传 PDF、DOCX、TXT、Markdown；异步处理并查看进度；审核节点与关系（前置关系自动检测环）；发布图谱版本，可回退。
- 学生：浏览 2D 知识图谱，搜索、筛选关系、查看来源；标记掌握进度，获得带理由的学习路径；提问并得到带出处的答案，资料不足时明确提示「资料未覆盖」。

完整产品定义见 [docs/product.md](docs/product.md)，技术边界见 [docs/architecture.md](docs/architecture.md)。

## 怎么用

- **普通用户**：从 Releases 下载对应平台的包，核对 `SHA256SUMS`，完整解压后双击入口（Mac 为 `start-macos.command`，Windows 为 `start-windows.cmd`），在浏览器向导里填向量服务 Key 并设置教师账号。需要先安装并打开 Docker Desktop，不需要 Python、Node 或 Go。详见 [docs/startup-guide.md](docs/startup-guide.md)。
- **开发者试用**：`scripts/start-demo.sh` 一键启动演示环境（演示模型，不联网、不产生费用）；正式模式、真实大模型、备份恢复、故障处理见 [docs/runbook.md](docs/runbook.md)。

## 技术栈

- Web：Vue 3、TypeScript、Vite、AntV G6（仅 2D）
- API：Python、FastAPI、SSE
- 数据：Neo4j（图谱与向量索引）、SQLite（业务、任务、进度）
- AI：OpenAI 兼容的大模型与向量接口；供应商与模型可配置
- 桌面启动器：Go 1.26.8（仅标准库），镜像按清单中的不可变摘要拉取

## 目录

```text
.
├── AGENTS.md                 # Codex / Claude 共同工作契约
├── CLAUDE.md                 # Claude 补充规则
├── .claude/                  # Claude 团队规则与 hooks
├── .mcp.json                 # 无密钥的团队 MCP 清单
├── docs/                     # 产品、架构、ADR、任务、运行手册、交接
├── specs/                    # 功能规格与验收标准
├── scripts/                  # 启动、质量门禁（verify.sh）、端到端、打包
├── launcher/                 # 桌面启动器（Go）：安装向导、Docker 生命周期、备份恢复
├── packaging/                # 发行清单、compose.release.yaml、双击入口
├── datasets/                 # 演示课程与示例资料
├── evaluation/               # 抽取与问答评测脚本
├── prompts/                  # 提示词版本
├── tests/                    # backend / frontend / contracts / e2e / startup / integration
└── src/
    ├── frontend/             # Vue 应用
    ├── backend/app/          # FastAPI 分层应用
    └── contracts/            # 前后端共享 API / 事件契约（OpenAPI 为真源）
```

## 协作方式

1. 先阅读 [AGENTS.md](AGENTS.md) 与 [任务看板](docs/tasks.md)。
2. 在任务看板认领任务，并以 `specs/` 的验收条件为准实现。
3. 修改共享接口、数据模型或范围时，同步更新架构文档或 ADR（[docs/decisions.md](docs/decisions.md)）。
4. 完成后运行：`./scripts/verify.sh`（模式 `basic`、`full`、`integration`，见脚本头注释）。
5. 写入 `docs/handoffs/<agent>-<task>.md`，再交由下一个 Agent 接续。

GitHub Actions 有三个工作流：[ci.yml](.github/workflows/ci.yml)（骨架校验、前端、后端、集成与端到端）、[startup.yml](.github/workflows/startup.yml)（启动器在 macOS、Ubuntu、Windows 运行器上的单元与静态检查，不等于平台实机验收）、[release-local.yml](.github/workflows/release-local.yml)（手动触发，只构建不发布）。

## 本地配置

复制 `.env.example` 为 `.env` 后填入本机配置。`.env`、`.claude/settings.local.json` 和 Codex 本地状态均不提交。基础校验不需要任何密钥；真实模型与向量服务的密钥只通过环境变量或个人配置接口提供，见 [docs/integrations.md](docs/integrations.md)。
