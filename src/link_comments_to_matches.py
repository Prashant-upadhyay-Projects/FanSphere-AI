"""
link_comments_to_matches.py
===========================

Joins Reddit comments to football fixtures using a combination of:
  1. Keyword matching against team aliases and rivalry vocabulary.
  2. Subreddit context as a strong prior.
  3. A temporal window around each fixture's kickoff.

Outputs a long-format DataFrame: one row per (match_id, comment_id) link,
plus a `link_confidence` in [0, 1] so downstream steps can threshold.

Design notes
------------
* Substring matching is a footgun: "real" matches "really", "madrid" matches
  any sentence about the city. We compile each alias into a regex with word
  boundaries (`\\b…\\b`) so we get token-level matches.

* A comment can legitimately link to multiple fixtures (e.g. it discusses a
  team's recent form). We keep all links and let the engagement step
  aggregate per match. This is a deliberate many-to-many design — it
  preserves signal that a one-best-match heuristic would discard.

* Confidence scoring is a transparent rule-based composition rather than a
  trained model. For a portfolio piece this is the right call: every score
  is auditable. A future iteration could replace this with a small classifier
  trained on hand-labeled (comment, match) pairs.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

import pandas as pd
import yaml


logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Config loading
# ---------------------------------------------------------------------------

@dataclass
class TeamSpec:
    name: str
    alias_regex: re.Pattern
    home_subreddits: set[str] = field(default_factory=set)


@dataclass
class RivalrySpec:
    name: str
    teams: tuple[str, str]
    keyword_regex: re.Pattern


@dataclass
class LinkingConfig:
    teams: dict[str, TeamSpec]
    rivalries: list[RivalrySpec]
    generic_football_subreddits: set[str]

    @classmethod
    def from_yaml(cls, path: Path | str) -> "LinkingConfig":
        with open(path, "r", encoding="utf-8") as fh:
            raw = yaml.safe_load(fh)

        teams = {}
        for team_name, spec in (raw.get("teams") or {}).items():
            aliases = spec.get("aliases", [])
            if not aliases:
                logger.warning("Team %s has no aliases; skipping", team_name)
                continue
            # Build a single compiled regex per team: \b(alias1|alias2|...)\b
            # Sort by length descending so multi-word aliases match before
            # their substrings (e.g. "real madrid" before "real").
            sorted_aliases = sorted(aliases, key=len, reverse=True)
            pattern = r"\b(?:" + "|".join(re.escape(a.lower()) for a in sorted_aliases) + r")\b"
            teams[team_name] = TeamSpec(
                name=team_name,
                alias_regex=re.compile(pattern, re.IGNORECASE),
                home_subreddits={s.lower() for s in spec.get("home_subreddits", [])},
            )

        rivalries = []
        for r_name, r_spec in (raw.get("rivalries") or {}).items():
            kws = r_spec.get("keywords", [])
            if not kws:
                continue
            pat = r"\b(?:" + "|".join(re.escape(k.lower()) for k in kws) + r")\b"
            rivalries.append(RivalrySpec(
                name=r_name,
                teams=tuple(r_spec["teams"]),  # type: ignore[arg-type]
                keyword_regex=re.compile(pat, re.IGNORECASE),
            ))

        generic = {s.lower() for s in raw.get("generic_football_subreddits", [])}
        return cls(teams=teams, rivalries=rivalries, generic_football_subreddits=generic)


# ---------------------------------------------------------------------------
# Linker
# ---------------------------------------------------------------------------

@dataclass
class LinkerOptions:
    window_hours_before: int = 48
    window_hours_after: int = 48
    min_confidence: float = 0.4   # links below this are dropped
    # confidence components (sum-to-1 not required; final clipped to [0, 1]):
    w_both_teams: float = 0.6     # both home + away mentioned in body
    w_one_team: float = 0.35      # only one team mentioned in body
    w_rivalry_keyword: float = 0.25
    w_home_subreddit_prior: float = 0.25
    w_generic_subreddit_prior: float = 0.10


class MatchLinker:
    """
    Links comments to matches.

    Usage
    -----
        cfg = LinkingConfig.from_yaml("config/team_aliases.yaml")
        linker = MatchLinker(cfg)
        links_df = linker.link(comments_df, matches_df)
    """

    def __init__(
        self,
        config: LinkingConfig,
        options: LinkerOptions | None = None,
    ) -> None:
        self.cfg = config
        self.opts = options or LinkerOptions()

    # ----- comment-level team detection (precomputed once) ----------------

    def _detect_teams_in_comment(self, body: str, subreddit: str) -> dict[str, float]:
        """
        Return a dict mapping team_name -> base evidence score (before joining
        to a specific match). Score components:
          - regex hit in body: 1.0
          - subreddit is home_subreddit for that team: 0.5 (added on top)
        """
        body_lc = body.lower()
        scores: dict[str, float] = {}
        sub = subreddit.lower()

        for team_name, spec in self.cfg.teams.items():
            score = 0.0
            if spec.alias_regex.search(body_lc):
                score += 1.0
            if sub in spec.home_subreddits:
                score += 0.5
            if score > 0:
                scores[team_name] = score
        return scores

    def _detect_rivalry(self, body: str) -> set[tuple[str, str]]:
        """Return the set of team-pairs implied by rivalry keywords in this body."""
        body_lc = body.lower()
        hits: set[tuple[str, str]] = set()
        for riv in self.cfg.rivalries:
            if riv.keyword_regex.search(body_lc):
                hits.add(tuple(sorted(riv.teams)))  # type: ignore[arg-type]
        return hits

    # ----- main link routine ----------------------------------------------

    def link(
        self,
        comments: pd.DataFrame,
        matches: pd.DataFrame,
    ) -> pd.DataFrame:
        """
        Parameters
        ----------
        comments : DataFrame with at least columns
                   [id, body, created_utc, subreddit, score]
        matches  : DataFrame with at least columns
                   [match_id, home_team, away_team, match_date]
                   match_date must be parseable to UTC.

        Returns
        -------
        DataFrame with columns:
            match_id, comment_id, subreddit, created_utc, match_date,
            link_confidence, link_reasons (semicolon-joined string)
        """
        self._validate(comments, matches)

        # Normalize match timestamps to epoch seconds for cheap arithmetic comparison.
        # Note: pandas 2.x may store datetimes at us / ms / ns precision depending on
        # the input format. Using total_seconds() against the UTC epoch is the only
        # precision-agnostic way to get epoch seconds reliably.
        m = matches.copy()
        m["match_date"] = pd.to_datetime(m["match_date"], utc=True, errors="coerce")
        m = m.dropna(subset=["match_date"]).reset_index(drop=True)
        m["match_epoch"] = (
            (m["match_date"] - pd.Timestamp("1970-01-01", tz="UTC")).dt.total_seconds()
        ).astype("int64")

        window_before = self.opts.window_hours_before * 3600
        window_after = self.opts.window_hours_after * 3600

        # Pre-detect teams per comment once. This is the expensive step
        # (regex over millions of comments), so we do it before the join.
        # NB: Helper columns avoid leading underscores because pandas itertuples
        # renames underscore-prefixed attrs to positional names (_0, _1, ...).
        logger.info("Pre-detecting team mentions in %d comments...", len(comments))
        comments = comments.copy()
        team_detections: list[dict[str, float]] = []
        rivalry_detections: list[set[tuple[str, str]]] = []
        for body, sub in zip(comments["body"].astype(str), comments["subreddit"].astype(str)):
            team_detections.append(self._detect_teams_in_comment(body, sub))
            rivalry_detections.append(self._detect_rivalry(body))
        comments["teams_hit"] = team_detections
        comments["rivalries_hit"] = rivalry_detections

        # Drop comments with zero team and zero rivalry signal up front.
        mask_has_signal = (
            comments["teams_hit"].map(bool) | comments["rivalries_hit"].map(bool)
        )
        signal_comments = comments.loc[mask_has_signal].copy()
        logger.info(
            "Of %d comments, %d carry at least one team or rivalry signal (%.1f%%).",
            len(comments), len(signal_comments),
            100 * len(signal_comments) / max(len(comments), 1),
        )

        # For each match, find candidate comments in the time window and score.
        link_rows: list[dict] = []
        for match_row in m.itertuples(index=False):
            t = match_row.match_epoch
            lo = t - window_before
            hi = t + window_after

            in_window = signal_comments[
                (signal_comments["created_utc"] >= lo)
                & (signal_comments["created_utc"] <= hi)
            ]
            if in_window.empty:
                continue

            home = match_row.home_team
            away = match_row.away_team
            rivalry_pair = tuple(sorted([home, away]))

            for c in in_window.itertuples(index=False):
                teams_hit = c.teams_hit
                rivalries_hit = c.rivalries_hit

                home_hit = home in teams_hit
                away_hit = away in teams_hit
                rivalry_hit = rivalry_pair in rivalries_hit

                if not (home_hit or away_hit or rivalry_hit):
                    continue

                conf, reasons = self._score(
                    home_hit=home_hit,
                    away_hit=away_hit,
                    rivalry_hit=rivalry_hit,
                    subreddit=c.subreddit,
                    home=home,
                    away=away,
                )
                if conf < self.opts.min_confidence:
                    continue

                link_rows.append({
                    "match_id": match_row.match_id,
                    "comment_id": c.id,
                    "subreddit": c.subreddit,
                    "created_utc": c.created_utc,
                    "match_epoch": t,
                    "minutes_from_kickoff": (c.created_utc - t) / 60.0,
                    "link_confidence": round(conf, 3),
                    "link_reasons": ";".join(reasons),
                })

        if not link_rows:
            logger.warning("No links produced. Check date ranges and team aliases.")
            return pd.DataFrame(columns=[
                "match_id", "comment_id", "subreddit", "created_utc",
                "match_epoch", "minutes_from_kickoff",
                "link_confidence", "link_reasons",
            ])

        out = pd.DataFrame(link_rows)
        logger.info(
            "Produced %d (match, comment) links across %d unique matches.",
            len(out), out["match_id"].nunique(),
        )
        return out

    # ----- scoring --------------------------------------------------------

    def _score(
        self,
        *,
        home_hit: bool,
        away_hit: bool,
        rivalry_hit: bool,
        subreddit: str,
        home: str,
        away: str,
    ) -> tuple[float, list[str]]:
        """Compose a [0,1] confidence from independent evidence sources."""
        score = 0.0
        reasons: list[str] = []

        if home_hit and away_hit:
            score += self.opts.w_both_teams
            reasons.append("both_teams_mentioned")
        elif home_hit or away_hit:
            score += self.opts.w_one_team
            reasons.append("home_mentioned" if home_hit else "away_mentioned")

        if rivalry_hit:
            score += self.opts.w_rivalry_keyword
            reasons.append("rivalry_keyword")

        sub = subreddit.lower()
        home_subs = self.cfg.teams.get(home, TeamSpec(home, re.compile(""))).home_subreddits
        away_subs = self.cfg.teams.get(away, TeamSpec(away, re.compile(""))).home_subreddits

        if sub in home_subs or sub in away_subs:
            score += self.opts.w_home_subreddit_prior
            reasons.append("team_home_subreddit")
        elif sub in self.cfg.generic_football_subreddits:
            score += self.opts.w_generic_subreddit_prior
            reasons.append("generic_football_subreddit")

        # Clip to [0, 1] — components can sum >1 in the both-teams + rivalry +
        # home-sub case, which is the highest-confidence configuration.
        return min(score, 1.0), reasons

    # ----- validation -----------------------------------------------------

    @staticmethod
    def _validate(comments: pd.DataFrame, matches: pd.DataFrame) -> None:
        required_c = {"id", "body", "created_utc", "subreddit"}
        required_m = {"match_id", "home_team", "away_team", "match_date"}
        missing_c = required_c - set(comments.columns)
        missing_m = required_m - set(matches.columns)
        if missing_c:
            raise ValueError(f"comments missing columns: {missing_c}")
        if missing_m:
            raise ValueError(f"matches missing columns: {missing_m}")
