# Codex 交接：J02 图结构检索

- task_id: J02
- 状态：实现完成；真实 Neo4j 验收待补
- 负责人：Codex（后端）

## 交付物与决定

- `src/backend/app/repositories/graph_search.py`：接收由 G07 绑定对象生成的 `GraphScope`，按课程与发布版本查询术语/知识点种子，逐跳扩展四类结构关系，按 `kp_id` 稳定截断节点并限制输出关系。硬上限为 2 跳、32 节点、128 关系，可向下调整；未知知识点 ID 忽略，无匹配为空结果。
- `tests/integration/test_j02.py`：参数边界与请求作用域测试；隔离 Neo4j 真实查询测试覆盖双向邻接、原始方向、课程/版本隔离、空命中与上限。
- `specs/grounded-qa.md`：补 J02 检索语义及上限。`docs/tasks.md`：认领、输入输出依赖风险与证据。
- 图子图只作 J04 的无编号结构上下文，不作为可引用来源。调用方负责鉴权并在请求入口绑定版本一次。

## 验证

- 实现前：定向测试因 `app.repositories.graph_search` 不存在而收集失败。
- `.venv/Scripts/python.exe -m pytest tests/integration/test_j02.py -q`：2 passed、3 skipped；跳过项需要 `SMARTSKETCH_TEST_NEO4J_URI/USER/PASSWORD`。
- `.venv/Scripts/python.exe -m py_compile src/backend/app/repositories/graph_search.py tests/integration/test_j02.py`：exit 0。
- 原工作区 `.venv/Scripts/python.exe -m pytest tests/backend -q`：3100 passed、1 failed（173.33s）；失败为 `tests/backend/test_e03.py::test_stdlib_transport_connection_refused`，预期 `ModelConnectionError`，实际 `ModelTimeoutError`。该项也在此前 I01 交接中记录。
- 隔离分支在旧基线复跑后端测试并排除上述 E03：3095 passed、1 deselected（156.06s）；rebase 到最新 `origin/main` 后重跑为 3101 passed、1 deselected（170.81s），J02+I01+G02 定向 30 passed、3 skipped。`PYTHONPATH` 指向隔离分支的 `src/backend`。`tests/integration/test_j02.py` 再次为 2 passed、3 skipped。`git diff --check` exit 0。`graph_search` 已改为只依赖仓储层 `GraphScope`。
- Git Bash `./scripts/verify.sh`：exit 1，`python3` 不存在；临时映射 Python 后仍 exit 1，缺 `datamodel-codegen`，B14 的临时仓库找不到映射解释器，部分契约脚本在 GBK 输出下发生 `UnicodeEncodeError`。
- `git diff --check`：exit 0（仅行尾转换警告）。

## 接口、风险、下一步

- 新增仓储函数 `search_graph(repo, scope, *, term="", kp_id=None, max_hops=2, max_nodes=32, max_edges=128) -> GraphSearchResult`；无 API、数据迁移或配置变更。
- 真实 Neo4j 查询未在此 Windows 环境执行。下一位 Agent 的首个动作：配置隔离 Neo4j 三个测试环境变量，运行 `tests/integration/test_j02.py`，再由 J04 接入同一请求绑定的版本对象。
- 本任务无破坏性修改；回滚仅删除本任务新增的仓储与测试文件，并撤销本任务在规格/任务板的增量。不要回退其他成员的未提交改动。
