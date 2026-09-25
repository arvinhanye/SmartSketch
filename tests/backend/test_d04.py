"""D04：DOCX 段落与表格解析（`app.services.parsers.docx`）。

测试用 DOCX 全部在测试里用 `zipfile` 拼装到 `tmp_path`，不入库、不引入测试依赖。

覆盖三类路径：
- 成功：多级标题（英文样式 ID、中文 Word 内置样式、basedOn 继承、段落直接 outlineLvl、
  无 styles.xml 时的样式 ID 兜底）、标题前正文「第N段」、表格块与单元格保序、列表合并、
  修订/超链接/内容控件中的文字、嵌入内容的处理范围、Strict 命名空间、`parser_version`。
- 边界：空段落与只有分页符的段落跳过、同名标题接续编号、标题跳级、合并单元格与嵌套表、
  标题规范化（空白、半角 `>`）、显示名为「标题 1」但无大纲级别的样式不算标题、outlineLvl 9。
- 失败：非 zip、截断 zip、缺 `word/document.xml`、坏 XML、根元素不对、DOCTYPE/实体炸弹、
  解压后超限、OLE 加密包、旧版 .doc、zip 条目加密、空文档/只有标题/只有图片、非 bytes 输入。
"""

from __future__ import annotations

import struct
import zipfile
from pathlib import Path

import pytest

from app.services.parsers import (
    BlockKind,
    DocumentUnreadableError,
    ParsedDocument,
    SourceFormat,
    UnreadableReason,
)
from app.services.parsers import docx as docx_parser
from app.services.parsers.docx import PARSER_VERSION, parse_docx

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
STRICT_W_NS = "http://purl.oclc.org/ooxml/wordprocessingml/main"
NS_DECL = (
    f'xmlns:w="{W_NS}" '
    'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" '
    'xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing" '
    'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
    'xmlns:mc="http://schemas.openxmlformats.org/markup-compatibility/2006" '
    'xmlns:wps="http://schemas.microsoft.com/office/word/2010/wordprocessingShape" '
    'xmlns:v="urn:schemas-microsoft-com:vml" '
    'xmlns:o="urn:schemas-microsoft-com:office:office" '
    'xmlns:m="http://schemas.openxmlformats.org/officeDocument/2006/math"'
)

CONTENT_TYPES = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
    '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
    '<Default Extension="xml" ContentType="application/xml"/>'
    '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
    "</Types>"
)
ROOT_RELS = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
    '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>'
    "</Relationships>"
)

# 英文版 Word：样式 ID 为 HeadingN，样式内带 outlineLvl。
EN_STYLES = [
    ("Normal", "Normal", None, None),
    ("Heading1", "heading 1", "Normal", 0),
    ("Heading2", "heading 2", "Normal", 1),
    ("Heading3", "heading 3", "Normal", 2),
]
# 中文版 Word：样式 ID 为 1、2、3（正文为 a），界面显示名是「标题 1」，靠 outlineLvl 判定。
ZH_STYLES = [
    ("a", "Normal", None, None),
    ("1", "heading 1", "a", 0),
    ("2", "heading 2", "a", 1),
    ("3", "heading 3", "a", 2),
]


# ---------------------------------------------------------------- 构造工具


def esc(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def run(text: str) -> str:
    return f'<w:r><w:t xml:space="preserve">{esc(text)}</w:t></w:r>'


def para(text: str = "", style: str | None = None, outline: int | None = None, inner: str = "") -> str:
    ppr = ""
    if style is not None or outline is not None:
        ppr = "<w:pPr>"
        if style is not None:
            ppr += f'<w:pStyle w:val="{style}"/>'
        if outline is not None:
            ppr += f'<w:outlineLvl w:val="{outline}"/>'
        ppr += "</w:pPr>"
    return f"<w:p>{ppr}{run(text) if text else ''}{inner}</w:p>"


def list_para(text: str, num_id: int = 1, ilvl: int = 0) -> str:
    return (
        f'<w:p><w:pPr><w:pStyle w:val="ListParagraph"/><w:numPr><w:ilvl w:val="{ilvl}"/>'
        f'<w:numId w:val="{num_id}"/></w:numPr></w:pPr>{run(text)}</w:p>'
    )


def cell(*paragraphs: str, props: str = "") -> str:
    body = "".join(paragraphs) or "<w:p/>"
    tcpr = f"<w:tcPr>{props}</w:tcPr>" if props else ""
    return f"<w:tc>{tcpr}{body}</w:tc>"


def table(*rows: list[str]) -> str:
    trs = "".join("<w:tr>" + "".join(cells) + "</w:tr>" for cells in rows)
    return f"<w:tbl><w:tblPr/><w:tblGrid/>{trs}</w:tbl>"


def text_cell(text: str) -> str:
    return cell(para(text))


def styles_xml(styles, extra: str = "") -> str:
    parts = []
    for style_id, name, based_on, outline in styles:
        xml = f'<w:style w:type="paragraph" w:styleId="{style_id}"><w:name w:val="{name}"/>'
        if based_on is not None:
            xml += f'<w:basedOn w:val="{based_on}"/>'
        if outline is not None:
            xml += f'<w:pPr><w:outlineLvl w:val="{outline}"/></w:pPr>'
        parts.append(xml + "</w:style>")
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<w:styles xmlns:w="{W_NS}">{"".join(parts)}{extra}</w:styles>'
    )


