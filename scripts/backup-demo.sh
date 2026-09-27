#!/usr/bin/env bash
# K10：SQLite + Neo4j 一致时间点备份（ADR-054；交接 docs/handoffs/claude-k10.md）。
#
# 用法（在仓库根目录，先停 API 与 worker；SQLITE_URL、NEO4J_URI/USER/PASSWORD 取自环境变量）：
#   scripts/backup-demo.sh [--out DIR]                           # Bolt 导出（JSON 行），任意 Neo4j 可用
#   scripts/backup-demo.sh [--out DIR] --neo4j-container NAME    # neo4j-admin 离线 dump（会停启该容器）
#   scripts/backup-demo.sh --inspect --sqlite PATH --neo4j-uri URI        # 只读检查一对库，打印 JSON
#   scripts/backup-demo.sh --export-graph FILE --neo4j-uri URI            # 只导出图（恢复脚本的安全副本用）
#
# 一致性：先持有全部课程写锁（发布、回滚、图编辑、T6 写图都要这把锁），并拒绝活动任务租约、
# 活动写锁与未完成的发布/回滚尝试（与 F14 scripts/reembed.py 第 1 步同口径）；然后
#   G0 读 Neo4j 摘要 → S1 SQLite 在线备份 → Neo4j 导出（或离线 dump）→ G2 摘要必须等于 G0
#   → S3 再做一次 SQLite 在线备份，逐表内容必须等于 S1
# 任一不等说明有人绕过写锁写库，备份失败且不留目录。发布指针必须指向已提交版本，且该版本的
# 副本能按快照摘要复核（G03 P9 verify），否则失败；旧版本缺副本、孤儿副本、悬空文本块只记警告。
#
# 产物：DIR/k10-<UTC 时间>-<随机>/{sqlite.db, graph.jsonl.gz | neo4j/neo4j.dump, manifest.json}，
# 先写 .<名>.partial 再原子改名；目录 0700、文件 0600（含账号口令散列等，不得提交或外传）。
# 最后一行 stdout 为备份目录。退出码：0 完成；1 失败（未留备份）；2 拒绝（未停机/未迁移/参数错）。
# 仅供演练：K10_AFTER_SNAPSHOT_HOOK 在 S1 之后、导出之前执行一条 shell 命令（测试并发写用）。
set -euo pipefail
K10_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export K10_ROOT
export PYTHONPATH="$K10_ROOT/src/backend${PYTHONPATH:+:$PYTHONPATH}"
exec "${PYTHON:-python3}" - "$@" <<'PY'
import argparse
import gzip
import hashlib
import json
import os
import re
import secrets
import sqlite3
import subprocess
import sys
import time
from collections import Counter
from contextlib import ExitStack, closing
from datetime import datetime, timezone
from pathlib import Path

FORMAT = "smartsketch-k10/1"
GRAPH_FORMAT = "smartsketch-k10-graph/1"
SQLITE_FILE = "sqlite.db"
GRAPH_FILE = "graph.jsonl.gz"
DUMP_FILE = "neo4j/neo4j.dump"
HOLDER = "k10-backup"
REQUIRED_TABLES = ("courses", "course_locks", "graph_versions", "processing_tasks", "chunks")
DOCKER = os.environ.get("DOCKER", "docker")


class Refused(Exception):
    """Nothing was done: the system is not stopped, the database is not migrated, or arguments are wrong."""


class Failed(Exception):
    """The backup was attempted and discarded."""


def say(message):
    print(message, file=sys.stderr, flush=True)


