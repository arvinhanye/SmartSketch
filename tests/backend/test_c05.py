"""C05: 文件落盘边界——格式校验、大小上限、原子写入、随机存储名。"""

import hashlib
import io
import os
import re
import threading
import zipfile
from pathlib import Path

import pytest

from app.services import file_storage
from app.services.file_storage import (
    FileStorage,
    FileStorageError,
    FileTooLargeError,
    InvalidFilenameError,
    StorageWriteError,
    UnsupportedFormatError,
    iter_file,
)

PDF_TYPE = "application/pdf"
DOCX_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
STORAGE_NAME = re.compile(r"^[0-9a-f]{32}\.(pdf|docx|txt|md)$")


def _pdf(body: bytes = b"") -> bytes:
    return b"%PDF-1.7\n%\xe2\xe3\xcf\xd3\n1 0 obj\n<<>>\nendobj\n" + body + b"%%EOF\n"


def _docx(extra: bytes = b"") -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("[Content_Types].xml", "<Types/>")
        archive.writestr("word/document.xml", "<w:document/>" + extra.decode())
    return buffer.getvalue()


def _zip_without_word() -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("[Content_Types].xml", "<Types/>")
        archive.writestr("xl/workbook.xml", "<workbook/>")
    return buffer.getvalue()


def _chunks(data: bytes, size: int = 7):
    for start in range(0, len(data), size):
        yield data[start : start + size]


def _entries(root: Path) -> list[str]:
    return sorted(entry.name for entry in root.iterdir())


@pytest.fixture
def root(tmp_path):
    path = tmp_path / "uploads"
    path.mkdir()
    return path


@pytest.fixture
def storage(root):
    return FileStorage(root, max_bytes=4096)


# ---------- 成功路径 ----------


@pytest.mark.parametrize(
    ("filename", "declared", "data", "fmt", "suffix"),
    [
        ("讲义.txt", "text/plain", "第一章 绪论\n数据结构\n".encode(), "txt", ".txt"),
        ("notes.md", "text/markdown", b"# Title\n\n- item\n", "markdown", ".md"),
        ("notes.markdown", "text/x-markdown", b"# Title\n", "markdown", ".md"),
        ("Slides.PDF", PDF_TYPE, _pdf(), "pdf", ".pdf"),
        ("教案.docx", DOCX_TYPE, _docx(), "docx", ".docx"),
    ],
)
def test_valid_formats_are_stored_with_metadata(storage, root, filename, declared, data, fmt, suffix):
    stored = storage.save(filename, declared, _chunks(data))

    assert stored.format == fmt
    assert stored.original_filename == filename
    assert stored.size_bytes == len(data)
    assert stored.content_hash == "sha256:" + hashlib.sha256(data).hexdigest()
    assert STORAGE_NAME.match(stored.storage_name)
    assert stored.storage_name.endswith(suffix)
    assert stored.path == root.resolve() / stored.storage_name
    assert stored.path.read_bytes() == data
    assert _entries(root) == [stored.storage_name]


@pytest.mark.parametrize("declared", [None, "", "application/octet-stream", "text/plain; charset=UTF-8"])
def test_unknown_or_generic_declared_type_falls_back_to_sniffing(storage, declared):
    stored = storage.save("readme.md", declared, [b"# hi\n"])
    assert stored.format == "markdown"


def test_storage_name_does_not_depend_on_original_filename(storage):
    first = storage.save("same.txt", "text/plain", [b"a"])
    second = storage.save("same.txt", "text/plain", [b"a"])
    assert first.storage_name != second.storage_name
    assert "same" not in first.storage_name
    assert first.content_hash == second.content_hash


def test_file_exactly_at_limit_is_accepted(root):
    storage = FileStorage(root, max_bytes=64)
    stored = storage.save("a.txt", "text/plain", _chunks(b"x" * 64, 10))
    assert stored.size_bytes == 64


def test_root_is_created_when_missing(tmp_path):
    storage = FileStorage(tmp_path / "nested" / "uploads", max_bytes=10)
    stored = storage.save("a.txt", None, [b"hi"])
    assert stored.path.parent == (tmp_path / "nested" / "uploads").resolve()


