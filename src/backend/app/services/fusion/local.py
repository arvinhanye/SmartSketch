"""Tentative semantic cards. Original mentions and all their qualifiers survive."""
from collections.abc import Sequence

from app.services.ai.relations import SectionEntity
from app.services.fusion.mapping import fingerprint, plan_mapping
from app.services.fusion.resolution import SemanticDecision


def local_normalization(entities: Sequence[SectionEntity], analysis: dict | None) -> dict:
    courses = {e.course_id for e in entities}
    if len(courses) > 1:
        raise ValueError('cross-course local normalization')
    snapshot = dict(course_id=next(iter(courses), 'empty'), edges=[], evidence=[], nodes=[
        dict(kp_id=e.entity_id, course_id=e.course_id, name=e.name, type=e.type,
             definition=e.definition) for e in sorted(entities, key=lambda e: e.entity_id)])
    decisions = [SemanticDecision(**d) for d in (analysis or {}).get('decisions', [])]
    mapped = plan_mapping(snapshot, decisions, existing_ids=())
    value = dict(version=1, mapping=mapped.mapping, groups=[list(g) for g in mapped.groups])
    return {**value, 'digest':fingerprint(value)}
