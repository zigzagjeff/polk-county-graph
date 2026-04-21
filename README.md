# Polk County Political Contribution Graph

> **391,881 contributions. 54,059 donors. 2,764 committees. 2003–2025.**  
> A Neo4j property graph that reveals the structural architecture of political money in the Des Moines metropolitan area — not who wrote the biggest checks, but who holds the network together.

Built on public data from the Iowa Ethics and Campaign Disclosure Board.  
A [Jeffrey Long](https://jeffreylong.net) portfolio project.

---

## The Finding

Standard campaign finance analysis ranks donors by dollars. This graph ranks them by structural indispensability — betweenness centrality, the measure of how many paths through the network run through a given node.

The result surfaces a category of donor that dollar-based analysis misses entirely:

| Donor | Betweenness Score | Total Given | Committees |
|---|---|---|---|
| Republican Party of Iowa | 0.0260 | $63,891,249 | 541 |
| **Dolan, MJ** | **0.0252** | **$41,435** | **183** |
| Iowa Democratic Party | 0.0188 | $49,356,831 | 417 |
| **Cacciatore, John** | **0.0164** | **$49,238** | **60** |
| AFSCME Iowa Council 61 | 0.0118 | $4,217,064 | 323 |
| **Maloney, Mary** | **0.0099** | **$5,206** | **38** |

MJ Dolan has nearly identical structural influence to the Republican Party of Iowa while spending 1,500× less money. Maloney and Cacciatore hold significant network positions on budgets under $50K. These are bridge donors — people whose participation connects otherwise-disconnected communities. A relational database cannot find them. A graph can.

---

## What This Graph Answers

| CQ | Question | Method |
|---|---|---|
| CQ1 | Who are the structurally indispensable donors — those whose removal most fragments the network? | Betweenness Centrality |
| CQ5 | Which candidates have concentrated single-community funding (vulnerable to donor exit) versus genuinely diversified support? | Louvain Community Detection |

Both algorithms run in the ETL transformation layer via NetworkX and are written back as node properties before loading to Neo4j — no GDS required.

---

## Community Structure (CQ5)

Louvain community detection found **258 communities** across the Johnston network. The top 5 each contain 3,000–4,800 donors and represent the network's structural backbone. A long tail of 150+ singleton communities captures isolated donors with no cross-committee participation.

| Community | Donors |
|---|---|
| 0 | 4,772 |
| 1 | 4,705 |
| 2 | 4,391 |
| 3 | 4,284 |
| 4 | 3,229 |
| … 253 others | … |

A committee drawing donors exclusively from one community is structurally fragile — its support base exits together. A committee with donors distributed across many communities has genuinely diversified structural support. The Cypher queries in [`cypher/`](./cypher/) surface both patterns.

---

## ETL Pipeline

Three-stage Python pipeline: Postgres → NetworkX → Neo4j AuraDB.

```
extract.py   →   transform.py   →   load.py
Postgres          NetworkX           AuraDB
server-side       DiGraph +          batched MERGE
cursor            betweenness +      committees first,
batched reads     Louvain            then donors,
parquet out       parquet out        then relationships
```

**Scale:** Johnston runs end-to-end in under 5 minutes. Des Moines (249K contributions) is the next target — the pipeline is designed for it. Server-side cursor batching in `extract.py` keeps memory flat regardless of dataset size.

Each script has human-in-the-loop checkpoints before any write operation. No data moves without confirmation.

---

## Stack

- **Source:** PostgreSQL — Iowa ECDB public contribution data (`iowa_campaign_contributions_v2_5`)
- **Transformation:** Python + NetworkX — DiGraph construction, betweenness centrality, Louvain community detection
- **Graph:** Neo4j AuraDB — Labeled Property Graph, MERGE-safe idempotent writes
- **Queries:** Cypher — reads pre-computed properties, no GDS dependency

---

## Repository Structure

```
polk-county-graph/
├── graph-data-model/
│   └── graph-data-model-v3.md   ← Node labels, relationship types, property schemas
├── etl/
│   ├── extract.py               ← Postgres → parquet (server-side cursor, checkpointed)
│   ├── transform.py             ← NetworkX graph + betweenness + Louvain → parquet
│   ├── load.py                  ← AuraDB MERGE writes, batched, checkpointed
│   └── SCHEMA.md                ← Source schema documentation
├── cypher/
│   └── README.md                ← CQ1 and CQ5 query documentation
└── README.md
```

---

## Status

**Cycle 1 — Johnston dataset · complete**

- [x] Graph data model v3
- [x] Postgres source schema documented
- [x] ETL pipeline — extract, transform, load
- [x] CQ1: Betweenness Centrality — validated
- [x] CQ5: Louvain Community Detection — validated
- [x] Graph live in Neo4j AuraDB

**Next:** Des Moines full dataset (249,923 contributions)

---

## About

Built by [Jeffrey Long](https://jeffreylong.net) — AI-augmented data engineering and graph intelligence.  
Follow the work: [Being Future Present](https://beingfuturepresent.com)