def test_path_for_and_delete_accept_only_generated_names(storage, root):
    stored = storage.save("a.txt", None, [b"hi"])
    assert storage.path_for(stored.storage_name) == stored.path
    for bad in ["../a.txt", "/etc/passwd", "a.txt", stored.storage_name + "/..", ""]:
        with pytest.raises(ValueError):
            storage.path_for(bad)
    assert storage.delete(stored.storage_name) is True
    assert storage.delete(stored.storage_name) is False
    assert _entries(root) == []


def test_iter_file_reads_binary_file_in_chunks(storage):
    data = b"line\n" * 100
    stored = storage.save("big.txt", None, iter_file(io.BytesIO(data), chunk_size=16))
    assert stored.size_bytes == len(data)


@pytest.mark.parametrize("max_bytes", [0, -1])
def test_non_positive_limit_is_rejected(root, max_bytes):
    with pytest.raises(ValueError):
        FileStorage(root, max_bytes=max_bytes)


# ---------- 文件名 / 路径穿越 ----------


@pytest.mark.parametrize(
    "filename",
    [
        "../evil.txt",
        "../../etc/passwd.txt",
        "/etc/cron.d/evil.txt",
        "..\\..\\evil.txt",
        "C:\\Users\\t\\a.txt",
        "sub/dir.txt",
        "..",
        ".",
        "",
        "a\x00.txt",
        "a\n.txt",
        "x" * 300 + ".txt",
        None,
    ],
)
def test_traversal_and_malformed_filenames_are_rejected(storage, root, tmp_path, filename):
    with pytest.raises(InvalidFilenameError) as caught:
        storage.save(filename, "text/plain", [b"hello"])
    assert caught.value.code == "VALIDATION_ERROR"
    assert _entries(root) == []
    assert sorted(p.name for p in tmp_path.iterdir()) == ["uploads"]


# ---------- 格式 / 伪扩展名 ----------


@pytest.mark.parametrize(
    ("filename", "declared", "data"),
    [
        ("tool.exe", None, b"MZ\x90\x00"),
        ("a.doc", None, b"\xd0\xcf\x11\xe0"),
        ("noext", None, b"hello"),
        (".pdf", PDF_TYPE, _pdf()),
        ("a.html", "text/html", b"<html></html>"),
        # 伪扩展名：内容特征与扩展名不符
        ("malware.pdf", PDF_TYPE, b"MZ\x90\x00\x03\x00\x00\x00" + b"\x00" * 64),
        ("elf.pdf", PDF_TYPE, b"\x7fELF\x02\x01\x01" + b"\x00" * 64),
        ("fake.docx", DOCX_TYPE, b"%PDF-1.7\nnot a zip"),
        ("sheet.docx", DOCX_TYPE, _zip_without_word()),
        ("broken.docx", DOCX_TYPE, b"PK\x03\x04" + b"\x00" * 40),
        ("binary.txt", "text/plain", b"MZ\x90\x00\x03\x00\x00\x00"),
        ("nul.md", "text/markdown", b"# ok\n\x00\x00"),
        ("pdf-as.txt", "text/plain", _pdf()),
        ("zip-as.md", None, _docx()),
        ("empty.txt", "text/plain", b""),
        ("empty.pdf", PDF_TYPE, b""),
        ("short.pdf", PDF_TYPE, b"%PD"),
        # 声明类型与扩展名冲突
        ("a.pdf", "text/plain", _pdf()),
        ("a.txt", "application/x-msdownload", b"hello"),
        ("a.md", PDF_TYPE, b"# hi"),
    ],
)
def test_unsupported_or_disguised_formats_are_rejected(storage, root, filename, declared, data):
    with pytest.raises(UnsupportedFormatError) as caught:
        storage.save(filename, declared, _chunks(data, 3))
    error = caught.value
    assert error.code == "UNSUPPORTED_FORMAT"
    assert error.details["supported"] == ["pdf", "docx", "txt", "markdown"]
    assert _entries(root) == []


def test_disguised_payload_fails_before_reading_whole_stream(storage, root):
    consumed = []

    def stream():
        for index in range(1000):
            consumed.append(index)
            yield b"MZ\x90\x00" if index == 0 else b"\x00" * 16

    with pytest.raises(UnsupportedFormatError):
        storage.save("evil.pdf", PDF_TYPE, stream())
    assert len(consumed) < 5
    assert _entries(root) == []


# ---------- 大小上限 ----------


