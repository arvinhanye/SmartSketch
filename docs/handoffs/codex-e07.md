# E07 向量适配与维度检查交接

- 任务：E07；2026-09-25；负责人 Codex（数据与 AI）；基线 `main@a7a0be0`。
- 状态：DONE（两项审查 P2 已修复）；E07 16 passed、后端 1035 passed，项目 `verify.sh` exit 0。

## 交付与决定

- `src/backend/app/services/ai/embeddings.py`：`EmbeddingAdapter(settings, client, cache=...)` 注入 E02 `EmbeddingClient`，依 `EMBEDDING_BATCH_SIZE` 分批，传入 `EMBEDDING_DIMENSIONS`。输出有 `model`、`dimensions`、`space`、文本 SHA-256 与向量值的 `EmbeddedVector`；向量值不进入 `repr`。
- 全批次验证响应数量、显式模型、维度及有限数值，再原子写入该批缓存；异常为 `EmbeddingBatchError(batch_index, completed_count)`，原客户端错误保存在异常链中。方法不会返回不完整结果；已完成批次的缓存可供重试。
- 同一次 `embed` 调用先按 `(space, sha256(text))` 合并待计算文本，跨批重复只发给模型一次，再按原输入位置展开结果。`EmbeddingCache` 使用同一键，默认容量 1024 条，按最近使用顺序淘汰，超限后重算被淘汰文本；提供 `clear_space` 供后续离线重新向量化收尾清理。fake 空间为 `fake/<dimensions>`；在线/本地为 `real/<model>/<dimensions>`，同维度换模型不命中旧缓存，真实模型名为 `fake` 也不与 fake 模式碰撞。
- `tests/backend/test_e07.py`：在原有 12 个用例上增加同批去重、跨批去重、LRU 淘汰重算和非法容量 4 个回归用例。审查问题先由新增测试复现为 4 failed，再修复为 16 passed。
- `docs/architecture.md` 记录 E07 边界；`docs/tasks.md` 记录认领和验收。

## 验证

- `$env:PYTHONPATH=(Resolve-Path src/backend).Path; .\.venv\Scripts\python.exe -m pytest tests/backend/test_e07.py -q`：12 passed。
- 同一环境执行 `python -m pytest tests/backend -q`：最终复跑 1031 passed、2 warnings（均为上游测试客户端废弃提示）。
- 同一环境执行 `python -m pytest tests/backend/test_e02.py tests/backend/test_e07.py -q`：新增 `repr` 用例前 75 passed。
- `$env:PYTHONIOENCODING='utf-8'; .\.venv\Scripts\python.exe scripts/check_contracts.py`：PASS。
- 同一编码环境执行 `python -m pytest tests/contracts/test_b08.py tests/contracts/test_b09.py tests/contracts/test_b10.py tests/contracts/test_b12.py tests/contracts/test_b13.py -q`：201 passed。
- 在 Git Bash 内设置 `PATH="$PWD/.venv/Scripts:$PWD/src/frontend/node_modules/.bin:$PATH"`，并设置 `SMARTSKETCH_BASH=E:\软件\Git\bin\bash.exe` 后运行 `.venv/Scripts/python.exe -m pytest tests/contracts -q`：255 passed。
- 通过 `E:\软件\Git\bin\bash.exe`，在 Bash 内设置相同 `PATH` 后运行 `./scripts/verify.sh`：exit 0；hook 测试、契约静态检查、生成物一致性、门禁负向测试 24 项和 B08/B09/B10/B12/B13 均通过。该 Git Bash 不在系统 `PATH`，直接调用 `bash` 会失败。
- `git diff --check`：最终代码和文档编辑后 exit 0（Git 仅提示 Windows 的 LF/CRLF 转换）。

### 审查 P2 修复复验（2026-09-25）

- `$env:PYTHONPATH=(Resolve-Path src/backend).Path; .\.venv\Scripts\python.exe -m pytest tests/backend/test_e07.py -q`：16 passed；新增 4 例在实现前为 4 failed、12 passed。
- 同一环境执行 `python -m pytest tests/backend -q`：1035 passed、2 warnings（测试客户端废弃提示）。
- Git Bash 中将 `.venv/Scripts`、前端 `node_modules/.bin`、契约工具 shim 和 Git Bash 自身的 `usr/bin`/`bin` 加入 `PATH` 后运行 `./scripts/verify.sh`：exit 0；生成物一致性、门禁负向 24 项及 B08/B09/B10/B12/B13 均通过。
- 有限 LRU 只保证单进程内存不会随唯一文本数无限增长；被淘汰文本在后续调用中重新计算，跨进程重启仍会清空。

## 接口、风险与下一步

- 新增内部 Python 接口，无 REST、数据库、环境变量或依赖变更。E03 将在线/本地 `EmbeddingClient` 注入该适配层；F03 写 Neo4j 前仍须按自身上下文核对 `EmbeddedVector.space`，不能只核对维度。F14 在切换完成后调用 `clear_space` 清理旧空间缓存；本缓存为进程内缓存，进程重启时自然清空。
- 当前工作区同时有 C03 未提交改动；本任务未编辑 C03 的源码或测试。`docs/tasks.md` 与 `docs/architecture.md` 的 E07 段落是在 C03 已有改动上增补，集成时保留两者。
- 无需迁移或破坏性回滚。仅回退 E07 自有代码、测试和文档段落即可。
