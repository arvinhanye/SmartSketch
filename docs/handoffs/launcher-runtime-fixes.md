# Launcher 与运行环境修复

输入：`launcher/start.ps1` 中文乱码导致脚本无法解析、内置 Neo4j 运行在含中文的路径下启动失败。
输出：`packaging/windows-external/launcher/start.ps1` 恢复 UTF-8（BOM）并保留“工作区凭据优先”；内置运行时改放纯 ASCII 路径；`使用手册.md` 增补“本机运行环境说明”与两条排查项。
验证：`Parser::ParseFile` 语法错误 0 处；`http://127.0.0.1:18080/health` 返回 200；教师令牌下 `POST /api/v1/api-settings/models` 返回 `ok:true`（2 个模型，209 ms），`POST /test` 返回 `ok:true`（256 ms，维 1024）。
风险：本机路径写死在 `launcher/local-runtime.json`，换机需改这三行；`%LOCALAPPDATA%\SmartSketch-External` 为数据目录，勿公开 `portable-config.json`。
回滚：恢复 `launcher/start.ps1` 与 `local-runtime.json` 即可；无数据库迁移。
