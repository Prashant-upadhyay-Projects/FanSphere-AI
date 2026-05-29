"""End-to-end pipeline orchestrator.

Flow:
    1. StatsBomb  → matches  + goal events
    2. Reddit     → posts / comments
    3. Sentiment  → VADER scoring + emotion overlay
    4. Match link → naive team-name keyword join Reddit → matches
    5. KPIs       → excitement, hype, engagement
    6. Persist    → PostgreSQL
    7. Segment    → KMeans fan clustering (written to outputs/ as CSV)
"""

from __future__ import annotations

import re
from pathlib import Path

import pandas as pd

from . import db_loader, generate_metrics, sentiment_analysis
from .config import OUTPUTS_DIR, SETTINGS, get_engine, get_logger
from .load_statsbomb import goals_per_match, load_goal_events, load_matches
from .reddit_scraper import scrape_subreddits

LOG = get_logger(__name__)


# ---------------------------------------------------------------------------
# Reddit → match linking (lightweight keyword match)
# ---------------------------------------------------------------------------
_WORD_RE = re.compile(r"[a-zA-Z]+")


def _team_keywords(team_name: str) -> set[str]:
    """Coarse keyword set for fuzzy team detection in Reddit text."""
    tokens = {t.lower() for t in _WORD_RE.findall(team_name) if len(t) > 3}
    # Add common shorthands
    shorthand = {
        "Barcelona": {"barca", "fcb"},
        "Real Madrid": {"madrid", "rma"},
        "Manchester United": {"united", "manu", "mufc"},
        "Manchester City": {"city", "mcfc"},
        "Liverpool": {"lfc"},
        "Arsenal": {"arsenal", "afc"},
        "Tottenham Hotspur": {"spurs", "thfc"},
    }
    tokens |= shorthand.get(team_name, set())
    return tokens


def _link_sentiment_to_matches(
    sentiment: pd.DataFrame, matches: pd.DataFrame
) -> pd.DataFrame:
    """Attach `match_id` to sentiment rows when both teams are mentioned.

    Deliberately conservative: a row is linked only when keywords for BOTH
    teams appear, anchoring it to a specific fixture.  Posts about a single
    club stay unlinked and feed into general sentiment trends instead.
    """
    if sentiment.empty or matches.empty:
        sentiment["match_id"] = None
        return sentiment

    # Pre-compute keyword sets once
    team_keywords = {
        team: _team_keywords(team)
        for team in pd.concat([matches["home_team"], matches["away_team"]]).unique()
    }

    match_lookup = matches[["match_id", "home_team", "away_team"]].to_dict("records")

    def find_match(text: str) -> int | None:
        lowered = text.lower()
        for m in match_lookup:
            home_kw = team_keywords[m["home_team"]]
            away_kw = team_keywords[m["away_team"]]
            if home_kw and away_kw and \
               any(k in lowered for k in home_kw) and \
               any(k in lowered for k in away_kw):
                return m["match_id"]
        return None

    LOG.info("Linking %d sentiment rows to matches", len(sentiment))
    sentiment = sentiment.copy()
    sentiment["match_id"] = sentiment["comment"].fillna("").map(find_match)
    linked = sentiment["match_id"].notna().sum()
    LOG.info("Linked %d/%d sentiment rows to a fixture", linked, len(sentiment))
    return sentiment


# ---------------------------------------------------------------------------
# Main entrypoint
# ---------------------------------------------------------------------------
def run(
    skip_reddit: bool = False,
    skip_statsbomb: bool = False,
    persist: bool = True,
) -> dict:
    """Execute the pipeline.  Returns a summary dict suitable for logging."""
    summary: dict = {}

    # 1) StatsBomb -------------------------------------------------------
    if skip_statsbomb:
        matches = pd.DataFrame()
        goals = pd.DataFrame(columns=["match_id", "goal_events"])
    else:
        matches = load_matches(SETTINGS.statsbomb_competition_ids)
        goal_events = load_goal_events(matches["match_id"]) if not matches.empty else pd.DataFrame()
        goals = goals_per_match(goal_events)
        summary["matches"] = len(matches)
        summary["goal_events"] = len(goal_events)

    # 2) Reddit ----------------------------------------------------------
    if skip_reddit:
        reddit = pd.DataFrame(
            columns=["source", "external_id", "comment", "upvotes", "posted_at"]
        )
    else:
        reddit = scrape_subreddits()
        summary["reddit_items"] = len(reddit)

    # 3) Sentiment -------------------------------------------------------
    sentiment = sentiment_analysis.score_dataframe(reddit) if not reddit.empty else reddit
    summary["sentiment_summary"] = sentiment_analysis.sentiment_summary(sentiment)

    # 4) Match linking ---------------------------------------------------
    sentiment = _link_sentiment_to_matches(sentiment, matches)

    # 5) KPIs ------------------------------------------------------------
    engagement = (
        generate_metrics.build_engagement_metrics(matches, sentiment, goals)
        if not matches.empty
        else pd.DataFrame()
    )
    summary["fan_sentiment_score"] = generate_metrics.fan_sentiment_score(sentiment)

    # 6) Persist ---------------------------------------------------------
    if persist:
        engine = get_engine()
        db_loader.upsert_matches(matches, engine)
        db_loader.insert_sentiment(sentiment, engine)
        db_loader.upsert_engagement(engagement, engine)

    # 7) Segmentation ----------------------------------------------------
    if not sentiment.empty:
        segments, _ = generate_metrics.segment_fans(sentiment)
        seg_path: Path = OUTPUTS_DIR / "fan_segments.csv"
        segments.to_csv(seg_path)
        summary["segment_csv"] = str(seg_path)

    # Side-output snapshots for the README / dashboard build -------------
    if not engagement.empty:
        engagement.to_csv(OUTPUTS_DIR / "engagement_metrics.csv", index=False)
    if not sentiment.empty:
        sentiment.to_csv(OUTPUTS_DIR / "fan_sentiment.csv", index=False)

    LOG.info("Pipeline complete: %s", summary)
    return summary


if __name__ == "__main__":  # pragma: no cover
    run()
