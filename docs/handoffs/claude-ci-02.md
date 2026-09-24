# Claude 交接：CI-02 前端与后端测试接入 CI

- `task_id`: CI-02
- `review_status`: ready_for_review（PR 待依赖合入后开）
- `worktree`: `/Users/arvinhan/Desktop/SmartSketch/.claude/worktrees/a09-dev-environment-check-8e5e93`，分支 `claude/ci-02`
- `base_commit`: `dddafb3`（main）
- 来源：审查意见 B01-R03、B05-R03；ArvinHan 2026-09-24 选定「把前端命令加进 CI」

## 交付物

- `.github/workflows/ci.yml`：在原 `scaffold` job 之外新增两个并行 job，风格与 CI-01 一致（`actions/*@v7`、`persist-credentials: false`、不开包管理缓存、只读权限）。
  - `frontend`：Node 24；`npm ci --prefix src/frontend`、`type-check`、`test -- --run`、`build`。
  - `backend`：Python 3.12；`pip install -e './src/backend[test]'`、`pip check`、`pytest tests/backend -q`。
- `docs/architecture.md`「持续集成」一节（原「持续集成（当前骨架阶段）」）、`README.md` 的 CI 说明、`docs/tasks.md` 的 CI-02 行。

## 依赖与合入顺序

新 job 要求 main 上已有 B02 的 `test` 脚本（PR #27）以及 B05/B06 的后端包与测试。B05/B06 已于 2026-09-24 合入（PR #14 `089e9ef`、PR #21 `afb9760`）。本分支合入了同步 main 后的 B02 分支，PR 以 `claude/frontend-dev-04eee7` 为目标，#27 合入后改为以 `main` 为目标。

## 实际验证

| 命令/方法 | 结果 |
| --- | --- |
| Ruby `YAML.load_file` 解析 | jobs = scaffold、frontend、backend；`permissions` 仍为 `contents: read` |
| 临时合并树（本分支 + `claude/b03-b04` + 已同步 main 的 B06），`env -i` 干净环境逐条运行 frontend job 命令 | `npm ci`、`type-check`、`test -- --run`（30 passed）、`build` 均 exit 0 |
| 同一合并树，Python 3.11 新虚拟环境运行 backend job 命令 | 安装与 `pip check` exit 0；`pytest tests/backend -q` 58 passed |
| `./scripts/verify.sh`、`git diff --check` | exit 0 |

临时合并树用完即删，没有推送。本地没有 Python 3.12；3.11（项目声明的最低版本）与 3.13 都已通过，3.12 在两者之间。GitHub 托管运行器上的首次运行待开 PR 后确认。

## 风险

- CI 用 Node 24 和 Python 3.12，本地验证用的是 Node 26 与 Python 3.11/3.13。版本差异由 `engines` 与 `requires-python` 约束，首次托管运行时核对。
- B02 的嵌套运行用例在 CI 中会再起一次 Vitest，整个前端 job 预计多 1～2 秒。
- 后端 job 的 `pip install -e` 会生成 egg-info（B05-R01），只影响 CI 工作区，不影响门禁。

## 回滚

撤销本分支对 `.github/workflows/ci.yml` 与三处文档的改动即可；无数据或外部状态。
