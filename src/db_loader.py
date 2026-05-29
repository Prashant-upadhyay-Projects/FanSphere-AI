"""PostgreSQL loader.

Each public function takes a tidy DataFrame and writes it to the matching
table.  Writes are idempotent: matches and engagement_metrics use UPSERT on
their natural key; fan_sentiment relies on the UNIQUE (source, external_id)
constraint and ignores duplicates.
"""

from __future__ import annotations

import pandas as pd
from sqlalchemy import text
from sqlalchemy.engine import Engine

from .config import get_engine, get_logger

LOG = get_logger(__name__)


# ---------------------------------------------------------------------------
# Generic helper
# ---------------------------------------------------------------------------
def _exec(engine: Engine, sql: str, rows: list[dict]) -> int:
    if not rows:
        return 0
    with engine.begin() as conn:
        conn.execute(text(sql), rows)
    return len(rows)


# ---------------------------------------------------------------------------
# matches
# ---------------------------------------------------------------------------
def upsert_matches(df: pd.DataFrame, engine: Engine | None = None) -> int:
    engine = engine or get_engine()
    if df.empty:
        LOG.info("No matches to load")
        return 0

    sql = """
        INSERT INTO matches (
            match_id, home_team, away_team, competition, season,
            match_date, home_score, away_score, is_rivalry
        ) VALUES (
            :match_id, :home_team, :away_team, :competition, :season,
            :match_date, :home_score, :away_score, :is_rivalry
        )
        ON CONFLICT (match_id) DO UPDATE SET
            home_team   = EXCLUDED.home_team,
            away_team   = EXCLUDED.away_team,
            competition = EXCLUDED.competition,
            season      = EXCLUDED.season,
            match_date  = EXCLUDED.match_date,
            home_score  = EXCLUDED.home_score,
            away_score  = EXCLUDED.away_score,
            is_rivalry  = EXCLUDED.is_rivalry;
    """
    rows = df.to_dict(orient="records")
    n = _exec(engine, sql, rows)
    LOG.info("Upserted %d matches", n)
    return n


# ---------------------------------------------------------------------------
# fan_sentiment
# ---------------------------------------------------------------------------
def insert_sentiment(df: pd.DataFrame, engine: Engine | None = None) -> int:
    engine = engine or get_engine()
    if df.empty:
        LOG.info("No sentiment rows to load")
        return 0

    sql = """
        INSERT INTO fan_sentiment (
            source, external_id, comment, upvotes,
            sentiment_score, sentiment_label, emotion,
            match_id, posted_at
        ) VALUES (
            :source, :external_id, :comment, :upvotes,
            :sentiment_score, :sentiment_label, :emotion,
            :match_id, :posted_at
        )
        ON CONFLICT (source, external_id) DO NOTHING;
    """

    work = df.copy()
    if "match_id" not in work.columns:
        work["match_id"] = None
    work["match_id"] = work["match_id"].where(work["match_id"].notna(), None)

    rows = work[
        [
            "source",
            "external_id",
            "comment",
            "upvotes",
            "sentiment_score",
            "sentiment_label",
            "emotion",
            "match_id",
            "posted_at",
        ]
    ].to_dict(orient="records")

    n = _exec(engine, sql, rows)
    LOG.info("Inserted %d sentiment rows (duplicates skipped)", n)
    return n


# ---------------------------------------------------------------------------
# engagement_metrics
# ---------------------------------------------------------------------------
def upsert_engagement(df: pd.DataFrame, engine: Engine | None = None) -> int:
    engine = engine or get_engine()
    if df.empty:
        LOG.info("No engagement rows to load")
        return 0

    sql = """
        INSERT INTO engagement_metrics (
            match_id, comment_volume, upvote_total, goal_events,
            avg_sentiment, engagement_score, excitement_index, match_hype_score
        ) VALUES (
            :match_id, :comment_volume, :upvote_total, :goal_events,
            :avg_sentiment, :engagement_score, :excitement_index, :match_hype_score
        )
        ON CONFLICT (match_id) DO UPDATE SET
            comment_volume   = EXCLUDED.comment_volume,
            upvote_total     = EXCLUDED.upvote_total,
            goal_events      = EXCLUDED.goal_events,
            avg_sentiment    = EXCLUDED.avg_sentiment,
            engagement_score = EXCLUDED.engagement_score,
            excitement_index = EXCLUDED.excitement_index,
            match_hype_score = EXCLUDED.match_hype_score,
            computed_at      = CURRENT_TIMESTAMP;
    """
    rows = df.to_dict(orient="records")
    n = _exec(engine, sql, rows)
    LOG.info("Upserted %d engagement rows", n)
    return n