def canon(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def digest(value):
    return hashlib.sha256(canon(value)).hexdigest()


def file_sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def quote_name(name):
    return "`" + str(name).replace("`", "``") + "`"


# ---------------------------------------------------------------- SQLite


def database_file(sqlite_url):
    from app.repositories.sqlite import database_path

    try:
        path = database_path(sqlite_url)
    except ValueError as exc:
        raise Refused(str(exc)) from None
    if not path.is_file():
        raise Refused(f"SQLite database {path} does not exist")
    return path


def sqlite_row(row):
    return canon([{"$hex": v.hex()} if isinstance(v, (bytes, bytearray)) else v for v in row])


def inspect_sqlite(path):
    """Row-level content of every table (layout- and journal-independent), pointers, integrity."""
    with closing(sqlite3.connect(path)) as db:
        integrity = db.execute("PRAGMA integrity_check").fetchone()[0]
        foreign_keys = len(db.execute("PRAGMA foreign_key_check").fetchall())
        schema = db.execute("SELECT type, name, sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_autoindex%' "
                            "ORDER BY type, name").fetchall()
        tables = {}
        for (name,) in db.execute("SELECT name FROM sqlite_master WHERE type = 'table' AND "
                                  "(name NOT LIKE 'sqlite_%' OR name = 'sqlite_sequence') ORDER BY name").fetchall():
            cursor = db.execute('SELECT * FROM "' + name.replace('"', '""') + '"')
            columns = [c[0] for c in cursor.description]
            rows = sorted(sqlite_row(r) for r in cursor)
            h = hashlib.sha256(canon(columns))
            for row in rows:
                h.update(b"\n" + row)
            tables[name] = {"rows": len(rows), "sha256": h.hexdigest()}
        pointers = []
        if "courses" in tables:
            pointers = [dict(zip(("course_id", "published_version_id", "published_version",
                                  "published_from_revision", "draft_revision"), r))
                        for r in db.execute("SELECT id, published_version_id, published_version, "
                                            "published_from_revision, draft_revision FROM courses ORDER BY id")]
    return {"integrity": integrity, "foreign_key_violations": foreign_keys, "schema_sha256": digest(schema),
            "tables": tables, "pointers": pointers}


def check_offline(url, holder=None):
    """F14 step 1 (scripts/reembed.py check_offline) plus other holders' course locks."""
    from app.repositories.sqlite import connect

    with connect(url) as db:
        if db.execute("SELECT 1 FROM processing_tasks WHERE lease_expires_at >= unixepoch() LIMIT 1").fetchone():
            raise Refused("active task lease: stop API and worker first")
        if db.execute("SELECT 1 FROM course_locks WHERE expires_at >= unixepoch() AND holder IS NOT ? LIMIT 1",
                      (holder,)).fetchone():
            raise Refused("active course write lock: stop API and worker first")
        if db.execute("SELECT 1 FROM graph_versions WHERE state IN ('preparing', 'materialized') LIMIT 1").fetchone():
            raise Refused("unfinished publish/rollback attempt: stop API and worker and run the G05 compensation "
                          "(reconcile.sweep) first")


def acquire_fence(url, holder, lock_seconds, stack):
    """Hold every course write lock (publish, rollback, graph edit and T6 all need it) for the whole run."""
    from app.repositories import course_locks
    from app.repositories.sqlite import connect

    with connect(url) as db:
        present = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        missing = [t for t in REQUIRED_TABLES if t not in present]
        if missing:
            raise Refused(f"SQLite database is not migrated (missing {', '.join(missing)}); run the migrations first")
        course_ids = [r[0] for r in db.execute("SELECT id FROM courses ORDER BY id")]
    check_offline(url)
    locks = []
    for course_id in course_ids:
        lock = course_locks.try_acquire(url, course_id, holder=holder, lease_seconds=lock_seconds)
        if lock is None:
            raise Refused(f"course {course_id} write lock is held by {course_locks.current_holder(url, course_id)!r}: "
                          "stop API and worker first")
        stack.enter_context(course_locks.held(url, lock, lease_seconds=lock_seconds))
        locks.append(lock)
    check_offline(url, holder)  # a lease or attempt that started while we were locking
    return locks


def assert_fence_held(url, holder, locks):
    from app.repositories.sqlite import connect

    with connect(url) as db:
        held = {r[0] for r in db.execute("SELECT token FROM course_locks WHERE holder = ? AND expires_at >= unixepoch()",
                                         (holder,))}
    if not {lock.token for lock in locks} <= held:
        raise Failed("a course write lock was lost during the backup; nothing is kept, re-run with API and worker "
                     "stopped")


def snapshot_sqlite(path, target, holder=None):
    """Online backup API: one read transaction, so one point in time even while WAL writers run."""
    with closing(sqlite3.connect(path, timeout=30)) as source, closing(sqlite3.connect(target)) as copy:
        source.backup(copy)
    with closing(sqlite3.connect(target, isolation_level=None)) as copy:
        copy.execute("PRAGMA journal_mode = DELETE")
        if holder is not None:
            copy.execute("DELETE FROM course_locks WHERE holder = ?", (holder,))
        if copy.execute("PRAGMA integrity_check").fetchone() != ("ok",):
            raise Failed("SQLite snapshot failed integrity_check")
    os.chmod(target, 0o600)


# ---------------------------------------------------------------- Neo4j


def driver_for(uri):
    from neo4j import GraphDatabase

    return GraphDatabase.driver(uri, auth=(os.environ.get("NEO4J_USER") or "neo4j",
                                           os.environ.get("NEO4J_PASSWORD") or ""),
                                notifications_min_severity="OFF")


def cypher(driver, query, **params):
    return [dict(r) for r in driver.execute_query(query, parameters_=params, routing_="w", database_="neo4j").records]


def wait_for_neo4j(driver, seconds):
    deadline = time.monotonic() + seconds
    while True:
        try:
            cypher(driver, "RETURN 1 AS ok")
            return
        except Exception as exc:
            if time.monotonic() > deadline:
                raise Failed(f"Neo4j did not come back within {seconds}s: {type(exc).__name__}") from None
            time.sleep(2)


def properties(values, where):
    return {str(k): plain(v, f"{where}.{k}") for k, v in values.items()}


def plain(value, where):
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, (list, tuple)):
        return [plain(v, where) for v in value]
    raise Failed(f"unsupported Neo4j property type {type(value).__name__} on {where}; extend the K10 export first")


