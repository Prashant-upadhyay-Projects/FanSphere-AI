"""
EXPERIMENT FILE — PHASE 1: AUTHOR CLUSTERING
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Agent: you MAY modify anything in this file (one change per iteration).
Goal: raise composite_1 = 0.6*silhouette + 0.4*cluster_stability above the
current best. See program.md → Phase 1 for the hypotheses and their order.

These configs mirror the REAL pipeline (src/generate_fan_segments.py), which
clusters authors on behaviour features. A winning config here is a 1-line
change you can port into that file.

Baseline (matches production):
  algorithm     = kmeans
  k             = 3
  normalization = standard
  features      = comment_frequency, sentiment_volatility, engagement_activity
"""

# ── Clustering algorithm config ───────────────────────────────────────────────
CLUSTERING_CONFIG = {
    # "kmeans" | "gmm" | "agglomerative"
    "algorithm": "kmeans",

    # Number of clusters (kmeans / gmm / agglomerative)
    "k": 4,

    # Reproducibility seed (kmeans / gmm only; agglomerative is deterministic)
    "random_state": 42,

    # GMM-specific: "full" | "tied" | "diag" | "spherical"
    "covariance_type": "full",
}

# ── Feature engineering config ────────────────────────────────────────────────
FEATURE_CONFIG = {
    # Author-level features to cluster on. Allowed (all derived from
    # outputs/stage3_comments_enriched.parquet):
    #   comment_frequency     — number of comments by the author
    #   sentiment_volatility  — std of the author's sentiment_score
    #   engagement_activity   — sum of the author's Reddit upvote 'score'
    #   avg_sentiment         — mean sentiment_score
    #   positive_ratio        — share of the author's comments labelled positive
    #   matches_covered       — distinct matches the author commented on
    "features": [
        "comment_frequency",
        "sentiment_volatility",
        "engagement_activity",
    ],

    # Drop authors with fewer than this many comments (production uses 3).
    "min_comments": 3,

    # Scale features before clustering?
    "normalize": True,

    # "standard" (z-score) | "minmax" | "robust" (median/IQR, outlier-resistant)
    "normalization": "robust",
}
