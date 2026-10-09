"""Malformed wire enums must fail at the real HTTP boundary before any edit IO."""
from __future__ import annotations

import sqlite3
import time
import uuid
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.api import graph_nodes, relations, review
from app.main import create_app
from app.repositories.accounts import insert_account
from app.repositories.courses import add_member, create_course
from app.repositories.sqlite import connect, migrate
from app.schemas.contracts import KnowledgePointStatus, KnowledgePointType, RelationType
from app.services.auth import issue_access_token
from test_f08 import assert_schema

SECRET = 'enum-regression-only-key-0123456789abcdefghij'
VALID_HASH = '$argon2id$v=19$m=65536,t=3,p=4$c2FsdA$aGFzaA'
INVALID = [
    pytest.param([], id='empty-list'),
    pytest.param(['concept'], id='singleton-list'),
    pytest.param({}, id='empty-object'),
    pytest.param({'value': 'concept'}, id='object'),
    pytest.param(True, id='true'),
    pytest.param(False, id='false'),
    pytest.param(0, id='zero'),
    pytest.param(1, id='one'),
    pytest.param(0.5, id='decimal'),
    pytest.param(None, id='null'),
    pytest.param('', id='empty-string'),
    pytest.param('not_an_enum', id='unknown-string'),
]
ROUTES = [
    pytest.param('PATCH', '/kp/k', 'type', {'expected_revision': 1, 'name': '合法修改'}, id='node-type'),
    pytest.param('PATCH', '/kp/k', 'status', {'expected_revision': 1, 'name': '合法修改'}, id='node-status'),
    pytest.param('PATCH', '/relations/r', 'type', {'from_id': 'a'}, id='relation-type'),
    pytest.param('PATCH', '/relations/r', 'status', {'from_id': 'a'}, id='relation-status'),
    pytest.param('POST', '/review/actions', 'item', {'rel_id': 'r', 'action': 'approve'}, id='review-item'),
    pytest.param('POST', '/review/actions', 'action',
                 {'item': 'low_confidence_relation', 'rel_id': 'r'}, id='review-action'),
]


@pytest.fixture
def http_env(tmp_path, monkeypatch):
    url = f'sqlite:///{tmp_path / "state.sqlite3"}'
    migrate(url)
    teacher = insert_account(url, account_id=uuid.uuid4().hex, username='teacher',
                             password_hash=VALID_HASH, role='teacher')
    student = insert_account(url, account_id=uuid.uuid4().hex, username='student',
                             password_hash=VALID_HASH, role='student')
    course = create_course(url, name='Enum regression', description=None, creator_id=teacher.id)
    add_member(url, course_id=course.id, user_id=student.id, role='student', added_by=teacher.id)
    monkeypatch.setenv('SQLITE_URL', url)
    monkeypatch.setenv('AUTH_JWT_SECRET', SECRET)
    contexts, statements = [], []

    def forbidden_context(*args, **kwargs):
        contexts.append(True)
        raise AssertionError('Invalid input entered graph edit context')

    for module in (graph_nodes, relations, review):
        monkeypatch.setattr(module, '_context', forbidden_context)

    def auth(user):
        token = issue_access_token(user_id=user.id, role=user.role, secret=SECRET.encode(),
                                   issued_at=int(time.time()), ttl_seconds=3600)
        return {'Authorization': f'Bearer {token}'}

    def snapshot():
        with connect(url) as db:
            return tuple(db.iterdump())

    original_connect = sqlite3.connect

    def traced_connect(*args, **kwargs):
        db = original_connect(*args, **kwargs)
        db.set_trace_callback(statements.append)
        return db

    with TestClient(create_app(), raise_server_exceptions=False) as client:
        monkeypatch.setattr(sqlite3, 'connect', traced_connect)
        yield SimpleNamespace(client=client, prefix=f'/api/v1/courses/{course.id}',
                              teacher=auth(teacher), student=auth(student), contexts=contexts,
                              statements=statements, snapshot=snapshot)


@pytest.mark.parametrize('method,path,field,base', ROUTES)
@pytest.mark.parametrize('value', INVALID)
def test_invalid_enum_is_422_without_partial_writes(http_env, method, path, field, base, value):
    before = http_env.snapshot()
    response = http_env.client.request(method, http_env.prefix + path,
                                       headers=http_env.teacher, json={**base, field: value})
    assert response.status_code == 422, response.text
    payload = response.json()
    assert payload['code'] == 'VALIDATION_ERROR'
    assert_schema('Error', payload)
    if path.startswith('/kp/') or field == 'action':
        reason = 'enum'
    elif field == 'item':
        reason = 'union_tag_invalid'
    else:
        reason = 'null_forbidden' if value is None else 'enum' if isinstance(value, str) else 'string_type'
    assert payload['details']['fields'] == [{'in': 'body', 'field': field, 'reason': reason}]
    assert not http_env.contexts
    assert http_env.snapshot() == before
    assert not [sql for sql in http_env.statements if sql.lstrip().upper().startswith(
        ('INSERT', 'UPDATE', 'DELETE', 'REPLACE', 'BEGIN IMMEDIATE', 'CREATE', 'ALTER', 'DROP'))]


@pytest.mark.parametrize('module,field,enum', [
    (graph_nodes, 'type', KnowledgePointType), (graph_nodes, 'status', KnowledgePointStatus),
    (relations, 'type', RelationType), (relations, 'status', KnowledgePointStatus),
])
def test_each_legal_patch_enum_remains_accepted(module, field, enum):
    for member in enum:
        body = {field: member.value}
        if module is graph_nodes:
            body['expected_revision'] = 1
            assert module._patch(body) == (1, {field: member.value})
        else:
            assert module._patch(body) == body


@pytest.mark.parametrize('item,target,actions', [
    ('low_confidence_relation', {'rel_id': 'r'}, ('approve', 'reject')),
    ('isolated_node', {'kp_id': 'k'}, ('approve', 'reject')),
    ('suspected_duplicate', {'kp_ids': ['a', 'b']}, ('merge', 'reject')),
])
def test_legal_review_discriminators_remain_accepted(item, target, actions):
    for action in actions:
        body = {'item': item, 'action': action, **target}
        if item == 'suspected_duplicate' and action == 'merge':
            body['primary_id'] = 'a'
        assert review._action(body) == body


@pytest.mark.parametrize('method,path,field,base', ROUTES[:1] + ROUTES[2:3] + ROUTES[4:5])
@pytest.mark.parametrize('identity,status', [('student', 403), ('unauthenticated', 401)])
def test_invalid_enum_does_not_bypass_existing_authorization(http_env, method, path, field, base, identity, status):
    response = http_env.client.request(method, http_env.prefix + path,
        headers=http_env.student if identity == 'student' else {}, json={**base, field: []})
    assert response.status_code == status
    assert not http_env.contexts