def read_schema(driver):
    items = [{"kind": "constraint", "name": r["name"], "statement": r["s"]}
             for r in cypher(driver, "SHOW CONSTRAINTS YIELD name, createStatement RETURN name, createStatement AS s")]
    items += [{"kind": "index", "name": r["name"], "statement": r["s"]}
              for r in cypher(driver, "SHOW INDEXES YIELD name, type, owningConstraint, createStatement "
                                      "WHERE owningConstraint IS NULL AND type <> 'LOOKUP' "
                                      "RETURN name, createStatement AS s")]
    return sorted(items, key=lambda i: (i["kind"] != "constraint", i["name"]))


def graph_records(driver):
    with driver.session(database="neo4j", default_access_mode="READ") as session:
        with session.begin_transaction() as tx:
            for r in tx.run("MATCH (n) RETURN elementId(n) AS i, labels(n) AS l, properties(n) AS p"):
                yield {"k": "n", "i": r["i"], "l": sorted(r["l"]), "p": properties(r["p"], f"node {r['i']}")}
            for r in tx.run("MATCH (a)-[r]->(b) RETURN elementId(a) AS s, elementId(b) AS e, type(r) AS t, "
                            "properties(r) AS p"):
                yield {"k": "r", "s": r["s"], "e": r["e"], "t": r["t"],
                       "p": properties(r["p"], f"relationship {r['t']}")}


class GraphDigest:
    """Order- and id-independent digest: nodes by labels+properties, relationships by type+properties+ends."""

    def __init__(self):
        self.ids = {}
        self.nodes = []
        self.rels = []
        self.labels = Counter()
        self.types = Counter()

    def add(self, record):
        if record["k"] == "n":
            key = digest({"l": record["l"], "p": record["p"]})
            self.ids[record["i"]] = key
            self.nodes.append(key)
            self.labels.update(record["l"])
        else:
            self.rels.append(digest({"t": record["t"], "p": record["p"], "s": self.ids[record["s"]],
                                     "e": self.ids[record["e"]]}))
            self.types[record["t"]] += 1

    def summary(self, schema):
        h = hashlib.sha256()
        for key in sorted(self.nodes):
            h.update(key.encode() + b"\n")
        h.update(b"#\n")
        for key in sorted(self.rels):
            h.update(key.encode() + b"\n")
        return {"digest": "sha256:" + h.hexdigest(), "nodes": len(self.nodes), "relationships": len(self.rels),
                "labels": dict(sorted(self.labels.items())), "types": dict(sorted(self.types.items())),
                "schema": schema}


def inspect_graph(driver):
    schema = read_schema(driver)
    graph = GraphDigest()
    for record in graph_records(driver):
        graph.add(record)
    return graph.summary(schema)


def export_graph(driver, target):
    schema = read_schema(driver)
    graph = GraphDigest()
    with gzip.open(target, "wt", encoding="utf-8") as out:
        out.write(json.dumps({"k": "format", "format": GRAPH_FORMAT}) + "\n")
        for item in schema:
            out.write(json.dumps({"k": "schema", **item}, ensure_ascii=False) + "\n")
        for record in graph_records(driver):
            graph.add(record)
            out.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")
    os.chmod(target, 0o600)
    return graph.summary(schema)


