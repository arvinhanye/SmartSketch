"""L12：来源与问答引用带同课资料的文件名（ADR-085，契约 SourceRef/Citation 的可选 document_name）。

文件名只取自同一课程的 `materials.filename`；他课或已删除的资料省略该字段（来源本身照常返回），
查名失败不影响回答。学生不需要资料列表权限即可看到文件名。
"""
from __future__ import annotations

import sqlite3
import time
from types import SimpleNamespace

import pytest

from app.config import Settings
from app.repositories.graph_read import NodeEvidence
from app.repositories.materials import material_names
from app.repositories.sqlite import connect, migrate
from app.services.ai.client import ModelResult, StreamDelta, StreamDone
from app.services.qa import chat as chat_module
from app.services.qa.chat import ChatService, PreparedChat
from app.services.qa.citations import CitationStream, Evidence
from app.services.qa.context import ContextStats, ContextStatus, EvidenceChunk, EvidenceContext, GraphContext
from app.services.qa.generate import AnswerGeneration
from app.services.versions.resolver import PublishedVersion
from test_f07 import PAGE, SECTION, assert_schema, kp, s  # noqa: F401  (s 是夹具)

SHA = "sha256:" + "0" * 64


def _material(url, course_id, material_id, filename):
    with connect(url) as db:
        db.execute("INSERT INTO materials (id, course_id, filename, format, size_bytes, content_hash, storage_name)"
                   " VALUES (?, ?, ?, 'pdf', 1, ?, ?)", (material_id, course_id, filename, SHA, material_id))


# ---- 仓储 ----------------------------------------------------------------------------------------

def test_material_names_are_course_scoped(s):
    _material(s.url, s.course.id, "m-own", "第3章 栈与队列.pdf")
    other = "f" * 32
    with connect(s.url) as db:
        db.execute("INSERT INTO courses (id, name, teacher_id) VALUES (?, '他课', ?)", (other, s.outsider.id))
    _material(s.url, other, "m-foreign", "他课机密.pdf")
    assert material_names(s.url, course_id=s.course.id, material_ids=["m-own", "m-foreign", "m-gone"]) == {
        "m-own": "第3章 栈与队列.pdf"}
    assert material_names(s.url, course_id=s.course.id, material_ids=[]) == {}


# ---- 知识点详情 -----------------------------------------------------------------------------------

def _detail_with_sources(s, evidence):
    s.reader.put("draft", nodes=[kp("a")], evidence=evidence)
    response = s.get("/kp/a", s.teacher)
    assert response.status_code == 200, response.text
    body = response.json()
    assert_schema("KnowledgePointDetail", body)
    return body["source_refs"]


def test_kp_detail_sources_carry_document_name(s):
    _material(s.url, s.course.id, "m1", "ch3-stack-queue.pdf")
    s.add_chunk("c1", [(PAGE, "栈是只允许在一端插入和删除的线性表")])
    [ref] = _detail_with_sources(s, [NodeEvidence("a", "c1", "m1", 0, 2)])
    assert ref["document_name"] == "ch3-stack-queue.pdf" and ref["page"] == 3


def test_document_name_never_crosses_courses(s):
    other = "e" * 32
    with connect(s.url) as db:
        db.execute("INSERT INTO courses (id, name, teacher_id) VALUES (?, '他课', ?)", (other, s.outsider.id))
    _material(s.url, other, "m-foreign", "他课机密.pdf")
    s.add_chunk("c1", [(SECTION, "栈是线性表")])
    [ref] = _detail_with_sources(s, [NodeEvidence("a", "c1", "m-foreign", 0, 2)])
    assert "document_name" not in ref


def test_deleted_material_omits_name_but_keeps_the_source(s):
    s.add_chunk("c1", [(SECTION, "栈是线性表")])
    [ref] = _detail_with_sources(s, [NodeEvidence("a", "c1", "m-gone", 0, 2)])
    assert "document_name" not in ref and ref["section_path"].startswith("第二章 栈")


