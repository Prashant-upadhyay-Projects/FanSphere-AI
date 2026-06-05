#!/usr/bin/env python3
"""
FanSphere AutoResearch — Evaluation Script
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
FROZEN FILE: the agent must NOT modify this file.
If it errors, log the error in results_log.md, revert your experiment change,
and stop. The human fixes evaluate.py.

It reads the REAL pipeline artifacts in ../outputs/ and calls the REAL
production code in ../src/, so a winning experiment config ports straight
into the project.

Usage:
  python evaluate.py --phase 1                # clustering quality
  python evaluate.py --phase 2                # sentiment model / aggregation
  python evaluate.py --phase 3                # engagement formula weights
  python evaluate.py --phase N --baseline     # measure & record this phase's baseline

Metric (per phase):
  Phase 1 : composite = 0.6*silhouette + 0.4*cluster_stability
  Phase 2 : composite = 0.5*rivalry_auc + 0.5*rivalry_margin_norm
  Phase 3 : composite = 0.5*rivalry_auc + 0.5*rivalry_margin_norm

Output: pretty JSON to stdout.
"""

from __future__ import annotations

import argparse
import json
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

# ── Paths ───────────────────────────────────────────────────────────────────
HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parent
OUTPUTS = REPO_ROOT / "outputs"
ENRICHED_PATH = OUTPUTS / "stage3_comments_enriched.parquet"
MATCHES_PATH = OUTPUTS / "stage2_matches.csv"
STAGE2_ENG_PATH = OUTPUTS / "stage2_engagement.csv"
BUDGET_PATH = HERE / "budget.json"

# Make the production package importable (../src).
sys.path.insert(0, str(REPO_ROOT))

EXCLUDED_AUTHORS = {"[deleted]", "AutoModerator", "", None}
PHASE1_W = {"silhouette": 0.6, "cluster_stability": 0.4}
ENG_W = {"rivalry_auc": 0.5, "rivalry_margin_norm": 0.5}
STABILITY_BOOTSTRAPS = 10
STABILITY_FRACTION = 0.8


# ═══════════════════════════════════════════════════════════════════════════
# Data loading
# ═══════════════════════════════════════════════════════════════════════════

def load_enriched(with_body: bool = False) -> pd.DataFrame:
    if not ENRICHED_PATH.exists():
        raise FileNotFoundError(
            f"Missing {ENRICHED_PATH}.\n"
            "Run the Stage 3 enrichment first: python -m src.enrich_comments_sentiment"
        )
    cols = [
        "match_id", "comment_id", "subreddit", "author",
        "created_utc", "link_confidence", "score",
        "sentiment_score", "sentiment_label",
    ]
    if with_body:
        cols.append("body")
    df = pd.read_parquet(ENRICHED_PATH, columns=cols)
    df["match_id"] = pd.to_numeric(df["match_id"], errors="coerce").astype("Int64")
    df = df.dropna(subset=["match_id"]).copy()
    df["match_id"] = df["match_id"].astype("int64")
    return df


def load_matches() -> pd.DataFrame:
    if not MATCHES_PATH.exists():
        raise FileNotFoundError(f"Missing {MATCHES_PATH}.")
    m = pd.read_csv(MATCHES_PATH)
    m["match_id"] = pd.to_numeric(m["match_id"], errors="coerce").astype("int64")
    if "is_rivalry" in m.columns:
        m["is_rivalry"] = (
            m["is_rivalry"].astype(str).str.strip().str.lower().isin(["true", "1", "yes"])
        )
    return m


def load_stage2_engagement() -> pd.DataFrame:
    if not STAGE2_ENG_PATH.exists():
        raise FileNotFoundError(f"Missing {STAGE2_ENG_PATH}.")
    e = pd.read_csv(STAGE2_ENG_PATH)
    e["match_id"] = pd.to_numeric(e["match_id"], errors="coerce").astype("int64")
    return e


# ═══════════════════════════════════════════════════════════════════════════
# Phase 1 — clustering
# ═══════════════════════════════════════════════════════════════════════════

def build_author_features(enriched: pd.DataFrame, min_comments: int) -> pd.DataFrame:
    df = enriched[~enriched["author"].isin(EXCLUDED_AUTHORS)].copy()
    df = df[df["author"].notna()]
    grouped = df.groupby("author").agg(
        comment_frequency=("comment_id", "count"),
        avg_sentiment=("sentiment_score", "mean"),
        sentiment_volatility=("sentiment_score", "std"),
        engagement_activity=("score", "sum"),
        matches_covered=("match_id", "nunique"),
        positive_ratio=("sentiment_label", lambda s: (s == "positive").mean()),
    )
    grouped["sentiment_volatility"] = grouped["sentiment_volatility"].fillna(0.0)
    grouped["engagement_activity"] = grouped["engagement_activity"].fillna(0)
    qualified = grouped[grouped["comment_frequency"] >= int(min_comments)].copy()
    if len(qualified) < 3:
        raise RuntimeError(
            f"Only {len(qualified)} authors with >= {min_comments} comments; "
            "clustering not viable."
        )
    return qualified


