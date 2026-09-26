# 交接：K02 真实模型抽取的人工判定与报告（Claude）

- 日期：2026-09-26
- 分支：`claude/project-thread-sp1d3a`，起于 `main@62834b2`（PR #257 合并后）
- 范围：把本机真实模型运行的结果计分、写入报告；不改代码、提示词、口径或金标。

## 交付物

- `evaluation/reports/extraction-accuracy.md`：第 2 节实测结论，第 3 节运行记录与 sha256，第 4 节 137 条逐条判定表，第 5 节错误类型与改进方向。
- `evaluation/reports/k02-live-20260926/judgments.json`：判定人 Arvinhan 的判定（`run_id = k02-live-20260926T084922Z`，种子 20260926）。
- `docs/tasks.md` K02 行与待决事项、`specs/course-knowledge-graph.md` 验收 7 注记。

## 输入

- 用户本机运行 `evaluation/run_live_extraction.py`（2026-09-26 08:49～08:54 UTC，请求与响应模型都是 `deepseek-flash`），上传 predictions.json、run.json、report.json、sample.json。这些文件含资料原文证据或属运行产物，不入库；sha256 记在报告第 3 节。
- 人工判定：Claude 做了一个判定页，逐条展示名称/类型、定义、原文证据、所属小节和金标对照，判定值由用户点选，未预填。首轮 137 条全判对且无备注；Claude 指出 5 条可能违反标准（p-e001 E2、p-e011/p-e019 E5/E3、p-r053/p-r055 R2），用户复核后只把 p-r053、p-r055 改判错。两条的 notes 由 Claude 按复核提示写为 R2，并在报告中注明。

## 验证

```bash
python evaluation/evaluate_extraction.py score --gold evaluation/fixtures/synthetic.json \
  --predictions <run>/predictions.json \
  --judgments evaluation/reports/k02-live-20260926/judgments.json --out report.json
```

- exit 0；`--out` 与标准输出两次结果 sha256 都是 `1f8f8e39…abd8`。
- `hard_indicators`：实体数 74、实体准确率 74/74、关系准确率 61/63（0.9683），`verdict = 达标`。
- 报告第 5 节里关于未命中原因的说法（跨小节 12/21、端点名称写法差异、`no_gold_match` 的类型分布、金标中递归两条边为 `RELATED_TO`）都用脚本对 report.json 的 `details` 与金标核对过。
- `./scripts/verify.sh` exit 0；`git diff --cached --check` exit 0；`test_k02.py` + `test_k02_run.py` 66 passed。

## 接口 / 数据变更

无。

## 风险

- 简化融合：只按 `normalize_name` 去重。完整融合（E08～E10）接入前，E12/F13 的 `merging` 也是直通（ADR-029），所以这是初步结论。
- 人工判定首轮全对、无备注。评审若要求判定依据，可参考报告第 4 节的逐条表和判定页记录。

## 下一步

1. 完整融合接入后，把本章处理到 `awaiting_review` 导出草稿，按报告第 3 节重新抽样判定。
2. 抽取改进见报告第 5 节：跨小节关系补抽、`CONTAINS` 与 `RELATED_TO` 的判别、截断小节拆批、是否把「基于」加入先修表述清单。
3. usage 实测（35 次调用都带 usage，计费 95858 token）可由协调方补到 `docs/integrations.md` D-02a 行。
