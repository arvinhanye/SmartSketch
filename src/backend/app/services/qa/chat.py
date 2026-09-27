"""J07 request preparation and terminal event assembly for grounded chat."""

from __future__ import annotations

import sqlite3
import time
from collections.abc import Iterator
from dataclasses import dataclass, field
from threading import Event
from typing import Any

from app.config import Settings
from app.repositories.chunks import ChunkStoreError, get_chunks
from app.repositories.graph_migrations import VectorSpaceError, sqlite_current_space
from app.repositories.graph_search import search_subgraph
from app.repositories.neo4j import Neo4jRepository, RepositoryError
from app.repositories.vector_search import search_chunks
from app.services.ai.client import ModelCallError
from app.services.ai.embeddings import EmbeddingAdapter, EmbeddingBatchError
from app.services.qa.citations import CitationStream, Evidence, not_covered
from app.services.qa.context import ContextBudget, EvidenceContext, build_context
from app.services.qa.generate import AnswerGeneration, AnswerGenerator, GenerationError
from app.services.qa.rewrite import QueryRewriter
from app.services.versions.resolver import PublishedVersion


_MESSAGES = {
    "LLM_UNAVAILABLE": "问答模型暂不可用，请稍后重试",
    "STORAGE_UNAVAILABLE": "课程资料暂不可用，请稍后重试",
    "BUDGET_EXCEEDED": "当前模型调用额度不足，请稍后重试",
    "INTERNAL_ERROR": "问答暂时失败，请稍后重试",
}


class ChatFailure(Exception):
    def __init__(self, code: str, *, reason: str | None = None) -> None:
        self.code = code
        self.reason = reason
        super().__init__(code)

    @property
    def status_code(self) -> int:
        return {"BUDGET_EXCEEDED": 429, "INTERNAL_ERROR": 500}.get(self.code, 503)

    def body(self, request_id: str | None = None) -> dict[str, Any]:
        details: dict[str, str] = {}
        if request_id is not None:
            details["request_id"] = request_id
        if self.reason is not None:
            details["reason"] = self.reason
        return {"code": self.code, "message": _MESSAGES[self.code], "details": details}


@dataclass
class ChatAudit:
    unknown_citation_count: int = 0
    invalidation_subtype: str | None = None
    uncovered_unit_count: int = 0
    truncated: bool = False
    first_delta_latency_ms: int | None = None


@dataclass(frozen=True)
class PreparedChat:
    version: PublishedVersion
    request_id: str
    started: float
    deadline: float
    query: str
    context: EvidenceContext
    audit: ChatAudit = field(default_factory=ChatAudit)

    @property
    def related_kp_ids(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys((*self.context.graph.kp_ids,
                                        *(kp for chunk in self.context.chunks for kp in chunk.kp_ids))))

    def latency_ms(self) -> int:
        return max(0, int((time.monotonic() - self.started) * 1000))


def _capture_audit(prepared: PreparedChat, citations: CitationStream | None) -> None:
    if citations is not None:
        prepared.audit.unknown_citation_count = citations.unknown_count
        prepared.audit.invalidation_subtype = citations.invalidation_subtype
        prepared.audit.uncovered_unit_count = citations.uncited_units
        prepared.audit.truncated = citations.truncated


