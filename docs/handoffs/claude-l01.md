# L01 隔离环境与三档门禁基线

```text
task_id: L01
review_status: ready_for_review
worktree: /Users/arvinhan/SmartSketch/.claude/worktrees/smartsketch-contest-sprint-77644f
base_commit: aa538c9
head_commit: 本任务提交（仅 docs/tasks.md 与本文件）
changed_files:
  - docs/tasks.md（认领 L01–L10；L01 置 DONE）
  - docs/handoffs/claude-l01.md
```

## 环境

- Python：`.venv` 用 `/Library/Frameworks/Python.framework/Versions/3.11/bin/python3.11`（3.11.9，与主检出的 `.venv` 同款）。依赖 `pip install -e 'src/backend[test]'`，版本全部来自 `pyproject.toml` 的锁定值。
- Node v26.4.0、npm 11.17.0；`npm ci --prefix src/frontend` 与根目录 `npm ci` 均 exit 0。
- Neo4j：`./scripts/dev-up.sh` 启动 `smartsketch-contest-sprint-77644f-neo4j-1`，映射 7688/7475，APOC 5.26.31；与主检出的 `smartsketch-neo4j-1`（7687/7474）并存。
- `.env`：工作区根目录，未跟踪、权限 600。两个供应商 key 由用户填在主检出的 `.env`，已按用户指示原样复制到工作区 `.env`，过程未显示或记录取值。

## 验证（实际结果）

| 命令 | 退出码 | 结果 |
| --- | --- | --- |
| `./scripts/verify.sh` | 0 | 基础档 PASS |
| `PYTHON=.venv/bin/python ./scripts/verify.sh full` | 0 | 后端 3559 通过、27 个登记过的跳过；前端 25 个文件 772 用例通过；类型检查与构建通过 |
| `PYTHON=.venv/bin/python ./scripts/verify.sh integration` | 1 | 集成用例 392 通过、4 跳过，PASS；图库后端用例 44 通过，PASS；端到端 2 条 FAIL |
| `PLAYWRIGHT_CHROMIUM_EXECUTABLE="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" scripts/e2e.sh` | 脚本输出「端到端通过」 | 教师、学生两条主线 2 passed（4.5 分钟） |

日志在 `.demo/logs/`（未入库）：`verify-basic.log`、`verify-full.log`、`verify-integration.log`、`e2e-chrome.log`。

## 发现

1. **集成档失败是环境原因，不是代码缺陷**：本机没有安装 Playwright 浏览器（`~/Library/Caches/ms-playwright` 不存在），两条端到端在启动浏览器时即失败。用项目已支持的 `PLAYWRIGHT_CHROMIUM_EXECUTABLE` 指向本机 Chrome 后两条都通过。之后跑集成档或端到端都要带这个变量。未下载 Playwright 浏览器。
2. **系统 Python 3.13 不适合本项目的锁定依赖**：首次用 `/opt/anaconda3/bin/python3`（3.13.5，x86_64）建环境时，pip 为某个没有预编译包的锁定依赖启动了 Rust 工具链引导（`puccinialin` 调 `rustup-init`），长时间无进展。已中止，改用 3.11。该引导只动了 9 月 24 日就存在的 `~/Library/Caches/puccinialin`，没有新建 `~/.cargo` 或 `~/.rustup`。
3. **在线向量在本机网络不可达**（影响 L02 问答基线与 L09）：`dashscope.aliyuncs.com:443` TCP 连接超时（`nc` 与 `curl` 均如此）；国际站 `dashscope-intl.aliyuncs.com` 可达，但用现有 key 请求返回鉴权失败，说明该 key 属于北京地域。`api.deepseek.com` 可达。待用户决定：恢复到北京地域的网络路径、改用国际站 key，或换一个本机可达的向量服务。
4. 重跑端到端期间我误停了它的外层 shell（把它当成另一条卡住的命令），端到端脚本本身未受影响并正常跑完、清理了一次性容器；因此该次运行的退出码没有被外层记录，结论取自脚本自己的输出。

## unverified

- 真实模型与真实向量：本任务未调用。累计真实模型计费 token：0。向量联调尝试 3 次，均未成功返回向量（两次连接超时、一次国际站鉴权失败），不产生计费。

## api_and_data_changes

无。

## rollback

无破坏性修改。`.venv`、`node_modules`、`.demo/`、`.e2e/`、`neo4j/` 均被 Git 忽略；停止本工作区 Neo4j 用 `./scripts/dev-down.sh`。

## next_action

L02：先测抽取耗时（只需要 DeepSeek，可达）；问答耗时与发布依赖向量服务，等发现 3 解决。同时推进 L03。
