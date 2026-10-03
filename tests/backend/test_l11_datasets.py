"""L11：比赛自编资料可被 worker 实际使用的解析器读出中文、页码与章节（不经模型）。"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from app.services.parsers.pdf import PARSER_VERSION, normalize_ideographs

# worker 实际使用的分派表（src/backend/app/workers/parse_task.py）：pdf 走 提取 → 页眉页脚清洗 → 标题分节
from app.workers.parse_task import _PARSERS

ROOT = Path(__file__).resolve().parents[2] / "datasets" / "contest"
MANIFEST_PATH = ROOT / "manifest.json"


def _documents(suffix: str | None = None) -> list[dict]:
    documents = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))["documents"]
    return [d for d in documents if suffix is None or d["path"].endswith(suffix)]


def test_manifest_lists_both_courses_in_both_formats():
    paths = {d["path"] for d in _documents()}
    for course in ("course1-ds-ch3/ch3-stack-queue", "course2-os-ch2/ch2-process-thread"):
        assert {f"{course}.md", f"{course}.pdf"} <= paths


@pytest.mark.parametrize("item", _documents() if MANIFEST_PATH.exists() else [], ids=lambda d: d["path"])
def test_manifest_hash_and_size_match(item):
    data = (ROOT / item["path"]).read_bytes()
    assert hashlib.sha256(data).hexdigest() == item["sha256"]
    assert len(data) == item["bytes"]


@pytest.mark.parametrize("item", _documents(".pdf") if MANIFEST_PATH.exists() else [], ids=lambda d: d["path"])
def test_text_pdf_parses_to_chinese_with_pages_and_sections(item):
    doc = _PARSERS["pdf"]((ROOT / item["path"]).read_bytes())
    text = "".join(block.text for block in doc.blocks)
    assert ("栈" in text) or ("进程" in text)
    assert "(cid:" not in text
    assert {block.locator.page for block in doc.blocks} >= {1, 2}
    assert any(block.locator.section_titles for block in doc.blocks)
    assert item["pages"] == max(block.locator.page for block in doc.blocks)


@pytest.mark.parametrize("item", _documents(".md") if MANIFEST_PATH.exists() else [], ids=lambda d: d["path"])
def test_markdown_parses_with_sections(item):
    doc = _PARSERS["markdown"]((ROOT / item["path"]).read_bytes())
    assert len(doc.blocks) >= 20
    assert sum(1 for block in doc.blocks if block.locator.section_titles) >= len(doc.blocks) - 2


# ---- L11 阻断：macOS 字体的 ToUnicode 把部分汉字映射成康熙部首（U+2F00–U+2FD5）或部首补充（U+2E80–U+2EF3）。
# 外观相同、编码不同，检索、引用片段与模型输入都会受影响；提取层改回统一汉字（PDF 解析器 pdf/2）。

def _radicals(text: str) -> list[str]:
    return [ch for ch in text if 0x2E80 <= ord(ch) <= 0x2EFF or 0x2F00 <= ord(ch) <= 0x2FDF]


def test_normalize_ideographs_maps_radicals_and_keeps_everything_else():
    assert normalize_ideographs("项\u2f6c\u2f83编") == "项目自编"
    assert normalize_ideographs("\u2ec4风") == "西风"           # 部首补充 ⻄ → 西
    unchanged = "全角，标点（保留）ＡＢ１２ abc 栈"
    assert normalize_ideographs(unchanged) == unchanged         # 不做全量 NFKC


def test_pdf_parser_version_bumped_for_ideograph_normalization():
    assert PARSER_VERSION == "pdf/2"


@pytest.mark.parametrize("item", _documents(".pdf") if MANIFEST_PATH.exists() else [], ids=lambda d: d["path"])
def test_contest_pdf_text_has_no_radical_lookalikes(item):
    doc = _PARSERS["pdf"]((ROOT / item["path"]).read_bytes())
    text = "".join(block.text for block in doc.blocks)
    assert _radicals(text) == []
    assert "项目自编" in text
