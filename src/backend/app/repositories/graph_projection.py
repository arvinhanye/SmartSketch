"""Read visible draft facts and materialize a new, write-once physical generation."""
from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
import hashlib
import json

from app.repositories.graph_relations import lock_draft
from app.repositories.neo4j import GraphScope, GraphScopeError

KINDS = ("CONTAINS", "PREREQUISITE", "RELATED_TO", "EXAMPLE_OF")


def _visible(var):
    return f"(coalesce({var}.contrib_manual,false) OR any(t IN coalesce({var}.contrib_tasks,[]) WHERE t IN $effective_task_ids))"


_NODES = f"""// fusion:nodes
MATCH (n:KnowledgePoint {{course_id:$course_id, version_id:$version_id}})
WHERE {_visible('n')} RETURN properties(n) AS p ORDER BY n.kp_id"""
_CHAPTERS = f"""// fusion:chapters
MATCH (n:Chapter {{course_id:$course_id, version_id:$version_id}})
WHERE {_visible('n')} RETURN properties(n) AS p ORDER BY n.chapter_id"""
_EDGES = f"""// fusion:edges
MATCH (a:KnowledgePoint {{course_id:$course_id, version_id:$version_id}})
 -[r {{course_id:$course_id, version_id:$version_id}}]->
 (b:KnowledgePoint {{course_id:$course_id, version_id:$version_id}})
WHERE type(r) IN $kinds AND {_visible('a')} AND {_visible('b')} AND {_visible('r')}
RETURN type(r) AS type,a.kp_id AS from_id,b.kp_id AS to_id,properties(r) AS p ORDER BY r.rel_id"""
_EVIDENCE = f"""// fusion:evidence
MATCH (n:KnowledgePoint {{course_id:$course_id, version_id:$version_id}})-[e:EVIDENCED_BY]->
 (c:Chunk {{course_id:$course_id}})
WHERE {_visible('n')} AND (e.task_id IS NULL OR e.task_id IN $effective_task_ids)
RETURN n.kp_id AS kp_id,c.chunk_id AS chunk_id,c.document_id AS document_id,
 c.revision_id AS revision_id,properties(e) AS props"""


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _props(p):
    return {k: v for k, v in p.items() if k != "version_id"}


def read_snapshot(repo, scope: GraphScope) -> dict:
    if scope.version_id != "draft": raise GraphScopeError("fusion requires a logical draft")
    nodes = [_props(r["p"]) for r in repo.read(_NODES, scope, reader="worker")]
    chapters = [_props(r["p"]) for r in repo.read(_CHAPTERS, scope, reader="worker")]
    edges = [{**r, "p": _props(r["p"])} for r in repo.read(_EDGES, scope, reader="worker", parameters={"kinds": list(KINDS)})]
    evidence = repo.read(_EVIDENCE, scope, reader="worker")
    return dict(course_id=scope.course_id, nodes=nodes, chapters=chapters, edges=edges,
                evidence=sorted(evidence, key=_json))


_RECEIPT = """MATCH (p:FusionProjection {course_id:$course_id,version_id:$version_id})
WHERE $effective_task_ids IS NOT NULL RETURN p.digest AS digest"""
_RECEIPT_WRITE = """CREATE (p:FusionProjection {course_id:$course_id,version_id:$version_id,digest:$digest})
RETURN size($effective_task_ids) AS visible_tasks"""
_NODE_WRITE = """UNWIND $rows AS row
CREATE (n:KnowledgePoint) SET n=row,n.course_id=$course_id,n.version_id=$version_id
RETURN count(n) AS count,size($effective_task_ids) AS visible_tasks"""
_CHAPTER_WRITE = """UNWIND $rows AS row
CREATE (n:Chapter) SET n=row,n.course_id=$course_id,n.version_id=$version_id
RETURN count(n) AS count,size($effective_task_ids) AS visible_tasks"""
_EVIDENCE_WRITE = """UNWIND $rows AS row
MATCH (n:KnowledgePoint {course_id:$course_id,version_id:$version_id,kp_id:row.kp_id})
MERGE (c:Chunk {course_id:$course_id,chunk_id:row.chunk_id})
ON CREATE SET c.document_id=row.document_id,c.revision_id=row.revision_id
CREATE (n)-[e:EVIDENCED_BY]->(c) SET e=row.props
RETURN count(e) AS count,size($effective_task_ids) AS visible_tasks"""
_EDGE_WRITE = {kind: f"""UNWIND $rows AS row
MATCH (a:KnowledgePoint {{course_id:$course_id,version_id:$version_id,kp_id:row.from_id}})
MATCH (b:KnowledgePoint {{course_id:$course_id,version_id:$version_id,kp_id:row.to_id}})
CREATE (a)-[r:{kind}]->(b) SET r=row.p,r.course_id=$course_id,r.version_id=$version_id
CREATE (i:RelationIdentity {{course_id:$course_id,version_id:$version_id,rel_id:row.p.rel_id,
 type:'{kind}',from_id:row.from_id,to_id:row.to_id}})
RETURN count(r) AS count,size($effective_task_ids) AS visible_tasks""" for kind in KINDS}


def write_snapshot(tx, snapshot: Mapping) -> None:
    scope = tx.scope
    if scope.version_id != "draft" or scope.storage_version_id is None:
        raise GraphScopeError("projection writes require a new isolated generation")
    data = deepcopy(dict(snapshot))
    if data.get("course_id") != scope.course_id:
        raise ValueError("projection outside course")
    ids = {n["kp_id"] for n in data["nodes"]}
    if len(ids) != len(data["nodes"]): raise ValueError("duplicate projection node")
    if any(n.get("course_id") != scope.course_id for n in [*data["nodes"], *data["chapters"]]):
        raise ValueError("cross-course projection node")
    if any(e["type"] not in KINDS or e["from_id"] not in ids or e["to_id"] not in ids
           or e["p"].get("course_id") != scope.course_id for e in data["edges"]):
        raise ValueError("invalid projection relation")
    if any(e["kp_id"] not in ids for e in data["evidence"]): raise ValueError("invalid evidence node")
    digest = hashlib.sha256(_json(data).encode()).hexdigest()
    lock_draft(tx)
    existing = tx.run(_RECEIPT)
    if existing:
        if len(existing) != 1 or existing[0]["digest"] != digest:
            raise ValueError("projection identity reused with different content")
        return
    for query, rows in ((_NODE_WRITE, data["nodes"]), (_CHAPTER_WRITE, data["chapters"]),
                        (_EVIDENCE_WRITE, data["evidence"])):
        for offset in range(0, len(rows), 200): tx.run(query, {"rows": rows[offset:offset+200]})
    for kind in KINDS:
        rows = [e for e in data["edges"] if e["type"] == kind]
        for offset in range(0, len(rows), 200): tx.run(_EDGE_WRITE[kind], {"rows": rows[offset:offset+200]})
    tx.run(_RECEIPT_WRITE, {"digest": digest})
