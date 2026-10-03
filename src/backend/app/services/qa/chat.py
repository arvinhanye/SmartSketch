"""J07 request preparation and terminal event assembly for grounded chat."""

from __future__ import annotations

import copy
import logging
import sqlite3
import time
from collections.abc import Iterator
from dataclasses import dataclass, field
from threading import Event
from typing import Any

from app.config import Settings
from app.repositories.chunks import ChunkStoreError, get_chunks
from app.repositories.materials import material_names
from app.repositories.graph_migrations import VectorSpaceError, sqlite_current_space
from app.repositories.graph_search import search_subgraph
from app.repositories.neo4j import Neo4jRepository, RepositoryError, read_deadline
from app.repositories.vector_search import search_chunks
from app.services.ai.client import ModelCallError
from app.services.ai.embeddings import (
    EmbeddingAdapter, EmbeddingBatchError, EmbeddingDeadlineExceeded, EmbeddingRecordError, embedding_calls,
)
from app.services.qa.citations import CitationStream, Evidence, TruncatedAnswer, not_covered
from app.services.qa.context import ContextBudget, EvidenceContext, build_context
from app.services.qa.generate import AnswerGeneration, AnswerGenerator, GenerationError
from app.services.qa.rewrite import QueryRewriter
from app.services.versions.resolver import PublishedVersion


logger = logging.getLogger(__name__)

_MESSAGES = {
    "LLM_UNAVAILABLE": "问答模型暂不可用，请稍后重试",
    "STORAGE_UNAVAILABLE": "课程资料暂不可用，请稍后重试",
    "BUDGET_EXCEEDED": "当前模型调用额度不足，请稍后重试",
    "INTERNAL_ERROR": "问答暂时失败，请稍后重试",
    "MODEL_CONFIG_REQUIRED": "请先在「模型 API 设置」中保存你的模型 API 配置",
}


class ChatFailure(Exception):
    def __init__(self, code: str, *, reason: str | None = None) -> None:
        self.code = code
        self.reason = reason
        super().__init__(code)

    @property
    def status_code(self) -> int:
        return {"BUDGET_EXCEEDED": 429, "INTERNAL_ERROR": 500, "MODEL_CONFIG_REQUIRED": 409}.get(self.code, 503)

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
                 rewriter: QueryRewriter | None, generator: AnswerGenerator | None) -> None:
        self.settings = settings
        self.repo = repo
        self.embedding = embedding
        self.rewriter = rewriter
        self.generator = generator
        self.current_space = sqlite_current_space(settings.SQLITE_URL)

    def with_models(self, rewriter: QueryRewriter, generator: AnswerGenerator) -> ChatService:
        """personal 模式：同一份检索依赖，换上当前用户的改写器与生成器（ADR-080 决定 4）。"""
        bound = copy.copy(self)
        bound.rewriter, bound.generator = rewriter, generator
        return bound

    def prepare(self, *, version: PublishedVersion, request_id: str, started: float,
                question: str, history: list[object] | None, kp_id: str | None) -> PreparedChat:
        """One deadline (``started`` + ``LLM_CHAT_TIMEOUT_SECONDS``) bounds rewrite, query embedding,
        graph retrieval and, later, generation (ADR-082 决定 3). Each step is checked before it starts,
        so nothing goes out once the deadline has passed; a failure after it is reported as ``timeout``.
        """
        deadline = started + self.settings.LLM_CHAT_TIMEOUT_SECONDS

        def check() -> None:
            if time.monotonic() >= deadline:
                raise ChatFailure("LLM_UNAVAILABLE", reason="timeout")

        rewritten = self.rewriter.rewrite(question, history, course_id=version.course_id,
                                          request_id=request_id, deadline=deadline)
        query = rewritten.query
        check()
        try:
            with read_deadline(deadline), embedding_calls(course_id=version.course_id, request_id=request_id):
                [vector] = self.embedding.embed((query,), deadline=deadline)
                check()
                space = self.current_space()
                scope = version.graph_scope()
                hits = search_chunks(self.repo, scope, version.revision_ids, vector, space=space,
                                     limit=self.settings.QA_VECTOR_LIMIT)
                check()
                graph = search_subgraph(self.repo, scope, version.revision_ids, (query,),
                                        seed_kp_ids=(kp_id,) if kp_id else ())
                check()
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
        except EmbeddingDeadlineExceeded as error:
            raise ChatFailure("LLM_UNAVAILABLE", reason="timeout") from error
        except EmbeddingRecordError as error:      # model_calls 预写失败：请求未发出（ADR-082 决定 6）
            check()
            raise ChatFailure("STORAGE_UNAVAILABLE") from error
        except (EmbeddingBatchError, ModelCallError) as error:
            check()
            raise ChatFailure("LLM_UNAVAILABLE") from error
        except (RepositoryError, VectorSpaceError, ChunkStoreError, sqlite3.Error) as error:
            check()
            raise ChatFailure("STORAGE_UNAVAILABLE") from error
        check()
        return PreparedChat(version, request_id, started, deadline, query, context)

    def _document_names(self, course_id: str, context: EvidenceContext) -> dict[str, str]:
        """引用的资料文件名（L12，ADR-085）；只取同课资料，查不到或出错都只是省略文件名，不影响回答。"""
        try:
            return material_names(self.settings.SQLITE_URL, course_id=course_id,
                                  material_ids={chunk.document_id for chunk in context.chunks})
        except sqlite3.Error as error:
            logger.warning("chat citation document names unavailable (%s)", type(error).__name__)
            return {}

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
            names = self._document_names(prepared.version.course_id, context)
            citations = CitationStream(
                prepared.version, prepared.request_id,
                (Evidence(chunk.index, chunk.chunk_id, chunk.document_id,
                          prepared.version.course_id, chunk.revision_id, chunk.text,
                          page=chunk.page, section_path=chunk.section_path,
                          document_name=names.get(chunk.document_id))
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
        except TruncatedAnswer:
            # ADR-082 决定 2：截断且出处校验不通过是生成故障，不归「资料未覆盖」
            _capture_audit(prepared, citations)
            yield {"event": "error", "error": ChatFailure("LLM_UNAVAILABLE", reason="truncated").body(prepared.request_id)}
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
