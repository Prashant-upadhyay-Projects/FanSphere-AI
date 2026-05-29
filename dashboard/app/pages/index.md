---
title: Executive Overview
sidebar_position: 1
hide_title: true
full_width: true
---

<!-- HERO ====================================================== -->

<div class="hero">
  <div class="hero-brand">
    <div class="hero-logo">FS</div>
    <div>
      <div class="hero-title">FanSphere AI</div>
      <div class="hero-sub">La Liga 2020/21 · Fan engagement intelligence platform</div>
    </div>
  </div>
  <div class="hero-meta">
    <span class="chip chip-crimson">10 fixtures</span>
    <span class="chip">907K comments analysed</span>
    <span class="chip">VADER sentiment + KMeans (k=3)</span>
    <span class="chip">3,628 authors clustered</span>
  </div>
</div>

<!-- HEADLINE KPIS ============================================== -->

```sql kpi_headline
select
    sum(fan_comment_count)::int                      as total_comments,
    avg(engagement_score_combined)                   as avg_combined,
    avg(engagement_score_football_norm)              as avg_football,
    avg(engagement_score_fans)                       as avg_fans,
    count(*) filter (where is_rivalry)               as n_rivalry,
    count(*)                                         as n_matches
from fansphere.engagement
```

```sql kpi_rivalry_premium
select
    avg(case when is_rivalry then engagement_score_combined end) as rivalry_avg,
    avg(case when not is_rivalry then engagement_score_combined end) as non_rivalry_avg,
    (avg(case when is_rivalry then engagement_score_combined end)
     - avg(case when not is_rivalry then engagement_score_combined end))
    / avg(case when not is_rivalry then engagement_score_combined end) as premium_pct
from fansphere.engagement
```

```sql kpi_top_match
select
    home_team || ' vs ' || away_team as match_label,
    score_str,
    total_goals,
    engagement_score_combined
from fansphere.ranking
where rank = 1
```

<Grid cols=4>
  <BigValue
    data={kpi_headline}
    value=total_comments
    title="Reddit comments analysed"
    fmt='#,##0'
  />
  <BigValue
    data={kpi_headline}
    value=avg_combined
    title="Avg combined engagement"
    fmt='0.000'
    comparison=avg_football
    comparisonTitle="Football side"
    comparisonFmt='0.000'
  />
  <BigValue
    data={kpi_top_match}
    value=match_label
    title="Top match by engagement"
  />
  <BigValue
    data={kpi_rivalry_premium}
    value=premium_pct
    title="Rivalry premium vs avg"
    fmt='+0.0%;-0.0%'
  />
</Grid>

<!-- FILTERS ==================================================== -->

<ButtonGroup name=rivalry_filter title="Match type" defaultValue="all">
  <ButtonGroupItem value="all" valueLabel="All matches"/>
  <ButtonGroupItem value="rivalry" valueLabel="Rivalry only"/>
  <ButtonGroupItem value="non" valueLabel="Non-rivalry"/>
</ButtonGroup>

<!-- ======================================================= -->

## Where fan attention and on-pitch excitement diverge

A point above the diagonal means fans engaged *more* than the football
itself warranted — and vice versa. Bubble size = total goals in the match.
**This single chart is the El Clásico paradox.**

```sql divergence
select
    home_team || ' vs ' || away_team as match_label,
    score_str,
    engagement_score_football_norm  as football,
    engagement_score_fans           as fans,
    total_goals,
    is_rivalry,
    case when is_rivalry then 'Rivalry (El Clásico)' else 'Non-rivalry' end as category
from fansphere.engagement
where 1=1
  ${inputs.rivalry_filter.value === 'rivalry' ? "and is_rivalry" : ""}
  ${inputs.rivalry_filter.value === 'non' ? "and not is_rivalry" : ""}
```

<ScatterPlot
  data={divergence}
  x=football
  y=fans
  size=total_goals
  series=category
  colorPalette={['#E11D5C','#94A3B8']}
  xMin=0 xMax=1.05
  yMin=0 yMax=1.0
  xAxisTitle="On-pitch engagement (normalised)"
  yAxisTitle="Fan engagement (normalised)"
  pointLabels=match_label
  pointLabelPosition=top
  chartAreaHeight=400
>
  <ReferenceLine
    x=0 y=0 x2=1 y2=1
    color=grey
    lineType=dashed
    label="fans matched the football"
    labelPosition=topRight
  />
</ScatterPlot>

<Alert status="info">
  <strong>How to read this:</strong> The diagonal is "fans matched the football."
  Both El Clásicos sit far above the diagonal — fans went off even though the on-pitch excitement was mid-pack.
  Real Sociedad 1–6 Barcelona sits far to the right: 7 goals, only moderate fan reaction.
  <em>Fans don't just react to goals — they react to stakes.</em>
</Alert>

<!-- ======================================================= -->

## Combined engagement ranking

The composite score = ½ × on-pitch (normalised) + ½ × fan-side.
Crimson bars mark rivalry fixtures.

```sql ranking_bar
select
    rank,
    home_team || ' vs ' || away_team as match_label,
    engagement_score_combined as score,
    case when is_rivalry then 'Rivalry' else 'Non-rivalry' end as category
from fansphere.ranking
order by engagement_score_combined desc
```

