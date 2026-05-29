# FanSphere AI — Future Scope, Use Cases & Research Extensions

This document captures where FanSphere AI can go from here. Three sections, each addressing a different audience:

1. **Technical roadmap** — concrete engineering work, ranked by impact and effort.
2. **Commercial use cases** — who would pay for this and why.
3. **Research & academic extensions** — open questions worth investigating, with method sketches.

---

## 1. Technical roadmap

The current build deliberately stops at one season, one league, and one sentiment model. Each row below is an extension I would make in priority order if continuing the project.

### High-impact, low-effort *(weekend changes)*

| Feature | What it gives you | Where to start |
|---|---|---|
| **Expand to full La Liga 2020/21 season** | 38 matchdays × 10 fixtures = 380 matches instead of 10. The statistical claims become defensible at population scale, and the segmentation gets meaningfully more clusters. | `src/load_statsbomb.py` — bump the match list; pipeline already handles batched ingestion |
| **Drop the score-string normalisation in the SQL** | Cleaner ranking display — score lines like "1–6" rendered with en-dash, not ASCII hyphen | `engagement.py → join_with_stage2()` |
| **Add a `season` selector to the dashboard** | Once multi-season data is in, the Evidence pages already have `<Dropdown>` patterns to reuse | `dashboard/app/pages/index.md` |
| **Build a CLI quick-stats command** | `python -m fansphere stats <match_id>` for terminal-level inspection without firing up Evidence | New file `src/cli.py` |
| **Cache the parquet writes** | `npm run sources` re-renders every table; only rebuild when source CSVs change | `dashboard/app/sources/fansphere/*.sql` add `materialized` keyword |

### High-impact, medium-effort *(week-long features)*

| Feature | What it gives you | Where to start |
|---|---|---|
| **Replace VADER with a fine-tuned transformer** | Better handling of sarcasm, code-switching (Spanish ↔ English ↔ Catalan), and rivalry-specific idioms. The `SentimentAnalyzer` ABC in `src/sentiment.py` already has a `TransformerAnalyzer` stub. | `cardiffnlp/twitter-roberta-base-sentiment-latest` via HuggingFace pipeline |
| **Real-time ingestion** | Switch from Pushshift archives to the live Reddit API for current matches. The `BaseRedditConnector` ABC was designed for exactly this swap. | Implement `LiveConnector(BaseRedditConnector)` in `src/load_reddit_archive.py` |
| **Add a fan-graph view** | Build the comment-reply network into a graph; surface influencer nodes per fanbase. Visualisable as a force-directed scatter in Evidence. | `networkx` on `comments_enriched` joined with parent-comment IDs (would need to extend the Reddit ingest to keep `parent_id`) |
| **Multi-league expansion** | Add Premier League (`r/PremierLeague`, `r/soccer`, club subs) and Champions League knockouts. Cross-league rivalry comparison opens up. | `config/team_aliases.yaml` is structured for this; add team blocks |
| **Per-player sentiment breakdown** | Use spaCy NER on comment bodies to tag player names, then aggregate sentiment per player per match. Surfaces "fans angry at Griezmann but cheering Pedri" type insights. | New module `src/player_sentiment.py`; feeds a new `player_sentiment` table |

### High-impact, high-effort *(month-plus initiatives)*

| Feature | What it gives you |
|---|---|
| **Causal model: events → sentiment shifts** | Move beyond correlation. Use the goal-event timestamps as natural intervention points and fit a CausalImpact / interrupted time-series model on the comment-curve to attribute sentiment swings to specific goals, red cards, or substitutions. |
| **Multilingual sentiment** | Train a custom classifier on Catalan/Spanish/English mixed-language football comments. Existing transformer models are weaker on multilingual sports text than they look on benchmarks. |
| **Predictive engagement scoring** | Given pre-match features (fixture, line-ups, weather, rivalry flag, team form), predict the expected engagement score. Useful for content scheduling. Tree-based regressor (XGBoost / LightGBM) on the historical engagement table. |
| **Cross-platform sentiment fusion** | Add Twitter / X, Instagram comments, TikTok captions. Each platform has different sentiment baselines — the interesting work is normalising them. |

