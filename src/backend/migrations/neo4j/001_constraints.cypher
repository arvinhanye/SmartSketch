// F03: Neo4j 5.26 schema. Every statement is independently repeatable.
CREATE CONSTRAINT kp_scope_id IF NOT EXISTS FOR (n:KnowledgePoint) REQUIRE (n.course_id, n.version_id, n.kp_id) IS UNIQUE;
CREATE CONSTRAINT chapter_scope_id IF NOT EXISTS FOR (n:Chapter) REQUIRE (n.course_id, n.version_id, n.chapter_id) IS UNIQUE;
CREATE CONSTRAINT chunk_course_id IF NOT EXISTS FOR (n:Chunk) REQUIRE (n.course_id, n.chunk_id) IS UNIQUE;
// F06 must MERGE this guard in the same transaction as a relation write: Neo4j
// cannot enforce one uniqueness constraint across four relationship types.
CREATE CONSTRAINT relation_identity_scope_id IF NOT EXISTS FOR (n:RelationIdentity) REQUIRE (n.course_id, n.version_id, n.rel_id) IS UNIQUE;
// F06: one guard node per course draft. Every relation write transaction locks it
// first, so reading the graph, checking cycles and committing form one write sequence.
CREATE CONSTRAINT draft_write_guard_scope IF NOT EXISTS FOR (n:DraftWriteGuard) REQUIRE (n.course_id, n.version_id) IS UNIQUE;
CREATE CONSTRAINT contains_scope_id IF NOT EXISTS FOR ()-[r:CONTAINS]-() REQUIRE (r.course_id, r.version_id, r.rel_id) IS UNIQUE;
CREATE CONSTRAINT prerequisite_scope_id IF NOT EXISTS FOR ()-[r:PREREQUISITE]-() REQUIRE (r.course_id, r.version_id, r.rel_id) IS UNIQUE;
CREATE CONSTRAINT related_to_scope_id IF NOT EXISTS FOR ()-[r:RELATED_TO]-() REQUIRE (r.course_id, r.version_id, r.rel_id) IS UNIQUE;
CREATE CONSTRAINT example_of_scope_id IF NOT EXISTS FOR ()-[r:EXAMPLE_OF]-() REQUIRE (r.course_id, r.version_id, r.rel_id) IS UNIQUE;
CREATE INDEX kp_contrib_manual IF NOT EXISTS FOR (n:KnowledgePoint) ON (n.course_id, n.version_id, n.contrib_manual);
CREATE INDEX chapter_contrib_manual IF NOT EXISTS FOR (n:Chapter) ON (n.course_id, n.version_id, n.contrib_manual);
CREATE INDEX chunk_revision IF NOT EXISTS FOR (n:Chunk) ON (n.course_id, n.revision_id);
