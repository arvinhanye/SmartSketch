"""演示模型模式（ADR-079）：``LLM_MODE=demo`` / ``EMBEDDING_MODE=demo``。

确定性、无网络的规则「模型」，让真实服务链路在没有付费模型时产出合理结果：

- 配置：两个模式新增 ``demo``；生产环境与 ``fake`` 一样禁止；演示向量自成一个空间（保留模型 ID），
  不与 ``fake/<维度>`` 混用。
- 抽取：演示客户端的输出能被 E05 实体、E06 补漏、E11 关系的真实解析与校验器原样接受（零丢弃）；
  用 ``tests/fixtures/documents/stack-queue-notes.md`` 走 worker 的解析 → 抽取阶段推进到 ``merging``；
  ``PREREQUISITE`` 只在有先修表述时给出，且始终无环。
- 问答：演示向量让字面重叠的问题越过相似度闸门、无关问题被拒；生成对覆盖问题逐句带 ``[n]`` 引用，
  经 J06 校验为 ``answered``；无重叠时输出哨兵，得到 ``NOT_COVERED``；改写原样返回问题。
"""

from __future__ import annotations

import hashlib
import json
import math
import secrets
import time
from pathlib import Path

import pytest

from app.config import DEMO_EMBEDDING_MODEL, SettingsError, embedding_space_identity, load_settings
from app.repositories import task_leases, tasks
from app.repositories.chunks import list_chunks
from app.repositories.model_calls import SqliteCallStore
from app.repositories.sqlite import migrate
from app.repositories.vector_search import ChunkHit
from app.services.ai.client import EmbeddingRequest, Message, ModelRequest, StreamDelta, StreamDone
from app.services.ai.demo import (
    DEMO_MODEL_ID,
    DemoEmbeddingClient,
    DemoModelClient,
    demo_vector,
)
from app.services.ai.embeddings import EmbeddingAdapter
from app.services.ai.entities import EntityExtractor
from app.services.ai.factory import build_embedding_client, build_model_clients, model_id
from app.services.ai.fake import FakeEmbeddingClient, FakeModelClient
from app.services.ai.gleaning import EntityGleaner, StopReason
from app.services.ai.policy import ModelCallPolicy
from app.services.ai.relations import RelationExtractor, SectionEntity, SourceChunk
from app.services.chunk_identity import ChunkIdentity, derive_chunk_id, text_sha256
from app.services.file_storage import FileStorage, StoredFile
from app.services.qa.citations import CitationStream, Evidence
from app.services.qa.context import ContextBudget, ContextReason, build_context
from app.services.qa.generate import AnswerGeneration, AnswerGenerator
from app.services.qa.rewrite import QueryRewriter, RewriteReason
from app.services.startup import validate_embedding_space
from app.services.versions.resolver import PublishedVersion
from app.workers import runner
from app.workers.extract_task import ExtractLimits, ExtractStatus, load_candidates, run_extract_stage
from app.workers.parse_task import ParseStatus, run_parse_stage

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "tests" / "fixtures" / "documents" / "stack-queue-notes.md"
COURSE = "course-demo"
#: 演示模式建议的相似度阈值（写入 .env.example 注释与交接）；本文件的闸门测试据此断言。
DEMO_THRESHOLD = 0.58

PREREQ_TEXT = (
    "# 第4章 队列\n\n"
    "队列是一种先进先出的线性表。\n"
    "循环队列是队列的一种实现。学习循环队列之前需要先掌握队列。\n"
    "学习队列之前需要先掌握循环队列。\n"
    "双端队列建立在队列的基础上。\n"
    "银行排队是队列的例子。\n"
)


# ---------------------------------------------------------------- 配置与装配


def _env(**overrides: str) -> dict[str, str]:
    base = {"LLM_MODE": "demo", "EMBEDDING_MODE": "demo"}
    base.update(overrides)
    return base


def test_demo_modes_load_and_are_forbidden_in_production():
    settings = load_settings(_env())
    assert (settings.LLM_MODE, settings.EMBEDDING_MODE) == ("demo", "demo")
    with pytest.raises(SettingsError) as raised:
        load_settings(_env(APP_ENV="production"))
    assert "LLM_MODE" in str(raised.value) and "EMBEDDING_MODE" in str(raised.value)
    # 演示不需要任何供应商变量
    assert load_settings(_env(LLM_EXTRACTION_MODEL="", LLM_API_KEY="")).LLM_MODE == "demo"


