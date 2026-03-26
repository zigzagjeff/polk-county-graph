# ETL Pipeline

Postgres → NetworkX → Neo4j AuraDB. Scripts arriving April 2026.

---

## Pipeline Overview

```
extract.py    →  Pull from Postgres by city filter → pandas DataFrame
transform.py  →  Build NetworkX DiGraph → compute betweenness centrality → enrich nodes
load.py       →  Write enriched nodes + relationships to AuraDB via Python driver
```

Each script is independent and runnable in isolation. Run them in sequence; debug them separately.

---

## Source Schema

See [`SCHEMA.md`](./SCHEMA.md) for the full Postgres schema, column reference, and the base extraction query.

---

## City Filter Strategy

| Phase             | City       | Contributions | Donors | Purpose                       |
| ----------------- | ---------- | ------------- | ------ | ----------------------------- |
| Development       | Johnston   | 33,275        | 4,461  | ETL validation, bug squashing |
| Portfolio release | Des Moines | 249,923       | 33,258 | Full structural analysis      |

Start with Johnston. Validate the graph structure and CQ1/CQ5 queries before expanding to Des Moines.

---

## AuraDB Constraints

Run against AuraDB **before any data load** (Neo4j 5.x syntax):

```cypher
CREATE CONSTRAINT donor_id_unique FOR (d:Donor) REQUIRE d.canonical_donor_id IS UNIQUE;
CREATE CONSTRAINT committee_cd_unique FOR (c:Committee) REQUIRE c.committee_cd IS UNIQUE;

CREATE INDEX donor_betweenness FOR (d:Donor) ON (d.betweenness_score);
CREATE FULLTEXT INDEX donorSearch FOR (d:Donor) ON EACH [d.display_name];
CREATE FULLTEXT INDEX committeeSearch FOR (c:Committee) ON EACH [c.committee_nm];
```

> Note: The constraint syntax above is Neo4j 5.x (AuraDB current). The ontology document uses 4.x syntax — use the statements here, not there.

---

## Cycle 1 Scope

Cycle 1 ETL supports CQ1 (Betweenness Centrality) and CQ5 (Louvain Community Detection) only.

**In scope:**

- `:Donor` nodes with `betweenness_score` computed in NetworkX
- `:Committee` nodes
- `:CONTRIBUTED_TO` relationships with aggregated properties

**Deferred to Cycle 2:**

- `:Household` nodes and deduplication (CQ2)
- `partisan_lean` inference (CQ3)
- `:CoordinatedEvent` nodes and coordination detection (CQ4)
