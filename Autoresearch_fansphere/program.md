# FanSphere AutoResearch — Program (Research Agenda)

## What this system does
FanSphere joins StatsBomb on-pitch data with Reddit fan comments, scores comment
sentiment (VADER), segments authors into behavioural cohorts, and produces a
composite engagement signal per fixture. This loop runs scientific experiments on
that pipeline, keeping only changes that beat the current best on a phase-specific,
**label-grounded** metric.

The experiments operate on the **real production code** (`src/engagement.py`,
`src/sentiment.py`, and the clustering in `src/generate_fan_segments.py`), so a
winning config is a 1–2 line change you can port into the project.

---

## The ratchet metrics (per phase)

> Each phase ratchets against its **own measured baseline** (`evaluate.py --phase N
> --baseline`), stored in `budget.json`. There is no single global baseline — Phase 1
> measures clustering quality, Phases 2–3 measure engagement-ranking validity.

### Phase 1 — clustering quality
```
composite = 0.6 * silhouette + 0.4 * cluster_stability
```
- **silhouette** — sklearn silhouette on the scaled author features (tighter, more
  separable cohorts → higher). Clamped to [0, 1].
- **cluster_stability** — mean Adjusted Rand Index over 10 subsample re-clusterings
  (does the cohort structure survive perturbation?). A degenerate 1-cluster solution
  is killed because its silhouette is 0.

### Phases 2 & 3 — engagement validity
```
composite = 0.5 * rivalry_auc + 0.5 * rivalry_margin_norm
```
- **rivalry_auc** — `roc_auc_score(is_rivalry, engagement_score)`: do the 2 rivalry
  fixtures (El Clásico) surface as high-engagement among all 10? Directly targets the
  "Clásico ranks #4" problem.
- **rivalry_margin_norm** — normalized gap between mean engagement of rivalry vs
  non-rivalry fixtures; supplies a continuous gradient where AUC is coarse.
- **Diagnostics (logged, NOT optimized):** each Clásico's rank, the top-3 fixtures,
  and Spearman(score, total_goals) — a sanity check that goals still matter without
  dominating.

Only keep a change that **strictly beats** the current best for the active phase.

---

## Phase 1 — Clustering (`experiment_1_clustering.py`)
**Baseline:** KMeans, k=3, StandardScaler, features = comment_frequency /
sentiment_volatility / engagement_activity (mirrors `generate_fan_segments.py`,
silhouette ≈ 0.40).

- **H1.1 — k sweep.** Try k=4, then k=2, k=5. Football fanbases plausibly split into
  ultras / match-watchers / stat-heads / casuals. Watch silhouette *and* stability.
- **H1.2 — RobustScaler.** Median/IQR scaling resists power-user outliers (authors
  with 1000+ comments) that distort StandardScaler. Try with the best k so far.
- **H1.3 — GMM.** Softer boundaries (`algorithm="gmm"`) for fuzzy fan behaviour;
  same k as the best KMeans.
- **H1.4 — Feature set.** Add `avg_sentiment`, then `positive_ratio`, then
  `matches_covered`. More behavioural axes can sharpen separation — or add noise.
- **H1.5 — Agglomerative.** `algorithm="agglomerative"` as a deterministic structural
  cross-check on the best k.

## Phase 2 — Sentiment (`experiment_2_sentiment.py`)
**Baseline:** VADER, mean aggregation. Engagement weights held at production default.

- **H2.1 — Median aggregation.** `aggregation="median"`: robust to the bimodal
  sentiment of rivalry fixtures (rival fans pulling opposite ways).
- **H2.2 — Upvote-weighted.** `aggregation="weighted_mean"`: community-endorsed
  comments count more than noise.
- **H2.3 — TextBlob cross-check.** `model="textblob"`: a different lexicon. If rankings
  move materially, VADER may be overfit to slang.
- *(Deferred: cardiffnlp/twitter-roberta — needs torch+transformers; revisit later
  with cached, sampled scoring.)*

## Phase 3 — Engagement formula (`experiment_3_engagement.py`)
**Baseline:** football 0.5 / fan 0.5; fan-blend volume 0.45 / affect 0.20 /
volatility 0.25 / reach 0.10 (the real `EngagementWeights`).
**Problem to solve:** the Clásico (4 goals, rivalry) ranks #4 behind 7-goal blowouts.

- **H3.1 — Fan-biased top split.** football=0.35, fan=0.65. It's a *fan* intelligence
  platform; fan affect is the product.
- **H3.2 — More volatility.** Raise the fan-blend `volatility` weight (contested,
  arguing fanbases = drama), lower `volume`. Keep the four weights summing to 1.0.
- **H3.3 — Down-weight raw volume.** El Clásico's comment volume saturates and drowns
  intensity; cut `volume`, raise `affect` + `volatility`.
- **H3.4 — Combined.** Best top-split + best fan-blend together, only if each helped
  alone.
- *(There is no xG in the data — only `total_goals` — so there is no goal-vs-xG knob.)*

---

## Constraints
- One hypothesis (one config change) per iteration.
- Always revert on a non-improving result (restore from `.snapshots/`).
- Log every attempt — kept or discarded — to `results_log.md`.
- Respect `budget.json` (`max_iterations`) and the usage guardrail (`guardrail.py`).
- Never advance phases or edit `../src/` — the human does both.
