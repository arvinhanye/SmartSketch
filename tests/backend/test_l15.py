"""L15 权限隔离和不可信文件名回归固化；真实 HTTP/SQLite，图读取记录 scope。"""
import pytest
from app.repositories.courses import add_member
from app.repositories.graph_read import NodeEvidence
from test_f07 import PAGE, kp, s, valid_schema  # noqa: F401
from test_l12 import _material


def test_outsider_cannot_read_kp_filename(s):
    _material(s.url, s.course.id, "m1", "本课资料.pdf")
    s.add_chunk("k", [(PAGE, "课程来源")])
    version = s.publish()
    s.reader.put(version, nodes=[kp("a", status="approved")], evidence=[NodeEvidence("a", "k", "m1", 0, 2)])
    response = s.get("/kp/a", s.outsider)
    assert response.status_code == 403
    assert "本课资料.pdf" not in response.text
    assert s.reader.calls == []


@pytest.mark.parametrize("path", ["/progress", "/recommend"])
def test_outsider_cannot_read_learning(s, path):
    assert s.get(path, s.outsider).status_code == 403
    assert s.reader.calls == []


def test_teacher_account_as_course_student_only_reads_published(s):
    add_member(s.url, course_id=s.course.id, user_id=s.outsider.id, role="student", added_by=s.teacher.id)
    s.reader.put("draft", nodes=[kp("draft-secret")])
    assert s.get("/graph", s.outsider).status_code == 404
    assert s.reader.calls == []
    version = s.publish()
    s.reader.put(version, nodes=[kp("published", status="approved")])
    response = s.get("/graph", s.outsider)
    assert response.status_code == 200
    assert [n["id"] for n in response.json()["nodes"]] == ["published"]
    assert all(scope.version_id == version and role == "student" for _, scope, role in s.reader.calls)


@pytest.mark.parametrize("schema", ["SourceRef", "Citation"])
def test_document_name_limit_is_enforced_by_contract(schema):
    body = {"chunk_id": "k", "document_id": "m", "page": 1, "text": "原文", "document_name": "a" * 256}
    if schema == "Citation": body["index"] = 1
    assert not valid_schema(schema, body)
    body["document_name"] = "a" * 255
    assert valid_schema(schema, body)
