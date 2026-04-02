"""
load.py — Write enriched graph data to Neo4j AuraDB.

Pipeline position: THIRD
Input:  three parquet files from etl/4validated/ (output of transform.py)
            - donors_{city}_{timestamp}.parquet
            - committees_{city}_{timestamp}.parquet
            - edges_{city}_{timestamp}.parquet
Output: nodes + relationships in AuraDB
        confirmation records → etl/5final/

Usage:
    python load.py                    # auto-selects latest validated files
    ETL_CITY_SLUG=johnston python load.py

Load order (non-negotiable):
    1. Committee nodes   — edges reference these; must exist first
    2. Donor nodes       — edges reference these
    3. CONTRIBUTED_TO    — both endpoints must be present before relationship write

Constraints required before first run (already applied via neo4j-aura MCP):
    CREATE CONSTRAINT donor_id_unique IF NOT EXISTS FOR (d:Donor) REQUIRE d.canonical_donor_id IS UNIQUE
    CREATE CONSTRAINT committee_cd_unique IF NOT EXISTS FOR (c:Committee) REQUIRE c.committee_cd IS UNIQUE
    CREATE INDEX donor_betweenness IF NOT EXISTS FOR (d:Donor) ON (d.betweenness_score)
    CREATE FULLTEXT INDEX donorSearch IF NOT EXISTS FOR (d:Donor) ON EACH [d.display_name]
    CREATE FULLTEXT INDEX committeeSearch IF NOT EXISTS FOR (c:Committee) ON EACH [c.committee_nm]

Checkpoints:
    1. Pre-load    — confirm file selection + record counts before any write
    2. Post-nodes  — confirm node counts in AuraDB after donor + committee write
    3. Post-edges  — confirm relationship count after CONTRIBUTED_TO write
    4. Handoff     — final summary + verification queries
"""

import os
import sys
import json
import logging
import decimal
import pandas as pd
from datetime import datetime, timezone
from pathlib import Path
from dotenv import load_dotenv
from neo4j import GraphDatabase

# ── Environment ────────────────────────────────────────────────────────────────

load_dotenv(Path(__file__).parent.parent / "Neo4j-4416fe7c-Created-2026-03-24.txt")

NEO4J_URI      = os.getenv("NEO4J_URI")
NEO4J_USERNAME = os.getenv("NEO4J_USERNAME")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD")
NEO4J_DATABASE = os.getenv("NEO4J_DATABASE")

BATCH_SIZE = 500   # AuraDB Free Tier safe limit — do not increase

ETL_ROOT    = Path(__file__).parent
VALIDATED   = ETL_ROOT / "4validated"
FINAL       = ETL_ROOT / "5final"
LOG_DIR     = ETL_ROOT / "logs"
FINAL.mkdir(exist_ok=True)
LOG_DIR.mkdir(exist_ok=True)

TIMESTAMP = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

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
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "log_level": level,
        "operation": operation,
        "step_name": step,
        "message":   message,
    }
    if records is not None:
        entry["records_processed"] = records
    getattr(logger, level.lower())(json.dumps(entry))

# ── Checkpoints ────────────────────────────────────────────────────────────────

def checkpoint_confirm(prompt: str) -> None:
    response = input(f"\n{prompt}\nProceed? [yes/no]: ").strip().lower()
    if response not in ("yes", "y"):
        print("Aborted by user.")
        sys.exit(0)

# ── Input file resolution ──────────────────────────────────────────────────────

def resolve_input_files() -> tuple[Path, Path, Path]:
    """
    Auto-select the most recent validated parquet trio.
    ETL_CITY_SLUG env var narrows selection if set (e.g. 'johnston').
    """
    slug = os.getenv("ETL_CITY_SLUG", "")

    def latest(pattern: str) -> Path:
        candidates = sorted(VALIDATED.glob(pattern), reverse=True)
        if not candidates:
            print(f"ERROR: No files matching {pattern} in {VALIDATED}")
            sys.exit(1)
        return candidates[0]

    prefix = f"*{slug}*" if slug else "*"
    donors_file     = latest(f"donors_{prefix}.parquet")
    committees_file = latest(f"committees_{prefix}.parquet")
    edges_file      = latest(f"edges_{prefix}.parquet")

    return donors_file, committees_file, edges_file

# ── Batch writer ───────────────────────────────────────────────────────────────

def write_batches(session, rows: list[dict], query: str, label: str, logger) -> int:
    """Write rows in batches of BATCH_SIZE. Returns total rows written."""
    total = 0
    for i in range(0, len(rows), BATCH_SIZE):
        batch = rows[i : i + BATCH_SIZE]
        session.run(query, rows=batch)
        total += len(batch)
        log(logger, "info", "load", f"batch_{label}",
            f"{label} batch {i // BATCH_SIZE + 1}: {len(batch)} rows", records=total)
        print(f"  ... {label} batch {i // BATCH_SIZE + 1}: {total:,} / {len(rows):,}")
    return total