<BarChart
  data={ranking_bar}
  x=match_label
  y=score
  series=category
  colorPalette={['#E11D5C','#94A3B8']}
  swapXY=true
  sort=false
  yAxisTitle="Combined engagement score [0, 1]"
  xAxisTitle=""
  yFmt='0.000'
  chartAreaHeight=420
  labels=true
  labelFmt='0.000'
/>

<!-- ======================================================= -->

## Full ranking with detail

Color intensity = magnitude within each numeric column.

```sql ranking_detail
select
    rank as "#",
    home_team || ' vs ' || away_team as "Match",
    match_date as "Date",
    score_str as "Score",
    total_goals as "Goals",
    is_rivalry as "Rivalry",
    fan_comment_count as "Fan comments",
    engagement_score_fans as "Fan score",
    engagement_score_football_norm as "Football score",
    engagement_score_combined as "Combined"
from fansphere.ranking
order by rank
```

<DataTable
  data={ranking_detail}
  rows=10
  rowShading=true
>
  <Column id="#" align=center/>
  <Column id="Match" wrap=true/>
  <Column id="Date" fmt='dd mmm yyyy'/>
  <Column id="Score" align=center/>
  <Column id="Goals" align=center/>
  <Column id="Rivalry" contentType=delta deltaSymbol=false/>
  <Column id="Fan comments" fmt='#,##0' contentType=colorscale colorScale=engagement/>
  <Column id="Fan score" fmt='0.000' contentType=colorscale colorScale=engagement/>
  <Column id="Football score" fmt='0.000' contentType=colorscale colorScale=engagement/>
  <Column id="Combined" fmt='0.000' contentType=colorscale colorScale=engagement/>
</DataTable>

<!-- ======================================================= -->

## The story this dashboard tells

**El Clásico generates the most raw fan volume — but doesn't win on
combined score.** The Apr 2021 Clásico saw 17,089 comments (the
highest in the dataset), yet ranks #7 of 10 on combined engagement
because it had only 3 goals.

**The biggest goal-fests rank highest.** Real Sociedad 1–6 Barcelona
(7 goals) and Barcelona 5–2 Real Betis (7 goals) take the top two
slots — the composite score weights on-pitch excitement equally with
fan reaction, and 7 goals normalises to a perfect football score.

**Fan volatility tells you what the average doesn't.** Fans argue
during rivalry games even when their team wins. The sentiment volatility
analysis on Page 4 (Sentiment Timeline) shows this clearly — non-rivalry
wins have the calmest fanbases, regardless of margin.

<div class="page-footer">
  <span>Pipeline: StatsBomb → Reddit Pushshift → VADER → KMeans → Evidence.dev · Methodology details on Page 5</span>
</div>

<style>
  /* Widen the page — overrides Evidence default max-width */
  .content-container,
  .content,
  main {
    max-width: 1400px !important;
  }

  /* HERO */
  .hero {
    background: linear-gradient(135deg, rgba(225,29,92,0.10) 0%, rgba(225,29,92,0) 60%);
    border: 1px solid var(--grey-200);
    border-radius: 16px;
    padding: 28px 32px;
    margin: 0 0 28px 0;
    display: flex;
    flex-direction: column;
    gap: 18px;
  }
  .hero-brand { display: flex; align-items: center; gap: 16px; }
  .hero-logo {
    width: 56px; height: 56px;
    background: var(--primary);
    color: white;
    border-radius: 12px;
    display: flex; align-items: center; justify-content: center;
    font-weight: 800; font-size: 18px; letter-spacing: -0.5px;
    box-shadow: 0 4px 16px rgba(225,29,92,0.30);
  }
  .hero-title {
    font-size: 30px; font-weight: 700; letter-spacing: -0.5px;
    line-height: 1.1;
  }
  .hero-sub {
    font-size: 14px; color: var(--grey-500); margin-top: 5px;
  }
  .hero-meta { display: flex; flex-wrap: wrap; gap: 8px; }
  .chip {
    display: inline-block;
    background: var(--grey-100);
    color: var(--grey-700);
    padding: 4px 12px;
    border-radius: 99px;
    font-size: 12px;
    font-weight: 500;
  }
  .chip-crimson {
    background: rgba(225,29,92,0.15);
    color: var(--primary);
  }

  /* Section headings (H2) — cyan, descriptive, with subtle underline */
  h2 {
    color: #22D3EE !important;
    font-size: 20px !important;
    font-weight: 600 !important;
    letter-spacing: -0.01em;
    margin-top: 40px !important;
    margin-bottom: 8px !important;
    padding-bottom: 6px;
    border-bottom: 1px solid rgba(34,211,238,0.20);
  }
  /* Optional darker-cyan variant if too bright in light mode */
  @media (prefers-color-scheme: light) {
    h2 { color: #0891B2 !important; border-bottom-color: rgba(8,145,178,0.25); }
  }

  .page-footer {
    margin-top: 48px;
    padding-top: 20px;
    border-top: 1px solid var(--grey-200);
    font-size: 12px;
    color: var(--grey-500);
  }
</style>
