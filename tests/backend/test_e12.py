"""E12：抽取阶段编排与块检查点（specs/task-processing.md §4、§5、§6、§8.2～§8.4；ADR-011；
E04/E05/E06/E11 交接的调用约定）。

已领取、处于 ``extracting`` 的任务：逐块实体抽取（E05，可选 E06 补漏），每块结束写块检查点；
全部块结束后按小节抽关系（E11），每个小节写一个检查点；最后带令牌条件 T4 ``extracting → merging``。
覆盖 E12 验收：每块失败可局部重试、并发上限、取消边界、重跑不重复计费/不污染来源；以及 TASK-4、
TASK-9、TASK-10、TASK-13、LEASE-2、LEASE-6、LEASE-11。
"""

from __future__ import annotations

import hashlib
import json
import re
import secrets
import shutil
import sqlite3
import threading
import time
from pathlib import Path

import pytest

from app.config import load_settings
from app.repositories import task_leases, tasks
from app.repositories.model_calls import SqliteCallStore
from app.repositories.sqlite import MIGRATIONS_DIR, connect, migrate
from app.services.ai.client import ModelRequest, ModelServerError
from app.services.ai.entities import EntityExtractor
from app.services.ai.fake import BAD_JSON_TEXT, FakeModelClient
from app.services.ai.gleaning import EntityGleaner
from app.services.ai.policy import ModelCallPolicy
from app.services.ai.relations import RelationExtractor
from app.services.file_storage import FileStorage, StoredFile
from app.workers import extract_task
from app.workers.extract_task import (
    ExtractionToolkit,
    ExtractLimits,
    ExtractStatus,
    load_candidates,
    run_extract_stage,
    task_entity_id,
)
from app.workers.parse_task import ParseStatus, run_parse_stage

COURSE = "course-a"
OTHER = "course-b"
MODEL = "extract-model"
LEASE_SECONDS = 60
MAX_ATTEMPTS = 3
SECRET_TEXT = "绝密原文-不得进入错误信息"

_SENTENCE = re.compile(r"(概念(\d{2}))是第\d章的第\d个知识点。")
_PREREQ = re.compile(r"学习(概念\d{2})之前需要先掌握(概念\d{2})。")
_CHUNK_HEAD = re.compile(r"\[(rev_[0-9a-f]{64}-\d+)\]")


class _Crash(BaseException):
    """模拟进程被杀：不被 ``except Exception`` 捕获。"""


def _material_text(chapters: int = 2, paragraphs: int = 5) -> bytes:
    lines: list[str] = []
    for c in range(1, chapters + 1):
        lines.append(f"第{c}章 主题{c}")
        for p in range(1, paragraphs + 1):
            lines.append(f"概念{c}{p}是第{c}章的第{p}个知识点。学习概念{c}{p}之前需要先掌握概念{c}{max(p - 1, 1)}。")
            lines.append("")
    return "\n".join(lines).encode("utf-8")


# --- 模型替身 ------------------------------------------------------------------------------------


def _entities_reply(prompt: str) -> str:
    items = []
    for sentence, name in ((m.group(0), m.group(1)) for m in _SENTENCE.finditer(prompt)):
        items.append({"name": name, "type": "concept", "definition": f"{name}的定义", "evidence": sentence,
                      "confidence": 0.9})
    for sentence, later, earlier in ((m.group(0), m.group(1), m.group(2)) for m in _PREREQ.finditer(prompt)):
        if later != earlier:
            items.append({"name": earlier, "type": "concept", "definition": f"{earlier}的定义",
                          "evidence": sentence, "confidence": 0.5})
    return json.dumps({"entities": items}, ensure_ascii=False)


def _relations_reply(prompt: str) -> str:
    ids = {}
    for line in prompt.splitlines():
        line = line.strip().rstrip(",")
        if line.startswith('{"id"'):
            row = json.loads(line)
            ids[row["name"]] = row["id"]
    items = []
    for match in _PREREQ.finditer(prompt):
        later, earlier = match.group(1), match.group(2)
        if later != earlier and later in ids and earlier in ids:
            items.append({"from_id": ids[earlier], "to_id": ids[later], "type": "PREREQUISITE",
                          "evidence": match.group(0), "confidence": 0.8})
    return json.dumps({"relations": items}, ensure_ascii=False)


class Script:
    """按块/小节内容决定应答；``hooks`` 可以对某个块或小节的第 N 次调用返回特定步骤或执行副作用。"""

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.active = 0
        self.peak = 0
        self.delay = 0.0
        self.calls: list[tuple[str, str]] = []  # (purpose, key)
        self.hooks: dict[str, object] = {}  # key -> callable(n) -> step | None

    @staticmethod
    def key_of(request: ModelRequest) -> str:
        prompt = request.messages[0].content
        if "实体表" in prompt:
            heads = _CHUNK_HEAD.findall(prompt)
            return "sec:" + (heads[0] if heads else "")
        found = _SENTENCE.search(prompt)
        return "chunk:" + (found.group(2) if found else "?")

    def __call__(self, request: ModelRequest):
        key = self.key_of(request)
        with self.lock:
            self.active += 1
            self.peak = max(self.peak, self.active)
            self.calls.append((request.purpose, key))
            n = sum(1 for _, k in self.calls if k == key)
        try:
            if self.delay:
                time.sleep(self.delay)
            hook = self.hooks.get(key)
            if hook is not None:
                step = hook(n)  # type: ignore[operator]
                if step is not None:
                    return step
            prompt = request.messages[0].content
            if key.startswith("sec:"):
                return _relations_reply(prompt)
            if "已抽取知识点" in prompt:
                return json.dumps({"entities": []})
            return _entities_reply(prompt)
        finally:
            with self.lock:
                self.active -= 1

    def count(self, key: str) -> int:
        return sum(1 for _, k in self.calls if k == key)