def test_student_sees_document_name_without_material_list_permission(s):
    _material(s.url, s.course.id, "m1", "ch3-stack-queue.md")
    s.add_chunk("c1", [(SECTION, "栈是线性表")])
    version_id = s.publish()
    s.reader.put(version_id, nodes=[kp("a", status="approved")], evidence=[NodeEvidence("a", "c1", "m1", 0, 2)])
    response = s.get("/kp/a", s.student)
    assert response.status_code == 200, response.text
    assert response.json()["source_refs"][0]["document_name"] == "ch3-stack-queue.md"
    assert s.client.get(f"/api/v1/courses/{s.course.id}/documents",
                        headers={"Authorization": f"Bearer {__import__('test_f07').token(s.student)}"}).status_code == 403


# ---- 问答引用 -------------------------------------------------------------------------------------

VERSION = PublishedVersion("c" * 32, "v" * 26, 1, frozenset({"revision"}))


def test_citation_carries_document_name_only_when_known():
    stream = CitationStream(VERSION, "r", [
        Evidence(1, "k1", "m1", VERSION.course_id, "revision", "栈是线性表", page=2, document_name="ch3.pdf"),
        Evidence(2, "k2", "m2", VERSION.course_id, "revision", "队列是线性表", section_path="第3章"),
    ])
    stream.feed("栈后进先出[1]。队列先进先出[2]。")
    stream.finish()
    final = stream.finalize(latency_ms=1)
    assert final["citations"][0]["document_name"] == "ch3.pdf"
    assert "document_name" not in final["citations"][1]


def _chat_service(url, answer):
    chunk = EvidenceChunk(1, "chunk-1", "revision", "m1", 2, None, "栈是只允许在一端插入和删除的线性表。",
                          0.9, ("vector",), (), 20)
    context = EvidenceContext(ContextStatus.READY, None, (chunk,), GraphContext(), 1, ContextStats())

    def supplier():
        yield StreamDelta(answer)
        yield StreamDone(ModelResult(answer, "m", "m", None, "stop"))

    generator = SimpleNamespace(generate=lambda *a, **k: AnswerGeneration(supplier, lambda: 10.0))
    service = ChatService(Settings(SQLITE_URL=url), None, None, None, generator)
    now = time.monotonic()
    return service, PreparedChat(VERSION, "r", now, now + 10, "什么是栈？", context)


@pytest.fixture
def chat_db(tmp_path):
    url = f"sqlite:///{(tmp_path / 'chat.sqlite').as_posix()}"
    migrate(url)
    with connect(url) as db:
        db.execute("INSERT INTO users(id, username, password_hash, role) VALUES (?, 'teacher', ?, 'teacher')",
                   ("u" * 32, "$argon2id$v=19$m=65536,t=3,p=4$c2FsdA$aGFzaA"))
        db.execute("INSERT INTO courses(id, name, teacher_id) VALUES (?, 'Course', ?)", (VERSION.course_id, "u" * 32))
    _material(url, VERSION.course_id, "m1", "ch3-stack-queue.pdf")
    return url


def test_chat_citations_carry_the_same_course_document_name(chat_db):
    service, prepared = _chat_service(chat_db, "栈后进先出[1]。")
    final = list(service.events(prepared))[-1]["final"]
    assert final["status"] == "answered"
    assert final["citations"][0]["document_name"] == "ch3-stack-queue.pdf"


def test_name_lookup_failure_does_not_break_the_answer(chat_db, monkeypatch):
    def broken(*args, **kwargs):
        raise sqlite3.OperationalError("database is locked")

    monkeypatch.setattr(chat_module, "material_names", broken)
    service, prepared = _chat_service(chat_db, "栈后进先出[1]。")
    final = list(service.events(prepared))[-1]["final"]
    assert final["status"] == "answered" and "document_name" not in final["citations"][0]
