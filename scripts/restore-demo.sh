#!/usr/bin/env bash
# K10：把 scripts/backup-demo.sh 的备份恢复到隔离副本并逐项核对（ADR-054；交接 docs/handoffs/claude-k10.md）。
#
# 用法（在仓库根目录）：
#   scripts/restore-demo.sh --from backups/k10/<备份> --sqlite-target <新文件> --neo4j-uri <空库 Bolt URI>
#       [--neo4j-container NAME]     # admin 备份：用 neo4j-admin load 装入该容器（会停启它）
#       [--report FILE]              # 写出核对报告 JSON
#   目标库凭据：RESTORE_NEO4J_USER / RESTORE_NEO4J_PASSWORD（缺省沿用 NEO4J_USER / NEO4J_PASSWORD）。
#
# 默认绝不覆盖：SQLite 目标必须不存在，Neo4j 目标必须没有节点；Neo4j 目标必须显式给出（不读 NEO4J_URI）。
# 覆盖已有库需同时给 --replace-existing 与 --confirm <备份 ID>，且目标已停机（无活动租约、写锁、未完成尝试）；
# 覆盖前先对目标做一份 K10 备份到 --safety-dir（缺省 <SQLite 目标目录>/k10-safety），
# 撤销覆盖即用同一脚本从该安全副本恢复。
#
# 恢复后用 backup-demo.sh --inspect 重新检查目标，与清单逐项比较：SQLite 逐表内容（含进度表）与结构、
# 发布指针、Neo4j 图摘要与结构、已提交版本按快照复核（引用、向量）、孤儿副本与悬空文本块。
# 退出码：0 已核对一致；1 恢复或核对失败（目标不可用，报告列出差异）；2 拒绝（未改动任何目标）。
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
import sqlite3
import subprocess
import sys
import time
from contextlib import closing
from pathlib import Path

FORMAT = "smartsketch-k10/1"
GRAPH_FORMAT = "smartsketch-k10-graph/1"
BACKUP_SCRIPT = Path(os.environ["K10_ROOT"]) / "scripts" / "backup-demo.sh"
DOCKER = os.environ.get("DOCKER", "docker")
BATCH = 500
_SCHEMA = re.compile(r"^(CREATE\s+(?:[A-Z]+\s+)*?(?:INDEX|CONSTRAINT)\s+`(?:[^`]|``)*`)\s")


class Refused(Exception):
    """Nothing was changed."""


class Failed(Exception):
    """The restore or its verification failed; the target must not be used."""


def say(message):
    print(message, file=sys.stderr, flush=True)


def file_sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def quote_name(name):
    return "`" + str(name).replace("`", "``") + "`"


def target_env():
    env = {k: v for k, v in os.environ.items() if k != "K10_AFTER_SNAPSHOT_HOOK"}
    env["NEO4J_USER"] = os.environ.get("RESTORE_NEO4J_USER") or os.environ.get("NEO4J_USER") or "neo4j"
    env["NEO4J_PASSWORD"] = os.environ.get("RESTORE_NEO4J_PASSWORD") or os.environ.get("NEO4J_PASSWORD") or ""
    return env


def backup_script(*args, sqlite_url=None):
    env = target_env()
    if sqlite_url is not None:
        env["SQLITE_URL"] = sqlite_url
    return subprocess.run(["bash", str(BACKUP_SCRIPT), *args], env=env, capture_output=True, text=True,
                          stdin=subprocess.DEVNULL)


# ---------------------------------------------------------------- the backup set


def load_backup(directory):
    manifest_file = directory / "manifest.json"
    if not manifest_file.is_file():
        raise Refused(f"{directory} has no manifest.json (not a finished K10 backup)")
    try:
        manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
    except ValueError:
        raise Refused("manifest.json is not valid JSON") from None
    if manifest.get("format") != FORMAT or not isinstance(manifest.get("inspection"), dict):
        raise Refused(f"unsupported backup format {manifest.get('format')!r}")
    if manifest.get("neo4j_mode") not in ("bolt", "admin"):
        raise Refused(f"unknown neo4j_mode {manifest.get('neo4j_mode')!r}")
    for name, expected in sorted(manifest.get("files", {}).items()):
        path = directory / name
        if not path.is_file() or file_sha256(path) != expected:
            raise Refused(f"checksum mismatch for {name}: the backup is damaged")
    needed = {"sqlite.db", "graph.jsonl.gz" if manifest["neo4j_mode"] == "bolt" else "neo4j/neo4j.dump"}
    if not needed <= set(manifest.get("files", {})):
        raise Refused(f"backup is incomplete (needs {sorted(needed)})")
    return manifest