def check_consistency(path, driver):
    """Pointer -> committed version -> copies that re-derive the snapshot digest; leftovers are listed."""
    from app.repositories.neo4j import Neo4jRepository
    from app.services.versions.materialize import verify
    from app.services.versions.snapshot import load_snapshot

    with closing(sqlite3.connect(path)) as db:
        courses = {r[0]: r for r in db.execute("SELECT id, published_version_id, published_version FROM courses")}
        committed = {r[1]: r for r in db.execute("SELECT course_id, version_id, version, snapshot_json, "
                                                 "embedding_space FROM graph_versions WHERE state = 'committed'")}
        chunks = set(db.execute("SELECT course_id, chunk_id FROM chunks").fetchall())
    repo = Neo4jRepository(driver)
    version_errors = {}
    for version_id, (_, _, _, snapshot, space) in sorted(committed.items()):
        try:
            verify(repo, load_snapshot(snapshot), version_id, space)
        except Exception as exc:
            version_errors[version_id] = f"{type(exc).__name__}: {exc}"[:300]
    pointer_errors = []
    for course_id, (_, version_id, version) in sorted(courses.items()):
        if version_id is None:
            continue
        row = committed.get(version_id)
        if row is None or row[0] != course_id or row[2] != version:
            pointer_errors.append(f"{course_id}: pointer {version_id} (v{version}) is not a committed version "
                                  "of this course")
        elif version_id in version_errors:
            pointer_errors.append(f"{course_id}: published version {version_id} does not verify: "
                                  f"{version_errors[version_id]}")
    stored = cypher(driver, "MATCH (n) WHERE (n:KnowledgePoint OR n:Chapter) AND n.version_id <> 'draft' "
                            "RETURN DISTINCT n.course_id AS c, n.version_id AS v")
    orphans = sorted(f"{r['c']}/{r['v']}" for r in stored
                     if r["v"] not in committed or committed[r["v"]][0] != r["c"])
    known = cypher(driver, "MATCH (n) WHERE n.course_id IS NOT NULL RETURN DISTINCT n.course_id AS c")
    unknown = sorted(str(r["c"]) for r in known if r["c"] not in courses)
    dangling = sorted(f"{r['c']}/{r['k']}" for r in cypher(driver, "MATCH (c:Chunk) RETURN c.course_id AS c, "
                                                                   "c.chunk_id AS k")
                      if (r["c"], r["k"]) not in chunks)
    return {"verified_versions": sorted(v for v in committed if v not in version_errors),
            "version_errors": version_errors, "pointer_errors": pointer_errors, "orphan_versions": orphans,
            "unknown_courses": unknown, "dangling_chunks": dangling}


def verdict(inspection):
    """(blocking problems, warnings) of an inspection."""
    sqlite, consistency = inspection["sqlite"], inspection["consistency"]
    blocking, warnings = [], []
    if sqlite["integrity"] != "ok":
        blocking.append(f"SQLite integrity_check: {sqlite['integrity']}")
    if sqlite["foreign_key_violations"]:
        blocking.append(f"SQLite foreign_key_check: {sqlite['foreign_key_violations']} violation(s)")
    blocking += [f"publish pointer: {e}" for e in consistency["pointer_errors"]]
    if consistency["unknown_courses"]:
        blocking.append(f"Neo4j holds data of courses absent from SQLite: {consistency['unknown_courses'][:5]}")
    pointed = {p["published_version_id"] for p in sqlite["pointers"]}
    warnings += [f"committed version {v} (not published now) does not verify: {e}"
                 for v, e in consistency["version_errors"].items() if v not in pointed]
    if consistency["orphan_versions"]:
        warnings.append(f"copies of uncommitted attempts (G05 sweep leftovers): {consistency['orphan_versions'][:5]}")
    if consistency["dangling_chunks"]:
        warnings.append(f"Chunk nodes without a SQLite chunk row: {consistency['dangling_chunks'][:5]}")
    return blocking, warnings


# ---------------------------------------------------------------- neo4j-admin (Docker)