# ── Cypher queries ─────────────────────────────────────────────────────────────

MERGE_COMMITTEE = """
UNWIND $rows AS row
MERGE (c:Committee {committee_cd: row.committee_cd})
ON CREATE SET
    c.committee_nm        = row.committee_nm,
    c.committee_type      = row.committee_type,
    c.total_received      = row.total_received,
    c.donor_count         = row.donor_count,
    c.community_id        = row.community_id,
    c.first_receipt_date  = date(row.first_receipt_date),
    c.last_receipt_date   = date(row.last_receipt_date)
ON MATCH SET
    c.total_received      = row.total_received,
    c.donor_count         = row.donor_count,
    c.community_id        = row.community_id
"""

MERGE_DONOR = """
UNWIND $rows AS row
MERGE (d:Donor {canonical_donor_id: row.canonical_donor_id})
ON CREATE SET
    d.display_name              = row.display_name,
    d.donor_type                = row.donor_type,
    d.total_given               = row.total_given,
    d.committee_count           = row.committee_count,
    d.betweenness_score         = row.betweenness_score,
    d.community_id              = row.community_id,
    d.first_contribution_date   = date(row.first_contribution_date),
    d.last_contribution_date    = date(row.last_contribution_date)
ON MATCH SET
    d.betweenness_score         = row.betweenness_score,
    d.total_given               = row.total_given,
    d.committee_count           = row.committee_count,
    d.community_id              = row.community_id
"""

MERGE_EDGE = """
UNWIND $rows AS row
MATCH (d:Donor {canonical_donor_id: row.donor_id})
MATCH (c:Committee {committee_cd: row.committee_cd})
MERGE (d)-[r:CONTRIBUTED_TO]->(c)
ON CREATE SET
    r.total_amount      = row.total_amount,
    r.transaction_count = row.transaction_count,
    r.first_date        = date(row.first_date),
    r.last_date         = date(row.last_date),
    r.max_single_gift   = row.max_single_gift
ON MATCH SET
    r.total_amount      = r.total_amount + row.total_amount,
    r.transaction_count = r.transaction_count + row.transaction_count,
    r.first_date        = CASE WHEN date(row.first_date) < r.first_date
                               THEN date(row.first_date) ELSE r.first_date END,
    r.last_date         = CASE WHEN date(row.last_date) > r.last_date
                               THEN date(row.last_date) ELSE r.last_date END,
    r.max_single_gift   = CASE WHEN row.max_single_gift > r.max_single_gift
                               THEN row.max_single_gift ELSE r.max_single_gift END
"""

COUNT_QUERY = """
MATCH (d:Donor) WITH count(d) AS donors
MATCH (c:Committee) WITH donors, count(c) AS committees
MATCH ()-[r:CONTRIBUTED_TO]->() RETURN donors, committees, count(r) AS relationships
"""

# ── Serialise rows ─────────────────────────────────────────────────────────────

def df_to_rows(df: pd.DataFrame) -> list[dict]:
    """Convert DataFrame to list of plain dicts safe for the Neo4j driver."""
    records = []
    for row in df.itertuples(index=False):
        d = row._asdict()
        # Convert any pandas Timestamp / date objects to ISO strings
        for k, v in d.items():
            if isinstance(v, decimal.Decimal):
                d[k] = float(v)
            elif hasattr(v, "isoformat"):
                d[k] = str(v)
            elif pd.isna(v) if not isinstance(v, (list, dict)) else False:
                d[k] = None
        records.append(d)
    return records

# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    logger = get_logger("load")
    log(logger, "info", "load", "start", "load.py starting")

    # ── Resolve input files ────────────────────────────────────────────────────
    donors_file, committees_file, edges_file = resolve_input_files()

    donors_df     = pd.read_parquet(donors_file)
    committees_df = pd.read_parquet(committees_file)
    edges_df      = pd.read_parquet(edges_file)

    city_slug = donors_file.stem.split("_")[1]  # e.g. "johnston"

    log(logger, "info", "load", "files_loaded",
        f"Donors: {len(donors_df):,} | Committees: {len(committees_df):,} | Edges: {len(edges_df):,}")

    # ── CHECKPOINT 1: Pre-load ─────────────────────────────────────────────────
    print("\n── CHECKPOINT 1: Pre-load ───────────────────────────────────")
    print(f"  donors_file       : {donors_file.name}")
    print(f"  committees_file   : {committees_file.name}")
    print(f"  edges_file        : {edges_file.name}")
    print(f"  donors            : {len(donors_df):,}")
    print(f"  committees        : {len(committees_df):,}")
    print(f"  edges             : {len(edges_df):,}")
    print(f"  target            : {NEO4J_URI}")
    print(f"  database          : {NEO4J_DATABASE}")
    print(f"  batch_size        : {BATCH_SIZE}")
    print("─────────────────────────────────────────────────────────────")

    checkpoint_confirm("Files confirmed. Begin AuraDB write?")

    # ── Connect ────────────────────────────────────────────────────────────────
    try:
        driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USERNAME, NEO4J_PASSWORD))
        driver.verify_connectivity()
    except Exception as e:
        log(logger, "error", "load", "connection", f"AuraDB connection failed: {e}")
        sys.exit(1)

    log(logger, "info", "load", "connection", "AuraDB connected")

    with driver.session(database=NEO4J_DATABASE) as session:

        # ── Write committees first ─────────────────────────────────────────────
        print("\n  Writing Committee nodes...")
        committee_rows = df_to_rows(committees_df)
        written_committees = write_batches(session, committee_rows, MERGE_COMMITTEE, "committees", logger)
        log(logger, "info", "load", "committees_complete",
            "Committee nodes written", records=written_committees)

        # ── Write donors ───────────────────────────────────────────────────────
        print("\n  Writing Donor nodes...")
        donor_rows = df_to_rows(donors_df)
        written_donors = write_batches(session, donor_rows, MERGE_DONOR, "donors", logger)
        log(logger, "info", "load", "donors_complete",
            "Donor nodes written", records=written_donors)

        # ── CHECKPOINT 2: Post-nodes ───────────────────────────────────────────
        result = session.run("MATCH (d:Donor) RETURN count(d) AS n").single()
        aura_donors = result["n"]
        result = session.run("MATCH (c:Committee) RETURN count(c) AS n").single()
        aura_committees = result["n"]

        print("\n── CHECKPOINT 2: Post-nodes ─────────────────────────────────")
        print(f"  Donor nodes in AuraDB     : {aura_donors:,}  (expected {len(donors_df):,})")
        print(f"  Committee nodes in AuraDB : {aura_committees:,}  (expected {len(committees_df):,})")
        if aura_donors != len(donors_df) or aura_committees != len(committees_df):
            print("  ⚠️  COUNT MISMATCH — check logs before proceeding")
        print("─────────────────────────────────────────────────────────────")

        checkpoint_confirm("Node counts look right. Write relationships?")

        # ── Write edges ────────────────────────────────────────────────────────
        print("\n  Writing CONTRIBUTED_TO relationships...")
        edge_rows = df_to_rows(edges_df)
        written_edges = write_batches(session, edge_rows, MERGE_EDGE, "edges", logger)
        log(logger, "info", "load", "edges_complete",
            "CONTRIBUTED_TO relationships written", records=written_edges)

        # ── CHECKPOINT 3: Post-edges ───────────────────────────────────────────
        result = session.run(
            "MATCH ()-[r:CONTRIBUTED_TO]->() RETURN count(r) AS n"
        ).single()
        aura_edges = result["n"]

        print("\n── CHECKPOINT 3: Post-edges ─────────────────────────────────")
        print(f"  CONTRIBUTED_TO in AuraDB  : {aura_edges:,}  (expected {len(edges_df):,})")
        if aura_edges != len(edges_df):
            print("  ⚠️  EDGE COUNT MISMATCH — some endpoints may be missing")
        print("─────────────────────────────────────────────────────────────")

    driver.close()

    # ── Write confirmation record ──────────────────────────────────────────────
    handoff = {
        "city":              city_slug,
        "timestamp":         TIMESTAMP,
        "donors_written":    written_donors,
        "committees_written":written_committees,
        "edges_written":     written_edges,
        "aura_donors":       aura_donors,
        "aura_committees":   aura_committees,
        "aura_edges":        aura_edges,
        "target_uri":        NEO4J_URI,
        "database":          NEO4J_DATABASE,
        "next_step":         "Verify in Neo4j Bloom — run CQ1 and CQ5 queries",
    }
    log(logger, "info", "load", "handoff", json.dumps(handoff))

    confirmation_file = FINAL / f"load_confirmation_{city_slug}_{TIMESTAMP}.json"
    confirmation_file.write_text(json.dumps(handoff, indent=2))

    # ── CHECKPOINT 4: Handoff ──────────────────────────────────────────────────
    print("\n── CHECKPOINT 4: Handoff ────────────────────────────────────")
    for k, v in handoff.items():
        print(f"  {k:22s}: {v}")
    print("─────────────────────────────────────────────────────────────")
    print(f"\n✓ load.py complete. Confirmation record: {confirmation_file.name}")
    print("  Next: open Neo4j Bloom and run CQ1 + CQ5 queries.\n")


if __name__ == "__main__":
    main()
