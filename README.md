# polk-county-graph

# Polk County Political Contribution Graph

> **391,881 contributions. 54,059 donors. 2,764 committees. 2003–2025.**  
> A Neo4j knowledge graph that reveals the structural architecture of political money in the Des Moines metropolitan area — not who wrote the biggest checks, but who holds the network together.

Built on public data from the Iowa Ethics and Campaign Disclosure Board.  
A [Jeffrey Long](https://jeffreylong.net) portfolio project.

---

## What This Graph Answers

Standard campaign finance analysis counts dollars. This graph asks structural questions.

| CQ   | Question                                                     | Method                              | Status      |
| ---- | ------------------------------------------------------------ | ----------------------------------- | ----------- |
| CQ1  | Who are the structurally indispensable donors — those whose removal most fragments the network? | Betweenness Centrality              | **Cycle 1** |
| CQ2  | Where does apparent donor diversity collapse into single-household political actors? | Address Deduplication + Node Merge  | Cycle 2     |
| CQ3  | Which organizations fund both parties — and are their recipient legislators structurally dependent on that bipartisan money? | Community Detection + Edge Analysis | Cycle 2     |
| CQ4  | Can the graph surface coordinated giving events, and what do their temporal patterns reveal about legislative influence operations? | Temporal Pattern Detection          | Cycle 2     |
| CQ5  | Which candidates have concentrated single-community funding (vulnerable to exit) versus genuinely diversified structural support? | Louvain Community Detection         | **Cycle 1** |

---

## Stack

![Neo4j](https://img.shields.io/badge/Neo4j-Graph_Database-blue)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-Source_Data-blue)
![Python](https://img.shields.io/badge/Python-ETL-blue)

- **Source:** PostgreSQL — Iowa ECDB public contribution data
- **Graph:** Neo4j — Labeled Property Graph model
- **ETL:** Python, built with [Marcus](https://github.com/zigzagjeff/AI-data-engineer) — an expert data engineering AI persona
- **Analysis:** Cypher queries targeting CQ1 and CQ5

---

## Repository Structure

```
polk-county-graph/
├── ontology/
│   └── ontology-v3.md       ← Domain taxonomy, formal ontology, LPG schema
├── etl/
│   ├── SCHEMA.md            ← Postgres source schema + ETL query skeleton
│   └── README.md            ← ETL pipeline (scripts arriving April 2026)
├── cypher/
│   └── README.md            ← CQ1 and CQ5 queries (arriving April 2026)
└── README.md
```

---

## Ontology

The [`ontology/`](./ontology/) directory contains the formal knowledge structure governing the graph — node labels, relationship types, property schemas, and the logical axioms that prevent structurally incoherent data from entering Neo4j.

Key design decisions documented there:

- Why `CoordinatedGivingEvent` is a hub node rather than O(N²) co-contributor edges
- Why `Household` is an analytical aggregate, not a `PoliticalActor`
- Why `ContributionEvent` lives on the edge, not as a node

The ontology is scoped to all five CQs. Cycle 1 implements the subset required for CQ1 and CQ5 only.

---

## Build Strategy

**Cycle 1** targets Johnston, Iowa (33,275 contributions, 4,461 donors) as the development dataset before expanding to Des Moines (249,923 contributions, 33,258 donors) for the portfolio release. This allows ETL validation and graph debugging at a scale that keeps iteration fast.

| Phase              | Dataset    | Goal                                                         |
| ------------------ | ---------- | ------------------------------------------------------------ |
| Development        | Johnston   | Validate ETL pipeline, debug graph structure, confirm CQ1/CQ5 queries |
| Portfolio release  | Des Moines | Full structural analysis, Bloom visualization                |
| Cycle 2 (deferred) | Des Moines | CQ2 household deduplication, CQ3 partisan analysis, CQ4 coordination detection |

---

## Status

**Cycle 1 — March–April 2026**

- [x] Ontology v3 complete
- [x] Postgres schema documented (`etl/SCHEMA.md`)
- [ ] ETL pipeline (Postgres → Neo4j) — Johnston
- [ ] CQ1: Betweenness Centrality queries
- [ ] CQ5: Louvain Community Detection queries
- [ ] Graph validation on Johnston dataset
- [ ] Portfolio release on Des Moines dataset

---

## About

This project is part of JL Intelligence's applied graph intelligence practice for Iowa political campaigns and organizations.  
Follow the build: [Substack](https://beingfuturepresent.com)
