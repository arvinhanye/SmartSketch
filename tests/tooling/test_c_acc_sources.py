"""C-ACC-A：持久化出处只读核验工具（`evaluation/audit_persisted_sources.py`），离线。

工具调用真实的 `read_knowledge_point`（与 API 知识点详情同一路径），但把它依赖的 SQLite 连接换成只读
（`mode=ro&immutable=1` + `query_only`）；图谱只经 `GraphReader` / `Neo4jRepository.read`（读路由）。
这里用临时迁移库 + 假图谱读取器，证明分类与计数正确、只读连接拒绝写入、输出不含正文。
"""

from __future__ import annotations

import importlib.util
import json
import sqlite3
import uuid
from pathlib import Path

import pytest

from app.repositories.graph_read import NodeEvidence
from app.repositories.sqlite import connect, migrate

ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location("audit_persisted_sources", ROOT / "evaluation/audit_persisted_sources.py")
audit = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(audit)

COURSE, OTHER = "c" * 32, "o" * 32
SHA = "sha256:" + "0" * 64
TEXT = "栈是只允许在一端进行插入和删除操作的线性表。"


def _db(tmp_path: Path) -> str:
    url = f"sqlite:///{(tmp_path / 'm.sqlite3').as_posix()}"
    migrate(url)
    with connect(url) as db:
        db.execute("INSERT INTO users (id, username, password_hash, role) VALUES (?, 'teacher1', ?, 'teacher')",
                   ("u" * 32, "$argon2id$v=19$m=65536,t=3,p=4$c2FsdA$aGFzaA"))
        for cid in (COURSE, OTHER):
            db.execute("INSERT INTO courses (id, name, teacher_id) VALUES (?, '课', ?)", (cid, "u" * 32))
            db.execute("INSERT INTO materials (id, course_id, filename, format, size_bytes, content_hash, storage_name)"
                       " VALUES (?, ?, ?, 'pdf', 1, ?, ?)", (f"m-{cid[0]}", cid, f"{cid[0]}.pdf", SHA, f"s-{cid[0]}"))
    return url


def _chunk(url: str, course_id: str, ordinal: int, *, page: int | None = 3, section: str | None = None) -> str:
    """按真实约束写一个文本块（修订 ID ``rev_`` + 64 位十六进制；块 ID = 修订 ID-序号），返回块 ID。"""
    locator = {"page": page} if page is not None else {"section_titles": [section], "paragraph": 1}
    sources = json.dumps([{"block_ordinal": 0, "start": 0, "end": len(TEXT), "locator": locator}], ensure_ascii=False)
    rev = "rev_" + ("c" if course_id == COURSE else "d") * 64          # 修订 ID 只允许十六进制
    with connect(url) as db:
        db.execute("INSERT OR IGNORE INTO material_revisions (revision_id, course_id, material_id, parser_version,"
                   " content_hash) VALUES (?, ?, ?, 'pdf/2+chunk/1', ?)", (rev, course_id, f"m-{course_id[0]}", SHA))
        db.execute("INSERT INTO chunks (chunk_id, revision_id, course_id, material_id, ordinal, text, text_sha256,"
                   " section_titles, sources) VALUES (?, ?, ?, ?, ?, ?, ?, '[]', ?)",
                   (f"{rev}-{ordinal}", rev, course_id, f"m-{course_id[0]}", ordinal, TEXT, SHA, sources))
    return f"{rev}-{ordinal}"


class FakeReader:
    def __init__(self, nodes, evidence):
        self._nodes, self._evidence = nodes, evidence

    def nodes(self, scope, reader, kp_ids=None):
        return [n for n in self._nodes if kp_ids is None or n["kp_id"] in kp_ids]

    def edges(self, scope, reader, kp_ids=None):
        return []

    def evidence(self, scope, reader, kp_ids):
        return [e for e in self._evidence if e.kp_id in set(kp_ids)]

    def chapters(self, scope, reader):
        return []


def _node(kp_id, source="ai"):
    return {"kp_id": kp_id, "name": f"名{kp_id}", "type": "concept", "definition": "d", "confidence": 0.9,
            "status": "draft", "source": source, "locked": False, "revision": 1, "chapter_id": None}


