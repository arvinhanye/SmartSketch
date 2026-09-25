# Claude 交接：D-11 上传配置落地

- 日期：2026-09-25
- 分支 / base：`claude/d11-upload-config` / `origin/main@04f8ac6`
- 角色：协调方。D-11 已签收（ArvinHan，2026-09-24），任务板把「配置落地」列为待认领，C13 合并后三份文件的锁已释放

## 交付物

| 文件 | 变更 |
| --- | --- |
| `src/backend/app/config.py` | `Settings` 新增 `STORAGE_DIR: str = "./storage"`、`UPLOAD_MAX_BYTES: int = 52_428_800`（≥ 1）；`_check_rules` 拒绝空白 `STORAGE_DIR` |
| `.env.example` | 在 `SQLITE_URL` 之后补两项与注释 |
| `docs/integrations.md` | 「应用运行与存储」表加两行；「启动校验（B06）」加 `STORAGE_DIR` 规则 |
| `tests/backend/test_d11_upload_config.py` | 10 个用例：缺省值、显式值、非法上限 5 例、空白目录 2 例、设置值直接构造 `FileStorage` 并在超限时报 `limit_bytes` |
| `docs/tasks.md` | D-11 决策行改为「配置已落地」；删掉 C05 节里的待认领说明；新增「D-11 上传配置落地」节 |

## 取值依据

- `UPLOAD_MAX_BYTES=52428800`：D-11 原文（50 MiB，超过即 413 `FILE_TOO_LARGE`，`details.limit_bytes`）。
- `STORAGE_DIR=./storage`：沿用 740adb 分支的 `.env.example` 与 integrations 登记。`docs/reviews/branch-integration-map.md` 已计划在「批 2」导入 `STORAGE_DIR`。它和 `SQLITE_URL` 的缺省库文件在同一个已被 `.gitignore` 忽略的 `storage/` 目录下。C05 的存储名是随机数加格式后缀，不会和 `smartsketch.sqlite3` 撞名。
- 启动校验只检查 `STORAGE_DIR` 非空白，不创建目录、也不检查可写。目录由 `FileStorage.__init__` 以 `0o700` 创建（C05），这样 worker 和迁移命令在没有资料目录时也能启动。

## 验证

| 命令 | 结果 |
| --- | --- |
| 红灯：只加测试后 `pytest tests/backend/test_d11_upload_config.py -q` | 10 failed（`AttributeError` 3 个、`DID NOT RAISE SettingsError` 7 个） |
| 改 `config.py` 后跑 D-11 与 B06 | D-11 全过；B06 `test_env_example_covers_every_setting` 按预期失败（示例文件未补） |
| 补 `.env.example` 后 `pytest tests/backend -q` | 730 passed，1 warning（既有 Starlette `httpx` 弃用提示） |
| 反向篡改：去掉空白目录检查 | 2 failed，恢复后 10 passed |
| 反向篡改：上限下界改为 `ge=0` | 1 failed，恢复后 10 passed |
| `./scripts/verify.sh`、`git diff --check` | exit 0（`Scaffold verification passed.`）；diff check 通过 |

## 接口 / 数据变更

新增两个环境变量，都有缺省值，不影响现有部署。没有契约、数据库或迁移变更。

## 下一步

- C06（Codex 进行中）、C07 构造存储时统一用 `FileStorage(settings.STORAGE_DIR, max_bytes=settings.UPLOAD_MAX_BYTES)`。
- F01 导入 740adb 的 Compose 与脚本时，`STORAGE_DIR` 已在 main，只需导入 `NEO4J_DATABASE` 和容器变量。

## 回滚

还原本 PR。两个设置字段都有缺省值，下游暂未引用，删除不影响其他模块。
