"""
build_stage3_outputs.py
=======================

Fast-path regenerator for the Stage 3 engagement outputs.

The Stage 3 notebook (`notebooks/stage3_audience_sentiment.ipynb`) is the
canonical pipeline, but it re-links ~907K comments from scratch on every run.
When only a *downstream* weight changes — e.g. the football/fan blend in
`join_with_stage2` — there's no need to re-link or re-score. This script reuses
the cached link table (`stage3_comments_linked.parquet`) and the already-scored
enriched parquet, and re-runs just:

    aggregate_per_match -> compute_engagement_score -> join_with_stage2 -> ranking

It mirrors the notebook's "Save Stage 3 outputs" cell exactly, so the schema the
Evidence dashboard consumes is preserved.

Regenerates:
  outputs/stage3_match_sentiment.csv
  outputs/stage3_engagement_enriched.csv
  outputs/stage3_ranking.csv

Run:  python -m src.build_stage3_outputs
"""

from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

from src.engagement import (
    EngagementWeights,
    aggregate_per_match,
    compute_engagement_score,
    join_with_stage2,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUT = PROJECT_ROOT / "outputs"
LINKED = OUT / "stage3_comments_linked.parquet"
ENRICHED = OUT / "stage3_comments_enriched.parquet"
STAGE2_MATCHES = OUT / "stage2_matches.csv"
STAGE2_ENG = OUT / "stage2_engagement.csv"

logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")
logger = logging.getLogger(__name__)


def main() -> None:
    for p in (LINKED, ENRICHED, STAGE2_MATCHES, STAGE2_ENG):
        if not p.exists():
            raise FileNotFoundError(
                f"Missing {p}. Run the Stage 3 notebook / enrichment first."
            )

    links = pd.read_parquet(LINKED)
    enriched = pd.read_parquet(ENRICHED, columns=["comment_id", "sentiment_score"])
    # comments_with_sentiment needs unique [id, sentiment]; sentiment is per-comment.
    scored = (
        enriched.drop_duplicates("comment_id")
        .rename(columns={"comment_id": "id", "sentiment_score": "sentiment"})[["id", "sentiment"]]
    )
    matches = pd.read_csv(STAGE2_MATCHES)
    stage2_engagement = pd.read_csv(STAGE2_ENG)

    # Fan-side aggregation + score (unchanged production weights).
    per_match = aggregate_per_match(links, scored)
    per_match = compute_engagement_score(
        per_match,
        weights=EngagementWeights(volume=0.45, affect=0.20, volatility=0.25, reach=0.10),
    )

    # Blend with Stage 2 — join_with_stage2 now defaults to the fan-biased
    # 0.35/0.65 weights (AutoResearch H3.1).
    combined = join_with_stage2(per_match, stage2_engagement)

    per_match.to_csv(OUT / "stage3_match_sentiment.csv", index=False)
    combined.to_csv(OUT / "stage3_engagement_enriched.csv", index=False)

    # Ranking — mirrors the notebook's save cell.
    ranking_base = combined.sort_values("engagement_score_combined", ascending=False).reset_index(drop=True)
    ranking_base.insert(0, "rank", ranking_base.index + 1)
    meta_cols = ["match_id", "match_date", "home_team", "away_team", "home_score", "away_score", "is_rivalry", "total_goals"]
    ranking = ranking_base.merge(matches[meta_cols], on="match_id", how="left")
    ranking["score_str"] = ranking["home_score"].astype(int).astype(str) + "-" + ranking["away_score"].astype(int).astype(str)
    ranking_cols = [
        "rank", "match_id", "match_date", "home_team", "away_team", "score_str",
        "total_goals", "is_rivalry", "fan_comment_count",
        "engagement_score_fans", "engagement_score_football_raw",
        "engagement_score_football_norm", "engagement_score_combined",
    ]
    ranking = ranking[[c for c in ranking_cols if c in ranking.columns]]
    ranking.to_csv(OUT / "stage3_ranking.csv", index=False)

    logger.info("Regenerated Stage 3 outputs. Top 5 by combined engagement:")
    for _, r in ranking.head(5).iterrows():
        logger.info("  #%d  %-22s vs %-16s  rivalry=%-5s  combined=%.4f",
                    int(r["rank"]), r["home_team"], r["away_team"],
                    str(r["is_rivalry"]), r["engagement_score_combined"])


if __name__ == "__main__":
    main()