def document_xml(body: str, ns_decl: str = NS_DECL) -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f"<w:document {ns_decl}><w:body>{body}<w:sectPr/></w:body></w:document>"
    )


def write_zip(path: Path, parts: dict[str, str | bytes]) -> bytes:
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for name, content in parts.items():
            zf.writestr(name, content)
    return path.read_bytes()


def make_docx(
    tmp_path: Path,
    body: str,
    styles=EN_STYLES,
    extra_parts: dict[str, str | bytes] | None = None,
    document: str | None = None,
) -> bytes:
    parts: dict[str, str | bytes] = {
        "[Content_Types].xml": CONTENT_TYPES,
        "_rels/.rels": ROOT_RELS,
        "word/document.xml": document if document is not None else document_xml(body),
    }
    if styles is not None:
        parts["word/styles.xml"] = styles if isinstance(styles, str) else styles_xml(styles)
    parts.update(extra_parts or {})
    return write_zip(tmp_path / "sample.docx", parts)


def rows(doc: ParsedDocument) -> list[tuple[str, str | None, BlockKind]]:
    return [(b.text, b.locator.section_path, b.kind) for b in doc.blocks]


def unreadable(data: bytes, **kwargs) -> UnreadableReason:
    with pytest.raises(DocumentUnreadableError) as info:
        parse_docx(data, **kwargs)
    return info.value.reason


# ---------------------------------------------------------------- 成功路径


def test_parser_version_and_format(tmp_path):
    doc = parse_docx(make_docx(tmp_path, para("只有一段正文。")))
    assert PARSER_VERSION == "docx/1"
    assert docx_parser.PARSER_VERSION == PARSER_VERSION
    assert doc.parser_version == PARSER_VERSION
    assert doc.source_format is SourceFormat.DOCX
    assert rows(doc) == [("只有一段正文。", "第1段", BlockKind.PARAGRAPH)]


def test_multilevel_headings_by_english_style_id(tmp_path):
    body = (
        para("第3章 栈与队列", "Heading1")
        + para("本章介绍两种受限线性表。")
        + para("3.1 栈", "Heading2")
        + para("栈是后进先出的线性表。")
        + para("入栈与出栈都在栈顶进行。")
        + para("3.1.1 顺序栈", "Heading3")
        + para("用数组实现。")
        + para("3.2 队列", "Heading2")
        + para("队列是先进先出的线性表。")
    )
    doc = parse_docx(make_docx(tmp_path, body))
    assert rows(doc) == [
        ("本章介绍两种受限线性表。", "第3章 栈与队列 > 第1段", BlockKind.PARAGRAPH),
        ("栈是后进先出的线性表。", "第3章 栈与队列 > 3.1 栈 > 第1段", BlockKind.PARAGRAPH),
        ("入栈与出栈都在栈顶进行。", "第3章 栈与队列 > 3.1 栈 > 第2段", BlockKind.PARAGRAPH),
        ("用数组实现。", "第3章 栈与队列 > 3.1 栈 > 3.1.1 顺序栈 > 第1段", BlockKind.PARAGRAPH),
        ("队列是先进先出的线性表。", "第3章 栈与队列 > 3.2 队列 > 第1段", BlockKind.PARAGRAPH),
    ]
    assert [b.ordinal for b in doc.blocks] == [0, 1, 2, 3, 4]
    assert doc.blocks[3].locator.section_titles == ("第3章 栈与队列", "3.1 栈", "3.1.1 顺序栈")