def test_reserved_demo_embedding_model_cannot_be_used_by_real_modes():
    with pytest.raises(SettingsError, match="EMBEDDING_MODEL"):
        load_settings({"EMBEDDING_MODE": "local", "EMBEDDING_MODEL": DEMO_EMBEDDING_MODEL})


def test_demo_embedding_space_is_distinct_from_fake(tmp_path):
    demo = load_settings(_env(SQLITE_URL=f"sqlite:///{tmp_path / 'a.sqlite3'}"))
    fake = load_settings({"SQLITE_URL": f"sqlite:///{tmp_path / 'a.sqlite3'}"})
    assert embedding_space_identity(demo) == (DEMO_EMBEDDING_MODEL, 1024, 0)
    assert embedding_space_identity(fake) == ("", 1024, 1)
    demo_space = EmbeddingAdapter(demo, DemoEmbeddingClient()).space
    assert demo_space == f"real/{DEMO_EMBEDDING_MODEL}/1024"
    assert demo_space != EmbeddingAdapter(fake, FakeEmbeddingClient()).space
    # 启动门禁：先以 demo 记录空间，再以 fake 启动即拒绝（须离线重新向量化）
    migrate(demo.SQLITE_URL)
    validate_embedding_space(demo)
    with pytest.raises(SettingsError, match="mismatch"):
        validate_embedding_space(fake)


def test_factory_builds_demo_clients_and_keeps_fake_mode():
    demo = load_settings(_env(LLM_EXTRACTION_MODEL="deepseek-flash", LLM_CHAT_MODEL="deepseek-flash"))
    primary, fallback = build_model_clients(demo)
    assert isinstance(primary, DemoModelClient) and fallback is None
    # 演示输出不能记在真实模型名下（避免与 live 抽取缓存键混淆）
    assert model_id(demo, "extraction") == model_id(demo, "chat") == DEMO_MODEL_ID
    assert isinstance(build_embedding_client(demo), DemoEmbeddingClient)

    fake = load_settings({})
    primary, fallback = build_model_clients(fake)
    assert type(primary) is FakeModelClient and fallback is None
    assert model_id(fake, "extraction") == "fake"
    assert type(build_embedding_client(fake)) is FakeEmbeddingClient


# ---------------------------------------------------------------- 抽取


def _chunks_of(data: bytes, fmt: str = "markdown") -> list[tuple[ChunkIdentity, str, tuple[str, ...]]]:
    from app.services.chunking import chunk_blocks
    from app.workers.parse_task import parse_document

    chunks = chunk_blocks(parse_document(fmt, data).blocks)
    revision = "rev_" + hashlib.sha256(data).hexdigest()
    out = []
    for chunk in chunks:
        identity = ChunkIdentity(
            chunk_id=derive_chunk_id(revision, chunk.ordinal), course_id=COURSE, document_id="doc-1",
            revision_id=revision, ordinal=chunk.ordinal, text_sha256=text_sha256(chunk.text),
            sources=chunk.sources,
        )
        out.append((identity, chunk.text, chunk.section_titles))
    return out


def test_entity_output_is_accepted_without_drops():
    extractor = EntityExtractor(DemoModelClient(), model=DEMO_MODEL_ID, max_output_tokens=4096)
    names: set[str] = set()
    for identity, text, _ in _chunks_of(FIXTURE.read_bytes()):
        result = extractor.extract(identity, text)
        assert result.ok, result.failure
        assert result.dropped == {}, (text, result.dropped)
        assert result.model_calls == (1 if text.strip() else 0)
        for candidate in result.candidates:
            assert candidate.evidence in text
            assert candidate.source.sources
        names |= {c.name for c in result.candidates}
    assert {"栈", "栈顶", "后进先出", "顺序栈", "链栈", "队列", "先进先出", "循环队列", "栈与队列"} <= names
    # 虚构声明句不是课程知识
    assert not any("讲义" in name or "SmartSketch" in name for name in names)


def test_gleaning_finds_nothing_new():
    client = DemoModelClient()
    extractor = EntityExtractor(client, model=DEMO_MODEL_ID, max_output_tokens=4096)
    gleaner = EntityGleaner(client, model=DEMO_MODEL_ID, max_output_tokens=4096, enabled=True)
    identity, text, _ = _chunks_of(FIXTURE.read_bytes())[1]
    first = extractor.extract(identity, text)
    assert first.candidates
    result = gleaner.glean(identity, text, first.candidates)
    assert result.ok and result.added == () and result.stop_reason is StopReason.NO_NEW_ENTITIES


