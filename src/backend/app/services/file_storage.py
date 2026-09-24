"""C05 文件落盘边界：把上传字节流校验后原子写入存储根目录。

- 只接受 PDF、DOCX、TXT、Markdown；扩展名、声明类型与内容特征三者须一致，
  否则 ``UNSUPPORTED_FORMAT``（``src/contracts/errors.v1.md``）。
- 边读边计数，超过 ``max_bytes`` 立即中止，``FILE_TOO_LARGE``，``details.limit_bytes``。
- 先写同目录临时文件，``fsync`` 后以硬链接发布为随机存储名（不覆盖已有文件），
  任何失败都删除临时文件，目录里不留半文件。
- 存储名只由随机数和校验后的格式决定；原始文件名只作元数据返回，从不参与路径拼接。

本模块不写数据库（C06），不处理 HTTP（C07）。配置由调用方传入根目录与上限。
"""

from __future__ import annotations

import hashlib
import os
import re
import secrets
import tempfile
import zipfile
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any, BinaryIO, Literal, TypeVar

DocumentFormat = Literal["pdf", "docx", "txt", "markdown"]

SUPPORTED_FORMATS: tuple[DocumentFormat, ...] = ("pdf", "docx", "txt", "markdown")
DEFAULT_CHUNK_SIZE = 64 * 1024
MAX_FILENAME_BYTES = 255
_PUBLISH_ATTEMPTS = 8
_TEMP_PREFIX = ".upload-"
_TEMP_SUFFIX = ".part"

DOCX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"

_EXTENSIONS: dict[str, DocumentFormat] = {
    ".pdf": "pdf",
    ".docx": "docx",
    ".txt": "txt",
    ".md": "markdown",
    ".markdown": "markdown",
}
_STORED_SUFFIX: dict[DocumentFormat, str] = {
    "pdf": ".pdf",
    "docx": ".docx",
    "txt": ".txt",
    "markdown": ".md",
}
_DECLARED_TYPES: dict[DocumentFormat, frozenset[str]] = {
    "pdf": frozenset({"application/pdf"}),
    "docx": frozenset({DOCX_MEDIA_TYPE}),
    "txt": frozenset({"text/plain"}),
    "markdown": frozenset({"text/markdown", "text/x-markdown", "text/plain"}),
}
# 浏览器对未知扩展名（常见于 .md）不给或给通用类型：此时只靠扩展名 + 内容嗅探。
_GENERIC_TYPES = frozenset({"", "application/octet-stream"})
_MAGIC: dict[DocumentFormat, bytes] = {"pdf": b"%PDF-", "docx": b"PK\x03\x04"}
# 文本类不得以这些二进制格式的签名开头（防止把 PDF/ZIP 改名为 .txt/.md）。
_TEXT_FORBIDDEN_PREFIXES = (b"%PDF-", b"PK\x03\x04")
# 允许 \t \n \v \f \r 与 ESC；其余 C0 控制字符（含 NUL）视为二进制内容。
_TEXT_FORBIDDEN_BYTES = bytes(set(range(0x00, 0x20)) - {0x09, 0x0A, 0x0B, 0x0C, 0x0D, 0x1B})
_DOCX_REQUIRED_ENTRIES = ("[Content_Types].xml", "word/document.xml")
_STORAGE_NAME = re.compile(r"[0-9a-f]{32}\.(?:pdf|docx|txt|md)")

T = TypeVar("T")


class FileStorageError(Exception):
    """落盘边界的可映射错误；``code`` 取自 ``api.v1.yaml`` 的 ``ErrorCode``。"""

    code = "INTERNAL_ERROR"

    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details: dict[str, Any] = details or {}


class UnsupportedFormatError(FileStorageError):
    """扩展名、声明类型或内容特征不属于 PDF/DOCX/TXT/Markdown（415）。"""

    code = "UNSUPPORTED_FORMAT"

    def __init__(self, reason: str) -> None:
        super().__init__(
            "仅支持 PDF、DOCX、TXT、Markdown 资料",
            {"reason": reason, "supported": list(SUPPORTED_FORMATS)},
        )


class FileTooLargeError(FileStorageError):
    """超过单文件上限（413），``details.limit_bytes`` 给出数值。"""

    code = "FILE_TOO_LARGE"

    def __init__(self, limit_bytes: int) -> None:
        super().__init__(f"文件超过上限 {limit_bytes} 字节", {"limit_bytes": limit_bytes})


