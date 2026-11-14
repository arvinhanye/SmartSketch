"""Pinned local normalization and relation dependency identity (ADR-102)."""
from dataclasses import asdict

from app.services.fusion.mapping import fingerprint


def checkpoint_normalization(current, checkpoints):
    if not checkpoints:
        return current
    versions = {(c.metadata or {}).get('normalization_version', 0) for c in checkpoints}
    if len(versions) != 1 or any(type(v) is not int or v not in (0, 1) for v in versions):
        raise ValueError('inconsistent normalization versions')
    return versions == {1}


def relation_input_digest(section_id, entities, chunks, extractor, policy, normalization):
    return fingerprint(dict(version=1, section_id=section_id,
        entities=[asdict(e) for e in entities], chunks=[asdict(c) for c in chunks],
        model=extractor.model, prompt=extractor.prompt().sha256,
        output_tokens=extractor.max_output_tokens,
        policy=None if policy is None else asdict(policy), normalization=normalization))


def dependent(result):
    return bool(result and result.get('normalization', {}).get('groups'))


def select_initial(result, selection, provisional=False):
    if selection is not None:
        if selection.get('kind') != 'initial' or selection.get('digest') != result.get('relation_input_digest'):
            return None
        return result
    return result if provisional or not dependent(result) else None
