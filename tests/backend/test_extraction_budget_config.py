"""Runtime budget overrides reach production factories without paid calls."""
import pytest
from app.config import SettingsError, load_settings
from app.services.ai.extraction_windows import WindowPolicy, relation_windows
from app.services.ai.fake import FakeModelClient
from app.services.ai.relations import RelationExtractor, SectionEntity
from app.services.ai.request_budget import WindowBudgetError
from app.workers.runner import build_toolkit
from tests.backend.test_extraction_windows import source


LARGE = {
    "LLM_EXTRACTION_MAX_OUTPUT_TOKENS": "4096000",
    "DISAMBIGUATION_EXTRACTION_MAX_INPUT_BYTES": "24000000",
    "DISAMBIGUATION_EXTRACTION_MAX_WINDOWS": "64000",
    "DISAMBIGUATION_ANALYSIS_ENABLED": "true",
}


@pytest.mark.parametrize("personal", [False, True])
def test_override_reaches_entities_relations_normalization_and_repairs(db_url, personal):
    if personal:
        from app.repositories.courses import create_course
        from app.workers.toolkits import TaskToolkits
        from tests.backend.test_l07 import _user, _configure, _bound_task, _lease, _settings
        user = _user(db_url, "budget-teacher")
        course = create_course(db_url, name="Budget test", description=None, creator_id=user.id)
        _configure(db_url, user, base_url="https://model.example/v1", model="m", key="test-only")
        task = _bound_task(db_url, course.id, user)
        kit = TaskToolkits(_settings(db_url, **LARGE)).for_lease(_lease(task))
    else:
        kit = build_toolkit(load_settings({"SQLITE_URL": db_url, **LARGE}))
    assert kit.window_policy == WindowPolicy(max_input_bytes=24000000, max_windows=64000)
    client = FakeModelClient(responder=lambda request: "invalid JSON")
    chunk = source("甲和乙彼此相关。")
    nodes = (SectionEntity("a", "c", "甲", "concept"), SectionEntity("b", "c", "乙", "concept"))
    kit.entities(client).extract(chunk.identity, chunk.text)
    kit.relations(client).extract("c", nodes, (chunk,))
    kit.relations(client).normalized().extract("c", nodes, (chunk,))
    assert len(client.calls) == 6  # Each extraction includes its repair.
    assert {call.request.max_output_tokens for call in client.calls} == {4096000}


def test_large_budget_keeps_full_29_entity_table_in_one_window():
    nodes = tuple(SectionEntity(str(i), "c", f"概念{i}", "concept", "限定条件" * 50) for i in range(29))
    chunks = (source("各概念之间存在有据关系。" * 100),)
    client = FakeModelClient()
    old = RelationExtractor(client, model="m", max_output_tokens=4096).normalized()
    with pytest.raises(WindowBudgetError, match="window_limit"):
        relation_windows(old, nodes, chunks, WindowPolicy())
    new = RelationExtractor(client, model="m", max_output_tokens=4096000).normalized()
    windows = relation_windows(new, nodes, chunks, WindowPolicy.from_settings(load_settings(LARGE)))
    assert len(windows) == 1 and windows[0].entities == nodes
    assert tuple(part.sliced for part in windows[0].sources) == chunks
    assert not client.calls


@pytest.mark.parametrize("key,value", [
    ("LLM_EXTRACTION_MAX_OUTPUT_TOKENS", "0"),
    ("LLM_EXTRACTION_MAX_OUTPUT_TOKENS", "4096001"),
    ("DISAMBIGUATION_EXTRACTION_MAX_INPUT_BYTES", "24000001"),
    ("DISAMBIGUATION_EXTRACTION_MAX_WINDOWS", "64001"),
])
def test_budget_overrides_remain_bounded(key, value):
    with pytest.raises(SettingsError):
        load_settings({key: value})


def test_defaults_and_old_checkpoint_policy_remain_compatible():
    settings = load_settings({})
    assert settings.LLM_EXTRACTION_MAX_OUTPUT_TOKENS == 4096
    assert settings.DISAMBIGUATION_EXTRACTION_MAX_INPUT_BYTES == 24000
    assert settings.DISAMBIGUATION_EXTRACTION_MAX_WINDOWS == 64
    assert WindowPolicy(max_windows=64).max_windows == 64
    with pytest.raises(ValueError):
        WindowPolicy(max_windows=64001)
