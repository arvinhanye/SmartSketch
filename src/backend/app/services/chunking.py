"""D08: chapter-aware semantic windows over immutable parser blocks.

Offsets in ``ChunkSource`` are half-open character offsets into ``ParsedBlock.text``.
The section-path prefixes are presentation text, not parser text, so they have no
source offsets of their own. D09 can assign stable identities to the returned
sequential chunk ordinals without changing the parser's block ordinals.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from bisect import bisect_right
import re

from app.services.parsers.models import ParsedBlock, SourceLocator


DEFAULT_TARGET_CHARS = 1500
DEFAULT_OVERLAP_CHARS = 200
_SENTENCE_END = re.compile(
    r"[。！？!?；;](?:[”’\"']+)?|(?<!\d)\.(?:[”’\"']+)?(?=\s|$)|\n+"
)


@dataclass(frozen=True, slots=True)
class ChunkSource:
    """The exact slice of one parser block represented in a chunk."""

    block_ordinal: int
    start: int
    end: int
    locator: SourceLocator


@dataclass(frozen=True, slots=True)
class SemanticChunk:
    """One extraction window and all parser locations contributing to it."""

    ordinal: int
    text: str
    section_titles: tuple[str, ...]
    sources: tuple[ChunkSource, ...]


def _render(sources: list[ChunkSource], by_ordinal: dict[int, ParsedBlock]) -> str:
    parts: list[str] = []
    for source in sources:
        block = by_ordinal[source.block_ordinal]
        path = source.locator.section_path
        body = block.text[source.start:source.end]
        if path:
            parts.append(f"{path}\n{body}")
        else:
            parts.append(body)
    return "\n\n".join(parts)


def _chunk_run(
    blocks: list[ParsedBlock], ordinal_start: int, target_chars: int, overlap_chars: int
) -> list[SemanticChunk]:
    # Budget the prefixes and separators as well as parser text, so a chapter
    # with many tiny paragraphs still yields approximately target-sized text.
    stream_parts: list[str] = []
    positions: list[tuple[int, int, ParsedBlock]] = []
    prefix_lengths: list[int] = []
    position = 0
    for block in blocks:
        path = block.locator.section_path
        prefix = f"{path}\n" if path else ""
        body_start = position + len(prefix)
        body_end = body_start + len(block.text)
        positions.append((body_start, body_end, block))
        prefix_lengths.append(len(prefix))
        stream_parts.extend((prefix, block.text, "\n\n"))
        position = body_end + 2
    stream = "".join(stream_parts)[:-2]
    body_starts = [item[0] for item in positions]
    body_starts_by_ordinal = {block.ordinal: body_start for body_start, _, block in positions}

    max_prefix_length = max(prefix_lengths, default=0)
    if max_prefix_length + 1 > target_chars:
        raise ValueError("section_path prefix leaves no room for source text within target_chars")
    # A very long repeated path consumes the space otherwise available for overlap.
    # Keep at least one new source character per window to guarantee progress.
    effective_overlap = min(overlap_chars, target_chars - max_prefix_length - 1)

    boundaries = [match.end() for match in _SENTENCE_END.finditer(stream)]
    by_ordinal = {block.ordinal: block for block in blocks}

    def sources_for(start: int, end: int) -> list[ChunkSource]:
        sources: list[ChunkSource] = []
        first = max(0, bisect_right(body_starts, start) - 1)
        for index in range(first, len(positions)):
            block_start, block_end, block = positions[index]
            if block_start >= end:
                break
            left, right = max(start, block_start), min(end, block_end)
            if left < right:
                sources.append(
                    ChunkSource(block.ordinal, left - block_start, right - block_start, block.locator)
                )
        return sources

    result: list[SemanticChunk] = []
    start = 0
    while start < len(stream):
        limit = min(start + target_chars, len(stream))
        end = limit
        if limit < len(stream):
            # Prefer a nearby sentence/paragraph end; an oversized sentence is
            # deliberately hard-split rather than allowed to stall progress.
            boundary_index = bisect_right(boundaries, limit) - 1
            if boundary_index >= 0 and boundaries[boundary_index] >= start + target_chars * 4 // 5:
                end = boundaries[boundary_index]

        sources = sources_for(start, end)
        if sources:
            text = _render(sources, by_ordinal)
            if len(text) > target_chars:
                # A window can begin inside the first block's presentation prefix.
                # Rendering restores that full prefix, so cap by actual output size.
                first_source = sources[0]
                first_block_start = body_starts_by_ordinal[first_source.block_ordinal]
                minimum_end = first_block_start + first_source.start + 1
                low, high = minimum_end, end
                best_end = minimum_end
                while low <= high:
                    candidate_end = (low + high) // 2
                    candidate_sources = sources_for(start, candidate_end)
                    candidate_text = _render(candidate_sources, by_ordinal)
                    if len(candidate_text) <= target_chars:
                        best_end = candidate_end
                        low = candidate_end + 1
                    else:
                        high = candidate_end - 1
                end = best_end
                sources = sources_for(start, end)
                text = _render(sources, by_ordinal)
            result.append(
                SemanticChunk(
                    ordinal=ordinal_start + len(result),
                    text=text,
                    section_titles=blocks[0].locator.section_titles,
                    sources=tuple(sources),
                )
            )
        if end == len(stream):
            break
        start = max(start + 1, end - effective_overlap)
    return result


def chunk_blocks(
    blocks: Iterable[ParsedBlock],
    *,
    target_chars: int = DEFAULT_TARGET_CHARS,
    overlap_chars: int = DEFAULT_OVERLAP_CHARS,
) -> tuple[SemanticChunk, ...]:
    """Group consecutive blocks by chapter, then create overlapping semantic windows.

    The chapter key is ``section_titles``, not ``section_path``: the latter
    includes paragraph numbers for non-PDF formats and would prevent merging.
    Empty iterables return an empty tuple, independently of ``ParsedDocument``'s
    non-empty invariant. ``overlap_chars`` must be smaller than ``target_chars``.
    """
    if type(target_chars) is not int or target_chars < 1:
        raise ValueError("target_chars must be a positive integer")
    if type(overlap_chars) is not int or not 0 <= overlap_chars < target_chars:
        raise ValueError("overlap_chars must be a nonnegative integer smaller than target_chars")

    ordered = list(blocks)
    if not all(isinstance(block, ParsedBlock) for block in ordered):
        raise TypeError("blocks must contain ParsedBlock values")
    if [block.ordinal for block in ordered] != list(range(len(ordered))):
        raise ValueError("parser block ordinals must be consecutive from zero")

    chunks: list[SemanticChunk] = []
    run: list[ParsedBlock] = []
    for block in ordered:
        if run and block.locator.section_titles != run[-1].locator.section_titles:
            chunks.extend(_chunk_run(run, len(chunks), target_chars, overlap_chars))
            run = []
        run.append(block)
    if run:
        chunks.extend(_chunk_run(run, len(chunks), target_chars, overlap_chars))
    return tuple(chunks)
