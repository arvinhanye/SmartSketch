"""B09 course, document, and course membership wire contract."""

from pathlib import Path

import jsonschema
import yaml


ROOT = Path(__file__).resolve().parents[2]
SPEC = yaml.safe_load((ROOT / "src/contracts/api.v1.yaml").read_text(encoding="utf-8"))
SCHEMAS = SPEC["components"]["schemas"]
PATHS = SPEC["paths"]


def operation(path: str, method: str):
    return PATHS[f"/api/v1{path}"][method]


def test_course_exposes_membership_role_and_filtered_list():
    course = SCHEMAS["Course"]
    assert "my_role" in course["required"]
    assert course["properties"]["my_role"] == {"$ref": "#/components/schemas/Role"}
    assert {"id", "name", "status", "created_at"} <= set(course["required"])
    listing = operation("/courses", "get")
    assert "成员" in listing["description"] and "发布" in listing["description"]
    assert listing["responses"]["200"]["content"]["application/json"]["schema"]["items"] == {
        "$ref": "#/components/schemas/Course"
    }


def test_existing_course_and_document_flows_have_success_and_errors():
    expected = {
        ("/courses", "get"): {"200", "401"},
        ("/courses", "post"): {"201", "401", "403", "422"},
        ("/courses/{cid}", "get"): {"200", "401", "403", "404"},
        ("/courses/{cid}/documents", "get"): {"200", "401", "403"},
        ("/courses/{cid}/documents", "post"): {"202", "401", "403", "413", "415"},
    }
    for (path, method), statuses in expected.items():
        assert statuses <= set(operation(path, method)["responses"]), (path, method)
    assert "GRAPH_NOT_PUBLISHED" in operation("/courses/{cid}", "get")["responses"]["404"]["description"]
    assert "429" in operation("/auth/login", "post")["responses"]


def test_member_operations_cover_create_idempotency_and_removal():
    listing = operation("/courses/{cid}/members", "get")
    add = operation("/courses/{cid}/members", "post")
    remove = operation("/courses/{cid}/members/{uid}", "delete")
    assert [listing["operationId"], add["operationId"], remove["operationId"]] == [
        "listMembers", "addMember", "removeMember"
    ]
    assert {"200", "401", "403"} <= set(listing["responses"])
    assert listing["responses"]["200"]["content"]["application/json"]["schema"]["items"] == {
        "$ref": "#/components/schemas/CourseMember"
    }
    assert {"200", "201", "401", "403", "404", "422"} <= set(add["responses"])
    assert {"204", "401", "403", "404"} <= set(remove["responses"])
    for code in ("200", "201"):
        assert add["responses"][code]["content"]["application/json"]["schema"] == {
            "$ref": "#/components/schemas/CourseMember"
        }
    assert remove["responses"]["204"].get("content") is None
    assert remove["parameters"][0] == {"$ref": "#/components/parameters/UserId"}


def test_request_schemas_do_not_declare_caller_identity():
    member = SCHEMAS["CourseMember"]
    assert set(member["required"]) == {"user_id", "username", "role", "created_at"}
    assert member["properties"]["role"] == {"$ref": "#/components/schemas/Role"}
    add = SCHEMAS["MemberAdd"]
    assert add["required"] == ["username"]
    assert "user_id" not in add["properties"] and "role" not in add["properties"]
    assert jsonschema.Draft202012Validator(add).is_valid({"username": "student1"})
    assert not jsonschema.Draft202012Validator(add).is_valid({"username": ""})
    assert not jsonschema.Draft202012Validator(add).is_valid({})
    ids = {op["operationId"] for path in PATHS.values() for method, op in path.items()
           if method in {"get", "post", "put", "patch", "delete"}}
    assert not any(name in ids for name in {"createUser", "registerUser", "signUp"})
    for path in PATHS.values():
        for method, op in path.items():
            if method not in {"post", "put", "patch"}:
                continue
            for media in op.get("requestBody", {}).get("content", {}).values():
                schema = media["schema"]
                if "$ref" in schema:
                    schema = SCHEMAS[schema["$ref"].rsplit("/", 1)[-1]]
                assert "user_id" not in schema.get("properties", {}), op["operationId"]


def test_get_course_404_is_only_unpublished_for_students():
    # identity-access §4.1：课程不存在与非成员同为 403 COURSE_FORBIDDEN，404 只来自 GRAPH_NOT_PUBLISHED
    responses = operation("/courses/{cid}", "get")["responses"]
    assert responses["403"] == {"$ref": "#/components/responses/Forbidden"}
    not_found = responses["404"]["description"]
    assert "GRAPH_NOT_PUBLISHED" in not_found
    assert "不存在" not in not_found.split("GRAPH_NOT_PUBLISHED")[0]
