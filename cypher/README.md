# Cypher Queries

Queries targeting CQ1 and CQ5. Scripts arriving April 2026.

---

## Cycle 1 Scope

| CQ   | Question                                                     | Method                      |
| ---- | ------------------------------------------------------------ | --------------------------- |
| CQ1  | Who are the structurally indispensable donors — those whose removal most fragments the network? | Betweenness Centrality      |
| CQ5  | Which candidates have concentrated single-community funding versus genuinely diversified structural support? | Louvain Community Detection |

CQ2, CQ3, and CQ4 queries are deferred to Cycle 2.

---

## CQ1 — Betweenness Centrality

Betweenness centrality is computed in Python (NetworkX) during ETL and written as `betweenness_score` on each `:Donor` node. These queries read from that pre-computed property.

```cypher
// Top 25 structurally indispensable donors
MATCH (d:Donor)
WHERE d.betweenness_score IS NOT NULL
RETURN d.display_name, d.betweenness_score, d.total_given, d.committee_count
ORDER BY d.betweenness_score DESC
LIMIT 25;
```

```cypher
// How does structural importance compare to raw dollar volume?
// High betweenness + low total_given = bridge donor, not checkbook donor
MATCH (d:Donor)
WHERE d.betweenness_score IS NOT NULL
RETURN d.display_name,
       d.betweenness_score,
       d.total_given,
       d.committee_count,
       d.betweenness_score / (d.total_given + 1) AS structural_efficiency
ORDER BY structural_efficiency DESC
LIMIT 25;
```

---

## CQ5 — Louvain Community Detection

Louvain is run via Neo4j Graph Data Science (GDS) library on AuraDB. Results are written back as `community_id` on `:Donor` nodes.

```cypher
// Project the graph for GDS
CALL gds.graph.project(
  'contribution-graph',
  ['Donor', 'Committee'],
  {
    CONTRIBUTED_TO: {
      orientation: 'UNDIRECTED',
      properties: 'total_amount'
    }
  }
);
```

```cypher
// Run Louvain and write community_id back to nodes
CALL gds.louvain.write('contribution-graph', {
  writeProperty: 'community_id'
})
YIELD communityCount, modularity;
```

```cypher
// Which candidates have concentrated single-community funding?
MATCH (d:Donor)-[:CONTRIBUTED_TO]->(c:Committee)
WHERE c.committee_type CONTAINS 'Candidate'
WITH c, d.community_id AS community, SUM(d.total_given) AS community_total
WITH c, community, community_total, SUM(community_total) OVER () AS grand_total
RETURN c.committee_nm,
       community,
       community_total,
       ROUND(100.0 * community_total / grand_total, 1) AS pct_from_community
ORDER BY c.committee_nm, pct_from_community DESC;
```

---

*Queries are validated against Johnston dataset before Des Moines run.*
