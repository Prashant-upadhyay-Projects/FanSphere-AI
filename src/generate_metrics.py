"""KPI generation and fan segmentation.

Implements the three headline metrics from the brief:

    excitement_index  = 0.4·norm(comments) + 0.3·norm(upvotes) + 0.3·norm(goals)
    fan_sentiment     = (positive - negative) / total
    match_hype_score  = 0.5·norm(social_volume) + 0.3·norm(goals) + 0.2·rivalry_weight

…then runs a lightweight KMeans (k=3) to segment fans into:
    Casual / Tactical / Highly Engaged
"""

from __future__ import annotations

from typing import Tuple

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler

from .config import get_logger

LOG = get_logger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _minmax(series: pd.Series) -> pd.Series:
    """Min-max scale a Series to [0, 100].  Constant series → 0."""
    if series.empty:
        return series
    lo, hi = series.min(), series.max()
    if hi == lo:
        return pd.Series(np.zeros(len(series)), index=series.index)
    return (series - lo) / (hi - lo) * 100


# ---------------------------------------------------------------------------
# Per-match engagement metrics
# ---------------------------------------------------------------------------
def build_engagement_metrics(
    matches: pd.DataFrame,
    sentiment: pd.DataFrame,
    goals_per_match: pd.DataFrame,
) -> pd.DataFrame:
    """Join the three streams and compute per-match KPIs.

    Reddit posts/comments are assigned to a match only if `match_id` is already
    set on the sentiment record (set by the pipeline via keyword matching, or
    left null when the post isn't match-specific).
    """
    LOG.info("Building engagement metrics for %d matches", len(matches))

    # Social aggregates per match
    social = (
        sentiment.dropna(subset=["match_id"])
        .groupby("match_id")
        .agg(
            comment_volume=("id", "count") if "id" in sentiment.columns else ("comment", "count"),
            upvote_total=("upvotes", "sum"),
            avg_sentiment=("sentiment_score", "mean"),
            positive=("sentiment_label", lambda s: (s == "positive").sum()),
            negative=("sentiment_label", lambda s: (s == "negative").sum()),
        )
        .reset_index()
    )

    df = matches.merge(social, on="match_id", how="left")
    df = df.merge(goals_per_match, on="match_id", how="left")

    # Fill social NaNs (matches with no Reddit chatter).  pd.to_numeric is
    # used to set the dtype explicitly before fillna — without it, pandas 2.x
    # raises a FutureWarning about silent object→numeric downcasting.
    for col in ("comment_volume", "upvote_total", "positive", "negative", "goal_events"):
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype(int)
    df["avg_sentiment"] = pd.to_numeric(df["avg_sentiment"], errors="coerce").fillna(0.0)

    # Normalised components ----------------------------------------------
    n_comments = _minmax(df["comment_volume"])
    n_upvotes = _minmax(df["upvote_total"])
    n_goals = _minmax(df["goal_events"].astype(float))
    social_volume = (df["comment_volume"] + df["upvote_total"]).astype(float)
    n_social = _minmax(social_volume)
    rivalry_weight = df["is_rivalry"].astype(int) * 100  # 0 or 100

    # Excitement Index ----------------------------------------------------
    df["excitement_index"] = (0.4 * n_comments + 0.3 * n_upvotes + 0.3 * n_goals).round(2)

    # Match Hype Score ----------------------------------------------------
    df["match_hype_score"] = (0.5 * n_social + 0.3 * n_goals + 0.2 * rivalry_weight).round(2)

    # Engagement Score (composite — drives ranking & dashboard tile) ------
    df["engagement_score"] = ((df["excitement_index"] + df["match_hype_score"]) / 2).round(2)

    columns = [
        "match_id",
        "comment_volume",
        "upvote_total",
        "goal_events",
        "avg_sentiment",
        "engagement_score",
        "excitement_index",
        "match_hype_score",
    ]
    return df[columns]


# ---------------------------------------------------------------------------
# Headline KPI
# ---------------------------------------------------------------------------
def fan_sentiment_score(sentiment: pd.DataFrame) -> float:
    """Top-line scalar:  (positive − negative) / total ∈ [-1, 1]."""
    if sentiment.empty:
        return 0.0
    pos = (sentiment["sentiment_label"] == "positive").sum()
    neg = (sentiment["sentiment_label"] == "negative").sum()
    return round((pos - neg) / len(sentiment), 4)


# ---------------------------------------------------------------------------
# Fan segmentation (KMeans, k=3)
# ---------------------------------------------------------------------------
SEGMENT_LABELS = ("Casual Fan", "Tactical Fan", "Highly Engaged Fan")


def _fan_features(sentiment: pd.DataFrame) -> pd.DataFrame:
    """Aggregate per-author features for clustering.

    For Reddit data we approximate `author` via the comment's source +
    external_id prefix.  If your future loaders expose a real author column,
    swap it in here.
    """
    work = sentiment.copy()
    work["author"] = work["external_id"].astype(str).str[:3] + "_" + work["source"]

    grouped = (
        work.groupby("author")
        .agg(
            comment_frequency=("comment", "count"),
            avg_sentiment=("sentiment_score", "mean"),
            sentiment_volatility=("sentiment_score", "std"),
            engagement_activity=("upvotes", "sum"),
        )
        .fillna(0)
    )
    return grouped


def segment_fans(sentiment: pd.DataFrame, random_state: int = 42) -> Tuple[pd.DataFrame, KMeans]:
    """Run KMeans (k=3) over per-author features.

    Returns (features_with_segment, fitted_model).  Segments are ordered by
    `engagement_activity` so labels stay stable across runs.
    """
    features = _fan_features(sentiment)
    if len(features) < 3:
        LOG.warning("Only %d fan rows — skipping segmentation", len(features))
        features["segment"] = "Unsegmented"
        return features, None  # type: ignore[return-value]

    matrix = features[
        ["comment_frequency", "sentiment_volatility", "engagement_activity"]
    ].to_numpy()
    scaled = StandardScaler().fit_transform(matrix)

    model = KMeans(n_clusters=3, n_init=10, random_state=random_state)
    raw_labels = model.fit_predict(scaled)

    # Order clusters by mean engagement so label mapping is deterministic
    features = features.assign(_raw=raw_labels)
    order = (
        features.groupby("_raw")["engagement_activity"].mean().sort_values().index.tolist()
    )
    label_map = {raw: SEGMENT_LABELS[i] for i, raw in enumerate(order)}
    features["segment"] = features["_raw"].map(label_map)
    features = features.drop(columns="_raw")

    LOG.info("Segment distribution: %s", features["segment"].value_counts().to_dict())
    return features, model
