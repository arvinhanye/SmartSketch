"""Deterministic preflight windows; preserve full cards and original source ranges."""
from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from itertools import combinations

from app.services.ai.entities import EntityExtractor
from app.services.ai.relations import RelationExtractor, SectionEntity, SourceChunk, _check_chunks, _check_entities
from app.services.ai.request_budget import WindowBudgetError
from app.services.chunk_identity import text_sha256


@dataclass(frozen=True)
class WindowPolicy:
    max_input_bytes: int = 24000
    overlap_chars: int = 512
    max_windows: int = 64
    version: int = 1

    def __post_init__(self):
        if (type(self.max_input_bytes) is not int or self.max_input_bytes < 1 or
            type(self.overlap_chars) is not int or not 0 <= self.overlap_chars <= 4096 or
            type(self.max_windows) is not int or not 1 <= self.max_windows <= 256 or
            type(self.version) is not int or self.version != 1):
            raise ValueError('invalid extraction window policy')

    @classmethod
    def from_settings(cls, settings):
        if not (settings.DISAMBIGUATION_ANALYSIS_ENABLED or settings.DISAMBIGUATION_AUTO_MERGE_ENABLED):
            return None
        return cls(max_input_bytes=settings.DISAMBIGUATION_EXTRACTION_MAX_INPUT_BYTES,
                   overlap_chars=settings.DISAMBIGUATION_EXTRACTION_OVERLAP_CHARS,
                   max_windows=settings.DISAMBIGUATION_EXTRACTION_MAX_WINDOWS)


@dataclass(frozen=True)
class SourceSlice:
    chunk: SourceChunk
    start: int
    end: int

    @property
    def sliced(self) -> SourceChunk:
        text = self.chunk.text[self.start:self.end]
        return SourceChunk(replace(self.chunk.identity, text_sha256=text_sha256(text)), text)


@dataclass(frozen=True)
class RelationWindow:
    entities: tuple[SectionEntity, ...]
    sources: tuple[SourceSlice, ...]


def _ranges(chunk: SourceChunk, fits: Callable[[SourceChunk], bool], policy: WindowPolicy) -> tuple[SourceSlice, ...]:
    if fits(chunk):
        return (SourceSlice(chunk, 0, len(chunk.text)),)
    windows = []
    start, length = 0, len(chunk.text)
    if not length:
        raise WindowBudgetError('input_budget')
    while start < length:
        low, high = start, length
        while low < high:
            mid = (low + high + 1) // 2
            if fits(SourceSlice(chunk, start, mid).sliced):
                low = mid
            else:
                high = mid - 1
        end = low
        if end == start or (end < length and end - start <= policy.overlap_chars):
            raise WindowBudgetError('input_budget')
        if len(windows) >= policy.max_windows:
            raise WindowBudgetError('window_limit')
        windows.append(SourceSlice(chunk, start, end))
        if end == length:
            break
        start = end - policy.overlap_chars
    return tuple(windows)


def entity_windows(extractor: EntityExtractor, chunk: SourceChunk, policy: WindowPolicy) -> tuple[SourceSlice, ...]:
    _check_chunks(chunk.identity.course_id, (chunk,))
    return _ranges(chunk, lambda c: extractor.request_size(c.text) <= policy.max_input_bytes, policy)


def gleaning_windows(gleaner, chunk: SourceChunk, known, policy: WindowPolicy) -> tuple[SourceSlice, ...]:
    return _ranges(chunk, lambda c: gleaner.request_size(c.text, known) <= policy.max_input_bytes, policy)


def _source_windows(extractor, entities, chunks, policy) -> tuple[RelationWindow, ...]:
    def fits(sources):
        return extractor.request_size(entities, tuple(s.sliced for s in sources)) <= policy.max_input_bytes
    all_sources = tuple(SourceSlice(c, 0, len(c.text)) for c in chunks)
    if fits(all_sources):
        return (RelationWindow(entities, all_sources),)
    windows, current = [], []
    for chunk in chunks:
        parts = _ranges(chunk, lambda c: extractor.request_size(entities, (c,)) <= policy.max_input_bytes, policy)
        for part in parts:
            repeated = any(s.chunk.identity.chunk_id == part.chunk.identity.chunk_id for s in current)
            if current and (repeated or not fits((*current, part))):
                windows.append(RelationWindow(entities, tuple(current)))
                # Share the adjacent original block when it fits; ranges within
                # one block already have character overlap and must not repeat IDs.
                last = current[-1]
                current = ([last] if last.chunk.identity.chunk_id != part.chunk.identity.chunk_id
                           and fits((last, part)) else [])
            current.append(part)
            if len(windows) >= policy.max_windows:
                raise WindowBudgetError('window_limit')
    if current:
        windows.append(RelationWindow(entities, tuple(current)))
    return tuple(windows)


def relation_windows(extractor: RelationExtractor, entities: Sequence[SectionEntity],
                     chunks: Sequence[SourceChunk], policy: WindowPolicy) -> tuple[RelationWindow, ...]:
    entities, chunks = tuple(entities), tuple(chunks)
    if not entities and not chunks:
        return ()
    course = entities[0].course_id if entities else chunks[0].identity.course_id
    _check_entities(course, entities)
    _check_chunks(course, chunks)
    if len(entities) < 2 or not any(c.text.strip() for c in chunks):
        return ()
    try:
        return _source_windows(extractor, entities, chunks, policy)
    except WindowBudgetError as exc:
        if exc.reason != 'input_budget' or len(entities) <= 2:
            raise
    # No quadratic materialization or unbounded fallback. Each pair must see
    # every source range; the cap is checked before any provider call.
    if len(entities) * (len(entities) - 1) // 2 > policy.max_windows:
        raise WindowBudgetError('window_limit')
    result = []
    for pair in combinations(entities, 2):
        windows = _source_windows(extractor, pair, chunks, policy)
        if len(result) + len(windows) > policy.max_windows:
            raise WindowBudgetError('window_limit')
        result.extend(windows)
    return tuple(result)
