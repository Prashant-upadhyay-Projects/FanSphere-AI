"""
sentiment.py
============

Sentiment scoring layer.

This module exposes a small interface (`SentimentAnalyzer`) and a concrete
VADER-backed implementation. Anything that returns a real number in [-1, 1]
satisfies the interface; upgrading to a transformer (e.g. DistilBERT
fine-tuned on social-media text, or `cardiffnlp/twitter-roberta-base-sentiment`)
is a drop-in replacement.

Why VADER as the baseline
-------------------------
* Rule-based and lexicon-driven, so 100% deterministic and offline.
* Specifically tuned for social-media text (caps, !, emoticons, slang),
  which is what Reddit comments look like.
* No GPU, no model downloads, runs in milliseconds per comment.

The cost: it doesn't understand context ("not bad" is mishandled in some
cases, sarcasm fails). For a portfolio piece this is fine as the baseline,
and the architecture makes the upgrade trivial.

Why not load a transformer here directly?
-----------------------------------------
Three reasons. (1) Reproducibility — the user shouldn't need a 500MB model
download to run Stage 3. (2) Determinism — quantization and batching can
introduce small numerical noise. (3) Speed — VADER on a million comments
runs in seconds; a transformer takes minutes on CPU. We expose the seam,
the user can pull a transformer in later.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Iterable

import pandas as pd


logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Interface
# ---------------------------------------------------------------------------

class SentimentAnalyzer(ABC):
    """
    Abstract sentiment analyzer.

    Implementations must:
      * return a float in [-1, 1] from `score(text)`
      * support batch scoring via `score_batch(texts)`
      * expose a `name` for logging / output provenance
    """
    name: str = "base"

    @abstractmethod
    def score(self, text: str) -> float: ...

    def score_batch(self, texts: Iterable[str]) -> list[float]:
        """Default batch impl falls back to per-item; subclasses can override."""
        return [self.score(t) for t in texts]


# ---------------------------------------------------------------------------
# VADER implementation
# ---------------------------------------------------------------------------

class VaderAnalyzer(SentimentAnalyzer):
    """
    VADER from the `vaderSentiment` package.

    We use the standalone `vaderSentiment` package rather than `nltk.sentiment`
    to avoid the nltk download-on-first-run side effect that breaks offline
    reproducibility. `vaderSentiment` ships the lexicon inside the wheel.
    """
    name = "vader"

    def __init__(self) -> None:
        try:
            from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
        except ImportError as e:  # pragma: no cover
            raise ImportError(
                "vaderSentiment is required. Install: pip install vaderSentiment"
            ) from e
        self._analyzer = SentimentIntensityAnalyzer()

    def score(self, text: str) -> float:
        if not text:
            return 0.0
        # The `compound` score is VADER's normalized [-1, 1] aggregate.
        return float(self._analyzer.polarity_scores(text)["compound"])


# ---------------------------------------------------------------------------
# Transformer placeholder — interface only
# ---------------------------------------------------------------------------

class TransformerAnalyzer(SentimentAnalyzer):
    """
    Stub for a future Hugging Face transformer-based analyzer.

    Not implemented in this stage — kept as a typed placeholder so the
    integration point is visible. A real implementation would:

        from transformers import pipeline
        self._pipe = pipeline(
            "sentiment-analysis",
            model="cardiffnlp/twitter-roberta-base-sentiment-latest",
            device=-1,  # or 0 for GPU
        )

    and map model labels {"negative", "neutral", "positive"} into [-1, 1].
    """
    name = "transformer"

    def __init__(self, model_name: str = "cardiffnlp/twitter-roberta-base-sentiment-latest") -> None:
        self.model_name = model_name
        raise NotImplementedError(
            "TransformerAnalyzer is intentionally a stub. "
            "Implement in a follow-up stage when GPU/throughput budget allows."
        )

    def score(self, text: str) -> float:  # pragma: no cover
        raise NotImplementedError


# ---------------------------------------------------------------------------
# DataFrame helpers
# ---------------------------------------------------------------------------

def score_dataframe(
    df: pd.DataFrame,
    *,
    text_col: str = "body",
    out_col: str = "sentiment",
    analyzer: SentimentAnalyzer | None = None,
) -> pd.DataFrame:
    """
    Append a sentiment column to a DataFrame.

    Returns a *new* DataFrame (does not mutate input). The analyzer used is
    recorded as a `sentiment_model` column for provenance — analysts looking
    at the output later can tell which model the numbers came from.
    """
    analyzer = analyzer or VaderAnalyzer()
    if text_col not in df.columns:
        raise ValueError(f"text_col '{text_col}' not in dataframe")

    logger.info("Scoring %d rows with analyzer=%s", len(df), analyzer.name)
    scores = analyzer.score_batch(df[text_col].astype(str).tolist())
    out = df.copy()
    out[out_col] = scores
    out["sentiment_model"] = analyzer.name
    return out
