**Polk County Political Contribution Graph**

Domain Taxonomy, Formal Ontology, and Graph Data Model

*JL Intelligence \| v1.0 \| March 2026*

**Document Purpose**

This document defines the formal knowledge structure underlying the Polk
County Political Contribution Graph --- a Neo4j graph database built on
Iowa Ethics and Campaign Disclosure Board public data. The graph models
391,881 contributions spanning 2003--2025 across 54,059 unique donors
and 2,764 recipient committees in the Des Moines metropolitan area.

The document is organized in three layers of increasing implementation
specificity:

-   Domain Taxonomy --- the classification hierarchy of entities and
    relationships in Iowa campaign finance

-   Formal Ontology --- class definitions, property domains and ranges,
    and logical axioms governing valid assertions

-   Labeled Property Graph Model --- the concrete Neo4j implementation,
    including node labels, relationship types, and property schemas

**Competency Questions Served**

The ontology is scoped to answer five competency questions (CQs) that
define the analytical boundary of this knowledge graph:

-----------------------------------------------------------------------

  **CQ**                  **Question**            **Analysis Type**

----------------------- ----------------------- -----------------------

  CQ1                     Who are the             Betweenness Centrality
                          structurally            
                          indispensable donors    
                          --- not the biggest     
                          check writers, but      
                          those whose removal     
                          most fragments the      
                          network?                

  CQ2                     Where does apparent     Address Deduplication +
                          donor diversity         Node Merge
                          collapse into           
                          single-household        
                          political actors, and   
                          what does that reveal   
                          about candidate         
                          dependency?             

  CQ3                     Which organizations     Community Detection +
                          fund both parties ---   Edge Analysis
                          and are their recipient 
                          legislators             
                          structurally dependent  
                          on that bipartisan      
                          money?                  

  CQ4                     Can the graph surface   Temporal Pattern
                          coordinated giving      Detection
                          events, and what does   
                          their temporal pattern  
                          reveal about            
                          legislative influence   
                          operations?             

  CQ5                     Which candidates have   Louvain Community
                          concentrated            Detection
                          single-community        
                          funding (vulnerable to  
                          exit) versus genuinely  
                          diversified structural  

                          support?                
  -----------------------------------------------------------------------

**1. Domain Taxonomy**

*Classification hierarchy for Iowa campaign finance entities and events*

The taxonomy organizes domain concepts into a hierarchy of increasing
specificity. This structure is implementation-agnostic --- it applies
equally to the LPG model, an RDF triplestore, or a relational schema.
Classes marked (abstract) have no direct instances; they exist to
organize shared properties inherited by subclasses.

**1.1 Entity Classes**

**PoliticalActor (abstract)**

The root class for any agent that participates in Iowa campaign finance
--- either as a contributor, recipient, or both. All PoliticalActors are
identified by a canonical identifier derived from normalized name and
address.

-   **Individual ⊂ PoliticalActor**

> *A natural person acting in their own name. Individuals may contribute
> directly or serve as candidates. Identified by normalized full name +
> address. Subject to household clustering.*

-   **Organization ⊂ PoliticalActor (abstract)**

> *A collective entity acting under an organizational identity. Includes
> all committee types and corporate donors. Identified by normalized
> organization name.*

-   **Committee ⊂ Organization (abstract)**

> *A formal committee registered with the Iowa Ethics and Campaign
> Disclosure Board. Identified by committee_cd (unique IECDB
> identifier). Subclassed by registration type.*

-   CandidateCommittee ⊂ Committee

> *Formed to support a specific candidate for elective office. Carries
> office_sought and district properties. May receive from individuals,
> PACs, and party committees.*

-   PartyCommittee ⊂ Committee

> *State or county central committees for recognized political parties.
> Operates as both contributor and recipient. Key nodes for partisan
> flow analysis.*

-   PoliticalActionCommittee ⊂ Committee

> *Registered PAC operating as an intermediary: collecting from members
> or donors and disbursing to candidate and party committees. The relay
> node in bundled contribution patterns. May appear as both contributor
> (via contr_committee_cd) and recipient.*

-   CorporateOrAssociationDonor ⊂ Organization

