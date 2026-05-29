# Power BI Dashboard — Build Guide

This guide builds the FanSphere AI dashboard directly from the CSV / parquet
outputs in `outputs/` — no PostgreSQL required. Build time: ~30–40 minutes.

**Scope:** Page 1 (Executive Overview) + Page 2 (Fan Sentiment). Pages 3 & 4
are deferred to a v1.1 release.

---

## What changed from the previous guide

This guide replaces an earlier Postgres-based draft. The substantive changes
are listed here so a returning reader knows what's intentional vs. what's a
typo:

- **Data source switched** PostgreSQL → CSV + parquet. The pipeline ships
  CSV-only by default; making the dashboard depend on Postgres would break
  reproducibility for anyone cloning the repo.
- **Headline KPIs now use `engagement_score_combined`** (the
  normalised [0,1] score introduced by the Phase 0 fix), not the old
  unit-broken Stage-2 sum.
- **Page 1 now features an "Engagement Divergence" scatter** —
  `engagement_score_football_norm` × `engagement_score_fans`, one point
  per match. This visual is the El Clásico paradox in one chart and is
  intended as the README hero screenshot.
- **`sentiment_label`** (positive / neutral / negative) is now derived in
  Power Query from the VADER compound score, using VADER's standard
  thresholds (±0.05). No upstream label column exists.
- **Custom theme JSON dropped.** Using Power BI's built-in Dark theme for
  zero-config reproducibility on any install.

---

## 1. Data sources

From **Home → Get data**:

| Source | Path | Connector |
|---|---|---|
| `stage2_matches` | `outputs/stage2_matches.csv` | Text/CSV |
| `stage3_engagement_enriched` | `outputs/stage3_engagement_enriched.csv` | Text/CSV |
| `stage3_comments_linked` | `outputs/stage3_comments_linked.parquet` | Parquet |

Set the data connectivity to **Import** for all three.

> If the parquet connector isn't visible: Get data → File → Parquet.
> Available in Power BI Desktop 2021-09 and later.

---

## 2. Power Query transforms

### `stage2_matches`

- Verify `match_date` is typed as **Date**.
- Verify `home_score`, `away_score`, `total_goals` are typed as **Whole Number**.
- Verify `is_rivalry` is typed as **True/False**.
- Add custom column **`match_label`**:
  ```
  [home_team] & " vs " & [away_team]
  ```
- Add custom column **`score_str`** (if not already present from Phase 0):
  ```
  Text.From([home_score]) & "–" & Text.From([away_score])
  ```

### `stage3_engagement_enriched`

