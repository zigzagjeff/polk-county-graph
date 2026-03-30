# Graph Data Model v3

**Project:** polk-county-graph  
**Cycle:** 1 — CQ1 (Betweenness Centrality) + CQ5 (Louvain Community Detection)  
**Source:** PostgreSQL `iowa_campaign_contributions_v2_5` + `iowa_candidate_registrations`  
**Target:** Neo4j AuraDB Free Tier  
**Date:** 2026-03-30

---

## Data Decisions

Three queries against live Postgres data drove this schema. Results below; queries archived in `data-decisions.md`.

**Decision 1 — Committee-as-Donor: Include.**  
21.7% of contributions (61,436 of 283,198) come from committees donating to other committees. 303 unique donor-committees. Too significant to ignore. `:Committee` appears on both sides of `:CONTRIBUTED_TO`.

**Decision 2 — Single `:Donor` label holds.**  
35,769 individual donors produce 209,781 contributions. 1,360 organizations produce 11,976. The split is meaningful but does not warrant separate labels for CQ1/CQ5. A `donor_type` property (`individual` | `organization`) carries the distinction. 5 records classified as `unknown` are excluded.

**Decision 3 — Individual transaction edges.**  
38.7% of donors contribute to the same committee more than once (14,469 of 37,395). Aggregated edges would distort the network structure at this rate. Each contribution becomes its own `:CONTRIBUTED_TO` relationship, keyed on `contribution_id`. This preserves temporal data for Bloom visualization and future-proofs CQ4 (coordination detection) without adding schema complexity.

---

## Schema

### Node Labels

Two node labels. No inheritance, no multi-labeling.

#### `:Donor`

Individuals and organizations who contribute to committees. Committees that donate to other committees are **not** `:Donor` nodes — they use their existing `:Committee` label.

| Property                  | Type    | Source                                                       | Required                    |
| ------------------------- | ------- | ------------------------------------------------------------ | --------------------------- |
| `canonical_donor_id`      | string  | `normalized_donor_key`                                       | yes — uniqueness constraint |
| `display_name`            | string  | Derived: `first_nm + ' ' + last_nm` (individual) or `normalized_organization_nm` (org) | yes                         |
| `donor_type`              | string  | `'individual'` or `'organization'`                           | yes                         |
| `city`                    | string  | `city`                                                       | yes                         |
| `state`                   | string  | `state_cd`                                                   | yes                         |
| `total_contributed`       | float   | Aggregated in ETL                                            | yes                         |
| `committee_count`         | integer | Count of distinct recipient committees                       | yes                         |
| `first_contribution_date` | date    | `MIN(date)`                                                  | yes                         |
| `last_contribution_date`  | date    | `MAX(date)`                                                  | yes                         |
| `betweenness_centrality`  | float   | NetworkX computation (CQ1)                                   | yes                         |
| `louvain_community`       | integer | NetworkX computation (CQ5)                                   | yes                         |

**Identity rule:** Keyed on `normalized_donor_key`. Records where `normalized_donor_key` is null or bare pipe (`'|'`) are excluded.

#### `:Committee`

Recipient committees — and donor committees when `contr_committee_cd` is populated. A committee may appear as both donor and recipient.

| Property            | Type   | Source                                                 | Required                             |
| ------------------- | ------ | ------------------------------------------------------ | ------------------------------------ |
| `committee_cd`      | string | `committee_cd` or `contr_committee_cd`                 | yes — uniqueness constraint          |
| `committee_nm`      | string | `normalized_committee_nm` or registration lookup       | yes                                  |
| `committee_type`    | string | `committee_type`                                       | no                                   |
| `candidate_name`    | string | `candidate_name_standardized` (from registration join) | no — null for PACs, party committees |
| `office_sought`     | string | `office_sought`                                        | no                                   |
| `party_affiliation` | string | `party_affiliation`                                    | no                                   |

**Identity rule:** Keyed on `committee_cd`. Donor-committees are keyed on `contr_committee_cd` and resolved against the `iowa_candidate_registrations` table for name and metadata. If no registration match exists, `committee_nm` falls back to `organization_nm` from the contribution record or the raw `contr_committee_cd` value.

---

### Relationship Types

One relationship type, two source patterns.

#### `:CONTRIBUTED_TO`

Each contribution record produces one relationship. No aggregation at the graph layer.

**Pattern 1 — Donor to Committee** (78.3% of contributions):

```
(:Donor)-[:CONTRIBUTED_TO]->(:Committee)
```

**Pattern 2 — Committee to Committee** (21.7% of contributions):

```
(:Committee)-[:CONTRIBUTED_TO]->(:Committee)
```

| Property           | Type    | Source             | Required              |
| ------------------ | ------- | ------------------ | --------------------- |
| `contribution_id`  | integer | `contribution_id`  | yes — edge identifier |
| `amount`           | float   | `amount`           | yes                   |
| `date`             | date    | `date`             | yes                   |
| `transaction_type` | string  | `transaction_type` | no                    |

