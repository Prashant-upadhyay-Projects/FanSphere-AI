"""Sentiment analysis using VADER.

Each text record gets:
- sentiment_score : VADER compound, [-1, 1]
- sentiment_label : positive / neutral / negative
- emotion         : excitement / frustration / optimism / neutral
                    (a light lexicon-based overlay — deliberately simple)
"""

from __future__ import annotations

import re
from typing import Iterable

import pandas as pd
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

from .config import get_logger

LOG = get_logger(__name__)
_ANALYZER = SentimentIntensityAnalyzer()


# ---------------------------------------------------------------------------
# Lexicons for the light-touch emotion overlay
# ---------------------------------------------------------------------------
EXCITEMENT_TERMS = {
    "goal", "goooal", "screamer", "wonderkid", "unreal", "insane", "incredible",
    "magic", "world class", "wow", "wow!", "amazing", "let's go", "lfg",
}
FRUSTRATION_TERMS = {
    "shocking", "disgrace", "awful", "terrible", "rubbish", "trash", "sack",
    "fire him", "embarrassing", "bottled", "joke", "robbed", "shambles",
}
OPTIMISM_TERMS = {
    "future", "promising", "build", "youth", "next season", "kids", "hope",
    "rebuild", "exciting times", "bright",
}

_WORD_RE = re.compile(r"[a-z][a-z']+")


def _emotion_label(text: str, compound: float) -> str:
    lowered = text.lower()
    tokens = set(_WORD_RE.findall(lowered))

    excitement_hit = bool(tokens & EXCITEMENT_TERMS) or any(t in lowered for t in EXCITEMENT_TERMS)
    frustration_hit = bool(tokens & FRUSTRATION_TERMS) or any(t in lowered for t in FRUSTRATION_TERMS)
    optimism_hit = bool(tokens & OPTIMISM_TERMS) or any(t in lowered for t in OPTIMISM_TERMS)

    # Resolution rules — emotional cue beats sentiment magnitude
    if excitement_hit and compound >= 0:
        return "excitement"
    if frustration_hit and compound <= 0:
        return "frustration"
    if optimism_hit:
        return "optimism"
    return "neutral"


def _label_from_compound(compound: float) -> str:
    if compound >= 0.05:
        return "positive"
    if compound <= -0.05:
        return "negative"
    return "neutral"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def score_text(text: str) -> dict:
    """Score a single piece of text."""
    compound = _ANALYZER.polarity_scores(text or "")["compound"]
    return {
        "sentiment_score": round(compound, 4),
        "sentiment_label": _label_from_compound(compound),
        "emotion": _emotion_label(text or "", compound),
    }


def score_dataframe(df: pd.DataFrame, text_col: str = "comment") -> pd.DataFrame:
    """Append sentiment columns to a DataFrame.  Non-destructive (returns a copy)."""
    if df.empty:
        for col in ("sentiment_score", "sentiment_label", "emotion"):
            df[col] = pd.Series(dtype="object")
        return df

    LOG.info("Scoring sentiment for %d records", len(df))
    scored = df[text_col].fillna("").map(score_text).apply(pd.Series)
    return pd.concat([df.reset_index(drop=True), scored.reset_index(drop=True)], axis=1)


def sentiment_summary(df: pd.DataFrame) -> dict:
    """Quick distribution summary — useful for logs and the README screenshot."""
    if df.empty:
        return {"positive": 0, "neutral": 0, "negative": 0, "mean_compound": 0.0}
    counts = df["sentiment_label"].value_counts().to_dict()
    return {
        "positive": int(counts.get("positive", 0)),
        "neutral": int(counts.get("neutral", 0)),
        "negative": int(counts.get("negative", 0)),
        "mean_compound": float(df["sentiment_score"].mean()),
    }
