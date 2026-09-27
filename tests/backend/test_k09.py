"""K09 demo import: idempotent, demo-course-only, retryable, refuses substituted material.

The worker is simulated through the importer's ``sleep`` hook (it moves the demo tasks'
stages), so these run without Neo4j; tests/integration/test_k09.py runs the real worker
and publish against Neo4j.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import shutil
import uuid
from pathlib import Path

import pytest

from app.config import load_settings
from app.repositories.accounts import insert_account
from app.repositories.courses import create_course, list_members
from app.repositories.sqlite import connect, migrate
from app.services.demo_import import DemoImportError, import_demo, load_manifest

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "datasets" / "demo" / "manifest.json"
VALID_HASH = "$argon2id$v=19$m=65536,t=3,p=4$c2FsdA$aGFzaA"


@pytest.fixture
def env(tmp_path):
    url = f"sqlite:///{(tmp_path / 'state.sqlite3').as_posix()}"
    migrate(url)
    settings = load_settings({"SQLITE_URL": url, "STORAGE_DIR": str(tmp_path / "files")})
    users = {name: insert_account(url, account_id=uuid.uuid4().hex, username=name,
                                  password_hash=VALID_HASH, role=role)
             for name, role in (("demo_teacher", "teacher"), ("demo_student", "student"),
                                ("demo_student2", "student"), ("other_teacher", "teacher"))}
    return settings, url, users


def _stages(url: str, course_id: str) -> list[str]:
    with connect(url) as db:
        return [row[0] for row in db.execute(
            "SELECT stage FROM processing_tasks WHERE course_id = ? ORDER BY created_at", (course_id,))]


def worker_sets(url: str, stage: str):
    """A fake worker: on each poll, move every queued task to ``stage``."""
    def sleep(_seconds: float) -> None:
        with connect(url) as db:
            failed = stage == "failed"
            db.execute("UPDATE processing_tasks SET stage = ?, progress = 1, cancel_requested = ?, "
                       "error_code = ?, error_message = ? WHERE stage = 'queued'",
                       (stage, int(stage == "cancelled"), "EXTRACTION_FAILED" if failed else None,
                        "simulated" if failed else None))
    return sleep


def test_manifest_documents_are_self_written_and_hash_pinned():
    manifest = load_manifest(MANIFEST)
    assert manifest.teacher == "demo_teacher" and manifest.documents
    raw = json.loads(MANIFEST.read_text(encoding="utf-8"))
    assert "自编" in raw["note"]
    for document in manifest.documents:
        assert hashlib.sha256(document.path.read_bytes()).hexdigest() == document.sha256


def test_first_run_creates_course_members_uploads_and_publishes(env):
    settings, url, users = env
    published = []
    report = import_demo(settings, load_manifest(MANIFEST), wait_seconds=5, poll_seconds=0,
                         sleep=worker_sets(url, "awaiting_review"),
                         publisher=lambda cid, tid: published.append((cid, tid)) or (1, False))
    assert report.course_created and report.course_id
    assert sorted(report.members_added) == ["demo_student", "demo_student2"]
    assert report.uploaded == ["ch3-stack-queue.md"] and report.skipped == []
    assert report.stages == {"ch3-stack-queue.md": "awaiting_review"}
    assert published == [(report.course_id, users["demo_teacher"].id)]
    assert report.published_version == 1


def test_rerun_does_not_duplicate_anything(env):
    settings, url, _ = env
    manifest = load_manifest(MANIFEST)
    first = import_demo(settings, manifest, wait_seconds=5, poll_seconds=0,
                        sleep=worker_sets(url, "awaiting_review"), publisher=lambda c, t: (1, False))
    second = import_demo(settings, manifest, wait_seconds=5, poll_seconds=0,
                         sleep=worker_sets(url, "awaiting_review"), publisher=lambda c, t: (1, True))
    assert second.course_id == first.course_id and not second.course_created
    assert second.members_added == [] and second.uploaded == []
    assert second.skipped == ["ch3-stack-queue.md"] and second.publish_unchanged is True
    with connect(url) as db:
        assert db.execute("SELECT COUNT(*) FROM courses").fetchone()[0] == 1
        assert db.execute("SELECT COUNT(*) FROM materials").fetchone()[0] == 1
    assert len(_stages(url, first.course_id)) == 1
    assert len(list_members(url, first.course_id)) == 3


def test_failed_processing_is_reported_then_retried_by_a_rerun(env):
    settings, url, _ = env
    manifest = load_manifest(MANIFEST)
    with pytest.raises(DemoImportError, match="re-run the importer to retry"):
        import_demo(settings, manifest, wait_seconds=5, poll_seconds=0,
                    sleep=worker_sets(url, "failed"), publisher=lambda c, t: pytest.fail("published"))
    report = import_demo(settings, manifest, wait_seconds=5, poll_seconds=0,
                         sleep=worker_sets(url, "awaiting_review"), publisher=lambda c, t: (1, False))
    assert report.uploaded == ["ch3-stack-queue.md"]
    assert _stages(url, report.course_id) == ["failed", "awaiting_review"]
    assert report.published_version == 1


def test_timeout_without_worker_is_resumable_and_does_not_publish(env):
    settings, url, _ = env
    manifest = load_manifest(MANIFEST)
    ticks = iter(range(100))
    with pytest.raises(DemoImportError, match="is the worker"):
        import_demo(settings, manifest, wait_seconds=3, poll_seconds=0, sleep=lambda s: None,
                    now=lambda: next(ticks), publisher=lambda c, t: pytest.fail("published"))
    report = import_demo(settings, manifest, wait_seconds=5, poll_seconds=0,
                         sleep=worker_sets(url, "awaiting_review"), publisher=lambda c, t: (1, False))
    assert report.uploaded == [] and report.skipped == ["ch3-stack-queue.md"]
    assert _stages(url, report.course_id) == ["awaiting_review"]


def test_only_the_demo_course_is_touched(env):
    settings, url, users = env
    other = create_course(url, name="真实课程", description=None, creator_id=users["other_teacher"].id)
    same_name_elsewhere = create_course(url, name=load_manifest(MANIFEST).name, description=None,
                                        creator_id=users["other_teacher"].id)
    report = import_demo(settings, load_manifest(MANIFEST), wait_seconds=5, poll_seconds=0,
                         sleep=worker_sets(url, "awaiting_review"), publisher=lambda c, t: (1, False))
    assert report.course_id not in (other.id, same_name_elsewhere.id)
    with connect(url) as db:
        assert db.execute("SELECT COUNT(*) FROM materials WHERE course_id != ?",
                          (report.course_id,)).fetchone()[0] == 0
        assert db.execute("SELECT COUNT(*) FROM course_members WHERE course_id IN (?, ?)",
                          (other.id, same_name_elsewhere.id)).fetchone()[0] == 2  # only their teachers


def test_substituted_or_escaping_documents_are_refused_before_any_write(env, tmp_path):
    settings, url, _ = env
    copy = tmp_path / "demo"
    shutil.copytree(MANIFEST.parent, copy)
    (copy / "ch3-stack-queue.md").write_text("真实课程讲义（不应被导入）", encoding="utf-8")
    with pytest.raises(DemoImportError, match="sha256"):
        import_demo(settings, load_manifest(copy / "manifest.json"), publisher=None, sleep=lambda s: None)
    raw = json.loads((copy / "manifest.json").read_text(encoding="utf-8"))
    raw["documents"][0]["path"] = "../outside.md"
    (copy / "manifest.json").write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(DemoImportError, match="escapes"):
        load_manifest(copy / "manifest.json")
    with connect(url) as db:
        assert db.execute("SELECT COUNT(*) FROM courses").fetchone()[0] == 0


def test_missing_accounts_are_refused_before_any_write(tmp_path):
    url = f"sqlite:///{(tmp_path / 'state.sqlite3').as_posix()}"
    migrate(url)
    settings = load_settings({"SQLITE_URL": url, "STORAGE_DIR": str(tmp_path / "files")})
    with pytest.raises(DemoImportError, match="seed-demo-accounts"):
        import_demo(settings, load_manifest(MANIFEST), publisher=None, sleep=lambda s: None)
    with connect(url) as db:
        assert db.execute("SELECT COUNT(*) FROM courses").fetchone()[0] == 0


def test_script_entry_point_loads(monkeypatch):
    spec = importlib.util.spec_from_file_location("import_demo_script", ROOT / "scripts" / "import-demo.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setenv("SQLITE_URL", "sqlite:////nonexistent-dir/x.sqlite3")
    assert module.main(["--no-publish"]) in (1, 2)
