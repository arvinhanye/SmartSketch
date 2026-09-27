#!/usr/bin/env python3
"""G08 backfill (ADR-055): give the text chunks of already committed versions a current-space vector.

Versions committed before G08 (ADR-066) have no ``Chunk`` vectors, so J01 cannot find their
chunks. Publishing again does not repair them: a digest-equal publish takes the idempotent path
and skips P8, and a revision superseded by a newer one is in no new snapshot. This command calls
the same ``index_chunks`` as publish step P8 over each selected version's snapshot revision list.

- Selection: every committed version of every course; ``--course`` limits it to one course and
  ``--version`` (only with ``--course``) to one committed version of that course.
- Revisions are de-duplicated per course (chunks are shared by the versions of a course), so each
  course's revision set is read and indexed once, in the scope of its newest selected version.
- V12: the space is the one SQLite records. The command refuses (nothing written, model not called)
  when the configured EMBEDDING_* space or any selected version's ``embedding_space`` differs from
  it; run ``scripts/reembed.py`` first.
- ``--dry-run`` only counts the chunks lacking a valid vector; it neither calls the model nor writes.
- Safe while API and worker run, no lock or stop needed: chunks are immutable and shared, and
  ``index_chunks`` only ``MERGE``s ``Chunk`` nodes and sets the vector of chunks that lack one —
  the same idempotent write a concurrent publish P8 would make. Version copies, pointers and
  SQLite are not touched. Re-running after an interruption finishes the rest.

Run from the repository root with the usual SQLITE_URL / NEO4J_* / EMBEDDING_* set::

    python3 scripts/backfill_chunk_vectors.py [--course ID [--version N]] [--dry-run]

Exit codes: 0 done (or nothing to do), 1 failed (Neo4j / model / stored snapshot; re-run to
finish), 2 refused (invalid arguments or configuration, unknown selection, space mismatch).
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src" / "backend"))

from app.repositories import versions  # noqa: E402
from app.repositories.graph_migrations import VectorSpaceError, sqlite_current_space  # noqa: E402
from app.repositories.neo4j import GraphScope, Neo4jRepository, RepositoryError  # noqa: E402
from app.repositories.versions import VersionRecord  # noqa: E402
from app.services.ai.embeddings import EmbeddingAdapter, EmbeddingBatchError  # noqa: E402
from app.services.versions.chunk_vectors import _chunks, _missing, index_chunks  # noqa: E402
from app.services.versions.snapshot import SnapshotFormatError, load_snapshot  # noqa: E402

REEMBED_HINT = "先运行 scripts/reembed.py 把向量迁到记录的空间（V12），再运行本命令"


class Refused(Exception):
    """Exit 2: nothing was read from Neo4j or written."""


class Failed(Exception):
    """Exit 1: stopped; what was written stays valid, re-run to finish."""


@dataclass(frozen=True)
class CourseWork:
    course_id: str
    versions: tuple[int, ...]  # 版本号，降序
    scope_version_id: str  # 最新入选版本；文本块跨版本共享，作用域只满足参数约定
    revision_ids: frozenset[str]


@dataclass(frozen=True)
class CourseResult:
    work: CourseWork
    total: int
    count: int  # 实跑为新算向量数；--dry-run 为缺向量数


def _selected(sqlite_url: str, course: str | None, version: int | None) -> dict[str, list[VersionRecord]]:
    if version is not None and course is None:
        raise Refused("--version 必须与 --course 一起使用")
    courses = versions.list_course_ids(sqlite_url)
    if course is not None:
        if course not in courses:
            raise Refused(f"课程 {course} 不存在")
        courses = [course]
    selected: dict[str, list[VersionRecord]] = {}
    for course_id in courses:
        if version is not None:
            record = versions.get_committed(sqlite_url, course_id, version)
            if record is None:
                raise Refused(f"课程 {course_id} 没有已提交的版本 {version}")
            records = [record]
        else:
            records = versions.list_versions(sqlite_url, course_id)
        if records:
            selected[course_id] = records
    return selected


def plan(sqlite_url: str, space: str, course: str | None, version: int | None) -> list[CourseWork]:
    """Select versions, check V12 for all of them, then read their snapshot revision lists."""
    selected = _selected(sqlite_url, course, version)
    mismatched = [f"{c} v{r.version}（{r.embedding_space}）" for c, records in selected.items()
                  for r in records if r.embedding_space != space]
    if mismatched:
        raise Refused(f"{len(mismatched)} 个版本的向量空间与记录空间 {space} 不同：{'、'.join(mismatched[:5])}；"
                      f"{REEMBED_HINT}")
    work: list[CourseWork] = []
    for course_id, records in selected.items():
        records = sorted(records, key=lambda r: r.version or 0, reverse=True)
        revision_ids: set[str] = set()
        for record in records:
            raw = versions.read_snapshot(sqlite_url, record.version_id)
            if raw is None:
                raise Failed(f"课程 {course_id} 版本 {record.version} 没有存储快照")
            try:
                snapshot = load_snapshot(raw)
            except SnapshotFormatError as exc:
                raise Failed(f"课程 {course_id} 版本 {record.version} 的快照无法解析：{exc}") from None
            revision_ids.update(r["revision_id"] for r in snapshot.data["revisions"])
        work.append(CourseWork(course_id, tuple(r.version or 0 for r in records), records[0].version_id,
                               frozenset(revision_ids)))
    return work


def run(*, sqlite_url: str, repo: Neo4jRepository, embedder: Any, space: str, work: Sequence[CourseWork],
        dry_run: bool) -> list[CourseResult]:
    """``work`` must come from ``plan`` (V12 already checked); ``index_chunks`` re-checks the embedder space."""
    results: list[CourseResult] = []
    for item in work:
        scope = GraphScope(item.course_id, item.scope_version_id)
        if dry_run:
            chunks = _chunks(sqlite_url, item.course_id, item.revision_ids)
            results.append(CourseResult(item, len(chunks), len(_missing(repo, scope, chunks, space))))
        else:
            result = index_chunks(sqlite_url, repo, embedder, scope, item.revision_ids, space)
            results.append(CourseResult(item, result.total, result.embedded))
    return results


def _embedder(settings: Any, client: Any) -> EmbeddingAdapter:
    if client is None:
        if settings.EMBEDDING_MODE == "fake":
            from app.services.ai.fake import FakeEmbeddingClient
            client = FakeEmbeddingClient()
        else:
            from app.services.ai.compatible import CompatibleEmbeddingClient
            client = CompatibleEmbeddingClient.from_settings(settings)
    return EmbeddingAdapter(settings, client)


def _version(value: str) -> int:
    number = int(value)
    if number < 1:
        raise ValueError(value)
    return number


def main(argv: Sequence[str] | None = None, *, environ: Mapping[str, str] | None = None,
         repo: Neo4jRepository | None = None, client: Any = None) -> int:
    parser = argparse.ArgumentParser(description="Backfill chunk vectors of committed versions (G08, ADR-055, ADR-066).")
    parser.add_argument("--course", help="只处理这门课程")
    parser.add_argument("--version", type=_version, help="只处理该课程的这个已提交版本号（需同时给 --course）")
    parser.add_argument("--dry-run", action="store_true", help="只统计缺向量的文本块，不调用向量模型、不写入")
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return 0 if exc.code == 0 else 2

    from app.config import SettingsError, load_settings
    try:
        settings = load_settings(environ)
    except SettingsError as exc:
        print(f"拒绝执行：{exc}", file=sys.stderr)  # 只列变量名，不含取值
        return 2

    own_repo = repo is None
    try:
        try:
            space = sqlite_current_space(settings.SQLITE_URL)()
        except (VectorSpaceError, ValueError) as exc:
            raise Refused(f"记录的向量空间不可用：{exc}") from None
        work = plan(settings.SQLITE_URL, space, args.course, args.version)
        embedder = None if args.dry_run else _embedder(settings, client)
        if embedder is not None and embedder.space != space:
            raise Refused(f"配置的向量空间 {embedder.space} 与记录空间 {space} 不同；{REEMBED_HINT}")
        if not work:
            print("没有入选的已提交版本，无需补齐。")
            return 0
        if own_repo:
            repo = Neo4jRepository.from_settings(settings)
        results = run(sqlite_url=settings.SQLITE_URL, repo=repo, embedder=embedder, space=space, work=work,
                      dry_run=args.dry_run)
    except Refused as exc:
        print(f"拒绝执行：{exc}", file=sys.stderr)
        return 2
    except Failed as exc:
        print(f"失败：{exc}；已写入的向量保留且有效，修复后重新运行即可补完", file=sys.stderr)
        return 1
    except (RepositoryError, VectorSpaceError, EmbeddingBatchError) as exc:
        print(f"失败：{type(exc).__name__}: {exc}；已写入的向量保留且有效，重新运行即可补完", file=sys.stderr)
        return 1
    except Exception as exc:  # 细节可能含连接串或服务端回显，只报类型
        print(f"失败：{type(exc).__name__}；已写入的向量保留且有效，重新运行即可补完", file=sys.stderr)
        return 1
    finally:
        if own_repo and repo is not None:
            repo.close()

    label = "缺向量" if args.dry_run else "新算向量"
    for r in results:
        listed = "、".join(f"v{v}" for v in r.work.versions)
        print(f"课程 {r.work.course_id}：版本 {listed}，修订 {len(r.work.revision_ids)} 个，"
              f"文本块 {r.total}，{label} {r.count}")
    total = sum(r.total for r in results)
    count = sum(r.count for r in results)
    suffix = "（--dry-run：未调用向量模型，未写入）" if args.dry_run else ""
    print(f"合计：课程 {len(results)} 门，文本块 {total}，{label} {count}，空间 {space}{suffix}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
