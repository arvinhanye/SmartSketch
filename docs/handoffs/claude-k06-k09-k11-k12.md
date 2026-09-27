# 交接：K06 / K09 / K11 / K12 与演示模型（Claude）

- 分支：`claude/project-thread-sa7c37`，基线 `main@adbe106`
- 日期：2026-09-27
- Issues：#145（K06）、#148（K09）、#150（K11）、#151（K12）

## 交付物

| 项 | 文件 |
| --- | --- |
| 课程详情路由 | `src/backend/app/api/courses.py`（`GET /courses/{cid}`）、`services/courses.py::course_detail`、`tests/backend/test_course_detail.py` |
| 版本面板修复 | `src/frontend/src/composables/useVersions.ts`（`published_version` 缺省视为从未发布）、`tests/frontend/h10.test.ts` |
| 演示模型（ADR-076） | `src/backend/app/services/ai/demo.py`、`factory.py`、`embeddings.py`、`config.py`；`tests/backend/test_demo_mode.py`、`tests/integration/test_demo_mode_live.py`；`docs/handoffs/claude-demo-model-mode.md` |
| 端到端运行器 | `scripts/e2e.sh`、`playwright.config.ts`、`tests/e2e/{fixtures,api}.ts` |
| K06 | `tests/e2e/student.spec.ts` |
| K09（ADR-078） | `datasets/demo/`、`src/backend/app/services/demo_import.py`、`scripts/import-demo.py`、`tests/backend/test_k09.py`、`tests/integration/test_k09.py` |
| K11（ADR-077） | `scripts/verify.sh`、`scripts/verify/{gate.py,allowed-skips.txt,backend.sh,frontend.sh,integration.sh}`、`tests/tooling/test_k11.py`、`.github/workflows/ci.yml`（新增 integration job） |
| K12 | `docs/runbook.md`、`docs/acceptance.md` |

## 验证（本机 Linux 容器实跑）

```bash
./scripts/verify.sh full                          # exit 0：后端 3532 passed / 27 登记跳过；前端 751 passed；构建通过
scripts/verify/integration.sh                     # exit 0：集成 392 passed / 4 登记跳过；F11 44 passed；端到端 2 passed
scripts/e2e.sh tests/e2e/student.spec.ts          # 1 passed
scripts/e2e.sh tests/e2e/teacher.spec.ts          # 1 passed
python scripts/import-demo.py                     # 两次：第二次无变化
.venv/bin/python -m pytest tests/tooling/test_k11.py -q   # 18 passed
```

## 接口 / 数据变更

- 新增 `GET /api/v1/courses/{cid}`（契约早已声明 `getCourse`，此前缺实现）。
- `Course.kp_count` 现在填写为当前发布版本的 `node_count`（契约早已声明，此前从未填写）；从未发布的课程省略。
- 新配置取值：`LLM_MODE=demo`、`EMBEDDING_MODE=demo`；演示向量空间 `real/smartsketch-demo-ngram-v1/1024` 与其他空间不可共库。
- `tests/integration/test_k10.py` 的子进程改用实际 Neo4j 账号（此前硬编码 `x`，在非默认口令的库上失败）。

## 风险

- 演示模型只证明链路，不代表抽取质量；问答阈值 0.58 仅对演示向量有效。
- CI integration job 首次在 GitHub runner 上运行，需拉 Neo4j 镜像与 Playwright 浏览器。
- K08 容器方式仍未在真实守护进程验证。

## 下一步 / 需人工

1. 签收 ADR-076、077、078；决定 D-08。
2. 问答页「涉及的知识点」显示原始 ID 且数量过多、出处显示文档 ID：需前端任务改为名称与文件名。
3. 本机（macOS）按 `docs/runbook.md` 第 2、4 节跑一遍；真实模型重跑 K02 验收 7、K04。
