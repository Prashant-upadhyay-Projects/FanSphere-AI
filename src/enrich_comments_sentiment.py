"""
enrich_comments_sentiment.py
============================

Phase A1 enrichment: produce a *linked, scored, body-bearing* per-comment
parquet so the downstream dashboard can show sentiment distributions, top
quotes, and per-minute sentiment timelines.

The original Stage 3 pipeline produced two artefacts that, between them,
have everything we need but never the right *combination* on disk:

* `outputs/stage3_comments_linked.parquet` — 93,298 rows of
  (match_id, comment_id, subreddit, created_utc, minutes_from_kickoff,
   link_confidence, link_reasons). No body, no sentiment.

* `data/interim/reddit_comments.parquet` — 907,158 rows with
  (id, body, score, author, created_utc, subreddit, link_id). No
  match linkage, no sentiment.

We join them on `comment_id == id`, run VADER from `src.sentiment`, and
write `outputs/stage3_comments_enriched.parquet`. That single file
unblocks dashboard Pages 2 (Match Drill-Down), 3 (Fan Segmentation —
uses authors from this file), and 4 (Sentiment Timeline).

Idempotent. Re-running overwrites the output.
"""

from __future__ import annotations

import logging
import sys
import time
from pathlib import Path

import pandas as pd

# Make `src` importable when run as a script from project root
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.sentiment import VaderAnalyzer  # noqa: E402


PROJECT_ROOT = Path(__file__).resolve().parent.parent
LINKED_PATH = PROJECT_ROOT / "outputs" / "stage3_comments_linked.parquet"
COMMENTS_PATH = PROJECT_ROOT / "data" / "interim" / "reddit_comments.parquet"
OUTPUT_PATH = PROJECT_ROOT / "outputs" / "stage3_comments_enriched.parquet"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)


def main() -> None:
    if not LINKED_PATH.exists():
        raise FileNotFoundError(f"Missing {LINKED_PATH}. Run Stage 3 first.")
    if not COMMENTS_PATH.exists():
        raise FileNotFoundError(f"Missing {COMMENTS_PATH}. Run load_reddit_archive.")

    logger.info("Reading linked comments: %s", LINKED_PATH)
    linked = pd.read_parquet(LINKED_PATH)
    logger.info("  linked rows: %d", len(linked))

    logger.info("Reading raw comments: %s", COMMENTS_PATH)
    # We only need body, score, author for the 93K linked subset, so
    # filter early to avoid carrying 907K * full-row in memory longer
    # than necessary.
    raw = pd.read_parquet(
        COMMENTS_PATH,
        columns=["id", "body", "score", "author"],
    )
    logger.info("  raw rows: %d", len(raw))

    logger.info("Joining linked -> raw on comment_id == id")
    enriched = linked.merge(
        raw,
        left_on="comment_id",
        right_on="id",
        how="inner",
    ).drop(columns=["id"])
    logger.info("  joined rows: %d", len(enriched))

    if len(enriched) < 0.95 * len(linked):
        logger.warning(
            "Join lost more than 5%% of rows (%d -> %d). "
            "Check that reddit_comments.parquet covers the linked window.",
            len(linked),
            len(enriched),
        )

    # Sanitise body — VADER on NaN/non-string explodes
    enriched["body"] = enriched["body"].fillna("").astype(str)

    logger.info("Scoring %d comments with VADER", len(enriched))
    t0 = time.perf_counter()
    analyzer = VaderAnalyzer()
    enriched["sentiment_score"] = analyzer.score_batch(enriched["body"].tolist())
    elapsed = time.perf_counter() - t0
    logger.info("  VADER done in %.1fs (%.0f comments/s)",
                elapsed, len(enriched) / elapsed)

    # Derived label for downstream filtering — VADER's standard thresholds
    def _label(s: float) -> str:
        if s >= 0.05:
            return "positive"
        if s <= -0.05:
            return "negative"
        return "neutral"

    enriched["sentiment_label"] = enriched["sentiment_score"].map(_label)
    enriched["sentiment_model"] = analyzer.name

    # Column ordering — link/identity first, then text, then scoring
    cols = [
        "match_id", "comment_id", "subreddit", "author",
        "created_utc", "match_epoch", "minutes_from_kickoff",
        "link_confidence", "link_reasons",
        "body", "score",
        "sentiment_score", "sentiment_label", "sentiment_model",
    ]
    enriched = enriched[[c for c in cols if c in enriched.columns]]

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    enriched.to_parquet(OUTPUT_PATH, index=False, compression="snappy")
    logger.info("Wrote %s (%.1f MB, %d rows)",
                OUTPUT_PATH,
                OUTPUT_PATH.stat().st_size / 1e6,
                len(enriched))

    # Sanity summary
    logger.info("Sentiment summary:")
    logger.info("  mean: %+.4f", enriched["sentiment_score"].mean())
    logger.info("  label distribution: %s",
                enriched["sentiment_label"].value_counts().to_dict())
    logger.info("  matches covered: %d", enriched["match_id"].nunique())


if __name__ == "__main__":
    main()
