"""Internal extraction.types responsibilities; public compatibility entry: app.workers.extract_task."""

from __future__ import annotations

import logging
from collections import Counter
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from decimal import Decimal
from enum import StrEnum
from app.config import Settings
from app.repositories.chunks import StoredChunk
from app.repositories.task_leases import Lease, ReclaimResult
from app.services.ai.client import ModelClient
from app.services.ai.entities import EntityCandidate, EntityExtractor
from app.services.ai.gleaning import EntityGleaner
from app.services.ai.policy import ModelCallPolicy
from app.services.ai.relations import RelationCandidate, RelationExtractor
from app.workers.parse_task import ParseOutcome

logger = logging.getLogger("app.workers.extract_task")

STAGE = "extracting"
NEXT_STAGE = "merging"
#: 块阶段占本阶段进度区间的份额，其余留给小节关系。
CHUNK_PROGRESS_SHARE = 0.8

OUTPUT_INVALID_CODE = "EXTRACTION_INCOMPLETE"
MODEL_ERROR_CODE = "LLM_UNAVAILABLE"
BUDGET_CODE = "BUDGET_EXCEEDED"

_NOW_TEXT = "strftime('%Y-%m-%dT%H:%M:%fZ', 'now')"
_MESSAGES = {
    "EXTRACTION_INCOMPLETE": "抽取失败的块超过允许比例",
    "LLM_UNAVAILABLE": "模型服务不可用，抽取失败的块超过允许比例",
    "INTERNAL_ERROR": "抽取阶段发生未预期的错误",
}


# ---------------------------------------------------------------- 公开数据结构


class ExtractStatus(StrEnum):
    ADVANCED = "advanced"  # T4：到 merging，仍持有租约
    CANCELLED = "cancelled"  # T8
    FAILED = "failed"  # T9：EXTRACTION_INCOMPLETE / LLM_UNAVAILABLE / 耗尽码 / INTERNAL_ERROR
    RELEASED = "released"  # 阶段级临时故障：已主动释放并退避，stage 不变
    LOST = "lost"  # 令牌已失效：此后未做任何写入


@dataclass(frozen=True)
class ExtractOutcome:
    status: ExtractStatus
    task_id: str
    stage: str | None
    sse_event: str | None
    chunks_total: int = 0
    chunks_done: int = 0
    chunks_failed: int = 0
    sections_total: int = 0
    sections_failed: int = 0
    error_code: str | None = None
    not_before: int | None = None


def _is_int(value: object) -> bool:
    return type(value) is int


@dataclass(frozen=True)
class ExtractLimits:
    """§5、§8.3 的阈值与并发上限；``from_settings`` 取 A07 登记的环境变量。"""

    max_attempts: int
    chunk_max_attempts: int = 2
    max_failed_ratio: float = 0.2
    max_concurrency: int = 8

    def __post_init__(self) -> None:
        for name in ("max_attempts", "chunk_max_attempts", "max_concurrency"):
            value = getattr(self, name)
            if not _is_int(value) or value < 1:
                raise ValueError(f"{name} must be an int >= 1")
        ratio = self.max_failed_ratio
        if isinstance(ratio, bool) or not isinstance(ratio, (int, float)) or not 0 <= ratio < 1:
            raise ValueError("max_failed_ratio must be in [0, 1)")

    @classmethod
    def from_settings(cls, settings: Settings) -> ExtractLimits:
        return cls(
            max_attempts=settings.TASK_MAX_ATTEMPTS,
            chunk_max_attempts=settings.TASK_CHUNK_MAX_ATTEMPTS,
            max_failed_ratio=settings.TASK_MAX_FAILED_CHUNK_RATIO,
            max_concurrency=settings.LLM_MAX_CONCURRENCY,
        )


@dataclass(frozen=True)
class ExtractionToolkit:
    """每进程一份：共享熔断状态的 E04 策略，以及把一个已绑定客户端变成抽取服务的工厂。"""

    policy: ModelCallPolicy
    entities: Callable[[ModelClient], EntityExtractor]
    relations: Callable[[ModelClient], RelationExtractor]
    gleaner: Callable[[ModelClient], EntityGleaner] | None = None
    #: personal 模式：调用归属的用户与每次尝试前的快照有效性检查（失效时抛 CredentialUnavailable，ADR-080）。
    user_id: str | None = None
    guard: Callable[[], None] | None = None
    #: personal 模式下任务快照里的模型名；全局模式为 None（模型名已固化在抽取器工厂里）。
    model: str | None = None


@dataclass(frozen=True)
class TaskEntity:
    """任务内去重后的实体：同一规范化名称的全部候选（各自带出处）。名称与类型取首次出现者。"""

    entity_id: str
    name: str = field(repr=False)
    type: str
    candidates: tuple[EntityCandidate, ...] = field(repr=False)


@dataclass(frozen=True)
class FailedChunk:
    """契约 ``FailedChunk`` 的来源：块 ID、最终错误码与原文定位。"""

    chunk_id: str
    code: str
    page: int | None
    section_path: str | None


@dataclass(frozen=True)
class FailedSection:
    section_id: str
    code: str
    section_path: str | None
    chunk_ids: tuple[str, ...]


@dataclass(frozen=True)
class ExtractionCandidates:
    """待持久化候选（交 ``merging``/F04/F13）。按块、小节的文档顺序排列。"""

    entities: tuple[TaskEntity, ...]
    relations: tuple[RelationCandidate, ...]
    failed_chunks: tuple[FailedChunk, ...]
    failed_sections: tuple[FailedSection, ...]


def exceeds_threshold(failed: int, total: int, ratio: float) -> bool:
    """§5：``failed / total > ratio``。阈值按其十进制写法精确比较（0.29 即 29/100）。"""
    if total <= 0:
        raise ValueError("total must be positive")
    return Decimal(failed) > Decimal(repr(ratio)) * total


# ---------------------------------------------------------------- 块与小节


@dataclass(frozen=True)
class _Section:
    section_id: str
    order: tuple[str, int]
    path: str | None
    chunks: tuple[StoredChunk, ...]


class _Halt(Exception):
    """阶段级停止：``circuit``（熔断打开）、``storage``（调用记录写不进）——临时故障，释放租约；
    ``auth``（供应商拒绝密钥，401/403）——任务级终止，不重试、不换 key（ADR-082 决定 4）。"""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True)
class _UnitResult:
    status: str
    attempts: int
    error_code: str | None
    result: Mapping[str, object] | None = field(default=None, repr=False)


# ---------------------------------------------------------------- 阶段编排


@dataclass
class _Progress:
    chunks_total: int
    chunks_done: int = 0
    chunks_failed: int = 0
    sections_total: int = 0
    sections_failed: int = 0
    by_code: Counter[str] = field(default_factory=Counter)

    def counts(self) -> dict[str, int]:
        return {
            "chunks_total": self.chunks_total,
            "chunks_done": self.chunks_done,
            "chunks_failed": self.chunks_failed,
            "sections_total": self.sections_total,
            "sections_failed": self.sections_failed,
        }


CREDENTIAL_MESSAGE = "个人模型 API 配置不可用，任务已终止；请检查「模型 API 设置」后重新上传"
AUTH_MESSAGE = "模型服务拒绝了 API 密钥，任务已终止；请检查「模型 API 设置」后重新上传"


# ---------------------------------------------------------------- 运行一次


@dataclass(frozen=True)
class RunOnceResult:
    reclaimed: ReclaimResult
    lease: Lease | None
    parse: ParseOutcome | None
    extract: ExtractOutcome | None
    handed_back: bool
