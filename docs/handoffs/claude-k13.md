# Claude 交接：K13 抽取消融实验（2026-09-26）

- 基线：`main@a44c680`，分支 `claude/project-thread-yswyz2`，issue #166。
- 状态：代码与 fake 测试完成；真实模型待 ArvinHan 在本机运行（开发云环境拦截 `api.deepseek.com`）。

## 交付物

- `evaluation/ablation.py`：三组消融编排，提供 `run` 和 `summarize` 两个子命令。
  - 单阶段组由本文件实现。
  - 两阶段组和补漏组调用 K02 `run_live_extraction.run`。
  - 汇总使用 `evaluate_extraction.score` 和 `sample`。
- `evaluation/prompts/extract_joint.yaml`：单阶段组专用提示词，不放 `prompts/`，不接入生产，因此不列入 `prompts/MANIFEST.md`。装载方式为 `PromptLibrary(evaluation/prompts)`。
- `tests/backend/test_k13.py`：22 项测试，只用 fake 模型。
- `evaluation/reports/ablation.md`：报告。包括方法、控制变量、预算和本机步骤；第 4 节等真实运行后回填。
- 扩围改动：
  - `docs/decisions.md` 新增 ADR-045，记录用户确认付费调用和单阶段定义；
  - `docs/integrations.md` 在 D-02d 行加备注；
  - `evaluation/README.md` 更新目录；
  - `docs/tasks.md` 新增 K13 行。

## 设计选择（Claude 选定，见 ADR-045）

1. **单阶段的定义**：每块一次调用，同时输出实体和块内关系。
   - 模型给出块内 ID（e1、e2……），脚本逐条走 E05 `_validate`，再映射到融合后的 ID。
   - 关系走 E11 `_validate`，校验内容为端点、证据、先修表述、方向、自环和重复。
   - 块内 ID 缺失或重复时，记 `invalid_local_id` 并丢弃。
2. **单阶段输出上限**：8192，即两阶段两类调用上限之和。
3. **补漏组**：只开 1 轮（`--glean-rounds` 可改）。
4. **预算**：
   - 单任务预算按组计。
   - 日预算按三组累计：每组开跑前，把剩余量作为该组的 `LLM_DAILY_TOKEN_BUDGET` 交给 E04。
   - 鉴权失败或记录预写失败时停止剩余组；预算拒绝只停当前组。
5. **写入保护**：`write_results` 先删掉组目录里上一次的 predictions，避免失败组被旧结果混读。

## 验证

- `python3 -m pytest tests/backend/test_k13.py -q`：22 passed。
- 5 处反向篡改都被检出，分别是：不扣日预算、不查重复块内 ID、不删旧 predictions、不停止鉴权失败、不停止剩余组。
- `python3 -m pytest tests/backend/test_k13.py tests/backend/test_k02_run.py tests/backend/test_k02.py tests/backend/test_e01.py -q`：157 passed。
- `LLM_MODE=fake python3 evaluation/ablation.py run --gold evaluation/fixtures/synthetic.json --out-dir <tmp>`：退出码 0，三组都是 ok，数字见报告第 5 节。
- `python3 -m pytest tests/backend -q`：2984 passed（1 条既有警告）。
- 按 CI 装好锁定契约工具后 `./scripts/verify.sh` exit 0；`git diff --check` 无输出。

## 接口与数据变更

无 API、契约、数据库或生产提示词变更。

## 风险与待决

- 结论只对简化融合成立，完整融合接入后需重跑。
- 三组人工判定工作量约为 K02 的三倍，报告以自动比对为主；是否补人工判定由 ArvinHan 决定。
- 两阶段组会调用 K02 私有辅助函数（`_check_stop`、`_count` 等）。以后 K02 重构时要同步修改本脚本，测试会发现断裂。

## 下一步

1. ArvinHan 在本机按报告第 6 节运行。
2. 回填报告第 4 节，把 K13 看板状态改为 DONE，并关闭 #166。
