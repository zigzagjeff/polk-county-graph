"""
extract.py — Pull Iowa campaign contributions from Postgres by city filter.

Pipeline position: FIRST
Input:  Postgres iowa_contributors (iowa_campaign_contributions_v2_5 + iowa_candidate_registrations)
Output: parquet file → etl/2extracted/iowa_contributions_extract_{city}_{timestamp}.parquet

Usage:
    python extract.py                    # defaults to Johnston
    ETL_CITY="Des Moines" python extract.py

Checkpoints:
    1. Discovery  — row count + quality metrics, waits for confirmation
    2. Sampling   — first 100 rows shown, waits for confirmation
    3. Full Run   — extracts complete dataset
    4. Handoff    — summary written to log
"""

import os
import sys
import json
import logging
import psycopg2
import pandas as pd
from datetime import datetime, timezone
from pathlib import Path
from dotenv import load_dotenv

# ── Environment ────────────────────────────────────────────────────────────────

load_dotenv(Path(__file__).parent.parent / "Postgres-iowa_contributors-local.txt")

PG_URI = os.getenv(
    "DATABASE_URI",
    "postgresql://political_user:secure_political_2024@localhost:5432/iowa_contributors"
)

CITY               = os.getenv("ETL_CITY", "Johnston")
DATA_QUALITY_MIN   = 80
DUPLICATE_MAX      = 50
BATCH_SIZE         = 10_000   # server-side cursor batch; keeps memory flat on Des Moines run

# ── Paths ──────────────────────────────────────────────────────────────────────

ETL_ROOT   = Path(__file__).parent
OUTPUT_DIR = ETL_ROOT / "2extracted"
LOG_DIR    = ETL_ROOT / "logs"
OUTPUT_DIR.mkdir(exist_ok=True)
LOG_DIR.mkdir(exist_ok=True)

TIMESTAMP   = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
CITY_SLUG   = CITY.lower().replace(" ", "_")
OUTPUT_FILE = OUTPUT_DIR / f"iowa_contributions_extract_{CITY_SLUG}_{TIMESTAMP}.parquet"

# ── Logging ────────────────────────────────────────────────────────────────────

def get_logger(operation: str) -> logging.Logger:
    logger = logging.getLogger(operation)
    logger.setLevel(logging.INFO)
    handler = logging.FileHandler(LOG_DIR / f"{operation}_{TIMESTAMP}.log")
    handler.setFormatter(logging.Formatter("%(message)s"))
    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(handler)
    logger.addHandler(console)
    return logger

def log(logger, level: str, operation: str, step: str, message: str, records: int = None):
    entry = {
        "timestamp":  datetime.now(timezone.utc).isoformat(),
        "log_level":  level,
        "operation":  operation,
        "step_name":  step,
        "message":    message,
    }
    if records is not None:
        entry["records_processed"] = records
    getattr(logger, level.lower())(json.dumps(entry))

# ── SQL ────────────────────────────────────────────────────────────────────────

COUNT_QUERY = """
SELECT
    COUNT(*)                                                        AS total,
    ROUND(AVG(data_quality_score)::numeric, 1)                     AS avg_quality,
    MIN(data_quality_score)                                         AS min_quality,
    MAX(data_quality_score)                                         AS max_quality,
    SUM(CASE WHEN normalized_donor_key IS NULL
              OR normalized_donor_key = '|' THEN 1 ELSE 0 END)     AS null_donor_keys,
    COUNT(DISTINCT normalized_donor_key)
        FILTER (WHERE normalized_donor_key IS NOT NULL
                  AND normalized_donor_key != '|')                  AS distinct_donors,
    COUNT(DISTINCT committee_cd)                                    AS distinct_committees
FROM iowa_campaign_contributions_v2_5
WHERE city = %(city)s
  AND state_cd = 'IA'
  AND data_quality_score >= %(quality_min)s
  AND duplicate_confidence_score < %(dup_max)s;
"""

EXTRACT_QUERY = """
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
    c.committee_type,
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
  AND c.state_cd = 'IA'
  AND c.data_quality_score >= %(quality_min)s
  AND c.duplicate_confidence_score < %(dup_max)s
  AND c.normalized_donor_key IS NOT NULL
  AND c.normalized_donor_key != '|'
ORDER BY c.date DESC;
"""

SAMPLE_QUERY = """
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
    c.committee_type,
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
  AND c.state_cd = 'IA'
  AND c.data_quality_score >= %(quality_min)s
  AND c.duplicate_confidence_score < %(dup_max)s
  AND c.normalized_donor_key IS NOT NULL
  AND c.normalized_donor_key != '|'
ORDER BY c.date DESC
LIMIT 100;
"""

PARAMS = {
    "city":        CITY,
    "quality_min": DATA_QUALITY_MIN,
    "dup_max":     DUPLICATE_MAX,
}

# ── Checkpoints ────────────────────────────────────────────────────────────────

