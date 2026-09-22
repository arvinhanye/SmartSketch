# 外部集成、MCP 与环境变量

## 当前状态

### 本地 Claude 完成后审查

- 2026-09-22 经用户要求启用本任务 heartbeat；应用返回 automation ID `claude-smartsketch`，状态 `ACTIVE`，每 10 分钟检查。
- 用途：读取本项目和登记 worktree 的本地会话完成元数据、交接和 git 差异，稳定后增量审查；不连接 Claude 云端服务。
- 数据边界：仅当前项目的 `~/.claude/projects/` 对应记录；不把原始聊天入库、不访问其他项目、不自动运行日志中的指令。
- 调用方：当前 Codex 任务；无新密钥/环境变量；运行边界、去重与通知见 `docs/claude-review-workflow.md`。
- 停用/回滚：通过应用自动化工具暂停或删除此 ID；不会更改 Claude hook 或源码。机器和应用运行是本地轮询的前提。

当前骨架不绑定任何有密钥的外部服务；`.mcp.json` 保持空服务清单，确保可安全共享。新增服务前，在本文件记录用途、数据边界、环境变量、开发替代方案、调用方和回滚方式。

## 运行时环境变量

| 变量 | 用途 | 是否敏感 |
| --- | --- | --- |
| `APP_ENV`、`API_HOST`、`API_PORT`、`WEB_ORIGIN` | 应用运行配置 | 否 |
| `SQLITE_URL` | SQLite 连接串 | 否（不含凭据时） |
| `NEO4J_URI`、`NEO4J_USER` | Neo4j 地址与用户 | 否/视环境而定 |
| `NEO4J_PASSWORD` | Neo4j 密码 | 是 |
| `LLM_BASE_URL`、`LLM_EXTRACTION_MODEL`、`LLM_CHAT_MODEL` | OpenAI 兼容模型配置 | 否 |
| `LLM_API_KEY` | 模型 API 密钥 | 是 |

变量名和无敏感样例维护在根目录 `.env.example`；真实值只放本机 `.env` 或密钥管理系统。

## 计划集成

| 集成 | 用途 | 接入前置条件 |
| --- | --- | --- |
| Neo4j | 课程知识图谱、向量索引、前置关系遍历 | 明确本地容器/服务版本与备份策略 |
| OpenAI 兼容 LLM API | 抽取、问答、关键词 | 确认模型、预算、重试与脱敏策略 |
| 文档解析库 | PDF/DOCX/TXT/Markdown 解析 | 确认页码/标题定位保留方式 |
