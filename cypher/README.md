# Cypher Queries

Queries targeting CQ1 and CQ5, validated against the Johnston development dataset.

---

## Cycle 1 Scope

| CQ   | Question                                                     | Method                      |
| ---- | ------------------------------------------------------------ | --------------------------- |
| CQ1  | Who are the structurally indispensable donors — those whose removal most fragments the network? | Betweenness Centrality      |
| CQ5  | Which candidates have concentrated single-community funding versus genuinely diversified structural support? | Louvain Community Detection |

CQ2, CQ3, and CQ4 queries are deferred to Cycle 2.

---

## Implementation Note: ETL-Layer Computation

Both betweenness centrality (CQ1) and Louvain community detection (CQ5) are computed in Python during ETL using NetworkX — not via Neo4j GDS. This is required because GDS is not available on AuraDB Free Tier.

Results are written as node properties before loading:

| Property            | Node                   | Source                              |
| ------------------- | ---------------------- | ----------------------------------- |
| `betweenness_score` | `:Donor`               | NetworkX `betweenness_centrality()` |
| `community_id`      | `:Donor`, `:Committee` | NetworkX `louvain_communities()`    |

The queries below read directly from these pre-computed properties. No GDS calls are required.

---

## CQ1 — Betweenness Centrality

```cypher
// Top 25 structurally indispensable donors
MATCH (d:Donor)
WHERE d.betweenness_score IS NOT NULL
RETURN d.display_name, d.betweenness_score, d.total_given, d.committee_count
ORDER BY d.betweenness_score DESC
LIMIT 25;
```

```cypher
// Structural efficiency: betweenness relative to dollars spent
// High betweenness + low total_given = bridge donor, not checkbook donor
// This is the graph-native insight relational analysis cannot surface
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

`community_id` is pre-computed in `transform.py` and written to `:Donor` nodes at load time.

```cypher
// Community distribution across donors
MATCH (d:Donor)
WHERE d.community_id IS NOT NULL
RETURN d.community_id AS community,
       count(d)        AS donor_count
ORDER BY donor_count DESC;
```

```cypher
// Which committees draw from a single community vs. many?
// Single-community funding = structurally vulnerable to donor exit
// Multi-community funding = genuinely diversified support base
MATCH (c:Committee)<-[:CONTRIBUTED_TO]-(d:Donor)
WITH c,
     d.community_id                  AS community,
     count(d)                        AS donors_in_community
WITH c,
     count(DISTINCT community)       AS community_count,
     sum(donors_in_community)        AS total_donors,
     max(donors_in_community)        AS top_community_donors
WHERE total_donors >= 10
WITH c,
     community_count,
     total_donors,
     round(toFloat(top_community_donors) / total_donors * 100, 1) AS top_community_pct
RETURN c.committee_nm    AS committee,
       c.committee_type  AS type,
       community_count,
       total_donors,
       top_community_pct
ORDER BY top_community_pct DESC
LIMIT 25;
```

```cypher
// Most structurally diversified committees (lowest top-community concentration)
// These are the committees with genuinely distributed support
MATCH (c:Committee)<-[:CONTRIBUTED_TO]-(d:Donor)
WITH c,
     d.community_id                  AS community,
     count(d)                        AS donors_in_community
WITH c,
     count(DISTINCT community)       AS community_count,
     sum(donors_in_community)        AS total_donors,
     max(donors_in_community)        AS top_community_donors
WHERE total_donors >= 10
WITH c,
     community_count,
     total_donors,
     round(toFloat(top_community_donors) / total_donors * 100, 1) AS top_community_pct
RETURN c.committee_nm    AS committee,
       c.committee_type  AS type,
       community_count,
       total_donors,
       top_community_pct
ORDER BY top_community_pct ASC
LIMIT 25;
```

---

*Queries validated against Johnston dataset (4,461 donors, 1,183 committees, 10,537 relationships) — April 2026.*
