"""B08: shared errors, source locations, and relation types."""

from pathlib import Path

import jsonschema
import yaml


ROOT = Path(__file__).resolve().parents[2]
SPEC = yaml.safe_load((ROOT / "src/contracts/api.v1.yaml").read_text(encoding="utf-8"))
SCHEMAS = SPEC["components"]["schemas"]


def test_shared_error_codes_cover_signed_off_domain_failures():
    codes = set(SCHEMAS["ErrorCode"]["enum"])
    assert {
        "DOCUMENT_UNREADABLE", "EXTRACTION_INCOMPLETE", "STORAGE_UNAVAILABLE",
        "INTERNAL_ERROR", "TASK_ATTEMPTS_EXHAUSTED", "PUBLISH_IN_PROGRESS",
        "COURSE_BUSY", "BUDGET_EXCEEDED",
    } <= codes
    assert {"NOT_COVERED", "TASK_FAILED", "not_covered", "failed"}.isdisjoint(codes)
    assert len(codes) == len(SCHEMAS["ErrorCode"]["enum"])


def test_source_ref_requires_a_real_location():
    source = SCHEMAS["SourceRef"]
    base = {"chunk_id": "chunk-1", "document_id": "doc-1"}
    for location in ({"page": 1}, {"section_path": "第一章"},
                     {"page": 2, "section_path": "第一章"}):
        jsonschema.validate(base | location, source)
    for location in ({}, {"page": 0}, {"page": -1}, {"page": None},
                     {"section_path": ""}, {"section_path": None},
                     {"page": 0, "section_path": ""}):
        assert not jsonschema.Draft202012Validator(source).is_valid(base | location)


def test_relation_types_are_closed():
    values = SCHEMAS["RelationType"]["enum"]
    assert values == ["CONTAINS", "PREREQUISITE", "RELATED_TO", "EXAMPLE_OF"]
    assert "PREREQUISITE_OF" not in values


def test_identity_security_is_explicit_for_protected_operations():
    schemes = SPEC["components"]["securitySchemes"]
    assert "仅作前端路由提示" in schemes["bearerAuth"]["description"]
    assert "不据此授权" in schemes["bearerAuth"]["description"]
    assert {key: schemes["eventTicket"][key] for key in ("type", "in", "name")} == {
        "type": "apiKey", "in": "query", "name": "ticket",
    }
    for path, item in SPEC["paths"].items():
        for method, operation in item.items():
            if method not in {"get", "post", "put", "patch", "delete"}:
                continue
            if operation.get("security", SPEC["security"]) == []:
                continue
            assert operation["responses"].get("401") == {
                "$ref": "#/components/responses/Unauthenticated"
            }, f"{method.upper()} {path} must document 401"