# ---------------------------------------------------------------- Neo4j


def driver_for(uri):
    from neo4j import GraphDatabase

    env = target_env()
    return GraphDatabase.driver(uri, auth=(env["NEO4J_USER"], env["NEO4J_PASSWORD"]),
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
                raise Failed(f"Neo4j did not come up within {seconds}s: {type(exc).__name__}") from None
            time.sleep(2)


def node_count(driver):
    return cypher(driver, "MATCH (n) RETURN count(n) AS c")[0]["c"]


def wipe(driver):
    while cypher(driver, "MATCH (n) WITH n LIMIT 5000 DETACH DELETE n RETURN count(*) AS c")[0]["c"]:
        pass
    for row in cypher(driver, "SHOW CONSTRAINTS YIELD name RETURN name"):
        cypher(driver, f"DROP CONSTRAINT {quote_name(row['name'])} IF EXISTS")
    for row in cypher(driver, "SHOW INDEXES YIELD name, type, owningConstraint "
                              "WHERE owningConstraint IS NULL AND type <> 'LOOKUP' RETURN name"):
        cypher(driver, f"DROP INDEX {quote_name(row['name'])} IF EXISTS")


def import_graph(driver, path):
    ids = {}
    pending, key = [], None

    def flush():
        nonlocal pending, key
        if not pending:
            return
        kind, name = key
        if kind == "n":
            labels = "".join(":" + quote_name(label) for label in name)
            rows = cypher(driver, f"UNWIND $rows AS row CREATE (n{labels}) SET n = row.p "
                                  "RETURN row.i AS i, elementId(n) AS e", rows=pending)
            ids.update((r["i"], r["e"]) for r in rows)
            created = len(rows)
        else:
            created = cypher(driver, "UNWIND $rows AS row MATCH (a) WHERE elementId(a) = row.s "
                                     "MATCH (b) WHERE elementId(b) = row.e "
                                     f"CREATE (a)-[r:{quote_name(name)}]->(b) SET r = row.p RETURN count(r) AS c",
                             rows=pending)[0]["c"]
        if created != len(pending):
            raise Failed(f"created {created} of {len(pending)} {kind} records")
        pending, key = [], None

    with gzip.open(path, "rt", encoding="utf-8") as graph:
        header = json.loads(next(graph))
        if header.get("format") != GRAPH_FORMAT:
            raise Failed(f"unsupported graph format {header.get('format')!r}")
        for line in graph:
            record = json.loads(line)
            if record["k"] == "schema":
                match = _SCHEMA.match(record["statement"])
                if not match:
                    raise Failed(f"unexpected schema statement for {record['name']!r}")
                cypher(driver, match.group(1) + " IF NOT EXISTS" + record["statement"][match.end(1):])
                continue
            row_key = ("n", tuple(record["l"])) if record["k"] == "n" else ("r", record["t"])
            if row_key != key or len(pending) >= BATCH:
                flush()  # before mapping ends: relationships follow every node in the file
                key = row_key
            if record["k"] == "n":
                pending.append({"i": record["i"], "p": record["p"]})
            else:
                pending.append({"s": ids[record["s"]], "e": ids[record["e"]], "p": record["p"]})
        flush()
    cypher(driver, "CALL db.awaitIndexes(600)")


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


def container_state(name):
    try:
        result = subprocess.run([DOCKER, "inspect", "--format", "{{.Config.Image}}|{{.State.Running}}", name],
                                capture_output=True, text=True, timeout=60, stdin=subprocess.DEVNULL)
    except (OSError, subprocess.TimeoutExpired):
        result = None
    if result is None or result.returncode:
        raise Refused(f"container {name!r} not found (is Docker running?)")
    image, running = result.stdout.strip().rsplit("|", 1)
    return image, running == "true"


def admin_load(container, image, dump_dir, driver, wait_seconds):
    import shutil
    import tempfile

    # The neo4j user (uid 7474) in the load container must read the dump; the backup stays 0700/0600,
    # so a readable copy is staged under a private (0700) temporary directory and removed afterwards.
    private = Path(tempfile.mkdtemp(prefix="k10-load-"))
    try:
        stage = private / "dump"
        stage.mkdir()
        shutil.copyfile(dump_dir / "neo4j.dump", stage / "neo4j.dump")
        os.chmod(stage, 0o755)
        os.chmod(stage / "neo4j.dump", 0o644)
        say(f"stopping {container} for neo4j-admin database load")
        docker("stop", "-t", "120", container)
        try:
            docker("run", "--rm", "--volumes-from", container, "-v", f"{stage}:/backups:ro", image,
                   "neo4j-admin", "database", "load", "neo4j", "--from-path=/backups",
                   "--overwrite-destination=true")
        finally:
            docker("start", container)
    finally:
        shutil.rmtree(private, ignore_errors=True)
    wait_for_neo4j(driver, wait_seconds)


# ---------------------------------------------------------------- comparison


def compare(expected, actual):
    differences = []
    es, as_ = expected["sqlite"], actual["sqlite"]
    if as_["integrity"] != "ok":
        differences.append(f"sqlite integrity_check: {as_['integrity']}")
    if as_["foreign_key_violations"] != es["foreign_key_violations"]:
        differences.append("sqlite foreign key violations differ")
    if as_["schema_sha256"] != es["schema_sha256"]:
        differences.append("sqlite schema differs")
    for table in sorted(set(es["tables"]) | set(as_["tables"])):
        if es["tables"].get(table) != as_["tables"].get(table):
            differences.append(f"sqlite table {table} differs")
    if as_["pointers"] != es["pointers"]:
        differences.append("sqlite publish pointers differ")
    eg, ag = expected["neo4j"], actual["neo4j"]
    for field in ("digest", "nodes", "relationships", "labels", "types"):
        if eg[field] != ag[field]:
            differences.append(f"neo4j graph {field} differs")
    restored = {(s["kind"], s["name"]): s["statement"] for s in ag["schema"]}
    for item in eg["schema"]:
        if restored.get((item["kind"], item["name"])) != item["statement"]:
            differences.append(f"neo4j schema {item['kind']} {item['name']} missing or different")
    ec, ac = expected["consistency"], actual["consistency"]
    for field in ("verified_versions", "pointer_errors", "orphan_versions", "unknown_courses", "dangling_chunks"):
        if ec[field] != ac[field]:
            differences.append(f"consistency {field} differs (version copies, pointers or references)")
    if sorted(ec["version_errors"]) != sorted(ac["version_errors"]):
        differences.append("consistency version_errors differs")
    return differences


# ---------------------------------------------------------------- the restore


def check_target_offline(url):
    """The same refusals the backup applies (F14 step 1), run through backup-demo.sh on the target."""
    from app.repositories.sqlite import connect

    with connect(url) as db:
        tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        if not {"courses", "course_locks", "graph_versions", "processing_tasks"} <= tables:
            raise Refused("the SQLite target is not a migrated SmartSketch database; refusing to replace it")
        if db.execute("SELECT 1 FROM processing_tasks WHERE lease_expires_at >= unixepoch() LIMIT 1").fetchone():
            raise Refused("active task lease on the target: stop API and worker first")
        if db.execute("SELECT 1 FROM course_locks WHERE expires_at >= unixepoch() LIMIT 1").fetchone():
            raise Refused("active course write lock on the target: stop API and worker first")
        if db.execute("SELECT 1 FROM graph_versions WHERE state IN ('preparing', 'materialized') LIMIT 1").fetchone():
            raise Refused("unfinished publish/rollback attempt on the target: run the G05 compensation first")


def restore(args):
    directory = Path(args.from_dir).resolve()
    manifest = load_backup(directory)
    backup_id = manifest["backup_id"]
    admin = manifest["neo4j_mode"] == "admin"
    if admin and not args.neo4j_container:
        raise Refused("this is a neo4j-admin backup: give --neo4j-container of the isolated target")
    if not admin and args.neo4j_container:
        raise Refused("this is a Bolt backup: it is restored over --neo4j-uri, drop --neo4j-container")
    if args.confirm is not None and not args.replace_existing:
        raise Refused("--confirm only applies together with --replace-existing")
    if args.replace_existing and args.confirm != backup_id:
        raise Refused(f"--replace-existing needs --confirm {backup_id} (the backup id) to overwrite existing data")

    target = Path(args.sqlite_target).resolve()
    target_url = f"sqlite:///{target.as_posix()}"
    sqlite_exists = target.exists() or Path(f"{target}-wal").exists()
    if sqlite_exists and not args.replace_existing:
        raise Refused(f"SQLite target {target} exists; restore into a new file (or --replace-existing "
                      f"--confirm {backup_id})")
    if sqlite_exists:
        check_target_offline(target_url)

    image = None
    if admin:
        image, running = container_state(args.neo4j_container)
    with driver_for(args.neo4j_uri) as driver:
        if admin and not running:
            docker("start", args.neo4j_container)
        wait_for_neo4j(driver, args.neo4j_wait)
        nodes = node_count(driver)
        if nodes and not args.replace_existing:
            raise Refused(f"Neo4j target {args.neo4j_uri} is not empty ({nodes} nodes); restore into an isolated, "
                          f"empty instance (or --replace-existing --confirm {backup_id})")

        safety = None
        if args.replace_existing and (sqlite_exists or nodes):
            safety_root = Path(args.safety_dir or target.parent / "k10-safety").resolve()
            if sqlite_exists:
                result = backup_script("--out", str(safety_root), "--neo4j-uri", args.neo4j_uri,
                                       "--allow-inconsistent", sqlite_url=target_url)
                say(result.stderr.rstrip())
                if result.returncode:
                    raise (Refused if result.returncode == 2 else Failed)(
                        "could not take the safety backup of the target; nothing was replaced")
                safety = result.stdout.strip().splitlines()[-1]
            else:
                safety = str(safety_root / f"graph-before-{backup_id}.jsonl.gz")
                result = backup_script("--export-graph", safety, "--neo4j-uri", args.neo4j_uri)
                if result.returncode:
                    raise Failed(f"could not export the target graph first: {result.stderr.strip()[-300:]}")
            say(f"safety copy of the replaced data: {safety}")

        say(f"restoring {backup_id} ({manifest['neo4j_mode']}) into {args.neo4j_uri} and {target}")
        try:
            if admin:
                admin_load(args.neo4j_container, image, directory / "neo4j", driver, args.neo4j_wait)
            else:
                if args.replace_existing:
                    wipe(driver)
                import_graph(driver, directory / "graph.jsonl.gz")
        except Failed:
            raise
        except Exception as exc:
            raise Failed(f"Neo4j restore stopped ({type(exc).__name__}: {str(exc)[:200]}); the target is "
                         "partially restored, discard it") from None

    target.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(directory / "sqlite.db")) as source, closing(sqlite3.connect(target)) as copy:
        source.backup(copy)
    os.chmod(target, 0o600)

    result = backup_script("--inspect", "--sqlite", str(target), "--neo4j-uri", args.neo4j_uri)
    if result.returncode:
        raise Failed(f"could not inspect the restored copy: {result.stderr.strip()[-300:]}")
    differences = compare(manifest["inspection"], json.loads(result.stdout))
    return {"status": "verified" if not differences else "mismatch", "backup_id": backup_id,
            "neo4j_mode": manifest["neo4j_mode"], "sqlite_target": str(target), "neo4j_uri": args.neo4j_uri,
            "safety_copy": safety, "differences": differences, "warnings": manifest.get("warnings", [])}