# --- 数据准备 ------------------------------------------------------------------------------------


def _url(path: Path) -> str:
    return f"sqlite:///{path.as_posix()}"


@pytest.fixture
def db_url(tmp_path: Path) -> str:
    url = _url(tmp_path / "state.sqlite3")
    migrate(url)
    return url


@pytest.fixture
def storage(tmp_path: Path) -> FileStorage:
    return FileStorage(tmp_path / "files", 10 * 1024 * 1024)


def _sql(url: str, statement: str, *params: object) -> list[tuple]:
    with connect(url) as database:
        return database.execute(statement, params).fetchall()


def _add_material(db_url: str, storage: FileStorage, data: bytes, *, course: str = COURSE) -> str:
    storage_name = secrets.token_hex(16) + ".txt"
    path = storage.path_for(storage_name)
    path.write_bytes(data)
    stored = StoredFile(
        storage_name=storage_name,
        path=path,
        original_filename="notes.txt",
        format="txt",  # type: ignore[arg-type]
        size_bytes=len(data),
        content_hash="sha256:" + hashlib.sha256(data).hexdigest(),
    )
    result = tasks.create_material_task(
        db_url, course_id=course, stored_file=stored, idempotency_key=secrets.token_hex(8)
    )
    return result.task.id


def _claim(db_url: str, owner: str = "worker-a") -> task_leases.Lease:
    lease = task_leases.claim_next(db_url, owner=owner, lease_seconds=LEASE_SECONDS, max_attempts=MAX_ATTEMPTS)
    assert lease is not None
    return lease


def _extracting(db_url: str, storage: FileStorage, data: bytes | None = None, *, course: str = COURSE):
    """上传 → 领取 → D11 解析到 ``extracting``（每段一块，便于数块），返回仍持有的租约。"""
    task_id = _add_material(db_url, storage, data if data is not None else _material_text(), course=course)
    lease = _claim(db_url)
    assert lease.task_id == task_id
    parsed = run_parse_stage(db_url, lease, storage=storage, max_attempts=MAX_ATTEMPTS,
                             target_chars=60, overlap_chars=0)
    assert parsed.status is ParseStatus.ADVANCED
    return task_leases.Lease(**{**lease.__dict__, "stage": "extracting", "progress": 0.10}), parsed.chunk_ids


def _policy(db_url: str, client: FakeModelClient, **overrides: object) -> ModelCallPolicy:
    kwargs: dict[str, object] = dict(
        max_retries=0, failure_threshold=1000, open_seconds=30, task_token_budget=10**9,
        daily_token_budget=10**9, sleep=lambda _s: None,
    )
    kwargs.update(overrides)
    return ModelCallPolicy(primary=client, store=SqliteCallStore(db_url), **kwargs)  # type: ignore[arg-type]


def _toolkit(db_url: str, script: Script, *, gleaning: bool = False, **policy: object) -> ExtractionToolkit:
    client = FakeModelClient(responder=script)
    return ExtractionToolkit(
        policy=_policy(db_url, client, **policy),
        entities=lambda c: EntityExtractor(c, model=MODEL, max_output_tokens=4000),
        relations=lambda c: RelationExtractor(c, model=MODEL, max_output_tokens=4000),
        gleaner=(lambda c: EntityGleaner(c, model=MODEL, max_output_tokens=4000, enabled=True)) if gleaning else None,
    )


def _limits(**kwargs: object) -> ExtractLimits:
    base: dict[str, object] = dict(max_attempts=MAX_ATTEMPTS, chunk_max_attempts=2, max_failed_ratio=0.2,
                                   max_concurrency=1)
    base.update(kwargs)
    return ExtractLimits(**base)  # type: ignore[arg-type]


def _run(db_url, lease, toolkit, **limits):
    return run_extract_stage(db_url, lease, toolkit=toolkit, limits=_limits(**limits))


def _row(db_url: str, task_id: str) -> dict[str, object]:
    (row,) = _sql(
        db_url,
        """SELECT stage, progress, cancel_requested, error_code, error_message, error_details,
                  lease_token, attempt, not_before FROM processing_tasks WHERE id = ?""",
        task_id,
    )
    keys = "stage progress cancel_requested error_code error_message error_details lease_token attempt not_before"
    return dict(zip(keys.split(), row))


def _checkpoints(db_url: str, task_id: str, kind: str = "chunk") -> dict[str, tuple]:
    rows = _sql(
        db_url,
        "SELECT unit_id, status, attempts, error_code FROM task_chunk_checkpoints WHERE task_id = ? AND unit_kind = ?",
        task_id, kind,
    )
    return {row[0]: row[1:] for row in rows}