def _section_relations(data: bytes):
    client = DemoModelClient()
    extractor = EntityExtractor(client, model=DEMO_MODEL_ID, max_output_tokens=4096)
    relations = RelationExtractor(client, model=DEMO_MODEL_ID, max_output_tokens=4096)
    sections: dict[tuple[str, ...], list] = {}
    for identity, text, titles in _chunks_of(data):
        sections.setdefault(titles, []).append((identity, text))
    found = []
    for titles, members in sections.items():
        entities: dict[str, SectionEntity] = {}
        for identity, text in members:
            for candidate in extractor.extract(identity, text).candidates:
                key = f"e{len(entities)}"
                if candidate.name not in {e.name for e in entities.values()}:
                    entities[key] = SectionEntity(key, COURSE, candidate.name, candidate.type)
        result = relations.extract(COURSE, list(entities.values()),
                                   [SourceChunk(identity, text) for identity, text in members])
        assert result.ok and result.dropped == {}, (titles, result.dropped)
        names = {e.entity_id: e.name for e in entities.values()}
        found += [(names[r.from_id], r.type, names[r.to_id]) for r in result.candidates]
    return found


def test_relations_follow_headings_and_are_accepted_without_drops():
    found = _section_relations(FIXTURE.read_bytes())
    assert ("栈与队列", "CONTAINS", "顺序栈") in found
    assert ("顺序栈", "CONTAINS", "栈顶") not in found  # 只包含本节定义的知识点
    assert ("栈与队列", "CONTAINS", "栈") in found
    assert ("队列", "CONTAINS", "循环队列") in found
    assert not [r for r in found if r[1] == "PREREQUISITE"]  # 资料没有先修表述


def _acyclic(edges: list[tuple[str, str]]) -> bool:
    graph: dict[str, set[str]] = {}
    for a, b in edges:
        graph.setdefault(a, set()).add(b)
    state: dict[str, int] = {}

    def visit(node: str) -> bool:
        state[node] = 1
        for nxt in graph.get(node, ()):
            if state.get(nxt) == 1 or (state.get(nxt) is None and not visit(nxt)):
                return False
        state[node] = 2
        return True

    return all(state.get(node) == 2 or visit(node) for node in list(graph))


def test_prerequisite_needs_cue_keeps_direction_and_stays_acyclic():
    found = _section_relations(PREREQ_TEXT.encode("utf-8"))
    prereq = [(a, b) for a, t, b in found if t == "PREREQUISITE"]
    assert ("队列", "循环队列") in prereq  # 学习循环队列之前需要先掌握队列
    assert ("循环队列", "队列") not in prereq  # 与已有边成环的反向表述被舍弃
    assert ("队列", "双端队列") in prereq  # 建立在……的基础上
    assert _acyclic(prereq)
    assert ("银行排队", "EXAMPLE_OF", "队列") in found


def test_unparseable_prompts_fall_back_to_empty_valid_json():
    client = DemoModelClient()
    for purpose in ("extract_entities", "extract_relations", "repair", "extract_entities_gleaning"):
        request = ModelRequest(purpose=purpose, model="m", messages=(Message("user", "no markers"),),
                               max_output_tokens=4096, response_format="json")
        data = client.complete(request).json()
        assert data in ({"entities": []}, {"relations": []})


# ---------------------------------------------------------------- worker 抽取阶段


def _material(db_url: str, storage: FileStorage, data: bytes) -> str:
    storage_name = secrets.token_hex(16) + ".md"
    path = storage.path_for(storage_name)
    path.write_bytes(data)
    stored = StoredFile(storage_name=storage_name, path=path, original_filename="notes.md",
                        format="markdown", size_bytes=len(data),  # type: ignore[arg-type]
                        content_hash="sha256:" + hashlib.sha256(data).hexdigest())
    return tasks.create_material_task(db_url, course_id=COURSE, stored_file=stored,
                                      idempotency_key=secrets.token_hex(8)).task.id