def feature_matrix(author_df: pd.DataFrame, feature_cfg: dict) -> np.ndarray:
    desired = feature_cfg.get(
        "features", ["comment_frequency", "sentiment_volatility", "engagement_activity"]
    )
    available = [c for c in desired if c in author_df.columns]
    if not available:
        raise RuntimeError(
            f"None of requested features {desired} exist. "
            f"Available: {list(author_df.columns)}"
        )
    X = author_df[available].fillna(0).to_numpy(dtype=float)
    if feature_cfg.get("normalize", True):
        from sklearn.preprocessing import StandardScaler, MinMaxScaler, RobustScaler
        scaler = {
            "standard": StandardScaler(),
            "minmax": MinMaxScaler(),
            "robust": RobustScaler(),
        }.get(feature_cfg.get("normalization", "standard"), StandardScaler())
        X = scaler.fit_transform(X)
    return X


def run_clustering(X: np.ndarray, cfg: dict, seed: int) -> np.ndarray:
    algo = cfg.get("algorithm", "kmeans").lower()
    k = int(cfg.get("k", 3))
    if algo == "kmeans":
        from sklearn.cluster import KMeans
        return KMeans(n_clusters=k, random_state=seed, n_init=10).fit_predict(X)
    if algo == "gmm":
        from sklearn.mixture import GaussianMixture
        return GaussianMixture(
            n_components=k,
            covariance_type=cfg.get("covariance_type", "full"),
            random_state=seed,
        ).fit_predict(X)
    if algo == "agglomerative":
        from sklearn.cluster import AgglomerativeClustering
        return AgglomerativeClustering(n_clusters=k).fit_predict(X)
    raise ValueError(f"Unknown algorithm '{algo}'. Use kmeans | gmm | agglomerative.")


def evaluate_phase1() -> dict:
    from sklearn.metrics import silhouette_score, adjusted_rand_score
    from experiment_1_clustering import CLUSTERING_CONFIG, FEATURE_CONFIG

    enriched = load_enriched()
    author_df = build_author_features(enriched, FEATURE_CONFIG.get("min_comments", 3))
    X = feature_matrix(author_df, FEATURE_CONFIG)
    seed = int(CLUSTERING_CONFIG.get("random_state", 42))

    base_labels = run_clustering(X, CLUSTERING_CONFIG, seed)
    n_clusters = len(set(base_labels))
    silhouette = (
        float(silhouette_score(X, base_labels)) if 2 <= n_clusters < len(X) else 0.0
    )

    # Stability via subsample re-clustering (algorithm-agnostic).
    rng = np.random.default_rng(seed)
    n = len(X)
    sub_n = max(int(STABILITY_FRACTION * n), 10)
    aris = []
    for b in range(STABILITY_BOOTSTRAPS):
        idx = rng.choice(n, size=sub_n, replace=False)
        sub_labels = run_clustering(X[idx], CLUSTERING_CONFIG, seed=b + 1)
        aris.append(adjusted_rand_score(base_labels[idx], sub_labels))
    cluster_stability = float(np.mean(aris)) if aris else 0.0

    sil_c = max(0.0, min(1.0, silhouette))
    stab_c = max(0.0, min(1.0, cluster_stability))
    composite = PHASE1_W["silhouette"] * sil_c + PHASE1_W["cluster_stability"] * stab_c

    return {
        "phase": 1,
        "silhouette": round(silhouette, 4),
        "cluster_stability": round(cluster_stability, 4),
        "composite": round(composite, 4),
        "details": {
            "algorithm": CLUSTERING_CONFIG.get("algorithm"),
            "k": CLUSTERING_CONFIG.get("k"),
            "normalization": FEATURE_CONFIG.get("normalization"),
            "features": [c for c in FEATURE_CONFIG.get("features", []) if c in author_df.columns],
            "n_authors": int(len(author_df)),
            "n_clusters_found": int(n_clusters),
            "stability_bootstraps": STABILITY_BOOTSTRAPS,
        },
    }


# ═══════════════════════════════════════════════════════════════════════════
# Phases 2 & 3 — engagement validity
# ═══════════════════════════════════════════════════════════════════════════

def _textblob_scores(bodies: list[str]) -> list[float]:
    try:
        from textblob import TextBlob
    except ImportError as e:
        raise ImportError("textblob required for model='textblob': pip install textblob") from e
    return [float(TextBlob(t).sentiment.polarity) if t else 0.0 for t in bodies]


