"""D09：资料修订 ID、块 ID 与抽取缓存键。

依据：ADR-012 修订 1 决定 9、`specs/teacher-review-publish.md` V2「资料修订」「文本块不可变」、
`docs/architecture.md`「解析输出与来源定位（D01）」、`docs/integrations.md`「模型版本与向量空间」。

派生公式（方案版本 1；任何改动都会让已持久化的块 ID 失配，必须升级方案标签并走迁移）：

- 规范编码 ``canon(parts)`` = ``json.dumps(parts, ensure_ascii=False, separators=(",", ":"))``
  的 UTF-8 字节。按 JSON 数组编码，字段边界无歧义，与字段内容无关。
- ``revision_id`` = ``"rev_" + sha256(canon(["smartsketch.revision/1", document_id,
  content_hash, parser_version])).hexdigest()``。资料修订即 ``RevisionKey`` 三元组；
  ``document_id`` 与规格 V2 的 ``material_id`` 为同一概念（ADR-016 决定 6），
  SQLite ``materials.id`` 为全库主键，因此修订 ID 天然不跨课程复用。
- 块 ID = ``f"{revision_id}-{ordinal}"``，``ordinal`` 为 D08 ``SemanticChunk.ordinal``
  （十进制、无前导零、从 0 起）。块 ID 可由 ``split_chunk_id`` 无损拆回修订 ID 与序号。
- 抽取缓存键 = ``"xc_" + sha256(canon(["smartsketch.extraction-cache/1", course_id, chunk_id,
  text_sha256, prompt_purpose, prompt_version, prompt_sha256, model_id])).hexdigest()``。
  含 ``course_id``（缓存不跨课程命中）、块文本哈希（即便块不可变被破坏也不误命中）、
  提示词用途/版本/模板哈希与实际给出结果的模型 ID（任一变化即失效）。

本模块只做纯计算：不读写存储、不调用模型、不记录日志。块文本不进入任何 ``repr``。
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable
from dataclasses import dataclass

from app.services.ai.client import ModelResult
from app.services.chunking import ChunkSource, SemanticChunk
from app.services.parsers.models import RevisionKey

__all__ = [
    "CACHE_KEY_SCHEME",
    "REVISION_SCHEME",
    "ChunkIdentity",
    "ChunkIdentityError",
    "assign_chunk_identities",
    "cache_model_id",
    "derive_chunk_id",
    "derive_revision_id",
    "extraction_cache_key",
    "revision_id_for",
    "split_chunk_id",
    "text_sha256",
]

#: 修订 ID 公式的方案标签，进入哈希输入。
REVISION_SCHEME = "smartsketch.revision/1"
#: 抽取缓存键公式的方案标签，进入哈希输入。
CACHE_KEY_SCHEME = "smartsketch.extraction-cache/1"

_CONTENT_HASH_RE = re.compile(r"sha256:[0-9a-f]{64}")
_REVISION_ID_RE = re.compile(r"rev_[0-9a-f]{64}")
_CHUNK_ID_RE = re.compile(r"(rev_[0-9a-f]{64})-(0|[1-9][0-9]*)")
_PROMPT_SHA_RE = re.compile(r"[0-9a-f]{64}")
_PURPOSE_RE = re.compile(r"[a-z][a-z0-9_]*")


class ChunkIdentityError(ValueError):
    """输入不满足身份派生的前置条件。出现即说明调用方实现有缺陷。"""


def _canon(parts: list[object]) -> bytes:
    return json.dumps(parts, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def _is_int(value: object) -> bool:
    return type(value) is int


def _check_nonblank(name: str, value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ChunkIdentityError(f"{name} 必须是非空字符串，收到 {value!r}")
    return value


def _check_content_hash(value: object) -> str:
    if not isinstance(value, str) or not _CONTENT_HASH_RE.fullmatch(value):
        raise ChunkIdentityError(f"content_hash 必须形如 sha256:<64 位小写十六进制>，收到 {value!r}")
    return value


def _check_parser_version(value: object) -> str:
    if not isinstance(value, str) or not value or any(ch.isspace() for ch in value):
        raise ChunkIdentityError(f"parser_version 必须是不含空白的非空字符串，收到 {value!r}")
    return value


def _check_revision_id(value: object) -> str:
    if not isinstance(value, str) or not _REVISION_ID_RE.fullmatch(value):
        raise ChunkIdentityError(f"revision_id 必须形如 rev_<64 位小写十六进制>，收到 {value!r}")
    return value


def _check_ordinal(value: object) -> int:
    if not _is_int(value) or value < 0:  # type: ignore[operator]
        raise ChunkIdentityError(f"ordinal 必须是 ≥ 0 的整数，收到 {value!r}")
    return value  # type: ignore[return-value]


# ---------------------------------------------------------------- 修订与块 ID


def derive_revision_id(document_id: str, content_hash: str, parser_version: str) -> str:
    """由资料修订三元组确定性派生 ``revision_id``。校验规则与 ``RevisionKey`` 一致。"""
    _check_nonblank("document_id", document_id)
    _check_content_hash(content_hash)
    _check_parser_version(parser_version)
    digest = hashlib.sha256(_canon([REVISION_SCHEME, document_id, content_hash, parser_version])).hexdigest()
    return f"rev_{digest}"


def revision_id_for(key: RevisionKey) -> str:
    """``derive_revision_id`` 的 ``RevisionKey`` 形式。"""
    if not isinstance(key, RevisionKey):
        raise TypeError(f"key 必须是 RevisionKey，收到 {type(key).__name__}")
    return derive_revision_id(key.document_id, key.content_hash, key.parser_version)


def derive_chunk_id(revision_id: str, ordinal: int) -> str:
    """块 ID = ``revision_id`` + ``-`` + 十进制块序号。"""
    _check_revision_id(revision_id)
    _check_ordinal(ordinal)
    return f"{revision_id}-{ordinal}"


def split_chunk_id(chunk_id: str) -> tuple[str, int]:
    """把规范块 ID 拆回 ``(revision_id, ordinal)``；非规范形式（前导零、全角数字等）一律拒绝。"""
    match = _CHUNK_ID_RE.fullmatch(chunk_id) if isinstance(chunk_id, str) else None
    if match is None or not match.group(2).isascii():
        raise ChunkIdentityError(f"chunk_id 不是规范形式 rev_<64 位十六进制>-<序号>，收到 {chunk_id!r}")
    return match.group(1), int(match.group(2))


def text_sha256(text: str) -> str:
    """块文本的 UTF-8 SHA-256，格式与 ``content_hash`` 相同（``sha256:<hex>``）。"""
    if not isinstance(text, str):
        raise ChunkIdentityError(f"text 必须是字符串，收到 {type(text).__name__}")
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class ChunkIdentity:
    """一个语义块的身份与出处。只带文本哈希，不带原文（原文由 D10 按块 ID 持久化）。"""

    course_id: str
    document_id: str
    revision_id: str
    chunk_id: str
    ordinal: int
    text_sha256: str
    sources: tuple[ChunkSource, ...]


def assign_chunk_identities(
    course_id: str, revision: RevisionKey, chunks: Iterable[SemanticChunk]
) -> tuple[ChunkIdentity, ...]:
    """为同一资料修订的 D08 语义块逐个分配身份。

    块序号必须从 0 起连续（D08 保证）；每块必须有非空文本与至少一个出处。
    同文不同处的块因序号不同而身份不同，各自保留自己的 ``sources``。
    """
    _check_nonblank("course_id", course_id)
    revision_id = revision_id_for(revision)
    ordered = list(chunks)
    identities: list[ChunkIdentity] = []
    for expected, chunk in enumerate(ordered):
        if not isinstance(chunk, SemanticChunk):
            raise TypeError(f"chunks 必须只含 SemanticChunk，收到 {type(chunk).__name__}")
        if not _is_int(chunk.ordinal) or chunk.ordinal != expected:
            raise ChunkIdentityError(f"块 ordinal 必须从 0 起连续：位置 {expected} 收到 {chunk.ordinal!r}")
        if not isinstance(chunk.text, str) or not chunk.text:
            raise ChunkIdentityError(f"块 {expected} 的 text 为空")
        if not chunk.sources or not all(isinstance(s, ChunkSource) for s in chunk.sources):
            raise ChunkIdentityError(f"块 {expected} 没有有效的 source 出处")
        identities.append(
            ChunkIdentity(
                course_id=course_id,
                document_id=revision.document_id,
                revision_id=revision_id,
                chunk_id=derive_chunk_id(revision_id, expected),
                ordinal=expected,
                text_sha256=text_sha256(chunk.text),
                sources=tuple(chunk.sources),
            )
        )
    return tuple(identities)


# ---------------------------------------------------------------- 抽取缓存键


def cache_model_id(result: ModelResult) -> str:
    """缓存键使用的模型 ID：实际给出结果的那次调用所**请求**的模型 ID（主用或备用）。

    不取 ``model_responded``：它在调用前无法得知（缓存查找发生在调用前），且可能为空。
    """
    if not isinstance(result, ModelResult):
        raise TypeError(f"result 必须是 ModelResult，收到 {type(result).__name__}")
    return result.model_requested


def extraction_cache_key(
    identity: ChunkIdentity,
    *,
    prompt_purpose: str,
    prompt_version: int,
    prompt_sha256: str,
    model_id: str,
) -> str:
    """块级抽取结果的缓存键。

    ``prompt_purpose``/``prompt_version``/``prompt_sha256`` 取 E01 ``PromptTemplate`` 的
    ``purpose``/``version``/``sha256``；``model_id`` 查找时取将要请求的模型 ID，写入时取
    ``cache_model_id(result)``。
    """
    if not isinstance(identity, ChunkIdentity):
        raise TypeError(f"identity 必须是 ChunkIdentity，收到 {type(identity).__name__}")
    _check_nonblank("course_id", identity.course_id)
    _check_nonblank("document_id", identity.document_id)
    if split_chunk_id(identity.chunk_id) != (_check_revision_id(identity.revision_id), _check_ordinal(identity.ordinal)):
        raise ChunkIdentityError("chunk_id 与 revision_id/ordinal 不一致")
    _check_content_hash_like("text_sha256", identity.text_sha256)
    if not isinstance(prompt_purpose, str) or not _PURPOSE_RE.fullmatch(prompt_purpose):
        raise ChunkIdentityError(f"prompt_purpose 必须是小写标识符，收到 {prompt_purpose!r}")
    if not _is_int(prompt_version) or prompt_version < 1:
        raise ChunkIdentityError(f"prompt_version 必须是 ≥ 1 的整数，收到 {prompt_version!r}")
    if not isinstance(prompt_sha256, str) or not _PROMPT_SHA_RE.fullmatch(prompt_sha256):
        raise ChunkIdentityError(f"prompt_sha256 必须是 64 位小写十六进制，收到 {prompt_sha256!r}")
    _check_nonblank("model_id", model_id)
    digest = hashlib.sha256(
        _canon(
            [
                CACHE_KEY_SCHEME,
                identity.course_id,
                identity.chunk_id,
                identity.text_sha256,
                prompt_purpose,
                prompt_version,
                prompt_sha256,
                model_id,
            ]
        )
    ).hexdigest()
    return f"xc_{digest}"


def _check_content_hash_like(name: str, value: object) -> None:
    if not isinstance(value, str) or not _CONTENT_HASH_RE.fullmatch(value):
        raise ChunkIdentityError(f"{name} 必须形如 sha256:<64 位小写十六进制>，收到 {value!r}")