def test_chinese_word_builtin_heading_styles(tmp_path):
    """中文 Word 的「标题 1」样式 ID 是 "1"，按样式里的 outlineLvl 判定层级。"""
    body = (
        para("第一章 绪论", "1")
        + para("数据结构研究数据的组织方式。", "a")
        + para("1.1 基本概念", "2")
        + para("数据元素是数据的基本单位。", "a")
    )
    doc = parse_docx(make_docx(tmp_path, body, styles=ZH_STYLES))
    assert rows(doc) == [
        ("数据结构研究数据的组织方式。", "第一章 绪论 > 第1段", BlockKind.PARAGRAPH),
        ("数据元素是数据的基本单位。", "第一章 绪论 > 1.1 基本概念 > 第1段", BlockKind.PARAGRAPH),
    ]


def test_heading_level_inherited_through_based_on_chain(tmp_path):
    styles = ZH_STYLES + [
        ("ChapterTitle", "Chapter Title", "1", None),  # 继承「标题 1」
        ("ChapterTitleRed", "Chapter Title Red", "ChapterTitle", None),  # 两级继承
        ("SectionTitle", "Section Title", "2", None),
    ]
    body = (
        para("第二章 线性表", "ChapterTitleRed")
        + para("2.1 顺序表", "SectionTitle")
        + para("顺序表用连续存储单元。")
    )
    doc = parse_docx(make_docx(tmp_path, body, styles=styles))
    assert rows(doc) == [
        ("顺序表用连续存储单元。", "第二章 线性表 > 2.1 顺序表 > 第1段", BlockKind.PARAGRAPH),
    ]


def test_based_on_cycle_does_not_hang(tmp_path):
    styles = EN_STYLES + [("LoopA", "Loop A", "LoopB", None), ("LoopB", "Loop B", "LoopA", None)]
    doc = parse_docx(make_docx(tmp_path, para("循环样式里的正文。", "LoopA"), styles=styles))
    assert rows(doc) == [("循环样式里的正文。", "第1段", BlockKind.PARAGRAPH)]


def test_direct_outline_level_on_paragraph(tmp_path):
    body = para("第4章 树", outline=0) + para("4.1 二叉树", outline=1) + para("每个结点至多两棵子树。")
    doc = parse_docx(make_docx(tmp_path, body))
    assert rows(doc) == [("每个结点至多两棵子树。", "第4章 树 > 4.1 二叉树 > 第1段", BlockKind.PARAGRAPH)]


def test_heading_style_id_fallback_without_styles_part(tmp_path):
    body = para("第5章 图", "Heading1") + para("5.1 存储", "heading2") + para("邻接矩阵与邻接表。")
    doc = parse_docx(make_docx(tmp_path, body, styles=None))
    assert rows(doc) == [("邻接矩阵与邻接表。", "第5章 图 > 5.1 存储 > 第1段", BlockKind.PARAGRAPH)]


def test_display_name_alone_does_not_make_heading(tmp_path):
    """样式显示名/别名写成「标题 1」但既不是内置标题 ID、也没有 outlineLvl：按正文处理。"""
    extra = (
        '<w:style w:type="paragraph" w:customStyle="1" w:styleId="Fancy">'
        '<w:name w:val="标题 1"/><w:aliases w:val="Heading 1,标题 1"/><w:basedOn w:val="Normal"/></w:style>'
    )
    styles = styles_xml(EN_STYLES, extra=extra)
    doc = parse_docx(make_docx(tmp_path, para("看起来像标题", "Fancy") + para("正文"), styles=styles))
    assert rows(doc) == [
        ("看起来像标题", "第1段", BlockKind.PARAGRAPH),
        ("正文", "第2段", BlockKind.PARAGRAPH),
    ]


def test_outline_level_9_marks_body_text_even_with_heading_style(tmp_path):
    body = para("第1章", "Heading1") + para("被改成正文级别的段落", "Heading2", outline=9)
    doc = parse_docx(make_docx(tmp_path, body))
    assert rows(doc) == [("被改成正文级别的段落", "第1章 > 第1段", BlockKind.PARAGRAPH)]


