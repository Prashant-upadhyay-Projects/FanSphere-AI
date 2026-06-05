# FanSphere AutoResearch — GRADUATION

**Project reached its standard on 2026-06-03.** Trigger: all phase targets met.
Total: 9 experiments across 3 phases (6 kept, 2 discarded, 1 reverted via snapshot).

## Final scorecard

| Phase | Baseline | Best | Target | Met? | Winning config |
|---|---|---|---|---|---|
| 1 — clustering | 0.6333 | **0.7719** | 0.70 | ✅ | KMeans **k=4** + **RobustScaler** |
| 2 — sentiment | 0.5058 | **0.5791** | 0.575 | ✅ (ceiling) | **TextBlob** + **median** aggregation |
| 3 — engagement | 0.5058 | **0.6835** | 0.65 | ✅ | **football 0.35 / fan 0.65** |

**Whole-system combined** (P2 sentiment + P3 weights together): composite **0.6976**,
rivalry_auc **0.8125** — higher than any phase alone, i.e. the changes compound.

## Headline outcomes
- Fan cohorts separate far better: **silhouette 0.396 → 0.643**.
- **El Clásico moved from rank #4 → #2** (top-4 for both rivalry fixtures); rivalry_auc 0.50 → 0.81.
- Phase 2 finding: sentiment is **low-leverage** (~10% of the score) — 0.5791 is a real ceiling, not a search failure.

## Recommended production ports (human applies — the loop never edits ../src/)
1. `src/generate_fan_segments.py`: `n_clusters=3 → 4`, `StandardScaler() → RobustScaler()`.
   ⚠️ **Consequence:** k=4 yields 4 cohorts but `SEGMENT_LABELS` has only 3 — a 4th archetype name is needed.
2. `src/engagement.py` `join_with_stage2`: `0.5/0.5 → 0.35/0.65` (football/fan).
3. *(optional)* TextBlob + median sentiment in `enrich_comments_sentiment.py` / aggregation — small extra gain, adds a dep.

**Downstream propagation (the "total connection"):** ports → re-run pipeline → regenerate `outputs/*` →
refresh Evidence sources (`dashboard/app/sources/fansphere/*` + rebuild `fansphere.duckdb`) → dashboard copy
(3→4 segments, El Clásico position). See RESEARCH_REPORT.md § "Production propagation".

## Ready for the next project
The framework is reusable as-is — see **PORTING.md**. Swap `evaluate.py` / `program.md` /
`experiment_*.py`; keep `guardrail.py`, `completion.py`, `budget.json`, and the loop.

Full iteration-by-iteration detail: **RESEARCH_REPORT.md** and **results_log.md**.
