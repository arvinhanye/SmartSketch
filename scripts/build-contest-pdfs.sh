#!/usr/bin/env bash
# L11：把 datasets/contest 下的自编 Markdown 打印成文本型 PDF，并重写 manifest.json。
# 用本机 Chrome 无头打印（不新增依赖）；PDF 内嵌字体带 ToUnicode，供 pdfminer 提取中文。
# 用法：scripts/build-contest-pdfs.sh   可用 CHROME=<可执行文件> 指定浏览器、PYTHON= 指定解释器。
set -euo pipefail
cd "$(dirname "$0")/.."
chrome="${CHROME:-/Applications/Google Chrome.app/Contents/MacOS/Google Chrome}"
py="${PYTHON:-.venv/bin/python}"
[[ -x $chrome ]] || { echo "找不到 Chrome：${chrome}（用 CHROME= 指定）" >&2; exit 1; }
work="$(mktemp -d)"
cleanup() { rm -f -- "$work"/*.html; rmdir -- "$work" 2>/dev/null || true; }
trap cleanup EXIT

for md in datasets/contest/*/*.md; do
  html="$work/$(basename "${md%.md}").html"
  "$py" - "$md" "$html" <<'PY'
import html, re, sys
src, out = sys.argv[1], sys.argv[2]
body = []
for line in open(src, encoding="utf-8").read().splitlines():
    heading = re.match(r"^(#{1,3})\s+(.*)", line)
    if heading:
        level = len(heading.group(1))
        body.append(f"<h{level}>{html.escape(heading.group(2))}</h{level}>")
    elif line.startswith("> "):
        body.append(f"<blockquote>{html.escape(line[2:])}</blockquote>")
    elif line.strip():
        body.append(f"<p>{html.escape(line)}</p>")
style = ("body{font-family:'PingFang SC','Heiti SC',sans-serif;font-size:12pt;line-height:1.7;margin:0 8mm}"
         "h1{font-size:20pt;margin:0 0 12pt}h2{font-size:16pt;margin:16pt 0 8pt}h3{font-size:13.5pt;margin:12pt 0 6pt}"
         "blockquote{color:#555;margin:0 0 10pt}p{margin:0 0 8pt}")
with open(out, "w", encoding="utf-8") as handle:
    handle.write(f"<!doctype html><html lang='zh-CN'><meta charset='utf-8'><style>{style}</style><body>"
                 + "\n".join(body) + "</body></html>")
PY
  "$chrome" --headless=new --disable-gpu --no-pdf-header-footer --print-to-pdf="${md%.md}.pdf" \
    "file://$html" >/dev/null 2>&1
done

PYTHONPATH=src/backend "$py" - <<'PY'
import hashlib, json
from pathlib import Path
from app.workers.parse_task import _PARSERS

root = Path("datasets/contest")
documents = []
for path in sorted(root.glob("*/*")):
    if path.suffix not in (".md", ".pdf"):
        continue
    data = path.read_bytes()
    entry = {"path": path.relative_to(root).as_posix(), "bytes": len(data),
             "sha256": hashlib.sha256(data).hexdigest(), "source": "SmartSketch 项目自编"}
    if path.suffix == ".md":
        entry["content_type"] = "text/markdown"
        entry["chars"] = len(data.decode("utf-8"))
    else:
        entry["content_type"] = "application/pdf"
        doc = _PARSERS["pdf"](data)
        entry["pages"] = max(block.locator.page for block in doc.blocks)
    documents.append(entry)
manifest = {"schema_version": 1,
            "note": "L11 参赛演示与评测资料：两门课各一章，Markdown 为源，PDF 由 scripts/build-contest-pdfs.sh 生成。全部自编。",
            "courses": [{"key": "course1-ds-ch3", "name": "数据结构：栈与队列"},
                        {"key": "course2-os-ch2", "name": "操作系统：进程与线程"}],
            "documents": documents}
(root / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print("\n".join(f"{d['path']}: {d['bytes']} 字节" + (f"，{d['pages']} 页" if "pages" in d else f"，{d['chars']} 字")
                for d in documents))
PY