def test_body_before_first_heading_uses_bare_paragraph_numbers(tmp_path):
    body = para("课程说明。") + para("考核方式。") + para("第1章 概述", "Heading1") + para("正文。")
    doc = parse_docx(make_docx(tmp_path, body))
    assert rows(doc) == [
        ("课程说明。", "第1段", BlockKind.PARAGRAPH),
        ("考核方式。", "第2段", BlockKind.PARAGRAPH),
        ("正文。", "第1章 概述 > 第1段", BlockKind.PARAGRAPH),
    ]
    assert doc.blocks[0].locator.section_titles == ()


def test_heading_stack_resets_and_allows_skipped_levels(tmp_path):
    body = (
        para("第1章", "Heading1")
        + para("1.1.1 细节", "Heading3")  # 跳过二级
        + para("跳级下的正文。")
        + para("第2章", "Heading1")
        + para("回到一级后的正文。")
    )
    doc = parse_docx(make_docx(tmp_path, body))
    assert rows(doc) == [
        ("跳级下的正文。", "第1章 > 1.1.1 细节 > 第1段", BlockKind.PARAGRAPH),
        ("回到一级后的正文。", "第2章 > 第1段", BlockKind.PARAGRAPH),
    ]


def test_repeated_heading_path_continues_paragraph_numbering(tmp_path):
    body = (
        para("习题", "Heading1") + para("第一题。")
        + para("附录", "Heading1") + para("附录正文。")
        + para("习题", "Heading1") + para("第二题。")
    )
    doc = parse_docx(make_docx(tmp_path, body))
    assert [b.locator.section_path for b in doc.blocks] == [
        "习题 > 第1段", "附录 > 第1段", "习题 > 第2段",
    ]


def test_heading_text_is_normalized(tmp_path):
    body = para("第3章　 栈 >  队列 ", "Heading1") + para("正文。")
    doc = parse_docx(make_docx(tmp_path, body))
    assert doc.blocks[0].locator.section_titles == ("第3章 栈 ＞ 队列",)


def test_empty_heading_is_ignored(tmp_path):
    body = para("第1章", "Heading1") + para("   ", "Heading2") + para("正文。")
    doc = parse_docx(make_docx(tmp_path, body))
    assert rows(doc) == [("正文。", "第1章 > 第1段", BlockKind.PARAGRAPH)]


def test_empty_and_whitespace_paragraphs_are_skipped(tmp_path):
    body = (
        para("")
        + para("第一段。")
        + para("   \t ")
        + '<w:p><w:r><w:br w:type="page"/></w:r></w:p>'
        + "<w:p/>"
        + para("第二段。")
    )
    doc = parse_docx(make_docx(tmp_path, body))
    assert rows(doc) == [
        ("第一段。", "第1段", BlockKind.PARAGRAPH),
        ("第二段。", "第2段", BlockKind.PARAGRAPH),
    ]


def test_runs_tabs_breaks_and_inline_wrappers(tmp_path):
    inner = (
        '<w:r><w:t>前</w:t><w:tab/><w:t>后</w:t><w:br/><w:t>换行</w:t></w:r>'
        '<w:hyperlink r:id="rId9"><w:r><w:t>链接文字</w:t></w:r></w:hyperlink>'
        '<w:ins w:id="1" w:author="t"><w:r><w:t>插入</w:t></w:r></w:ins>'
        '<w:del w:id="2" w:author="t"><w:r><w:delText>删除</w:delText></w:r></w:del>'
        '<w:r><w:fldChar w:fldCharType="begin"/></w:r>'
        '<w:r><w:instrText> PAGE </w:instrText></w:r>'
        '<w:r><w:fldChar w:fldCharType="separate"/></w:r>'
        '<w:r><w:t>域结果</w:t></w:r>'
        '<w:r><w:fldChar w:fldCharType="end"/></w:r>'
        '<w:r><w:rPr><w:vanish/></w:rPr><w:t>隐藏</w:t></w:r>'
        '<w:sdt><w:sdtContent><w:r><w:t>控件</w:t></w:r></w:sdtContent></w:sdt>'
        '<w:smartTag w:element="x"><w:r><w:t>标记</w:t></w:r></w:smartTag>'
    )
    doc = parse_docx(make_docx(tmp_path, para(inner=inner)))
    assert doc.blocks[0].text == "前\t后\n换行链接文字插入域结果控件标记"


