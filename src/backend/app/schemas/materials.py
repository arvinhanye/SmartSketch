"""Contract models for ``listDocuments`` / ``uploadDocument`` (src/contracts/api.v1.yaml)."""

from typing import Literal

from pydantic import BaseModel

DocumentFormat = Literal["pdf", "docx", "txt", "markdown"]
TaskStage = Literal[
    "queued",
    "parsing",
    "extracting",
    "merging",
    "persisting",
    "awaiting_review",
    "completed",
    "failed",
    "cancelled",
]


class Document(BaseModel):
    id: str
    course_id: str
    filename: str
    format: DocumentFormat
    size_bytes: int
    parse_status: TaskStage
    uploaded_at: str  # ISO 8601 UTC, e.g. 2026-09-25T01:02:03.456Z


class UploadAccepted(BaseModel):
    task_id: str
    document_id: str
