"""
build_dashboard_db.py
=====================

Rebuilds the Evidence dashboard's DuckDB
(`dashboard/app/sources/fansphere/fansphere.duckdb`) from the canonical
`outputs/` artifacts.

Why this exists: the dashboard DuckDB was originally hand-loaded in a sandbox
session (see `dashboard/HANDOFF.md`) with no committed loader, so refreshing the
dashboard after a pipeline change was not reproducible. This script closes that
gap. Run it whenever `outputs/` change, then refresh the Evidence cache:

    python -m src.build_dashboard_db
    cd dashboard/app && npm run sources

Tables (mirrors the original schema the Evidence `.sql` files select from):
  matches, goal_events, fan_segments, match_sentiment, ranking,
  comments_enriched, comments_linked,
  engagement_raw  = the join_with_stage2 output (stage3_engagement_enriched.csv),
  engagement      = engagement_raw ⨝ matches + match_label + score_str.

Requires: duckdb  (pip install duckdb)
"""

from __future__ import annotations

import logging
from pathlib import Path

import duckdb

PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUT = PROJECT_ROOT / "outputs"
DB = PROJECT_ROOT / "dashboard" / "app" / "sources" / "fansphere" / "fansphere.duckdb"

logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")
logger = logging.getLogger(__name__)

CSV_TABLES = {
    "matches":         "stage2_matches.csv",
    "goal_events":     "stage2_goal_events.csv",
    "fan_segments":    "fan_segments.csv",
    "match_sentiment": "stage3_match_sentiment.csv",
    "ranking":         "stage3_ranking.csv",
    "engagement_raw":  "stage3_engagement_enriched.csv",
}
PARQUET_TABLES = {
    "comments_enriched": "stage3_comments_enriched.parquet",
    "comments_linked":   "stage3_comments_linked.parquet",
}


def main() -> None:
    missing = [f for f in list(CSV_TABLES.values()) + list(PARQUET_TABLES.values())
               if not (OUT / f).exists()]
    if missing:
        raise FileNotFoundError(f"Missing outputs: {missing}. Run the pipeline first.")
    if not DB.parent.exists():
        raise FileNotFoundError(f"Dashboard source dir not found: {DB.parent}")

    con = duckdb.connect(str(DB))
    try:
        for table, fname in CSV_TABLES.items():
            p = (OUT / fname).as_posix()
            con.execute(f"CREATE OR REPLACE TABLE {table} AS SELECT * FROM read_csv_auto('{p}', header=true)")
        for table, fname in PARQUET_TABLES.items():
            p = (OUT / fname).as_posix()
            con.execute(f"CREATE OR REPLACE TABLE {table} AS SELECT * FROM read_parquet('{p}')")

        # engagement is a VIEW over engagement_raw + matches (matches the original
        # schema) — it auto-reflects the refreshed base tables.
        con.execute("DROP VIEW IF EXISTS engagement")
        con.execute("DROP TABLE IF EXISTS engagement")
        con.execute("""
            CREATE VIEW engagement AS
            SELECT r.*,
                   m.home_team, m.away_team, m.match_date, m.home_score, m.away_score,
                   m.is_rivalry, m.total_goals,
                   m.home_team || ' vs ' || m.away_team AS match_label,
                   CAST(m.home_score AS INTEGER) || '-' || CAST(m.away_score AS INTEGER) AS score_str
            FROM engagement_raw r
            LEFT JOIN matches m USING (match_id)
        """)

        logger.info("Rebuilt %s", DB)
        for t in ("matches", "goal_events", "fan_segments", "match_sentiment", "ranking",
                  "engagement_raw", "engagement", "comments_enriched", "comments_linked"):
            n = con.execute(f"SELECT count(*) FROM {t}").fetchone()[0]
            logger.info("  %-18s %d rows", t, n)
        logger.info("Segment sizes: %s",
                    con.execute("select segment, count(*) from fan_segments group by 1 order by 2 desc").fetchall())
        logger.info("Top fixture (rank 1): %s",
                    con.execute("select home_team, away_team, is_rivalry from ranking where rank=1").fetchone())
        # Sanity: is_rivalry must be usable as a boolean by the dashboard.
        rc = con.execute("select count(*) from matches where is_rivalry").fetchone()[0]
        logger.info("Rivalry matches (boolean check): %d", rc)
    finally:
        con.close()


if __name__ == "__main__":
    main()