def main(argv):
    parser = argparse.ArgumentParser(prog="restore-demo.sh", description="K10 restore drill into an isolated copy")
    parser.add_argument("--from", dest="from_dir", required=True, help="backup directory (with manifest.json)")
    parser.add_argument("--sqlite-target", required=True, help="SQLite file to create (must not exist)")
    parser.add_argument("--neo4j-uri", required=True, help="Bolt URI of the empty, isolated Neo4j target")
    parser.add_argument("--neo4j-container", help="Docker container of that target (neo4j-admin backups)")
    parser.add_argument("--neo4j-wait", type=int, default=180)
    parser.add_argument("--replace-existing", action="store_true", help="allow overwriting existing data")
    parser.add_argument("--confirm", help="the backup id, required with --replace-existing")
    parser.add_argument("--safety-dir", help="where the replaced data is backed up first")
    parser.add_argument("--report", help="write the verification report (JSON) here")
    args = parser.parse_args(argv)
    os.umask(0o077)
    try:
        report = restore(args)
    except Refused as exc:
        say(f"refused: {exc}")
        return 2
    except Failed as exc:
        say(f"failed: {exc}")
        report = {"status": "failed", "differences": [str(exc)]}
        code = 1
    except Exception as exc:
        say(f"failed: {type(exc).__name__}: {str(exc)[:300]}")
        report = {"status": "failed", "differences": [type(exc).__name__]}
        code = 1
    else:
        code = 0 if report["status"] == "verified" else 1
    if args.report:
        Path(args.report).parent.mkdir(parents=True, exist_ok=True)
        Path(args.report).write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    if code == 0:
        say(f"verified: {report['backup_id']} restored and matches its manifest")
        print(json.dumps(report, ensure_ascii=False))
    elif report.get("status") == "mismatch":
        say("mismatch: the restored copy does NOT match the backup; do not use it:\n  - "
            + "\n  - ".join(report["differences"]))
    return code


sys.exit(main(sys.argv[1:]))
PY
