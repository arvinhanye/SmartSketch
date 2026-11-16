"""The relation timeout reaches both worker factories and their HTTP calls."""

import pytest

from app.config import SettingsError, load_settings
from app.repositories.courses import create_course
from app.repositories.model_configs import save_config
from app.services.ai import compatible_base
from app.services.ai.compatible import CompatibleModelClient
from app.services.ai.policy import CallAttribution
from app.services.ai.relations import RelationExtractor
from app.services.credentials import CredentialCipher
from app.workers import toolkits
from app.workers.runner import build_toolkit
from tests.backend.test_disambiguation_resolution import pair, reply
from tests.backend.test_l07 import ROOT_KEY, _bound_task, _lease, _settings, _user
from test_e03 import ScriptedResponse, ScriptedTransport, completion_body
from test_e11 import COURSE, _chunks, _entities


BASE_URL = "https://model.example/v1"
FALLBACK_URL = "https://backup.example/v1"


def _repair_transport(*outputs: str) -> ScriptedTransport:
    return ScriptedTransport(*(
        ScriptedResponse(200, completion_body(content=content, model="m"))
        for output in outputs
        for content in ("invalid JSON", output)
    ))


@pytest.mark.parametrize("personal", [False, True], ids=["live", "personal"])
@pytest.mark.parametrize(
    ("timeout_env", "general_timeout", "relation_timeout"),
    [({}, 60, 180), ({"LLM_REQUEST_TIMEOUT_SECONDS": "47.5", "LLM_RELATION_TIMEOUT_SECONDS": "190.5"}, 47.5, 190.5)],
    ids=["defaults", "overrides"],
)
def test_worker_factories_apply_relation_timeout_to_relations_and_their_repairs(
    db_url, monkeypatch, personal, timeout_env, general_timeout, relation_timeout,
):
    transport = _repair_transport('{"entities":[]}', '{"relations":[]}', '{"relations":[]}', reply("DIFFERENT"))
    env = {"DISAMBIGUATION_ANALYSIS_ENABLED": "true", **timeout_env}
    if personal:
        monkeypatch.setattr(toolkits, "build_transport", lambda settings: transport)
        user = _user(db_url, "timeout-teacher")
        course = create_course(db_url, name="Timeout test", description=None, creator_id=user.id)
        save_config(
            db_url, user_id=user.id, base_url=BASE_URL, model="m",
            sealed=CredentialCipher(ROOT_KEY).seal(user.id, "test-key"), key_hint="-key", disable_thinking=True,
        )
        task = _bound_task(db_url, course.id, user)
        toolkit = build_toolkit(_settings(db_url, **env))(_lease(task))
        expected_context = dict(mode="personal", base_url=BASE_URL, model="m", disable_thinking=True)
    else:
        monkeypatch.setattr(compatible_base, "StdlibTransport", lambda: transport)
        toolkit = build_toolkit(load_settings({
            "SQLITE_URL": db_url,
            "LLM_MODE": "live",
            "LLM_BASE_URL": BASE_URL,
            "LLM_API_KEY": "test-key",
            "LLM_EXTRACTION_MODEL": "m",
            "LLM_CHAT_MODEL": "m",
            "LLM_FALLBACK_BASE_URL": FALLBACK_URL,
            "LLM_FALLBACK_API_KEY": "other-key",
            "LLM_FALLBACK_EXTRACTION_MODEL": "fallback",
            "LLM_FALLBACK_CHAT_MODEL": "fallback",
            **env,
        }))
        expected_context = dict(
            mode="live", base_url=BASE_URL, model="m", fallback_base_url=FALLBACK_URL, fallback_model="fallback",
        )
    client = toolkit.policy.bind(CallAttribution(course_id=COURSE))
    chunks = _chunks()

    assert toolkit.entities(client).extract(chunks[0].identity, chunks[0].text).ok
    assert toolkit.relations(client).extract(COURSE, _entities(), chunks).ok
    assert toolkit.relations(client).normalized().extract(COURSE, _entities(), chunks).ok
    assert toolkit.resolver(client).resolve(*pair()).status == "complete"

    assert [call["timeout"] for call in transport.calls] == [
        general_timeout, general_timeout,  # entity request and repair
        relation_timeout, relation_timeout,  # relation request and repair
        relation_timeout, relation_timeout,  # normalized relation request and repair
        general_timeout, general_timeout,  # semantic adjudication and repair
    ]
    assert toolkit.analysis_context == expected_context


def test_direct_relation_extractor_without_override_uses_client_timeout():
    transport = _repair_transport('{"relations":[]}')
    client = CompatibleModelClient(BASE_URL, "test-key", transport=transport, default_timeout_seconds=72)
    extractor = RelationExtractor(client, model="m", max_output_tokens=4096)

    assert extractor.extract(COURSE, _entities(), _chunks()).ok
    assert [call["timeout"] for call in transport.calls] == [72, 72]


@pytest.mark.parametrize("value", ["0", "-1", "inf", "nan"])
def test_relation_timeout_requires_positive_finite_seconds(value):
    with pytest.raises(SettingsError, match="LLM_RELATION_TIMEOUT_SECONDS"):
        load_settings({"LLM_RELATION_TIMEOUT_SECONDS": value})
