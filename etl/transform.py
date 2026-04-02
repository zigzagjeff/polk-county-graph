"""
transform.py — Build NetworkX graph, compute betweenness centrality + Louvain communities.

Pipeline position: SECOND
Input:  parquet file from etl/2extracted/ (output of extract.py)
Output: three parquet files → etl/4validated/
        - donors_{city}_{timestamp}.parquet
        - committees_{city}_{timestamp}.parquet
        - edges_{city}_{timestamp}.parquet

Usage:
    python transform.py                                    # auto-selects latest parquet in 2extracted/
    ETL_INPUT=etl/2extracted/iowa_contributions_extract_johnston_20260401_203153.parquet python transform.py

Checkpoints:
    1. Pre-build   — confirm input file + record count before graph construction
    2. Pre-compute — confirm graph size before betweenness (slow step)
    3. Post-compute — show betweenness distribution + top donors
    4. Handoff     — output file summary + next step

Cycle 1 scope: CQ1 (betweenness centrality) + CQ5 (Louvain community detection)
"""

import os
import sys
import json
import logging
import pandas as pd
import networkx as nx
from datetime import datetime, timezone
from pathlib import Path
from dotenv import load_dotenv

# ── Environment ────────────────────────────────────────────────────────────────

load_dotenv(Path(__file__).parent.parent / "Postgres-iowa_contributors-local.txt")

ETL_ROOT    = Path(__file__).parent
INPUT_DIR   = ETL_ROOT / "2extracted"
OUTPUT_DIR  = ETL_ROOT / "4validated"
LOG_DIR     = ETL_ROOT / "logs"
OUTPUT_DIR.mkdir(exist_ok=True)
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

def resolve_input_file() -> Path:
    """
    Use ETL_INPUT env var if set, otherwise auto-select the most recent
    parquet in 2extracted/.
    """
    env_input = os.getenv("ETL_INPUT")
    if env_input:
        p = Path(env_input)
        if not p.exists():
            print(f"ERROR: ETL_INPUT file not found: {p}")
            sys.exit(1)
        return p

    candidates = sorted(INPUT_DIR.glob("iowa_contributions_extract_*.parquet"), reverse=True)
    if not candidates:
        print(f"ERROR: No parquet files found in {INPUT_DIR}")
        sys.exit(1)
    return candidates[0]  # most recent by filename timestamp

# ── Graph construction ─────────────────────────────────────────────────────────

def build_graph(df: pd.DataFrame) -> tuple[nx.DiGraph, pd.DataFrame]:
    """
    Build directed graph: Donor → Committee.
    Aggregates all contributions per canonical donor-committee pair.
    Returns the graph and the edge DataFrame for downstream use.
    """
    edge_agg = (
        df.groupby(["normalized_donor_key", "committee_cd"])
        .agg(
            total_amount=("amount", "sum"),
            transaction_count=("contribution_id", "count"),
            first_date=("date", "min"),
            last_date=("date", "max"),
            max_single_gift=("amount", "max"),
        )
        .reset_index()
    )

    G = nx.DiGraph()
    for _, row in edge_agg.iterrows():
        G.add_edge(
            row["normalized_donor_key"],
            row["committee_cd"],
            total_amount=float(row["total_amount"]),
            transaction_count=int(row["transaction_count"]),
            first_date=str(row["first_date"]),
            last_date=str(row["last_date"]),
            max_single_gift=float(row["max_single_gift"]),
        )

    return G, edge_agg

# ── Betweenness centrality (CQ1) ───────────────────────────────────────────────

def compute_betweenness(G: nx.DiGraph) -> dict:
    """
    Normalized betweenness centrality on undirected projection.
    Donors act as bridges between committees — undirected captures this.
    O(VE) complexity: Johnston (~5,600 nodes) runs in seconds.
    Des Moines (~34,000 nodes) will take 5–15 minutes — not a hang.
    """
    G_undirected = G.to_undirected()
    return nx.betweenness_centrality(G_undirected, normalized=True)

# ── Louvain community detection (CQ5) ─────────────────────────────────────────

def compute_louvain(G: nx.DiGraph) -> dict:
    """
    Louvain community detection on undirected projection.
    Returns dict of node → community_id (integer).
    Communities are numbered 0..N-1 by size descending.
    """
    G_undirected = G.to_undirected()
    communities = nx.community.louvain_communities(G_undirected, seed=42)
    # Sort largest community first for stable, human-readable IDs
    communities_sorted = sorted(communities, key=len, reverse=True)
    node_to_community = {}
    for community_id, members in enumerate(communities_sorted):
        for node in members:
            node_to_community[node] = community_id
    return node_to_community

# ── Display name derivation ────────────────────────────────────────────────────

def derive_display_name(row: pd.Series) -> str:
    """
    Organization → use normalized_organization_nm.
    Individual   → LAST, FIRST (or just last if first is missing).
    """
    if pd.notna(row.get("normalized_organization_nm")) and str(row["normalized_organization_nm"]).strip():
        return str(row["normalized_organization_nm"]).strip()
    last  = str(row.get("last_nm", "") or "").strip()
    first = str(row.get("first_nm", "") or "").strip()
    if last and first:
        return f"{last}, {first}"
    return last or row["normalized_donor_key"]

