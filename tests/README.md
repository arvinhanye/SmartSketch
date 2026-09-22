# 测试

按被测对象分目录，与 `src/` 的所有权边界一致：

| 目录 | 归属 | 被测对象 |
| --- | --- | --- |
| [`tests/backend/`](backend/) | Backend / Data-AI Agent | FastAPI 路由、领域服务、仓储、worker |
| [`tests/frontend/`](frontend/) | Frontend Agent | Vue 组件、composables、G6 适配层 |
| [`tests/contracts/`](contracts/) | Backend Agent | 契约真源与生成物的一致性、跨端字段约定 |

## 运行

测试运行器的配置分别属于 **M0-03**（后端）与 **M0-02**（前端），本目录只定目录与约定，不含 `pyproject.toml` / `package.json`。

两端初始化后，把实际命令接进 `scripts/verify/backend.sh` 与 `scripts/verify/frontend.sh` 已预留的调用点——不要改 `scripts/verify.sh` 本体（AGENTS.md §3「写争用规则」）。在那之前统一入口仍是：

```bash
./scripts/verify.sh
```

## 优先覆盖清单

`.claude/rules/testing.md` 要求优先覆盖以下六项。每项都必须有成功、边界与失败三条路径：

| # | 覆盖点 | 关键断言 | 主要落点 |
| --- | --- | --- | --- |
| 1 | 前置关系环检测 | 成环时写入被拒，并返回导致冲突的节点/关系 | `tests/backend/` |
| 2 | 课程隔离 | 任何查询与写入都带 `course_id`；跨课程读取返回空或 403，不泄漏 | `tests/backend/` |
| 3 | 抽取审核状态 | 草稿仅教师可编辑；低置信度项可审核；学生读不到未发布草稿 | `tests/backend/` |
| 4 | 来源引用 | 回答要么带至少一个可定位来源，要么返回 `NOT_COVERED`（ADR-003） | `tests/backend/` |
| 5 | SSE 任务状态转换 | 状态机按 ADR-005 推进；终态后不再发事件；取消请求后任务进入 `cancelled`，且对已终态任务取消返回明确错误码（ADR-006） | `tests/backend/`、`tests/frontend/` |
| 6 | 学习路径排序 | 推荐顺序满足前置依赖，且每条建议带可解释理由 | `tests/backend/` |

## 约定

- **Bug 先加可复现测试，再改实现**（`.claude/rules/testing.md`）。
- 文件名 `test_<被测单元>_<场景>.py` / `<被测单元>.spec.ts`；用例名写清「什么条件下期望什么」，不写 `test_1`。
- 不提交真实课程资料作为夹具。需要样本时用 `datasets/` 的脱敏标注集，或在用例内构造最小数据。
- 交接文件里记录**实际运行过的命令与结果**，不要只写「测试通过」。