def docker(*args, timeout=900):
    try:
        result = subprocess.run([DOCKER, *args], capture_output=True, text=True, timeout=timeout,
                                stdin=subprocess.DEVNULL)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise Failed(f"docker {args[0]} failed: {exc}") from None
    if result.returncode:
        raise Failed(f"docker {args[0]} failed: {result.stderr.strip()[-500:]}")
    return result.stdout.strip()


def container_image(name):
    try:
        info = docker("inspect", "--format", "{{.Config.Image}}|{{.State.Running}}", name, timeout=60)
    except Failed:
        raise Refused(f"container {name!r} not found (is Docker running?)") from None
    image, running = info.rsplit("|", 1)
    return image, running == "true"


def admin_dump(container, image, directory, driver, wait_seconds):
    """Community edition dumps only a stopped database: stop the container, dump from its volumes, start it."""
    directory.mkdir()
    os.chmod(directory, 0o777)  # the neo4j user (uid 7474) inside the dump container writes here
    say(f"stopping {container} for neo4j-admin database dump")
    docker("stop", "-t", "120", container)
    try:
        docker("run", "--rm", "--volumes-from", container, "-v", f"{directory}:/backups", image,
               "neo4j-admin", "database", "dump", "neo4j", "--to-path=/backups")
    finally:
        docker("start", container)
        os.chmod(directory, 0o700)
    dump = directory / "neo4j.dump"
    if not dump.is_file():
        raise Failed("neo4j-admin produced no neo4j.dump")
    try:
        os.chmod(dump, 0o600)
    except PermissionError:
        pass
    wait_for_neo4j(driver, wait_seconds)


# ---------------------------------------------------------------- the backup


def run_backup(args):
    url = os.environ.get("SQLITE_URL") or ""
    uri = args.neo4j_uri or os.environ.get("NEO4J_URI") or ""
    if not url or not uri:
        raise Refused("SQLITE_URL and NEO4J_URI (or --neo4j-uri) are required")
    path = database_file(url)
    stamp = datetime.now(timezone.utc)
    backup_id = f"k10-{stamp.strftime('%Y%m%dT%H%M%SZ')}-{secrets.token_hex(3)}"
    holder = f"{HOLDER}-{backup_id}"
    out = Path(args.out).resolve()
    final, partial = out / backup_id, out / f".{backup_id}.partial"
    image = None
    if args.neo4j_container:
        image, running = container_image(args.neo4j_container)
        if not running:
            raise Refused(f"container {args.neo4j_container!r} is not running")

    with ExitStack() as stack:
        locks = acquire_fence(url, holder, args.lock_seconds, stack)          # refusals end here
        driver = stack.enter_context(driver_for(uri))
        out.mkdir(parents=True, exist_ok=True)
        partial.mkdir()
        try:
            before = inspect_graph(driver)                                    # G0
            snapshot_sqlite(path, partial / SQLITE_FILE, holder)              # S1
            hook = os.environ.get("K10_AFTER_SNAPSHOT_HOOK")
            if hook:
                subprocess.run(hook, shell=True, check=False, stdin=subprocess.DEVNULL)
            if image is None:
                graph = export_graph(driver, partial / GRAPH_FILE)
                consistency = check_consistency(partial / SQLITE_FILE, driver)
                after = inspect_graph(driver)
                if graph["digest"] != before["digest"] or after["digest"] != before["digest"]:
                    raise Failed("Neo4j changed during the backup (a writer bypassed the course write locks); "
                                 "nothing is kept, stop API and worker and re-run")
            else:
                consistency = check_consistency(partial / SQLITE_FILE, driver)
                admin_dump(args.neo4j_container, image, partial / "neo4j", driver, args.neo4j_wait)
                graph = inspect_graph(driver)                                 # G2 after the restart
                if graph["digest"] != before["digest"]:
                    raise Failed("Neo4j changed during the backup (a writer bypassed the course write locks); "
                                 "nothing is kept, stop API and worker and re-run")
            recheck = partial / ".recheck.db"                                 # S3
            snapshot_sqlite(path, recheck, holder)
            first, second = inspect_sqlite(partial / SQLITE_FILE), inspect_sqlite(recheck)
            recheck.unlink()
            changed = sorted(t for t in set(first["tables"]) | set(second["tables"])
                             if first["tables"].get(t) != second["tables"].get(t))
            if changed or first["schema_sha256"] != second["schema_sha256"]:
                raise Failed(f"SQLite changed during the backup (tables: {', '.join(changed) or 'schema'}); "
                             "nothing is kept, stop API and worker and re-run")
            assert_fence_held(url, holder, locks)

            inspection = {"sqlite": first, "neo4j": graph, "consistency": consistency}
            blocking, warnings = verdict(inspection)
            if blocking and not args.allow_inconsistent:
                raise Failed("the stores are not consistent, refusing to keep this backup:\n  - "
                             + "\n  - ".join(blocking))
            warnings = blocking + warnings
            files = {SQLITE_FILE: file_sha256(partial / SQLITE_FILE)}
            data_file = GRAPH_FILE if image is None else DUMP_FILE
            files[data_file] = file_sha256(partial / data_file)
            manifest = {
                "format": FORMAT, "backup_id": backup_id, "created_at": stamp.isoformat(),
                "neo4j_mode": "bolt" if image is None else "admin",
                "source": {"sqlite": str(path), "neo4j_uri": uri, "neo4j_container": args.neo4j_container,
                           "neo4j_image": image},
                "fence": {"courses_locked": len(locks), "holder": holder},
                "files": files, "inspection": inspection, "warnings": warnings,
            }
            (partial / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=1),
                                                   encoding="utf-8")
            os.chmod(partial / "manifest.json", 0o600)
            os.chmod(partial, 0o700)
            partial.rename(final)
        except BaseException:
            import shutil

            shutil.rmtree(partial, ignore_errors=True)
            raise
    for warning in warnings:
        say(f"warning: {warning}")
    pointers = [p for p in inspection["sqlite"]["pointers"] if p["published_version_id"]]
    say(f"backup {backup_id}: {len(inspection['sqlite']['tables'])} SQLite tables, "
        f"{graph['nodes']} nodes / {graph['relationships']} relationships, {len(pointers)} published course(s)")
    print(final)