def test_body_level_content_controls_are_unwrapped(tmp_path):
    body = (
        "<w:sdt><w:sdtPr/><w:sdtContent>"
        + para("第1章", "Heading1")
        + para("控件里的正文。")
        + "</w:sdtContent></w:sdt>"
        + para("控件外的正文。")
    )
    doc = parse_docx(make_docx(tmp_path, body))
    assert rows(doc) == [
        ("控件里的正文。", "第1章 > 第1段", BlockKind.PARAGRAPH),
        ("控件外的正文。", "第1章 > 第2段", BlockKind.PARAGRAPH),
    ]


def test_table_becomes_single_table_block_with_cells_in_order(tmp_path):
    body = (
        para("第2章 复杂度", "Heading1")
        + para("常见复杂度如下表。")
        + table(
            [text_cell("算法"), text_cell("时间"), text_cell("空间")],
            [text_cell("冒泡排序"), text_cell("O(n^2)"), text_cell("O(1)")],
            [text_cell("归并排序"), text_cell("O(n log n)"), text_cell("O(n)")],
        )
        + para("表后的说明。")
    )
    doc = parse_docx(make_docx(tmp_path, body))
    assert rows(doc) == [
        ("常见复杂度如下表。", "第2章 复杂度 > 第1段", BlockKind.PARAGRAPH),
        (
            "算法 | 时间 | 空间\n冒泡排序 | O(n^2) | O(1)\n归并排序 | O(n log n) | O(n)",
            "第2章 复杂度 > 第2段",
            BlockKind.TABLE,
        ),
        ("表后的说明。", "第2章 复杂度 > 第3段", BlockKind.PARAGRAPH),
    ]


def test_table_merged_cells_nested_tables_and_empty_rows(tmp_path):
    nested = table([text_cell("内1"), text_cell("内2")], [text_cell("内3"), text_cell("内4")])
    body = table(
        [cell(para("合并表头"), props='<w:gridSpan w:val="2"/>'), text_cell("C")],
        [cell(para("纵向"), props='<w:vMerge w:val="restart"/>'), text_cell("B2"), text_cell("C2")],
        [cell(props="<w:vMerge/>"), cell(para("多段一"), para("多段二")), cell(nested)],
        [cell(), cell(), cell()],  # 全空行跳过
    )
    doc = parse_docx(make_docx(tmp_path, body))
    assert rows(doc) == [
        (
            "合并表头 | C\n纵向 | B2 | C2\n | 多段一 多段二 | 内1 内2 内3 内4",
            "第1段",
            BlockKind.TABLE,
        )
    ]


def test_empty_table_is_skipped(tmp_path):
    body = table([cell(), cell()]) + para("唯一正文。")
    doc = parse_docx(make_docx(tmp_path, body))
    assert rows(doc) == [("唯一正文。", "第1段", BlockKind.PARAGRAPH)]


def test_consecutive_numbered_paragraphs_become_one_list_block(tmp_path):
    body = (
        para("第1章", "Heading1")
        + para("线性表的基本操作：")
        + list_para("初始化")
        + list_para("插入", ilvl=1)
        + list_para("删除")
        + para("列表后的正文。")
        + list_para("另一个列表", num_id=2)
    )
    doc = parse_docx(make_docx(tmp_path, body))
    assert rows(doc) == [
        ("线性表的基本操作：", "第1章 > 第1段", BlockKind.PARAGRAPH),
        ("初始化\n插入\n删除", "第1章 > 第2段", BlockKind.LIST),
        ("列表后的正文。", "第1章 > 第3段", BlockKind.PARAGRAPH),
        ("另一个列表", "第1章 > 第4段", BlockKind.LIST),
    ]


def test_list_is_split_by_heading_and_num_id_zero_is_not_a_list(tmp_path):
    no_list = (
        '<w:p><w:pPr><w:numPr><w:ilvl w:val="0"/><w:numId w:val="0"/></w:numPr></w:pPr>'
        + run("取消编号的段落")
        + "</w:p>"
    )
    body = list_para("甲") + para("第1章", "Heading1") + list_para("乙") + no_list
    doc = parse_docx(make_docx(tmp_path, body))
    assert rows(doc) == [
        ("甲", "第1段", BlockKind.LIST),
        ("乙", "第1章 > 第1段", BlockKind.LIST),
        ("取消编号的段落", "第1章 > 第2段", BlockKind.PARAGRAPH),
    ]