def _extract_with_worker_toolkit(tmp_path: Path, data: bytes):
    db_url = f"sqlite:///{(tmp_path / 'state.sqlite3').as_posix()}"
    migrate(db_url)
    storage = FileStorage(tmp_path / "files", 10 * 1024 * 1024)
    settings = load_settings(_env(SQLITE_URL=db_url, STORAGE_DIR=str(tmp_path / "files")))
    task_id = _material(db_url, storage, data)
    lease = task_leases.claim_next(db_url, owner="w", lease_seconds=60, max_attempts=3)
    assert lease is not None and lease.task_id == task_id
    parsed = run_parse_stage(db_url, lease, storage=storage, max_attempts=3)
    assert parsed.status is ParseStatus.ADVANCED
    lease = task_leases.Lease(**{**lease.__dict__, "stage": "extracting", "progress": 0.10})
    outcome = run_extract_stage(db_url, lease, toolkit=runner.build_toolkit(settings),
                                limits=ExtractLimits.from_settings(settings))
    return db_url, task_id, outcome


def test_worker_extract_stage_succeeds_on_fixture(tmp_path):
    db_url, task_id, outcome = _extract_with_worker_toolkit(tmp_path, FIXTURE.read_bytes())
    assert outcome.status is ExtractStatus.ADVANCED, outcome
    assert outcome.chunks_failed == 0 and outcome.sections_failed == 0
    result = load_candidates(db_url, course_id=COURSE, task_id=task_id)
    assert len(result.entities) >= 8
    assert result.relations
    assert result.failed_chunks == () and result.failed_sections == ()


def test_worker_prerequisites_are_acyclic(tmp_path):
    db_url, task_id, outcome = _extract_with_worker_toolkit(tmp_path, PREREQ_TEXT.encode("utf-8"))
    assert outcome.status is ExtractStatus.ADVANCED
    result = load_candidates(db_url, course_id=COURSE, task_id=task_id)
    prereq = [(r.from_id, r.to_id) for r in result.relations if r.type == "PREREQUISITE"]
    assert prereq and _acyclic(prereq)


# ---------------------------------------------------------------- 向量与问答


def _cos(a: tuple[float, ...], b: tuple[float, ...]) -> float:
    return sum(x * y for x, y in zip(a, b, strict=True))


def _score(question: str, text: str) -> float:
    """与 Neo4j 余弦索引相同的归一：(1 + cos) / 2。"""
    return (1 + _cos(demo_vector(question, 1024), demo_vector(text, 1024))) / 2


def test_demo_vectors_are_deterministic_unit_and_sized():
    client = DemoEmbeddingClient()
    result = client.embed(EmbeddingRequest(model=DEMO_EMBEDDING_MODEL, texts=("栈", "", "队列"), dimensions=64))
    assert len(result.vectors) == 3 and all(len(v) == 64 for v in result.vectors)
    for vector in result.vectors:
        assert math.isclose(math.sqrt(sum(x * x for x in vector)), 1.0, rel_tol=1e-9)
    assert result.vectors[0] == demo_vector("栈", 64)
    assert result.model_responded == DEMO_EMBEDDING_MODEL


def test_lexical_overlap_beats_unrelated_text():
    texts = [text for _, text, _ in _chunks_of(FIXTURE.read_bytes())]
    stack = max(_score("什么是栈", t) for t in texts)
    queue = max(_score("队列的特点", t) for t in texts)
    unrelated = max(_score(q, t) for q in ("今天天气怎么样", "如何做红烧肉", "光合作用的原理") for t in texts)
    assert stack >= DEMO_THRESHOLD and queue >= DEMO_THRESHOLD
    assert unrelated < DEMO_THRESHOLD
    assert min(stack, queue) - unrelated > 0.05


def _policy(tmp_path: Path, client: DemoModelClient) -> ModelCallPolicy:
    db_url = f"sqlite:///{(tmp_path / 'calls.sqlite3').as_posix()}"
    migrate(db_url)
    return ModelCallPolicy(primary=client, store=SqliteCallStore(db_url), max_retries=0,
                           failure_threshold=100, open_seconds=30, task_token_budget=10**9,
                           daily_token_budget=10**9, sleep=lambda _s: None)