**Routing logic in ETL:** If `contr_committee_cd IS NOT NULL`, the source node is `(:Committee {committee_cd: contr_committee_cd})`. Otherwise, the source node is `(:Donor {canonical_donor_id: normalized_donor_key})`.

---

## Computed Properties

Both algorithms run in the ETL transformation layer (NetworkX) and are written to node properties before loading to Neo4j. AuraDB Free Tier does not include the Graph Data Science library.

### CQ1: Betweenness Centrality

**Algorithm:** `networkx.betweenness_centrality` on the undirected projection of the full bipartite network (donors + committees as nodes, contributions as edges).

**Scope:** Computed for all nodes in the projected graph. Written to `:Donor` nodes as `betweenness_centrality`. Committee betweenness values are computed but not written in Cycle 1.

**NetworkX graph construction:** For betweenness computation, edges are aggregated to one edge per donor-committee pair (or committee-committee pair). The Neo4j graph retains individual transaction edges — these are different representations for different purposes.

**Interpretation:** High betweenness centrality identifies donors whose removal would most fragment the contribution network — structurally indispensable brokers, not necessarily the largest dollar contributors.

### CQ5: Louvain Community Detection

**Algorithm:** `networkx.community.louvain_communities` on the donor unipartite projection.

**Projection:** Two donors share an edge in the projection if they both contribute to at least one common committee. Edge weight = count of shared committees. This produces donor clusters that reflect shared funding patterns.

**Scope:** Written to `:Donor` nodes as `louvain_community` (integer community identifier).

**Interpretation:** For each candidate's committee, examine the community distribution of contributing donors. Concentrated single-community funding signals structural vulnerability to exit. Diversified multi-community funding signals resilient support.

---

## Constraints and Indexes

Run before any data load. Neo4j 5.x syntax.

```cypher
-- Uniqueness constraints (also serve as implicit indexes)
CREATE CONSTRAINT donor_id_unique IF NOT EXISTS
  FOR (d:Donor) REQUIRE d.canonical_donor_id IS UNIQUE;

CREATE CONSTRAINT committee_cd_unique IF NOT EXISTS
  FOR (c:Committee) REQUIRE c.committee_cd IS UNIQUE;

-- Performance indexes
CREATE INDEX donor_betweenness IF NOT EXISTS
  FOR (d:Donor) ON (d.betweenness_centrality);

CREATE INDEX donor_community IF NOT EXISTS
  FOR (d:Donor) ON (d.louvain_community);

CREATE INDEX donor_type IF NOT EXISTS
  FOR (d:Donor) ON (d.donor_type);

-- Full-text indexes for Bloom search
CREATE FULLTEXT INDEX donor_name_search IF NOT EXISTS
  FOR (d:Donor) ON EACH [d.display_name];

CREATE FULLTEXT INDEX committee_name_search IF NOT EXISTS
  FOR (c:Committee) ON EACH [c.committee_nm];
```

---

## ETL Filter

All queries against the source table use this filter:

```sql
WHERE city = %(city)s
  AND state_cd = 'IA'
  AND data_quality_score >= 80
  AND duplicate_confidence_score < 50
```

Records excluded: `normalized_donor_key IS NULL`, `normalized_donor_key = '|'`, and the 5 records with no determinable donor type.

---

## Load Strategy

Direct batch loading via the Neo4j Python driver. MERGE, never CREATE. Batch size: 500 rows.

**Load order matters:**

1. `:Committee` nodes — all recipient committees, then donor-only committees
2. `:Donor` nodes — with computed betweenness and community properties
3. `:CONTRIBUTED_TO` relationships — Pattern 1 (Donor→Committee), then Pattern 2 (Committee→Committee)

MERGE requires constraints to exist before the first write.

---

## Scope Boundaries

**In Cycle 1:**

- `:Donor` and `:Committee` nodes
- `:CONTRIBUTED_TO` relationships (both patterns)
- Betweenness centrality and Louvain community as computed properties
- Johnston development → Des Moines portfolio release

**Deferred to Cycle 2:**

- `:Candidate` as a separate node (currently properties on `:Committee`)
- `:Office` and `:City` as separate nodes
- `:REPRESENTS` relationship (Committee→Candidate)
- Household deduplication (`usaddress` + Levenshtein ≤ 2)
- Voter file enrichment
- CQ3 (shared-committee projection), CQ4 (coordination detection)
- `campaign_finance_classification = 'STANDARD'` filter evaluation

---

## Schema Versioning

| Version | Date       | Changes                                                      |
| ------- | ---------- | ------------------------------------------------------------ |
| v1      | —          | Initial ontology                                             |
| v2      | —          | Gemini peer review integration                               |
| v3      | 2026-03-30 | Data-driven rebuild: committee-as-donor inclusion, individual transaction edges, single Donor label confirmed, Candidate/Office/City deferred, computed properties defined |
