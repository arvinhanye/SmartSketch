"""Consume bounded windows within an existing atomic chunk/section attempt."""
from __future__ import annotations

from dataclasses import asdict, replace
import hashlib
import json

from app.services.ai.entities import _layout, _sources_for
from app.services.ai.extraction_windows import WindowPolicy, entity_windows, relation_windows, gleaning_windows
from app.services.ai.gleaning import entity_mention_key
from app.services.ai.relations import _edge_key
from app.services.ai.request_budget import WindowBudgetError


def checkpoint_policy(current, checkpoints):
    if not checkpoints:
        return current
    policies = [(c.metadata or {}).get('window_policy') for c in checkpoints]
    if all(p is None for p in policies):
        return None  # old task retains its original extraction algorithm
    if any(p is None for p in policies) or any(p != policies[0] for p in policies):
        raise ValueError('inconsistent extraction window checkpoints')
    return WindowPolicy(**policies[0])


def _report(extractor, chunks, entities, policy, update, *, gleaner=None):
    content = dict(policy=asdict(policy), chunks=[asdict(c) for c in chunks],
                   entities=None if entities is None else [asdict(e) for e in entities],
                   model=extractor.model, prompt=extractor.prompt().sha256,
                   request_floor=extractor.request_size('') if entities is None else extractor.request_size((),()))
    if gleaner is not None and gleaner.enabled:
        content['gleaning'] = dict(model=gleaner.model, prompt=gleaner.prompt().sha256,
            request_floor=gleaner.request_size('',()), rounds=gleaner.max_rounds)
    digest = hashlib.sha256(json.dumps(content, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
    report = dict(version=1, status='partial', input_digest=digest,
                  planned_windows=None, completed_windows=0, reason=None,
                  gleaning_planned_windows=0, gleaning_completed_windows=0)
    update(report)
    return report


def _restore(candidate, part):
    start = candidate.source.evidence_start + part.start
    end = candidate.source.evidence_end + part.start
    original = part.chunk
    if original.text[start:end] != candidate.evidence:
        raise ValueError('window evidence does not match original source')
    source = replace(candidate.source, evidence_start=start, evidence_end=end,
                     sources=_sources_for(_layout(original.identity.sources, original.text),
                                          original.identity.sources, start, end))
    return replace(candidate, source=source)


def extract_entities(extractor, chunk, policy, update, *, gleaner=None):
    report = _report(extractor, (chunk,), None, policy, update, gleaner=gleaner)
    result = {}
    try:
        windows = entity_windows(extractor, chunk, policy)
        report['planned_windows'] = len(windows)
        if gleaner is not None and gleaner.enabled and len(windows)*2 > policy.max_windows:
            raise WindowBudgetError('window_limit')
        for part in windows:
            sliced = part.sliced
            extracted = extractor.extract(sliced.identity, sliced.text)
            if not extracted.ok:
                report['reason'] = 'output_invalid'
                return (), 'EXTRACTION_INCOMPLETE'
            candidates = extracted.candidates
            if gleaner is not None and gleaner.enabled:
                candidates, error = _glean(gleaner, sliced, candidates, policy, report)
                if error is not None:
                    report['reason'] = 'gleaning_incomplete'
                    return (), error
            for candidate in candidates:
                restored = _restore(candidate, part)
                result.setdefault(entity_mention_key(restored), restored)
            report['completed_windows'] += 1
    except WindowBudgetError as exc:
        report['reason'] = exc.reason
        raise
    except Exception:
        report['reason'] = 'model_or_execution_error'
        raise
    report.update(status='complete', reason=None)
    return tuple(result.values()), None


def _glean(gleaner, chunk, candidates, policy, report):
    known = {entity_mention_key(c):c for c in candidates}
    for _ in range(gleaner.max_rounds):
        windows = gleaning_windows(gleaner,chunk,tuple(known.values()),policy)
        planned = report['gleaning_planned_windows'] + len(windows)
        if report['planned_windows'] + planned > policy.max_windows:
            raise WindowBudgetError('window_limit')
        report['gleaning_planned_windows'] = planned
        added = {}
        for part in windows:
            # Only hints fully inside this source slice need local coordinates.
            # Planning budgets the full known table, and no stored candidate is dropped.
            local = tuple(replace(c,source=replace(c.source,
                evidence_start=c.source.evidence_start-part.start,
                evidence_end=c.source.evidence_end-part.start)) for c in known.values()
                if part.start <= c.source.evidence_start < c.source.evidence_end <= part.end)
            sliced = part.sliced
            result = gleaner.glean(sliced.identity,sliced.text,local,preserve_mentions=True,round_limit=1)
            if not result.ok:
                return (), result.error_code or 'EXTRACTION_INCOMPLETE'
            for candidate in result.added:
                restored = _restore(candidate,part)
                key = entity_mention_key(restored)
                if key not in known:
                    added.setdefault(key,restored)
            report['gleaning_completed_windows'] += 1
        if not added:
            break
        known.update(added)
    return tuple(known.values()), None


def plan_relations(extractor, entities, chunks, policy, update):
    report = _report(extractor,chunks,entities,policy,update)
    try:
        windows = relation_windows(extractor,entities,chunks,policy)
    except WindowBudgetError as exc:
        report['reason'] = exc.reason
        raise
    report['planned_windows'] = len(windows)
    return windows


def extract_relations(extractor, course_id, entities, chunks, policy, update, *, prepared=None):
    report = _report(extractor, chunks, entities, policy, update)
    result = {}
    try:
        windows = prepared if prepared is not None else relation_windows(extractor, entities, chunks, policy)
        report['planned_windows'] = len(windows)
        for window in windows:
            extracted = extractor.extract(course_id, window.entities, tuple(p.sliced for p in window.sources))
            if not extracted.ok:
                report['reason'] = 'output_invalid'
                return (), 'EXTRACTION_INCOMPLETE'
            by_id = {p.chunk.identity.chunk_id:p for p in window.sources}
            for candidate in extracted.candidates:
                restored = _restore(candidate, by_id[candidate.source.chunk_id])
                source = restored.source
                key = (*_edge_key(restored.from_id, restored.to_id, restored.type),
                       source.chunk_id, source.evidence_start, source.evidence_end)
                result.setdefault(key, restored)
            report['completed_windows'] += 1
    except WindowBudgetError as exc:
        report['reason'] = exc.reason
        raise
    except Exception:
        report['reason'] = 'model_or_execution_error'
        raise
    report.update(status='complete', reason=None)
    return tuple(result.values()), None
