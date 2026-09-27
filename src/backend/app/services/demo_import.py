"""K09: idempotent import of the demo course described by ``datasets/demo/manifest.json``.

Rules (atomic-tasks K09 acceptance):

- **Re-running never duplicates.** The course is found by (teacher, name); a member already
  present is kept; a document whose content hash already has a live task in the course is
  skipped; publishing an unchanged draft returns the existing version (G05 digest check).
- **Only the demo course is written.** Every write names the demo course's ID; nothing is
  ever deleted, in this course or any other.
- **Failures are retryable.** A document whose latest task ended ``failed``/``cancelled`` is
  uploaded again on the next run (D-16: re-processing is a new upload); interrupted runs
  resume from whatever state the database holds.
- **No real material.** Documents must live under the manifest's directory and match the
  SHA-256 recorded in the manifest, so an edited or substituted file is refused before any
  write.

Documents are processed by the running worker (``python -m app.workers``); the importer
only enqueues them and waits. It does not claim tasks itself, because the worker queue is
shared by all courses and claiming here could process another course's task.
"""

from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.config import Settings
from app.repositories.accounts import AccountRecord, find_by_username
from app.repositories.courses import (
    CourseRecord,
    add_member,
    create_course,
    list_member_courses,
)
from app.services.materials import list_course_materials, upload_material

DONE_STAGES = frozenset({"awaiting_review", "completed"})
RETRY_STAGES = frozenset({"failed", "cancelled"})


class DemoImportError(RuntimeError):
    """Refused before or during import; the message says what to fix."""


@dataclass(frozen=True)
class DemoDocument:
    path: Path
    content_type: str
    sha256: str


@dataclass(frozen=True)
class DemoManifest:
    key: str
    name: str
    description: str | None
    teacher: str
    students: tuple[str, ...]
    documents: tuple[DemoDocument, ...]
    publish: bool


@dataclass
class ImportReport:
    course_id: str = ""
    course_created: bool = False
    members_added: list[str] = field(default_factory=list)
    uploaded: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    stages: dict[str, str] = field(default_factory=dict)
    published_version: int | None = None
    publish_unchanged: bool | None = None

    def as_dict(self) -> dict[str, Any]:
        return dict(self.__dict__)


def load_manifest(path: Path) -> DemoManifest:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        course = raw["course"]
        base = path.parent.resolve()
        documents = []
        for item in raw["documents"]:
            doc_path = (base / item["path"]).resolve()
            if base not in doc_path.parents:
                raise DemoImportError(f"document path escapes the manifest directory: {item['path']}")
            documents.append(DemoDocument(doc_path, item["content_type"], item["sha256"].lower()))
        return DemoManifest(
            key=course["key"], name=course["name"], description=course.get("description"),
            teacher=course["teacher"], students=tuple(course.get("students", ())),
            documents=tuple(documents), publish=bool(raw.get("publish", True)),
        )
    except (OSError, ValueError, KeyError, TypeError) as error:
        raise DemoImportError(f"invalid manifest {path}: {error}") from None


def _account(settings: Settings, username: str, role: str) -> AccountRecord:
    account = find_by_username(settings.SQLITE_URL, username)
    if account is None:
        raise DemoImportError(
            f"account {username!r} does not exist; run scripts/seed-demo-accounts.py first")
    if account.role != role or account.disabled_at is not None:
        raise DemoImportError(f"account {username!r} is not an active {role}")
    return account


def _read_checked(document: DemoDocument) -> bytes:
    try:
        data = document.path.read_bytes()
    except OSError as error:
        raise DemoImportError(f"cannot read {document.path}: {error}") from None
    digest = hashlib.sha256(data).hexdigest()
    if digest != document.sha256:
        raise DemoImportError(f"{document.path.name} does not match the manifest sha256; refusing to import")
    return data


def _find_course(settings: Settings, teacher: AccountRecord, name: str) -> CourseRecord | None:
    matches = [row for row, role in list_member_courses(settings.SQLITE_URL, teacher.id)
               if role == "teacher" and row.teacher_id == teacher.id and row.name == name]
    if len(matches) > 1:
        raise DemoImportError(f"{len(matches)} courses named {name!r} belong to {teacher.username}; resolve manually")
    return matches[0] if matches else None


def import_demo(
    settings: Settings,
    manifest: DemoManifest,
    *,
    publisher: Callable[[str, str], tuple[int, bool]] | None,
    wait_seconds: float = 300.0,
    poll_seconds: float = 1.0,
    sleep: Callable[[float], None] = time.sleep,
    now: Callable[[], float] = time.monotonic,
) -> ImportReport:
    """Import (or resume importing) the demo course; ``publisher(course_id, teacher_id)``
    returns ``(version, unchanged)`` and is only called once every document is processed."""
    url = settings.SQLITE_URL
    # Validate everything before the first write.
    teacher = _account(settings, manifest.teacher, "teacher")
    students = [_account(settings, username, "student") for username in manifest.students]
    payloads = [(document, _read_checked(document)) for document in manifest.documents]

    report = ImportReport()
    course = _find_course(settings, teacher, manifest.name)
    if course is None:
        course = create_course(url, name=manifest.name, description=manifest.description, creator_id=teacher.id)
        report.course_created = True
    report.course_id = course.id

    for student in students:
        _, created = add_member(url, course_id=course.id, user_id=student.id, role="student", added_by=teacher.id)
        if created:
            report.members_added.append(student.username)

    def latest_by_hash() -> dict[str, str]:
        # list_course_materials is newest-first per D-16; keep the newest row per hash.
        stages: dict[str, str] = {}
        for row in sorted(list_course_materials(settings, course.id), key=lambda r: r.uploaded_at):
            stages[row.content_hash] = row.parse_status
        return stages

    existing = latest_by_hash()
    for document, data in payloads:
        stage = existing.get(f"sha256:{document.sha256}")
        if stage is not None and stage not in RETRY_STAGES:
            report.skipped.append(document.path.name)
            continue
        upload_material(settings, course_id=course.id, filename=document.path.name,
                        content_type=document.content_type, chunks=[data])
        report.uploaded.append(document.path.name)

    deadline = now() + wait_seconds
    while True:
        existing = latest_by_hash()
        report.stages = {doc.path.name: existing.get(f"sha256:{doc.sha256}", "missing") for doc, _ in payloads}
        failed = [name for name, stage in report.stages.items() if stage in RETRY_STAGES]
        if failed:
            raise DemoImportError(
                f"processing failed for {', '.join(failed)}; re-run the importer to retry "
                f"(course {course.id})")
        if all(stage in DONE_STAGES for stage in report.stages.values()):
            break
        if now() >= deadline:
            raise DemoImportError(
                f"documents still processing after {wait_seconds:.0f}s ({report.stages}); is the worker "
                f"(python -m app.workers) running? Re-run the importer to resume.")
        sleep(poll_seconds)

    if manifest.publish and publisher is not None:
        report.published_version, report.publish_unchanged = publisher(course.id, teacher.id)
    return report
