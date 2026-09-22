# 外部参考资料

本仓库的文档是**派生物**。权威方案在仓库外，仓库文档是对它的转述与细化——两者一旦不一致，**以权威文档为准**，并按本文末尾的清单回查仓库。

所有外部资料均在 `/Users/arvinhan/Desktop/A10--数字马力杯--项目规划/`（以下称「规划目录」），**只读**。

## 权威方案

| | |
| --- | --- |
| 文件 | `规划目录/智绘学途_S2解决方案.docx` |
| 状态 | **权威版本**。仓库内 `docs/product.md`、`docs/architecture.md`、`specs/` 都是它的派生物 |
| 同目录 PDF | `智绘学途_S2解决方案.pdf` 是同版本导出，**便于检索但不是权威**；两者不一致时以 docx 为准 |
| 不入库 | 受版权与体积限制，`.gitignore` 已排除 `*.pdf`、`*.docx`、`*.pptx` |

其他权威材料：`【A10】…【金扬智能】.docx`（命题企业原始需求）、`参赛评分指南.doc`、`项目概要介绍_智绘学途 v1.0.docx`。

## 已归档、**不要据此实现**

| 文件 | 状态 | 已被推翻的内容 |
| --- | --- | --- |
| `规划目录/方案概要和解决方案/S2_解决方案_初稿.md` | **已归档** | 「React 前端」「2D / 3D 双模式」 |
| `规划目录/方案概要和解决方案/S1_方案概要_草稿.md` | 早期草稿 | 四大特色仍有效，但「前端 React，图谱渲染用 AntV G6 与 3d-force-graph」「特色（四）三维学习空间」均已过时 |

**现行决定：Vue 3 + TypeScript + Vite + AntV G6，仅 2D 图谱**，见 [ADR-001](decisions/ADR-001-vue3-g6-2d-graph.md) 与 AGENTS.md §1。3D 图谱在 AGENTS.md §1 的「不在本阶段实现」清单里。

冷启动的 Agent 读到旧稿里的 React 或 3D 时，不要据此改代码或改文档——那是被 ADR-001 推翻的历史方案。

## 参考项目（只读，不复制源码）

| 项目 | 本地位置 | 许可 | 用途 |
| --- | --- | --- | --- |
| neo4j-labs/llm-graph-builder | `规划目录/参考项目/llm-graph-builder` | Apache-2.0 | 处理流水线、图建模、检索 Cypher、SSE 进度 |
| HKUDS/LightRAG | `规划目录/参考项目/LightRAG` | MIT | 分块算法、提示词结构、图谱编辑接口 |

**规则**：只读源码，**不把源码复制进本仓库**。一旦实际借用，必须在同一次提交内按根目录 [`NOTICE`](../NOTICE) 的四项要求登记——具体文件路径、修改说明、保留上游版权与许可、补一条 ADR。Apache-2.0 要求保留版权声明并注明修改，这是参赛提交材料的合规项。

### 团队自撰的研究

`规划目录/参考项目/对照笔记.md` 是整套实现研究里价值最高的资产，**不含第三方源码**，已纳入版本控制：

→ [`docs/references/参考项目对照笔记.md`](references/参考项目对照笔记.md)

该副本开头标注了路径前提、项目旧名「知径」，以及三条已过时的结论。**原件更新后副本不会自动同步**，副本内记了原件内容的 sha256 前缀，用于判断是否已漂移。

## docx 更新后的同步检查清单

权威 docx 一改，下列仓库文件可能无声漂移。按章节对应关系逐项复核：

| S2 章节 | 需复核的仓库文件 |
| --- | --- |
| §3 功能清单、表 3.2 | `docs/product.md` 的 MVP 范围表、非目标清单 |
| §4.2 表 4.2 里程碑 | `docs/tasks/M0.md`、`docs/tasks/M1.md` 的截止日期与窗口对照 |
| §4.3.2 任务状态机 | [ADR-005](decisions/ADR-005-task-state-machine.md)、[ADR-006](decisions/ADR-006-implement-task-cancel.md)、`src/contracts/README.md` 的 SSE 章节 |
| §4.3.3 图谱发布状态 | `specs/teacher-review-publish.md` 的三态流转 |
| §6.1 表 6.1 技术栈 | AGENTS.md §1、`docs/architecture.md` |
| §6.3 表 6.5 业务数据表 | `docs/architecture.md` 核心数据模型 |
| §6.4.6 智能问答 | `specs/grounded-qa.md`、[ADR-003](decisions/ADR-003-answer-source-citation.md) |
| §6.4.7 学习路径推荐 | `specs/learning-path.md` 的候选集判定与评分公式 |
| §6.4.8 教师端图谱修正 | `specs/teacher-review-publish.md` |
| §6.5 表 6.6 主要接口 | `src/contracts/`（M0-04a 起）、`docs/tasks/M1.md` |
| §6.6 模型调用约束 | `.env.example`、`docs/integrations.md` 变量表 |
| §6.7 表 6.8 提示词清单 | `prompts/MANIFEST.md` 的 8 项 `id` 与用途 |
| §6.8 部署方案 | `docker-compose.yml`、`docs/integrations.md` 本地依赖环境 |
| §7 UI 界面 | `specs/` 各份的交互相关验收条件 |

复核完成后在对应的交接文件里记录「按 docx `<版本或日期>` 复核」，否则下一个人无从判断复核是否做过。

## 不在本仓库留存的东西

- 参考项目源码
- 权威 docx / PDF 本身
- 真实课程资料（见 `datasets/README.md` 与 D-01）
