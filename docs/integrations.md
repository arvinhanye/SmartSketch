# 外部集成、MCP 与环境变量

## 当前状态

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