### Architecture refactors I'd prioritise

- Promote `engagement.py` weights into a YAML config so business users can re-weight without touching code. Currently hard-coded.
- Move from notebook-driven Stage 3 to a proper Airflow / Prefect DAG. Notebooks are fine for portfolio; not for production.
- Add `pytest` coverage for the linker (`link_comments_to_matches.py`) — it's the riskiest piece and untested. Golden-file tests against a hand-labelled subset would catch regressions when the rules change.
- Replace the Postgres optional path with DuckDB-only. The two-store architecture is now legacy; DuckDB handles everything the dashboard needs.

---

## 2. Commercial use cases

If FanSphere AI were spun out into a product, these are the buyers and the pitches.

### Clubs — commercial & sponsorship teams

**The pitch:** *"We tell you which fixtures actually moved your fanbase — not just which ones generated noise."*

The Clásico paradox in this very repo is the wedge. A club's commercial team is selling sponsorship inventory and content placements. The natural-but-wrong instinct is to price El Clásico as the premium product because it draws the most volume. The data says the *Levante 3–3* draw drove higher *engaged* fan reaction. Putting a sponsor's mid-tier activation against that fixture is a better-priced trade than burying them in Clásico clutter.

**What we'd sell:**
- Per-fixture engagement scores in advance (predictive model from the roadmap)
- Cohort-sized activation windows (Hardcore Core fans are 3% of the audience but 30% of the conversation — that's a targetable cohort)
- Rivalry-adjusted hype scoring for ticket pricing

**Competitive landscape:** Genius Sports, Stats Perform, Two Circles. We compete on transparency — every score has a documented formula, every link has a confidence value. Black-box models lose contracts when a club's analyst can't defend the number to the CMO.

### Broadcasters & rights-holders

**The pitch:** *"Programme your content calendar around fan emotional peaks, not just match scheduling."*

A broadcaster running a digital channel (DAZN, Movistar+, ESPN+) wants to publish post-match content when fan attention is peaking. The volume curve on the Match Lens page shows that peak is *not* the final whistle — it's 15–30 minutes after, when fans are processing the result. Push the content there.

**What we'd sell:**
- Recommended content-drop windows per fixture (derived from the comment volume curve)
- Sentiment-pre-screened reaction clips (use comment sentiment as a signal for what to feature in highlight packages)
- Fanbase-mood reports for production briefings

### Betting operators

**The pitch:** *"Fan sentiment is a leading indicator we can correlate with in-play betting market movements."*

Volatility in fan sentiment during the match tends to precede price moves in in-play markets. We don't sell odds prediction — we sell the signal feed. Quants integrate it however they want.

**What we'd sell:**
- Real-time sentiment-volatility feed by match (requires the real-time ingestion roadmap item)
- Per-team sentiment indices used as model inputs
- Anomaly alerts when sentiment swings break thresholds

**Caveat:** this is the most regulatorily-exposed buyer; treat carefully. Don't sell anything that looks like a "tipping" signal.

### Sponsorship measurement agencies

**The pitch:** *"Quantified brand-association uplift from sponsorship placements, beyond impression counting."*

Currently, sponsorship ROI is measured in impressions and brand-mention counts. Adding sentiment-tagged mentions (was the brand mentioned positively or negatively?) is a more defensible measurement layer for the agency selling to brands.

**What we'd sell:**
- Sentiment-tagged brand mention reports per campaign
- Comparison of activation impact across fixtures (which Clásico generated more positive sponsor mentions — the one your activation was at, or the one at your competitor's?)
- Year-on-year sentiment trend lines per partnership

### Fan engagement platforms (loyalty, CRM)

**The pitch:** *"Your loyalty program doesn't know which segment of your fanbase is which. We do."*

The Tribes segmentation is the wedge: Casuals get email blasts; Tacticals get tactical-deep-dive content; Hardcore gets early-access drops and meet-the-team perks. The same comms volume produces dramatically different engagement when targeted by behavioural cohort.

**What we'd sell:**
- Author-level cluster labels via API (cluster ID + confidence)
- Cohort sizing for campaign planning
- Cohort-level sentiment trends over time

---

## 3. Research & academic extensions

The dataset and the pipeline both invite empirical research questions that go beyond the dashboard's descriptive output.

### Causal: do goals cause sentiment shifts, or just precede them?

The comment-curve data has fine-grained timestamps (`minutes_from_kickoff`). The goal-event data has matched timestamps. Standard causal inference toolkit applies:

- **Method**: Interrupted time-series with the goal events as interventions. Pre/post sentiment averages with a counterfactual modelled on quiet periods.
- **Specifically interesting test**: Does an opponent's goal produce a larger sentiment shift than your own team's goal? (Hypothesis: yes, because losses are more emotionally salient than wins — Kahneman's prospect theory in football form.)
- **Data needed**: Already in `comments_enriched` + `goal_events`. No new collection required.

### Cross-cultural fanbase comparison

The dataset includes `r/barca` (Catalan + Spanish + English speakers; club aligned with Catalan identity) and `r/realmadrid` (Spanish + English; aligned with Madrid / "national" identity). Hypothesis worth testing:

- **Claim to test**: Catalan-identifying fans express sentiment differently — more political coding, more siege-mentality language during rivalry matches.
- **Method**: Fine-tune a multilingual sentiment model with explicit Catalan support; compare sentiment distributions for the same match across both subreddits.
- **Why it matters**: Most football sentiment research treats fanbases as homogeneous. They're not. Cultural identity moderates the relationship between match events and fan reaction.

### Rivalry-amplification model

The current pipeline flags rivalry as a binary (`is_rivalry`). A more interesting model treats rivalry as a continuous "amplification coefficient" learned from the data.

- **Method**: Mixed-effects regression with sentiment volatility as the outcome, match events as predictors, and a fanbase-pair random effect. The fitted random-effect coefficient *is* the rivalry-amplification score for that pair.
- **Output**: A continuous rivalry score per fanbase pair, learned end-to-end rather than hand-coded. Could replace the curated `RIVALRY_PAIRS` list with a data-driven one.

### Information-theoretic engagement measure

The current composite engagement score is a weighted blend. A more principled measure is *mutual information* between match events and fan sentiment:

- **Method**: Discretise sentiment into bins; compute MI between binned sentiment and event types (goal, card, substitution, half-time). Matches with high MI are "informationally engaged" — fan sentiment reflects what's happening on the pitch.
- **Why it's interesting**: A low-MI match might be one where fans are arguing about something *off* the pitch (a transfer rumour, a manager controversy) regardless of the result. Identifying these gives commercial teams a heads-up on narrative-driven engagement spikes.

### Author embedding space

KMeans on 5 hand-picked features is a deliberate baseline. A natural research extension:

- **Method**: Train an author-level embedding using either (a) a doc2vec-style model on each author's concatenated comments, or (b) a graph embedding (node2vec) on the reply network. Cluster the embeddings.
- **Hypothesis**: Embedding-based clusters will surface micro-segments that hand-picked features miss — e.g. "match-thread regulars who never post outside game-time" vs. "all-week tactical posters who barely engage during matches."
- **Validation**: Inter-cluster sentiment patterns, comment-length distributions, and predictive utility for behavioural outcomes (does a cluster forecast retention?).

### Open dataset contribution

The 93,298 linked comments + sentiment + segmentation labels are a non-trivial dataset for sports-NLP research. With minor cleanup (PII scrubbing, dedup, license clarification), this could be released as an open benchmark:

- **Use cases**: training/eval of football-specific sentiment models, fan-segmentation baselines, multilingual sports NLP.
- **Practical step**: publish to HuggingFace Datasets or Kaggle with a model card and intended-use statement.

---

## Closing note

The above is intentionally optimistic. The current FanSphere AI repo is a deliberately small system that demonstrates pipeline thinking end to end. None of the extensions above require throwing away what's here — every roadmap item slots into the existing module boundaries.

If only one extension were prioritised, it would be **multi-season expansion** (low effort, high impact on statistical credibility) followed by the **transformer sentiment upgrade** (medium effort, the most defensible single quality improvement).