class InvalidFilenameError(FileStorageError):
    """原始文件名含路径成分、控制字符或超长（422）。"""

    code = "VALIDATION_ERROR"

    def __init__(self, reason: str) -> None:
        super().__init__("文件名无效", {"fields": {"file": reason}})


class StorageWriteError(FileStorageError):
    """存储目录不可写、磁盘满或 fsync 失败（503）。"""

    code = "STORAGE_UNAVAILABLE"

    def __init__(self, message: str = "资料存储暂不可用") -> None:
        super().__init__(message)


@dataclass(frozen=True)
class StoredFile:
    """落盘结果，供 C06 写资料/修订记录。"""

    storage_name: str
    path: Path
    original_filename: str
    format: DocumentFormat
    size_bytes: int
    content_hash: str  # "sha256:<hex>"，对应 specs/teacher-review-publish.md 修订的 content_hash


def iter_file(fileobj: BinaryIO, chunk_size: int = DEFAULT_CHUNK_SIZE) -> Iterator[bytes]:
    """把二进制文件对象（如 ``UploadFile.file``）按块读出。"""
    while chunk := fileobj.read(chunk_size):
        yield chunk


def _random_stem() -> str:
    return secrets.token_hex(16)


def _disk(operation: Callable[..., T], *args: Any) -> T:
    """执行本模块自己的磁盘操作；OSError 统一映射为 STORAGE_UNAVAILABLE。"""
    try:
        return operation(*args)
    except OSError:
        raise StorageWriteError() from None


def _write_all(fd: int, data: bytes) -> None:
    view = memoryview(data)
    while view:
        written = os.write(fd, view)
        view = view[written:]


def _check_filename(filename: object) -> str:
    if not isinstance(filename, str) or not filename:
        raise InvalidFilenameError("empty")
    if filename in {".", ".."} or "/" in filename or "\\" in filename:
        raise InvalidFilenameError("path_component")
    if any(ord(character) < 0x20 or ord(character) == 0x7F for character in filename):
        raise InvalidFilenameError("control_character")
    try:
        encoded = filename.encode("utf-8")
    except UnicodeEncodeError:
        raise InvalidFilenameError("encoding") from None
    if len(encoded) > MAX_FILENAME_BYTES:
        raise InvalidFilenameError("too_long")
    return filename


def _format_from_extension(filename: str) -> DocumentFormat:
    extension = os.path.splitext(filename)[1].lower()
    document_format = _EXTENSIONS.get(extension)
    if document_format is None:
        raise UnsupportedFormatError("extension")
    return document_format


def _check_declared_type(document_format: DocumentFormat, declared: str | None) -> None:
    media_type = (declared or "").split(";", 1)[0].strip().lower()
    if media_type in _GENERIC_TYPES:
        return
    if media_type not in _DECLARED_TYPES[document_format]:
        raise UnsupportedFormatError("declared_type")


class _Sniffer:
    """在流上逐块检查内容特征，尽早拒绝伪扩展名。"""

    def __init__(self, document_format: DocumentFormat) -> None:
        self.format = document_format
        self.head = b""
        self.head_verified = False

    def feed(self, chunk: bytes) -> None:
        if self.format in ("txt", "markdown"):
            if chunk.translate(None, _TEXT_FORBIDDEN_BYTES) != chunk:
                raise UnsupportedFormatError("content_mismatch")
        if self.head_verified:
            return
        self.head += chunk[:8]
        self._check_head(final=False)

    def finish(self, size_bytes: int) -> None:
        if size_bytes == 0:
            raise UnsupportedFormatError("empty")
        self._check_head(final=True)

    def _check_head(self, final: bool) -> None:
        if self.format in _MAGIC:
            magic = _MAGIC[self.format]
            if len(self.head) >= len(magic):
                if not self.head.startswith(magic):
                    raise UnsupportedFormatError("content_mismatch")
                self.head_verified = True
            elif not magic.startswith(self.head) or final:
                raise UnsupportedFormatError("content_mismatch")
            return
        longest = max(len(prefix) for prefix in _TEXT_FORBIDDEN_PREFIXES)
        if any(self.head.startswith(prefix) for prefix in _TEXT_FORBIDDEN_PREFIXES):
            raise UnsupportedFormatError("content_mismatch")
        if len(self.head) >= longest or final:
            self.head_verified = True


