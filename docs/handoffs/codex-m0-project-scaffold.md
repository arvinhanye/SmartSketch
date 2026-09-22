# Codex 交接：M0-01 项目协作与应用骨架

- **状态**：DONE
- **日期**：2026-09-22
- **范围**：建立 Codex / Claude 共同工作契约、协作规则、基础产品与架构文档、任务看板、规格、应用源码预留目录与唯一基础校验入口。

## 已交付

- 根目录 `AGENTS.md`：角色边界、认领/完成流程、质量门禁、交接格式与核心工程约束。
- `CLAUDE.md`、`.claude/settings.json`、三份角色规则与两份 hooks；个人 `settings.local.json` 已被忽略。
- `docs/`：产品、架构、ADR、任务、集成及交接约定，内容对应 A10 方案的当前技术取舍（Vue 3、2D G6、FastAPI、Neo4j + SQLite）。
- `specs/course-knowledge-graph.md`：课程图谱 MVP 的数据规则与验收条件。
- `src/`：前端、后端分层和共享契约预留目录；尚未安装业务依赖或创建应用实现。
- `scripts/verify.sh`：检查项目骨架、JSON、忽略规则、任务状态和 DAG 文档约束。

## 验证

```text
./scripts/verify.sh                         → Scaffold verification passed.
bash -n scripts/verify.sh .claude/hooks/*.sh → passed
python3 -m json.tool .mcp.json              → passed
python3 -m json.tool .claude/settings.json  → passed
git check-ignore .claude/settings.local.json → ignored
```

## 配置/API/数据影响

- 新增 `.env.example`，只含变量名与非敏感开发占位值；没有写入任何密钥。
- `.mcp.json` 为共享空清单；接入外部 MCP 前需更新 `docs/integrations.md`。
- 未定义可执行 API、数据库迁移或依赖锁文件；该工作由 M0-02 至 M0-05 逐项完成。

## 风险与下一步

1. 先由前后端共同完成 **M0-04**，版本化 REST DTO、SSE 任务事件和图谱交换格式，避免分别初始化后接口漂移。
2. 后端 Agent 接续 **M0-03** 时创建 `GET /health`、测试与启动命令；前端 Agent 接续 **M0-02** 时初始化 Vue 3/Vite，并依据契约连接 API 客户端。
3. Codex Desktop 的 `.codex/` 是受保护的本地元数据目录；当前环境不允许手动创建。README 已明确它由 Desktop 管理，仓库协作不依赖该目录被提交。

## 回滚

本任务只新增基础结构。需要撤回时，逐个删除本次新增的受版本控制文件；不要使用全局重置或清理命令，以免影响其他 Agent 的改动。
