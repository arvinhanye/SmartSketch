#!/usr/bin/env python3
"""C-ACC-A：只读核验持久化后知识点详情里的实际出处（``source_refs``）。

走 API 知识点详情的同一条路径 ``app.services.graph.read.read_knowledge_point``（草稿作用域、教师读取），
图谱只经 ``GraphReader`` / ``Neo4jRepository.read``（读路由，服务器拒绝写入）。该路径依赖的 SQLite 连接
被临时换成只读（``mode=ro&immutable=1`` + ``PRAGMA query_only``），不在测量库目录生成任何文件；
运行前后记录数据库 SHA-256 并断言不变。

核验内容（每门课）：
- 草稿实际知识点数；``source`` 字段（``ai`` / ``manual`` 是**生成方式标签**，不是引用证据）分布；
- 详情 ``source_refs``：每个 AI 知识点是否至少一条可定位来源（页码或章节）、条数、带页码 / 章节 / 文件名的条数；
- 原始证据边（``EVIDENCED_BY``）：块在 SQLite 本课中是否存在（否则悬空）、文档是否属于本课、
  是否有指向他课块的边（课程过滤之外的单独只读计数）。

输出只含编号、计数与摘要哈希，不含课程正文、密钥或连接口令。

用法（连接口令按用户授权从环境文件读取，只取 NEO4J_URI / NEO4J_USER / NEO4J_PASSWORD，不打印）::

    python evaluation/audit_persisted_sources.py --db <测量库> --env-file <测量区 .env> \\
        --course <course_id> --course <course_id> --out evaluation/raw/c-acc-a/sources.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import sys
import urllib.parse
from collections import Counter
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.repositories import chunks as chunks_repo
from app.repositories import materials as materials_repo
from app.repositories import tasks as tasks_repo
from app.repositories.graph_read import DRAFT, GraphReader
from app.repositories.neo4j import GraphScope, Neo4jRepository
from app.repositories.sqlite import database_path
from app.services.graph import read as read_service
from app.services.graph.read import ReadTarget, SourceUnavailable, read_knowledge_point

NEO4J_KEYS = ("NEO4J_URI", "NEO4J_USER", "NEO4J_PASSWORD")

#: 指向他课文本块的证据边数（应用查询按课程过滤，看不到这类边，所以单独只读计数）
CROSS_COURSE_EVIDENCE = """
MATCH (n:KnowledgePoint {course_id: $course_id, version_id: $version_id})-[e:EVIDENCED_BY]->(c:Chunk)
WHERE $effective_task_ids IS NOT NULL AND c.course_id <> $course_id
RETURN count(e) AS edges
"""


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@contextmanager
def readonly_connect(sqlite_url: str) -> Iterator[sqlite3.Connection]:
    """只读且不碰锁文件：``immutable=1`` 假定期间无人写库（测量服务已停、WAL 为空）。"""
    path = database_path(sqlite_url)
    uri = "file:" + urllib.parse.quote(str(path)) + "?mode=ro&immutable=1"
    database = sqlite3.connect(uri, uri=True, isolation_level=None)
    try:
        database.execute("PRAGMA query_only = ON")
        yield database
    finally:
        database.close()


def _ro(sqlite_url: str):
    return readonly_connect(sqlite_url)


_PATCHED = (chunks_repo, materials_repo, tasks_repo, read_service)


@contextmanager
def readonly_repositories() -> Iterator[None]:
    """详情路径用到的仓储模块临时改用只读连接；退出时恢复。"""
    saved = [(module, module.connect) for module in _PATCHED]
    try:
        for module in _PATCHED:
            module.connect = _ro
        yield
    finally:
        for module, original in saved:
            module.connect = original


def _course_materials(sqlite_url: str, course_id: str) -> set[str]:
    with readonly_connect(sqlite_url) as db:
        return {row[0] for row in db.execute("SELECT id FROM materials WHERE course_id = ?", (course_id,))}


def audit_course(reader: Any, sqlite_url: str, *, course_id: str, effective_task_ids: Sequence[str],
                 cross_course_evidence: Callable[[], int]) -> dict[str, Any]:
    scope = GraphScope(course_id, DRAFT, effective_task_ids=tuple(effective_task_ids))
    target = ReadTarget(scope, "teacher", None)
    nodes = reader.nodes(scope, "teacher")
    labels = Counter(str(node.get("source") or "") for node in nodes)
    refs_total = with_page = with_section = with_name = 0
    located_ai = manual_without = 0
    missing_ai: list[str] = []
    unreadable: list[dict[str, str]] = []
    digest_rows: list[list[Any]] = []
    for node in nodes:
        kp_id = node["kp_id"]
        is_manual = node.get("source") == "manual"
        try:
            detail = read_knowledge_point(reader, sqlite_url, target, kp_id)
        except SourceUnavailable:
            missing_ai.append(kp_id)
            continue
        except Exception as error:              # 读取失败照实记录，不当作有出处
            unreadable.append({"kp_id": kp_id, "error": type(error).__name__})
            continue
        refs = [ref.root.model_dump(exclude_none=True) for ref in detail.source_refs]
        if not refs:
            if is_manual:
                manual_without += 1
            else:
                missing_ai.append(kp_id)
            continue
        if not is_manual:
            located_ai += 1
        for ref in refs:
            refs_total += 1
            with_page += "page" in ref
            with_section += "section_path" in ref
            with_name += "document_name" in ref
            digest_rows.append([kp_id, ref["chunk_id"], ref["document_id"], ref.get("page"), ref.get("section_path")])

    evidence = reader.evidence(scope, "teacher", [node["kp_id"] for node in nodes])
    known = {chunk.chunk_id: chunk for chunk in chunks_repo.get_chunks(
        sqlite_url, course_id=course_id, chunk_ids=sorted({e.chunk_id for e in evidence}))}
    materials = _course_materials(sqlite_url, course_id)
    dangling = sorted({e.chunk_id for e in evidence if e.chunk_id not in known})
    documents = {e.document_id or known[e.chunk_id].material_id for e in evidence
                 if e.document_id or e.chunk_id in known}
    digest_rows.sort(key=lambda row: json.dumps(row, ensure_ascii=False))
    return {
        "course_id": course_id,
        "effective_task_ids": list(effective_task_ids),
        "nodes": len(nodes),
        "source_label": dict(sorted(labels.items())),
        "ai_nodes_with_located_refs": located_ai,
        "manual_nodes_without_refs": manual_without,
        "refs": {"total": refs_total, "with_page": with_page, "with_section_path": with_section,
                 "with_document_name": with_name},
        "evidence_edges": len(evidence),
        "distinct_chunks": len({e.chunk_id for e in evidence}),
        "defects": {
            "ai_nodes_without_located_refs": sorted(missing_ai),
            "dangling_chunks": dangling,
            "foreign_documents": sorted(d for d in documents if d not in materials),
            "cross_course_evidence_edges": cross_course_evidence(),
            "unreadable_nodes": unreadable,
        },
        "refs_digest": hashlib.sha256(json.dumps(digest_rows, ensure_ascii=False).encode("utf-8")).hexdigest(),
    }


def _neo4j_env(path: Path) -> dict[str, str]:
    """只取三个连接变量；值不打印、不写盘。"""
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        key, sep, value = line.partition("=")
        key = key.strip()
        if sep and key in NEO4J_KEYS:
            values[key] = value.strip().strip('"').strip("'")
    missing = [key for key in NEO4J_KEYS if not values.get(key)]
    if missing:
        raise SystemExit(f"环境文件缺少 {', '.join(missing)}")
    return values


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="只读核验持久化后知识点详情的实际出处")
    parser.add_argument("--db", required=True, help="测量 SQLite 文件路径（只读打开）")
    parser.add_argument("--env-file", required=True, help="只从中读取 NEO4J_URI / NEO4J_USER / NEO4J_PASSWORD")
    parser.add_argument("--course", action="append", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)

    from neo4j import GraphDatabase

    db_path = Path(args.db).resolve()
    sqlite_url = f"sqlite:///{db_path.as_posix()}"
    before = file_sha256(db_path)
    env = _neo4j_env(Path(args.env_file))
    driver = GraphDatabase.driver(env["NEO4J_URI"], auth=(env["NEO4J_USER"], env["NEO4J_PASSWORD"]))
    repo = Neo4jRepository(driver)
    reader = GraphReader(repo)
    courses = []
    try:
        with readonly_repositories():
            for course_id in args.course:
                with readonly_connect(sqlite_url) as db:
                    effective = tasks_repo.read_effective_task_ids(db, course_id)
                scope = GraphScope(course_id, DRAFT, effective_task_ids=effective)
                courses.append(audit_course(
                    reader, sqlite_url, course_id=course_id, effective_task_ids=effective,
                    cross_course_evidence=lambda scope=scope: int(
                        repo.read(CROSS_COURSE_EVIDENCE, scope, reader="teacher")[0]["edges"])))
    finally:
        driver.close()
    after = file_sha256(db_path)
    if after != before:
        raise SystemExit("测量库文件在核验期间发生变化：结果作废")
    parsed = urllib.parse.urlparse(env["NEO4J_URI"])
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "read_path": "app.services.graph.read.read_knowledge_point（草稿、教师）+ GraphReader 读路由",
        "neo4j_endpoint": f"{parsed.scheme}://{parsed.hostname}:{parsed.port}",
        "sqlite": {"path": str(db_path), "sha256_before": before, "sha256_after": after,
                   "open_mode": "mode=ro&immutable=1 + query_only"},
        "courses": courses,
    }
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    defects = sum(len(c["defects"]["ai_nodes_without_located_refs"]) + len(c["defects"]["dangling_chunks"])
                  + len(c["defects"]["foreign_documents"]) + c["defects"]["cross_course_evidence_edges"]
                  + len(c["defects"]["unreadable_nodes"]) for c in courses)
    print(json.dumps({"courses": [{k: c[k] for k in ("course_id", "nodes", "ai_nodes_with_located_refs", "refs")}
                                  for c in courses], "defect_items": defects}, ensure_ascii=False))
    return 0 if defects == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