- Verify all `engagement_score_*` columns are typed as **Decimal Number**.
- Verify `fan_comment_count` is typed as **Whole Number**.
- Remove the duplicate metadata columns if they were re-introduced by the
  merge in the notebook (`home_team`, `away_team`, `match_date` — these
  live on `stage2_matches` as the dimension; you'll use the relationship).

### `stage3_comments_linked`

- Verify `match_id` is typed as **Whole Number** (must match
  `stage2_matches[match_id]` exactly for the relationship to fire).
- Verify `sentiment_score` is typed as **Decimal Number**.
- Convert `created_utc` to a datetime column if it's a Unix epoch:
  - Add Column → Custom Column → `#datetime(1970,1,1,0,0,0) + #duration(0,0,0,[created_utc])`
  - Or if it's already an ISO string, set type to **Date/Time**.
- Add custom column **`sentiment_label`**:
  ```
  if [sentiment_score] > 0.05 then "positive"
  else if [sentiment_score] < -0.05 then "negative"
  else "neutral"
  ```
  > These thresholds are VADER's recommended bands. Tune in the formula
  > bar if you want stricter or looser classification.
- Add custom column **`date`** = `Date.From([created_utc])`.

---

## 3. Model relationships

| From | To | Cardinality | Direction |
|---|---|---|---|
| `stage2_matches[match_id]` | `stage3_engagement_enriched[match_id]` | 1 : 1 | single |
| `stage2_matches[match_id]` | `stage3_comments_linked[match_id]` | 1 : * | single |

### Date table

Add a date table sized to the actual data window:

```DAX
DateTable =
ADDCOLUMNS (
    CALENDAR ( DATE ( 2020, 9, 1 ), DATE ( 2021, 6, 30 ) ),
    "Year",       YEAR ( [Date] ),
    "Month",      FORMAT ( [Date], "MMM" ),
    "MonthNum",   MONTH ( [Date] ),
    "WeekNum",    WEEKNUM ( [Date] )
)
```

Mark as date table. Connect `DateTable[Date]` → `stage3_comments_linked[date]`
(single direction). Optional: also connect → `stage2_matches[match_date]`.

---

## 4. DAX measures

Create a `_Measures` table (Enter Data → empty table named `_Measures`) and
add the following:

```DAX
-- Match-level (from stage3_engagement_enriched) -----------------------
Avg Combined Engagement =
AVERAGE ( stage3_engagement_enriched[engagement_score_combined] )

Top Combined Score =
MAX ( stage3_engagement_enriched[engagement_score_combined] )

Top Match Label =
VAR _MaxScore = [Top Combined Score]
RETURN
CALCULATE (
    SELECTEDVALUE ( stage2_matches[match_label] ),
    FILTER (
        ALL ( stage3_engagement_enriched ),
        stage3_engagement_enriched[engagement_score_combined] = _MaxScore
    )
)

Avg Football Norm =
AVERAGE ( stage3_engagement_enriched[engagement_score_football_norm] )

Avg Fan Score =
AVERAGE ( stage3_engagement_enriched[engagement_score_fans] )

Total Fan Comments =
SUM ( stage3_engagement_enriched[fan_comment_count] )

Match Rank =
RANKX (
    ALL ( stage3_engagement_enriched[match_id] ),
    [Avg Combined Engagement],
    ,
    DESC,
    DENSE
)

-- Comment-level (from stage3_comments_linked) -------------------------
Mean Sentiment =
AVERAGE ( stage3_comments_linked[sentiment_score] )

Comment Count =
COUNTROWS ( stage3_comments_linked )

Positive Comments =
CALCULATE (
    [Comment Count],
    stage3_comments_linked[sentiment_label] = "positive"
)

Negative Comments =
CALCULATE (
    [Comment Count],
    stage3_comments_linked[sentiment_label] = "negative"
)

Sentiment Net Score =
DIVIDE (
    [Positive Comments] - [Negative Comments],
    [Comment Count]
)

Sentiment Volatility =
STDEV.P ( stage3_comments_linked[sentiment_score] )
```

---

## 5. Theme

**View → Themes → Dark.**

That's the entire step. The built-in dark theme provides usable contrast
and matches Power BI's published defaults. Typography stays at its default
Segoe UI.

Optional polish that doesn't require a custom theme:
- Set page background to a dark grey (`#1A1F2B`) for card-on-page separation.
- Use white for visual titles, `#9CA3AF` for subtitles.
- Reserve red (`#EF4444`) for negative deltas only; default chart palette
  for everything else.

---

## 6. Page 1 — Executive Overview

**Intent:** in five seconds, communicate the headline finding — combined
engagement ranks the matches differently than raw fan volume would.

| # | Visual | Type | Fields |
|---|---|---|---|
| 1 | Top Match | Card | `[Top Match Label]` with subtitle showing `[Top Combined Score]` formatted as 0.000 |
| 2 | Total Fan Comments | Card | `[Total Fan Comments]` (expect ~93K) |
| 3 | Avg Combined Score | Card | `[Avg Combined Engagement]` formatted as 0.000 |
| 4 | Rivalry Matches | Card | `CALCULATE(COUNTROWS(stage2_matches), stage2_matches[is_rivalry] = TRUE)` |
| 5 | **Engagement Divergence** ⭐ | Scatter | X: `Avg Football Norm` · Y: `Avg Fan Score` · Details: `stage2_matches[match_label]` · Size: `SUM(stage2_matches[total_goals])` · Legend: `stage2_matches[is_rivalry]` |
| 6 | Combined Engagement Ranking | Bar chart (horizontal) | Y: `stage2_matches[match_label]` · X: `Avg Combined Engagement` · sort descending · data labels on |

### Notes on visual #5 (the headline scatter)

This is the most important chart in the project. To make it readable:

- **Axis ranges:** lock both X and Y to **0–1**. Right-click axis → Format →
  X axis / Y axis → Start = 0, End = 1.
- **Reference line:** add a diagonal y = x line (Format → Analytics → Median
  / Constant line — Power BI doesn't natively do y=x, easiest workaround is
  to draw a shape line from (0,0) to (1,1) over the chart, or add a
  constant line at Y = 0.5 and call out the diagonal in the title).
- **Title:** "Where fan attention and on-pitch excitement diverge".
- **Subtitle:** "Above the diagonal: fans engaged more than the football
  warranted. Below: the opposite."
- **Annotation:** highlight the El Clásico point with a text label.

### Notes on visual #6 (ranking bar)

Sort by `Avg Combined Engagement` descending. Add the combined score as a
data label (formatted 0.000). This bar replaces the table-style "Top
matches" in the previous guide because a bar is faster to scan and gives
the same information.

---

## 7. Page 2 — Fan Sentiment

**Intent:** show that across 93K linked comments, sentiment varied
meaningfully by match and by subreddit — not just in volume but in tone
and polarisation.

| # | Visual | Type | Fields |
|---|---|---|---|
| 1 | Mean Sentiment | Card | `[Mean Sentiment]` formatted as +0.000 |
| 2 | Sentiment Net Score | Card with conditional colour | `[Sentiment Net Score]` — green if > 0, red if < 0 |
| 3 | Mean sentiment over time | Line chart | X: `DateTable[Date]` · Y: `[Mean Sentiment]` · add a constant line at 0 |
| 4 | Sentiment mix per match | 100% stacked bar | Y: `stage2_matches[match_label]` (sorted by total comments desc) · X: `[Comment Count]` · Legend: `stage3_comments_linked[sentiment_label]` |
| 5 | Subreddit comparison | Clustered column | X: `stage3_comments_linked[subreddit]` · Y: `[Comment Count]` and `[Mean Sentiment]` (dual axis) |

### Notes on visual #4 (sentiment mix per match)

This is Page 2's headline. Sort the Y axis by total comment volume so the
most-discussed matches appear at the top, then the % positive / neutral /
negative bars expose which fanbases were celebrating vs. furious.

Colour legend: positive → green, neutral → grey, negative → red.

### Notes on visual #5 (subreddit comparison)

You only have two subreddits in the linked data (`r/Barca`, `r/realmadrid`),
so this is a 2-bar chart. The interesting comparison is the dual axis:
volume + tone side-by-side. The fanbase with higher volume isn't
necessarily the one with more positive tone.

---

## 8. Page polish

Apply to both pages:

- Lock alignment to an **8 px grid** (View → Snap to Grid).
- Limit to **6 visuals per page**.
- Single accent colour per page (Page 1 uses default blue, Page 2 uses
  green/red for sentiment).
- Page title in white, 24pt; subtitle in `#9CA3AF`, 11pt.
- Footer line: "FanSphere AI · La Liga 2020/21 · n = 10 matches, 93,298
  linked comments" — small, `#6B7280`, bottom-left.

---

## 9. Screenshot capture checklist

For the README hero block, capture in this order:

| File | Source | What to crop |
|---|---|---|
| `assets/dashboard_p1_overview.png` | Page 1 full | Whole page including footer |
| `assets/dashboard_p1_divergence.png` | Page 1 visual #5 only | Just the scatter, tight crop |
| `assets/dashboard_p2_sentiment.png` | Page 2 full | Whole page |

Export each at **1920 × 1080** (Power BI: File → Export → PowerPoint for
the page-level shots, or Win+Shift+S for tight crops). PNG, not JPEG.

Reference the divergence scatter alone (`dashboard_p1_divergence.png`) in
the README's *Results* section, directly above the ranking table.

---

## Reference: what each visual tells the recruiter

| Visual | Skill it signals |
|---|---|
| Engagement Divergence scatter | Conceptual modelling — you found a real divergence in the data and built a chart that exposes it |
| 100% stacked sentiment-mix bar | Categorical NLP downstream — you derived labels from continuous VADER scores and aggregated them per match |
| Subreddit dual-axis | You handled volume × tone as two different signals on the same axis without conflating them |
| Combined Engagement ranking | Honest composite scoring — both components visible, [0,1] scale, normalisation transparent |