def derive_donor_type(row: pd.Series) -> str:
    if pd.notna(row.get("normalized_organization_nm")) and str(row["normalized_organization_nm"]).strip():
        return "Organization"
    return "Individual"

# ── Node table builders ────────────────────────────────────────────────────────

def build_donor_nodes(
    df: pd.DataFrame,
    betweenness: dict,
    communities: dict,
) -> pd.DataFrame:
    """
    One row per canonical donor. Enriched with betweenness + community.
    canonical_donor_id = normalized_donor_key (the graph node ID).
    """
    donor_agg = (
        df.groupby("normalized_donor_key")
        .agg(
            total_given=("amount", "sum"),
            committee_count=("committee_cd", "nunique"),
            first_contribution_date=("date", "min"),
            last_contribution_date=("date", "max"),
            # Take first non-null value for name fields
            first_nm=("first_nm", "first"),
            last_nm=("last_nm", "first"),
            normalized_organization_nm=("normalized_organization_nm", "first"),
        )
        .reset_index()
    )

    donor_agg["display_name"]     = donor_agg.apply(derive_display_name, axis=1)
    donor_agg["donor_type"]       = donor_agg.apply(derive_donor_type, axis=1)
    donor_agg["betweenness_score"] = donor_agg["normalized_donor_key"].map(betweenness).fillna(0.0)
    donor_agg["community_id"]     = donor_agg["normalized_donor_key"].map(communities).fillna(-1).astype(int)

    return donor_agg[[
        "normalized_donor_key",   # → canonical_donor_id in Neo4j
        "display_name",
        "donor_type",
        "total_given",
        "committee_count",
        "betweenness_score",
        "community_id",
        "first_contribution_date",
        "last_contribution_date",
    ]].rename(columns={"normalized_donor_key": "canonical_donor_id"})


def build_committee_nodes(
    df: pd.DataFrame,
    communities: dict,
) -> pd.DataFrame:
    """
    One row per committee. Enriched with community_id from Louvain.
    """
    committee_agg = (
        df.groupby("committee_cd")
        .agg(
            committee_nm=("normalized_committee_nm", "first"),
            committee_type=("committee_type", "first"),
            total_received=("amount", "sum"),
            donor_count=("normalized_donor_key", "nunique"),
            first_receipt_date=("date", "min"),
            last_receipt_date=("date", "max"),
        )
        .reset_index()
    )

    committee_agg["community_id"] = committee_agg["committee_cd"].map(communities).fillna(-1).astype(int)

    return committee_agg[[
        "committee_cd",
        "committee_nm",
        "committee_type",
        "total_received",
        "donor_count",
        "community_id",
        "first_receipt_date",
        "last_receipt_date",
    ]]


def build_edge_table(edge_agg: pd.DataFrame) -> pd.DataFrame:
    """
    One row per donor-committee pair. These become :CONTRIBUTED_TO relationships.
    Rename normalized_donor_key → donor_id for clarity in load.py.
    """
    return edge_agg.rename(columns={"normalized_donor_key": "donor_id"})[[
        "donor_id",
        "committee_cd",
        "total_amount",
        "transaction_count",
        "first_date",
        "last_date",
        "max_single_gift",
    ]]

# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    logger = get_logger("transform")
    log(logger, "info", "transform", "start", "transform.py starting")

    # ── Resolve input ──────────────────────────────────────────────────────────
    input_file = resolve_input_file()
    df = pd.read_parquet(input_file)
    city_slug = input_file.stem.split("_extract_")[1].rsplit("_", 2)[0]  # e.g. "johnston"

    log(logger, "info", "transform", "input_loaded",
        f"Loaded: {input_file.name}", records=len(df))

    # ── CHECKPOINT 1: Pre-build ────────────────────────────────────────────────
    print("\n── CHECKPOINT 1: Pre-build ──────────────────────────────────")
    print(f"  input_file        : {input_file.name}")
    print(f"  total_records     : {len(df):,}")
    print(f"  distinct_donors   : {df['normalized_donor_key'].nunique():,}")
    print(f"  distinct_committees: {df['committee_cd'].nunique():,}")
    print(f"  date_range        : {df['date'].min()} → {df['date'].max()}")
    print(f"  amount_total      : ${df['amount'].sum():,.2f}")
    print("─────────────────────────────────────────────────────────────")

    checkpoint_confirm("Input looks correct. Build graph?")

    # ── Build graph ────────────────────────────────────────────────────────────
    log(logger, "info", "transform", "graph_build_start", "Building NetworkX DiGraph")
    G, edge_agg = build_graph(df)
    log(logger, "info", "transform", "graph_build_complete",
        f"Graph built: {G.number_of_nodes()} nodes, {G.number_of_edges()} edges")

    donor_nodes_in_graph    = sum(1 for n in G.nodes() if n in set(df["normalized_donor_key"]))
    committee_nodes_in_graph = sum(1 for n in G.nodes() if n in set(df["committee_cd"]))

    # ── CHECKPOINT 2: Pre-compute ──────────────────────────────────────────────
    print("\n── CHECKPOINT 2: Pre-compute ────────────────────────────────")
    print(f"  total_nodes       : {G.number_of_nodes():,}  ({donor_nodes_in_graph:,} donors + {committee_nodes_in_graph:,} committees)")
    print(f"  total_edges       : {G.number_of_edges():,}  (donor→committee pairs)")
    print(f"  graph_density     : {nx.density(G):.6f}")
    print(f"  weakly_connected  : {nx.number_weakly_connected_components(G):,} components")
    print()
    print("  Next: betweenness centrality (may take a few minutes for Des Moines)")
    print("  Then: Louvain community detection")
    print("─────────────────────────────────────────────────────────────")

    checkpoint_confirm("Graph structure looks right. Run betweenness + Louvain?")

    # ── Betweenness centrality (CQ1) ───────────────────────────────────────────
    log(logger, "info", "transform", "betweenness_start", "Computing betweenness centrality")
    print("\n  Computing betweenness centrality...")
    betweenness = compute_betweenness(G)
    log(logger, "info", "transform", "betweenness_complete",
        f"Betweenness computed for {len(betweenness):,} nodes")

    # ── Louvain community detection (CQ5) ──────────────────────────────────────
    log(logger, "info", "transform", "louvain_start", "Computing Louvain communities")
    print("  Computing Louvain communities...")
    communities = compute_louvain(G)
    num_communities = len(set(communities.values()))
    log(logger, "info", "transform", "louvain_complete",
        f"Louvain complete: {num_communities} communities detected")

    # ── CHECKPOINT 3: Post-compute ─────────────────────────────────────────────
    scores = sorted(betweenness.values(), reverse=True)
    nonzero = [s for s in scores if s > 0]

    # Top 10 donors by betweenness
    donor_keys = set(df["normalized_donor_key"])
    top_donors = sorted(
        [(n, s) for n, s in betweenness.items() if n in donor_keys],
        key=lambda x: x[1],
        reverse=True
    )[:10]

    print("\n── CHECKPOINT 3: Post-compute ───────────────────────────────")
    print(f"  nodes_scored      : {len(scores):,}")
    print(f"  nonzero_scores    : {len(nonzero):,}")
    print(f"  max_betweenness   : {scores[0]:.6f}")
    print(f"  median_betweenness: {scores[len(scores)//2]:.6f}")
    print(f"  communities       : {num_communities}")
    print()
    print("  Top 10 donors by betweenness centrality:")
    for rank, (node, score) in enumerate(top_donors, 1):
        print(f"    {rank:2d}. {node:<40s} {score:.6f}")
    print("─────────────────────────────────────────────────────────────")

    checkpoint_confirm("Results look valid. Write output files?")

    # ── Build output tables ────────────────────────────────────────────────────
    log(logger, "info", "transform", "tables_start", "Building output node/edge tables")

    donors_df     = build_donor_nodes(df, betweenness, communities)
    committees_df = build_committee_nodes(df, communities)
    edges_df      = build_edge_table(edge_agg)

    # ── Write parquet files ────────────────────────────────────────────────────
    donors_file     = OUTPUT_DIR / f"donors_{city_slug}_{TIMESTAMP}.parquet"
    committees_file = OUTPUT_DIR / f"committees_{city_slug}_{TIMESTAMP}.parquet"
    edges_file      = OUTPUT_DIR / f"edges_{city_slug}_{TIMESTAMP}.parquet"

    donors_df.to_parquet(donors_file, index=False)
    committees_df.to_parquet(committees_file, index=False)
    edges_df.to_parquet(edges_file, index=False)

    log(logger, "info", "transform", "write_donors",
        f"Donors written: {donors_file.name}", records=len(donors_df))
    log(logger, "info", "transform", "write_committees",
        f"Committees written: {committees_file.name}", records=len(committees_df))
    log(logger, "info", "transform", "write_edges",
        f"Edges written: {edges_file.name}", records=len(edges_df))

    # ── CHECKPOINT 4: Handoff ──────────────────────────────────────────────────
    handoff = {
        "city":              city_slug,
        "donors_file":       str(donors_file),
        "committees_file":   str(committees_file),
        "edges_file":        str(edges_file),
        "donor_count":       len(donors_df),
        "committee_count":   len(committees_df),
        "edge_count":        len(edges_df),
        "communities":       num_communities,
        "top_donor":         top_donors[0][0] if top_donors else "n/a",
        "top_betweenness":   round(top_donors[0][1], 6) if top_donors else 0,
        "next_step":         "Run load.py — remember to create AuraDB constraints first",
    }
    log(logger, "info", "transform", "handoff", json.dumps(handoff))

    print("\n── CHECKPOINT 4: Handoff ────────────────────────────────────")
    for k, v in handoff.items():
        print(f"  {k:22s}: {v}")
    print("─────────────────────────────────────────────────────────────")
    print("\n✓ transform.py complete. Next: load.py\n")


if __name__ == "__main__":
    main()
