# repositories/

Neo4j 与 SQLite 读写，Cypher 与 SQL 只在这一层。每个查询都必须按 `course_id` 隔离。

不放：产品策略与业务判断（→ `services/`）、HTTP 细节、跨存储事务编排。