def test_docx_blocks_never_carry_page_or_line_numbers(tmp_path):
    body = (
        para("第1章", "Heading1")
        + para("前")
        + '<w:p><w:r><w:br w:type="page"/></w:r></w:p>'
        + '<w:p><w:r><w:lastRenderedPageBreak/><w:t>分页后</w:t></w:r></w:p>'
        + table([text_cell("x")])
    )
    doc = parse_docx(make_docx(tmp_path, body))
    for block in doc.blocks:
        assert block.locator.page is None
        assert block.locator.line_start is None and block.locator.line_end is None
        assert "page" not in block.locator.to_source_fields()
    assert [b.locator.paragraph for b in doc.blocks] == [1, 2, 3]


def test_embedded_content_scope(tmp_path):
    """正文只取段落与表格文字；图片、文本框、嵌入对象、公式、页眉页脚、脚注、批注不进块。"""
    drawing = (
        '<w:r><w:drawing><wp:inline><wp:docPr id="1" name="图片 1" descr="替代文字"/>'
        '<a:graphic><a:graphicData uri="x"/></a:graphic></wp:inline></w:drawing></w:r>'
    )
    textbox = (
        "<w:r><mc:AlternateContent><mc:Choice Requires=\"wps\"><w:drawing><wp:anchor>"
        "<a:graphic><a:graphicData><wps:wsp><wps:txbx><w:txbxContent>"
        + para("文本框文字")
        + "</w:txbxContent></wps:txbx></wps:wsp></a:graphicData></a:graphic></wp:anchor></w:drawing>"
        "</mc:Choice><mc:Fallback><w:pict><v:shape><v:textbox><w:txbxContent>"
        + para("文本框文字")
        + "</w:txbxContent></v:textbox></v:shape></w:pict></mc:Fallback></mc:AlternateContent></w:r>"
    )
    ole = '<w:r><w:object><v:shape/><o:OLEObject ProgID="Excel.Sheet.12" r:id="rId5"/></w:object></w:r>'
    math = "<m:oMath><m:r><m:t>a+b</m:t></m:r></m:oMath>"
    refs = (
        '<w:commentRangeStart w:id="0"/><w:r><w:t>被批注的正文</w:t></w:r><w:commentRangeEnd w:id="0"/>'
        '<w:r><w:commentReference w:id="0"/></w:r>'
        '<w:r><w:footnoteReference w:id="1"/></w:r>'
    )
    body = (
        para(inner=drawing)  # 只有图片的段落 → 空段落跳过
        + para("图前", inner=drawing + "<w:r><w:t>图后</w:t></w:r>")
        + para(inner=textbox)
        + para("对象前", inner=ole)
        + para("公式前", inner=math)
        + para(inner=refs)
        + '<w:altChunk r:id="rId7"/>'
    )
    extra = {
        "word/header1.xml": f'<w:hdr xmlns:w="{W_NS}">{para("页眉文字")}</w:hdr>',
        "word/footer1.xml": f'<w:ftr xmlns:w="{W_NS}">{para("页脚文字")}</w:ftr>',
        "word/footnotes.xml": f'<w:footnotes xmlns:w="{W_NS}"><w:footnote w:id="1">{para("脚注文字")}</w:footnote></w:footnotes>',
        "word/comments.xml": f'<w:comments xmlns:w="{W_NS}"><w:comment w:id="0">{para("批注文字")}</w:comment></w:comments>',
        "word/media/image1.png": b"\x89PNG\r\n\x1a\n" + b"\x00" * 16,
    }
    doc = parse_docx(make_docx(tmp_path, body, extra_parts=extra))
    assert [b.text for b in doc.blocks] == ["图前图后", "对象前", "公式前", "被批注的正文"]
    joined = "".join(b.text for b in doc.blocks)
    for leaked in ("文本框", "页眉", "页脚", "脚注", "批注文字", "替代文字", "a+b"):
        assert leaked not in joined


def test_strict_ooxml_namespace_is_supported(tmp_path):
    strict_decl = f'xmlns:w="{STRICT_W_NS}"'
    doc_xml = document_xml(para("第1章", "Heading1") + para("严格模式正文。"), ns_decl=strict_decl)
    strict_styles = styles_xml(EN_STYLES).replace(W_NS, STRICT_W_NS)
    doc = parse_docx(make_docx(tmp_path, "", styles=strict_styles, document=doc_xml))
    assert rows(doc) == [("严格模式正文。", "第1章 > 第1段", BlockKind.PARAGRAPH)]


