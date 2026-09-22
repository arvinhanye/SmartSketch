# CLAUDE.md

@AGENTS.md

## Claude 补充约定

- 每次开始前，先读取 `AGENTS.md`、`docs/tasks.md` 和本次相关规格。
- 遵循 `.claude/rules/` 中与改动范围匹配的规则；规则是对共同契约的补充，不覆盖共同契约。
- 运行命令或改动文件后，使用 `docs/handoffs/claude-<task>.md` 留下可复现交接；不要代替 Codex 写 `codex-*.md`。
- 仅使用 `.mcp.json` 的团队共享、无密钥配置。个人配置放 `settings.local.json` 或本机环境变量，绝不提交。