def _call_rows(db_url: str, task_id: str) -> list[tuple]:
    return _sql(db_url, "SELECT chunk_id, purpose, is_repair, chunk_attempt FROM model_calls WHERE task_id = ?", task_id)


def _key(chunk_ids: tuple[str, ...], index: int) -> str:
    """第 index 块（从 0 起）在替身里的键：每章 5 段，块文本以「概念<章><段>」开头。"""
    return f"chunk:{index // 5 + 1}{index % 5 + 1}"


# --- 成功路径 ------------------------------------------------------------------------------------


def test_all_chunks_and_sections_checkpointed_then_t4_to_merging(db_url, storage):
    lease, chunk_ids = _extracting(db_url, storage)
    assert len(chunk_ids) == 10
    script = Script()

    outcome = _run(db_url, lease, _toolkit(db_url, script))

    assert outcome.status is ExtractStatus.ADVANCED
    assert outcome.stage == "merging" and outcome.sse_event == "stage"
    assert (outcome.chunks_total, outcome.chunks_done, outcome.chunks_failed) == (10, 10, 0)
    assert (outcome.sections_total, outcome.sections_failed) == (2, 0)
    row = _row(db_url, lease.task_id)
    assert row["stage"] == "merging" and row["progress"] == pytest.approx(0.60)
    assert row["lease_token"] == lease.token  # 仍持有租约，交给下一阶段
    checkpoints = _checkpoints(db_url, lease.task_id)
    assert set(checkpoints) == set(chunk_ids)
    assert all(value == ("done", 1, None) for value in checkpoints.values())
    assert len(_checkpoints(db_url, lease.task_id, "section")) == 2
    # 每块一次实体调用 + 每小节一次关系调用
    assert len(_call_rows(db_url, lease.task_id)) == 12


def test_candidates_carry_sources_and_task_entity_ids(db_url, storage):
    lease, chunk_ids = _extracting(db_url, storage)
    _run(db_url, lease, _toolkit(db_url, Script()))

    result = load_candidates(db_url, course_id=COURSE, task_id=lease.task_id)

    names = {entity.name for entity in result.entities}
    assert {f"概念{c}{p}" for c in (1, 2) for p in range(1, 6)} <= names
    for entity in result.entities:
        assert entity.entity_id == task_entity_id(lease.task_id, entity.name)
        assert entity.candidates
        for candidate in entity.candidates:
            assert candidate.source.course_id == COURSE
            assert candidate.source.chunk_id in chunk_ids
            assert candidate.source.sources
    ids = {entity.entity_id for entity in result.entities}
    assert result.relations, "应得到先修关系"
    for relation in result.relations:
        assert relation.type == "PREREQUISITE"
        assert relation.from_id in ids and relation.to_id in ids and relation.from_id != relation.to_id
        assert relation.source.chunk_id in chunk_ids
    assert result.failed_chunks == () and result.failed_sections == ()


def test_task_entity_id_is_deterministic_by_normalized_name():
    assert task_entity_id("t1", "概念11") == task_entity_id("t1", " 概念 11 ")
    assert task_entity_id("t1", "Stack") == task_entity_id("t1", "ｓｔａｃｋ")
    assert task_entity_id("t1", "概念11") != task_entity_id("t2", "概念11")
    assert task_entity_id("t1", "概念11") != task_entity_id("t1", "概念12")


def test_same_name_across_chunks_becomes_one_entity_with_all_sources(db_url, storage):
    lease, _ = _extracting(db_url, storage)
    _run(db_url, lease, _toolkit(db_url, Script()))

    result = load_candidates(db_url, course_id=COURSE, task_id=lease.task_id)

    by_name = {entity.name: entity for entity in result.entities}
    # 概念11 在第 1 段自述，又在第 2 段作为先修出现
    assert len({c.source.chunk_id for c in by_name["概念11"].candidates}) == 2
    assert len(result.entities) == len(by_name)


# --- 并发上限 ------------------------------------------------------------------------------------


@pytest.mark.parametrize("limit", [1, 3])
def test_concurrent_model_calls_never_exceed_the_limit(db_url, storage, limit):
    lease, _ = _extracting(db_url, storage)
    script = Script()
    script.delay = 0.03

    outcome = _run(db_url, lease, _toolkit(db_url, script), max_concurrency=limit)

    assert outcome.status is ExtractStatus.ADVANCED
    assert script.peak == limit


def test_limits_reject_invalid_values():
    with pytest.raises(ValueError):
        _limits(max_concurrency=0)
    with pytest.raises(ValueError):
        _limits(chunk_max_attempts=0)
    with pytest.raises(ValueError):
        _limits(max_failed_ratio=1.0)
    with pytest.raises(ValueError):
        _limits(max_failed_ratio=-0.1)


def test_limits_from_settings():
    settings = load_settings({"LLM_MAX_CONCURRENCY": "6", "TASK_CHUNK_MAX_ATTEMPTS": "3",
                              "TASK_MAX_FAILED_CHUNK_RATIO": "0.1", "TASK_MAX_ATTEMPTS": "4"})
    limits = ExtractLimits.from_settings(settings)
    assert (limits.max_concurrency, limits.chunk_max_attempts, limits.max_failed_ratio, limits.max_attempts) == (
        6, 3, 0.1, 4)


