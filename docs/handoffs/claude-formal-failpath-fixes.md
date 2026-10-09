# Claude 交接：正式模式失败路径验收后的修复批次 2（FORMAL-RELEASE-01）

```text
from: Claude
to: 用户 / DeepSeek harness（第二轮）
date: 2026-10-09
task: FORMAL-RELEASE-01 修复批次 2（ADR-095）
input: docs/handoffs/deepseek-formal-failures-20261009.md（FAILPATHS: FAIL）
branch: claude/release-launcher-merge（本地，未推送）
```

## 1. 交付物

| 缺陷 | 判断 | 改动 |
| --- | --- | --- |
| M5 超限上传返回 nginx 英文 HTML 413 | 属实 | `src/frontend/nginx.conf`：`client_max_body_size` 51m；`error_page 413` 返回契约形状的 `FILE_TOO_LARGE` JSON |
| M7 发布时向量偶发失败返回笼统 500 | 属实 | `services/ai/embeddings.py` 无截止时间调用方对瞬时故障有界重试（2 次，1s/3s）；`api/versions.py` 向量失败返回 503 `LLM_UNAVAILABLE` + `details.reason`；前端 `useVersions.ts` 固定可行动文案 |
| M9(b) 守护进程不可达时终端误报「已启动」 | 基本不成立 | 不修（网页状态已显示 Docker 未就绪） |
| C2 超长提问返回 503 | 规格未定义 | `ChatRequest.question` ≤ 2000 字（契约 + 输入框 `maxlength`） |
| 向导误填维度（1021）无校验 | 新发现 | `launcher/.../config.go` `checkKnownDimensions`；`ui/app.js` + `index.html` 页面内拦截与 datalist |
| 「docker kill 后不自愈」 | 观察，非缺陷 | Claude 实测属实；手动 kill 在 Docker 视为人为停止，真实崩溃自愈未实测 |

规格与决策：`specs/teacher-review-publish.md` V5.1、`specs/grounded-qa.md`（输入长度上限）、`docs/integrations.md`、`docs/decisions.md` ADR-095、`docs/tasks.md`。

## 2. 接口 / 数据变更

- `POST /courses/{cid}/publish` 新增 503 响应：`LLM_UNAVAILABLE`，`details.reason ∈ {vector_unavailable, vector_rejected}`（契约 `api.v1.yaml` 与生成物已同步，`gen-contracts.sh --check` 一致）。不新增错误码。
- `ChatRequest.question` 增加 `maxLength: 2000`。超出返回 422 `VALIDATION_ERROR`。
- 无数据迁移、无 Neo4j / SQLite 结构变更。回滚：回退本批提交即可，不涉及数据。

## 3. 验证（均为 Claude 在本机实际运行）

| 范围 | 命令 | 结果 |
| --- | --- | --- |
| 向量重试 | `pytest tests/backend/test_e07.py` | 21 通过（新增 4 条重试用例：瞬时重试成功、有界、永久错误不重试、带截止时间不重试） |
| 发布错误映射 | `pytest tests/backend/test_g06.py` | 18 通过（新增 3 条 503 映射） |
| 问题长度 | `pytest tests/backend/test_chat_question_limit.py` | 4 通过 |
| nginx | `pytest tests/integration/test_k08.py tests/tooling/test_startup_release.py`；`nginx -t`；真实 nginx 容器 POST 60MB | 28 通过 1 跳过；语法通过；实测返回 `application/json` 的 `FILE_TOO_LARGE` |
| 契约 | `scripts/gen-contracts.sh --check`、`scripts/check_contracts.py` | 一致、通过 |
| 前端 | `vitest run tests/frontend`；`npm run type-check` | 75 文件 / 1285 条通过；类型检查通过 |
| 向导 | `pytest tests/startup/test_wizard_guidance.py`（真实浏览器） | 通过（含 1021 被拦下且未发出请求） |
| 启动器 | `go test ./...`（Go 1.26.8，`TMPDIR` 指向可 chmod 目录） | 通过；`gofmt`、`go vet` 无输出 |
| 后端全量 | 见 `docs/tasks.md` 末尾记录 | 见下 |

后端全量：`tests/backend tests/tooling tests/contracts`，**去掉 `tests/tooling/test_stop_procs.py::test_grace_period_is_not_shortened_by_shell_seconds_rounding`**（该用例在本机 macOS 上稳定失败：宽限期实测 0.01 秒，期望 ≥ 2 秒；脚本与测试文件本批未改动，同文件其余 3 条通过；Linux CI 之前为绿；已记为待查，未在本批处理）。结果见本文件末尾「补充」。

**未验证**：发布期向量失败的真实触发（`vector_unavailable` 靠单元测试；`vector_rejected` 可用无效向量密钥在最终镜像上复现）；`release_smoke` 三个场景需要用新代码重建镜像后才能跑（需要推送，等用户批准）；真实崩溃（非手动 kill）后的容器自愈。

## 4. 风险

- 重试最坏使发布多等约 4 秒；永久配置错误不重试，不增加等待。
- nginx 上限与 `UPLOAD_MAX_BYTES` 是两处各自定义的值，调大后者必须同步调大 `nginx.conf`（测试已断言「代理上限 ≥ 文件上限 + 表单开销」）。
- 向导只校验已知模型（`text-embedding-v4`）；其他模型的维度仍可填错，且无法在向导内修复，只能走教师向量设置或重装。
- 前端与后端代码已变，**必须重建镜像、更换清单摘要**后才能进入第二轮验收；现有 `rc-8a33ab9` 包不含这些修复。

## 5. 下一步

1. 用户批准后：推送并重建后端、前端镜像，生成新清单与 darwin-amd64 包。
2. 新隔离安装（用户走向导，维度 1024、端口避开 8080/8081 已占用者）。
3. 第二轮交 DeepSeek（交接稿另写）：复核 M5（`FILE_TOO_LARGE` JSON）、发布 503 `vector_rejected`（无效向量密钥）、C2 的 422、O1 端口冲突、O2 备份恢复；**每步后即时核算用量，生成类累计达 300,000 立即停**。
4. 启动器 PR 合入 main 且 CI 变绿后出包。

## 补充：后端全量结果

- `pytest tests/backend tests/tooling tests/contracts`（去掉上述 1 条）：**4484 通过、27 跳过、3 失败**。3 条失败是 `tests/contracts/test_b14.py` 两条与 `test_contracts.py` 一条，原因是我的测试进程 PATH 里的 python 没有 `yaml`（`ModuleNotFoundError`），生成脚本中途退出。带上正确 PATH（venv + `node_modules/.bin`）后这两个文件共 **28 通过**，生成物与契约一致。
- `./scripts/verify.sh basic`：通过（骨架、钩子回归、契约门禁）。
- 未跑：`verify.sh full/integration`、`release_smoke`（需新镜像）、Playwright E2E。
- 待查（与本批无关）：`tests/tooling/test_stop_procs.py::test_grace_period_is_not_shortened_by_shell_seconds_rounding` 在本机 macOS 上稳定失败（宽限期实测 0.01 秒）。

