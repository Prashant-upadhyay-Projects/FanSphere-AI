"""
generate_fan_segments.py
========================

Phase A2 enrichment: cluster fans into behaviour-driven segments.

Reads `outputs/stage3_comments_enriched.parquet` (produced by
`enrich_comments_sentiment.py`), aggregates per-author behaviour
features, and runs KMeans (k=3) to label each author as one of
Casual / Tactical / Highly Engaged.

Why these three labels?
-----------------------
The label is *assigned*, not learned. KMeans gives us three numbered
clusters; we relabel them by mean engagement so the mapping is stable
across runs. The interpretive names come from the brief — they're the
sports-analytics archetypes recruiters expect to see for this kind of
audience-intelligence project.

Features (per author):
  comment_frequency     — total comments by this author across all matches
  avg_sentiment         — mean VADER compound score
  sentiment_volatility  — std of VADER (a fan who swings hot/cold)
  engagement_activity   — total upvotes received (proxy for influence)
  matches_covered       — number of distinct matches commented on
  positive_ratio        — share of their comments labelled positive

Output: `outputs/fan_segments.csv` — one row per qualifying author.

Authors with fewer than MIN_COMMENTS=3 comments are dropped from the
clustering (they're too sparse for behaviour modelling) and reported
separately in the log. Bot/deleted accounts are excluded.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score
from sklearn.preprocessing import StandardScaler


PROJECT_ROOT = Path(__file__).resolve().parent.parent
ENRICHED_PATH = PROJECT_ROOT / "outputs" / "stage3_comments_enriched.parquet"
OUTPUT_PATH = PROJECT_ROOT / "outputs" / "fan_segments.csv"

MIN_COMMENTS = 3
EXCLUDED_AUTHORS = {"[deleted]", "AutoModerator", "", None}
SEGMENT_LABELS = ("Casual Fan", "Tactical Fan", "Highly Engaged Fan")
RANDOM_STATE = 42

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)


def main() -> None:
    if not ENRICHED_PATH.exists():
        raise FileNotFoundError(
            f"Missing {ENRICHED_PATH}. Run enrich_comments_sentiment first."
        )

    logger.info("Reading enriched comments: %s", ENRICHED_PATH)
    df = pd.read_parquet(ENRICHED_PATH)
    logger.info("  rows: %d, unique authors: %d", len(df), df["author"].nunique())

    # Filter out bot/deleted/empty authors
    df = df[~df["author"].isin(EXCLUDED_AUTHORS)].copy()
    df = df[df["author"].notna()]
    logger.info("After excluding bots/deleted: %d rows, %d authors",
                len(df), df["author"].nunique())

    # Per-author features ---------------------------------------------------
    grouped = df.groupby("author").agg(
        comment_frequency=("comment_id", "count"),
        avg_sentiment=("sentiment_score", "mean"),
        sentiment_volatility=("sentiment_score", "std"),
        engagement_activity=("score", "sum"),
        matches_covered=("match_id", "nunique"),
        positive_ratio=("sentiment_label",
                        lambda s: (s == "positive").sum() / len(s)),
        primary_subreddit=("subreddit",
                           lambda s: s.value_counts().idxmax()),
    )
    grouped["sentiment_volatility"] = grouped["sentiment_volatility"].fillna(0.0)
    grouped["engagement_activity"] = grouped["engagement_activity"].fillna(0).astype(int)

    qualified = grouped[grouped["comment_frequency"] >= MIN_COMMENTS].copy()
    logger.info("Qualified authors (>=%d comments): %d / %d",
                MIN_COMMENTS, len(qualified), len(grouped))

    if len(qualified) < 3:
        raise RuntimeError(
            f"Only {len(qualified)} qualified authors — KMeans k=3 not viable."
        )

    # Clustering ------------------------------------------------------------
    feature_cols = [
        "comment_frequency",
        "sentiment_volatility",
        "engagement_activity",
    ]
    X = qualified[feature_cols].to_numpy()
    X_scaled = StandardScaler().fit_transform(X)

    model = KMeans(n_clusters=3, n_init=10, random_state=RANDOM_STATE)
    raw_labels = model.fit_predict(X_scaled)
    sil = silhouette_score(X_scaled, raw_labels)
    logger.info("Silhouette score: %.4f", sil)

    qualified["_raw_cluster"] = raw_labels

    # Stable label assignment: order clusters by mean engagement_activity
    # so 'Casual Fan' is always the lowest-engagement cluster.
    order = (
        qualified.groupby("_raw_cluster")["engagement_activity"]
        .mean()
        .sort_values()
        .index.tolist()
    )
    label_map = {raw: SEGMENT_LABELS[i] for i, raw in enumerate(order)}
    qualified["segment"] = qualified["_raw_cluster"].map(label_map)
    qualified = qualified.drop(columns="_raw_cluster")

    # Diagnostic columns for the dashboard ----------------------------------
    qualified["silhouette_score"] = round(sil, 4)

    # Reset author into a column for CSV friendliness
    qualified = qualified.reset_index()

    # Reorder for readability
    qualified = qualified[[
        "author", "segment", "primary_subreddit",
        "comment_frequency", "matches_covered",
        "avg_sentiment", "sentiment_volatility", "positive_ratio",
        "engagement_activity", "silhouette_score",
    ]]

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    qualified.to_csv(OUTPUT_PATH, index=False)
    logger.info("Wrote %s (%d authors)", OUTPUT_PATH, len(qualified))

    # Segment summary -------------------------------------------------------
    logger.info("Segment distribution:")
    summary = qualified.groupby("segment").agg(
        n_authors=("author", "count"),
        mean_comments=("comment_frequency", "mean"),
        mean_volatility=("sentiment_volatility", "mean"),
        mean_upvotes=("engagement_activity", "mean"),
    ).round(2)
    for seg, row in summary.iterrows():
        logger.info("  %-22s n=%4d  mean_comments=%.1f  volatility=%.3f  upvotes=%.1f",
                    seg, int(row["n_authors"]),
                    row["mean_comments"], row["mean_volatility"], row["mean_upvotes"])


if __name__ == "__main__":
    main()
