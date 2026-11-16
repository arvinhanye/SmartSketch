"""Completed semantic decisions survive failures without replaying model calls."""
from dataclasses import replace
import json

import pytest

from app.services.ai.fake import FakeModelClient
from app.services.ai.policy import ModelUnavailableError
from app.services.fusion.resolution import SemanticResolver
from app.workers.extraction.analysis import analyze_section
from tests.backend.test_disambiguation_generation import entities, different


class MemoryDecisions:
    def __init__(self):
        self.rows = {}

    def get(self, digest, left, right):
        return self.rows.get((digest, left, right))

    def put(self, digest, decision):
        self.rows[(digest, decision['left_id'], decision['right_id'])] = json.loads(json.dumps(decision))


def test_completed_pairs_survive_mid_analysis_failure_and_json_roundtrip():
    nodes, chunks = entities(3)
    cache = MemoryDecisions()
    def fail_second(request):
        if len(first.calls) == 2:
            raise ModelUnavailableError()
        return different(request)
    first = FakeModelClient(responder=fail_second)
    with pytest.raises(ModelUnavailableError):
        analyze_section(nodes, chunks, resolver=SemanticResolver(first, model='m'), max_pairs=3, cache=cache)
    assert len(cache.rows) == 1
    resumed = FakeModelClient(responder=different)
    report = analyze_section(nodes, chunks, resolver=SemanticResolver(resumed, model='m'), max_pairs=3, cache=cache)
    assert len(resumed.calls) == 2 and report['completed_pairs'] == 3
    third = FakeModelClient(responder=lambda _: pytest.fail('Completed analysis must not call model'))
    assert analyze_section(nodes, chunks, resolver=SemanticResolver(third, model='m'), max_pairs=3, cache=cache) == report


@pytest.mark.parametrize('change', ['definition', 'source', 'model', 'prompt', 'output', 'input', 'context'])
def test_changed_semantic_inputs_do_not_reuse_prior_decisions(change):
    nodes, chunks = entities(2)
    cache = MemoryDecisions()
    first = FakeModelClient(responder=different)
    analyze_section(nodes, chunks, resolver=SemanticResolver(first, model='m'), max_pairs=1,
                    cache=cache, context={'base_url': 'https://one.example'})
    client = FakeModelClient(responder=different)
    resolver = SemanticResolver(client, model='new' if change == 'model' else 'm',
                                max_output_tokens=2048 if change == 'output' else 1024,
                                max_input_bytes=48000 if change == 'input' else 24000)
    if change == 'definition':
        nodes = (replace(nodes[0], candidates=(replace(nodes[0].candidates[0], definition='新条件'),)), nodes[1])
    elif change == 'source':
        chunks['ch0'].text += '新增上下文'
    elif change == 'prompt':
        resolver.template = replace(resolver.template, sha256='f' * 64)
    context = {'base_url': 'https://two.example' if change == 'context' else 'https://one.example'}
    analyze_section(nodes, chunks, resolver=resolver, max_pairs=1, cache=cache, context=context)
    assert len(client.calls) == 1


def test_incomplete_same_verification_is_not_saved_as_complete():
    nodes, chunks = entities(2)
    cache = MemoryDecisions()
    def same_then_fail(request):
        if len(first.calls) == 2:
            raise ModelUnavailableError()
        return different(request).replace('"DIFFERENT"', '"SAME"').replace('["对象不同"]', '[]')
    first = FakeModelClient(responder=same_then_fail)
    with pytest.raises(ModelUnavailableError):
        analyze_section(nodes, chunks, resolver=SemanticResolver(first, model='m'), max_pairs=1, cache=cache)
    assert not cache.rows


def test_failed_and_deferred_results_are_retried_instead_of_cached():
    nodes, chunks = entities(2)
    cache = MemoryDecisions()
    analyze_section(nodes, chunks, resolver=SemanticResolver(FakeModelClient(responder=lambda _: 'bad'), model='m'),
                    max_pairs=1, cache=cache)
    analyze_section(nodes, chunks, resolver=SemanticResolver(FakeModelClient(), model='m', max_input_bytes=1),
                    max_pairs=1, cache=cache)
    assert not cache.rows