def _match_avg_sentiment(enriched: pd.DataFrame, sentiment: pd.Series, mode: str) -> pd.Series:
    """Per-match average sentiment honouring the aggregation mode."""
    tmp = pd.DataFrame({
        "match_id": enriched["match_id"].to_numpy(),
        "sent": np.asarray(sentiment, dtype=float),
        "w": enriched["score"].clip(lower=0).fillna(0).to_numpy(dtype=float),
    })
    if mode == "median":
        return tmp.groupby("match_id")["sent"].median()
    if mode == "weighted_mean":
        def _wm(g):
            w = g["w"].to_numpy()
            if w.sum() <= 0:
                return g["sent"].mean()
            return float(np.average(g["sent"].to_numpy(), weights=w))
        return tmp.groupby("match_id").apply(_wm)
    return tmp.groupby("match_id")["sent"].mean()  # mean (baseline)


def compute_match_engagement(
    enriched: pd.DataFrame,
    sentiment: pd.Series,
    fan_weights,
    football_w: float,
    fan_w: float,
    aggregation: str = "mean",
) -> pd.DataFrame:
    """Run the REAL engagement code, returning a per-match score frame."""
    from src.engagement import aggregate_per_match, compute_engagement_score, join_with_stage2

    links = enriched[["match_id", "comment_id", "link_confidence", "created_utc", "subreddit"]].copy()
    scored = pd.DataFrame({"id": enriched["comment_id"].to_numpy(), "sentiment": np.asarray(sentiment, float)})

    per_match = aggregate_per_match(links, scored)

    # Honour aggregation mode for the affect component (mean is the production default).
    if aggregation != "mean":
        override = _match_avg_sentiment(enriched, sentiment, aggregation)
        per_match["avg_sentiment"] = per_match["match_id"].map(override).fillna(per_match["avg_sentiment"])

    per_match = compute_engagement_score(per_match, fan_weights)
    merged = join_with_stage2(per_match, load_stage2_engagement())

    # Re-apply the top-level blend with the experiment's football/fan split
    # (join_with_stage2 hardcodes 0.5/0.5; we parameterise it here).
    merged["engagement_score_combined"] = (
        football_w * merged["engagement_score_football_norm"].fillna(0.0)
        + fan_w * merged["engagement_score_fans"].fillna(0.0)
    ).clip(0.0, 1.0)
    return merged[[
        "match_id", "engagement_score_combined",
        "engagement_score_fans", "engagement_score_football_norm",
    ]]


def _spearman(a: np.ndarray, b: np.ndarray) -> float:
    if len(a) < 3:
        return 0.0
    ra = pd.Series(a).rank().to_numpy()
    rb = pd.Series(b).rank().to_numpy()
    if np.std(ra) == 0 or np.std(rb) == 0:
        return 0.0
    return float(np.corrcoef(ra, rb)[0, 1])


def rivalry_metrics(scores: pd.DataFrame, matches: pd.DataFrame) -> dict:
    from sklearn.metrics import roc_auc_score

    df = scores.merge(
        matches[["match_id", "is_rivalry", "total_goals", "home_team", "away_team"]],
        on="match_id", how="left",
    )
    df["is_rivalry"] = df["is_rivalry"].fillna(False).astype(bool)
    s = df["engagement_score_combined"].fillna(0.0).to_numpy(dtype=float)
    y = df["is_rivalry"].to_numpy()

    auc = float(roc_auc_score(y, s)) if (y.any() and not y.all()) else 0.5
    if y.any() and not y.all():
        margin = float(s[y].mean() - s[~y].mean())
    else:
        margin = 0.0
    margin_norm = max(0.0, min(1.0, (margin + 1.0) / 2.0))
    composite = ENG_W["rivalry_auc"] * auc + ENG_W["rivalry_margin_norm"] * margin_norm

    df["rank"] = df["engagement_score_combined"].rank(ascending=False, method="min")
    rivalry_rows = df[df["is_rivalry"]].sort_values("rank")
    rivalry_ranks = [
        {
            "match": f"{r.home_team} vs {r.away_team}",
            "rank": int(r["rank"]),
            "score": round(float(r["engagement_score_combined"]), 4),
        }
        for _, r in rivalry_rows.iterrows()
    ]
    top3 = df.sort_values("rank").head(3)
    top3_list = [
        {"match": f"{r.home_team} vs {r.away_team}", "rank": int(r["rank"]),
         "score": round(float(r["engagement_score_combined"]), 4),
         "is_rivalry": bool(r["is_rivalry"])}
        for _, r in top3.iterrows()
    ]

    return {
        "rivalry_auc": round(auc, 4),
        "rivalry_margin_norm": round(margin_norm, 4),
        "composite": round(composite, 4),
        "diagnostics": {
            "rivalry_fixture_ranks": rivalry_ranks,
            "top3_fixtures": top3_list,
            "spearman_score_vs_goals": round(
                _spearman(s, df["total_goals"].fillna(0).to_numpy(dtype=float)), 4
            ),
            "n_fixtures": int(len(df)),
            "n_rivalry": int(y.sum()),
        },
    }


