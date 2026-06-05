"""
EXPERIMENT FILE — PHASE 3: ENGAGEMENT FORMULA
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Claude Code: You MAY modify anything in this file (one change per iteration).
Goal: raise composite_eng = 0.5*rivalry_auc + 0.5*rivalry_margin_norm by
re-weighting the engagement formula. See program.md → Phase 3.

These weights map ONE-TO-ONE onto the real production code:
  - FAN_BLEND_WEIGHTS  -> src.engagement.EngagementWeights(volume, affect, volatility, reach)
  - football_weight / fan_weight -> the combined blend in src.engagement.join_with_stage2
A winning config here is a 1-2 line change in src/engagement.py.

Known problem to fix:
  El Clásico (4 goals, rivalry=True) currently ranks #4 — beaten by 7-goal
  non-rivalry blowouts. The production 0.5/0.5 split + volume-heavy fan blend
  over-rewards goals and raw comment volume. We want rivalry fixtures to surface
  as high-engagement (higher rivalry_auc / margin).

Note: there is NO xG in the data (outputs only carry total_goals), so there is
no goal-vs-xG knob. Goals enter only through the Stage-2 football score.

CONSTRAINTS (evaluate.py will warn if violated):
  football_weight + fan_weight  == 1.0
  volume + affect + volatility + reach  == 1.0
"""

ENGAGEMENT_CONFIG = {
    # ── Top-level blend: on-pitch (Stage 2) vs fan-side (Stage 3) ────────────
    "football_weight": 0.35,   # must sum to 1.0 with fan_weight
    "fan_weight":      0.65,

    # ── Fan-blend weights (src.engagement.EngagementWeights) ─────────────────
    # Production baseline: volume 0.45 / affect 0.20 / volatility 0.25 / reach 0.10
    "FAN_BLEND_WEIGHTS": {
        "volume":     0.45,   # log1p(weighted_comment_count) — saturates for El Clásico
        "affect":     0.20,   # |mean sentiment|
        "volatility": 0.25,   # std of sentiment — contested narratives = drama
        "reach":      0.10,   # log1p(unique_subreddits) — cross-community reach
    },
}
