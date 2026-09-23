# Codex 交接：A10 批 1 契约真源与生成链

- 状态：本地完成，待独立审查、PR 与远端 CI；执行分支 `codex/a10-batch1`，基于批 0 `c795741`。
- 来源：A10 [导入映射](../reviews/branch-integration-map.md) 第 3 节批 1；契约源文件从 `claude/worktree-contract-conflicts-740adb@978671e` 按路径检出，未整枝合并。
- 范围：`src/contracts/**`、契约生成/校验脚本、`tests/contracts/**`、CI 与总门禁、仅约束生成物的 `.gitattributes`；按 N1 同步 `Chunk` 命名，更新架构与任务板。未改 B02/B06 工作树。

## 交付

1. 导入 `api.v1.yaml`、`events.v1.md`、`errors.v1.md`、契约 README 与 3 份来源交接；从 YAML 重新生成并入库 `openapi.json`、3 份独立 JSON Schema、`python/models.py`、`typescript/openapi.d.ts`。22 条路径、59 个 schema、189 个引用。
2. 严格调用 `scripts/check_contracts.py`、`scripts/gen-contracts.sh --check` 与契约负例；`scripts/verify.sh` 增加契约门禁，CI 安装版本锁定的 Python 与 Node 工具。
3. N1：架构、教师发布规格及 D10 计划中的文本块标签统一为 `Chunk`；命名扫描仅豁免架构表中对 S2 旧别名的明确禁止说明，新增旧 `SourceChunk` 负例。A08 已随当前基线存在，故保留 `specs/learning-path.md` 扫描；尚未导入的 A09 `grounded-qa.md` 暂移出，A09 合入时须加回。
4. 来源版本锁的 `jsonschema==4.23.0` 与 `openapi-spec-validator==0.9.0` 无法共同安装；改为 `jsonschema==4.26.0`，本地安装与 `pip check` 均通过。生成器明确 `--encoding utf-8`，修复 Windows 默认 cp936 使 Python 产物无法导入的问题；统一生成物为 LF，并以 `.gitattributes` 保证 Windows 检出也保持 LF，使跨平台 `--check` 字节比较成立。在 Windows 上直接调用已安装的 `openapi-typescript` 命令，避免 `npx --no-install` 意外访问注册表。

## 实际验证

| 检查 | 结果 |
| --- | --- |
| `./scripts/gen-contracts.sh --check` | PASS，全部生成阶段与真源一致 |
| `tests/contracts/test_contracts.py` | 22/22 PASS，含缺依赖、坏引用、旧 `SourceChunk`、缺生成阶段、UTF-8 locale 负例 |
| `./scripts/verify.sh` | PASS，包含 hook、契约结构、生成物同步、22 项门禁负例 |
| `python docs/reviews/validate_atomic_plan.py` | PASS，140 项、依赖无环、JSON/Markdown 一致 |
| 导入 `src/contracts/v1/generated/python/models.py` | PASS，66 个生成模型类可导入 |
| `python -m pip check`、CI YAML 解析、`git diff --check` | PASS |

验证在隔离工作树内进行。Python 3.12 工具装在该工作树的 `.tools/py`，Node 包装在 `.tools/node`，由共享仓库 `.git/info/exclude` 忽略，均未入库。Windows 本地运行 `verify.sh` 需要 Git Bash，并把这些目录加入 Bash `PATH`；CI 直接按版本锁安装。远端 GitHub Actions 尚未运行，不能将本地通过等同于 CI 通过。

## 接口、风险与回滚

- 本批没有新业务端点或数据库迁移；导入现有 v1 契约及生成类型，运行时消费由 B08～B15 后续完成。
- `events.v1.md` §2 仍有来源分支的旧转换表，与已签收的 `specs/task-processing.md` 不一致。已在文首明确以现行规格为准；B10 必须把旧表改为指向该规格，并更新对应 YAML 字段/票据端点。此项不可当作本批通过的时序验收。
- A10 分支和前置 #16/#14/#15 未全部合入主线；按 ADR-016 须依次审查并由项目负责人合并，不能把本批直接并入当前远端 main。
- 回滚本批时撤销其提交与 CI 安装步骤，并删除本批生成物；恢复旧 `jsonschema` 锁之前须同时选择可兼容的 `openapi-spec-validator` 版本并重新运行门禁。无数据迁移。隔离 `.tools` 仅是本地验证依赖，不影响仓库或其他工作树。
