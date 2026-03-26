# Iowa Campaign Contributions — Database Schema

**Database:** iowa_contributors (PostgreSQL)  
**Schema:** public  
**Retrieved:** 2026-03-26

---

## Tables Overview

| Table | Purpose |
|---|---|
| `iowa_campaign_contributions_v2_5` | Core contributions data — the main ETL source |
| `iowa_candidate_registrations` | Candidate + committee registry |
| `iowa_election_results` | Election outcomes |
| `iowa_congressional_districts` | Geographic reference |
| `iowa_state_house_districts` | Geographic reference |
| `iowa_state_senate_districts` | Geographic reference |
| `iowa_precinct_boundaries` | Geographic reference |
| `iowa_suspicious_patterns_v2_5` | Flagged contribution patterns |
| `iowa_suspicious_pattern_members_v2_5` | Members of suspicious pattern groups |
| `iowa_etl_operations_v2_5` | ETL audit log |
| `iowa_etl_comparison_v1_v2_5` | Version comparison table |
| `iowa_etl_dead_letter_queue` | Failed ETL records |
| `iowa_voter_file_blocks` | Voter file data |
| `iowa_voter_file_blocks_staging` | Voter file staging |
| `etl_operations_audit` | General ETL audit |
| `business_rules_config` | Business rules configuration |
| `data_quality_flag_definitions` | Data quality flag reference |
| `spatial_ref_sys` | PostGIS spatial reference |

---

## Core ETL Tables

### `iowa_campaign_contributions_v2_5`
The primary source table for the Neo4j graph ETL.

**Key columns for graph extraction:**

| Column | Type | Notes |
|---|---|---|
| `contribution_id` | bigint PK | Unique contribution identifier |
| `date` | date | Contribution date |
| `amount` | numeric | Contribution amount (positive, enforced by constraint) |
| `committee_cd` | varchar | Recipient committee code — **join key to candidates** |
| `committee_nm` | varchar | Recipient committee name |
| `committee_type` | varchar | Type of committee |
| `contr_committee_cd` | varchar | Contributor committee code (when donor is a committee) |
| `organization_nm` | varchar | Donor organization name (raw) |
| `first_nm` | varchar | Donor first name |
| `last_nm` | varchar | Donor last name |
| `city` | varchar | Donor city — **city filter field** |
| `state_cd` | char | Donor state |
| `zip` | varchar | Donor zip code |
| `normalized_donor_key` | varchar | Cleaned donor identity key — use for deduplication |
| `normalized_organization_nm` | varchar | Cleaned org name |
| `normalized_committee_nm` | varchar | Cleaned committee name |
| `data_quality_score` | integer | 0–100, default 100 |
| `duplicate_confidence_score` | integer | Higher = more likely duplicate |
| `data_quality_flags` | text[] | Array of flag codes |
| `campaign_finance_classification` | varchar | Default: 'STANDARD' |
| `transaction_type` | varchar | Type of transaction |

**Useful indexes for ETL queries:**
- `idx_contrib_v2_5_donor_individual` — on `normalized_donor_key` (excludes nulls and bare `|`)
- `idx_contrib_v2_5_donor_org` — on `normalized_organization_nm`
- `idx_contrib_v2_5_committee_lookup` — on `committee_cd, normalized_committee_nm`
- `idx_contrib_v2_5_quality_scores` — on `data_quality_score, duplicate_confidence_score`

**Recommended ETL filter:**
```sql
WHERE city = 'Des Moines'          -- or target city
  AND data_quality_score >= 80     -- exclude low-quality records
  AND duplicate_confidence_score < 50  -- exclude likely duplicates
  AND campaign_finance_classification = 'STANDARD'
```

---

### `iowa_candidate_registrations`
Committee-to-candidate lookup. Join to contributions via `committee_cd`.

| Column | Type | Notes |
|---|---|---|
| `registration_id` | bigint PK | |
| `candidate_name` | varchar | Raw candidate name |
| `candidate_name_standardized` | varchar | Cleaned name — use this |
| `committee_cd` | varchar | **Join key to contributions** |
| `committee_nm` | varchar | Committee name |
| `election_year` | integer | |
| `office_sought` | varchar | Position running for |
| `district` | varchar | District identifier |
| `party_affiliation` | varchar | Political party |
| `incumbent_status` | boolean | |
| `filing_date` | date | |
| `withdrawn_date` | date | Null if still active |

**Unique constraint:** `(candidate_name_standardized, election_year, office_sought, district)`

---

## Graph Model Mapping

```
(Donor)-[:CONTRIBUTED_TO {amount, date, transaction_type}]->(Committee)
(Committee)-[:REGISTERED_TO]->(Candidate)
(Candidate)-[:SOUGHT]->(Office)
(Donor)-[:LOCATED_IN]->(City)
```

**Node types:**
- `Donor` — keyed on `normalized_donor_key` (individuals) or `normalized_organization_nm` (orgs)
- `Committee` — keyed on `committee_cd`
- `Candidate` — keyed on `candidate_name_standardized + election_year`
- `City` — keyed on `city + state_cd`

**Relationship properties to carry into Neo4j:**
- `CONTRIBUTED_TO`: `amount`, `date`, `transaction_type`, `data_quality_score`

---

## ETL Query Skeleton

```python
import psycopg2
import pandas as pd

query = """
SELECT
    c.contribution_id,
    c.normalized_donor_key,
    c.first_nm,
    c.last_nm,
    c.normalized_organization_nm,
    c.city,
    c.state_cd,
    c.committee_cd,
    c.normalized_committee_nm,
    c.amount,
    c.date,
    c.transaction_type,
    c.data_quality_score,
    r.candidate_name_standardized,
    r.office_sought,
    r.district,
    r.party_affiliation,
    r.election_year
FROM iowa_campaign_contributions_v2_5 c
LEFT JOIN iowa_candidate_registrations r
    ON c.committee_cd = r.committee_cd
WHERE c.city = %(city)s
  AND c.data_quality_score >= 80
  AND c.duplicate_confidence_score < 50
ORDER BY c.date DESC;
"""

df = pd.read_sql(query, conn, params={"city": "Des Moines"})
```