> *Non-committee organization contributing directly (e.g., employer PAC
> not registered as a standalone committee). Identified via
> organization_nm field.*

**Household**

A compound class representing a cluster of Individual instances sharing
a common residential address and exhibiting name proximity (Levenshtein
distance ≤ 2 on normalized_donor_key). The Household is not itself a
PoliticalActor --- it is an analytical aggregate used to resolve
apparent donor diversity into structural funding units.

> *Rationale: Iowa campaign finance reporting accepts name variants as
> independent filers. The Debra/Deb/Deborah Hansen cluster at 1469 Glen
> Oaks Dr, West Des Moines --- contributing \$650K+ to Republican
> candidates --- illustrates a systematic pattern where one funding unit
> appears as three or more separate donors in raw data. The Household
> class collapses this for accurate betweenness calculation.*

**1.2 Relational Concepts and Event Classes**

**ContributionEvent (Relational Concept --- not instantiated as a
node)**

A discrete financial transfer from a PoliticalActor to a Committee, as
reported to the IECDB. Each event has a date, amount, and
transaction_type. In the LPG implementation, ContributionEvent is NOT
modeled as a node --- its properties are aggregated onto the
CONTRIBUTED_TO relationship. It is defined here as a relational concept
for ontological completeness, documenting the source semantics of
CONTRIBUTED_TO edge properties.

> *Engineer note: There is no ContributionEvent node in Neo4j. The
> CONTRIBUTED_TO edge carries total_amount, transaction_count,
> first_date, last_date, and max_single_gift as aggregated properties.
> Marcus aggregates all transactions per Donor--Committee pair before
> load --- not after.*

**CoordinatedGivingEvent**

A derived class representing a detected pattern of multiple
PoliticalActors contributing identical amounts to the same Committee on
the same date. This class has no direct source data instantiation --- it
is computed during ETL from ContributionEvent clustering. Modeled as a
node in the LPG to support CQ4 temporal analysis.

> *Observed instances: January 10, 2016 --- 11 PACs, \$1,000 each,
> Citizens for Gronstal; January 9, 2011 --- 9 PACs, \$1,000 each, same
> recipient. These session-opening tribute patterns repeat across
> multiple years and multiple legislative leaders of both parties.*

**1.3 Taxonomic Hierarchy Summary**

----------------------------------------------------------------------------------------------

  **Class**                     **Parent**        **Abstract?**     **Source Identity Field**

----------------------------- ----------------- ----------------- ----------------------------

  PoliticalActor                ---               Yes               ---

  Individual                    PoliticalActor    No                normalized_donor_key +
                                                                    address

  Organization                  PoliticalActor    Yes               ---

  Committee                     Organization      Yes               committee_cd

  CandidateCommittee            Committee         No                committee_cd

  PartyCommittee                Committee         No                committee_cd

  PoliticalActionCommittee      Committee         No                committee_cd

  CorporateOrAssociationDonor   Organization      No                normalized_organization_nm

  Household                     (analytical       No                address + name cluster
                                aggregate)                          

  ContributionEvent             --- (relational   N/A               Lives on CONTRIBUTED_TO edge
                                concept)                            

  CoordinatedGivingEvent        ---               No                derived: date + committee +

                                                                    amount
  ----------------------------------------------------------------------------------------------

**2. Formal Ontology**

*Class definitions, property semantics, domain/range constraints, and
logical axioms*

This section defines the ontology using OWL-aligned notation. Although
the implementation target is a Labeled Property Graph (Neo4j), the
ontological rigor defined here constrains what Marcus may assert ---
preventing structurally incoherent data from entering the graph and
ensuring that CQ answers are logically valid, not artifacts of modeling
error.

Notation: domain(P) denotes the class of subjects in property P
assertions. range(P) denotes the class of objects. ⊑ denotes subclass. ≡
denotes equivalence. ⊥ denotes disjoint classes.

**2.1 Object Properties**

Object properties relate instances to instances. Each carries domain and
range constraints.

---------------------------------------------------------------------------------------------------------

  **Property**      **Domain**                 **Range**                **Cardinality**   **Notes**

