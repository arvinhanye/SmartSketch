#!/usr/bin/env python3
"""K09：把 ``datasets/demo/`` 示例课程包幂等导入本机数据库（一键演示数据）。

验收（docs/atomic-tasks.json K09）：**重跑不重复；只写示例课；失败可重试；不混入真实资料或删除他课**。

设计要点（ADR-077）：

1. **幂等键** = ``课程名 + 资料标题 + 内容 sha256``（同一课程内的 ``processing_tasks.idempotency_key``
   唯一）。重跑时先按「同标题 + 同 content_hash」判定已存在并跳过；即使判定与写入之间发生竞争，
   服务层 ``create_material_task`` 的幂等重放也会返回原任务并不新增行。
2. **只写示例课**：课程按 manifest 的 ``course.name`` 解析；名称已属于其他教师、或 ``--course-id``
   指向的不是这门示例课，一律在写入前拒绝。脚本从不删除或改写任何课程/资料/任务。
3. **失败可重试**：全部源文件在**任何写入之前**校验（存在、可读、sha256 与 manifest 一致、
   标题后缀与格式一致、格式 ≥ 2 种）。写入阶段每条资料走真实服务层 ``upload_material``
   （资料 + queued 任务同事务，落盘失败自带补偿删除），失败只影响该条；重跑会跳过已成功的条目。
4. 走**真实服务层**：``services.courses.create_new_course`` 与 ``services.materials.upload_material``，
   与 HTTP 路由同一条链路；上传后排队任务由 worker（``python -m app.workers``）领取，脚本不解析资料。
5. 配置只从环境变量经 ``load_settings`` 读取（不读 .env 文件）；口令/密钥不进命令行参数。

退出码：0 成功（含无新可做）；1 写入阶段有失败；2 配置/示例包/账号/守卫拒绝（未写任何数据）。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sqlite3
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src" / "backend"))

from app.config import Settings, SettingsError, load_settings  # noqa: E402
from app.repositories.accounts import AccountRecord, find_by_username, list_accounts  # noqa: E402
from app.repositories.courses import (  # noqa: E402
    CourseRecord,
    get_course,
    list_member_courses,
)
from app.repositories.sqlite import MigrationError, pending_migrations  # noqa: E402
from app.services.courses import create_new_course  # noqa: E402
from app.services.file_storage import DOCX_MEDIA_TYPE, FileStorageError  # noqa: E402
from app.services.materials import list_course_materials, upload_material  # noqa: E402

SCHEMA_VERSION = 1
DEFAULT_DATASET = Path(__file__).resolve().parents[1] / "datasets" / "demo"
DEFAULT_TEACHER = "demo_teacher"
REQUIRED_FORMATS = 2  # MVP 赛题：示例包格式 ≥ 2 种
MAX_IDEMPOTENCY_KEY = 255  # app.repositories.tasks 的硬上限
_SHA256 = re.compile(r"sha256:[0-9a-f]{64}\Z")
_FORMAT_EXTENSIONS = {
    "pdf": (".pdf",),
    "docx": (".docx",),
    "txt": (".txt",),
    "markdown": (".md", ".markdown"),
}
_MEDIA_TYPES = {
    "pdf": "application/pdf",
    "docx": DOCX_MEDIA_TYPE,
    "txt": "text/plain",
    "markdown": "text/markdown",
}
_LOG = "[demo-import]"


class Refused(Exception):
    """写入前拒绝：配置、示例包、账号或守卫不允许本次导入。"""


@dataclass(frozen=True)
class Document:
    path: Path
    title: str
    format: str
    sha256: str
    description: str


def idempotency_key(course_name: str, document: Document) -> str:
    """稳定幂等键：课程名 + 资料标题 + 内容 sha256（同一课程内唯一，长度由 build_plan 校验）。"""
    return f"k09::{course_name}::{document.title}::{document.sha256}"


@dataclass(frozen=True)
class CourseSpec:
    name: str
    description: str | None


@dataclass(frozen=True)
class DocumentPlan:
    document: Document
    will_create: bool
    reason: str


@dataclass(frozen=True)
class Plan:
    settings: Settings
    dataset: Path
    course: CourseSpec
    teacher: AccountRecord
    target: CourseRecord | None
    documents: tuple[DocumentPlan, ...]

    @property
    def course_reason(self) -> str:
        return "新建示例课" if self.target is None else "已存在，跳过"


# ---------------------------------------------------------------- 示例包校验（只读）


def _load_manifest(dataset: Path) -> dict:
    manifest_path = dataset / "manifest.json"
    if not manifest_path.is_file():
        raise Refused(f"示例包缺少 manifest.json：{manifest_path}")
    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise Refused(f"manifest.json 无法解析：{exc}") from None
    if not isinstance(data, dict):
        raise Refused("manifest.json 顶层必须是对象")
    if data.get("schema_version") != SCHEMA_VERSION:
        raise Refused(f"schema_version 必须是 {SCHEMA_VERSION}，实际为 {data.get('schema_version')!r}")
    notice = data.get("notice")
    if not isinstance(notice, str) or not notice.strip():
        raise Refused("manifest.json 缺少 notice：必须写明这是自编示例数据、不是真实课程资料")
    if "自编" not in notice and "不是真实课程资料" not in notice:
        print(f"{_LOG} 警告：notice 未写明「自编示例数据」，请确认示例包来源", file=sys.stderr)
    return data


def _course_spec(manifest: dict) -> CourseSpec:
    course = manifest.get("course")
    if not isinstance(course, dict):
        raise Refused("manifest.json 缺少 course 段")
    name = course.get("name")
    if not isinstance(name, str) or not name.strip() or len(name) > 120:
        raise Refused("course.name 必须是 1～120 字符的非空字符串（契约 CourseCreate.name）")
    description = course.get("description")
    if description is not None and (not isinstance(description, str) or len(description) > 1000):
        raise Refused("course.description 必须是不超过 1000 字符的字符串")
    return CourseSpec(name=name.strip(), description=description)


def _documents(manifest: dict, dataset: Path) -> tuple[Document, ...]:
    entries = manifest.get("documents")
    if not isinstance(entries, list) or not entries:
        raise Refused("manifest.json 的 documents 必须是非空数组")
    documents: list[Document] = []
    for index, entry in enumerate(entries):
        where = f"documents[{index}]"
        if not isinstance(entry, dict):
            raise Refused(f"{where} 必须是对象")
        raw_path = entry.get("path")
        title = entry.get("title")
        document_format = entry.get("format")
        declared = entry.get("sha256")
        if not isinstance(raw_path, str) or not raw_path.strip():
            raise Refused(f"{where}.path 必填")
        if not isinstance(title, str) or not title.strip():
            raise Refused(f"{where}.title 必填")
        if document_format not in _FORMAT_EXTENSIONS:
            raise Refused(f"{where}.format 必须是 {sorted(_FORMAT_EXTENSIONS)} 之一")
        if not isinstance(declared, str) or not _SHA256.match(declared):
            raise Refused(f"{where}.sha256 必须是 'sha256:<64 位小写十六进制>'")
        title = title.strip()
        if "/" in title or "\\" in title or title in {".", ".."}:
            raise Refused(f"{where}.title 不能含路径成分（落盘文件名）")
        suffix = Path(title).suffix.lower()
        if suffix not in _FORMAT_EXTENSIONS[document_format]:
            raise Refused(
                f"{where}：标题后缀 {suffix or '(无)'} 与声明格式 {document_format} 不一致"
            )
        source = (dataset / raw_path).resolve()
        try:
            source.relative_to(dataset.resolve())
        except ValueError:
            raise Refused(f"{where}.path 必须位于示例包目录内") from None
        if not source.is_file():
            raise Refused(f"{where} 的源文件不存在：{raw_path}")
        documents.append(
            Document(
                path=source,
                title=title,
                format=document_format,
                sha256=declared,
                description=str(entry.get("description") or ""),
            )
        )
    formats = {document.format for document in documents}
    if len(formats) < REQUIRED_FORMATS:
        # 不阻断导入：赛题要求的是**随仓库交付**的示例包覆盖面，由 tests/integration/test_k09.py 校验；
        # 允许作者用 --dataset 指向只含一种格式的临时包做局部导入。
        print(
            f"{_LOG} 警告：示例包只覆盖 {len(formats)} 种格式（MVP 演示要求至少 {REQUIRED_FORMATS} 种）",
            file=sys.stderr,
        )
    titles = [document.title for document in documents]
    if len(set(titles)) != len(titles):
        raise Refused("documents 的 title 必须互不相同（幂等键与落盘名都以它为准）")
    for document in documents:
        raw = document.path.read_bytes()
        actual = "sha256:" + hashlib.sha256(raw).hexdigest()
        if actual != document.sha256:
            raise Refused(
                f"源文件 {document.path.name} 的内容 sha256 与 manifest 不一致"
                f"（manifest {document.sha256}，实际 {actual}）；请同步 manifest.json 或恢复文件"
            )
    return tuple(documents)


# ---------------------------------------------------------------- 目标课程解析（只读，含硬性守卫）


def _resolve_target(
    sqlite_url: str, teacher: AccountRecord, spec: CourseSpec, explicit_course_id: str | None
) -> CourseRecord | None:
    """返回目标课程；不需要新建时返回已有记录，需要新建时返回 None。

    硬性守卫（只写示例课）：实际写入的名称/教师与 manifest 不符即拒绝，绝不落到别的课程上。
    """
    if explicit_course_id is not None:
        target = get_course(sqlite_url, explicit_course_id)
        if target is None:
            raise Refused(f"--course-id {explicit_course_id} 在库中不存在")
        if target.name != spec.name or target.teacher_id != teacher.id:
            raise Refused(
                f"--course-id {explicit_course_id} 指向的课程不是示例课"
                f"（课程名 {target.name!r}、teacher_id {target.teacher_id}）"
            )
        return target

    mine = [row for row, _ in list_member_courses(sqlite_url, teacher.id) if row.name == spec.name]
    if len(mine) > 1:
        raise Refused(f"教师 {teacher.username} 名下有多门同名课程 {spec.name!r}，无法确定目标，请改用 --course-id")
    if mine:
        if mine[0].teacher_id != teacher.id:
            raise Refused(f"课程 {spec.name!r} 的创建者不是 {teacher.username}，拒绝写入")
        return mine[0]

    # 该教师还没有这门课：新建之前确认课名没有被其他教师占用（绝不复用/改写他人课程）。
    for account in list_accounts(sqlite_url):
        for row, _ in list_member_courses(sqlite_url, account.id):
            if row.name == spec.name and row.teacher_id != teacher.id:
                raise Refused(
                    f"课程名 {spec.name!r} 已属于其他教师（teacher_id {row.teacher_id}）；"
                    "请改用其他课名或先由该教师处理，脚本不会写入、删除或改写他人课程"
                )
    return None


def _existing_material(settings: Settings, course_id: str, document: Document) -> bool:
    for record in list_course_materials(settings, course_id):
        if record.filename == document.title and record.content_hash == document.sha256:
            return True
    return False


# ---------------------------------------------------------------- 计划与执行


def build_plan(args: argparse.Namespace) -> Plan:
    dataset = Path(args.dataset).expanduser().resolve()
    if not dataset.is_dir():
        raise Refused(f"示例包目录不存在：{dataset}")
    manifest = _load_manifest(dataset)
    spec = _course_spec(manifest)
    documents = _documents(manifest, dataset)
    for document in documents:
        if len(idempotency_key(spec.name, document)) > MAX_IDEMPOTENCY_KEY:
            raise Refused(f"资料 {document.title!r} 的幂等键超过 {MAX_IDEMPOTENCY_KEY} 字符")

    try:
        settings = load_settings()
    except SettingsError as exc:
        raise Refused(f"配置无效：{exc}") from None
    try:
        pending = pending_migrations(settings.SQLITE_URL)
    except MigrationError as exc:
        raise Refused(f"SQLite 迁移历史不一致：{exc}") from None
    if pending:
        raise Refused(
            "数据库有待应用的迁移（" + "、".join(pending) + "）；"
            "请先停 API 与 worker，再运行 `python -m app.repositories.sqlite`"
        )

    teacher = find_by_username(settings.SQLITE_URL, args.teacher)
    if teacher is None:
        raise Refused(
            f"账号 {args.teacher!r} 不存在；先运行 "
            "`SEED_DEMO_PASSWORD=<本机口令> python3 scripts/seed-demo-accounts.py` 建演示账号"
        )
    if teacher.role != "teacher":
        raise Refused(f"账号 {args.teacher!r} 的角色是 {teacher.role}，示例课需要一个教师账号")

    target = _resolve_target(settings.SQLITE_URL, teacher, spec, args.course_id)
    plans = tuple(
        DocumentPlan(
            document=document,
            will_create=target is None or not _existing_material(settings, target.id, document),
            reason="" if target is None else "已存在相同内容（同标题 + 同 content_hash）",
        )
        for document in documents
    )
    return Plan(
        settings=settings,
        dataset=dataset,
        course=spec,
        teacher=teacher,
        target=target,
        documents=plans,
    )


def _print_plan(plan: Plan) -> None:
    print(f"{_LOG} 示例包：{plan.dataset}（schema_version={SCHEMA_VERSION}）")
    print(f"{_LOG} 导入账号：{plan.teacher.username}（{plan.teacher.role}）")
    print(f"{_LOG} 目标课程：{plan.course.name} —— {plan.course_reason}")


def report_plan(plan: Plan) -> None:
    """dry-run：只报告将做什么，不写库、不落盘、不建目录。"""
    _print_plan(plan)
    created = 0 if plan.target is not None else 1
    skipped = 0 if plan.target is None else 1
    if plan.target is None:
        print(f"{_LOG} would create course    {plan.course.name}")
    else:
        print(f"{_LOG} would skip   course    {plan.course.name}（已存在 course_id={plan.target.id}）")
    for item in plan.documents:
        if item.will_create:
            created += 1
            print(
                f"{_LOG} would create document  {item.document.title}"
                f"  format={item.document.format} sha256={item.document.sha256}"
            )
        else:
            skipped += 1
            print(f"{_LOG} would skip   document  {item.document.title}  （{item.reason}）")
    print(f"{_LOG} summary created={created} skipped={skipped} failed=0")
    print(f"{_LOG} dry-run：未写入任何数据（未建课程、未落盘、未建任务）")


def apply_plan(plan: Plan) -> int:
    _print_plan(plan)
    course_id: str | None = plan.target.id if plan.target is not None else None
    created = 0
    skipped = 0
    failed = 0

    if plan.target is None:
        course = create_new_course(
            plan.settings.SQLITE_URL,
            plan.teacher,
            name=plan.course.name,
            description=plan.course.description,
        )
        course_id = course.id
        # 硬性守卫：真实写入对象必须就是 manifest 声明的那门课。
        if course.name != plan.course.name:
            raise Refused(f"新建课程返回的名称 {course.name!r} 与 manifest 不一致，已停止后续写入")
        created += 1
        print(f"{_LOG} created  course    {course.name}  course_id={course.id}")
    else:
        skipped += 1
        print(f"{_LOG} skipped  course    {plan.course.name}（已存在 course_id={plan.target.id}）")

    assert course_id is not None
    for item in plan.documents:
        document = item.document
        if not item.will_create:
            skipped += 1
            print(f"{_LOG} skipped  document  {document.title}  （{item.reason}）")
            continue
        try:
            raw = document.path.read_bytes()
            if "sha256:" + hashlib.sha256(raw).hexdigest() != document.sha256:
                raise Refused(f"{document.title} 在导入过程中发生变化，请重新运行")
            result = upload_material(
                plan.settings,
                course_id=course_id,
                filename=document.title,
                content_type=_MEDIA_TYPES[document.format],
                chunks=iter([raw]),
                idempotency_key=idempotency_key(plan.course.name, document),
            )
        except FileStorageError as exc:
            failed += 1
            print(f"{_LOG} failed   document  {document.title}  code={exc.code} {exc.message}", file=sys.stderr)
            continue
        except (OSError, sqlite3.Error, ValueError) as exc:
            failed += 1
            print(f"{_LOG} failed   document  {document.title}  {type(exc).__name__}: {exc}", file=sys.stderr)
            continue
        created += 1
        print(
            f"{_LOG} created  document  {document.title}  format={document.format}"
            f" size={len(raw)} task={result.task_id} document_id={result.document_id}"
        )

    print(f"{_LOG} summary created={created} skipped={skipped} failed={failed} course_id={course_id}")
    _print_usage(plan, failed)
    return 1 if failed else 0


def _print_usage(plan: Plan, failed: int) -> None:
    origin = plan.settings.WEB_ORIGIN
    print(f"{_LOG} 如何在网页上看到这门课：")
    print(f"{_LOG}   1) 打开 {origin} ，用 {plan.teacher.username} 登录，课程列表里就有「{plan.course.name}」")
    print(f"{_LOG}   2) 本次共 {len(plan.documents)} 条资料按真实上传链路处理（成功即生成 processing_tasks 排队）；")
    print(f"{_LOG}      教师可在审核页核对知识点并发布，学生端发布后才可见图谱")
    print(f"{_LOG}      worker 命令： python -m app.workers（工作目录 src/backend；或 ./scripts/dev-up.sh 起本地整套）")
    print(f"{_LOG}   3) 任务进度： GET /api/v1/tasks/{{tid}}（tid 见上面每行的 task=…）")
    if failed:
        print(f"{_LOG} 有 {failed} 条资料失败：修复后重跑本命令即可续传，已导入的条目会被跳过", file=sys.stderr)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="import-demo.py",
        description="把 datasets/demo 的示例课程包幂等导入（重跑不重复；只写示例课；支持 --dry-run）",
    )
    parser.add_argument("--dataset", default=str(DEFAULT_DATASET), help="示例包目录（含 manifest.json）")
    parser.add_argument("--teacher", default=DEFAULT_TEACHER, help=f"导入用的教师账号名（缺省 {DEFAULT_TEACHER}）")
    parser.add_argument("--course-id", default=None, help="显式指定目标课程 ID，必须就是示例课，否则拒绝")
    parser.add_argument("--dry-run", action="store_true", help="只报告将做什么，不写入任何数据")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        plan = build_plan(args)
    except Refused as exc:
        print(f"{_LOG} 拒绝导入：{exc}", file=sys.stderr)
        print(f"{_LOG} 未写入任何数据；排除原因后重跑本命令即可", file=sys.stderr)
        return 2
    if args.dry_run:
        report_plan(plan)
        return 0
    try:
        return apply_plan(plan)
    except Refused as exc:
        # 走到这里说明计划已开始执行（例如课程已建、随后源文件变化）：不承诺「零写入」。
        print(f"{_LOG} 拒绝导入：{exc}", file=sys.stderr)
        print(f"{_LOG} 已写入的条目按条原子保留；重跑本命令会跳过它们并从断点续上", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print(f"{_LOG} 已中断：每条资料各自原子（资料 + 任务同事务），重跑会跳过已导入的条目", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
