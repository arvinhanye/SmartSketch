# 消歧后端成果提交交接

日期：2026-11-11；任务：DISAMBIG-PR-01；负责人：Codex。

用户已授权提交此前保留的 BE-01～03、完整设计和接口交接，并推送创建 PR；此前交接中的“未提交、未推送”描述是各批结束时的历史状态。本轮不自动合并 PR。

## 范围

- 分支 `codex/knowledge-disambiguation`；main 基线 `31a7e6c260c0a3b63f4466d28812cf59f6dc12b2`，提交前重新查询远端确认相同，没有该分支的已有 PR。
- 三态裁决、混合召回、原始提及、整组和图结构校验、独立草稿投影及撤销、审核过滤、覆盖/历史/撤销 API、契约生成类型、对应测试及文档。
- 前端仅新增接口客户端、两条原因标签及接口测试；Claude `d102915` 工作树保持干净。
- 原 86 个已核对文件，加本交接；不含开发数据库、真实课程资料、构建产物、临时验证日志或密钥。未修改本地模型配置和开发数据。

## 提交前重新验证

| 命令 | 结果 |
| --- | --- |
| `PATH="$PWD/.venv/bin:$PATH" ./scripts/verify.sh` | exit 0；契约真源及生成物一致，基础门禁通过 |
| `.venv/bin/python -m pytest tests/backend/test_disambiguation*.py tests/backend/test_fusion*.py tests/backend/test_graph_projection.py tests/tooling/test_backend_layering.py -q` | 150 passed，25.61s，exit 0 |
| `PATH="$PWD/.venv/bin:$PATH" scripts/verify/backend.sh full` | 4488 passed / 27 登记跳过 / 1 既有弃用警告，897.97s，exit 0 |
| `scripts/verify/frontend.sh full` | 85 文件 / 1446 passed；类型检查和构建通过，exit 0；既有大包警告保留 |
| `git diff --cached --check`、暂存文件哈希核对 | 通过，验证期间代码未改变 |

前批隔离 Neo4j、撤销冲突和 Claude 临时兼容副本的证据见 BE-02/03 交接；本轮没有重新运行这些外部集成，不把单元门禁替代为浏览器或真实模型验收。此前独立审查及修复记录也保留在对应交接中。

## 运行与下一批

分析和自动合并默认仍关闭。迁移 021 与物理草稿指针的回退必须遵循 BE-02 交接，不能只删除列或把代码直接退回不识别指针的版本。未执行开发库迁移。

长窗口/跨窗口覆盖、局部规范化后关系抽取与受影响关系重抽、手动合并服务端计划、新 UI 控件和真实模型质量/减负/速度评测仍待后续实施。下一批从本次稳定提交继续，避免把后续未验收代码混进本 PR。
