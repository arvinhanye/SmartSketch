# K04 交接

- 基线：`origin/main` 已包含 J07（PR #293）。K04 PR #296 的 SSE 审查意见已按 `meta → delta* → done/error` 修正；首个有效 `delta` 计首字时延，`done/error` 计完整响应时延。
- 定向测试限于正常 SSE、error SSE、p50/p95 三项，`pytest tests/backend/test_k04.py -q`：3 passed；`git diff --check` 通过。报告保留机器、抽取/问答模型、并发、样本数与目标/实测的分列。
- `verify.sh` 在本机未通过：Git Bash 初始缺 `python3`，映射项目虚拟环境后契约门禁又遇 Windows GBK 输出错误和缺少锁定的 `datamodel-codegen`。未修改与 K04 无关的契约工具链。
- 实际测量：**尚未执行**。当前机器无运行中的 Neo4j、课程 API 或 Docker，也无可用测试课程；没有生成或伪造 p50/p95。等待测试环境后，以一个模型、并发 1、约 5 个实际样本运行。付费模型调用仍需另行确认。
- 原始样本由 `evaluation/benchmark_pipeline.py fixture --out <path>` 从自编章节确定性生成，约 2 万字。`run` 的输出应保存为本次报告，记录实际环境与模型模式；假模型结果须明确标记，不能当真实模型性能。
