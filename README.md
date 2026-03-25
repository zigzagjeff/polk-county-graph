# polk-county-graph
# Polk County Political Contribution Graph

> **391,881 contributions. 54,059 donors. 2,764 committees. 2003–2025.**  
> A Neo4j knowledge graph that reveals the structural architecture of political money in the Des Moines metropolitan area — not who wrote the biggest checks, but who holds the network together.

Built on public data from the Iowa Ethics and Campaign Disclosure Board.  
A [Jeffrey Long](https://jeffreylong.net) portfolio project.

---

## What This Graph Answers

Standard campaign finance analysis counts dollars. This graph asks structural questions.

| CQ | Question | Method |
|----|----------|--------|
| CQ1 | Who are the structurally indispensable donors — those whose removal most fragments the network? | Betweenness Centrality |
| CQ2 | Where does apparent donor diversity collapse into single-household political actors? | Address Deduplication + Node Merge |
| CQ3 | Which organizations fund both parties — and are their recipient legislators structurally dependent on that bipartisan money? | Community Detection + Edge Analysis |
| CQ4 | Can the graph surface coordinated giving events, and what do their temporal patterns reveal about legislative influence operations? | Temporal Pattern Detection |
| CQ5 | Which candidates have concentrated single-community funding (vulnerable to exit) versus genuinely diversified structural support? | Louvain Community Detection |

---

## Stack

![Neo4j](https://img.shields.io/badge/Neo4j-Graph_Database-blue)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-Source_Data-blue)
![Python](https://img.shields.io/badge/Python-ETL-blue)

- **Source:** PostgreSQL — Iowa ECDB public contribution data
- **Graph:** Neo4j — Labeled Property Graph model
- **ETL:** Python, built with [Marcus](https://github.com/zigzagjeff/AI-data-engineer) — an expert data engineering AI persona
- **Analysis:** Cypher queries targeting five competency questions

---

## Repository Structure

```
polk-county-graph/
├── ontology/
│   └── ontology-v3.md       ← Domain taxonomy, formal ontology, LPG schema
├── etl/
│   └── README.md            ← ETL pipeline (scripts arriving April 2026)
├── cypher/
│   └── README.md            ← CQ queries (arriving April 2026)
└── README.md
```

---

## Ontology

The [`ontology/`](./ontology/) directory contains the formal knowledge structure governing the graph — node labels, relationship types, property schemas, and the logical axioms that prevent structurally incoherent data from entering Neo4j.

Key design decisions documented there:
- Why `CoordinatedGivingEvent` is a hub node rather than O(N²) co-contributor edges
- Why `Household` is an analytical aggregate, not a `PoliticalActor`
- Why `ContributionEvent` lives on the edge, not as a node

---

## Status

**Cycle 1 — March–April 2026**

- [x] Ontology v3 complete
- [ ] ETL pipeline (Postgres → Neo4j)
- [ ] Cypher queries for CQ1–CQ5
- [ ] Initial graph analysis

---

## About

This project is part of JL Intelligence's applied graph intelligence practice for Iowa political campaigns and organizations.  
Follow the build: [Substack](https://beingfuturepresent.com)