def test_utf16_encoded_document_part(tmp_path):
    doc_xml = document_xml(para("第1章", "Heading1") + para("UTF-16 正文。"))
    encoded = doc_xml.replace('encoding="UTF-8"', 'encoding="UTF-16"').encode("utf-16")
    doc = parse_docx(make_docx(tmp_path, "", document=encoded))
    assert rows(doc) == [("UTF-16 正文。", "第1章 > 第1段", BlockKind.PARAGRAPH)]


def test_accepts_bytearray_and_memoryview(tmp_path):
    data = make_docx(tmp_path, para("正文。"))
    assert rows(parse_docx(bytearray(data))) == rows(parse_docx(memoryview(data)))


# ---------------------------------------------------------------- 失败路径


def test_rejects_non_bytes_input():
    with pytest.raises(TypeError):
        parse_docx("word/document.xml")  # type: ignore[arg-type]


@pytest.mark.parametrize("data", [b"", b"not a zip at all", b"PK\x03\x04garbage"])
def test_non_zip_bytes_are_corrupted(data):
    assert unreadable(data) is UnreadableReason.CORRUPTED


def test_truncated_zip_is_corrupted(tmp_path):
    data = make_docx(tmp_path, para("正文。" * 200))
    assert unreadable(data[: len(data) // 2]) is UnreadableReason.CORRUPTED


def test_crc_mismatch_is_corrupted(tmp_path):
    path = tmp_path / "stored.docx"
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_STORED) as zf:
        zf.writestr("word/document.xml", document_xml(para("正文内容，用于破坏校验。")))
    data = bytearray(path.read_bytes())
    pos = data.find("用于".encode())
    data[pos] ^= 0x01
    assert unreadable(bytes(data)) is UnreadableReason.CORRUPTED


def test_missing_document_part_is_corrupted(tmp_path):
    data = write_zip(
        tmp_path / "no-main.docx",
        {"[Content_Types].xml": CONTENT_TYPES, "word/styles.xml": styles_xml(EN_STYLES)},
    )
    with pytest.raises(DocumentUnreadableError) as info:
        parse_docx(data)
    assert info.value.reason is UnreadableReason.CORRUPTED
    assert "word/document.xml" in info.value.detail


@pytest.mark.parametrize(
    "document",
    [
        "<w:document><w:body>",  # 不闭合
        f'<w:document xmlns:w="{W_NS}"><w:body><w:p></w:body></w:document>',  # 标签错位
        f'<x:root xmlns:x="urn:other"><x:body/></x:root>',  # 根元素不是 w:document
        f'<w:document xmlns:w="{W_NS}"><w:other/></w:document>',  # 缺 w:body
    ],
)
def test_malformed_document_xml_is_corrupted(tmp_path, document):
    assert unreadable(make_docx(tmp_path, "", document=document)) is UnreadableReason.CORRUPTED


def test_malformed_styles_xml_is_corrupted(tmp_path):
    data = make_docx(tmp_path, para("正文。"), styles="<w:styles>")
    assert unreadable(data) is UnreadableReason.CORRUPTED


BOMB = (
    '<?xml version="1.0"?>'
    '<!DOCTYPE lolz [<!ENTITY lol "lol">'
    '<!ENTITY lol2 "&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;">'
    '<!ENTITY lol3 "&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;">]>'
    f'<w:document xmlns:w="{W_NS}"><w:body><w:p><w:r><w:t>&lol3;</w:t></w:r></w:p></w:body></w:document>'
)
EXTERNAL_ENTITY = (
    '<?xml version="1.0"?>'
    '<!DOCTYPE d [<!ENTITY xxe SYSTEM "file:///etc/passwd">]>'
    f'<w:document xmlns:w="{W_NS}"><w:body><w:p><w:r><w:t>&xxe;</w:t></w:r></w:p></w:body></w:document>'
)


@pytest.mark.parametrize("document", [BOMB, EXTERNAL_ENTITY])
def test_doctype_and_entities_are_rejected_in_document(tmp_path, document):
    assert unreadable(make_docx(tmp_path, "", document=document)) is UnreadableReason.CORRUPTED


def test_doctype_is_rejected_in_styles(tmp_path):
    styles = '<?xml version="1.0"?><!DOCTYPE s []>' + styles_xml(EN_STYLES).split("?>", 1)[1]
    assert unreadable(make_docx(tmp_path, para("正文。"), styles=styles)) is UnreadableReason.CORRUPTED


def test_decompressed_size_limit_guards_against_zip_bombs(tmp_path):
    # 高压缩比：几十 KB 的 zip 解压后远超限额；限额按实际读出的字节判定，不信任头部声明的大小。
    body = para("压" * 200_000)
    data = make_docx(tmp_path, body)
    assert len(data) < 50_000
    with pytest.raises(DocumentUnreadableError) as info:
        parse_docx(data, max_part_bytes=100_000)
    assert info.value.reason is UnreadableReason.CORRUPTED
    assert "上限" in info.value.detail
    assert parse_docx(data, max_part_bytes=2_000_000).blocks[0].text == "压" * 200_000


def test_default_part_limit_is_bounded():
    assert 0 < docx_parser.MAX_PART_BYTES <= 256 * 1024 * 1024


def test_size_limit_ignores_forged_header_size(tmp_path):
    """篡改中央目录声明的解压大小：不得静默读出截断内容，按 corrupted 拒绝。"""
    data = bytearray(make_docx(tmp_path, para("炸" * 100_000)))
    pos = data.find(b"PK\x01\x02")
    while pos != -1:
        name_len = struct.unpack_from("<H", data, pos + 28)[0]
        name = bytes(data[pos + 46 : pos + 46 + name_len])
        if name == b"word/document.xml":
            struct.pack_into("<I", data, pos + 24, 10)  # 声明解压后只有 10 字节
        pos = data.find(b"PK\x01\x02", pos + 4)
    assert unreadable(bytes(data), max_part_bytes=50_000) is UnreadableReason.CORRUPTED


OLE_MAGIC = bytes.fromhex("D0CF11E0A1B11AE1")


def test_ole_encrypted_package_is_encrypted():
    """加密的 DOCX 是 OLE 复合文件，内含 EncryptionInfo / EncryptedPackage 流。"""
    data = OLE_MAGIC + b"\x00" * 504 + "EncryptionInfo".encode("utf-16-le") + b"\x00" * 64
    data += "EncryptedPackage".encode("utf-16-le") + b"\x00" * 64
    assert unreadable(data) is UnreadableReason.ENCRYPTED


def test_ole_without_encryption_streams_is_legacy_doc_and_corrupted():
    """旧版 .doc 也是 OLE 文件；没有加密流时不能谎称加密，按无法解析处理。"""
    data = OLE_MAGIC + b"\x00" * 504 + "WordDocument".encode("utf-16-le") + b"\x00" * 64
    with pytest.raises(DocumentUnreadableError) as info:
        parse_docx(data)
    assert info.value.reason is UnreadableReason.CORRUPTED
    assert ".doc" in info.value.detail


def test_zip_entry_encryption_flag_is_encrypted(tmp_path):
    data = bytearray(make_docx(tmp_path, para("正文。")))
    for sig, flag_offset in ((b"PK\x03\x04", 6), (b"PK\x01\x02", 8)):
        pos = data.find(sig)
        while pos != -1:
            flags = struct.unpack_from("<H", data, pos + flag_offset)[0]
            struct.pack_into("<H", data, pos + flag_offset, flags | 0x1)
            pos = data.find(sig, pos + 4)
    assert unreadable(bytes(data)) is UnreadableReason.ENCRYPTED


@pytest.mark.parametrize(
    "body",
    [
        "",  # 只有 sectPr
        para("") + para("   ") + "<w:p/>",
        para("第1章", "Heading1") + para("1.1", "Heading2"),  # 只有标题，没有正文块
        para(inner='<w:r><w:drawing><wp:inline><wp:docPr id="1" name="p"/></wp:inline></w:drawing></w:r>'),
        table([cell(), cell()]),
    ],
    ids=["empty-body", "blank-paragraphs", "headings-only", "image-only", "empty-table"],
)
def test_documents_without_text_blocks_are_no_text(tmp_path, body):
    assert unreadable(make_docx(tmp_path, body)) is UnreadableReason.NO_TEXT
