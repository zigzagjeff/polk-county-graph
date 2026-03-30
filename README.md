# polk-county-graph

# Polk County Political Contribution Graph

> **391,881 contributions. 54,059 donors. 2,764 committees. 2003–2025.**  
> A Neo4j property graph that reveals the structural architecture of political money in the Des Moines metropolitan area — not who wrote the biggest checks, but who holds the network together.

Built on public data from the Iowa Ethics and Campaign Disclosure Board.  
A [Jeffrey Long](https://jeffreylong.net) portfolio project.

---

## What This Graph Answers

Standard campaign finance analysis counts dollars. This graph asks structural questions that relational databases cannot answer.

| CQ   | Question                                                     | Method                      | Status      |
| ---- | ------------------------------------------------------------ | --------------------------- | ----------- |
| CQ1  | Who are the structurally indispensable donors — those whose removal most fragments the network? | Betweenness Centrality      | **Cycle 1** |
| CQ5  | Which candidates have concentrated single-community funding (vulnerable to exit) versus genuinely diversified structural support? | Louvain Community Detection | **Cycle 1** |

Both algorithms are computed in the ETL transformation layer using NetworkX and written back as node properties before loading to Neo4j.

---

## Stack

![Neo4j](https://img.shields.io/badge/Neo4j-Graph_Database-blue)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-Source_Data-blue)
![Python](https://img.shields.io/badge/Python-ETL-blue)

- **Source:** PostgreSQL — Iowa ECDB public contribution data
- **Graph:** Neo4j AuraDB — Labeled Property Graph
- **ETL:** Python — extract, transform, load pipeline with NetworkX graph computation
- **Analysis:** Cypher queries targeting CQ1 and CQ5

---

## Repository Structure

```
polk-county-graph/
├── graph-data-model/
│   └── graph-data-model-v3.md   ← Node labels, relationship types, property schemas
├── etl/
│   ├── SCHEMA.md                ← Postgres source schema + ETL query skeleton
│   └── README.md                ← ETL pipeline documentation
├── cypher/
│   └── README.md                ← CQ1 and CQ5 query documentation
└── README.md
```

---

## Graph Data Model

The [`graph-data-model/`](./graph-data-model/) directory defines the property graph schema governing this implementation — node labels, relationship types, property definitions, and Neo4j constraints.

The Cycle 1 schema is intentionally minimal:

```
(:Donor)-[:CONTRIBUTED_TO {amount, date, contribution_id}]->(:Committee)
```

Computed properties written to `:Donor` nodes at load time:

- `betweenness_centrality` — structural indispensability score (CQ1)
- `louvain_community` — community membership identifier (CQ5)

---

## Build Strategy

**Cycle 1** targets Johnston, Iowa (33,275 contributions, 4,461 donors) as the development dataset before expanding to Des Moines (249,923 contributions, 33,258 donors) for the portfolio release.

| Phase             | Dataset    | Goal                                                         |
| ----------------- | ---------- | ------------------------------------------------------------ |
| Development       | Johnston   | Validate ETL pipeline, debug graph structure, confirm CQ1/CQ5 queries |
| Portfolio release | Des Moines | Full structural analysis, Bloom visualization                |

---

## Status

**Cycle 1**

- [x] Graph data model v3 complete
- [x] Postgres schema documented (`etl/SCHEMA.md`)
- [ ] ETL pipeline (Postgres → Neo4j) — Johnston
- [ ] CQ1: Betweenness Centrality
- [ ] CQ5: Louvain Community Detection
- [ ] Graph validation on Johnston dataset
- [ ] Portfolio release on Des Moines dataset

---

## About

This project is part of JL Intelligence's applied graph intelligence practice for Iowa political campaigns and organizations.  
Follow the build: [Substack](https://beingfuturepresent.com)
