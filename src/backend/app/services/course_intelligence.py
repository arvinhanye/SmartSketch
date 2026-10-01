"""课程智能功能的可用状态：向量是否由真实模型生成、需不需要重新处理资料。

只用真实服务：演示向量的课程不能被当作在线数据使用，也不改数据库里的模型名或维度，
而是让用户自己触发「重新处理资料」（重新跑一遍资料处理，保留原有资料与图谱）。
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.config import Settings, embedding_space_identity
from app.repositories import versions as version_repo
from app.repositories.materials import list_materials
from app.services.materials import open_storage, upload_material
#: 旧数据被标记为「演示向量」的判据：空间形如 ``fake/<维度>``
FAKE_SPACE_PREFIX = "fake/"


@dataclass(frozen=True)
class CourseVectorStatus:
    """课程当前的向量情况。``needs_reprocess`` 为真时智能功能不可用。"""

    ready: bool
    embedding_space: str | None
    current_space: str
    needs_reprocess: bool
    documents: int
    message: str = ""
    can_reprocess: bool = False
    reasons: tuple[str, ...] = field(default_factory=tuple)

    def as_dict(self) -> dict:
        return {
            "ready": self.ready,
            "embedding_space": self.embedding_space,
            "current_space": self.current_space,
            "needs_reprocess": self.needs_reprocess,
            "documents": self.documents,
            "message": self.message,
            "can_reprocess": self.can_reprocess,
            "reasons": list(self.reasons),
        }


NEEDS_REPROCESS_MESSAGE = "这门课程需要重新处理资料后才能使用智能功能。"


def configured_space(settings: Settings) -> str:
    """本机当前配置指向的真实向量空间（与启动门禁同一推导）。"""
    model, dimensions, is_fake = embedding_space_identity(settings)
    return f"{'fake' if is_fake else model}/{dimensions}"


def course_vector_status(settings: Settings, course_id: str) -> CourseVectorStatus:
    documents = list_materials(settings.SQLITE_URL, course_id=course_id)
    current = configured_space(settings)
    published = version_repo.current_version(settings.SQLITE_URL, course_id)
    space = published.embedding_space if published is not None else None
    reasons: list[str] = []
    if published is None:
        reasons.append("not_published")
    if space is not None and space.startswith(FAKE_SPACE_PREFIX):
        # 演示向量的课程：旧向量不能直接当在线向量用
        reasons.append("demo_vectors")
    elif space is not None and space != current:
        reasons.append("different_space")
    needs_reprocess = bool(reasons)
    return CourseVectorStatus(
        ready=not needs_reprocess,
        embedding_space=space,
        current_space=current,
        needs_reprocess=needs_reprocess,
        documents=len(documents),
        message=NEEDS_REPROCESS_MESSAGE if needs_reprocess else "",
        can_reprocess=bool(documents),
        reasons=tuple(reasons),
    )


def reprocess_course(settings: Settings, course_id: str) -> tuple[list[str], int]:
    """重新处理本课程已上传的资料：用原文件重新排队，保留原有资料与图谱。

    返回 ``(新任务 ID, 资料总数)``；读不到原文件时该条资料会被跳过。
    """
    storage = open_storage(settings)
    records = list_materials(settings.SQLITE_URL, course_id=course_id)
    task_ids: list[str] = []
    for record in records:
        try:
            path = storage.path_for(record.storage_name)
            with path.open("rb") as handle:
                result = upload_material(
                    settings,
                    course_id=course_id,
                    filename=record.filename,
                    content_type=None,
                    chunks=iter(lambda: handle.read(1024 * 1024), b""),
                )
        except Exception:  # 文件缺失等：跳过这条资料，继续处理其余资料
            continue
        task_ids.append(result.task_id)
    return task_ids, len(records)
