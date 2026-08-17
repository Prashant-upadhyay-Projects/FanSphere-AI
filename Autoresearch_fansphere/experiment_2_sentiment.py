"""
EXPERIMENT FILE — PHASE 2: SENTIMENT MODEL & AGGREGATION
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Agent: you MAY modify anything in this file (one change per iteration).
Goal: raise composite_eng = 0.5*rivalry_auc + 0.5*rivalry_margin_norm by
improving sentiment quality. See program.md → Phase 2.

How it's evaluated: evaluate.py re-scores comment bodies with the chosen model,
re-aggregates sentiment to the match level, then runs the REAL engagement code
(src.engagement) and checks how well the resulting scores separate rivalry from
non-rivalry fixtures. Engagement weights are held at the production default so
this phase isolates the sentiment variable.

Baseline (matches production):
  model       = vader
  aggregation = mean
"""

SENTIMENT_CONFIG = {
    # Scoring backend: "vader" | "textblob"
    #   vader    — lexicon tuned for social media (production baseline, fast)
    #   textblob — different lexicon (PatternAnalyzer); a cross-check on VADER
    "model": "textblob",

    # Match-level aggregation of comment sentiment:
    #   "mean"          — simple average (baseline)
    #   "median"        — robust to bimodal rivalry distributions
    #   "weighted_mean" — weight each comment by its Reddit upvote 'score'
    "aggregation": "median",

    # ── Deferred future work (NOT enabled) ───────────────────────────────────
    # A transformer (cardiffnlp/twitter-roberta-base-sentiment-latest) was the
    # original Future-Scope idea. It needs torch+transformers (~2GB) and is slow
    # on CPU/Windows, so it is intentionally out of scope for this lean loop.
    # Prove the loop on vader/textblob first; revisit transformers later with a
    # cached, sampled scoring pass.
}