# --- 块级局部重试（L2）与部分失败 --------------------------------------------------------------------


def test_bad_output_retries_only_that_chunk(db_url, storage):
    lease, chunk_ids = _extracting(db_url, storage)
    script = Script()
    script.hooks[_key(chunk_ids, 3)] = lambda n: BAD_JSON_TEXT if n <= 2 else None  # 首次尝试：原调用+修复都坏

    outcome = _run(db_url, lease, _toolkit(db_url, script))

    assert outcome.status is ExtractStatus.ADVANCED and outcome.chunks_failed == 0
    checkpoints = _checkpoints(db_url, lease.task_id)
    assert checkpoints[chunk_ids[3]] == ("done", 2, None)
    assert all(v == ("done", 1, None) for k, v in checkpoints.items() if k != chunk_ids[3])
    calls = [row for row in _call_rows(db_url, lease.task_id) if row[0] == chunk_ids[3]]
    assert sorted((row[1], row[2], row[3]) for row in calls) == [
        ("extract_entities", 0, 1), ("extract_entities", 0, 2), ("repair", 1, 1)]


def test_chunk_failed_after_attempts_is_recorded_and_within_threshold_continues(db_url, storage):
    """TASK-9 / LEASE-11：10 块失败 2 块、阈值 0.2 → 继续；失败块带定位与错误码，不再重试。"""
    lease, chunk_ids = _extracting(db_url, storage)
    script = Script()
    for index in (2, 7):
        script.hooks[_key(chunk_ids, index)] = lambda n: BAD_JSON_TEXT

    outcome = _run(db_url, lease, _toolkit(db_url, script))

    assert outcome.status is ExtractStatus.ADVANCED
    assert (outcome.chunks_done, outcome.chunks_failed) == (10, 2)
    checkpoints = _checkpoints(db_url, lease.task_id)
    for index in (2, 7):
        assert checkpoints[chunk_ids[index]] == ("failed", 2, "EXTRACTION_INCOMPLETE")
        assert script.count(_key(chunk_ids, index)) == 4  # 2 次尝试 × （原调用 + 修复）
    failed = load_candidates(db_url, course_id=COURSE, task_id=lease.task_id).failed_chunks
    assert [f.chunk_id for f in failed] == [chunk_ids[2], chunk_ids[7]]
    assert all(f.code == "EXTRACTION_INCOMPLETE" and f.section_path for f in failed)
    assert failed[0].section_path.startswith("第1章 主题1")


def test_ratio_exactly_at_threshold_continues_and_zero_threshold_is_strict(db_url, storage):
    lease, chunk_ids = _extracting(db_url, storage)
    script = Script()
    script.hooks[_key(chunk_ids, 0)] = lambda n: BAD_JSON_TEXT

    outcome = _run(db_url, lease, _toolkit(db_url, script), max_failed_ratio=0.1)
    assert outcome.status is ExtractStatus.ADVANCED  # 1/10 = 0.1，含等号

    lease2, _ = _extracting(db_url, storage)
    script2 = Script()
    script2.hooks["chunk:11"] = lambda n: BAD_JSON_TEXT
    outcome2 = _run(db_url, lease2, _toolkit(db_url, script2), max_failed_ratio=0.0)
    assert outcome2.status is ExtractStatus.FAILED and outcome2.error_code == "EXTRACTION_INCOMPLETE"


def test_ratio_uses_exact_decimal_comparison():
    """29/100 与阈值 0.29 相等应继续（避免二进制浮点把 0.29 表示得略小）。"""
    assert extract_task.exceeds_threshold(29, 100, 0.29) is False
    assert extract_task.exceeds_threshold(30, 100, 0.29) is True
    assert extract_task.exceeds_threshold(2, 10, 0.2) is False
    assert extract_task.exceeds_threshold(1, 10, 0.0) is True


def test_over_threshold_fails_extraction_incomplete_with_counts(db_url, storage):
    """TASK-13：10 块失败 3 块（混合原因）→ EXTRACTION_INCOMPLETE，details 含计数与阈值。"""
    lease, chunk_ids = _extracting(db_url, storage)
    script = Script()
    script.hooks[_key(chunk_ids, 1)] = lambda n: BAD_JSON_TEXT
    script.hooks[_key(chunk_ids, 4)] = lambda n: ModelServerError(MODEL)
    script.hooks[_key(chunk_ids, 8)] = lambda n: ModelServerError(MODEL)

    outcome = _run(db_url, lease, _toolkit(db_url, script))

    assert outcome.status is ExtractStatus.FAILED and outcome.sse_event == "error"
    row = _row(db_url, lease.task_id)
    assert row["stage"] == "failed" and row["error_code"] == "EXTRACTION_INCOMPLETE"
    assert row["lease_token"] is None
    details = json.loads(row["error_details"])
    assert details["chunks_failed"] == 3 and details["chunks_total"] == 10 and details["threshold"] == 0.2
    assert details["by_code"] == {"EXTRACTION_INCOMPLETE": 1, "LLM_UNAVAILABLE": 2}
    assert _checkpoints(db_url, lease.task_id, "section") == {}  # 失败后不再抽关系