def _check_docx_structure(path: Path) -> None:
    try:
        with zipfile.ZipFile(path) as archive:
            names = set(archive.namelist())
    except OSError:
        raise StorageWriteError() from None
    except (zipfile.BadZipFile, ValueError, EOFError):
        raise UnsupportedFormatError("content_mismatch") from None
    if not all(entry in names for entry in _DOCX_REQUIRED_ENTRIES):
        raise UnsupportedFormatError("content_mismatch")


def _fsync_directory(directory: Path) -> None:
    if os.name != "posix":
        return
    fd = os.open(directory, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


class FileStorage:
    """把上传资料落到 ``root`` 下；实例无可变状态，可在多线程间共享。"""

    def __init__(self, root: str | os.PathLike[str], max_bytes: int) -> None:
        if isinstance(max_bytes, bool) or not isinstance(max_bytes, int) or max_bytes <= 0:
            raise ValueError("max_bytes must be a positive integer")
        path = Path(root)
        _disk(path.mkdir, 0o700, True, True)
        self.root = _disk(path.resolve, True)
        if not self.root.is_dir():
            raise StorageWriteError("存储根目录不是目录")
        self.max_bytes = max_bytes

    def save(
        self, original_filename: object, declared_type: str | None, chunks: Iterable[bytes]
    ) -> StoredFile:
        """校验并落盘；失败时抛 ``FileStorageError`` 子类或流自身的异常，且不留文件。"""
        filename = _check_filename(original_filename)
        document_format = _format_from_extension(filename)
        _check_declared_type(document_format, declared_type)

        sniffer = _Sniffer(document_format)
        digest = hashlib.sha256()
        size_bytes = 0
        fd, temp_name = _disk(
            tempfile.mkstemp, _TEMP_SUFFIX, _TEMP_PREFIX, str(self.root)
        )
        temp_path = Path(temp_name)
        fd_open = True
        try:
            for chunk in chunks:  # 流自身的异常（客户端断开等）原样上抛
                if not isinstance(chunk, (bytes, bytearray, memoryview)):
                    raise TypeError("upload chunks must be bytes")
                data = bytes(chunk)
                if not data:
                    continue
                size_bytes += len(data)
                if size_bytes > self.max_bytes:
                    raise FileTooLargeError(self.max_bytes)
                sniffer.feed(data)
                digest.update(data)
                _disk(_write_all, fd, data)
            sniffer.finish(size_bytes)
            _disk(os.fsync, fd)
            fd_open = False
            _disk(os.close, fd)
            if document_format == "docx":
                _check_docx_structure(temp_path)
            final_path = self._publish(temp_path, _STORED_SUFFIX[document_format])
        finally:
            if fd_open:
                try:
                    os.close(fd)
                except OSError:
                    pass
            try:
                temp_path.unlink(missing_ok=True)
            except OSError:
                pass

        return StoredFile(
            storage_name=final_path.name,
            path=final_path,
            original_filename=filename,
            format=document_format,
            size_bytes=size_bytes,
            content_hash=f"sha256:{digest.hexdigest()}",
        )

    def path_for(self, storage_name: str) -> Path:
        """把本服务生成的存储名还原为路径；其他任何字符串都拒绝。"""
        if not isinstance(storage_name, str) or not _STORAGE_NAME.fullmatch(storage_name):
            raise ValueError("not a storage name generated by FileStorage")
        path = self.root / storage_name
        self._ensure_inside(path)
        return path

    def delete(self, storage_name: str) -> bool:
        """补偿用：删除已落盘文件；文件不存在返回 False。"""
        path = self.path_for(storage_name)
        try:
            path.unlink()
        except FileNotFoundError:
            return False
        except OSError:
            raise StorageWriteError() from None
        return True

    def _ensure_inside(self, path: Path) -> None:
        resolved = path.resolve(strict=False)
        if resolved.parent != self.root:
            raise ValueError("path escapes storage root")

    def _publish(self, temp_path: Path, suffix: str) -> Path:
        for _ in range(_PUBLISH_ATTEMPTS):
            final_path = self.root / f"{_random_stem()}{suffix}"
            self.path_for(final_path.name)
            try:
                os.link(temp_path, final_path)  # 目标已存在即失败，绝不覆盖
            except FileExistsError:
                continue
            except OSError:
                raise StorageWriteError() from None
            try:
                _fsync_directory(self.root)
            except OSError:
                try:
                    final_path.unlink()
                except OSError:
                    pass
                raise StorageWriteError() from None
            return final_path
        raise StorageWriteError("无法分配存储名")
