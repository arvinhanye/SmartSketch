# Claude 交接：一键启动演示环境（DEMO-01）

- review_status: ready_for_review
- 分支：`claude/one-click-start-2ibfrb`，base `main@86bb94d`
- 决定：无新 ADR（只把运行手册方式 B 自动化，沿用 ADR-076 演示模型与 0.58 阈值、ADR-078 导入只增不删）

## 交付物

| 文件 | 内容 |
| --- | --- |
| `scripts/start-demo.sh` | 一键启动：`.venv` 与后端依赖 → 前端 `npm ci` → 缺 `.env` 时生成演示配置 → `dev-up.sh` → 迁移 → 建号 → API + worker → `import-demo.py` → Vite 前端 → 打开浏览器；Ctrl+C 结束三组进程，Neo4j 保留 |
| `docs/runbook.md` | §2 新增「一键启动」小节，原手动步骤改名「方式 B：本机进程，手动」 |
| `.gitignore` | 忽略 `.demo/`（脚本日志） |

## 行为要点

- 本次进程强制 `LLM_MODE=demo`、`EMBEDDING_MODE=demo`、`APP_ENV=development`、`QA_SIMILARITY_THRESHOLD=0.58`（可用 `DEMO_QA_SIMILARITY_THRESHOLD` 改），不写回 `.env`。
- 已有 `.env` 只在 `AUTH_JWT_SECRET` 空或短于 32 位时补随机值；其余一律不动（`NEO4J_PASSWORD` 与已有库绑定）。
- 演示口令：`SEED_DEMO_PASSWORD`，缺省 `smartsketch-demo`；账号已存在时不重置，提示「沿用原口令」。
- 后端进程均从 `src/backend` 启动，与运行手册手动步骤共用 `src/backend/storage/`。
- 启动前检查 8000 与前端端口是否被占用；任一服务中途退出则打印其日志尾部并整体收尾。
- 按 macOS 自带 bash 3.2 编写（不用 `wait -n`、关联数组）。

## 验证（云端 Linux 容器，Python 3.11、Node 22、Docker 29）

```bash
scripts/start-demo.sh --no-open          # 从零：无 .venv、.env、node_modules
```

- 首次：依赖安装、Neo4j 拉镜像启动、迁移、三个账号 `created`、导入报告 `published_version: 1`、前端 5173 就绪。
- 经前端代理 `POST /api/v1/auth/login`（demo_student / smartsketch-demo）得到令牌，`GET /api/v1/courses` 返回已发布的「【示例】数据结构：栈与队列」。
- `kill -TERM` 脚本：打印停止信息，API、worker、vite 无残留。
- 伪终端内第二次运行后发送 Ctrl+C：账号 `exists, unchanged`，导入 `publish_unchanged: true`，退出后无残留进程。
- `./scripts/verify.sh`：exit 0（`Scaffold verification passed.`；容器内先按 `src/contracts/toolchain.txt` 装了 datamodel-code-generator 与 openapi-typescript）。

## 风险与下一步

- 未在 macOS 上实跑；bash 3.2 兼容只做了人工核对。请在 Mac 上跑一次 `scripts/start-demo.sh`。
- 若本机 Neo4j 库此前以 fake/真实向量建过，API 会拒绝启动；脚本会打印 API 日志尾部，按运行手册第 3 节换库或 reembed。

## 修复：macOS bash 3.2 报 `API_PORT�: unbound variable`（2026-09-27）

- 现象：用户在 Mac 上运行，第 120 行 `:$API_PORT）` 报 unbound variable。macOS 自带 bash 3.2 在 UTF-8 locale 下把紧跟变量的全角字符首字节读成变量名的一部分。
- 修复：所有紧跟非 ASCII 字符的变量改为 `${VAR}`（`start-demo.sh`、`e2e.sh`、`verify/integration.sh`、`tests/hooks/test_block_dangerous.sh`）。
- 回归：`tests/tooling/test_shell_multibyte_vars.py` 扫描 `scripts/`、`tests/`、`.claude/` 下全部 `.sh`；修复前 1 failed，修复后 3 passed。`./scripts/verify.sh` exit 0；云端重跑 `start-demo.sh` 启动与 TERM 清理正常。
- Linux 上无法复现 macOS 的字符分类行为，Mac 实测仍待用户确认。