----------------- -------------------------- ------------------------ ----------------- -----------------

  :contributedTo    PoliticalActor             Committee                Many-to-many      Core financial
                                                                                          flow. PAC may
                                                                                          appear as both
                                                                                          subject and
                                                                                          object (relay
                                                                                          pattern).

  :disbursedTo      PoliticalActionCommittee   Committee                Many-to-many      Outbound PAC
                                                                                          flow.
                                                                                          Distinguishes
                                                                                          relay nodes from
                                                                                          direct donors.

  :memberOf         Individual                 Household                Many-to-one       Derived from
                                                                                          address + name
                                                                                          cluster. Enables
                                                                                          household-level
                                                                                          betweenness.

  :affiliatedWith   Individual                 CandidateCommittee       Many-to-many      For candidates
                                                                                          who are also
                                                                                          donors. Enables
                                                                                          cross-role
                                                                                          analysis.

  :participatedIn   PoliticalActor             CoordinatedGivingEvent   Many-to-many      Links donor nodes
                                                                                          to detected
                                                                                          coordination
                                                                                          events. Supports

                                                                                          CQ4.
  ---------------------------------------------------------------------------------------------------------

> *Note on :coContributorOf: This symmetric property was considered but
> omitted from the LPG implementation. In a graph with 391k
> transactions, materializing direct co-contributor edges creates an
> O(N²) clique for every coordination event --- 11 co-contributors
> generates 55 edges instead of 11. The :CoordinatedEvent hub node
> provides equivalent query capability without the relationship
> explosion. All co-contributor queries should traverse
> (:Donor)-\[:PARTICIPATED_IN\]-\>(:CoordinatedEvent)\<-\[:PARTICIPATED_IN\]-(:Donor).*

**2.2 Datatype Properties**

-----------------------------------------------------------------------------------------------------

  **Property**         **Domain**               **Datatype**   **Source Field**       **Notes**

-------------------- ------------------------ -------------- ---------------------- -----------------

  :amount              ContributionEvent        xsd:decimal    amount                 Contribution
                                                                                      amount in USD.
                                                                                      Always positive.

  :contributionDate    ContributionEvent        xsd:date       date                   Date reported to
                                                                                      IECDB.

  :canonicalDonorId    PoliticalActor           xsd:string     derived                Assigned during
                                                                                      ETL
                                                                                      deduplication.
                                                                                      Stable across
                                                                                      name variants.

  :normalizedKey       PoliticalActor           xsd:string     normalized_donor_key   IECDB normalized
                                                                                      identifier. May
                                                                                      be non-unique
                                                                                      across household
                                                                                      members.

  :committeeType       Committee                xsd:string     committee_type         IECDB
                                                                                      registration
                                                                                      category (Iowa
                                                                                      PAC, State House,
                                                                                      Governor, etc.).

  :partisanLean        Committee                xsd:string     derived                DEMOCRAT \|
                                                                                      REPUBLICAN \|
                                                                                      BIPARTISAN \|
                                                                                      NONPARTISAN.
                                                                                      Derived from
                                                                                      committee_nm
                                                                                      pattern matching.

  :betweennessScore    PoliticalActor           xsd:decimal    computed               Normalized
                                                                                      betweenness
                                                                                      centrality.
                                                                                      Computed in
                                                                                      NetworkX, written
                                                                                      as node property
                                                                                      before AuraDB
                                                                                      load.

  :householdId         Individual               xsd:string     derived                Links Individual
                                                                                      to Household
                                                                                      aggregate node.

  :coordinationScore   CoordinatedGivingEvent   xsd:integer    computed               Number of
                                                                                      co-contributors
                                                                                      in the event.
                                                                                      Higher = stronger
                                                                                      coordination
                                                                                      signal.

  :totalGiven          PoliticalActor           xsd:decimal    aggregated             Lifetime
                                                                                      contribution
                                                                                      total within Polk

                                                                                      County scope.
  -----------------------------------------------------------------------------------------------------

**2.3 Logical Axioms**

**Disjointness Axioms**

The following classes are mutually exclusive. No instance may belong to
more than one:

-----------------------------------------------------------------------

  **Axiom**                           **Rationale**

