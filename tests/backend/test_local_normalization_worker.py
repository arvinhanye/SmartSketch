"""Generation pins local semantics and never exposes unconfirmed relation dependencies."""
from dataclasses import asdict, replace
import json

import pytest

from app.repositories.extraction_checkpoints import Checkpoint
from app.services.ai.fake import FakeModelClient
from app.services.ai.extraction_windows import WindowPolicy
from app.services.ai.relations import SectionEntity
from app.workers.extraction.types import _Section
from app.workers.extraction.units import _extract_section, _extract_chunk
from tests.backend.test_extraction_window_worker import toolkit, stored, LEASE, LIMITS
from tests.backend.test_local_normalization import same


def test_normalization_precedes_relation_call_and_keeps_mapping_evidence(monkeypatch):
    seen=[]
    def analyze(*a,**k):
        seen.append('analysis')
        return dict(decisions=[asdict(same('a','b'))],input_digest='analysis')
    monkeypatch.setattr('app.workers.extraction.units.analyze_section', analyze)
    client=FakeModelClient(responder=lambda request: seen.append(request) or '{"relations":[]}')
    kit=replace(toolkit(client),local_normalization=True,
                window_policy=WindowPolicy(max_input_bytes=16000))
    entities=(SectionEntity('a','c','散列表','concept','限定甲'),SectionEntity('b','c','哈希表','concept','限定乙'))
    section=_Section('s',('r',0),None,(stored('散列表也叫哈希表。'),))
    out=_extract_section(kit,LEASE,LIMITS,section,entities)
    assert out.status=='done' and seen[0]=='analysis'
    assert seen[1].purpose=='extract_normalized_relations'
    result=out.result
    assert result['normalization']['mapping']=={'a':'a','b':'a'}
    assert result['normalization']['groups']==[['a','b']]
    assert len(result['relation_input_digest'])==64
    assert out.metadata['normalization_version']==1
    assert out.metadata['window_coverage']['status']=='complete'
    changed=_extract_section(kit,LEASE,LIMITS,replace(section,chunks=(stored('有新的限定。'),)),entities)
    assert changed.result['relation_input_digest'] != result['relation_input_digest']


def test_chunk_pins_local_algorithm_even_without_semantic_groups():
    client=FakeModelClient(responder=lambda _: '{"entities":[]}')
    out=_extract_chunk(replace(toolkit(client),local_normalization=True),LEASE,LIMITS,stored('资料'))
    assert out.metadata['normalization_version']==1


@pytest.mark.parametrize('enabled',[True,False])
def test_resume_pins_old_or_new_checkpoint_version(enabled):
    from app.workers.extraction.local import checkpoint_normalization
    def checkpoint(meta):
        return Checkpoint('chunk','c','done',1,None,{'entity_identity_version':2,'entities':[]},meta)
    assert checkpoint_normalization(enabled,[]) is enabled
    assert not checkpoint_normalization(enabled,[checkpoint(None)])
    assert checkpoint_normalization(enabled,[checkpoint({'normalization_version':1})])
    with pytest.raises(ValueError):
        checkpoint_normalization(enabled,[checkpoint(None),checkpoint({'normalization_version':1})])


def test_provisional_relations_require_explicit_valid_selection():
    from app.workers.extraction.local import select_initial
    result={'chunk_ids':['r-0'],'relations':[{'example':1}],
            'normalization':{'groups':[['a','b']]},'relation_input_digest':'sha'}
    assert select_initial(result,None,False) is None
    assert select_initial(result,None,True)==result
    assert select_initial(result,{'kind':'initial','digest':'sha'},False)==result
    assert select_initial(result,{'kind':'initial','digest':'stale'},False) is None
    assert select_initial({**result,'normalization':{'groups':[]}},None,False) is not None
