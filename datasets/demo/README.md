# 示例课程包（K09，自编合成数据）

本目录是 SmartSketch 的**一键演示数据**包，由 `scripts/import-demo.py` 读取。

- **不是真实课程资料**：`documents/` 下的讲义正文与其中的知识点全部由本项目自编（合成素材），
  不含密钥、个人信息，也不是任何教材、课件或课程网站的摘录，可自由修改与分发。
- `manifest.json` 是唯一真源：`schema_version`、`notice`、`course`（课程名与描述）、`documents`
  （每条含相对路径 `path`、资料标题 `title`、格式 `format`、内容 `sha256`）。
- 导入脚本按 `course.name + title + sha256` 组成稳定幂等键：文件内容不变则重跑只跳过，
  内容变化则会作为一条新资料导入；`sha256` 与实际文件不一致时脚本在**写入任何数据之前**拒绝执行。
- 格式目前覆盖 2 种（Markdown、TXT），满足赛题「格式 ≥ 2 种」；PDF/DOCX 若要加入，
  在 `documents/` 放置真实可解析的文件并补一条记录即可，无需改脚本。

用法见 `docs/runbook`（K12 编写）与 `docs/tasks.md` 的 K09 小节。