class ChatService:
    def __init__(self, settings: Settings, repo: Neo4jRepository, embedding: EmbeddingAdapter,
                 rewriter: QueryRewriter, generator: AnswerGenerator) -> None:
        self.settings = settings
        self.repo = repo
        self.embedding = embedding
        self.rewriter = rewriter
        self.generator = generator
        self.current_space = sqlite_current_space(settings.SQLITE_URL)

    def prepare(self, *, version: PublishedVersion, request_id: str, started: float,
                question: str, history: list[object] | None, kp_id: str | None) -> PreparedChat:
        deadline = started + self.settings.LLM_CHAT_TIMEOUT_SECONDS
        rewritten = self.rewriter.rewrite(question, history, course_id=version.course_id,
                                          request_id=request_id, deadline=deadline)
        query = rewritten.query
        try:
            [vector] = self.embedding.embed((query,))
            space = self.current_space()
            scope = version.graph_scope()
            hits = search_chunks(self.repo, scope, version.revision_ids, vector, space=space,
                                 limit=self.settings.QA_VECTOR_LIMIT)
            graph = search_subgraph(self.repo, scope, version.revision_ids, (query,),
                                    seed_kp_ids=(kp_id,) if kp_id else ())
            context = build_context(
                course_id=version.course_id, revision_ids=version.revision_ids,
                vector_hits=hits, subgraph=graph,
                load_chunks=lambda ids: get_chunks(self.settings.SQLITE_URL, course_id=version.course_id,
                                                   chunk_ids=ids),
                threshold=self.settings.QA_SIMILARITY_THRESHOLD,
                budget=ContextBudget(self.settings.QA_CONTEXT_CHUNK_TOKENS,
                                     self.settings.QA_CONTEXT_GRAPH_TOKENS,
                                     self.settings.QA_CONTEXT_MAX_CHUNKS),
            )
        except (EmbeddingBatchError, ModelCallError) as error:
            raise ChatFailure("LLM_UNAVAILABLE") from error
        except (RepositoryError, VectorSpaceError, ChunkStoreError, sqlite3.Error) as error:
            raise ChatFailure("STORAGE_UNAVAILABLE") from error
        if time.monotonic() >= deadline:
            raise ChatFailure("LLM_UNAVAILABLE", reason="timeout")
        return PreparedChat(version, request_id, started, deadline, query, context)

    def events(self, prepared: PreparedChat, stop: Event | None = None) -> Iterator[dict[str, Any]]:
        context = prepared.context
        status = "answered" if context.covered else "not_covered"
        yield {"event": "meta", "status": status, "retrieved": context.retrieved,
               "graph_version": prepared.version.graph_version, "request_id": prepared.request_id}
        if not context.covered:
            final = not_covered(context.reason.value, graph_version=prepared.version.graph_version,
                                request_id=prepared.request_id, latency_ms=prepared.latency_ms(),
                                related_kp_ids=prepared.related_kp_ids)
            yield {"event": "done", "final": final}
            return

        generation: AnswerGeneration | None = None
        citations: CitationStream | None = None
        try:
            candidate = self.generator.generate(prepared.query, context,
                                                course_id=prepared.version.course_id,
                                                request_id=prepared.request_id,
                                                deadline=prepared.deadline)
            if not isinstance(candidate, AnswerGeneration):
                raise ChatFailure("INTERNAL_ERROR")
            generation = candidate
            citations = CitationStream(
                prepared.version, prepared.request_id,
                (Evidence(chunk.index, chunk.chunk_id, chunk.document_id,
                          prepared.version.course_id, chunk.revision_id, chunk.text,
                          page=chunk.page, section_path=chunk.section_path)
                 for chunk in context.chunks),
            )
            for raw in generation:
                if stop is not None and stop.is_set():
                    return
                delta = citations.feed(raw)
                if delta:
                    if prepared.audit.first_delta_latency_ms is None:
                        prepared.audit.first_delta_latency_ms = prepared.latency_ms()
                    yield {"event": "delta", "delta": delta}
                if citations.stop_supplier:
                    generation.close()
                    break
            if stop is not None and stop.is_set():
                return
            if time.monotonic() >= prepared.deadline:
                raise ChatFailure("LLM_UNAVAILABLE", reason="timeout")
            tail = citations.finish()
            if tail:
                if prepared.audit.first_delta_latency_ms is None:
                    prepared.audit.first_delta_latency_ms = prepared.latency_ms()
                yield {"event": "delta", "delta": tail}
            final = citations.finalize(
                latency_ms=prepared.latency_ms(),
                truncated=bool(generation.result and generation.result.truncated),
                related_kp_ids=prepared.related_kp_ids,
            )
            _capture_audit(prepared, citations)
            yield {"event": "done", "final": final}
        except GenerationError as error:
            _capture_audit(prepared, citations)
            yield {"event": "error", "error": ChatFailure(error.code, reason=error.details_reason).body(prepared.request_id)}
        except ChatFailure as error:
            _capture_audit(prepared, citations)
            yield {"event": "error", "error": error.body(prepared.request_id)}
        except Exception:
            _capture_audit(prepared, citations)
            yield {"event": "error", "error": ChatFailure("INTERNAL_ERROR").body(prepared.request_id)}
        finally:
            if generation is not None:
                generation.close()
