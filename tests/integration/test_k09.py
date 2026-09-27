"""K09 示例课程幂等导入：``datasets/demo/`` 课程包与 ``scripts/import-demo.py``。

验收（docs/atomic-tasks.json K09）：**重跑不重复；只写示例课；失败可重试；不混入真实资料或删除他课**。

测试分两组：

- 不需要 Neo4j 的用例（默认全跑）：真实 SQLite 临时库（``migrate`` 建全表）+ 真实服务层
  （``create_new_course`` / ``upload_material``）建「他课」与半成品；脚本按 ``sqlite:///`` +
  ``STORAGE_DIR`` 环境变量实跑，断言幂等键、守卫、dry-run 与失败续跑。
- 真实 Neo4j 用例（``SMARTSKETCH_TEST_NEO4J_URI/USER/PASSWORD``，未配置即整条跳过）：导入后由测试
  自带确定性 responder 驱动**真实 worker 流水线**（``run_pipeline_once``）落图，证明示例包能被真实
  解析/抽取链路消费，且重跑仍零新增。

断言口径：``created/skipped/failed`` 取脚本 stdout 的汇总行；「零新增」用整库 ``iterdump`` 逐行比对，
比单独计数更严（任何行被改写也会判红）。
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import uuid
from contextlib import closing
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.config import load_settings
from app.repositories.accounts import insert_account
from app.repositories.courses import create_course
from app.repositories.model_calls import SqliteCallStore
from app.repositories.sqlite import connect, database_path, migrate
from app.services.ai.client import ModelRequest
from app.services.ai.entities import EntityExtractor
from app.services.ai.fake import FakeModelClient
from app.services.ai.policy import ModelCallPolicy
from app.services.ai.relations import RelationExtractor
from app.services.materials import upload_material
from app.workers.extract_task import ExtractionToolkit
from app.workers.persist_graph import run_pipeline_once

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "import-demo.py"
DATASET = ROOT / "datasets" / "demo"
MANIFEST_PATH = DATASET / "manifest.json"
MANIFEST = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
COURSE_NAME = MANIFEST["course"]["name"]
DEMO_TEACHER = "demo_teacher"

_EXTENSIONS = {".pdf": "pdf", ".docx": "docx", ".txt": "txt", ".md": "markdown", ".markdown": "markdown"}
VALID_HASH = "$argon2id$v=19$m=65536,t=3,p=4$c2FsdA$aGFzaA"
_ENV = ("SMARTSKETCH_TEST_NEO4J_URI", "SMARTSKETCH_TEST_NEO4J_USER", "SMARTSKETCH_TEST_NEO4J_PASSWORD")
_LIVE = all(os.environ.get(name) for name in _ENV)
live = pytest.mark.skipif(not _LIVE, reason="isolated Neo4j fixture not configured")


# ---------------------------------------------------------------- helpers


def sqlite_url(path: Path) -> str:
    return f"sqlite:///{path.as_posix()}"


def sql(url: str, query: str, *params: object) -> list[tuple]:
    with connect(url) as database:
        return database.execute(query, params).fetchall()


def dump(url: str) -> list[str]:
    """整库逐行转储：任何新增/改写/删除都会让两次结果不同。"""
    with closing(sqlite3.connect(database_path(url))) as database:
        return list(database.iterdump())


def storage_files(root: Path) -> list[Path]:
    return sorted(path for path in root.rglob("*") if path.is_file()) if root.exists() else []


def script_env(tmp_path: Path, url: str, *, storage: Path | None = None, extra: dict | None = None) -> dict:
    env = {**os.environ}
    env.pop("PYTHONPATH", None)  # 脚本自己设置 import 路径（与 test_k10 同约定）
    env.update(
        {
            "APP_ENV": "test",
            "SQLITE_URL": url,
            "STORAGE_DIR": str(storage if storage is not None else tmp_path / "storage"),
            "LLM_MODE": "fake",
            "EMBEDDING_MODE": "fake",
            "UPLOAD_MAX_BYTES": "52428800",
            "NEO4J_URI": os.environ.get(_ENV[0], "bolt://127.0.0.1:1"),
            "NEO4J_USER": os.environ.get(_ENV[1], "neo4j"),
            "NEO4J_PASSWORD": os.environ.get(_ENV[2], "not-used"),
        }
    )
    env.update(extra or {})
    return env


def run_cli(env: dict, *args: str, timeout: int = 300) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args], env=env, capture_output=True, text=True, timeout=timeout, cwd=ROOT
    )


def summary(result: subprocess.CompletedProcess) -> tuple[int, int, int]:
    """``(created, skipped, failed)``：计数含课程本身（1 门）与每条资料。"""
    match = re.search(r"created=(\d+) skipped=(\d+) failed=(\d+)", result.stdout)
    assert match, f"no summary line in stdout:\n{result.stdout}\n{result.stderr}"
    return tuple(int(value) for value in match.groups())  # type: ignore[return-value]


def manual_import(env: dict, *args: str) -> subprocess.CompletedProcess:
    result = run_cli(env, *args)
    assert result.returncode == 0, f"import failed ({result.returncode}):\n{result.stdout}\n{result.stderr}"
    return result


def copied_dataset(tmp_path: Path, name: str = "dataset") -> Path:
    target = tmp_path / name
    shutil.copytree(DATASET, target)
    return target


def write_manifest(dataset: Path, documents: list[dict]) -> None:
    data = json.loads((dataset / "manifest.json").read_text(encoding="utf-8"))
    data["documents"] = documents
    (dataset / "manifest.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def reseal(dataset: Path, relative: str) -> None:
    """内容改动后重算 manifest 的 sha256（模拟作者同步示例包）。"""
    raw = (dataset / relative).read_bytes()
    data = json.loads((dataset / "manifest.json").read_text(encoding="utf-8"))
    for document in data["documents"]:
        if document["path"] == relative:
            document["sha256"] = "sha256:" + hashlib.sha256(raw).hexdigest()
    (dataset / "manifest.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def demo_course(url: str) -> tuple | None:
    rows = sql(url, "SELECT id, name, description, teacher_id FROM courses WHERE name = ?", COURSE_NAME)
    return rows[0] if rows else None


def course_materials(url: str, course_id: str) -> list[tuple]:
    return sql(
        url,
        "SELECT filename, format, size_bytes, content_hash FROM materials WHERE course_id = ? ORDER BY filename",
        course_id,
    )


def course_tasks(url: str, course_id: str) -> list[tuple]:
    return sql(
        url,
        "SELECT stage, idempotency_key FROM processing_tasks WHERE course_id = ? ORDER BY rowid",
        course_id,
    )


def counts(url: str) -> dict[str, int]:
    return {
        "courses": sql(url, "SELECT count(*) FROM courses")[0][0],
        "members": sql(url, "SELECT count(*) FROM course_members")[0][0],
        "materials": sql(url, "SELECT count(*) FROM materials")[0][0],
        "tasks": sql(url, "SELECT count(*) FROM processing_tasks")[0][0],
    }


@pytest.fixture
def db(tmp_path: Path) -> str:
    """真实 SQLite 临时库：应用全部迁移并建好 demo_teacher。"""
    url = sqlite_url(tmp_path / "state" / "smartsketch.sqlite3")
    (tmp_path / "state").mkdir(parents=True, exist_ok=True)
    migrate(url)
    insert_account(url, account_id=uuid.uuid4().hex, username=DEMO_TEACHER, password_hash=VALID_HASH, role="teacher")
    return url


def teacher_of(url: str, username: str = DEMO_TEACHER) -> str:
    return sql(url, "SELECT id FROM users WHERE username = ?", username)[0][0]


def other_course_with_data(url: str, name: str = "操作系统（他课）") -> SimpleNamespace:
    """另一门课 + 它的资料与任务：导入不得碰它。"""
    teacher = insert_account(
        url, account_id=uuid.uuid4().hex, username="other_teacher", password_hash=VALID_HASH, role="teacher"
    )
    course = create_course(url, name=name, description="他课的说明", creator_id=teacher.id)
    settings = load_settings(
        {
            "SQLITE_URL": url,
            "STORAGE_DIR": str(Path(url[10:]).parent / "other-storage"),
            "APP_ENV": "test",
            "LLM_MODE": "fake",
            "EMBEDDING_MODE": "fake",
        }
    )
    upload_material(
        settings,
        course_id=course.id,
        filename="他人资料.txt",
        content_type="text/plain",
        chunks=[b"other course content, not demo data\n"],
    )
    return SimpleNamespace(id=course.id, teacher_id=teacher.id, name=name)


# ---------------------------------------------------------------- 示例包自洽（不写库）


def test_manifest_and_files_are_self_consistent_and_not_real_material():
    data = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    assert data["schema_version"] == 1
    assert "自编" in data["notice"] and "不是真实课程资料" in data["notice"]
    assert data["course"]["name"] and data["course"]["description"]
    documents = data["documents"]
    assert len(documents) >= 2
    formats = set()
    for document in documents:
        raw = (DATASET / document["path"]).read_bytes()
        assert document["sha256"] == "sha256:" + hashlib.sha256(raw).hexdigest()
        assert document["format"] in {"pdf", "docx", "txt", "markdown"}
        # 标题后缀必须与声明格式一致：落盘时由 FileStorage 按扩展名复核
        assert _EXTENSIONS[Path(document["title"]).suffix.lower()] == document["format"]
        formats.add(document["format"])
    assert len(formats) >= 2  # MVP：格式 ≥ 2 种


def test_demo_documents_read_like_course_notes():
    """示例正文要能切句、含明确知识点句与先修句（LLM_MODE=fake 下的演示仍可读）。"""
    text = "\n".join((DATASET / d["path"]).read_text(encoding="utf-8") for d in MANIFEST["documents"])
    assert len(re.findall(r"^[\u4e00-\u9fff]{2,8}是.+。$", text, re.MULTILINE)) >= 4
    assert "之前需要先掌握" in text
    assert "/Users/" not in text and "password" not in text.lower()


# ---------------------------------------------------------------- 首次导入与幂等


def test_first_import_creates_the_course_and_every_document(tmp_path: Path, db: str):
    env = script_env(tmp_path, db)
    result = manual_import(env)
    assert summary(result) == (len(MANIFEST["documents"]) + 1, 0, 0)  # 课程 1 + 资料 N

    course = demo_course(db)
    assert course is not None
    assert course[1] == COURSE_NAME and course[3] == teacher_of(db)
    assert sql(db, "SELECT role FROM course_members WHERE course_id = ? AND user_id = ?", course[0], course[3]) == [
        ("teacher",)
    ]
    assert course_materials(db, course[0]) == sorted(
        (
            document["title"],
            document["format"],
            (DATASET / document["path"]).stat().st_size,
            document["sha256"],
        )
        for document in MANIFEST["documents"]
    )
    tasks = course_tasks(db, course[0])
    assert [stage for stage, _ in tasks] == ["queued"] * len(MANIFEST["documents"])
    # 幂等键 = 课程名 + 标题 + 内容 sha256：身份里必须真的含内容哈希
    keys = dict(
        sql(
            db,
            "SELECT m.filename, t.idempotency_key FROM processing_tasks AS t "
            "JOIN materials AS m ON m.course_id = t.course_id AND m.id = t.document_id "
            "WHERE t.course_id = ?",
            course[0],
        )
    )
    for document in MANIFEST["documents"]:
        key = keys[document["title"]]
        assert key.endswith(document["sha256"]) and document["title"] in key and COURSE_NAME in key
    assert len(storage_files(tmp_path / "storage")) == len(MANIFEST["documents"])
    assert "created" in result.stdout and "created=0 skipped=0 failed=0" not in result.stdout


def test_second_import_changes_nothing_at_all(tmp_path: Path, db: str):
    env = script_env(tmp_path, db)
    manual_import(env)
    before_rows, before_files = dump(db), storage_files(tmp_path / "storage")
    before_counts = counts(db)

    again = manual_import(env)
    assert summary(again) == (0, len(MANIFEST["documents"]) + 1, 0)  # 课程 + 全部资料都在跳过
    assert counts(db) == before_counts
    assert dump(db) == before_rows  # 一行都没多、没改、没删
    assert storage_files(tmp_path / "storage") == before_files  # 重复落盘已被补偿删除
    assert "skipped" in again.stdout


def test_a_third_import_with_an_explicit_course_id_is_also_a_no_op(tmp_path: Path, db: str):
    env = script_env(tmp_path, db)
    manual_import(env)
    course_id = demo_course(db)[0]
    before = dump(db)
    again = manual_import(env, "--course-id", course_id)
    assert summary(again) == (0, len(MANIFEST["documents"]) + 1, 0)
    assert dump(db) == before


# ---------------------------------------------------------------- 只写示例课


def test_other_courses_are_never_touched_or_deleted(tmp_path: Path, db: str):
    other = other_course_with_data(db)
    other_rows = (
        sql(db, "SELECT * FROM courses WHERE id = ?", other.id),
        sql(db, "SELECT * FROM course_members WHERE course_id = ?", other.id),
        sql(db, "SELECT * FROM materials WHERE course_id = ?", other.id),
        sql(db, "SELECT * FROM processing_tasks WHERE course_id = ?", other.id),
    )
    env = script_env(tmp_path, db)
    manual_import(env)
    manual_import(env)
    assert (
        sql(db, "SELECT * FROM courses WHERE id = ?", other.id),
        sql(db, "SELECT * FROM course_members WHERE course_id = ?", other.id),
        sql(db, "SELECT * FROM materials WHERE course_id = ?", other.id),
        sql(db, "SELECT * FROM processing_tasks WHERE course_id = ?", other.id),
    ) == other_rows
    # 示例课里只有示例包声明的资料，没有混入他课资料
    course_id = demo_course(db)[0]
    assert {row[0] for row in course_materials(db, course_id)} == {d["title"] for d in MANIFEST["documents"]}


def test_refuses_when_the_demo_course_name_belongs_to_another_teacher(tmp_path: Path, db: str):
    teacher = insert_account(
        db, account_id=uuid.uuid4().hex, username="other_teacher", password_hash=VALID_HASH, role="teacher"
    )
    taken = create_course(db, name=COURSE_NAME, description="别人先占了同一个课名", creator_id=teacher.id)
    before = dump(db)
    result = run_cli(script_env(tmp_path, db))
    assert result.returncode == 2, result.stdout + result.stderr
    assert COURSE_NAME in result.stderr
    assert dump(db) == before
    assert sql(db, "SELECT count(*) FROM materials") == [(0,)]
    assert sql(db, "SELECT teacher_id FROM courses WHERE id = ?", taken.id) == [(teacher.id,)]


def test_refuses_a_course_id_that_is_not_the_demo_course(tmp_path: Path, db: str):
    other = other_course_with_data(db)
    before = dump(db)
    result = run_cli(script_env(tmp_path, db), "--course-id", other.id)
    assert result.returncode == 2, result.stdout + result.stderr
    assert "course-id" in result.stderr or "示例课" in result.stderr
    assert dump(db) == before


def test_refuses_when_the_course_id_does_not_exist(tmp_path: Path, db: str):
    before = dump(db)
    result = run_cli(script_env(tmp_path, db), "--course-id", "0" * 32)
    assert result.returncode == 2
    assert "course-id" in result.stderr
    assert dump(db) == before


# ---------------------------------------------------------------- 配置与账号守卫


def test_an_unmigrated_database_is_refused_before_writing(tmp_path: Path):
    url = sqlite_url(tmp_path / "empty.sqlite3")
    with closing(sqlite3.connect(database_path(url))):
        pass
    result = run_cli(script_env(tmp_path, url))
    assert result.returncode == 2
    assert "迁移" in result.stderr or "migrat" in result.stderr
    assert not storage_files(tmp_path / "storage")


def test_a_missing_demo_teacher_is_refused_with_the_next_step(tmp_path: Path, db: str):
    sql(db, "DELETE FROM users WHERE username = ?", DEMO_TEACHER)
    before = dump(db)
    result = run_cli(script_env(tmp_path, db))
    assert result.returncode == 2
    assert "seed-demo-accounts.py" in result.stderr
    assert dump(db) == before


def test_a_student_account_with_the_demo_username_is_refused(tmp_path: Path, db: str):
    sql(db, "DELETE FROM users WHERE username = ?", DEMO_TEACHER)
    insert_account(db, account_id=uuid.uuid4().hex, username=DEMO_TEACHER, password_hash=VALID_HASH, role="student")
    before = dump(db)
    result = run_cli(script_env(tmp_path, db))
    assert result.returncode == 2
    assert "角色" in result.stderr
    assert dump(db) == before


# ---------------------------------------------------------------- dry-run


def test_dry_run_reports_the_plan_without_writing_anything(tmp_path: Path, db: str):
    before = dump(db)
    result = run_cli(script_env(tmp_path, db), "--dry-run")
    assert result.returncode == 0, result.stderr
    assert "dry-run" in result.stdout
    assert summary(result) == (len(MANIFEST["documents"]) + 1, 0, 0)
    assert dump(db) == before
    assert not storage_files(tmp_path / "storage")
    assert not (tmp_path / "storage").exists()  # 连存储目录都不建


def test_dry_run_after_import_reports_skips(tmp_path: Path, db: str):
    env = script_env(tmp_path, db)
    manual_import(env)
    before, files = dump(db), storage_files(tmp_path / "storage")
    result = run_cli(env, "--dry-run")
    assert result.returncode == 0
    assert summary(result) == (0, len(MANIFEST["documents"]) + 1, 0)
    assert dump(db) == before and storage_files(tmp_path / "storage") == files


# ---------------------------------------------------------------- 失败与续跑


def test_a_missing_or_corrupted_source_file_is_refused_then_retry_converges(tmp_path: Path, db: str):
    dataset = copied_dataset(tmp_path)
    broken = dataset / "documents" / "trees.txt"
    original = broken.read_bytes()
    before = dump(db)

    broken.rename(broken.with_suffix(".txt.moved"))  # 源文件被改名
    missing = run_cli(script_env(tmp_path, db), "--dataset", str(dataset))
    assert missing.returncode == 2, missing.stdout + missing.stderr
    assert "不存在" in missing.stderr  # 拒绝原因必须是缺文件，而不是别的失败
    assert dump(db) == before and not storage_files(tmp_path / "storage")  # 未写任何数据

    broken.write_bytes(original + b"\x00corrupted\n")  # 源文件被损坏（与 manifest 的 sha256 不符）
    corrupted = run_cli(script_env(tmp_path, db), "--dataset", str(dataset))
    assert corrupted.returncode == 2, corrupted.stdout + corrupted.stderr
    assert "sha256" in corrupted.stderr
    assert dump(db) == before and not storage_files(tmp_path / "storage")

    broken.write_bytes(original)  # 恢复后重跑收敛
    retried = manual_import(script_env(tmp_path, db), "--dataset", str(dataset))
    assert summary(retried) == (len(MANIFEST["documents"]) + 1, 0, 0)
    assert counts(db)["materials"] == len(MANIFEST["documents"])


def test_a_half_finished_import_is_resumed_without_duplicating_the_first_document(tmp_path: Path, db: str):
    dataset = copied_dataset(tmp_path)
    documents = MANIFEST["documents"]
    write_manifest(dataset, documents[:1])  # 第一次只有第一条：模拟中途停下来
    env = script_env(tmp_path, db)
    first = manual_import(env, "--dataset", str(dataset))
    assert summary(first) == (2, 0, 0)  # 课程 + 1 条资料
    course_id = demo_course(db)[0]
    first_material = sql(db, "SELECT * FROM materials WHERE course_id = ?", course_id)

    write_manifest(dataset, documents)  # 恢复完整示例包后重跑：只补缺的那条
    second = manual_import(env, "--dataset", str(dataset))
    assert summary(second) == (1, 2, 0)  # 补 1 条资料；课程与已导入的第一条被跳过
    assert sql(db, "SELECT * FROM materials WHERE course_id = ? AND filename = ?", course_id, documents[0]["title"]) == first_material
    assert counts(db)["materials"] == len(documents)
    assert counts(db)["tasks"] == len(documents)


def test_changed_source_content_is_imported_as_a_new_document(tmp_path: Path, db: str):
    """幂等键含内容 sha256：内容变了是一次新导入，内容没变才跳过。"""
    env = script_env(tmp_path, db)
    manual_import(env)
    dataset = copied_dataset(tmp_path)
    changed = dataset / MANIFEST["documents"][1]["path"]
    changed.write_bytes(changed.read_bytes() + "补充：二叉搜索树的查找平均复杂度是对数级。\n".encode("utf-8"))
    reseal(dataset, MANIFEST["documents"][1]["path"])

    again = manual_import(script_env(tmp_path, db), "--dataset", str(dataset))
    assert summary(again) == (1, 2, 0)  # 只有变了的第二条重新导入；课程与第一条跳过
    course_id = demo_course(db)[0]
    hashes = {row[3] for row in course_materials(db, course_id)}
    assert "sha256:" + hashlib.sha256(changed.read_bytes()).hexdigest() in hashes
    assert counts(db)["materials"] == len(MANIFEST["documents"]) + 1


def test_a_write_failure_exits_nonzero_and_the_retry_converges(tmp_path: Path, db: str):
    """写入阶段失败（存储不可用）：非 0 退出、不产生半成品；解除后重跑补齐。"""
    clean_env = script_env(tmp_path, db)
    blocked_storage = tmp_path / "blocked-storage"
    blocked_storage.write_text("不是目录：让 FileStorage 建目录失败\n", encoding="utf-8")
    blocked_env = script_env(tmp_path, db, storage=blocked_storage)

    result = run_cli(blocked_env)
    assert result.returncode == 1, result.stdout + result.stderr
    assert summary(result) == (1, 0, len(MANIFEST["documents"]))  # 课程建成，资料全部失败
    assert "STORAGE_UNAVAILABLE" in result.stderr
    course_id = demo_course(db)[0]
    assert sql(db, "SELECT count(*) FROM materials WHERE course_id = ?", course_id) == [(0,)]
    assert sql(db, "SELECT count(*) FROM processing_tasks WHERE course_id = ?", course_id) == [(0,)]

    blocked_storage.unlink()  # 解除故障后重跑：只补资料，课程被跳过
    retried = manual_import(clean_env)
    assert summary(retried) == (len(MANIFEST["documents"]), 1, 0)
    assert counts(db) == {"courses": 1, "members": 1, "materials": len(MANIFEST["documents"]),
                          "tasks": len(MANIFEST["documents"])}
    # 再跑一次仍是零新增
    before = dump(db)
    assert summary(manual_import(clean_env)) == (0, len(MANIFEST["documents"]) + 1, 0)
    assert dump(db) == before


def test_a_manifest_that_declares_a_format_the_file_does_not_have_is_refused(tmp_path: Path, db: str):
    dataset = copied_dataset(tmp_path)
    data = json.loads((dataset / "manifest.json").read_text(encoding="utf-8"))
    data["documents"][0]["title"] = "线性结构示例讲义.txt"  # 内容仍是 Markdown，标题后缀改成 .txt
    (dataset / "manifest.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    before = dump(db)
    result = run_cli(script_env(tmp_path, db), "--dataset", str(dataset))
    assert result.returncode == 2, result.stdout + result.stderr
    assert "后缀" in result.stderr
    assert dump(db) == before and not storage_files(tmp_path / "storage")


# ---------------------------------------------------------------- 真实 Neo4j：导入 → 真实流水线 → 幂等


def _responder(request: ModelRequest) -> str:
    """确定性 responder：从资料块逐行取「X 是…」为知识点，「学习 X 之前需要先掌握 Y」为先修关系。"""
    prompt = request.messages[0].content
    if "实体表（JSON" in prompt:  # E11 关系阶段
        ids: dict[str, str] = {}
        for line in prompt.splitlines():
            line = line.strip().rstrip(",")
            if line.startswith('{"id"'):
                row = json.loads(line)
                ids[row["name"]] = row["id"]
        items = []
        for match in re.finditer(r"学习(.+?)之前需要先掌握(.+?)。", prompt):
            later, earlier = match.group(1), match.group(2)
            if later in ids and earlier in ids and later != earlier:
                items.append(
                    {
                        "from_id": ids[earlier],
                        "to_id": ids[later],
                        "type": "PREREQUISITE",
                        "evidence": match.group(0),
                        "confidence": 0.8,
                    }
                )
        return json.dumps({"relations": items}, ensure_ascii=False)
    if "资料块：" not in prompt:  # 其他 purpose 一律不产知识
        return json.dumps({"entities": []}, ensure_ascii=False)
    chunk_text = prompt.split("资料块：", 1)[1]
    items = []
    for line in chunk_text.splitlines():
        sentence = line.strip()
        match = re.match(r"([\u4e00-\u9fff]{2,8})是(.+)。$", sentence)
        if match:
            items.append(
                {
                    "name": match.group(1),
                    "type": "concept",
                    "definition": sentence,
                    "evidence": sentence,
                    "confidence": 0.9,
                }
            )
    return json.dumps({"entities": items}, ensure_ascii=False)


def _toolkit(url: str) -> ExtractionToolkit:
    policy = ModelCallPolicy(
        primary=FakeModelClient(responder=_responder),
        store=SqliteCallStore(url),
        max_retries=0,
        failure_threshold=1000,
        open_seconds=30,
        task_token_budget=10**9,
        daily_token_budget=10**9,
        sleep=lambda _seconds: None,
    )
    return ExtractionToolkit(
        policy=policy,
        entities=lambda client: EntityExtractor(client, model="extract-model", max_output_tokens=4000),
        relations=lambda client: RelationExtractor(client, model="extract-model", max_output_tokens=4000),
    )


@pytest.fixture
def neo(tmp_path: Path):
    """每条用例独立课程 ID；只清理自己写入的图数据。"""
    neo4j = pytest.importorskip("neo4j")
    from app.repositories.graph_migrations import apply_migrations
    from app.repositories.neo4j import Neo4jRepository

    driver = neo4j.GraphDatabase.driver(os.environ[_ENV[0]], auth=(os.environ[_ENV[1]], os.environ[_ENV[2]]))
    apply_migrations(driver)

    def q(query: str, **params):
        return [
            dict(record)
            for record in driver.execute_query(query, parameters_=params, routing_="w", database_="neo4j").records
        ]

    course_id: list[str] = []
    try:
        yield SimpleNamespace(driver=driver, repo=Neo4jRepository(driver), q=q, course_id=course_id)
    finally:
        for value in course_id:
            q("MATCH (n {course_id: $c}) DETACH DELETE n", c=value)
        driver.close()


@live
def test_live_import_feeds_the_real_pipeline_and_stays_idempotent(tmp_path: Path, db: str, neo):
    env = script_env(tmp_path, db)
    manual_import(env)
    course_id = demo_course(db)[0]
    neo.course_id.append(course_id)

    settings = load_settings(env)
    toolkit = _toolkit(db)
    processed = 0
    for _ in range(20):
        outcome = run_pipeline_once(settings, toolkit=toolkit, repo=neo.repo, owner="k09-test")
        if outcome.lease is None:
            break
        processed += 1
    assert processed == len(MANIFEST["documents"]), f"未处理完全部资料：{processed}"

    stages = sorted(stage for (stage,) in sql(db, "SELECT stage FROM processing_tasks WHERE course_id = ?", course_id))
    assert stages == ["awaiting_review"] * len(MANIFEST["documents"])
    [graph] = neo.q(
        "MATCH (n:KnowledgePoint {course_id: $c, version_id: 'draft'}) RETURN count(n) AS nodes", c=course_id
    )
    assert graph["nodes"] > 0  # 示例包能被真实解析/抽取链路消费
    labels = {row["label"] for row in neo.q("MATCH (n {course_id: $c}) UNWIND labels(n) AS label "
                                            "RETURN DISTINCT label", c=course_id)}
    assert labels <= {"KnowledgePoint", "Chapter", "Chunk", "RelationIdentity", "DraftWriteGuard"}

    before = counts(db)
    again = manual_import(env)
    assert summary(again) == (0, len(MANIFEST["documents"]) + 1, 0)
    assert counts(db) == before  # 已处理任务的资料重跑也不新增任务/资料
    [graph_again] = neo.q(
        "MATCH (n:KnowledgePoint {course_id: $c, version_id: 'draft'}) RETURN count(n) AS nodes", c=course_id
    )
    assert graph_again["nodes"] == graph["nodes"]
