"""D09：资料修订 ID、块 ID 与抽取缓存键（ADR-012 修订 1 决定 9；docs/integrations.md「模型版本与向量空间」）。"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from app.services.ai.client import ModelResult
from app.services.chunk_identity import (
    ChunkIdentity,
    ChunkIdentityError,
    assign_chunk_identities,
    cache_model_id,
    derive_chunk_id,
    derive_revision_id,
    extraction_cache_key,
    revision_id_for,
    revision_parser_version,
    split_chunk_id,
    text_sha256,
)
from app.services import chunking
from app.services.chunking import (
    CHUNKER_VERSION,
    DEFAULT_OVERLAP_CHARS,
    DEFAULT_TARGET_CHARS,
    ChunkSource,
    SemanticChunk,
    chunk_blocks,
    chunking_version,
)
from app.services.parsers.models import ParsedBlock, RevisionKey, SourceLocator

HASH_A = "sha256:" + "a" * 64
HASH_B = "sha256:" + "b" * 64
PROMPT_SHA = "c" * 64
PROMPT_SHA_2 = "d" * 64
# ADR-018：修订键里的 parser_version 是「解析器版本+分块版本」复合版本。
CHUNK_V = "chunk/1@1500-200"
PV_PDF = f"pdf/1+{CHUNK_V}"
PV_PDF2 = f"pdf/2+{CHUNK_V}"
PV_TXT = f"txt/1+{CHUNK_V}"


def _canon(parts: list[object]) -> bytes:
    return json.dumps(parts, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def _expected_revision_id(document_id: str, content_hash: str, parser_version: str) -> str:
    digest = hashlib.sha256(
        _canon(["smartsketch.revision/1", document_id, content_hash, parser_version])
    ).hexdigest()
    return f"rev_{digest}"


def _pdf_chunk(ordinal: int, text: str, page: int) -> SemanticChunk:
    locator = SourceLocator(page=page)
    return SemanticChunk(
        ordinal=ordinal,
        text=text,
        section_titles=(),
        sources=(ChunkSource(block_ordinal=ordinal, start=0, end=len(text), locator=locator),),
    )


def _key(document_id: str = "doc-1", content_hash: str = HASH_A, parser: str = PV_PDF) -> RevisionKey:
    return RevisionKey(document_id=document_id, content_hash=content_hash, parser_version=parser)


def _cache_key(identity: ChunkIdentity, **overrides: object) -> str:
    params: dict[str, object] = {
        "prompt_purpose": "extract_entities",
        "prompt_version": 1,
        "prompt_sha256": PROMPT_SHA,
        "model_id": "model-primary-2026-01-01",
    }
    params.update(overrides)
    return extraction_cache_key(identity, **params)  # type: ignore[arg-type]


# ---------------------------------------------------------------- revision_id


def test_revision_id_follows_documented_formula():
    assert derive_revision_id("doc-1", HASH_A, PV_PDF) == _expected_revision_id("doc-1", HASH_A, PV_PDF)


def test_identity_values_are_pinned_across_releases():
    # 固定值：公式或编码一旦改变，已持久化的块 ID 与缓存全部失配，必须显式升级方案版本。
    # ADR-018 后输入改为复合版本 "pdf/1+chunk/1@1500-200"（公式未变，仅输入变化），值已按公式重算。
    assert derive_revision_id("doc-1", HASH_A, PV_PDF) == (
        "rev_228fb4b57b9a53afa4c58d1a61e4d5b50a646dc3f39fc4953ebaeb383926ab4e"
    )
    identity = assign_chunk_identities("course-1", _key(), [_pdf_chunk(0, "甲。", 1)])[0]
    assert identity.chunk_id == "rev_228fb4b57b9a53afa4c58d1a61e4d5b50a646dc3f39fc4953ebaeb383926ab4e-0"
    assert _cache_key(identity) == "xc_8395acd0e6641e421398c46705345b6b295ef2bf21ac30eec73bb2b5d9b520ac"


def test_revision_id_accepts_revision_key():
    assert revision_id_for(_key()) == derive_revision_id("doc-1", HASH_A, PV_PDF)


@pytest.mark.parametrize(
    "other",
    [("doc-2", HASH_A, PV_PDF), ("doc-1", HASH_B, PV_PDF), ("doc-1", HASH_A, PV_PDF2)],
    ids=["document", "content", "parser"],
)
def test_revision_id_changes_with_each_component(other):
    assert derive_revision_id(*other) != derive_revision_id("doc-1", HASH_A, PV_PDF)


def test_revision_components_cannot_be_shifted_across_field_boundaries():
    # 编码必须区分字段边界：拼接相同但分段不同的输入不得同 ID。
    assert derive_revision_id("a|b", HASH_A, f"c+{CHUNK_V}") != derive_revision_id("a", HASH_A, f"b|c+{CHUNK_V}")


def test_revision_id_is_stable_across_processes():
    code = (
        "from app.services.chunk_identity import derive_revision_id;"
        f"print(derive_revision_id('doc-1', {HASH_A!r}, {PV_PDF!r}))"
    )
    outputs = set()
    for seed in ("0", "1", "12345"):
        env = dict(os.environ, PYTHONHASHSEED=seed)
        out = subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, text=True, check=True)
        outputs.add(out.stdout.strip())
    assert outputs == {derive_revision_id("doc-1", HASH_A, PV_PDF)}


@pytest.mark.parametrize(
    "content_hash",
    [
        "a" * 64,
        "sha256:" + "A" * 64,
        "sha256:" + "a" * 63,
        "sha256:" + "a" * 65,
        "md5:" + "a" * 32,
        "sha256:" + "g" * 64,
        " sha256:" + "a" * 64,
        "",
        None,
    ],
)
def test_bad_content_hash_rejected(content_hash):
    with pytest.raises(ChunkIdentityError, match="content_hash"):
        derive_revision_id("doc-1", content_hash, PV_PDF)  # type: ignore[arg-type]


@pytest.mark.parametrize("parser_version", ["", " ", "pdf /1", "pdf/1\n", "\tpdf/1", None, 1])
def test_bad_parser_version_rejected(parser_version):
    with pytest.raises(ChunkIdentityError, match="parser_version"):
        derive_revision_id("doc-1", HASH_A, parser_version)  # type: ignore[arg-type]


@pytest.mark.parametrize("document_id", ["", "   ", None, 7])
def test_bad_document_id_rejected(document_id):
    with pytest.raises(ChunkIdentityError, match="document_id"):
        derive_revision_id(document_id, HASH_A, PV_PDF)  # type: ignore[arg-type]


def test_revision_id_for_rejects_non_revision_key():
    with pytest.raises(TypeError):
        revision_id_for(("doc-1", HASH_A, PV_PDF))  # type: ignore[arg-type]


def test_chunk_identity_error_is_value_error():
    assert issubclass(ChunkIdentityError, ValueError)


# ---------------------------------------------------------------- ADR-018 复合版本


def test_chunker_version_constant_and_default_chunking_version():
    assert CHUNKER_VERSION == "chunk/1"
    assert chunking_version() == f"chunk/1@{DEFAULT_TARGET_CHARS}-{DEFAULT_OVERLAP_CHARS}"
    assert chunking_version() == "chunk/1@1500-200"


def test_chunking_version_carries_actual_parameters():
    assert chunking_version(200, 20) == "chunk/1@200-20"
    assert chunking_version(target_chars=1, overlap_chars=0) == "chunk/1@1-0"
    assert chunking_version(overlap_chars=0) == f"chunk/1@{DEFAULT_TARGET_CHARS}-0"


def test_chunking_version_reads_chunker_version(monkeypatch):
    monkeypatch.setattr(chunking, "CHUNKER_VERSION", "chunk/2")
    assert chunking_version() == f"chunk/2@{DEFAULT_TARGET_CHARS}-{DEFAULT_OVERLAP_CHARS}"


@pytest.mark.parametrize(
    ("target", "overlap"),
    [(0, 0), (-1, 0), (100, 100), (100, 101), (100, -1), (True, 0), (100, False), (1.5, 0), ("100", 0), (100, None)],
)
def test_chunking_version_rejects_parameters_chunk_blocks_rejects(target, overlap):
    block = ParsedBlock(ordinal=0, text="甲。", locator=SourceLocator(paragraph=1))
    with pytest.raises(ValueError) as from_blocks:
        chunk_blocks([block], target_chars=target, overlap_chars=overlap)
    with pytest.raises(ValueError) as from_version:
        chunking_version(target, overlap)
    assert str(from_version.value) == str(from_blocks.value)


def test_revision_parser_version_format():
    assert revision_parser_version("pdf/1", "chunk/1@1500-200") == "pdf/1+chunk/1@1500-200"
    assert revision_parser_version("txt/1", chunking_version(200, 20)) == "txt/1+chunk/1@200-20"
    assert revision_parser_version("docx/3", chunking_version()) == f"docx/3+{chunking_version()}"


@pytest.mark.parametrize("parser_version", ["", " ", "pdf /1", "pdf/1\n", "pdf+1", "+", "pdf/1+", None, 1])
def test_revision_parser_version_rejects_bad_parser_segment(parser_version):
    with pytest.raises(ChunkIdentityError, match="parser_version"):
        revision_parser_version(parser_version, CHUNK_V)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "chunk_version",
    [
        "",
        "chunk/1",
        "chunk/1@1500",
        "chunk/1@1500-",
        "chunk/@1500-200",
        "chunk/1@0-0",
        "chunk/1@01500-200",
        "chunk/1@1500-0200",
        "chunk/1@1500--1",
        "chunk/1@-1500-200",
        "chunk/1@1500-200 ",
        " chunk/1@1500-200",
        "chunk/1 @1500-200",
        "chunker/1@1500-200",
        "Chunk/1@1500-200",
        "chunk/1@1500-200+x",
        "chunk/1@１５００-200",
        "chunk/1@1500-200-1",
        None,
        1,
    ],
)
def test_revision_parser_version_rejects_bad_chunking_segment(chunk_version):
    with pytest.raises(ChunkIdentityError, match="chunking_version"):
        revision_parser_version("pdf/1", chunk_version)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "parser_version",
    [
        "pdf/1",
        "txt/1",
        "pdf/1+",
        f"+{CHUNK_V}",
        "pdf/1+chunk/1",
        "pdf/1+chunk/1@1500",
        "pdf/1+chunk/1@0-0",
        f"pdf+1+{CHUNK_V}",
        f"{CHUNK_V}+pdf/1",
        f"pdf/1+{CHUNK_V}+x",
        f"pdf/1+{CHUNK_V}+{CHUNK_V}",
    ],
)
def test_revision_id_rejects_parser_version_without_valid_chunking_segment(parser_version):
    with pytest.raises(ChunkIdentityError, match="parser_version"):
        derive_revision_id("doc-1", HASH_A, parser_version)
    key = RevisionKey(document_id="doc-1", content_hash=HASH_A, parser_version=parser_version)
    with pytest.raises(ChunkIdentityError, match="parser_version"):
        revision_id_for(key)
    with pytest.raises(ChunkIdentityError, match="parser_version"):
        assign_chunk_identities("course-1", key, [_pdf_chunk(0, "甲。", 1)])


def test_revision_id_accepts_composed_version():
    pv = revision_parser_version("pdf/1", chunking_version())
    assert pv == PV_PDF
    assert derive_revision_id("doc-1", HASH_A, pv) == _expected_revision_id("doc-1", HASH_A, "pdf/1+chunk/1@1500-200")


def _txt_blocks() -> list[ParsedBlock]:
    return [
        ParsedBlock(ordinal=i, text=t, locator=SourceLocator(section_titles=("第1章",), paragraph=i + 1))
        for i, t in enumerate(["第一段。" * 30, "第二段。" * 30, "第三段。" * 30])
    ]


@pytest.mark.parametrize(("left", "right"), [((200, 20), (300, 20)), ((200, 20), (200, 40))], ids=["target", "overlap"])
def test_chunking_parameters_change_revision_and_chunk_ids(left, right):
    # 同一资料、同一内容、同一解析器，仅分块参数不同 → 修订与块 ID 都不同（ADR-018 决定 2）。
    blocks = _txt_blocks()
    ids = []
    for target, overlap in (left, right):
        key = _key(parser=revision_parser_version("txt/1", chunking_version(target, overlap)))
        identities = assign_chunk_identities(
            "course-1", key, chunk_blocks(blocks, target_chars=target, overlap_chars=overlap)
        )
        ids.append((revision_id_for(key), {i.chunk_id for i in identities}))
    (rev_a, chunks_a), (rev_b, chunks_b) = ids
    assert rev_a != rev_b
    assert chunks_a.isdisjoint(chunks_b)


def test_chunker_rule_version_change_yields_new_revision(monkeypatch):
    # 仅 CHUNKER_VERSION 不同（参数与内容相同）→ 修订与块 ID 不同（ADR-018 决定 2）。
    chunks = [_pdf_chunk(0, "甲。", 1)]
    old_key = _key(parser=revision_parser_version("pdf/1", chunking_version()))
    monkeypatch.setattr(chunking, "CHUNKER_VERSION", "chunk/2")
    new_key = _key(parser=revision_parser_version("pdf/1", chunking_version()))
    assert new_key.parser_version == "pdf/1+chunk/2@1500-200"
    old = assign_chunk_identities("course-1", old_key, chunks)[0]
    new = assign_chunk_identities("course-1", new_key, chunks)[0]
    assert old.revision_id != new.revision_id
    assert old.chunk_id != new.chunk_id
    assert derive_revision_id("doc-1", HASH_A, "pdf/1+chunk/1@1500-200") != derive_revision_id(
        "doc-1", HASH_A, "pdf/1+chunk/2@1500-200"
    )


# ---------------------------------------------------------------- chunk_id


def test_chunk_id_is_revision_id_plus_decimal_ordinal():
    rev = derive_revision_id("doc-1", HASH_A, PV_PDF)
    assert derive_chunk_id(rev, 0) == f"{rev}-0"
    assert derive_chunk_id(rev, 12) == f"{rev}-12"


def test_chunk_id_round_trips():
    rev = derive_revision_id("doc-1", HASH_A, PV_PDF)
    for ordinal in (0, 1, 9, 10, 12345):
        assert split_chunk_id(derive_chunk_id(rev, ordinal)) == (rev, ordinal)


@pytest.mark.parametrize("ordinal", [-1, True, False, 1.0, "1", None])
def test_bad_ordinal_rejected(ordinal):
    rev = derive_revision_id("doc-1", HASH_A, PV_PDF)
    with pytest.raises(ChunkIdentityError, match="ordinal"):
        derive_chunk_id(rev, ordinal)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "revision_id",
    ["", "rev_" + "a" * 63, "rev_" + "A" * 64, "REV_" + "a" * 64, "a" * 64, "rev_" + "a" * 64 + " ", None],
)
def test_bad_revision_id_rejected(revision_id):
    with pytest.raises(ChunkIdentityError, match="revision_id"):
        derive_chunk_id(revision_id, 0)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "chunk_id",
    [
        "",
        "rev_" + "a" * 64,
        "rev_" + "a" * 64 + "-",
        "rev_" + "a" * 64 + "-01",
        "rev_" + "a" * 64 + "--1",
        "rev_" + "a" * 64 + "-1a",
        "rev_" + "a" * 64 + "-+1",
        "rev_" + "a" * 64 + "-１",
        "rev_" + "a" * 63 + "-1",
        None,
    ],
)
def test_split_rejects_non_canonical_chunk_ids(chunk_id):
    with pytest.raises(ChunkIdentityError, match="chunk_id"):
        split_chunk_id(chunk_id)  # type: ignore[arg-type]


# ---------------------------------------------------------------- assign_chunk_identities


def test_same_text_on_different_pages_has_independent_identity_and_source():
    text = "栈是后进先出的线性表。"
    chunks = [_pdf_chunk(0, text, page=3), _pdf_chunk(1, text, page=7)]
    first, second = assign_chunk_identities("course-1", _key(), chunks)
    assert first.chunk_id != second.chunk_id
    assert first.text_sha256 == second.text_sha256
    assert first.sources[0].locator.page == 3
    assert second.sources[0].locator.page == 7
    assert _cache_key(first) != _cache_key(second)


def test_assigned_identity_fields():
    chunks = [_pdf_chunk(0, "甲。", 1), _pdf_chunk(1, "乙。", 2)]
    identities = assign_chunk_identities("course-1", _key(), chunks)
    rev = revision_id_for(_key())
    assert [i.chunk_id for i in identities] == [f"{rev}-0", f"{rev}-1"]
    assert all(i.revision_id == rev for i in identities)
    assert all(i.course_id == "course-1" for i in identities)
    assert all(i.document_id == "doc-1" for i in identities)
    assert [i.ordinal for i in identities] == [0, 1]
    assert identities[0].text_sha256 == "sha256:" + hashlib.sha256("甲。".encode("utf-8")).hexdigest()
    assert identities[0].text_sha256 == text_sha256("甲。")
    assert identities[1].sources == chunks[1].sources


def test_identity_repr_does_not_leak_text():
    identity = assign_chunk_identities("course-1", _key(), [_pdf_chunk(0, "机密原文内容。", 1)])[0]
    assert "机密原文内容" not in repr(identity)


def test_rerun_with_same_inputs_is_stable():
    blocks = [
        ParsedBlock(ordinal=i, text=t, locator=SourceLocator(section_titles=("第1章",), paragraph=i + 1))
        for i, t in enumerate(["第一段。" * 30, "第二段。" * 30, "第三段。" * 30])
    ]
    pv = revision_parser_version("txt/1", chunking_version(200, 20))
    a = assign_chunk_identities("course-1", _key(parser=pv), chunk_blocks(blocks, target_chars=200, overlap_chars=20))
    b = assign_chunk_identities("course-1", _key(parser=pv), chunk_blocks(blocks, target_chars=200, overlap_chars=20))
    assert len(a) > 1
    assert a == b
    assert [_cache_key(x) for x in a] == [_cache_key(x) for x in b]


def test_parser_upgrade_yields_new_chunk_ids():
    chunks = [_pdf_chunk(0, "甲。", 1)]
    old = assign_chunk_identities("course-1", _key(parser=PV_PDF), chunks)[0]
    new = assign_chunk_identities("course-1", _key(parser=PV_PDF2), chunks)[0]
    assert old.revision_id != new.revision_id
    assert old.chunk_id != new.chunk_id


def test_changed_content_yields_new_chunk_ids():
    chunks = [_pdf_chunk(0, "甲。", 1)]
    old = assign_chunk_identities("course-1", _key(content_hash=HASH_A), chunks)[0]
    new = assign_chunk_identities("course-1", _key(content_hash=HASH_B), chunks)[0]
    assert old.chunk_id != new.chunk_id


def test_cross_course_identity_not_reused():
    # 同一文件分别上传到两门课：资料 ID 不同 → 修订与块 ID 不同；缓存键也不同。
    chunks = [_pdf_chunk(0, "甲。", 1)]
    in_a = assign_chunk_identities("course-a", _key(document_id="doc-a"), chunks)[0]
    in_b = assign_chunk_identities("course-b", _key(document_id="doc-b"), chunks)[0]
    assert in_a.revision_id != in_b.revision_id
    assert in_a.chunk_id != in_b.chunk_id
    assert _cache_key(in_a) != _cache_key(in_b)


def test_cache_key_contains_course_even_if_chunk_id_collides():
    # 防御：即使上游错误地复用了资料 ID，缓存也不得跨课程命中。
    chunks = [_pdf_chunk(0, "甲。", 1)]
    in_a = assign_chunk_identities("course-a", _key(), chunks)[0]
    in_b = assign_chunk_identities("course-b", _key(), chunks)[0]
    assert in_a.chunk_id == in_b.chunk_id
    assert _cache_key(in_a) != _cache_key(in_b)


@pytest.mark.parametrize("course_id", ["", "  ", None, 3])
def test_bad_course_id_rejected(course_id):
    with pytest.raises(ChunkIdentityError, match="course_id"):
        assign_chunk_identities(course_id, _key(), [_pdf_chunk(0, "甲。", 1)])  # type: ignore[arg-type]


def test_non_consecutive_chunk_ordinals_rejected():
    with pytest.raises(ChunkIdentityError, match="ordinal"):
        assign_chunk_identities("course-1", _key(), [_pdf_chunk(0, "甲。", 1), _pdf_chunk(2, "乙。", 2)])
    with pytest.raises(ChunkIdentityError, match="ordinal"):
        assign_chunk_identities("course-1", _key(), [_pdf_chunk(1, "甲。", 1)])


def test_chunk_without_source_or_text_rejected():
    no_source = SemanticChunk(ordinal=0, text="甲。", section_titles=(), sources=())
    with pytest.raises(ChunkIdentityError, match="source"):
        assign_chunk_identities("course-1", _key(), [no_source])
    empty = SemanticChunk(ordinal=0, text="", section_titles=(), sources=_pdf_chunk(0, "x", 1).sources)
    with pytest.raises(ChunkIdentityError, match="text"):
        assign_chunk_identities("course-1", _key(), [empty])


def test_assign_rejects_wrong_types():
    with pytest.raises(TypeError):
        assign_chunk_identities("course-1", ("doc-1", HASH_A, PV_PDF), [_pdf_chunk(0, "甲。", 1)])  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        assign_chunk_identities("course-1", _key(), ["甲。"])  # type: ignore[list-item]


def test_empty_chunk_list_yields_empty_tuple():
    assert assign_chunk_identities("course-1", _key(), []) == ()


# ---------------------------------------------------------------- extraction cache key


def _identity(course_id: str = "course-1") -> ChunkIdentity:
    return assign_chunk_identities(course_id, _key(), [_pdf_chunk(0, "甲。", 1)])[0]


def test_cache_key_follows_documented_formula():
    identity = _identity()
    digest = hashlib.sha256(
        _canon(
            [
                "smartsketch.extraction-cache/1",
                "course-1",
                identity.chunk_id,
                identity.text_sha256,
                "extract_entities",
                1,
                PROMPT_SHA,
                "model-primary-2026-01-01",
            ]
        )
    ).hexdigest()
    assert _cache_key(identity) == f"xc_{digest}"


def test_cache_key_is_deterministic():
    assert _cache_key(_identity()) == _cache_key(_identity())


@pytest.mark.parametrize(
    "override",
    [
        {"prompt_version": 2},
        {"prompt_sha256": PROMPT_SHA_2},
        {"prompt_purpose": "extract_relations"},
        {"model_id": "model-backup-2026-01-01"},
    ],
    ids=["prompt_version", "prompt_sha256", "purpose", "model_id"],
)
def test_prompt_or_model_change_invalidates_cache(override):
    identity = _identity()
    assert _cache_key(identity, **override) != _cache_key(identity)


def test_cache_key_changes_if_text_hash_differs_for_same_chunk_id():
    # 防御块不可变被破坏：同一块 ID 若文本不同，缓存不得命中。
    identity = _identity()
    tampered = ChunkIdentity(
        course_id=identity.course_id,
        document_id=identity.document_id,
        revision_id=identity.revision_id,
        chunk_id=identity.chunk_id,
        ordinal=identity.ordinal,
        text_sha256=text_sha256("乙。"),
        sources=identity.sources,
    )
    assert _cache_key(tampered) != _cache_key(identity)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("prompt_version", 0),
        ("prompt_version", -1),
        ("prompt_version", True),
        ("prompt_version", "1"),
        ("prompt_sha256", "C" * 64),
        ("prompt_sha256", "c" * 63),
        ("prompt_sha256", "sha256:" + "c" * 64),
        ("prompt_purpose", ""),
        ("prompt_purpose", "Extract"),
        ("prompt_purpose", "extract entities"),
        ("model_id", ""),
        ("model_id", "   "),
        ("model_id", None),
    ],
)
def test_bad_cache_key_parameters_rejected(field, value):
    with pytest.raises(ChunkIdentityError, match=field):
        _cache_key(_identity(), **{field: value})


def test_cache_key_rejects_non_identity():
    with pytest.raises(TypeError):
        extraction_cache_key(  # type: ignore[arg-type]
            "rev_x-0", prompt_purpose="extract_entities", prompt_version=1, prompt_sha256=PROMPT_SHA, model_id="m"
        )


def test_cache_key_revalidates_identity_fields():
    identity = _identity()
    broken = ChunkIdentity(
        course_id=identity.course_id,
        document_id=identity.document_id,
        revision_id=identity.revision_id,
        chunk_id=identity.revision_id + "-1",  # 与 ordinal 0 不符
        ordinal=identity.ordinal,
        text_sha256=identity.text_sha256,
        sources=identity.sources,
    )
    with pytest.raises(ChunkIdentityError, match="chunk_id"):
        _cache_key(broken)


def test_cache_model_id_uses_requested_model_of_producing_call():
    # 实际给出结果的调用所请求的模型 ID（主用或备用），不取响应里可能为别名展开或为空的 model 字段。
    result = ModelResult(
        text="{}",
        model_requested="model-backup-2026-01-01",
        model_responded="model-backup-latest",
        usage=None,
        finish_reason="stop",
    )
    assert cache_model_id(result) == "model-backup-2026-01-01"
    no_response_model = ModelResult(
        text="{}", model_requested="model-primary", model_responded=None, usage=None, finish_reason="stop"
    )
    assert cache_model_id(no_response_model) == "model-primary"


def test_cache_model_id_rejects_non_result():
    with pytest.raises(TypeError):
        cache_model_id("model-primary")  # type: ignore[arg-type]


def test_module_imports_only_stdlib_and_project():
    import ast

    path = Path(__file__).resolve().parents[2] / "src/backend/app/services/chunk_identity.py"
    tree = ast.parse(path.read_text("utf-8"))
    allowed = {"__future__", "hashlib", "json", "re", "dataclasses", "collections", "typing", "app"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            names = [node.module or ""]
        else:
            continue
        for name in names:
            assert name.split(".")[0] in allowed, name