def _ask(tmp_path: Path, question: str) -> dict:
    """无 Neo4j 的问答链路：演示向量检索 → J04 闸门 → J05 演示生成 → J06 引用校验。"""
    db_url = f"sqlite:///{(tmp_path / 'state.sqlite3').as_posix()}"
    migrate(db_url)
    storage = FileStorage(tmp_path / "files", 10 * 1024 * 1024)
    _material(db_url, storage, FIXTURE.read_bytes())
    lease = task_leases.claim_next(db_url, owner="w", lease_seconds=60, max_attempts=3)
    assert lease is not None
    assert run_parse_stage(db_url, lease, storage=storage, max_attempts=3).status is ParseStatus.ADVANCED
    chunks = list_chunks(db_url, course_id=COURSE, material_id=lease.document_id)
    version = PublishedVersion(COURSE, "v1", 1, frozenset(c.revision_id for c in chunks))
    query = demo_vector(question, 1024)
    hits = [ChunkHit(c.chunk_id, c.revision_id, c.material_id, (1 + _cos(query, demo_vector(c.text, 1024))) / 2)
            for c in chunks]
    by_id = {c.chunk_id: c for c in chunks}
    context = build_context(course_id=COURSE, revision_ids=version.revision_ids, vector_hits=hits, subgraph=None,
                            load_chunks=lambda ids: [by_id[i] for i in ids if i in by_id],
                            threshold=DEMO_THRESHOLD, budget=ContextBudget(12000, 2000, 8))
    if not context.covered:
        return {"status": "not_covered", "reason": context.reason.value}
    generator = AnswerGenerator(_policy(tmp_path, DemoModelClient()), model=DEMO_MODEL_ID)
    generation = generator.generate(question, context, course_id=COURSE, request_id="r1",
                                    deadline=time.monotonic() + 30)
    assert isinstance(generation, AnswerGeneration)
    stream = CitationStream(version, "r1", (
        Evidence(c.index, c.chunk_id, c.document_id, COURSE, c.revision_id, c.text,
                 page=c.page, section_path=c.section_path) for c in context.chunks))
    for piece in generation:
        stream.feed(piece)
        if stream.stop_supplier:
            generation.close()
            break
    stream.finish()
    return stream.finalize(latency_ms=1)


@pytest.mark.parametrize("question, expected", [("什么是栈", "后进先出"), ("队列的特点", "先进先出")])
def test_covered_questions_are_answered_with_citations(tmp_path, question, expected):
    final = _ask(tmp_path, question)
    assert final["status"] == "answered", final
    assert final["citations"] and expected in final["answer"]
    assert all(c["chunk_id"] and c["text"] for c in final["citations"])


def test_unrelated_question_is_not_covered(tmp_path):
    final = _ask(tmp_path, "今天天气怎么样")
    assert final["status"] == "not_covered"
    assert final["reason"] == ContextReason.BELOW_SIMILARITY_THRESHOLD.value


def test_generation_without_overlap_emits_sentinel(tmp_path):
    client = DemoModelClient()
    prompt = ("<<课程资料>>\n<<资料 1>>（第1段）\n栈是一种线性表。\n<<课程资料结束>>\n\n"
              "<<学生问题>>\n红烧肉怎么做\n<<学生问题结束>>")
    request = ModelRequest(purpose="answer_with_context", model="m", messages=(Message("user", prompt),),
                           max_output_tokens=1024, response_format="text")
    assert client.complete(request).text == "<<INSUFFICIENT_EVIDENCE>>"
    events = list(client.stream(request))
    assert isinstance(events[-1], StreamDone)
    assert "".join(e.text for e in events if isinstance(e, StreamDelta)) == "<<INSUFFICIENT_EVIDENCE>>"


def test_rewrite_returns_question_unchanged(tmp_path):
    rewriter = QueryRewriter(_policy(tmp_path, DemoModelClient()), model=DEMO_MODEL_ID)
    result = rewriter.rewrite("它的特点是什么", [{"role": "user", "content": "什么是栈"},
                                                {"role": "assistant", "content": "栈是线性表[1]。"}],
                              course_id=COURSE, request_id="r1", deadline=time.monotonic() + 30)
    assert result.query == "它的特点是什么"
    assert result.model_called and result.reason is RewriteReason.UNCHANGED


def test_judge_and_summary_outputs_are_well_formed():
    client = DemoModelClient()
    sources = json.dumps([{"quote": "栈是线性表", "source_id": "s1"}], ensure_ascii=False)
    prompt = (f"知识点 A：栈\n定义 A：栈是线性表\n来源 A：{sources}\n\n"
              f"知识点 B：栈\n定义 B：线性表\n来源 B：{sources.replace('s1', 's2')}\n")
    judged = client.complete(ModelRequest(purpose="judge_duplicate", model="m", messages=(Message("user", prompt),),
                                          max_output_tokens=512, response_format="json")).json()
    assert judged["same"] is True and judged["reason"] and set(judged["source_ids"]) == {"s1", "s2"}
