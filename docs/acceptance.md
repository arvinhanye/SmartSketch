# SmartSketch 验收矩阵（K12）

每行指向可复查的真实证据：自动化用例（文件路径）、端到端步骤或报告。**「演示模型」**指 `LLM_MODE=demo`（ADR-076，规则抽取、无付费调用）；它证明链路可用，不证明抽取质量。运行方法见 [runbook.md](runbook.md)。

最近一次完整验证：2026-09-27，Linux（云端容器），分支 `claude/project-thread-sa7c37`。

| 命令 | 结果 |
| --- | --- |
| `./scripts/verify.sh full` | 通过：后端 3532 passed / 27 skipped（均为登记的「需一次性 Neo4j」），前端 22 files / 751 passed，构建通过 |
| `scripts/verify/integration.sh` | 通过：集成 392 passed / 4 登记跳过，F11 图库 44 passed，端到端 2 passed |
| `scripts/e2e.sh tests/e2e/teacher.spec.ts` | 1 passed（K05） |
| `scripts/e2e.sh tests/e2e/student.spec.ts` | 1 passed（K06） |
| `python scripts/import-demo.py`（两次） | 第一次建课、上传、发布 v1；第二次 `uploaded: []`、`publish_unchanged: true` |

## 教师主线

| 能力（`docs/product.md`） | 验收点 | 证据 | 状态 |
| --- | --- | --- | --- |
| 资料导入 | 四种格式上传、任务状态可见、失败可重试 | K05 `tests/e2e/teacher.spec.ts`（txt/md/pdf/docx 全部到「待审核」；首传网络失败后重试成功）；`tests/backend/test_c06.py`、`test_c07.py`、`test_d02.py`–`test_d05.py` | 通过（演示模型） |
| 异步处理进度 | 解析→抽取→融合→持久化→待审核，SSE 推送 | `tests/backend/test_c08.py`–`test_c11.py`、`tests/integration/test_f13.py`；K05 等待页面状态变为「待审核」 | 通过 |
| 图谱构建 | 四类关系、课程隔离、前置无环 | `tests/backend/test_e11.py`、`test_f05.py`；`tests/integration/test_demo_mode_live.py`（草稿图非空、PREREQUISITE 无环） | 通过（融合为简化版，D-08 待定） |
| 教师审核 | 编辑节点/关系、成环拒绝、低置信度队列 | K05（添加前置关系成功，反向添加提示「前置关系会形成环路」）；`tests/backend/test_f08.py`、`test_f11.py`、`test_relations_api.py`；`tests/frontend/h07.test.ts`、`h09.test.ts`、`h14.test.ts` | 通过 |
| 发布与回滚 | 发布版本、学生可见、回滚为前滚新版本 | K05（发布后「学生当前看到 v1」，学生页显示 v1）；`tests/backend/test_g06.py`、`tests/integration/test_g05.py`；`tests/frontend/h10.test.ts` | 通过 |
| 课程详情 | 课程页加载课程信息；课程卡片显示已发布版本的知识点数 | `tests/backend/test_course_detail.py`（本轮补上 `GET /courses/{cid}`，此前课程页恒显示「课程加载失败」；`kp_count` 此前从未填写，卡片恒为「知识点：0」） | 通过 |

## 学生主线

| 能力 | 验收点 | 证据 | 状态 |
| --- | --- | --- | --- |
| 浏览已发布图谱 | 只见已发布版本，2D 图谱、卡片、详情、来源 | K06 `tests/e2e/student.spec.ts`（v1、图谱、卡片视图）；`tests/frontend/h04.test.ts`–`h06.test.ts`、`h11.test.ts` | 通过 |
| 草稿不可见、旧版稳定 | 教师改草稿后学生仍见 v1 原名 | K06 第 3 步 | 通过 |
| 跨课程拒绝 | 非成员课程页面与接口均拒绝 | K06 第 4 步（页面不渲染，`GET /graph` 403）；`tests/backend/test_c03.py` | 通过 |
| 掌握标记与推荐 | 标记后推荐按服务端刷新，理由来自服务端 | K06 第 2 步（已掌握项从推荐中消失，刷新后进度仍为 mastered）；`tests/backend/test_i02.py`–`test_i05.py`；`tests/frontend/i06.test.ts` | 通过 |
| 可信问答 | 回答带可点击出处；未覆盖时显示「资料未覆盖」且无引用 | K06 第 5、6 步；`tests/backend/test_j03.py`–`test_j07.py`、`test_j10.py`；`tests/frontend/j08.test.ts`、`j09.test.ts` | 通过（演示模型） |

## 运维与数据

| 能力 | 证据 | 状态 |
| --- | --- | --- |
| 示例课程幂等导入（K09） | `tests/backend/test_k09.py`（9 例：重跑不重复、失败可重试、只写示例课、替换资料被拒）；`tests/integration/test_k09.py`（真实 worker + 发布 + 重跑） | 通过 |
| 质量门禁（K11） | `tests/tooling/test_k11.py`（18 例：零测试、失败、未登记跳过、模式隔离、未知模式）；CI 四个 job | 通过 |
| 备份与恢复（K10） | `tests/integration/test_k10.py` | 通过（集成档） |
| 容器部署（K08） | `tests/integration/test_k08.py` 静态检查通过；镜像构建用例在门禁中登记为跳过 | **未在真实守护进程验证** |

## 未满足或待人工

| 项 | 说明 | 需要谁 |
| --- | --- | --- |
| 抽取质量硬指标 | 以 K02 真实模型判定为准（74 实体，61/63 关系达标，简化融合）；接入完整融合后需重跑 | 用户（付费调用、D-08 阈值） |
| 真实模型性能 | K04 仅有假模型数据，真实首字/总时延需本机付费运行 | 用户 |
| macOS / Windows | 未实测 | 用户本机 |
| 容器方式 | `docker compose --profile app up` 未在真实守护进程跑通 | 用户本机 |
| 问答页「涉及的知识点」 | 显示原始 `kp_…` 标识而非名称，且一次列出数十个；出处显示文档 ID 而非文件名（J09 页面遗留） | 后续前端任务 |

## 集成档

`scripts/verify/integration.sh` 在一次性 Neo4j 5.26 上运行 `tests/integration` 与 F11 图库用例，再跑两条端到端。2026-09-27 结果：`tests/integration` 392 passed、4 skipped（均为白名单登记的 Docker 用例）；`tests/backend/test_f11.py` 44 passed；K05、K06 端到端 2 passed。