def test_over_threshold_all_model_errors_fails_llm_unavailable(db_url, storage):
    lease, chunk_ids = _extracting(db_url, storage)
    script = Script()
    for index in (1, 4, 8):
        script.hooks[_key(chunk_ids, index)] = lambda n: ModelServerError(MODEL)

    outcome = _run(db_url, lease, _toolkit(db_url, script))

    assert outcome.status is ExtractStatus.FAILED and outcome.error_code == "LLM_UNAVAILABLE"
    details = json.loads(_row(db_url, lease.task_id)["error_details"])
    assert (details["chunks_failed"], details["chunks_total"], details["threshold"]) == (3, 10, 0.2)


def test_early_decision_stops_calling_the_model(db_url, storage):
    """失败块数一超过 floor(阈值 × 总数) 就判定，不再为剩余块花钱；结论与跑完全部块相同。"""
    lease, chunk_ids = _extracting(db_url, storage)
    script = Script()
    script.hooks[_key(chunk_ids, 0)] = lambda n: BAD_JSON_TEXT

    outcome = _run(db_url, lease, _toolkit(db_url, script), max_failed_ratio=0.0)

    assert outcome.status is ExtractStatus.FAILED and outcome.error_code == "EXTRACTION_INCOMPLETE"
    assert {key for _, key in script.calls} == {_key(chunk_ids, 0)}


def test_budget_exceeded_fails_the_chunk_without_retry(db_url, storage):
    lease, chunk_ids = _extracting(db_url, storage)
    script = Script()

    outcome = _run(db_url, lease, _toolkit(db_url, script, task_token_budget=1))

    assert outcome.status is ExtractStatus.FAILED and outcome.error_code == "EXTRACTION_INCOMPLETE"
    checkpoints = _checkpoints(db_url, lease.task_id)
    assert checkpoints[chunk_ids[0]] == ("done", 1, None)
    failed = [v for v in checkpoints.values() if v[0] == "failed"]
    assert failed and all(v == ("failed", 1, "BUDGET_EXCEEDED") for v in failed)
    assert json.loads(_row(db_url, lease.task_id)["error_details"])["by_code"] == {"BUDGET_EXCEEDED": 3}


# --- 取消边界 ------------------------------------------------------------------------------------


def test_cancel_before_start_goes_straight_to_cancelled(db_url, storage):
    lease, _ = _extracting(db_url, storage)
    _sql(db_url, "UPDATE processing_tasks SET cancel_requested = 1 WHERE id = ?", lease.task_id)
    script = Script()

    outcome = _run(db_url, lease, _toolkit(db_url, script))

    assert outcome.status is ExtractStatus.CANCELLED and outcome.sse_event == "cancelled"
    assert script.calls == []
    row = _row(db_url, lease.task_id)
    assert row["stage"] == "cancelled" and row["lease_token"] is None


def test_cancel_takes_effect_at_the_next_chunk_boundary(db_url, storage):
    """TASK-4：在途调用完成后其结果不写检查点；之后不再调用模型，任务转 cancelled。"""
    lease, chunk_ids = _extracting(db_url, storage)
    script = Script()

    def cancel_during_call(n):
        _sql(db_url, "UPDATE processing_tasks SET cancel_requested = 1 WHERE id = ?", lease.task_id)
        return None

    script.hooks[_key(chunk_ids, 2)] = cancel_during_call

    outcome = _run(db_url, lease, _toolkit(db_url, script))

    assert outcome.status is ExtractStatus.CANCELLED
    assert set(_checkpoints(db_url, lease.task_id)) == {chunk_ids[0], chunk_ids[1]}
    assert {key for _, key in script.calls} == {_key(chunk_ids, i) for i in range(3)}
    row = _row(db_url, lease.task_id)
    assert row["stage"] == "cancelled" and row["lease_token"] is None and row["error_code"] is None


def test_cancel_during_relation_phase_is_honoured(db_url, storage):
    lease, chunk_ids = _extracting(db_url, storage)
    script = Script()
    first_section = "sec:" + chunk_ids[0]

    def cancel_during_call(n):
        _sql(db_url, "UPDATE processing_tasks SET cancel_requested = 1 WHERE id = ?", lease.task_id)
        return None

    script.hooks[first_section] = cancel_during_call

    outcome = _run(db_url, lease, _toolkit(db_url, script))

    assert outcome.status is ExtractStatus.CANCELLED
    assert _checkpoints(db_url, lease.task_id, "section") == {}
    assert _row(db_url, lease.task_id)["stage"] == "cancelled"


# --- 重跑：不重复计费、不污染来源 -------------------------------------------------------------------


