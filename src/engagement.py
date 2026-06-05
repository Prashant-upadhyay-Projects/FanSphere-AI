"""
engagement.py
=============

Aggregates per-comment sentiment into per-match engagement features and a
composite engagement score.

Feature design
--------------
For each match we compute:

  comment_count           Total linked comments.
  weighted_comment_count  Sum of link_confidence — gives less credit to weak links.
  avg_sentiment           Mean VADER compound. Sign of the fan mood.
  sentiment_volatility    Std of VADER compound. *Key signal.* High std = the
                          fanbase is split / arguing, which is a stronger
                          excitement proxy than uniform praise.
  positive_ratio          Share of comments with sentiment >= +0.1.
  negative_ratio          Share with sentiment <= -0.1.
  peak_hour_count         Max comments in any one hour in the match window.
  unique_subreddits       Cross-community reach.

Composite engagement_score
--------------------------
A bounded [0, 1] composite. Each component is min-max scaled across the
matches in the input, then linearly combined:

    engagement_score = 0.45 * volume_norm
                     + 0.20 * affect_norm
                     + 0.25 * volatility_norm
                     + 0.10 * reach_norm

Why these weights? They reflect the analytical thesis: *volume of discussion*
matters most for engagement, but pure quietness can hide intensity, so we
boost matches with high emotional charge (affect) and contested narratives
(volatility). Reach across communities is a smaller but real signal that the
match transcended its home fanbase. Weights are exposed as a parameter so
this is a hypothesis the user can refute, not a magic number.

The score is meaningful only *within* a comparison set — it's a relative
ranking tool, not an absolute fan-interest measurement.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

import numpy as np
import pandas as pd


logger = logging.getLogger(__name__)


@dataclass
class EngagementWeights:
    volume: float = 0.45
    affect: float = 0.20
    volatility: float = 0.25
    reach: float = 0.10

    def __post_init__(self) -> None:
        total = self.volume + self.affect + self.volatility + self.reach
        if abs(total - 1.0) > 1e-6:
            logger.warning(
                "EngagementWeights sum to %.4f, not 1.0. Score interpretation will skew.",
                total,
            )


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------

def aggregate_per_match(
    links: pd.DataFrame,
    comments_with_sentiment: pd.DataFrame,
    *,
    positive_threshold: float = 0.1,
    negative_threshold: float = -0.1,
) -> pd.DataFrame:
    """
    Join links to scored comments and aggregate by match.

    Parameters
    ----------
    links : DataFrame from MatchLinker.link() — must include
            [match_id, comment_id, link_confidence, created_utc, subreddit].
    comments_with_sentiment : DataFrame containing [id, sentiment] (plus body etc.).
    """
    _validate(links, comments_with_sentiment)

    if links.empty:
        logger.warning("Empty links DataFrame; returning empty aggregate.")
        return pd.DataFrame()

    # Join. Keep only the columns we need to keep memory predictable.
    merged = links.merge(
        comments_with_sentiment[["id", "sentiment"]].rename(columns={"id": "comment_id"}),
        on="comment_id",
        how="left",
    )

    # Comments that failed sentiment scoring become NaN — drop them.
    before = len(merged)
    merged = merged.dropna(subset=["sentiment"])
    if before != len(merged):
        logger.info("Dropped %d links with missing sentiment.", before - len(merged))

    # Bucket by hour for peak-hour calculation.
    merged["hour_bucket"] = (merged["created_utc"] // 3600).astype("int64")

    grouped = merged.groupby("match_id", sort=False)
    rows = []
    for match_id, g in grouped:
        rows.append({
            "match_id": match_id,
            "comment_count": len(g),
            "weighted_comment_count": float(g["link_confidence"].sum()),
            "avg_sentiment": float(g["sentiment"].mean()),
            "sentiment_volatility": float(g["sentiment"].std(ddof=0)) if len(g) > 1 else 0.0,
            "positive_ratio": float((g["sentiment"] >= positive_threshold).mean()),
            "negative_ratio": float((g["sentiment"] <= negative_threshold).mean()),
            "peak_hour_count": int(g.groupby("hour_bucket").size().max()),
            "unique_subreddits": int(g["subreddit"].nunique()),
        })

    out = pd.DataFrame(rows)
    logger.info("Aggregated to %d matches.", len(out))
    return out


# ---------------------------------------------------------------------------
# Composite score
# ---------------------------------------------------------------------------

def compute_engagement_score(
    per_match: pd.DataFrame,
    weights: Optional[EngagementWeights] = None,
) -> pd.DataFrame:
    """
    Add a composite `engagement_score` column to per-match aggregates.

    The score is bounded [0, 1] and is relative to the input set — comparing
    scores across two different runs with different match sets is not
    meaningful.
    """
    if per_match.empty:
        return per_match.assign(engagement_score=[])

    weights = weights or EngagementWeights()
    out = per_match.copy()

    # Components.
    out["volume_raw"] = np.log1p(out["weighted_comment_count"])
    out["affect_raw"] = out["avg_sentiment"].abs()
    out["volatility_raw"] = out["sentiment_volatility"]
    out["reach_raw"] = np.log1p(out["unique_subreddits"])

    for col in ("volume_raw", "affect_raw", "volatility_raw", "reach_raw"):
        out[col.replace("_raw", "_norm")] = _minmax(out[col])

    out["engagement_score"] = (
        weights.volume     * out["volume_norm"]
        + weights.affect     * out["affect_norm"]
        + weights.volatility * out["volatility_norm"]
        + weights.reach      * out["reach_norm"]
    ).clip(0.0, 1.0)

    # Drop intermediate _raw columns; keep _norm for transparency.
    out = out.drop(columns=[c for c in out.columns if c.endswith("_raw")])
    return out


# ---------------------------------------------------------------------------
# Merge with Stage 2 football engagement
# ---------------------------------------------------------------------------

def join_with_stage2(
    stage3_engagement: pd.DataFrame,
    stage2_engagement: pd.DataFrame,
    *,
    stage2_score_col: str = "engagement_score",
    football_weight: float = 0.35,
    fan_weight: float = 0.65,
) -> pd.DataFrame:
    """
    Combine fan-side (stage 3) and football-side (stage 2) engagement signals.

    UNIT MISMATCH FIX: Stage 2 engagement_score is on a raw 0–30 scale while
    Stage 3 engagement_score_fans is on a [0, 1] scale. A naive 50/50 blend
    would give Stage 2 ~97% of the effective weight. We min-max normalize
    Stage 2 first so both signals contribute equally.

    Output includes:
      engagement_score_football_raw   — original Stage 2 score (0–30 scale)
      engagement_score_football_norm  — min-max normalized to [0, 1]
      engagement_score_combined       — football_weight*norm + fan_weight*fans,
                                         clipped to [0, 1] (default fan-biased 0.35/0.65)
    """
    s2 = stage2_engagement.copy()
    if stage2_score_col not in s2.columns:
        # Be forgiving — stage 2 may use a different column name.
        candidates = [c for c in s2.columns if "engagement" in c.lower() or "excite" in c.lower()]
        if not candidates:
            raise KeyError(
                f"Could not find '{stage2_score_col}' in stage2 engagement. "
                f"Available columns: {list(s2.columns)}"
            )
        stage2_score_col = candidates[0]
        logger.info("Using '%s' as stage 2 engagement column.", stage2_score_col)

    s2 = s2.rename(columns={stage2_score_col: "engagement_score_football_raw"})

    # Min-max normalize Stage 2 score to [0, 1] so it is on the same scale as
    # engagement_score_fans before blending.
    raw = s2["engagement_score_football_raw"].fillna(0.0)
    lo, hi = raw.min(), raw.max()
    if hi - lo < 1e-12:
        logger.warning(
            "All Stage 2 engagement_score values are identical (%.4f); "
            "engagement_score_football_norm set to 0 for all rows.",
            lo,
        )
        s2["engagement_score_football_norm"] = 0.0
    else:
        s2["engagement_score_football_norm"] = ((raw - lo) / (hi - lo)).clip(0.0, 1.0)

    s3 = stage3_engagement.rename(columns={
        "engagement_score": "engagement_score_fans",
        "comment_count": "fan_comment_count",
        "avg_sentiment": "fan_avg_sentiment",
        "sentiment_volatility": "fan_sentiment_volatility",
    })

    merged = s2.merge(s3, on="match_id", how="left")

    # Fans-side may be missing for matches we couldn't link to comments. Mark
    # them as zero so the combined score doesn't NaN out — and emit a count.
    n_missing = merged["engagement_score_fans"].isna().sum()
    if n_missing:
        logger.info(
            "%d of %d matches have no fan-side engagement; filling with 0.",
            n_missing, len(merged),
        )
    merged["engagement_score_fans"] = merged["engagement_score_fans"].fillna(0.0)
    merged["fan_comment_count"] = merged["fan_comment_count"].fillna(0).astype(int)

    # Combined score on matching [0, 1] scales.
    # Fan-biased 0.35/0.65 default from the AutoResearch loop (H3.1): weighting the
    # fan signal higher surfaces rivalry fixtures (e.g. El Clasico) that the old
    # 50/50 split buried mid-table on this fan-intelligence platform.
    merged["engagement_score_combined"] = (
        football_weight * merged["engagement_score_football_norm"].fillna(0.0)
        + fan_weight * merged["engagement_score_fans"]
    ).clip(0.0, 1.0)
    return merged


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------

def _minmax(s: pd.Series) -> pd.Series:
    lo, hi = s.min(), s.max()
    if hi - lo < 1e-12:
        return pd.Series(np.zeros(len(s)), index=s.index)
    return (s - lo) / (hi - lo)


def _validate(links: pd.DataFrame, scored: pd.DataFrame) -> None:
    needed_links = {"match_id", "comment_id", "link_confidence", "created_utc", "subreddit"}
    needed_scored = {"id", "sentiment"}
    missing_l = needed_links - set(links.columns)
    missing_s = needed_scored - set(scored.columns)
    if missing_l:
        raise ValueError(f"links missing columns: {missing_l}")
    if missing_s:
        raise ValueError(f"comments_with_sentiment missing columns: {missing_s}")