----------------------------------- -----------------------------------

  Individual ⊥ Organization           A natural person is not a committee
                                      or organization in IECDB data.

  CandidateCommittee ⊥ PartyCommittee IECDB registration type is mutually
                                      exclusive.

  CandidateCommittee ⊥                IECDB registration type is mutually
  PoliticalActionCommittee            exclusive.

  PartyCommittee ⊥                    IECDB registration type is mutually

  PoliticalActionCommittee            exclusive.
  -----------------------------------------------------------------------

**Relay Node Axiom**

A PoliticalActionCommittee that appears as both a contributor (via
contr_committee_cd) and a recipient (via committee_cd) in the
contributions table is asserted as a relay node. Formally:

> ∃x : PoliticalActionCommittee(x) ∧ contributedTo(x, y) ∧
> contributedTo(z, x)
>
> → relayNode(x) = true
>
> *443 distinct PAC relay nodes are present in the Polk County slice.
> These are the most analytically significant nodes for betweenness
> centrality --- they bridge individual donors to candidate committees
> across partisan lines.*
>
> *Implementation timing: is_relay_node is flagged via post-load Cypher,
> not during Marcus ETL. After the initial batch load completes, run:
> MATCH (c:Committee) WHERE EXISTS { MATCH (c)-\[:CONTRIBUTED_TO\]-\>()
> } SET c.is_relay_node = true. This is more reliable than ETL detection
> because it operates on the fully loaded graph state.*

**Household Equivalence Axiom**

Two Individual instances are asserted as members of the same Household
if and only if:

> sameAddress(a, b) ∧ levenshtein(normalizedKey(a), normalizedKey(b)) ≤
> 2
>
> → ∃h : Household(h) ∧ memberOf(a, h) ∧ memberOf(b, h)
>
> *Implementation: Marcus applies this axiom during ETL in two passes.
> Pass 1 --- address normalization: the Python usaddress library parses
> street addresses into structured components (street number, street
> name, suffix) and produces a canonical form. This resolves \'123 Main
> St\' and \'123 Main Street\' to the same canonical address before
> comparison. Pass 2 --- name proximity: Levenshtein distance ≤ 2 on
> normalized_donor_key at the same canonical address. The
> canonical_donor_id property is the household-level identifier that
> collapses variants for betweenness computation.*

**Coordination Detection Axiom**

A CoordinatedGivingEvent is instantiated when:

> ∃e1, e2 : ContributionEvent(e1) ∧ ContributionEvent(e2)
>
> ∧ date(e1) = date(e2)
>
> ∧ amount(e1) = amount(e2)
>
> ∧ recipient(e1) = recipient(e2)
>
> ∧ contributor(e1) ≠ contributor(e2)
>
> ∧ count({e : same conditions}) ≥ 3
>
> → CoordinatedGivingEvent(g) ∧ participatedIn(contributor(e1), g) ∧
> participatedIn(contributor(e2), g)
>
> *Threshold of 3+ contributors on identical amount/date/recipient is
> conservative. The January session-opening clusters reach 11
> co-contributors. This axiom instantiates the CoordinatedGivingEvent
> node in the graph.*

**Partisan Lean Inference Axiom**

Partisan lean is inferred from committee naming patterns where direct
party registration data is unavailable:

> committeeNm(c) MATCHES \'(?i)(democrat\|hubbell\|gronstal\|culver)\' →
> partisanLean(c) = \'DEMOCRAT\'
>
> committeeNm(c) MATCHES \'(?i)(republican\|reynolds\|branstad\|iowa
> gop)\' → partisanLean(c) = \'REPUBLICAN\'
>
> let D = sum of amounts given to DEMOCRAT-lean committees
>
> let R = sum of amounts given to REPUBLICAN-lean committees
>
> let minority = min(D, R), let total = D + R
>
> minority/total \>= 0.20 =\> partisanLean = BIPARTISAN
>
> minority / total \< 0.20 → partisanLean(x) = partisan direction of
> majority
>
> *The 20% threshold prevents noise from distorting classification. A
> donor giving  to Democrats and ,000 to Republicans is classified
> REPUBLICAN, not BIPARTISAN. This reflects genuine access-buying
> behavior (Credit Union PAC: 58K R / 75K D = 44% minority = BIPARTISAN)
> versus nominal cross-party giving. Coverage is partial --- committee
> naming conventions are not standardized in IECDB data. Lean is
> best-effort inference documented as a known limitation.*