def test_takeover_resumes_from_checkpoints_without_recalling_done_chunks(db_url, storage):
    """LEASE-2：已完成 6 块时崩溃；接管后只对剩余 4 块调用模型，前 6 块在 model_calls 中无新增。"""
    lease, chunk_ids = _extracting(db_url, storage)
    script = Script()

    def crash(n):
        raise _Crash()

    script.hooks[_key(chunk_ids, 6)] = crash
    with pytest.raises(_Crash):
        _run(db_url, lease, _toolkit(db_url, script))
    assert len(_checkpoints(db_url, lease.task_id)) == 6
    before = {cid: sum(1 for r in _call_rows(db_url, lease.task_id) if r[0] == cid) for cid in chunk_ids}
    progress_before = _row(db_url, lease.task_id)["progress"]
    assert progress_before > 0.10

    _sql(db_url, "UPDATE processing_tasks SET lease_expires_at = unixepoch() - 1 WHERE id = ?", lease.task_id)
    takeover = task_leases.claim_next(db_url, owner="worker-b", lease_seconds=LEASE_SECONDS,
                                      max_attempts=MAX_ATTEMPTS)
    assert takeover is not None and takeover.task_id == lease.task_id and takeover.attempt == 2
    script2 = Script()
    outcome = _run(db_url, takeover, _toolkit(db_url, script2))

    assert outcome.status is ExtractStatus.ADVANCED and outcome.chunks_done == 10
    assert {k for _, k in script2.calls if k.startswith("chunk:")} == {_key(chunk_ids, i) for i in range(6, 10)}
    after = {cid: sum(1 for r in _call_rows(db_url, lease.task_id) if r[0] == cid) for cid in chunk_ids}
    for cid in chunk_ids[:6]:
        assert after[cid] == before[cid]
    assert _row(db_url, lease.task_id)["progress"] >= progress_before
    # 来源不重复：每个 (实体, 块, 证据区间) 只出现一次
    result = load_candidates(db_url, course_id=COURSE, task_id=lease.task_id)
    seen = [(e.entity_id, c.source.chunk_id, c.source.evidence_start)
            for e in result.entities for c in e.candidates]
    assert len(seen) == len(set(seen))


def test_takeover_after_chunks_skips_finished_sections(db_url, storage):
    lease, chunk_ids = _extracting(db_url, storage)
    script = Script()
    second_section = "sec:" + chunk_ids[5]

    def crash(n):
        raise _Crash()

    script.hooks[second_section] = crash
    with pytest.raises(_Crash):
        _run(db_url, lease, _toolkit(db_url, script))
    assert len(_checkpoints(db_url, lease.task_id, "section")) == 1

    _sql(db_url, "UPDATE processing_tasks SET lease_expires_at = unixepoch() - 1 WHERE id = ?", lease.task_id)
    takeover = _claim(db_url, "worker-b")
    script2 = Script()
    outcome = _run(db_url, takeover, _toolkit(db_url, script2))

    assert outcome.status is ExtractStatus.ADVANCED
    assert [k for _, k in script2.calls] == [second_section]


def test_checkpoint_rows_are_immutable_and_course_scoped(db_url, storage):
    lease, chunk_ids = _extracting(db_url, storage)
    _run(db_url, lease, _toolkit(db_url, Script()))
    with pytest.raises(sqlite3.DatabaseError):
        _sql(db_url, "UPDATE task_chunk_checkpoints SET status = 'failed', error_code = 'X', result = NULL")
    with pytest.raises(sqlite3.DatabaseError):
        _sql(
            db_url,
            """INSERT INTO task_chunk_checkpoints (task_id, course_id, unit_kind, unit_id, status, attempts, result)
               VALUES (?, ?, 'chunk', 'x', 'done', 1, '{}')""",
            lease.task_id, OTHER,
        )
    assert load_candidates(db_url, course_id=OTHER, task_id=lease.task_id).entities == ()


def _checkpoint_migration() -> Path:
    # D-10：合并前可能改号，按文件名后缀定位，不写死版本号。
    (path,) = MIGRATIONS_DIR.glob("*_extraction_checkpoints.sql")
    return path


def _copy_migrations(target: Path, *, include_own: bool) -> Path:
    last = _checkpoint_migration().name[:3]
    target.mkdir(parents=True, exist_ok=True)
    for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
        version = path.name[:3]
        if version < last or (include_own and version == last):
            shutil.copyfile(path, target / path.name)
    return target


def _schema(url: str) -> list[tuple]:
    return _sql(url, "SELECT type, name, tbl_name, sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%' "
                     "ORDER BY type, name")


def test_documented_rollback_restores_previous_schema_and_the_migration_can_be_reapplied(tmp_path):
    url = _url(tmp_path / "rollback.sqlite3")
    migrate(url, _copy_migrations(tmp_path / "before", include_own=False))
    previous = _schema(url)
    migrate(url, _copy_migrations(tmp_path / "all", include_own=True))

    prefix = "-- ROLLBACK: "
    steps = [line[len(prefix):] for line in _checkpoint_migration().read_text(encoding="utf-8").splitlines()
             if line.startswith(prefix)]
    assert steps
    with connect(url) as database:
        database.execute("BEGIN IMMEDIATE")
        for step in steps:
            database.execute(step)
        database.execute("COMMIT")

    assert _schema(url) == previous
    assert migrate(url, tmp_path / "all") == [_checkpoint_migration().name[:3]]


def test_deleting_the_task_removes_its_checkpoints(db_url, storage):
    """ADR-021 删除资料会删除任务行；检查点随任务删除，不阻塞删除。"""
    lease, _ = _extracting(db_url, storage)
    _run(db_url, lease, _toolkit(db_url, Script()))
    with connect(db_url) as database:
        database.execute("DELETE FROM task_revisions WHERE task_id = ?", (lease.task_id,))
        database.execute("DELETE FROM processing_tasks WHERE id = ?", (lease.task_id,))
    assert _sql(db_url, "SELECT count(*) FROM task_chunk_checkpoints")[0][0] == 0


