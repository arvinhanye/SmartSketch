# OPT-06A：compatible.py 按职责拆分

- task_id：OPT-06A；负责人 Codex；状态 IN_PROGRESS（实现与后端全量通过，共用门禁/最终审查待完成）。
- 本地分支 `codex/opt-06a-compatible`；任务基线 `ffef748`，产品整合基线 `ec92026`。
- 用户已允许本地整合 OPT-03/05 后继续，暂不推送或合并远端 PR。未来本项 PR 以 `codex/opt-06-base` 为 base。

## 文件与边界

| 文件（均位于 src/backend/app/services/ai/） | 职责 |
| --- | --- |
| compatible.py | 保留 CompatibleModelClient 聊天实现、旧导入入口及显式再导出；1074 行降为 423 行 |
| compatible_transport.py | HttpResponse/HttpTransport、DNS/连接、ExchangeDeadline、stdlib HTTP transport |
| compatible_protocol.py | token 估计、请求常量、响应/用量解析、HTTP 错误映射 |
| compatible_base.py | 共享凭据/URL 校验、POST、deadline 读取、错误体与 JSON 读取 |
| compatible_embedding.py | CompatibleEmbeddingClient、批次/维度/向量/模型检查 |

函数和类的实现原样搬移；新模块依赖无环，不反向导入 compatible。原入口保留所有原定义（包括已有消费者直接导入的内部符号），以及原先导入的模块属性。__all__ 的内容与顺序不变。没有改 key/URL 安全检查、超时覆盖范围、错误类别、流式事件或用量规则。

## 验证

- 临时 AST/运行时审计：44 个定义的实现 AST 相同；30 个函数/类签名相同；旧入口与新归属模块的对象身份相同；__all__ 相同。证据 `.superpowers/sdd/2026-11-10-opt-06-responsibility-split/a-audit.json`。
- `PYTHONPATH=src/backend .venv/bin/python -m pytest tests/backend/test_e03.py tests/backend/test_e04.py tests/backend/test_l05.py tests/backend/test_c02b_disable_thinking.py -q -p no:cacheprovider`：**413 passed，exit 0**（31.36 秒；已有 Starlette/httpx 弃用警告）。
- `PATH="$PWD/.venv/bin:$PATH" scripts/verify/backend.sh full`：**4264 passed / 27 登记 skip，gate PASS，exit 0**；原始证据 `a-backend-full.log` / `.exit`。
- 共用 `./scripts/verify.sh` 基础门禁将在四项最终状态运行；最终独立审查和差异检查尚未完成。
- 日志目录为上述 `.superpowers/sdd/2026-11-10-opt-06-responsibility-split/`，定向日志 `a-targeted.log` / `.exit`。

## 接口、数据与未完成项

没有 API/契约、数据模型、数据库、配置、依赖或供应商协议改动。仅同步内部源码映射。纯搬移沿用现有行为回归，不添加只验证文件布局的测试。

当前未完成：共用门禁、最终审查。无真实付费模型调用。回滚本项代码时按本项独立提交范围恢复；没有数据回滚步骤。
