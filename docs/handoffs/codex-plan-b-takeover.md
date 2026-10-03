# Codex 接手计划 B：完成记录

```text
date: 2026-10-03
base: c85ee536cce9402b4c8e2d1d405be9e20ee3ab7d
branch: codex/plan-b-takeover
worktree: /Users/arvinhan/.codex/worktrees/plan-b-takeover/SmartSketch
status: 本地修复、L15、完整门禁完成；真实模型测量已交 DeepSeek 待执行
review: docs/reviews/codex-plan-b-c85ee53.md
```

## 交付

复审 5a34fec..56610d4 的16提交；c85ee53仅是交接/门禁文档提交。修复推荐按钮序号、已掌握后继误报解锁、QA画布挂载与自动推荐覆盖、长来源重复全文、显式0.5误报未标注，及最终审查发现的换号建课结果污染。正式回归分别先红后绿。没有降低原学生E2E断言。

完成L15课程角色导航、概览阶段与主动作、学生用户名入课空态、跨课权限/发布版/文件名边界/恶意文本、双课程个人模式E2E。保留原次要链接。增加SPA切课迟到问答正文、出处及历史隔离回归；后端隔离及恶意文本已有行为作为回归固化。

ADR-086：按用户批准的调高方向与交接建议，定稿QA输出2048；改写仍300；不放宽逐句出处、D1终态与D3统一15秒截止。ADR-087：可选importance_defaulted/difficulty_defaulted由原属性缺失计算，旧响应缺字段显示数值；无数据库迁移、依赖升级。契约真源及Python/TypeScript/OpenAPI生成物同步。领域层分层不变。基础设施和个人凭据规则沿用ADR-080，未新增服务。

## 最终整体验证

```bash
env -u VERIFY_NEO4J_URI -u VERIFY_NEO4J_USER -u VERIFY_NEO4J_PASSWORD \
  -u LLM_MODE -u EMBEDDING_MODE -u E2E_NEO4J_URI -u E2E_LLM_MODE -u E2E_EMBEDDING_MODE \
  PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$PWD/src/backend" PYTHON=.venv/bin/python \
  PATH="$PWD/.venv/bin:$PWD/node_modules/.bin:$PATH" \
  E2E_API_PORT=18500 E2E_WEB_PORT=15673 E2E_NEO4J_PORT=18188 E2E_PROVIDER_PORT=19390 VERIFY_NEO4J_PORT=18189 \
  PLAYWRIGHT_CHROMIUM_EXECUTABLE='/Applications/Google Chrome.app/Contents/MacOS/Google Chrome' \
  ./scripts/verify.sh integration
```

**实际整体exit0**，日志 /private/tmp/plan-b-integration-verified.log：

| 阶段 | 实际结果 |
| --- | --- |
| 基础/契约/生成一致性 | PASS，32路径/129schema/385引用；负向门禁25项 |
| 后端+工具全量 | 3780 passed、27已登记skip |
| 前端 | 37文件901 passed，type-check/build exit0 |
| Neo4j集成 | 393 passed、4已登记skip |
| 图库后端 | 44 passed |
| 演示端到端 | 2 passed（teacher/student） |
| 个人模式假供应商 | 4 passed（闭环、取消重传、错误key、双课程隔离） |
| 格式检查 | git diff --check exit0 |

最后端到端目录：.e2e/20261003-140306、.e2e/20261003-140422，包含服务日志和Playwright报告，均不入库。没有未登记skip。已有FastAPI弃用告警与G6打包体积告警保留，不为此升级依赖。

独立D/N回归：
- 后端 `test_d1.py test_d2.py test_d3.py test_n01_n06.py test_n07_n08.py test_e12.py`：116 passed/exit0。
- 前端 `d1-d3.test.ts n03-n05.test.ts h02.test.ts`：107 passed/exit0。
- D1逐句出处/截断分类PASS；D2本地记账与发布集成PASS（真实在线向量待实测）；D3deadline和传输边界PASS；N01/N06配置身份竞态PASS；N02鉴权终止PASS；N03会话、N04清除、N05防重PASS；N07存储门禁/N08模型名校验PASS。

中间失败如实登记：第一次显式demo向量影响test_b06默认fake断言，中止exit143并清理本人容器；第二次唯一失败是test_i05旧字段集合断言，同步新增两字段的明确false后仍保留精确断言，I05+l14 41 passed；第三次整体验证exit0，不用拼接多次结果冒充完整通过。未增加skip、删除测试或回退他人改动。

## 范围保留、下一步、回滚

Codex本轮没有真实生成模型/线上向量调用。L11-7 PDF真实复测未到；两课各5题、2048成功率/首字/完整耗时/费用、在线向量记账只交DeepSeek，见codex-plan-b-deepseek-qa.md。最新已知生成累计619217/5000000，开跑前更新并确认预算。历史抽取未达60秒、准确率未人工评估，不宣称赛题全达标。

次要延期：教师未保存修改时搜索视口与选中一致性；问答引用全文折叠统一；远处解锁点可见性；同章PDF+MD跨任务重复融合不在本期。最终审查只进行一轮，重要发现正式补测修复，次要项留账本，不反复审查循环。

旧Codex checkout有早期基线和文档改动，保留；从c85ee53新建本托管工作树，不修改Claude checkout。复用Claude虚拟环境（PYTHONPATH始终指向本worktree源码），复制现有node_modules，没有复制.env/数据库/个人密钥。修复仅保存本地codex分支，不推送、不合并、不快进冲刺分支。

下一位首个动作：读本报告和真实测量交接，取得L11-7最新报告与预算，再由用户安排测量checkout同步。使用已有两门Markdown发布课，避免重复抽取。不把旧冲刺5a34fec当2048修复版本测量。

回滚：在本分支对本轮修复提交执行git revert并重新生成契约/跑integration；不reset或clean其他工作树。没有数据迁移需撤回。若真实2048延迟或费用不理想，由用户重新决定上限，再同步ADR/规格；保持出处校验和统一截止。