# --- 阶段级临时故障、租约与未预期错误 --------------------------------------------------------------


def test_open_breaker_releases_without_recording_a_failed_chunk(db_url, storage):
    """LEASE-6：熔断打开 → 当前块不记失败块，任务主动释放并退避 30 秒。"""
    lease, chunk_ids = _extracting(db_url, storage)
    script = Script()
    script.hooks[_key(chunk_ids, 3)] = lambda n: ModelServerError(MODEL)

    outcome = _run(db_url, lease, _toolkit(db_url, script, failure_threshold=1, max_retries=1))

    assert outcome.status is ExtractStatus.RELEASED and outcome.sse_event is None
    row = _row(db_url, lease.task_id)
    assert row["stage"] == "extracting" and row["lease_token"] is None and row["error_code"] is None
    now = _sql(db_url, "SELECT unixepoch()")[0][0]
    assert now + 25 <= row["not_before"] <= now + 31
    checkpoints = _checkpoints(db_url, lease.task_id)
    assert set(checkpoints) == set(chunk_ids[:3])
    assert all(v[0] == "done" for v in checkpoints.values())


def test_open_breaker_on_last_attempt_fails_llm_unavailable(db_url, storage):
    lease, chunk_ids = _extracting(db_url, storage)
    _sql(db_url, "UPDATE processing_tasks SET attempt = ? WHERE id = ?", MAX_ATTEMPTS, lease.task_id)
    script = Script()
    script.hooks[_key(chunk_ids, 0)] = lambda n: ModelServerError(MODEL)

    outcome = _run(db_url, lease, _toolkit(db_url, script, failure_threshold=1, max_retries=1))

    assert outcome.status is ExtractStatus.FAILED and outcome.error_code == "LLM_UNAVAILABLE"
    details = json.loads(_row(db_url, lease.task_id)["error_details"])
    assert details == {"attempts": MAX_ATTEMPTS, "stage": "extracting"}


class _BrokenStore(SqliteCallStore):
    def prewrite(self, record, *, task_budget, daily_budget):  # noqa: ANN001
        raise sqlite3.OperationalError("database is locked")


def test_call_record_failure_is_storage_unavailable_release(db_url, storage):
    lease, _ = _extracting(db_url, storage)
    toolkit = _toolkit(db_url, Script())
    broken = ExtractionToolkit(
        policy=ModelCallPolicy(primary=FakeModelClient(responder=Script()), store=_BrokenStore(db_url),
                               max_retries=0, failure_threshold=1000, open_seconds=30,
                               task_token_budget=10**9, daily_token_budget=10**9),
        entities=toolkit.entities, relations=toolkit.relations,
    )

    outcome = _run(db_url, lease, broken)

    assert outcome.status is ExtractStatus.RELEASED
    assert _checkpoints(db_url, lease.task_id) == {}
    assert _row(db_url, lease.task_id)["stage"] == "extracting"


def test_lost_lease_stops_writing(db_url, storage):
    lease, chunk_ids = _extracting(db_url, storage)
    script = Script()

    def steal(n):
        _sql(db_url, "UPDATE processing_tasks SET lease_token = ? WHERE id = ?", "f" * 32, lease.task_id)
        return None

    script.hooks[_key(chunk_ids, 1)] = steal

    outcome = _run(db_url, lease, _toolkit(db_url, script))

    assert outcome.status is ExtractStatus.LOST
    assert set(_checkpoints(db_url, lease.task_id)) == {chunk_ids[0]}
    assert _row(db_url, lease.task_id)["stage"] == "extracting"


def test_stale_lease_writes_nothing(db_url, storage):
    lease, _ = _extracting(db_url, storage)
    stale = task_leases.Lease(**{**lease.__dict__, "token": "e" * 32})
    script = Script()

    outcome = _run(db_url, stale, _toolkit(db_url, script))

    assert outcome.status is ExtractStatus.LOST and script.calls == []


def test_unexpected_error_fails_internal_without_leaking_text(db_url, storage, caplog):
    lease, chunk_ids = _extracting(db_url, storage)
    script = Script()

    def boom(n):
        raise RuntimeError(SECRET_TEXT)

    script.hooks[_key(chunk_ids, 0)] = boom

    outcome = _run(db_url, lease, _toolkit(db_url, script))

    assert outcome.status is ExtractStatus.FAILED and outcome.error_code == "INTERNAL_ERROR"
    row = _row(db_url, lease.task_id)
    assert row["error_details"] is None and SECRET_TEXT not in row["error_message"]
    assert SECRET_TEXT not in caplog.text


def test_wrong_stage_or_course_is_a_caller_error(db_url, storage):
    lease, _ = _extracting(db_url, storage)
    with pytest.raises(ValueError):
        _run(db_url, task_leases.Lease(**{**lease.__dict__, "course_id": OTHER}), _toolkit(db_url, Script()))
    _run(db_url, lease, _toolkit(db_url, Script()))  # → merging
    with pytest.raises(ValueError):
        _run(db_url, lease, _toolkit(db_url, Script()))