def _run(url, nodes, evidence, cross=0):
    return audit.audit_course(FakeReader(nodes, evidence), url, course_id=COURSE, effective_task_ids=("t1",),
                              cross_course_evidence=lambda: cross)


def test_counts_api_refs_with_location_and_separates_source_label(tmp_path):
    url = _db(tmp_path)
    k1 = _chunk(url, COURSE, 0, page=3)
    k2 = _chunk(url, COURSE, 1, page=None, section="第3章 栈")
    nodes = [_node("a"), _node("b"), _node("m", source="manual")]
    evidence = [NodeEvidence("a", k1, "m-c", 0, 6), NodeEvidence("b", k2, None, None, None)]
    report = _run(url, nodes, evidence)
    assert report["nodes"] == 3
    assert report["source_label"] == {"ai": 2, "manual": 1}
    assert report["ai_nodes_with_located_refs"] == 2
    assert report["refs"] == {"total": 2, "with_page": 1, "with_section_path": 1, "with_document_name": 2}
    assert report["manual_nodes_without_refs"] == 1                  # 手工无来源是显式空态，不算缺陷
    assert report["defects"] == {"ai_nodes_without_located_refs": [], "dangling_chunks": [],
                                 "foreign_documents": [], "cross_course_evidence_edges": 0, "unreadable_nodes": []}


def test_flags_ai_node_without_locatable_source_dangling_chunk_and_foreign_document(tmp_path):
    url = _db(tmp_path)
    k1 = _chunk(url, COURSE, 0)
    kx = _chunk(url, OTHER, 0)
    nodes = [_node("a"), _node("b"), _node("c")]
    evidence = [NodeEvidence("a", k1, "m-o", 0, 6),                # 文档属于别的课
                NodeEvidence("b", "gone", None, None, None),       # 块不在 SQLite：悬空
                NodeEvidence("c", kx, None, None, None)]           # 块属于别的课：本课查不到
    report = _run(url, nodes, evidence, cross=1)
    defects = report["defects"]
    assert set(defects["ai_nodes_without_located_refs"]) == {"b", "c"}
    assert defects["dangling_chunks"] == sorted(["gone", kx])
    assert defects["foreign_documents"] == ["m-o"]
    assert defects["cross_course_evidence_edges"] == 1


def test_report_has_no_text_and_a_stable_digest(tmp_path):
    url = _db(tmp_path)
    k1 = _chunk(url, COURSE, 0)
    nodes, evidence = [_node("a")], [NodeEvidence("a", k1, "m-c", 0, 6)]
    first, second = _run(url, nodes, evidence), _run(url, nodes, evidence)
    assert TEXT not in json.dumps(first, ensure_ascii=False) and TEXT[:6] not in json.dumps(first, ensure_ascii=False)
    assert first["refs_digest"] == second["refs_digest"] and len(first["refs_digest"]) == 64


def test_readonly_connector_rejects_writes_and_leaves_the_file_unchanged(tmp_path):
    url = _db(tmp_path)
    path = Path(url.removeprefix("sqlite:///"))
    before = audit.file_sha256(path)
    with audit.readonly_connect(url) as db:
        assert db.execute("SELECT count(*) FROM courses").fetchone() == (2,)
        with pytest.raises(sqlite3.OperationalError):
            db.execute("DELETE FROM courses")
    assert audit.file_sha256(path) == before


def test_patched_service_path_uses_only_readonly_connections(tmp_path, monkeypatch):
    url = _db(tmp_path)
    k1 = _chunk(url, COURSE, 0)
    opened: list[str] = []
    real = audit.readonly_connect

    def spy(sqlite_url):
        opened.append(sqlite_url)
        return real(sqlite_url)

    monkeypatch.setattr(audit, "readonly_connect", spy)
    with audit.readonly_repositories():
        _run(url, [_node("a")], [NodeEvidence("a", k1, "m-c", 0, 6)])
    assert opened                                                   # 详情路径确实经由只读连接
    from app.repositories import chunks, materials
    assert chunks.connect is connect and materials.connect is connect   # 退出后恢复原连接