def checkpoint_confirm(prompt: str) -> None:
    """Pause and require explicit confirmation before proceeding."""
    response = input(f"\n{prompt}\nProceed? [yes/no]: ").strip().lower()
    if response not in ("yes", "y"):
        print("Aborted by user.")
        sys.exit(0)

# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    logger = get_logger("extract")
    log(logger, "info", "extract", "start",
        f"City: {CITY} | Quality >= {DATA_QUALITY_MIN} | Dup confidence < {DUPLICATE_MAX}")

    # ── Connect ────────────────────────────────────────────────────────────────
    try:
        conn = psycopg2.connect(PG_URI)
    except Exception as e:
        log(logger, "error", "extract", "connection", f"Postgres connection failed: {e}")
        sys.exit(1)

    log(logger, "info", "extract", "connection", "Postgres connected")

    # ── CHECKPOINT 1: Discovery ────────────────────────────────────────────────
    with conn.cursor() as cur:
        cur.execute(COUNT_QUERY, PARAMS)
        row = cur.fetchone()
        cols = [desc[0] for desc in cur.description]
        discovery = dict(zip(cols, row))

    log(logger, "info", "extract", "discovery", "Discovery metrics collected",
        records=int(discovery["total"]))

    print("\n── CHECKPOINT 1: Discovery ──────────────────────────────────")
    for k, v in discovery.items():
        print(f"  {k:25s}: {v}")
    print("─────────────────────────────────────────────────────────────")

    checkpoint_confirm("Discovery complete. Review metrics above.")

    # ── CHECKPOINT 2: Sampling ─────────────────────────────────────────────────
    sample_df = pd.read_sql(SAMPLE_QUERY, conn, params=PARAMS)
    log(logger, "info", "extract", "sampling", "Sample extracted", records=len(sample_df))

    print("\n── CHECKPOINT 2: Sample (first 5 rows) ─────────────────────")
    print(sample_df.head().to_string(index=False))
    print(f"\n  Columns          : {list(sample_df.columns)}")
    print(f"  Null donor keys  : {sample_df['normalized_donor_key'].isna().sum()}")
    print(f"  Amount range     : ${sample_df['amount'].min():,.2f} – ${sample_df['amount'].max():,.2f}")
    print(f"  Date range       : {sample_df['date'].min()} → {sample_df['date'].max()}")
    print("─────────────────────────────────────────────────────────────")

    checkpoint_confirm("Sample looks good?")

    # ── CHECKPOINT 3: Full Run ─────────────────────────────────────────────────
    log(logger, "info", "extract", "full_run_start", f"Starting full extraction for {CITY}")

    chunks = []
    cols = None
    with conn.cursor(name="extract_cursor") as cur:  # server-side cursor = low memory footprint
        cur.itersize = BATCH_SIZE
        cur.execute(EXTRACT_QUERY, PARAMS)
        batch_num = 0
        while True:
            rows = cur.fetchmany(BATCH_SIZE)
            if not rows:
                break
            if cols is None:
                cols = [desc[0] for desc in cur.description]  # populated after first fetch
            batch_num += 1
            chunk = pd.DataFrame(rows, columns=cols)
            chunks.append(chunk)
            log(logger, "info", "extract", "batch",
                f"Batch {batch_num} fetched", records=len(chunk))
            print(f"  ... batch {batch_num}: {len(chunk):,} rows")

    df = pd.concat(chunks, ignore_index=True)
    conn.close()

    log(logger, "info", "extract", "full_run_complete", "Extraction complete", records=len(df))
    print(f"\n── Full extraction complete: {len(df):,} rows ───────────────")

    # ── Write parquet ──────────────────────────────────────────────────────────
    df.to_parquet(OUTPUT_FILE, index=False)
    log(logger, "info", "extract", "write", f"Parquet written: {OUTPUT_FILE}", records=len(df))

    # ── CHECKPOINT 4: Handoff ──────────────────────────────────────────────────
    handoff = {
        "output_file":         str(OUTPUT_FILE),
        "city":                CITY,
        "total_records":       len(df),
        "distinct_donors":     int(df["normalized_donor_key"].nunique()),
        "distinct_committees": int(df["committee_cd"].nunique()),
        "date_range":          f"{df['date'].min()} → {df['date'].max()}",
        "amount_total":        float(df["amount"].sum()),
        "null_donor_keys":     int(df["normalized_donor_key"].isna().sum()),
        "next_step":           "Run transform.py against output file above",
    }
    log(logger, "info", "extract", "handoff", json.dumps(handoff))

    print("\n── CHECKPOINT 4: Handoff ────────────────────────────────────")
    for k, v in handoff.items():
        print(f"  {k:25s}: {v}")
    print("─────────────────────────────────────────────────────────────")
    print("\n✓ extract.py complete. Next: transform.py\n")


if __name__ == "__main__":
    main()
