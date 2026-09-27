"""PR #264 独立审查遗留项的契约回归（ADR-072）。

- 遗留 2：手工无来源节点用 ``KnowledgePointDetailWithoutSource``（``source_refs`` 必须为空数组）表示；
  ``KnowledgePointDetail`` 的 ``minItems: 1`` 必须保持不变——AI 节点缺来源仍是完整性故障。
- 真源、生成物与后端模型三处必须一致（生成物由 ``scripts/gen-contracts.sh`` 产出）。
"""

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

REF = {"chunk_id": "chunk_1", "document_id": "doc_1", "page": 1}
MANUAL_NODE = {
    "id": "kp_1", "course_id": "c_1", "name": "栈", "type": "concept",
    "definition": "后进先出", "level": 0, "confidence": 1.0,
    "status": "approved", "source": "manual", "locked": False, "revision": 1,
}


def valid(name, payload):
    return jsonschema.Draft202012Validator(
        {"$defs": DEFS, "$ref": f"#/$defs/{name}"}
    ).is_valid(payload)


def generated_models():
    path = ROOT / "src/contracts/v1/generated/python/models.py"
    spec = importlib.util.spec_from_file_location("leftovers264_generated_models", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_detail_keeps_requiring_a_locatable_source_while_the_empty_state_is_its_own_shape():
    assert not valid("KnowledgePointDetail", MANUAL_NODE | {"source_refs": []})
    assert valid("KnowledgePointDetail", MANUAL_NODE | {"source_refs": [REF]})
    assert valid("KnowledgePointDetailWithoutSource", MANUAL_NODE | {"source_refs": []})
    assert not valid("KnowledgePointDetailWithoutSource", MANUAL_NODE | {"source_refs": [REF]})


def test_knowledge_point_detail_response_is_the_two_shapes():
    content = PATHS["/api/v1/courses/{cid}/kp/{kid}"]["get"]["responses"]["200"]["content"]["application/json"]
    assert content["schema"]["oneOf"] == [
        {"$ref": "#/components/schemas/KnowledgePointDetail"},
        {"$ref": "#/components/schemas/KnowledgePointDetailWithoutSource"},
    ]


def test_generated_pydantic_model_accepts_the_explicit_empty_array_only():
    models = generated_models()
    models.KnowledgePointDetailWithoutSource.model_validate(MANUAL_NODE | {"source_refs": []})
    with pytest.raises(Exception):
        models.KnowledgePointDetailWithoutSource.model_validate(MANUAL_NODE | {"source_refs": [REF]})


def test_generated_typescript_exposes_both_shapes():
    ts = (ROOT / "src/contracts/v1/generated/typescript/openapi.d.ts").read_text(encoding="utf-8")
    assert "KnowledgePointDetailWithoutSource:" in ts
    assert "KnowledgePointDetail:" in ts