# --- 补漏与关系失败 ---------------------------------------------------------------------------------


def test_gleaning_adds_entities_and_its_bad_output_fails_the_attempt(db_url, storage):
    lease, chunk_ids = _extracting(db_url, storage)
    script = Script()
    target = _key(chunk_ids, 0)
    glean_calls = {"n": 0}
    original = script.__call__

    def responder(request):
        # 补漏的原调用与修复调用都带「已抽取知识点」列表
        if "已抽取知识点" in request.messages[0].content and Script.key_of(request) == target:
            glean_calls["n"] += 1
            with script.lock:
                script.calls.append((request.purpose, target))
            if glean_calls["n"] <= 2:
                return BAD_JSON_TEXT
            return json.dumps({"entities": [{"name": "补漏概念", "type": "concept", "definition": "补",
                                             "evidence": "概念11是第1章的第1个知识点。", "confidence": 0.6}]},
                              ensure_ascii=False)
        return original(request)

    client = FakeModelClient(responder=responder)
    toolkit = ExtractionToolkit(
        policy=_policy(db_url, client),
        entities=lambda c: EntityExtractor(c, model=MODEL, max_output_tokens=4000),
        relations=lambda c: RelationExtractor(c, model=MODEL, max_output_tokens=4000),
        gleaner=lambda c: EntityGleaner(c, model=MODEL, max_output_tokens=4000, enabled=True),
    )

    outcome = _run(db_url, lease, toolkit)

    assert outcome.status is ExtractStatus.ADVANCED
    assert _checkpoints(db_url, lease.task_id)[chunk_ids[0]] == ("done", 2, None)
    names = {e.name for e in load_candidates(db_url, course_id=COURSE, task_id=lease.task_id).entities}
    assert "补漏概念" in names


def test_relation_failure_is_recorded_but_not_counted_against_the_threshold(db_url, storage):
    """ArvinHan 2026-09-26：小节关系抽取失败不计入失败块阈值，只记在检查点里。"""
    lease, chunk_ids = _extracting(db_url, storage)
    script = Script()
    for head in (chunk_ids[0], chunk_ids[5]):
        script.hooks["sec:" + head] = lambda n: BAD_JSON_TEXT

    outcome = _run(db_url, lease, _toolkit(db_url, script), max_failed_ratio=0.0)

    assert outcome.status is ExtractStatus.ADVANCED
    assert (outcome.chunks_failed, outcome.sections_failed) == (0, 2)
    sections = _checkpoints(db_url, lease.task_id, "section")
    assert all(v == ("failed", 2, "EXTRACTION_INCOMPLETE") for v in sections.values())
    result = load_candidates(db_url, course_id=COURSE, task_id=lease.task_id)
    assert result.relations == () and len(result.failed_sections) == 2
    assert result.entities


def test_failed_chunk_entities_are_left_out_of_the_section_table(db_url, storage):
    lease, chunk_ids = _extracting(db_url, storage)
    script = Script()
    script.hooks[_key(chunk_ids, 4)] = lambda n: BAD_JSON_TEXT  # 第 1 章第 5 段

    _run(db_url, lease, _toolkit(db_url, script))

    names = {e.name for e in load_candidates(db_url, course_id=COURSE, task_id=lease.task_id).entities}
    assert "概念15" not in names


# --- 运行一次入口 --------------------------------------------------------------------------------


def _settings(db_url: str, storage: FileStorage):
    return load_settings({"SQLITE_URL": db_url, "STORAGE_DIR": str(storage.root), "TASK_LEASE_SECONDS": "15"})


def test_run_once_parses_extracts_and_hands_back_at_merging(db_url, storage):
    task_id = _add_material(db_url, storage, _material_text())

    result = extract_task.run_once(_settings(db_url, storage), toolkit=_toolkit(db_url, Script()),
                                   owner="worker-a", storage=storage)

    assert result.lease is not None and result.lease.task_id == task_id
    assert result.parse is not None and result.parse.status is ParseStatus.ADVANCED
    assert result.extract is not None and result.extract.status is ExtractStatus.ADVANCED
    assert result.handed_back is True
    row = _row(db_url, task_id)
    assert row["stage"] == "merging" and row["lease_token"] is None and row["attempt"] == 0


def test_run_once_picks_up_a_task_already_in_extracting(db_url, storage):
    lease, _ = _extracting(db_url, storage)
    task_leases.release_on_shutdown(db_url, lease.task_id, lease.token)

    result = extract_task.run_once(_settings(db_url, storage), toolkit=_toolkit(db_url, Script()),
                                   owner="worker-b", storage=storage)

    assert result.parse is None and result.extract is not None
    assert result.extract.status is ExtractStatus.ADVANCED
    assert _row(db_url, lease.task_id)["stage"] == "merging"


def test_run_once_hands_back_merging_tasks(db_url, storage):
    lease, _ = _extracting(db_url, storage)
    _run(db_url, lease, _toolkit(db_url, Script()))
    task_leases.release_on_shutdown(db_url, lease.task_id, lease.token)
    script = Script()

    result = extract_task.run_once(_settings(db_url, storage), toolkit=_toolkit(db_url, script),
                                   owner="worker-b", storage=storage)

    assert result.extract is None and result.handed_back is True and script.calls == []