def evaluate_phase2() -> dict:
    from experiment_2_sentiment import SENTIMENT_CONFIG
    from src.engagement import EngagementWeights

    model = SENTIMENT_CONFIG.get("model", "vader").lower()
    aggregation = SENTIMENT_CONFIG.get("aggregation", "mean").lower()

    enriched = load_enriched(with_body=(model == "textblob"))
    if model == "vader":
        sentiment = enriched["sentiment_score"]  # identical to a fresh VADER pass
    elif model == "textblob":
        sentiment = pd.Series(_textblob_scores(enriched["body"].fillna("").astype(str).tolist()))
    else:
        raise ValueError(f"Unknown sentiment model '{model}'. Use vader | textblob.")

    scores = compute_match_engagement(
        enriched, sentiment,
        fan_weights=EngagementWeights(),        # production default (held fixed)
        football_w=0.5, fan_w=0.5,              # production default (held fixed)
        aggregation=aggregation,
    )
    result = rivalry_metrics(scores, load_matches())
    result["phase"] = 2
    result["details"] = {"model": model, "aggregation": aggregation}
    return result


def evaluate_phase3() -> dict:
    from experiment_3_engagement import ENGAGEMENT_CONFIG
    from src.engagement import EngagementWeights

    fw = float(ENGAGEMENT_CONFIG.get("football_weight", 0.5))
    fanw = float(ENGAGEMENT_CONFIG.get("fan_weight", 0.5))
    blend = ENGAGEMENT_CONFIG.get("FAN_BLEND_WEIGHTS", {})
    weights = EngagementWeights(
        volume=float(blend.get("volume", 0.45)),
        affect=float(blend.get("affect", 0.20)),
        volatility=float(blend.get("volatility", 0.25)),
        reach=float(blend.get("reach", 0.10)),
    )

    warnings_list = []
    if abs((fw + fanw) - 1.0) > 1e-6:
        warnings_list.append(f"football_weight+fan_weight={fw + fanw:.3f} (should be 1.0)")
    blend_sum = weights.volume + weights.affect + weights.volatility + weights.reach
    if abs(blend_sum - 1.0) > 1e-6:
        warnings_list.append(f"fan-blend weights sum to {blend_sum:.3f} (should be 1.0)")

    enriched = load_enriched()
    scores = compute_match_engagement(
        enriched, enriched["sentiment_score"],  # baseline VADER held fixed
        fan_weights=weights, football_w=fw, fan_w=fanw, aggregation="mean",
    )
    result = rivalry_metrics(scores, load_matches())
    result["phase"] = 3
    result["details"] = {
        "football_weight": fw, "fan_weight": fanw,
        "fan_blend": {"volume": weights.volume, "affect": weights.affect,
                      "volatility": weights.volatility, "reach": weights.reach},
        "constraint_warnings": warnings_list,
    }
    return result


# ═══════════════════════════════════════════════════════════════════════════
# Baseline recording
# ═══════════════════════════════════════════════════════════════════════════

def record_baseline(phase: int, composite: float) -> None:
    """Record the phase baseline. The baseline is also the phase's initial 'best'."""
    if not BUDGET_PATH.exists():
        return
    p = str(phase)
    budget = json.loads(BUDGET_PATH.read_text(encoding="utf-8"))
    budget.setdefault("baselines", {})[p] = composite
    budget.setdefault("best_scores", {})[p] = composite
    budget.setdefault("best_configs", {})[p] = "baseline (measured)"
    BUDGET_PATH.write_text(json.dumps(budget, indent=2), encoding="utf-8")


# ═══════════════════════════════════════════════════════════════════════════
# Entry point
# ═══════════════════════════════════════════════════════════════════════════

def main() -> None:
    parser = argparse.ArgumentParser(description="FanSphere AutoResearch Evaluator")
    parser.add_argument("--phase", type=int, required=True, choices=[1, 2, 3])
    parser.add_argument("--baseline", action="store_true",
                        help="Record this run as the phase baseline in budget.json")
    args = parser.parse_args()

    try:
        result = {1: evaluate_phase1, 2: evaluate_phase2, 3: evaluate_phase3}[args.phase]()
        if args.baseline:
            record_baseline(args.phase, result["composite"])
            result["recorded_as_baseline"] = True
        print(json.dumps(result, indent=2), flush=True)
    except Exception as e:
        import traceback
        print(json.dumps({
            "error": str(e),
            "traceback": traceback.format_exc(),
            "composite": -1.0,
        }, indent=2), flush=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
