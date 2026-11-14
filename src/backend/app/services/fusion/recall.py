"""Bounded union of name/alias, lexical and real-vector nearest-neighbour retrieval.

Retrieval scores are ranks, never semantic confidence or permission to merge.
Lexical postings avoid scanning unrelated pairs. Exact vector top-k uses O(n*k)
retained results, O(n²*d) arithmetic; it creates no model calls or all-pairs table.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
import heapq
import math
import re
import unicodedata

from app.services.ai.embeddings import EmbeddedVector
from app.services.fusion.candidates import cosine_similarity
from app.services.fusion.normalize import normalize_name

RECALL_VERSION = 1


@dataclass(frozen=True)
class RecallCard:
    entity_id: str
    course_id: str
    name: str = field(repr=False)
    definition: str = field(repr=False)
    aliases: tuple[str, ...] = field(default=(), repr=False)


@dataclass(frozen=True)
class RecalledPair:
    left_id: str
    right_id: str
    channels: tuple[str, ...]
    rank_score: float


@dataclass(frozen=True)
class RecallResult:
    pairs: tuple[RecalledPair, ...]
    total_possible_pairs: int
    truncated_pairs: int
    missing_channels: tuple[str, ...]
    limited_queries: int
    version: int = RECALL_VERSION


def _terms(text: str) -> Counter:
    text = unicodedata.normalize("NFKC", text).casefold()
    words = re.findall(r"[a-z0-9_]+|[\u3400-\u9fff]+", text)
    return Counter(token for word in words for token in
                   ([word] if word.isascii() or len(word) < 2 else
                    [word[i:i+2] for i in range(len(word)-1)]))


def recall_candidates(cards: Sequence[RecallCard], *, top_k: int, max_pairs: int,
                      vectors: Mapping[str, EmbeddedVector] | None = None) -> RecallResult:
    if any(type(n) is not int or n < 1 for n in (top_k, max_pairs)):
        raise ValueError("positive retrieval budgets required")
    items = sorted(cards, key=lambda c: c.entity_id)
    ids = {c.entity_id for c in items}
    if len(ids) != len(items) or len({c.course_id for c in items}) > 1:
        raise ValueError("duplicate ID or cross-course corpus")
    if any(not c.entity_id or not c.course_id for c in items):
        raise ValueError("missing corpus scope")
    if vectors is not None:
        if set(vectors) != ids:
            raise ValueError("incomplete vector corpus")
        spaces = {v.space for v in vectors.values()}
        if len(spaces) > 1 or any(not s.startswith("real/") or "demo" in s for s in spaces):
            raise ValueError("a single real semantic vector space is required")
        for v in vectors.values():
            cosine_similarity(v, v)  # dimension, finite-value and nonzero checks
    names, postings, tokens = defaultdict(set), defaultdict(set), {}
    for c in items:
        for name in (c.name, *c.aliases):
            for key in normalize_name(name).keys:
                names[key].add(c.entity_id)
        tokens[c.entity_id] = _terms(" ".join((c.name, *c.aliases, c.definition)))
        for term in tokens[c.entity_id]:
            postings[term].add(c.entity_id)
    lengths = {k: sum(v.values()) for k, v in tokens.items()}
    avg = sum(lengths.values()) / max(1, len(items)) or 1
    found: dict[tuple[str, str], dict[str, float]] = {}
    limited = 0

    def add(a: str, scores: Mapping[str, float], channel: str):
        nonlocal limited
        usable = [(b, s) for b, s in scores.items() if b != a and s > 0]
        limited += len(usable) > top_k
        for rank, (b, _) in enumerate(heapq.nsmallest(top_k, usable, key=lambda p: (-p[1], p[0])), 1):
            key = tuple(sorted((a, b)))
            found.setdefault(key, {})[channel] = max(found.get(key, {}).get(channel, 0), 1/(60+rank))

    for c in items:
        own = set()
        for name in (c.name, *c.aliases):
            for key in normalize_name(name).keys:
                own.update(names[key])
        add(c.entity_id, {k: 1. for k in own}, "name")
        scores: dict[str, float] = defaultdict(float)
        for term in tokens[c.entity_id]:
            hits = postings[term]
            idf = math.log(1 + (len(items)-len(hits)+0.5)/(len(hits)+0.5))
            for other in hits:
                tf = tokens[other][term]
                scores[other] += idf * tf * 2.2 / (tf + 1.2*(0.25+0.75*lengths[other]/avg))
        add(c.entity_id, scores, "lexical")
        if vectors is not None:
            add(c.entity_id, {other: cosine_similarity(vectors[c.entity_id], vectors[other])
                              for other in ids if other != c.entity_id}, "vector")
    pairs = [RecalledPair(a, b, tuple(sorted(channels)), sum(channels.values()))
             for (a, b), channels in found.items()]
    pairs.sort(key=lambda p: (-p.rank_score, p.left_id, p.right_id))
    return RecallResult(tuple(pairs[:max_pairs]), len(items)*(len(items)-1)//2,
                        max(0, len(pairs)-max_pairs), ("vector",) if vectors is None else (), limited)