**3. Labeled Property Graph Model**

*Neo4j node labels, relationship types, and property schemas*

This section defines the concrete LPG implementation targeting Neo4j
AuraDB Free Tier. All ontological classes from Section 2 map to node
labels or relationship types. Properties are carried on nodes and
relationships as defined by the datatype property schema.

Data source: iowa_campaign_contributions_v2_5 (Postgres), Polk County
scope (city IN \[\'Des Moines\', \'West Des Moines\'\]),
data_quality_score \> 3.

**3.1 Node Labels**

> **(:Donor)**

Represents a deduplicated political actor --- individual or
organizational --- after household clustering. One Donor node per
canonical_donor_id. Corresponds to ontology classes Individual,
CorporateOrAssociationDonor, or PoliticalActionCommittee when acting in
contributor role.

> *Label stacking: Donor nodes carry additional labels reflecting their
> taxonomic subclass: (:Donor:Individual), (:Donor:Organization),
> (:Donor:PAC). Individuals who have also registered as candidates
> additionally carry (:Donor:Individual:Candidate), enabling efficient
> self-funding queries without full graph traversal.*

--------------------------------------------------------------------------------------------------

  **Property**              **Type**          **Source**             **Notes**

------------------------- ----------------- ---------------------- -------------------------------

  canonical_donor_id        String            derived (ETL)          Primary key. Stable across name
                                                                     variants. UUID format.

  normalized_donor_key      String\[\]        normalized_donor_key   Array of all key variants
                                                                     collapsed into this node.

  display_name              String            derived                Best human-readable name from
                                                                     variants.

  donor_type                String            derived                INDIVIDUAL \| ORGANIZATION \|
                                                                     PAC

  partisan_lean             String            inferred               DEMOCRAT \| REPUBLICAN \|
                                                                     BIPARTISAN \| NONPARTISAN \|
                                                                     UNKNOWN

  total_given               Float             aggregated             Sum of all amounts in Polk
                                                                     County scope.

  committee_count           Integer           aggregated             Distinct recipient committees
                                                                     funded.

  first_contribution_date   Date              aggregated             Earliest contribution date.

  last_contribution_date    Date              aggregated             Most recent contribution date.

  betweenness_score         Float             computed (NetworkX)    Normalized betweenness
                                                                     centrality. Core CQ1 property.

  household_id              String            derived (ETL)          Links to Household node. Null
                                                                     for non-clustered donors.

  is_relay_pac              Boolean           derived                True if this donor also appears
                                                                     as a recipient committee.

  is_candidate              Boolean           derived                True if this Individual has a
                                                                     registration in
                                                                     iowa_candidate_registrations.
                                                                     Drives :Candidate label.

  minority_giving_pct       Float             computed               Fraction of partisan giving to
                                                                     minority party. Drives

                                                                     BIPARTISAN threshold logic.
  --------------------------------------------------------------------------------------------------

> **(:Committee)**

Represents a registered recipient committee. May carry additional labels
to reflect taxonomic subclass: :CandidateCommittee, :PartyCommittee, or
:PAC. Labels are not mutually exclusive in Neo4j --- a node may carry
(:Committee:PAC) simultaneously.

---------------------------------------------------------------------------------------

  **Property**              **Type**          **Source**                **Notes**

------------------------- ----------------- ------------------------- -----------------

  committee_cd              String            committee_cd              Primary key.
                                                                        IECDB unique
                                                                        identifier.

  committee_nm              String            committee_nm              Official
                                                                        registered name.

  normalized_committee_nm   String            normalized_committee_nm   ETL-normalized
                                                                        for
                                                                        deduplication.

  committee_type            String            committee_type            Raw IECDB type
                                                                        string (Iowa PAC,
                                                                        State House,
                                                                        etc.).

  partisan_lean             String            inferred                  DEMOCRAT \|
                                                                        REPUBLICAN \|
                                                                        BIPARTISAN \|
                                                                        NONPARTISAN \|
                                                                        UNKNOWN

  office_level              String            derived                   STATEWIDE \|
                                                                        LEGISLATIVE \|
                                                                        LOCAL \| PARTY \|
                                                                        PAC

  total_received            Float             aggregated                Sum of all
                                                                        inbound
                                                                        contributions in
                                                                        Polk County
                                                                        scope.

  donor_count               Integer           aggregated                Distinct
                                                                        canonical donors
                                                                        contributing.

  is_relay_node             Boolean           derived                   True if this
                                                                        committee also
                                                                        appears as a
                                                                        contributor.

  pac_dependency_ratio      Float             computed                  Fraction of total
                                                                        received from PAC
                                                                        sources. Supports

                                                                        CQ3.
  ---------------------------------------------------------------------------------------

> **(:Household)**

Analytical aggregate node grouping Individual donors sharing a
residential address with name proximity. Does not directly contribute
--- it is a structural container enabling household-level betweenness
calculation. Supports CQ2.

------------------------------------------------------------------------------

  **Property**             **Type**          **Source**        **Notes**

------------------------ ----------------- ----------------- -----------------

  household_id             String            derived (ETL)     Primary key. UUID
                                                               format.

  canonical_address        String            derived           Normalized street
                                                               address.

  member_count             Integer           aggregated        Number of Donor
                                                               nodes in this
                                                               household.

  total_household_giving   Float             aggregated        Sum across all
                                                               member Donor
                                                               nodes.

  partisan_lean            String            inferred          Household-level
                                                               lean derived from
                                                               recipient
                                                               partisanship.

  household_betweenness    Float             computed          Betweenness score
                                                               treating
                                                               household as

                                                               single node.
  ------------------------------------------------------------------------------

> **(:CoordinatedEvent)**

Derived event node representing a detected coordinated giving burst.
Instantiated by Marcus ETL when 3+ donors give identical amounts to the
same recipient on the same date. Enables temporal visualization in Bloom
and supports CQ4.

--------------------------------------------------------------------------

  **Property**        **Type**          **Source**        **Notes**

------------------- ----------------- ----------------- ------------------

  event_id            String            derived           Primary key.
                                                          date +
                                                          committee_cd +
                                                          amount hash.

  event_date          Date              date              Date of
                                                          coordinated
                                                          contributions.

  amount              Float             amount            Common
                                                          contribution
                                                          amount.

  recipient_cd        String            committee_cd      Target committee.

  donor_count         Integer           computed          Number of
                                                          co-contributors.
                                                          Coordination
                                                          intensity measure.

  session_proximate   Boolean           derived           True if event date
                                                          falls within 30
                                                          days of Iowa
                                                          legislative

                                                          session start.
  --------------------------------------------------------------------------

**3.2 Relationship Types**

> **(:Donor)-\[:CONTRIBUTED_TO\]-\>(:Committee)**

The primary financial edge. Carries aggregated contribution data between
a canonical Donor and a recipient Committee. One edge per
Donor-Committee pair (aggregated across all individual transactions).
Individual transaction detail is preserved in properties.

-----------------------------------------------------------------------

  **Property**            **Type**                **Notes**

----------------------- ----------------------- -----------------------

  total_amount            Float                   Sum of all
                                                  contributions from this
                                                  donor to this
                                                  committee.

  transaction_count       Integer                 Number of distinct
                                                  contribution records.

  first_date              Date                    Date of first
                                                  contribution.

  last_date               Date                    Date of most recent
                                                  contribution.

  max_single_gift         Float                   Largest single
                                                  contribution amount.

  coordinated_events      Integer                 Count of coordinated
                                                  giving events involving

                                                  this edge.
  -----------------------------------------------------------------------

> **(:Committee:PAC)-\[:DISBURSED_TO\]-\>(:Committee)**

Outbound edge from PAC relay nodes to downstream committees.
Distinguished from CONTRIBUTED_TO to preserve the relay structure for
path analysis. Enables queries tracing money from original donor through
intermediary PAC to final candidate.

> *Present for 443 PAC relay nodes in the Polk County slice. Key to CQ3
> access-buyer analysis.*
>
> **(:Donor)-\[:HOUSEHOLD_MEMBER_OF\]-\>(:Household)**

Links individual Donor nodes to their Household aggregate. Created
during ETL deduplication when the household clustering axiom fires.
Enables CQ2 household bundling analysis.

> **(:Donor)-\[:PARTICIPATED_IN\]-\>(:CoordinatedEvent)**

Links donor nodes to detected coordination events. Created when the
coordination detection axiom fires during ETL. Enables CQ4 temporal
pattern analysis and Bloom visualization of session-opening tribute
patterns.

> **(:Donor:Individual:Candidate)-\[:REPRESENTS\]-\>(:Committee)**

Links a candidate Individual to the committee formed on their behalf.
This is the ownership/representation relationship distinguishing a
candidate from a mere donor. Enables self-funding analysis (CQ2
extension) and traversal from committee back to the candidate as a
person.

> *Join key: iowa_candidate_registrations.candidate_name_standardized is
> matched against normalized_donor_key to identify candidate Donors. The
> corresponding committee_cd from that registration record provides the
> Committee node identifier. One :REPRESENTS edge per
> candidate-committee registration. A candidate running for multiple
> offices across multiple cycles may have multiple :REPRESENTS edges.*

-------------------------------------------------------------------------------

  **Property**            **Type**                **Notes**

----------------------- ----------------------- -------------------------------

  registration_year       Integer                 Election year from
                                                  iowa_candidate_registrations.

  office_sought           String                  Office from
                                                  iowa_candidate_registrations.

  self_funded_amount      Float                   Sum of contributions from this
                                                  Donor to this Committee.
                                                  Populated post-load.

  self_funded_pct         Float                   self_funded_amount /
                                                  Committee.total_received.

                                                  Populated post-load.
  -------------------------------------------------------------------------------

**3.3 Graph Constraints and Indexes**

The following constraints are required before Marcus loads data into
AuraDB:

-----------------------------------------------------------------------

  **Cypher Statement**                **Purpose**

----------------------------------- -----------------------------------

  CREATE CONSTRAINT ON (d:Donor)      Prevents duplicate donor nodes
  ASSERT d.canonical_donor_id IS      
  UNIQUE                              

  CREATE CONSTRAINT ON (c:Committee)  Prevents duplicate committee nodes
  ASSERT c.committee_cd IS UNIQUE     

  CREATE CONSTRAINT ON (h:Household)  Prevents duplicate household nodes
  ASSERT h.household_id IS UNIQUE     

  CREATE CONSTRAINT ON                Prevents duplicate event nodes
  (e:CoordinatedEvent) ASSERT         
  e.event_id IS UNIQUE                

  CREATE INDEX FOR (d:Donor) ON       Enables range queries for CQ1
  (d.betweenness_score)               

  CREATE INDEX FOR (d:Donor) ON       Enables partisan filter for CQ3
  (d.partisan_lean)                   

  CREATE INDEX FOR                    Enables temporal queries for CQ4
  (e:CoordinatedEvent) ON             
  (e.event_date)                      

  CREATE FULLTEXT INDEX donorSearch   Enables Bloom name search --- type
  FOR (d:Donor) ON EACH               \'Hansen\' to surface all Hansen
  \[d.display_name\]                  nodes

  CREATE FULLTEXT INDEX               Enables Bloom committee name search
  committeeSearch FOR (c:Committee)   

  ON EACH \[c.committee_nm\]          
  -----------------------------------------------------------------------

**3.4 Cardinality and Scale**

-----------------------------------------------------------------------

  **Element**             **Estimated Count**     **Notes**

----------------------- ----------------------- -----------------------

  :Donor nodes            \~47,000                54,059
                                                  normalized_donor_keys
                                                  after household
                                                  deduplication. Estimate
                                                  accounts for \~12%
                                                  collapse rate.

  :Committee nodes        2,764                   Distinct committee_cd
                                                  values in Polk County
                                                  slice.

  :PAC nodes (subset)     443                     Relay PACs appearing as
                                                  both contributors and
                                                  recipients.

  :Household nodes        \~2,500--4,000          Estimated from address
                                                  clustering. Actual
                                                  count determined during
                                                  ETL.

  :CoordinatedEvent nodes \~200--400              Conservative estimate
                                                  from session-date
                                                  clustering. Actual
                                                  count determined during
                                                  ETL.

  :CONTRIBUTED_TO edges   \~120,000               Aggregated from 391,881
                                                  raw transactions. One
                                                  edge per canonical
                                                  Donor--Committee pair.

  Total nodes             \~52,000--55,000        Well within AuraDB Free
                                                  Tier limit (\~200,000
                                                  nodes).

  Total edges             \~130,000--140,000      Well within AuraDB Free
                                                  Tier limit (\~400,000

                                                  relationships).
  -----------------------------------------------------------------------

**4. Known Limitations and Scope Boundaries**

*Documented constraints on graph validity*

The following limitations are known, documented, and intentional. They
are not failures of modeling --- they are the honest boundary conditions
of the data and the scope of this implementation. Each represents a
potential Phase 2 enrichment.

-----------------------------------------------------------------------

  **Limitation**          **Impact**              **Phase 2 Resolution**

----------------------- ----------------------- -----------------------

  Partisan lean is        Committee lean is       Iowa SOS voter
  inferred, not ground    derived from name       registration file
  truth                   pattern matching.       provides ground-truth
                          Committees with         party affiliation for
                          non-obvious names are   candidates. \~\$800 for
                          classified UNKNOWN.     Polk County.

  Household deduplication Donors at PO Boxes or   Voter file VUID
  is address-based        commercial addresses    provides canonical
                          (e.g., Hy-Vee corporate individual identity
                          HQ) may be              independent of address.
                          over-clustered.         

  Disbursement data not   PAC-to-candidate flows  IECDB disbursement
  available in source     are identified via      table enrichment in
                          contr_committee_cd on   Phase 2.
                          inbound records, not    
                          dedicated disbursement  
                          records.                

  Data currency: last     Contributions from      Scheduled data refresh
  update July 2025        August 2025 onward are  using existing Postgres
                          not present. 2026       ETL pipeline.
                          primary cycle is        
                          partially missing.      

  Scope limited to Polk   Statewide donor         Statewide expansion is
  County                  networks are partially  a configuration change,
                          visible --- only        not a model change.
                          contributions by Polk   Full dataset: 2.7M
                          County residents are    contributions.
                          captured. Major         
                          statewide donors may    
                          appear truncated.       

  Donor address mobility  The dataset spans       Voter file VUID creates
  not modeled temporally  2003--2025. A donor who identity that persists
                          moved addresses appears across address changes.
                          as two separate Donor   Alternatively, a
                          nodes in two Household  temporal address
                          clusters. This inflates property with
                          apparent donor counts   valid_from/valid_to
                          and may split           could merge mobile
                          betweenness scores for  donors --- out of scope
                          long-tenured donors.    for v1.

  Marriage/name changes   The household           Voter file VUID
  not resolved by         equivalence axiom uses  resolves this
  Levenshtein             name proximity          definitively. In the
                          (Levenshtein ≤ 2). A    absence of the voter
                          name change from        file, same-address
                          \'Smith\' to \'Jones\'  donors with large
                          will not be caught,     contribution totals and
                          creating two separate   sudden name changes
                          Donor nodes for the     could be flagged for
                          same person. PO Box     manual review.
                          filers and commercial   
                          addresses may also      
                          cause false-positive    
                          household clustering.   

  LPG does not natively   Neo4j does not prevent  APOC triggers or a
  enforce OWL axioms      ontologically invalid   validation layer could
                          assertions. Constraint  enforce axioms
                          compliance depends on   post-load. Out of scope

                          Marcus ETL correctness. for v1.
  -----------------------------------------------------------------------

**Data Source and Provenance**

All data is sourced from the Iowa Ethics and Campaign Disclosure Board
public campaign finance database, accessed via the
iowa_contributions_v2_5 Postgres dataset (last updated July 2025). All
data is public record. No personally identifiable information beyond
what appears in the public IECDB disclosure system is incorporated.

This document was prepared by JL Intelligence. The graph implementation
targets Neo4j AuraDB Free Tier. The ontological framework is LPG-native
and does not depend on RDF/OWL tooling for implementation, though the
formal definitions in Section 2 are compatible with OWL 2 DL and could
be serialized as an OWL ontology for interoperability purposes.
