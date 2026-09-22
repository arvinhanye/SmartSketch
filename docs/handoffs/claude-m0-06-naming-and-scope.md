# Claude 交接：M0-06 命名统一 + M0-08 评测资产目录

- **状态**：DONE
- **日期**：2026-09-22
- **范围**：消除 S2 V0.4 与仓库契约文档的命名/模型/状态机分歧（P1），补齐赛题明确要求但 MVP 范围遗漏的能力（P2），建立提示词与评测资产目录，并为上述约定增加自动化门禁。
- **不在本次范围**：S2 源文档（Word/PDF）的三处措辞同步，已登记为 M4-04。

## 已交付

### P1 一致性修复（依据 ADR-004）

| 分歧 | 裁决 | 落点 |
| --- | --- | --- |
| `RELATED` vs `RELATED_TO` | 以仓库为准，保留 `RELATED_TO` | S2 待改（M4-04） |
| `APPLIES_TO` vs `EXAMPLE_OF` | 以仓库为准，保留 `EXAMPLE_OF` | S2 待改（M4-04） |
| `Chunk` vs `SourceChunk` | 以 S2 为准，统一为 `Chunk` | `docs/architecture.md` |
| Neo4j 缺 `Chapter`/`Document` | 补齐，含 `HAS_CHAPTER`/`HAS_DOCUMENT`/`HAS_CHUNK`/`EVIDENCE` | `docs/architecture.md` |
| `KnowledgePoint` 字段不足 | 补 `aliases`/`type`/`importance`/`difficulty`/`level`/`source`/`locked`/`embedding` | `architecture.md`、`specs` |
| SQLite 缺用户与审计表 | 补 `users`/`course_members`/`edit_logs`/`llm_calls`，并改用「模型名 / 表名」两列 | `docs/architecture.md` |
| 任务状态机两侧各缺一半 | 合并，并新增两份文档都遗漏的 `cancelled` | `specs` 验收条件 2 |

`users`/`course_members` 是必补项：赛题技术要求（四）强制教师端与学生端双角色，原仓库数据模型无用户实体。

`cancelled` 是新发现的漏洞：S2 接口表已有 `POST /api/tasks/{tid}/cancel`，但两份文档都未定义对应状态。

### P2 范围补齐（每项对应赛题原文）

| 补入能力 | 赛题依据 | 落点 |
| --- | --- | --- |
| 学习材料生成（讲解 + 示例 + 3 题） | 问题说明（三） | MVP 表、验收条件 7、M2-11 |
| 卡片/列表视图 | 技术要求（二） | MVP 表、验收条件 5、M2-10 |
| 推荐路径可视化 | 技术要求（三） | MVP 表、验收条件 8、M2-07 |
| 性能指标 ≤60s / ≤15s | 技术要求（五） | MVP 表、验收条件 9、M3-04 |
| 知识点 ≥20、关系 ≥3 类、准确率 ≥70% | 技术要求（一） | 验收条件 10、M3-01 |
| 多课程 ≥2 门 | 技术要求（四） | MVP 表、验收条件 3、M2-12 |
| 提示词记录 / 准确率报告 / 问答测试集 | 提交材料（五） | `prompts/`、`evals/`、M4-02/03 |

### 新增资产

- `prompts/README.md`：版本化目录约定、front matter 格式、8 个提示词清单、CHANGELOG 模板；约定已发布版本不可修改，效果列必须指向评测报告。
- `evals/README.md`：标注规范（双人独立标注 + Cohen's Kappa + 别名归一）、抽取与问答指标定义、消融实验表、性能报告基准要求。

### 任务看板

`docs/tasks.md` 重写为 M0–M4 五个里程碑共 49 项可认领任务。编号细分说明已写入文件头：原 M1-02/03 拆为子项，原 M1-05 的审核与发布移入 M2。

## 验证

```text
bash -n scripts/verify.sh                    → 通过
./scripts/verify.sh                          → Scaffold verification passed.

负向测试（验证门禁真会触发，测试后文件已完整还原）：
  注入 APPLIES_TO 到 specs/  → Naming drift (ADR-004): 'APPLIES_TO' found, use EXAMPLE_OF；exit=1
  移除 specs/ 的 cancelled   → Task state machine misses 'cancelled' (ADR-004)；exit=1
  还原后复跑                 → Scaffold verification passed.；exit=0
  diff 比对备份              → 文件已完整还原
```

未运行前后端测试：`src/frontend/` 与 `src/backend/` 尚无实现代码与测试命令（M0-02/M0-03 未开始）。

## 配置 / API / 数据影响

- **数据模型有破坏性变更**：Neo4j 节点与关系、`KnowledgePoint` 字段、SQLite 表集合均已变更。由于尚无实现代码与数据库实例，**本次无需迁移**。M0-05 建库脚本须直接按新模型编写。
- **API 契约未定义**：M0-04a~d 仍为 TODO。契约编写必须以 ADR-004 为唯一命名基线。
- 未新增环境变量，未改动 `.env.example`、`.mcp.json`。
- `scripts/verify.sh` 新增两类门禁：契约文档命名漂移（扫描 `AGENTS.md`、`docs/architecture.md`、`specs/course-knowledge-graph.md`）与任务状态机完整性。注意门禁依赖 `prompts/README.md`、`evals/README.md` 存在。

## 风险与下一步

1. **D-02 / D-03 仍阻塞主链路**。S2 已写明 DeepSeek 主 / 通义千问备，也已设计 `users` 表与 `/api/auth/login`，但未经正式裁定、未写入 ADR。这两项分别卡住 M1-03a 与 M0-03，需决策人今日确认并由 M0-07 回写 ADR-005。本次未代为决策。
2. **进度风险最高**。距 10-08 提交 17 天，业务代码为 0 行，而 S2 排期的 M1 主链路节点为 9-26（5 天后）。建议 M0-04a~d 立即拉齐，M0-02/03/05 并行起步。
3. 命名门禁只扫描三份契约文档，不扫描实现代码。M0-04 产出 `src/contracts/` 后，应把该目录加入 `contract_docs` 数组。
4. S2 源文档三处措辞未同步（M4-04），在 S2 出 V0.5 前，以仓库文档为准。

## 回滚

本次仅改动文档、规格与校验脚本，无代码与数据影响。

```bash
git checkout -- AGENTS.md docs/ specs/ scripts/verify.sh
```

新增目录用 `rm -r prompts evals` 逐个移除。注意 `scripts/verify.sh` 的必需文件检查依赖 `prompts/README.md` 与 `evals/README.md`，两者必须与脚本同进同退，不可只删目录而保留脚本改动。