def main(argv):
    parser = argparse.ArgumentParser(prog="backup-demo.sh", description="K10 consistent SQLite + Neo4j backup")
    parser.add_argument("--out", default="backups/k10", help="parent directory of the backup (default backups/k10)")
    parser.add_argument("--neo4j-uri", help="Bolt URI (default NEO4J_URI)")
    parser.add_argument("--neo4j-container", help="dump with neo4j-admin from this Docker container (stops it)")
    parser.add_argument("--neo4j-wait", type=int, default=180, help="seconds to wait for Neo4j after a restart")
    parser.add_argument("--lock-seconds", type=int, default=600, help="course write lock lease (renewed)")
    parser.add_argument("--allow-inconsistent", action="store_true",
                        help="keep the backup even if the pointer check fails (safety copies before a restore)")
    parser.add_argument("--inspect", action="store_true", help="print the inspection of --sqlite and --neo4j-uri")
    parser.add_argument("--sqlite", help="SQLite file for --inspect")
    parser.add_argument("--export-graph", metavar="FILE", help="only export the graph of --neo4j-uri to FILE")
    args = parser.parse_args(argv)
    os.umask(0o077)
    try:
        if args.inspect:
            if not args.sqlite or not args.neo4j_uri:
                raise Refused("--inspect needs --sqlite and --neo4j-uri")
            path = Path(args.sqlite)
            if not path.is_file():
                raise Refused(f"{path} does not exist")
            with driver_for(args.neo4j_uri) as driver:
                result = {"sqlite": inspect_sqlite(path), "neo4j": inspect_graph(driver),
                          "consistency": check_consistency(path, driver)}
            print(json.dumps(result, ensure_ascii=False))
        elif args.export_graph:
            if not args.neo4j_uri:
                raise Refused("--export-graph needs --neo4j-uri")
            target = Path(args.export_graph)
            if target.exists():
                raise Refused(f"{target} already exists")
            target.parent.mkdir(parents=True, exist_ok=True)
            with driver_for(args.neo4j_uri) as driver:
                print(json.dumps(export_graph(driver, target), ensure_ascii=False))
        else:
            run_backup(args)
    except Refused as exc:
        say(f"refused: {exc}")
        return 2
    except Failed as exc:
        say(f"failed: {exc}")
        return 1
    except Exception as exc:  # driver or SQLite errors: never keep a half backup, never print secrets
        say(f"failed: {type(exc).__name__}: {str(exc)[:300]}")
        return 1
    return 0


sys.exit(main(sys.argv[1:]))
PY
