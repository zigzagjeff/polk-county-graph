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
| v3      | 2026-03-30 | Data-driven rebuild: committee-as-donor inclusion, individual transaction edges, single Donor label confirmed, Candidate/Office/City deferred, computed properties defined |# Polk County Political Contribution Graph

## Domain Taxonomy, Formal Ontology, and Graph Data Model

**JL Intelligence &nbsp;·&nbsp; v3.0 &nbsp;·&nbsp; March 2026**

> *A Neo4j graph database built on Iowa Ethics and Campaign Disclosure Board public data. 391,881 contributions · 54,059 unique donors · 2,764 recipient committees · Des Moines metro · 2003–2025.*

---

## Table of Contents

1. [Document Purpose](#document-purpose)
2. [Domain Taxonomy](#1-domain-taxonomy)
   - [Entity Classes](#11-entity-classes)
   - [Relational Concepts and Event Classes](#12-relational-concepts-and-event-classes)
   - [Taxonomic Hierarchy Summary](#13-taxonomic-hierarchy-summary)
3. [Formal Ontology](#2-formal-ontology)
   - [Object Properties](#21-object-properties)
   - [Datatype Properties](#22-datatype-properties)
   - [Logical Axioms](#23-logical-axioms)
4. [Labeled Property Graph Model](#3-labeled-property-graph-model)
   - [Node Labels](#31-node-labels)
   - [Relationship Types](#32-relationship-types)
   - [Graph Constraints and Indexes](#33-graph-constraints-and-indexes)
   - [Cardinality and Scale](#34-cardinality-and-scale)
5. [Known Limitations and Scope Boundaries](#4-known-limitations-and-scope-boundaries)
6. [Data Source and Provenance](#data-source-and-provenance)

---

## Document Purpose

This document defines the formal knowledge structure underlying the Polk County Political Contribution Graph. It is organized in three layers of increasing implementation specificity:

- **Domain Taxonomy** — the classification hierarchy of entities and relationships in Iowa campaign finance
- **Formal Ontology** — class definitions, property domains and ranges, and logical axioms governing valid assertions
- **Labeled Property Graph Model** — the concrete Neo4j implementation: node labels, relationship types, and property schemas

### Competency Questions

The ontology is scoped to answer five competency questions (CQs) that define the analytical boundary of this graph:

| CQ      | Question                                                     | Analysis Type                       |
| ------- | ------------------------------------------------------------ | ----------------------------------- |
| **CQ1** | Who are the structurally indispensable donors — not the biggest check writers, but those whose removal most fragments the network? | Betweenness Centrality              |
| **CQ2** | Where does apparent donor diversity collapse into single-household political actors, and what does that reveal about candidate dependency? | Address Deduplication + Node Merge  |
| **CQ3** | Which organizations fund both parties — and are their recipient legislators structurally dependent on that bipartisan money? | Community Detection + Edge Analysis |
| **CQ4** | Can the graph surface coordinated giving events, and what does their temporal pattern reveal about legislative influence operations? | Temporal Pattern Detection          |
| **CQ5** | Which candidates have concentrated single-community funding (vulnerable to exit) versus genuinely diversified structural support? | Louvain Community Detection         |

---

## 1. Domain Taxonomy

*Classification hierarchy for Iowa campaign finance entities and events.*

The taxonomy organizes domain concepts into a hierarchy of increasing specificity. This structure is implementation-agnostic — it applies equally to the LPG model, an RDF triplestore, or a relational schema. Classes marked **(abstract)** have no direct instances; they exist to organize shared properties inherited by subclasses.

### 1.1 Entity Classes

#### `PoliticalActor` *(abstract)*

The root class for any agent that participates in Iowa campaign finance — either as a contributor, recipient, or both. All PoliticalActors are identified by a canonical identifier derived from normalized name and address.

---

#### `Individual` ⊂ `PoliticalActor`

A natural person acting in their own name. Individuals may contribute directly or serve as candidates. Identified by `normalized_donor_key` + address. Subject to household clustering.

---

#### `Organization` ⊂ `PoliticalActor` *(abstract)*

A collective entity acting under an organizational identity. Includes all committee types and corporate donors. Identified by normalized organization name.

---

#### `Committee` ⊂ `Organization` *(abstract)*

A formal committee registered with the Iowa Ethics and Campaign Disclosure Board. Identified by `committee_cd` (unique IECDB identifier). Subclassed by registration type.

**Subclasses:**

| Class                      | Description                                                  |
| -------------------------- | ------------------------------------------------------------ |
| `CandidateCommittee`       | Formed to support a specific candidate. Carries `office_sought` and `district`. May receive from individuals, PACs, and party committees. |
| `PartyCommittee`           | State or county central committees for recognized parties. Operates as both contributor and recipient. Key nodes for partisan flow analysis. |
| `PoliticalActionCommittee` | Registered PAC operating as an intermediary: collecting from members and disbursing to candidate/party committees. The relay node in bundled contribution patterns. May appear as both contributor (via `contr_committee_cd`) and recipient. |

---

#### `CorporateOrAssociationDonor` ⊂ `Organization`

A non-committee organization contributing directly (e.g., employer PAC not registered as a standalone committee). Identified via `organization_nm` field.

---

#### `Household`

An analytical aggregate representing a cluster of `Individual` instances sharing a common residential address and exhibiting name proximity (Levenshtein distance ≤ 2 on `normalized_donor_key`).

The `Household` is **not** itself a `PoliticalActor` — it is a structural container used to resolve apparent donor diversity into actual funding units.

> **Rationale:** Iowa campaign finance reporting accepts name variants as independent filers. The Debra/Deb/Deborah Hansen cluster at 1469 Glen Oaks Dr, West Des Moines — contributing $650K+ to Republican candidates — illustrates a systematic pattern where one funding unit appears as three or more separate donors in raw data. The Household class collapses this for accurate betweenness calculation.

---

### 1.2 Relational Concepts and Event Classes

#### `ContributionEvent` *(Relational Concept — not instantiated as a node)*

A discrete financial transfer from a `PoliticalActor` to a `Committee`, as reported to the IECDB. In the LPG implementation, `ContributionEvent` is **not** modeled as a node — its properties are aggregated onto the `CONTRIBUTED_TO` relationship.

> **Engineer note:** There is no `ContributionEvent` node in Neo4j. The `CONTRIBUTED_TO` edge carries `total_amount`, `transaction_count`, `first_date`, `last_date`, and `max_single_gift` as aggregated properties. Marcus aggregates all transactions per Donor–Committee pair **before** load — not after.

---

#### `CoordinatedGivingEvent` *(instantiated as a node)*

A derived class representing a detected pattern of multiple `PoliticalActors` contributing identical amounts to the same `Committee` on the same date. Unlike `ContributionEvent`, this **is** modeled as a `:CoordinatedEvent` node to support temporal visualization and CQ4 pattern queries.

> **Observed instances:** January 10, 2016 — 11 PACs, $1,000 each, Citizens for Gronstal. January 9, 2011 — 9 PACs, $1,000 each, same recipient. These session-opening tribute patterns repeat across multiple years and legislative leaders of both parties.

---

### 1.3 Taxonomic Hierarchy Summary

| Class                         | Parent                   | Abstract? | Source Identity Field                   |
| ----------------------------- | ------------------------ | --------- | --------------------------------------- |
| `PoliticalActor`              | —                        | Yes       | —                                       |
| `Individual`                  | `PoliticalActor`         | No        | `normalized_donor_key` + address        |
| `Organization`                | `PoliticalActor`         | Yes       | —                                       |
| `Committee`                   | `Organization`           | Yes       | `committee_cd`                          |
| `CandidateCommittee`          | `Committee`              | No        | `committee_cd`                          |
| `PartyCommittee`              | `Committee`              | No        | `committee_cd`                          |
| `PoliticalActionCommittee`    | `Committee`              | No        | `committee_cd`                          |
| `CorporateOrAssociationDonor` | `Organization`           | No        | `normalized_organization_nm`            |
| `Household`                   | *(analytical aggregate)* | No        | address + name cluster                  |
| `ContributionEvent`           | *(relational concept)*   | N/A       | Lives on `CONTRIBUTED_TO` edge          |
| `CoordinatedGivingEvent`      | —                        | No        | `derived: date + committee_cd + amount` |

---

## 2. Formal Ontology

*Class definitions, property semantics, domain/range constraints, and logical axioms.*

This section defines the ontology using OWL-aligned notation. Although the implementation target is a Labeled Property Graph (Neo4j), the ontological rigor defined here constrains what Marcus may assert — preventing structurally incoherent data from entering the graph and ensuring that CQ answers are logically valid, not artifacts of modeling error.

**Notation:** `domain(P)` denotes the class of subjects in property `P` assertions. `range(P)` denotes the class of objects. `⊑` denotes subclass. `⊥` denotes disjoint classes.

---

### 2.1 Object Properties

| Property          | Domain                     | Range                    | Cardinality  | Notes                                                        |
| ----------------- | -------------------------- | ------------------------ | ------------ | ------------------------------------------------------------ |
| `:contributedTo`  | `PoliticalActor`           | `Committee`              | Many-to-many | Core financial flow. PAC may appear as both subject and object (relay pattern). |
| `:disbursedTo`    | `PoliticalActionCommittee` | `Committee`              | Many-to-many | Outbound PAC flow. Distinguishes relay nodes from direct donors. |
| `:memberOf`       | `Individual`               | `Household`              | Many-to-one  | Derived from address + name cluster. Enables household-level betweenness. |
| `:affiliatedWith` | `Individual`               | `CandidateCommittee`     | Many-to-many | For donors who also hold elected office. Enables cross-role analysis. |
| `:represents`     | `Individual`               | `CandidateCommittee`     | Many-to-many | **Ownership/representation.** Links a candidate to their committee. Distinct from `:affiliatedWith` (donor→committee) — this is candidate→own committee. |
| `:participatedIn` | `PoliticalActor`           | `CoordinatedGivingEvent` | Many-to-many | Links donor nodes to detected coordination events. Supports CQ4. |

> **Note on `:coContributorOf`:** A symmetric property linking co-contributors was considered but omitted. In a graph with 391k transactions, materializing direct co-contributor edges creates an O(N²) clique — 11 co-contributors generates 55 edges instead of 11. The `:PARTICIPATED_IN` → `:CoordinatedEvent` hub provides equivalent query capability without the relationship explosion. All co-contributor queries should traverse `(:Donor)-[:PARTICIPATED_IN]->(:CoordinatedEvent)<-[:PARTICIPATED_IN]-(:Donor)`.

---

### 2.2 Datatype Properties

| Property             | Domain                   | Datatype      | Source Field           | Notes                                                        |
| -------------------- | ------------------------ | ------------- | ---------------------- | ------------------------------------------------------------ |
| `:canonicalDonorId`  | `PoliticalActor`         | `xsd:string`  | derived                | Assigned during ETL deduplication. Stable across name variants. |
| `:normalizedKey`     | `PoliticalActor`         | `xsd:string`  | `normalized_donor_key` | IECDB normalized identifier. May be non-unique across household members. |
| `:committeeType`     | `Committee`              | `xsd:string`  | `committee_type`       | IECDB registration category (Iowa PAC, State House, Governor, etc.). |
| `:partisanLean`      | `Committee`              | `xsd:string`  | derived                | `DEMOCRAT` \| `REPUBLICAN` \| `BIPARTISAN` \| `NONPARTISAN` \| `UNKNOWN` |
| `:betweennessScore`  | `PoliticalActor`         | `xsd:decimal` | computed               | Normalized betweenness centrality. Computed in NetworkX, written as node property before AuraDB load. |
| `:householdId`       | `Individual`             | `xsd:string`  | derived                | Links Individual to Household aggregate node.                |
| `:coordinationScore` | `CoordinatedGivingEvent` | `xsd:integer` | computed               | Number of co-contributors. Higher = stronger coordination signal. |
| `:totalGiven`        | `PoliticalActor`         | `xsd:decimal` | aggregated             | Lifetime contribution total within Polk County scope.        |
| `:minorityGivingPct` | `PoliticalActor`         | `xsd:decimal` | computed               | Fraction of partisan giving to minority party. Drives BIPARTISAN threshold logic. |

---

### 2.3 Logical Axioms

#### Disjointness Axioms

The following classes are mutually exclusive. No instance may belong to more than one:

| Axiom                                           | Rationale                                                    |
| ----------------------------------------------- | ------------------------------------------------------------ |
| `Individual ⊥ Organization`                     | A natural person is not a committee or organization in IECDB data. |
| `CandidateCommittee ⊥ PartyCommittee`           | IECDB registration type is mutually exclusive.               |
| `CandidateCommittee ⊥ PoliticalActionCommittee` | IECDB registration type is mutually exclusive.               |
| `PartyCommittee ⊥ PoliticalActionCommittee`     | IECDB registration type is mutually exclusive.               |

---

#### Relay Node Axiom

A `PoliticalActionCommittee` that appears as both a contributor and a recipient is asserted as a relay node:

```
∃x : PoliticalActionCommittee(x) ∧ contributedTo(x, y) ∧ contributedTo(z, x)
  → is_relay_node(x) = true
```

> 443 distinct PAC relay nodes are present in the Polk County slice. These are the most analytically significant nodes for betweenness centrality — they bridge individual donors to candidate committees across partisan lines.
>
> **Implementation timing:** `is_relay_node` is flagged via **post-load Cypher**, not during Marcus ETL. After the initial batch load completes, run:
>
> ```cypher
> MATCH (c:Committee)
> WHERE EXISTS { MATCH (c)-[:CONTRIBUTED_TO]->() }
> SET c.is_relay_node = true
> ```
>
> This is more reliable than ETL detection because it operates on the fully loaded graph state.

---

#### Household Equivalence Axiom

Two `Individual` instances are asserted as members of the same `Household` if and only if:

```
sameAddress(a, b) ∧ levenshtein(normalizedKey(a), normalizedKey(b)) ≤ 2
  → ∃h : Household(h) ∧ memberOf(a, h) ∧ memberOf(b, h)
```

> **Implementation:** Marcus applies this axiom during ETL in two passes:
>
> 1. **Address normalization:** The Python `usaddress` library parses street addresses into structured components (number, name, suffix) and produces a canonical form. This resolves `"123 Main St"` and `"123 Main Street"` to the same canonical address before comparison.
> 2. **Name proximity:** Levenshtein distance ≤ 2 on `normalized_donor_key` at the same canonical address.
>
> The `canonical_donor_id` property is the household-level identifier that collapses variants for betweenness computation.

---

#### Coordination Detection Axiom

A `CoordinatedGivingEvent` is instantiated when 3+ contributors give identical amounts to the same recipient on the same date:

```
∃e1, e2 : ContributionEvent(e1) ∧ ContributionEvent(e2)
  ∧ date(e1) = date(e2)
  ∧ amount(e1) = amount(e2)
  ∧ recipient(e1) = recipient(e2)
  ∧ contributor(e1) ≠ contributor(e2)
  ∧ count({e : same conditions}) ≥ 3
  → CoordinatedGivingEvent(g)
    ∧ participatedIn(contributor(e1), g)
    ∧ participatedIn(contributor(e2), g)
```

> Threshold of 3+ contributors is conservative. The January session-opening clusters reach 11 co-contributors. This axiom instantiates the `:CoordinatedEvent` node in the graph.

---

#### Partisan Lean Inference Axiom

Partisan lean is inferred from committee naming patterns where direct registration data is unavailable:

```
committeeNm(c) MATCHES '(?i)(democrat|hubbell|gronstal|culver)'
  → partisanLean(c) = 'DEMOCRAT'

committeeNm(c) MATCHES '(?i)(republican|reynolds|branstad|iowa gop)'
  → partisanLean(c) = 'REPUBLICAN'

let D = sum of amounts given to DEMOCRAT-lean committees
let R = sum of amounts given to REPUBLICAN-lean committees
let minority = min(D, R),  total = D + R

minority / total ≥ 0.20  →  partisanLean(x) = 'BIPARTISAN'
minority / total < 0.20  →  partisanLean(x) = direction of majority
```

> The 20% threshold is applied to **dollar amounts, not transaction counts**. A donor making 100 small Democratic contributions and one large Republican contribution is classified by the weighted dollar split, not the transaction ratio. This prevents high-frequency small donors from appearing BIPARTISAN based on volume alone.
>
> Example: Credit Union PAC — $58K Republican / $75K Democrat = 44% minority share = **BIPARTISAN**. Coverage is partial; lean is a best-effort inference, not ground truth.

---

## 3. Labeled Property Graph Model

*Neo4j node labels, relationship types, and property schemas.*

All ontological classes from Section 2 map to node labels or relationship types. Data source: `iowa_campaign_contributions_v2_5` (Postgres), Polk County scope (`city IN ['Des Moines', 'West Des Moines']`), `data_quality_score > 3`.

---

### 3.1 Node Labels

#### `:Donor`

Represents a deduplicated political actor — individual or organizational — after household clustering. One `Donor` node per `canonical_donor_id`.

**Label stacking:** Donor nodes carry additional labels reflecting their taxonomic subclass: `:Donor:Individual`, `:Donor:Organization`, `:Donor:PAC`. Individuals who have also registered as candidates additionally carry `:Donor:Individual:Candidate`, enabling efficient self-funding queries without full graph traversal.

| Property                  | Type     | Source                 | Notes                                                        |
| ------------------------- | -------- | ---------------------- | ------------------------------------------------------------ |
| `canonical_donor_id`      | String   | derived (ETL)          | Primary key. Stable across name variants. UUID format.       |
| `normalized_donor_key`    | String[] | `normalized_donor_key` | Array of all key variants collapsed into this node.          |
| `display_name`            | String   | derived                | Best human-readable name from variants.                      |
| `donor_type`              | String   | derived                | `INDIVIDUAL` \| `ORGANIZATION` \| `PAC`                      |
| `partisan_lean`           | String   | inferred               | `DEMOCRAT` \| `REPUBLICAN` \| `BIPARTISAN` \| `NONPARTISAN` \| `UNKNOWN` |
| `total_given`             | Float    | aggregated             | Sum of all amounts in Polk County scope.                     |
| `committee_count`         | Integer  | aggregated             | Distinct recipient committees funded.                        |
| `first_contribution_date` | Date     | aggregated             | Earliest contribution date.                                  |
| `last_contribution_date`  | Date     | aggregated             | Most recent contribution date.                               |
| `betweenness_score`       | Float    | computed (NetworkX)    | Normalized betweenness centrality. Core CQ1 property.        |
| `household_id`            | String   | derived (ETL)          | Links to Household node. Null for non-clustered donors.      |
| `is_relay_pac`            | Boolean  | derived                | True if this donor also appears as a recipient committee.    |
| `is_candidate`            | Boolean  | derived                | True if this Individual has a registration in `iowa_candidate_registrations`. Drives `:Candidate` label. |
| `minority_giving_pct`     | Float    | computed               | Fraction of partisan giving to minority party. Drives BIPARTISAN threshold logic. |

---

#### `:Committee`

Represents a registered recipient committee. May carry additional labels reflecting taxonomic subclass: `:CandidateCommittee`, `:PartyCommittee`, or `:PAC`. Labels are not mutually exclusive in Neo4j — a node may carry `:Committee:PAC` simultaneously.

| Property                  | Type    | Source                    | Notes                                                        |
| ------------------------- | ------- | ------------------------- | ------------------------------------------------------------ |
| `committee_cd`            | String  | `committee_cd`            | Primary key. IECDB unique identifier.                        |
| `committee_nm`            | String  | `committee_nm`            | Official registered name.                                    |
| `normalized_committee_nm` | String  | `normalized_committee_nm` | ETL-normalized for deduplication.                            |
| `committee_type`          | String  | `committee_type`          | Raw IECDB type string (Iowa PAC, State House, etc.).         |
| `partisan_lean`           | String  | inferred                  | `DEMOCRAT` \| `REPUBLICAN` \| `BIPARTISAN` \| `NONPARTISAN` \| `UNKNOWN` |
| `office_level`            | String  | derived                   | `STATEWIDE` \| `LEGISLATIVE` \| `LOCAL` \| `PARTY` \| `PAC`  |
| `total_received`          | Float   | aggregated                | Sum of all inbound contributions in Polk County scope.       |
| `donor_count`             | Integer | aggregated                | Distinct canonical donors contributing.                      |
| `is_relay_node`           | Boolean | derived                   | True if this committee also appears as a contributor. Set via post-load Cypher. |
| `pac_dependency_ratio`    | Float   | computed                  | Fraction of total received from PAC sources. Supports CQ3.   |

---

#### `:Household`

Analytical aggregate node grouping `Individual` donors sharing a residential address with name proximity. Does not directly contribute — it is a structural container enabling household-level betweenness calculation. Supports CQ2.

| Property                 | Type    | Source        | Notes                                                     |
| ------------------------ | ------- | ------------- | --------------------------------------------------------- |
| `household_id`           | String  | derived (ETL) | Primary key. UUID format.                                 |
| `canonical_address`      | String  | derived       | Normalized street address via `usaddress`.                |
| `member_count`           | Integer | aggregated    | Number of Donor nodes in this household.                  |
| `total_household_giving` | Float   | aggregated    | Sum across all member Donor nodes.                        |
| `partisan_lean`          | String  | inferred      | Household-level lean derived from recipient partisanship. |
| `household_betweenness`  | Float   | computed      | Betweenness score treating household as single node.      |

---

#### `:CoordinatedEvent`

Derived event node representing a detected coordinated giving burst. Instantiated by Marcus ETL when 3+ donors give identical amounts to the same recipient on the same date. Enables temporal visualization in Bloom and supports CQ4.

| Property            | Type    | Source         | Notes                                                        |
| ------------------- | ------- | -------------- | ------------------------------------------------------------ |
| `event_id`          | String  | derived        | Primary key. Hash of `date + committee_cd + amount`.         |
| `event_date`        | Date    | `date`         | Date of coordinated contributions.                           |
| `amount`            | Float   | `amount`       | Common contribution amount.                                  |
| `recipient_cd`      | String  | `committee_cd` | Target committee.                                            |
| `donor_count`       | Integer | computed       | Number of co-contributors. Coordination intensity measure.   |
| `session_proximate` | Boolean | derived        | True if event date falls within 30 days of Iowa legislative session start. |

---

### 3.2 Relationship Types

#### `(:Donor)-[:CONTRIBUTED_TO]->(:Committee)`

The primary financial edge. Carries aggregated contribution data between a canonical Donor and a recipient Committee. **One edge per Donor–Committee pair** (aggregated across all individual transactions).

| Property             | Type    | Notes                                                        |
| -------------------- | ------- | ------------------------------------------------------------ |
| `total_amount`       | Float   | Sum of all contributions from this donor to this committee.  |
| `transaction_count`  | Integer | Number of distinct contribution records.                     |
| `first_date`         | Date    | Date of first contribution.                                  |
| `last_date`          | Date    | Date of most recent contribution.                            |
| `max_single_gift`    | Float   | Largest single contribution amount.                          |
| `coordinated_events` | Integer | Count of coordinated giving events involving this edge.      |
| *[Merge Policy]*     |         | When processing in chunks: `total_amount = SUM()`, `transaction_count = SUM()`, `first_date = MIN()`, `last_date = MAX()`, `max_single_gift = MAX()`, `coordinated_events = SUM()`. Use `MERGE ... ON MATCH SET` in Cypher for incremental updates. |

---

#### `(:Committee:PAC)-[:DISBURSED_TO]->(:Committee)`

Outbound edge from PAC relay nodes to downstream committees. Distinguished from `CONTRIBUTED_TO` to preserve relay structure for path analysis. Enables queries tracing money from original donor through intermediary PAC to final candidate.

> Present for 443 PAC relay nodes in the Polk County slice. Key to CQ3 access-buyer analysis.

---

#### `(:Donor)-[:HOUSEHOLD_MEMBER_OF]->(:Household)`

Links individual Donor nodes to their Household aggregate. Created during ETL deduplication when the Household Equivalence Axiom fires.

---

#### `(:Donor)-[:PARTICIPATED_IN]->(:CoordinatedEvent)`

Links donor nodes to detected coordination events. Created when the Coordination Detection Axiom fires during ETL. Enables CQ4 temporal pattern analysis and Bloom visualization of session-opening tribute patterns.

---

#### `(:Donor:Individual:Candidate)-[:REPRESENTS]->(:Committee)`

Links a candidate Individual to the committee formed on their behalf. This is the **ownership/representation** relationship, distinct from `:CONTRIBUTED_TO` (a donor giving money) or `:affiliatedWith` (a donor who also holds office).

> **Join key:** `iowa_candidate_registrations.candidate_name_standardized` is matched against `normalized_donor_key` to identify candidate Donors. The corresponding `committee_cd` from that registration provides the Committee node identifier. One `:REPRESENTS` edge per candidate-committee registration. A candidate running for multiple offices across multiple cycles may have multiple `:REPRESENTS` edges.

| Property             | Type    | Notes                                                        |
| -------------------- | ------- | ------------------------------------------------------------ |
| `registration_year`  | Integer | Election year from `iowa_candidate_registrations`.           |
| `office_sought`      | String  | Office from `iowa_candidate_registrations`.                  |
| `self_funded_amount` | Float   | Sum of contributions from this Donor to this Committee. Populated post-load. |
| `self_funded_pct`    | Float   | `self_funded_amount / Committee.total_received`. Populated post-load. |

---

### 3.3 Graph Constraints and Indexes

Run these statements against AuraDB **before** any data load:

```cypher
// Uniqueness constraints
CREATE CONSTRAINT ON (d:Donor) ASSERT d.canonical_donor_id IS UNIQUE;
CREATE CONSTRAINT ON (c:Committee) ASSERT c.committee_cd IS UNIQUE;
CREATE CONSTRAINT ON (h:Household) ASSERT h.household_id IS UNIQUE;
CREATE CONSTRAINT ON (e:CoordinatedEvent) ASSERT e.event_id IS UNIQUE;

// Performance indexes
CREATE INDEX FOR (d:Donor) ON (d.betweenness_score);       -- CQ1 range queries
CREATE INDEX FOR (d:Donor) ON (d.partisan_lean);           -- CQ3 partisan filter
CREATE INDEX FOR (e:CoordinatedEvent) ON (e.event_date);   -- CQ4 temporal queries

// Full-text indexes (enables Bloom name search)
CREATE FULLTEXT INDEX donorSearch FOR (d:Donor) ON EACH [d.display_name];
CREATE FULLTEXT INDEX committeeSearch FOR (c:Committee) ON EACH [c.committee_nm];
```

---

### 3.4 Cardinality and Scale

| Element                   | Estimated Count      | Notes                                                        |
| ------------------------- | -------------------- | ------------------------------------------------------------ |
| `:Donor` nodes            | ~47,000              | 54,059 normalized_donor_keys after household deduplication. Estimate accounts for ~12% collapse rate. |
| `:Committee` nodes        | 2,764                | Distinct `committee_cd` values in Polk County slice.         |
| `:PAC` nodes (subset)     | 443                  | Relay PACs appearing as both contributors and recipients.    |
| `:Household` nodes        | ~2,500–4,000         | Estimated from address clustering. Actual count determined during ETL. |
| `:CoordinatedEvent` nodes | ~200–400             | Conservative estimate from session-date clustering.          |
| `:CONTRIBUTED_TO` edges   | ~120,000             | Aggregated from 391,881 raw transactions. One edge per canonical Donor–Committee pair. |
| **Total nodes**           | **~52,000–55,000**   | **Well within AuraDB Free Tier limit (~200,000 nodes).**     |
| **Total edges**           | **~130,000–140,000** | **Well within AuraDB Free Tier limit (~400,000 relationships).** |

---

## 4. Known Limitations and Scope Boundaries

The following limitations are known, documented, and intentional. They are the honest boundary conditions of the data and the scope of this implementation. Each represents a potential Phase 2 enrichment.

| Limitation                                            | Impact                                                       | Phase 2 Resolution                                           |
| ----------------------------------------------------- | ------------------------------------------------------------ | ------------------------------------------------------------ |
| Partisan lean is inferred, not ground truth           | Committee lean derived from name pattern matching. Committees with non-obvious names are classified `UNKNOWN`. | Iowa SOS voter registration file provides ground-truth party affiliation for candidates (~$800 for Polk County). |
| Household deduplication is address-based              | Donors at PO Boxes or commercial addresses (e.g., Hy-Vee HQ at 5820 Westown Pkwy) may be over-clustered. | Voter file VUID provides canonical individual identity independent of address. |
| **Donor address mobility not modeled temporally**     | The dataset spans 2003–2025. A donor who moved addresses appears as two separate Donor nodes in two Household clusters. This inflates apparent donor counts and may split betweenness scores for long-tenured donors. | Voter file VUID creates identity that persists across address changes. Alternatively, temporal address properties (`valid_from`/`valid_to`) could merge mobile donors — out of scope for v1. |
| **Marriage/name changes not resolved by Levenshtein** | The Household Equivalence Axiom uses name proximity (Levenshtein ≤ 2). A name change from "Smith" to "Jones" will not be caught, creating two separate Donor nodes for the same person. | Voter file VUID resolves this definitively. In the absence of the voter file, same-address donors with large contribution totals and sudden name changes could be flagged for manual review. |
| Disbursement data not in source                       | PAC-to-candidate flows identified via `contr_committee_cd` on inbound records, not dedicated disbursement records. | IECDB disbursement table enrichment in Phase 2.              |
| Data currency: last update July 2025                  | Contributions from August 2025 onward are missing. 2026 primary cycle is partially absent. | Scheduled data refresh using existing Postgres ETL pipeline. |
| Scope limited to Polk County                          | Statewide donor networks are partially visible — only contributions by Polk County residents are captured. Major statewide donors may appear truncated. | Statewide expansion is a configuration change, not a model change. Full dataset: 2.7M contributions. |
| LPG does not natively enforce OWL axioms              | Neo4j does not prevent ontologically invalid assertions. Constraint compliance depends on Marcus ETL correctness. | APOC triggers or a validation layer could enforce axioms post-load. Out of scope for v1. |

---

## Data Source and Provenance

All data is sourced from the **Iowa Ethics and Campaign Disclosure Board** public campaign finance database, accessed via the `iowa_contributions_v2_5` Postgres dataset (last updated July 2025). All data is public record. No personally identifiable information beyond what appears in the public IECDB disclosure system is incorporated.

This document was prepared by **JL Intelligence**. The graph implementation targets Neo4j AuraDB Free Tier. The ontological framework is LPG-native and does not depend on RDF/OWL tooling for implementation, though the formal definitions in Section 2 are compatible with OWL 2 DL and could be serialized as an OWL ontology for interoperability purposes.

---

*Polk County Political Contribution Graph &nbsp;·&nbsp; JL Intelligence &nbsp;·&nbsp; v3.0*
