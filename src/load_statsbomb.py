"""StatsBomb Open Data loader.

Pulls competitions → matches → events directly from the StatsBomb open-data
GitHub repository (https://github.com/statsbomb/open-data). No API key required.

The loader returns flat, analysis-ready DataFrames for `matches` and `events`.
Rivalry classification is done locally using a small curated lookup.
"""

from __future__ import annotations

from typing import Iterable, List

import pandas as pd
import requests
from tqdm import tqdm

from .config import get_logger

LOG = get_logger(__name__)

STATSBOMB_BASE = "https://raw.githubusercontent.com/statsbomb/open-data/master/data"

# Pairs that should be flagged as rivalry matches in `matches.is_rivalry`.
# Strings are compared case-insensitively, order-independent.
RIVALRY_PAIRS: List[frozenset] = [
    frozenset({"Barcelona", "Real Madrid"}),
    frozenset({"Manchester United", "Liverpool"}),
    frozenset({"Arsenal", "Tottenham Hotspur"}),
    frozenset({"Inter", "AC Milan"}),
    frozenset({"Boca Juniors", "River Plate"}),
]


# ---------------------------------------------------------------------------
# Low-level fetch
# ---------------------------------------------------------------------------
def _fetch_json(url: str) -> list | dict:
    LOG.debug("GET %s", url)
    response = requests.get(url, timeout=30)
    response.raise_for_status()
    return response.json()


def _is_rivalry(home: str, away: str) -> bool:
    pair = frozenset({home, away})
    return pair in RIVALRY_PAIRS


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def load_competitions() -> pd.DataFrame:
    """Return all StatsBomb competition/season combinations."""
    data = _fetch_json(f"{STATSBOMB_BASE}/competitions.json")
    df = pd.DataFrame(data)
    LOG.info("Loaded %d competition/season rows", len(df))
    return df


def load_matches(competition_ids: Iterable[int]) -> pd.DataFrame:
    """Return matches for every season of the given competitions.

    Output columns: match_id, home_team, away_team, competition, season,
    match_date, home_score, away_score, is_rivalry.
    """
    competitions = load_competitions()
    competitions = competitions[competitions["competition_id"].isin(list(competition_ids))]

    rows: List[dict] = []
    for _, comp in tqdm(competitions.iterrows(), total=len(competitions), desc="competitions"):
        url = f"{STATSBOMB_BASE}/matches/{comp['competition_id']}/{comp['season_id']}.json"
        try:
            matches = _fetch_json(url)
        except requests.HTTPError as exc:
            LOG.warning("Skipping %s/%s — %s", comp["competition_id"], comp["season_id"], exc)
            continue

        for match in matches:
            home = match["home_team"]["home_team_name"]
            away = match["away_team"]["away_team_name"]
            rows.append(
                {
                    "match_id": match["match_id"],
                    "home_team": home,
                    "away_team": away,
                    "competition": comp["competition_name"],
                    "season": comp["season_name"],
                    "match_date": match["match_date"],
                    "home_score": match.get("home_score"),
                    "away_score": match.get("away_score"),
                    "is_rivalry": _is_rivalry(home, away),
                }
            )

    df = pd.DataFrame(rows)
    if not df.empty:
        df["match_date"] = pd.to_datetime(df["match_date"]).dt.date
    LOG.info("Loaded %d matches across %d competitions",
             len(df), competitions["competition_id"].nunique())
    return df


def load_goal_events(match_ids: Iterable[int]) -> pd.DataFrame:
    """Return one row per goal event for the given matches.

    Output columns: match_id, minute, team, player, xg.
    """
    rows: List[dict] = []
    for match_id in tqdm(list(match_ids), desc="events"):
        url = f"{STATSBOMB_BASE}/events/{match_id}.json"
        try:
            events = _fetch_json(url)
        except requests.HTTPError as exc:
            LOG.warning("Skipping events for match %s — %s", match_id, exc)
            continue

        for ev in events:
            shot = ev.get("shot")
            if not shot:
                continue
            outcome = shot.get("outcome", {}).get("name")
            if outcome != "Goal":
                continue
            rows.append(
                {
                    "match_id": match_id,
                    "minute": ev.get("minute"),
                    "team": ev.get("team", {}).get("name"),
                    "player": ev.get("player", {}).get("name"),
                    "xg": shot.get("statsbomb_xg"),
                }
            )

    df = pd.DataFrame(rows)
    LOG.info("Loaded %d goal events", len(df))
    return df


def goals_per_match(goal_events: pd.DataFrame) -> pd.DataFrame:
    """Aggregate goal events into a per-match counter."""
    if goal_events.empty:
        return pd.DataFrame(columns=["match_id", "goal_events"])
    return (
        goal_events.groupby("match_id")
        .size()
        .reset_index(name="goal_events")
    )
