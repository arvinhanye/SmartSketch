"""L11-7：PDF 段落合并——自动换行的续行并回同一段，句子不再被换行切断（ADR-084，解析器 headings/2）。

L11-6 真实模型实测：Chrome 打印的 PDF 经版面分析后几乎一行一个文本框，原先一行就是一块（同章 PDF 114 块、
平均 38 字，Markdown 37 块、平均 119 字），「学习 X 之前需要先掌握 Y」这类先修句式被换行拆开，
PDF 课程抽不出 PREREQUISITE、repair 激增。续行判定只用版面几何，不改标题判定与页码定位。
"""
from __future__ import annotations

import logging
from pathlib import Path

import pytest

from app.services.parsers.pdf import PdfLine
from app.services.parsers.pdf_headings import HEADINGS_VERSION, to_sectioned_document
from app.workers.parse_task import _PARSERS

ROOT = Path(__file__).resolve().parents[2] / "datasets" / "contest"
RIGHT = 556.0


def line(index: int, text: str, *, y1: float, x1: float = RIGHT, box: int | None = None, page: int = 1,
         size: float = 12.0, x0: float = 50.0) -> PdfLine:
    return PdfLine(page=page, index=index, box=index if box is None else box, text=text, font_name="PingFang",
                   font_size=size, bold=False, bold_ratio=0.0, x0=x0, y0=y1 - size, x1=x1, y1=y1)


def blocks(lines: list[PdfLine]) -> list[str]:
    return [block.text for block in to_sectioned_document(lines).blocks]


def test_wrapped_lines_in_separate_boxes_join_into_one_paragraph_without_newline():
    # 满行 + 正常行距（8pt）+ 左对齐 → 续行；中文之间直接相连
    lines = [
        line(0, "学习本章之前需要先掌握线性表的顺序存储与链式存储，因", y1=700),
        line(1, "为栈和队列的两种实现方式都直接沿用这两种存储结构。", y1=680, x1=400),
    ]
    assert blocks(lines) == ["学习本章之前需要先掌握线性表的顺序存储与链式存储，因为栈和队列的两种实现方式都直接沿用这两种存储结构。"]


def test_paragraph_gap_starts_a_new_block():
    lines = [
        line(0, "第一段的最后一行，写满到右边界附近的文字", y1=700),
        line(1, "第二段第一行。", y1=672),          # 行距 16pt ≈ 1.3 倍字号：段落之间
    ]
    assert blocks(lines) == ["第一段的最后一行，写满到右边界附近的文字", "第二段第一行。"]


def test_short_last_line_ends_the_paragraph_even_with_tight_spacing():
    lines = [
        line(0, "段尾短行。", y1=700, x1=200),
        line(1, "下一段紧挨着开始。", y1=680),
    ]
    assert blocks(lines) == ["段尾短行。", "下一段紧挨着开始。"]


def test_latin_words_are_joined_with_a_space():
    lines = [
        line(0, "A stack is a linear list that only allows", y1=700),
        line(1, "insertion and deletion at one end.", y1=680, x1=300),
    ]
    assert blocks(lines) == ["A stack is a linear list that only allows insertion and deletion at one end."]


def test_indented_or_resized_lines_are_not_continuations():
    lines = [
        line(0, "正文满行，后面跟着一个缩进的列表项或代码", y1=700),
        line(1, "  1. 缩进的列表项", y1=680, x0=80, x1=300),
        line(2, "不同字号的说明文字", y1=664, size=9.0, x1=300),
    ]
    assert len(blocks(lines)) == 3


def test_same_box_non_continuation_keeps_the_line_break():
    # 同一文本框内的短行（如列表、诗行）仍按原样以换行连接，不被并成一行
    lines = [
        line(0, "正文满行，写满到右边界附近的一段说明文字", y1=740),
        line(1, "第一项", y1=700, x1=120, box=1),
        line(2, "第二项", y1=680, x1=120, box=1),
    ]
    assert blocks(lines) == ["正文满行，写满到右边界附近的一段说明文字", "第一项\n第二项"]


def test_lines_never_join_across_pages():
    lines = [line(0, "页末满行的文字，后面接下一页", y1=60, page=1), line(0, "下一页开头。", y1=760, page=2, x1=200)]
    assert len(blocks(lines)) == 2


def test_headings_version_bumped():
    assert HEADINGS_VERSION == "headings/2"


@pytest.mark.parametrize("path", ["course1-ds-ch3/ch3-stack-queue.pdf", "course2-os-ch2/ch2-process-thread.pdf"])
def test_contest_pdf_paragraphs_are_whole_and_block_count_close_to_markdown(path):
    logging.disable(logging.WARNING)
    try:
        pdf_doc = _PARSERS["pdf"]((ROOT / path).read_bytes())
        md_doc = _PARSERS["markdown"]((ROOT / path.replace(".pdf", ".md")).read_bytes())
    finally:
        logging.disable(logging.NOTSET)
    assert len(pdf_doc.blocks) <= len(md_doc.blocks) * 1.5          # 原先约 3 倍
    texts = [block.text for block in pdf_doc.blocks]
    assert not any("\n" in text for text in texts)                  # 正文段落里没有换行切断
    if "ch3" in path:
        assert any("学习本章之前需要先掌握线性表的顺序存储与链式存储，因为栈和队列" in text for text in texts)
    else:
        assert any("学习本章之前需要先掌握程序的执行过程与中断机制" in text for text in texts)
    assert all(block.locator.page and block.locator.page >= 1 for block in pdf_doc.blocks)
