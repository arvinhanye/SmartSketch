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
├── README.md                 # 本文件
├── NOTICE                    # 第三方参考项目与许可登记
├── .claude/                  # 团队规则与 hooks
│   ├── rules/                # 前端 / 后端 / 测试规则
│   └── hooks/                # 破坏性命令拦截、完成通知
├── .mcp.json                 # 无密钥的团队 MCP 清单
├── .env.example              # 环境变量名与无敏感占位值
├── .gitignore                # 含原始课程资料与参考方案原文的忽略规则
├── docker-compose.yml        # 本地依赖（Neo4j + APOC）
├── docs/
│   ├── product.md            # 产品定义
│   ├── architecture.md       # 架构与源码映射
│   ├── integrations.md       # 外部集成、环境变量、本地启停
│   ├── decisions/            # ADR，一条一文件
│   ├── tasks.md + tasks/     # 任务看板索引 + 按里程碑分文件
│   └── handoffs/             # Agent 交接记录
├── specs/                    # 功能规格与验收标准
├── scripts/
│   ├── verify.sh             # 质量门禁分发器
│   ├── verify/               # 各领域子门禁与必需文件清单
│   └── dev-*.sh              # 本地依赖启停
├── tests/                    # backend / frontend / contracts 测试
├── prompts/                  # 提示词资产：约定、模板、索引
├── evaluation/               # 抽取与问答评测脚本，reports/ 不入库
├── datasets/                 # 标注集；raw/ 放原始资料，不入库
└── src/
    ├── frontend/             # Vue 应用
    ├── backend/app/          # FastAPI 分层：api/schemas/services/repositories/workers
    └── contracts/            # 前后端共享 API / 事件契约
```

Codex Desktop 若在本机生成 `.codex/`，它是**可选的本地目录，不提交**，仓库协作不依赖它——所以上面的树里没有它。

## 协作方式

1. 先阅读 [AGENTS.md](AGENTS.md) 与[任务看板索引](docs/tasks.md)，再看对应的 `docs/tasks/<里程碑>.md`。
2. 在 `docs/tasks/<里程碑>.md` 认领任务，**只改自己那一行**，并以 `specs/` 的验收条件为准实现。
3. 修改共享接口、数据模型或范围时，同步更新架构文档；新决策新建 `docs/decisions/ADR-<编号>-<slug>.md`（[索引](docs/decisions/README.md)）。
4. 完成后运行：`./scripts/verify.sh`（分发到 `scripts/verify/` 下的各领域门禁，任一失败即整体失败）。
5. 写入 `docs/handoffs/<agent>-<task>.md`，再交由下一个 Agent 接续。

新增内容一律新建文件，不追加共享文件——门禁清单加进 `scripts/verify/manifests/<领域>.txt`，新门禁写进 `scripts/verify/<领域>.sh`。详见 AGENTS.md §3「写争用规则」。

## 本地配置

复制 `.env.example` 为 `.env` 后填入本机配置。`.env`、`.claude/settings.local.json`、Codex 本地状态、原始课程资料与评测报告均不提交。当前不需要任何密钥即可运行基础校验。

启动本地依赖：`./scripts/dev-up.sh`；停止：`./scripts/dev-down.sh`。详见 [docs/integrations.md](docs/integrations.md)。