def test_one_byte_over_limit_is_rejected_without_leftovers(root):
    storage = FileStorage(root, max_bytes=64)
    with pytest.raises(FileTooLargeError) as caught:
        storage.save("a.txt", "text/plain", _chunks(b"x" * 65, 10))
    assert caught.value.code == "FILE_TOO_LARGE"
    assert caught.value.details == {"limit_bytes": 64}
    assert _entries(root) == []


def test_oversize_stream_is_aborted_early(root):
    storage = FileStorage(root, max_bytes=100)
    consumed = []

    def endless():
        while True:
            consumed.append(1)
            yield b"y" * 30

    with pytest.raises(FileTooLargeError):
        storage.save("a.txt", None, endless())
    assert len(consumed) == 4
    assert _entries(root) == []


def test_large_pdf_over_limit_is_rejected(root):
    storage = FileStorage(root, max_bytes=len(_pdf()) + 10)
    with pytest.raises(FileTooLargeError):
        storage.save("a.pdf", PDF_TYPE, _chunks(_pdf(b"z" * 11)))
    assert _entries(root) == []


# ---------- 中断的流 / 写入失败 ----------


class ClientDisconnected(Exception):
    pass


def test_interrupted_stream_propagates_and_leaves_no_partial_file(storage, root):
    def stream():
        yield b"%PDF-1.7\n"
        yield b"partial content"
        raise ClientDisconnected("connection reset")

    with pytest.raises(ClientDisconnected):
        storage.save("a.pdf", PDF_TYPE, stream())
    assert _entries(root) == []


def test_keyboard_interrupt_also_cleans_up(storage, root):
    def stream():
        yield b"hello"
        raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        storage.save("a.txt", None, stream())
    assert _entries(root) == []


def test_non_bytes_chunk_fails_without_leftovers(storage, root):
    with pytest.raises(TypeError):
        storage.save("a.txt", None, [b"ok", "text"])
    assert _entries(root) == []


def test_fsync_failure_maps_to_storage_unavailable_and_cleans_up(storage, root, monkeypatch):
    def broken_fsync(fd):
        raise OSError(5, "I/O error")

    monkeypatch.setattr(file_storage.os, "fsync", broken_fsync)
    with pytest.raises(StorageWriteError) as caught:
        storage.save("a.txt", None, [b"hello"])
    assert caught.value.code == "STORAGE_UNAVAILABLE"
    assert isinstance(caught.value, FileStorageError)
    assert _entries(root) == []


def test_publish_failure_cleans_up_temp_file(storage, root, monkeypatch):
    def broken_link(src, dst):
        raise OSError(28, "No space left on device")

    monkeypatch.setattr(file_storage.os, "link", broken_link)
    with pytest.raises(StorageWriteError):
        storage.save("a.txt", None, [b"hello"])
    assert _entries(root) == []


def test_name_collision_never_overwrites_existing_file(storage, root, monkeypatch):
    first = storage.save("a.txt", None, [b"first"])
    names = iter([first.storage_name.split(".")[0], "b" * 32])
    monkeypatch.setattr(file_storage, "_random_stem", lambda: next(names))

    second = storage.save("a.txt", None, [b"second"])

    assert second.storage_name == "b" * 32 + ".txt"
    assert first.path.read_bytes() == b"first"
    assert second.path.read_bytes() == b"second"
    assert _entries(root) == sorted([first.storage_name, second.storage_name])


def test_concurrent_uploads_with_same_filename_do_not_overwrite(storage, root):
    payloads = [f"payload {index}\n".encode() * (index + 1) for index in range(16)]
    results = [None] * len(payloads)
    barrier = threading.Barrier(len(payloads))

    def worker(index):
        def stream():
            barrier.wait()
            yield from _chunks(payloads[index], 5)

        results[index] = storage.save("同名.txt", "text/plain", stream())

    threads = [threading.Thread(target=worker, args=(index,)) for index in range(len(payloads))]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    names = {result.storage_name for result in results}
    assert len(names) == len(payloads)
    for payload, result in zip(payloads, results):
        assert result.path.read_bytes() == payload
    assert _entries(root) == sorted(names)


def test_temp_files_are_private_and_final_file_mode_is_restrictive(storage):
    stored = storage.save("a.txt", None, [b"hi"])
    if os.name == "posix":
        assert stored.path.stat().st_mode & 0o077 == 0
