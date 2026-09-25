"""B11: graph editing, downgraded relations, and publish-version wire contract."""

import copy
import importlib.util
import sys
from pathlib import Path

import jsonschema
import pytest
import yaml


ROOT = Path(__file__).resolve().parents[2]
API = yaml.safe_load((ROOT / "src/contracts/api.v1.yaml").read_text(encoding="utf-8"))
SCHEMAS = API["components"]["schemas"]
PATHS = API["paths"]


def _rewrite(value):
    if isinstance(value, dict):
        return {k: (v.replace("#/components/schemas/", "#/$defs/")
                    if k == "$ref" else _rewrite(v)) for k, v in value.items()}
    if isinstance(value, list):
        return [_rewrite(v) for v in value]
    return value


DEFS = _rewrite(copy.deepcopy(SCHEMAS))


def generated_models():
    path = ROOT / "src/contracts/v1/generated/python/models.py"
    spec = importlib.util.spec_from_file_location("b11_generated_models", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def valid(name, payload):
    return jsonschema.Draft202012Validator(
        {"$defs": DEFS, "$ref": f"#/$defs/{name}"}
    ).is_valid(payload)


REF = {"chunk_id": "chunk_1", "document_id": "doc_1", "page": 1}
RELATION = {
    "id": "r_1", "course_id": "c_1", "type": "PREREQUISITE",
    "from_id": "kp_1", "to_id": "kp_2", "confidence": 0.8,
    "status": "draft", "source": "ai", "source_refs": [REF],
}
NODE = {
    "id": "kp_1", "course_id": "c_1", "name": "栈", "type": "concept",
    "definition": "后进先出", "level": 0, "confidence": 0.9,
    "status": "approved", "source": "manual", "locked": True, "revision": 1,
}


@pytest.mark.parametrize("field", ["status", "source", "source_refs"])
def test_relation_response_requires_a02_r01_fields(field):
    assert valid("Relation", RELATION)
    assert not valid("Relation", {k: v for k, v in RELATION.items() if k != field})


@pytest.mark.parametrize("bad", [
    RELATION | {"source": "model"},
    RELATION | {"source_refs": [{"chunk_id": "chunk_1", "document_id": "doc_1"}]},
    RELATION | {"source_refs": [REF | {"page": 0}]},
])
def test_relation_rejects_invalid_source(bad):
    assert not valid("Relation", bad)


def test_manual_relation_can_have_empty_source_refs_and_create_is_server_populated():
    assert valid("Relation", RELATION | {"source": "manual", "source_refs": []})
    assert valid("RelationCreate", {"type": "RELATED_TO", "from_id": "kp_1", "to_id": "kp_2"})


@pytest.mark.parametrize("schema,payload", [
    ("Relation", RELATION | {"from_id": ""}),
    ("Relation", RELATION | {"to_id": ""}),
    ("RelationCreate", {"type": "PREREQUISITE", "from_id": "", "to_id": "kp_2"}),
    ("RelationCreate", {"type": "PREREQUISITE", "from_id": "kp_1", "to_id": ""}),
    ("RelationUpdate", {"from_id": ""}),
    ("RelationUpdate", {"to_id": ""}),
])
def test_relation_endpoints_must_not_be_blank(schema, payload):
    assert not valid(schema, payload)


def test_node_detail_requires_locatable_source():
    assert not valid("KnowledgePointDetail", NODE | {"source_refs": []})
    assert not valid("KnowledgePointDetail", NODE | {"source_refs": [{"chunk_id": "chunk_1", "document_id": "doc_1"}]})
    assert valid("KnowledgePointDetail", NODE | {"source_refs": [REF]})


def test_downgraded_relation_explains_original_type_and_cycle():
    downgraded = RELATION | {
        "type": "RELATED_TO", "status": "low_confidence",
        "downgraded_from_type": "PREREQUISITE",
        "downgrade_cycle": ["kp_1", "kp_2", "kp_1"],
    }
    assert valid("Relation", downgraded)
    for field in ("downgraded_from_type", "downgrade_cycle"):
        assert not valid("Relation", {k: v for k, v in downgraded.items() if k != field})
    assert not valid("Relation", downgraded | {"downgraded_from_type": "CONTAINS"})
    assert not valid("Relation", downgraded | {"downgrade_cycle": ["kp_1"]})
    assert not valid("Relation", RELATION | {"downgrade_cycle": ["kp_1", "kp_1"]})


def test_node_revision_and_optimistic_edit_request():
    assert valid("KnowledgePoint", NODE)
    assert not valid("KnowledgePoint", {k: v for k, v in NODE.items() if k != "revision"})
    assert not valid("KnowledgePoint", NODE | {"revision": 0})
    assert valid("KnowledgePointUpdate", {"expected_revision": 1, "name": "新名称"})
    assert not valid("KnowledgePointUpdate", {"name": "新名称"})
    assert not valid("KnowledgePointUpdate", {"expected_revision": 1})
    assert not valid("KnowledgePointUpdate", {"expected_revision": 0, "name": "新名称"})
    assert not valid("KnowledgePointUpdate", {"expected_revision": 1, "unexpected": "x"})
    responses = PATHS["/api/v1/courses/{cid}/kp/{kid}"]["patch"]["responses"]
    assert "409" in responses


def test_graph_response_binds_course_and_nullable_version():
    graph = SCHEMAS["GraphExchange"]
    assert {"course_id", "graph_version", "nodes", "edges"} <= set(graph["required"])
    assert graph["properties"]["graph_version"]["type"] == ["integer", "null"]


def test_version_and_publish_result_fields():
    version = {"version": 2, "published_at": "2026-09-24T12:00:00Z", "kind": "rollback", "source_version": 1}
    assert valid("GraphVersion", version)
    assert not valid("GraphVersion", {k: v for k, v in version.items() if k != "kind"})
    assert not valid("GraphVersion", version | {"kind": "restore"})
    assert not valid("GraphVersion", version | {"source_version": 0})
    assert not valid("GraphVersion", {k: v for k, v in version.items() if k != "source_version"})
    assert not valid("GraphVersion", version | {"kind": "publish"})
    assert "commit_seq" not in SCHEMAS["PublishedGraphVersion"]["properties"]
    assert "commit_seq" not in SCHEMAS["RollbackGraphVersion"]["properties"]
    assert "merged_from" not in SCHEMAS["KnowledgePoint"]["properties"]
    result = {"version": 2, "published_at": version["published_at"], "unchanged": False,
              "excluded": {"low_confidence_nodes": 1, "low_confidence_edges": 2, "cascaded_edges": 0}}
    assert valid("PublishResult", result)
    for field in ("unchanged", "excluded"):
        assert not valid("PublishResult", {k: v for k, v in result.items() if k != field})
    assert not valid("PublishResult", result | {"excluded": result["excluded"] | {"cascaded_edges": -1}})


def test_publish_blocked_is_typed_and_reasons_are_closed():
    publish = PATHS["/api/v1/courses/{cid}/publish"]["post"]["responses"]["409"]
    assert publish["content"]["application/json"]["schema"] == {
        "oneOf": [{"$ref": "#/components/schemas/PublishBlockedError"},
                  {"$ref": "#/components/schemas/PublishConflictError"}]}
    def error(reason):
        return {"code": "PUBLISH_BLOCKED", "message": "图谱不可发布", "details": {"reasons": [reason]}}
    for reason in ({"kind": "cycle", "cycle": ["a", "b", "a"]},
                   {"kind": "dangling_endpoint", "relation_id": "r1"},
                   {"kind": "invalid_source_ref", "chunk_id": "chunk1"},
                   {"kind": "empty_graph"}, {"kind": "invalid_lineage", "kp_id": "kp1"}):
        assert valid("PublishBlockedError", error(reason)), reason
    for bad in (error({"kind": "cycle"}), error({"kind": "cycle", "cycle": ["a"]}),
                error({"kind": "unknown"}), error({"kind": "invalid_lineage", "kp_id": 3}),
                error({"kind": "empty_graph"}) | {"code": "COURSE_BUSY"},
                {"code": "PUBLISH_BLOCKED", "message": "x", "details": {"reasons": []}}):
        assert not valid("PublishBlockedError", bad), bad


def test_closed_cycle_requires_service_validation_beyond_json_schema():
    assert SCHEMAS["PublishBlockedCycleReason"]["properties"]["cycle"]["x-closed-cycle"] is True
    assert SCHEMAS["RelationDowngraded"]["properties"]["downgrade_cycle"]["x-closed-cycle"] is True


def test_rollback_exposes_conflict_response():
    responses = PATHS["/api/v1/courses/{cid}/versions/{version}/rollback"]["post"]["responses"]
    assert "409" in responses
    assert responses["409"]["$ref"] == "#/components/responses/Conflict"


@pytest.mark.parametrize("path,method", [
    ("/api/v1/courses/{cid}/kp", "post"),
    ("/api/v1/courses/{cid}/kp/{kid}", "patch"),
    ("/api/v1/courses/{cid}/kp/{kid}", "delete"),
    ("/api/v1/courses/{cid}/kp/merge", "post"),
    ("/api/v1/courses/{cid}/relations", "post"),
    ("/api/v1/courses/{cid}/relations/{rid}", "patch"),
    ("/api/v1/courses/{cid}/relations/{rid}", "delete"),
])
def test_every_teacher_draft_write_declares_course_busy_conflict(path, method):
    response = PATHS[path][method]["responses"]
    assert response["409"] == {"$ref": "#/components/responses/Conflict"}


def test_generated_python_models_reject_missing_conditional_fields():
    models = generated_models()
    models.Relation.model_validate(RELATION)
    models.Relation.model_validate(RELATION | {
        "type": "RELATED_TO", "status": "low_confidence",
        "downgraded_from_type": "PREREQUISITE", "downgrade_cycle": ["kp_1", "kp_2", "kp_1"]})
    edit = models.KnowledgePointUpdate.model_validate({"expected_revision": 1, "name": "新名称", "definition": "更新定义"})
    assert edit.model_dump()["definition"] == "更新定义"
    models.GraphVersion.model_validate({"version": 1, "published_at": "2026-09-24T12:00:00Z", "kind": "publish"})
    models.PublishBlockedReason.model_validate({"kind": "cycle", "cycle": ["a", "b", "a"]})
    for cls, bad in (
        (models.Relation, RELATION | {"downgraded_from_type": "PREREQUISITE"}),
        (models.KnowledgePointUpdate, {"expected_revision": 1}),
        (models.GraphVersion, {"version": 2, "published_at": "2026-09-24T12:00:00Z", "kind": "rollback"}),
        (models.PublishBlockedReason, {"kind": "cycle"}),
    ):
        with pytest.raises(Exception):
            cls.model_validate(bad)


def test_generated_typescript_edit_request_keeps_required_revision_and_nonempty_patch():
    ts = (ROOT / "src/contracts/v1/generated/typescript/openapi.d.ts").read_text(encoding="utf-8")
    block = ts.split("KnowledgePointUpdate:", 1)[1].split("MergeRequest:", 1)[0]
    assert "expected_revision: number" in block
    assert "} & ({" in block
    assert "name: string" in block and "status: components[\"schemas\"][\"KnowledgePointStatus\"]" in block
    assert "unknown" not in block
